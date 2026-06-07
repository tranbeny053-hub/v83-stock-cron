"""Fail-closed market-data validation."""

from __future__ import annotations

from datetime import UTC, datetime
from math import isfinite

from crypto_probability_engine.adapters.types import MarketCandle, MarketSnapshot, OrderBookSnapshot
from crypto_probability_engine.api.schemas import ErrorCode
from crypto_probability_engine.config.defaults import (
    DEFAULT_PHASE1A,
    TIMEFRAME_SECONDS,
    min_history_for,
)


class DataValidationError(ValueError):
    def __init__(self, code: ErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code


def _ensure_utc(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise DataValidationError(ErrorCode.SCHEMA_VALIDATION_FAILED, f"{field_name} must be UTC.")
    if value.utcoffset().total_seconds() != 0:
        raise DataValidationError(ErrorCode.SCHEMA_VALIDATION_FAILED, f"{field_name} must be UTC.")


def _ensure_finite(value: float, field_name: str) -> None:
    if not isfinite(value):
        raise DataValidationError(
            ErrorCode.SCHEMA_VALIDATION_FAILED,
            f"{field_name} must be finite.",
        )


def _validate_candle(candle: MarketCandle) -> None:
    _ensure_utc(candle.open_time_utc, "open_time_utc")
    _ensure_utc(candle.close_time_utc, "close_time_utc")
    if candle.close_time_utc <= candle.open_time_utc:
        raise DataValidationError(ErrorCode.SCHEMA_VALIDATION_FAILED, "Candle interval is invalid.")
    for field_name in ("open", "high", "low", "close", "volume"):
        value = getattr(candle, field_name)
        _ensure_finite(value, field_name)
        if value < 0:
            raise DataValidationError(
                ErrorCode.SCHEMA_VALIDATION_FAILED,
                f"{field_name} is negative.",
            )
    if candle.low > candle.high:
        raise DataValidationError(ErrorCode.SCHEMA_VALIDATION_FAILED, "Candle low exceeds high.")
    if candle.open > candle.high or candle.close > candle.high:
        raise DataValidationError(ErrorCode.SCHEMA_VALIDATION_FAILED, "Candle price exceeds high.")
    if candle.open < candle.low or candle.close < candle.low:
        raise DataValidationError(ErrorCode.SCHEMA_VALIDATION_FAILED, "Candle price below low.")


def validate_candles(
    candles: tuple[MarketCandle, ...],
    timeframe: str,
    *,
    now_utc: datetime | None = None,
    min_bars: int | None = None,
) -> None:
    if timeframe not in TIMEFRAME_SECONDS:
        raise DataValidationError(ErrorCode.SCHEMA_VALIDATION_FAILED, "Unsupported timeframe.")
    required_bars = min_bars if min_bars is not None else min_history_for(timeframe)
    if len(candles) < required_bars:
        raise DataValidationError(ErrorCode.INSUFFICIENT_DATA, "Insufficient candle history.")

    last_close: datetime | None = None
    expected_seconds = TIMEFRAME_SECONDS[timeframe]
    seen_opens: set[datetime] = set()
    for candle in candles:
        _validate_candle(candle)
        if candle.open_time_utc in seen_opens:
            raise DataValidationError(
                ErrorCode.SCHEMA_VALIDATION_FAILED,
                "Duplicate candle timestamp.",
            )
        seen_opens.add(candle.open_time_utc)
        if last_close is not None and candle.open_time_utc != last_close:
            gap_seconds = abs((candle.open_time_utc - last_close).total_seconds())
            if gap_seconds >= expected_seconds:
                raise DataValidationError(
                    ErrorCode.SCHEMA_VALIDATION_FAILED,
                    "Gap in candle series.",
                )
        last_close = candle.close_time_utc

    now = now_utc or datetime.now(UTC)
    _ensure_utc(now, "now_utc")
    age_seconds = (now - candles[-1].close_time_utc).total_seconds()
    if age_seconds > expected_seconds * DEFAULT_PHASE1A.freshness_multiplier:
        raise DataValidationError(ErrorCode.STALE_CANDLES, "Latest candle is stale.")


def validate_order_book(book: OrderBookSnapshot | None) -> None:
    if book is None:
        return
    _ensure_utc(book.as_of_utc, "order_book.as_of_utc")
    if not book.bids or not book.asks:
        raise DataValidationError(ErrorCode.PROVIDER_DEGRADED, "Order book is empty.")
    best_bid = book.bids[0].price
    best_ask = book.asks[0].price
    for level in (*book.bids, *book.asks):
        _ensure_finite(level.price, "book.price")
        _ensure_finite(level.size, "book.size")
        if level.price <= 0 or level.size < 0:
            raise DataValidationError(ErrorCode.SCHEMA_VALIDATION_FAILED, "Invalid book level.")
    if best_bid >= best_ask:
        raise DataValidationError(ErrorCode.DATA_CONFLICT, "Order book is crossed or locked.")


def validate_market_snapshot(snapshot: MarketSnapshot, *, min_bars: int | None = None) -> None:
    _ensure_utc(snapshot.as_of_utc, "snapshot.as_of_utc")
    validate_candles(
        snapshot.candles,
        snapshot.timeframe,
        now_utc=snapshot.as_of_utc,
        min_bars=min_bars,
    )
    validate_order_book(snapshot.order_book)


def assert_snapshots_coherent(
    left: MarketSnapshot,
    right: MarketSnapshot,
    *,
    tolerance_bps: float = DEFAULT_PHASE1A.price_disagreement_bps,
) -> None:
    report = snapshot_coherence_report(left, right, tolerance_bps=tolerance_bps)
    if report["status"] != "OK":
        raise DataValidationError(ErrorCode.DATA_CONFLICT, report["reason"])


def snapshot_coherence_report(
    left: MarketSnapshot,
    right: MarketSnapshot,
    *,
    tolerance_bps: float = DEFAULT_PHASE1A.price_disagreement_bps,
) -> dict:
    left_candle, right_candle = _latest_common_closed_candles(left, right)
    left_price = left_candle.close
    right_price = right_candle.close
    _ensure_finite(left_price, "left_price")
    _ensure_finite(right_price, "right_price")
    mid = (left_price + right_price) / 2.0
    if mid <= 0:
        raise DataValidationError(ErrorCode.DATA_CONFLICT, "Invalid comparison price.")
    disagreement_bps = abs(left_price - right_price) / mid * 10_000.0
    status = "OK" if disagreement_bps <= tolerance_bps else "DATA_CONFLICT"
    reason = "Providers are coherent." if status == "OK" else "Provider price conflict."
    return {
        "status": status,
        "reason": reason,
        "left_provider": left.provider,
        "right_provider": right.provider,
        "aligned_open_time_utc": _as_z(left_candle.open_time_utc),
        "aligned_close_time_utc": _as_z(left_candle.close_time_utc),
        "left_price": left_price,
        "right_price": right_price,
        "disagreement_bps": round(disagreement_bps, 6),
        "tolerance_bps": tolerance_bps,
    }


def _latest_common_closed_candles(
    left: MarketSnapshot,
    right: MarketSnapshot,
) -> tuple[MarketCandle, MarketCandle]:
    closed_cutoff = min(left.as_of_utc, right.as_of_utc)
    left_by_close = {
        candle.close_time_utc: candle
        for candle in left.candles
        if candle.close_time_utc <= closed_cutoff
    }
    right_by_close = {
        candle.close_time_utc: candle
        for candle in right.candles
        if candle.close_time_utc <= closed_cutoff
    }
    common_closes = sorted(set(left_by_close) & set(right_by_close))
    if not common_closes:
        raise DataValidationError(
            ErrorCode.DATA_CONFLICT,
            "No equivalent closed candle bucket for provider comparison.",
        )
    close_time = common_closes[-1]
    return left_by_close[close_time], right_by_close[close_time]


def _as_z(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")
