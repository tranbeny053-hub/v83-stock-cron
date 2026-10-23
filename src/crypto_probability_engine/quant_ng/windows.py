"""PROPOSAL, UNWIRED: acquire one validated closed-candle window; this module decides nothing.

Nothing outside ``quant_ng`` imports this module. It never fetches more than once and never
falls back to a shorter window.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType

from crypto_probability_engine.adapters.candle_history import (
    CANDLE_HISTORY_MAX_BARS,
    CandleHistoryAdapter,
    assert_history_extends_snapshot,
    validate_candle_history,
)
from crypto_probability_engine.adapters.types import MarketCandle, MarketSnapshot, ProviderError
from crypto_probability_engine.normalizers.symbols import NormalizedSymbol
from crypto_probability_engine.validation.market_data import DataValidationError

TIMEFRAME_SECONDS = MappingProxyType({"15m": 900, "1H": 3_600, "4H": 14_400})


class WindowSource(StrEnum):
    SNAPSHOT = "SNAPSHOT"
    HISTORY = "HISTORY"


class UnavailableReason(StrEnum):
    TIMEFRAME_UNSUPPORTED = "TIMEFRAME_UNSUPPORTED"
    BARS_OUT_OF_RANGE = "BARS_OUT_OF_RANGE"
    SNAPSHOT_MISMATCH = "SNAPSHOT_MISMATCH"
    SHORT_SNAPSHOT = "SHORT_SNAPSHOT"
    HISTORY_FAILED = "HISTORY_FAILED"
    HISTORY_INVALID = "HISTORY_INVALID"
    HISTORY_CONFLICT = "HISTORY_CONFLICT"
    WINDOW_MALFORMED = "WINDOW_MALFORMED"


class WindowUnavailable(Exception):
    """A requested full window cannot be acquired and validated."""

    def __init__(self, reason: UnavailableReason, detail: str) -> None:
        self.reason = reason
        self.detail = detail
        super().__init__(f"{reason.value}: {detail}")


@dataclass(frozen=True)
class Window:
    """A validated, complete candle window and its source metadata."""

    provider: str
    normalized_symbol: str
    timeframe: str
    candles: tuple[MarketCandle, ...]
    source: WindowSource
    requests: int

    def __post_init__(self) -> None:
        if not self.candles:
            raise ValueError("Window candles must not be empty")

    @property
    def last_close_utc(self) -> datetime:
        return self.candles[-1].close_time_utc


def require_well_formed(candles: Sequence[MarketCandle], timeframe: str) -> None:
    """Require positive, UTC, bar-aligned candles that are ordered and exactly adjacent."""

    if timeframe not in TIMEFRAME_SECONDS:
        raise WindowUnavailable(
            UnavailableReason.TIMEFRAME_UNSUPPORTED, f"Unsupported timeframe {timeframe!r}."
        )
    if not candles:
        raise WindowUnavailable(UnavailableReason.WINDOW_MALFORMED, "Window is empty.")

    bar = TIMEFRAME_SECONDS[timeframe]
    previous: MarketCandle | None = None
    for candle in candles:
        opened, closed = candle.open_time_utc, candle.close_time_utc
        for moment in (opened, closed):
            if moment.utcoffset() is None or moment.utcoffset().total_seconds() != 0:
                raise WindowUnavailable(
                    UnavailableReason.WINDOW_MALFORMED, "Candle times must be UTC."
                )
        if (closed - opened).total_seconds() != bar:
            raise WindowUnavailable(
                UnavailableReason.WINDOW_MALFORMED, "Candles must span exactly one bar."
            )
        if int(opened.timestamp()) % bar != 0:
            raise WindowUnavailable(
                UnavailableReason.WINDOW_MALFORMED, "Candles must open on a UTC bar boundary."
            )
        if previous is not None and opened != previous.close_time_utc:
            raise WindowUnavailable(
                UnavailableReason.WINDOW_MALFORMED,
                "Candles must be ordered and exactly adjacent.",
            )
        prices = (candle.open, candle.high, candle.low, candle.close)
        if not all(math.isfinite(price) and price > 0.0 for price in prices):
            raise WindowUnavailable(
                UnavailableReason.WINDOW_MALFORMED, "Candle prices must be finite and positive."
            )
        if candle.low > candle.high:
            raise WindowUnavailable(
                UnavailableReason.WINDOW_MALFORMED, "Candle low exceeds high."
            )
        previous = candle


def acquire_window(
    snapshot: MarketSnapshot,
    *,
    symbol: NormalizedSymbol,
    bars_required: int,
    history_adapter: CandleHistoryAdapter | None = None,
    now_utc: datetime | None = None,
) -> Window:
    """Return the requested complete window, failing closed without retry or shortening."""

    if snapshot.timeframe not in TIMEFRAME_SECONDS:
        raise WindowUnavailable(
            UnavailableReason.TIMEFRAME_UNSUPPORTED,
            f"Unsupported timeframe {snapshot.timeframe!r}.",
        )
    if (isinstance(bars_required, bool) or not isinstance(bars_required, int)
            or not 1 <= bars_required <= CANDLE_HISTORY_MAX_BARS):
        raise WindowUnavailable(
            UnavailableReason.BARS_OUT_OF_RANGE,
            f"bars_required must be between 1 and {CANDLE_HISTORY_MAX_BARS}.",
        )
    if symbol.display != snapshot.normalized_symbol:
        raise WindowUnavailable(
            UnavailableReason.SNAPSHOT_MISMATCH,
            "Symbol does not match the market snapshot.",
        )
    if len(snapshot.candles) >= bars_required:
        candles = snapshot.candles[-bars_required:]
        require_well_formed(candles, snapshot.timeframe)
        return Window(
            provider=snapshot.provider,
            normalized_symbol=snapshot.normalized_symbol,
            timeframe=snapshot.timeframe,
            candles=candles,
            source=WindowSource.SNAPSHOT,
            requests=0,
        )
    if history_adapter is None:
        raise WindowUnavailable(
            UnavailableReason.SHORT_SNAPSHOT, "Snapshot does not contain enough candles."
        )

    try:
        history = history_adapter.fetch_candle_history(
            symbol, snapshot.timeframe, bars=bars_required
        )
    except DataValidationError as exc:
        raise WindowUnavailable(UnavailableReason.HISTORY_INVALID, str(exc)) from exc
    except (ProviderError, ValueError) as exc:
        raise WindowUnavailable(UnavailableReason.HISTORY_FAILED, str(exc)) from exc

    try:
        if (history.requested_bars != bars_required
                or len(history.candles) != bars_required):
            raise WindowUnavailable(
                UnavailableReason.HISTORY_INVALID,
                "Candle history does not hold exactly the requested number of candles.",
            )
        validate_candle_history(history, now_utc=now_utc)
    except ValueError as exc:
        raise WindowUnavailable(UnavailableReason.HISTORY_INVALID, str(exc)) from exc
    try:
        assert_history_extends_snapshot(history, snapshot)
    except DataValidationError as exc:
        raise WindowUnavailable(UnavailableReason.HISTORY_CONFLICT, str(exc)) from exc

    require_well_formed(history.candles, snapshot.timeframe)
    return Window(
        provider=history.provider,
        normalized_symbol=history.normalized_symbol,
        timeframe=history.timeframe,
        candles=history.candles,
        source=WindowSource.HISTORY,
        requests=history.requests,
    )
