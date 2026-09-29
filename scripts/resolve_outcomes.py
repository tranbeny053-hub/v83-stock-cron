"""Resolve due predictions using bounded candles from their exact reference-price venue.
Require an exact terminal bar, exclude lookahead, and count only successful outcome saves.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from math import isfinite
from types import MappingProxyType
from typing import Any

from crypto_probability_engine.adapters.http_client import PublicHttpClient
from crypto_probability_engine.adapters.mappers import (
    BINANCE_BASE_URL,
    OKX_BASE_URL,
    map_interval,
    parse_binance_candles,
    parse_okx_candles,
    provider_symbol,
)
from crypto_probability_engine.adapters.types import MarketCandle, ProviderError
from crypto_probability_engine.config.defaults import (
    DEFAULT_PHASE1A,
    TIMEFRAME_SECONDS,
)
from crypto_probability_engine.config.settings import Settings
from crypto_probability_engine.normalizers.symbols import normalize_symbol
from crypto_probability_engine.persistence.prediction_origin import PredictionOrigin
from crypto_probability_engine.persistence.repository import (
    InMemoryPersistenceRepository,
    PersistenceRepository,
    SupabasePersistenceRepository,
    SupabaseRestRepository,
)

RESOLVER_VERSION = "resolver-v2a-exact-eligibility"
EXACT_SOURCE_PROVIDERS = MappingProxyType({"BINANCE_PUBLIC": "binance", "OKX_PUBLIC": "okx"})
# Fixed-duration bars only. 1M uses an approximate 30-day duration, so it has no exact terminal bar.
EXACT_TIMEFRAMES = frozenset({"15m", "1H", "4H", "1D", "1W"})
MAX_WINDOW_BARS = 96
BINANCE_KLINES_PATH = "/api/v3/klines"
OKX_CANDLES_PATH = "/api/v5/market/candles"  # serves only the latest 1,440 bars
OKX_HISTORY_CANDLES_PATH = "/api/v5/market/history-candles"
OKX_RECENT_MAX_BARS_BACK = 1400  # margin below 1,440
EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


@dataclass(frozen=True)
class CandleWindow:
    provider: str
    data_source: str
    normalized_symbol: str
    timeframe: str
    first_open_utc: datetime
    terminal_open_utc: datetime
    terminal_close_utc: datetime
    bars: int
    now_utc: datetime


FetchCandles = Callable[[CandleWindow, Settings], Sequence[MarketCandle]]


def build_resolver_repository(settings: Settings) -> PersistenceRepository:
    """Build the operator resolver repository, preferring direct DB access when present."""

    if settings.supabase_db_url:
        return SupabasePersistenceRepository(settings.supabase_db_url)
    if settings.supabase_url and settings.supabase_service_role_key:
        return SupabaseRestRepository(
            settings.supabase_url,
            settings.supabase_service_role_key,
        )
    return InMemoryPersistenceRepository()


def resolve_due_predictions(
    repository: PersistenceRepository,
    *,
    settings: Settings | None = None,
    now_utc: datetime | None = None,
    limit: int = 100,
    fetch_candles: FetchCandles | None = None,
) -> dict[str, int]:
    """Resolve due predictions without mutating predictions or failing the batch."""

    settings = settings or Settings.from_env()
    now = _coerce_utc(now_utc or datetime.now(tz=UTC))
    due_predictions = repository.fetch_due_unresolved_predictions(
        now,
        limit,
        data_sources=tuple(EXACT_SOURCE_PROVIDERS),
        timeframes=tuple(sorted(EXACT_TIMEFRAMES)),
        prediction_origins=(PredictionOrigin.USER_REQUESTED.value,),
    )
    stats = {"due": len(due_predictions), "resolved": 0, "skipped": 0, "failed": 0}
    candle_fetcher = fetch_candles or fetch_public_candles
    for prediction in due_predictions:
        try:
            outcome = build_outcome_row(
                prediction,
                now_utc=now,
                settings=settings,
                fetch_candles=candle_fetcher,
            )
            if outcome is None:
                stats["skipped"] += 1
                continue
            status = repository.save_prediction_outcome(outcome)
            if status == "OK":
                stats["resolved"] += 1
            else:
                stats["failed"] += 1
        except Exception:
            stats["failed"] += 1
    return stats


def build_outcome_row(
    prediction: dict,
    *,
    now_utc: datetime,
    settings: Settings,
    fetch_candles: FetchCandles,
) -> dict | None:
    source = prediction.get("data_source")
    if not isinstance(source, str) or source not in EXACT_SOURCE_PROVIDERS:
        return None
    timeframe = prediction.get("timeframe")
    if not isinstance(timeframe, str) or timeframe not in EXACT_TIMEFRAMES:
        return None
    reference_close_utc = _parse_utc(prediction["reference_close_utc"])
    reference_price = float(prediction["reference_price"])
    horizon_end_utc = _parse_utc(prediction["horizon_end_utc"])
    if not isfinite(reference_price) or reference_price <= 0.0:
        return None
    interval = timedelta(seconds=TIMEFRAME_SECONDS[timeframe])
    span = horizon_end_utc - reference_close_utc
    if span <= timedelta(0) or span % interval != timedelta(0):
        return None
    bars = span // interval
    if bars > MAX_WINDOW_BARS:
        return None
    if prediction.get("horizon_bars") is not None:
        try:
            if int(prediction["horizon_bars"]) != bars:
                return None
        except (TypeError, ValueError, OverflowError):
            return None
    now = _coerce_utc(now_utc)
    if now <= horizon_end_utc:
        return None
    window = CandleWindow(
        provider=EXACT_SOURCE_PROVIDERS[source],
        data_source=source,
        normalized_symbol=str(prediction["normalized_symbol"]),
        timeframe=timeframe,
        first_open_utc=reference_close_utc,
        terminal_open_utc=horizon_end_utc - interval,
        terminal_close_utc=horizon_end_utc,
        bars=bars,
        now_utc=now,
    )
    candles = fetch_candles(window, settings)
    by_close: dict[datetime, MarketCandle] = {}
    for candle in candles:
        close = _coerce_utc(candle.close_time_utc)
        if not reference_close_utc < close <= horizon_end_utc:
            continue
        open_time = _coerce_utc(candle.open_time_utc)
        if close - open_time != interval:
            raise ValueError("resolver candle does not span exactly one bar")
        if close in by_close and by_close[close] != candle:
            raise ValueError("conflicting duplicate candles in resolver window")
        by_close[close] = candle
    outcome_candle = by_close.get(horizon_end_utc)
    if outcome_candle is None:
        return None
    observed = [by_close[close] for close in sorted(by_close)]
    terminal_return_frac = (float(outcome_candle.close) - reference_price) / reference_price
    decision_band_frac = _decision_band(prediction)
    return {
        "prediction_id": str(prediction["prediction_id"]),
        "resolved_at_utc": _iso_utc(now_utc),
        "outcome_close_utc": _iso_utc(horizon_end_utc),
        "outcome_reference_price": float(outcome_candle.close),
        "terminal_return_frac": terminal_return_frac,
        "realized_label": _realized_label(terminal_return_frac, decision_band_frac),
        "decision_band_frac": decision_band_frac,
        "max_favorable_frac": (max(float(candle.high) for candle in observed) - reference_price)
        / reference_price,
        "max_adverse_frac": (min(float(candle.low) for candle in observed) - reference_price)
        / reference_price,
        "candles_observed": len(observed),
        "resolver_version": RESOLVER_VERSION,
        "data_source": window.data_source,
        "is_live_data": True,
    }


def fetch_public_candles(
    window: CandleWindow,
    settings: Settings,
) -> Sequence[MarketCandle]:
    """Fetch a bounded candle window from the reference-price venue only."""

    normalized = normalize_symbol(window.normalized_symbol)
    client = PublicHttpClient.from_settings(settings)
    timeframe = window.timeframe
    provider = window.provider
    if provider == "binance":
        interval_ms = TIMEFRAME_SECONDS[timeframe] * 1000
        payload = client.get_json(
            base_url=BINANCE_BASE_URL,
            path=BINANCE_KLINES_PATH,
            params={
                "symbol": provider_symbol(normalized, provider),
                "interval": map_interval(timeframe, provider),
                "startTime": _millis(window.first_open_utc),
                "endTime": _millis(window.terminal_close_utc) + interval_ms,
                "limit": window.bars + 3,
            },
            provider=provider,
        )
        return parse_binance_candles(payload, timeframe=timeframe)
    if provider == "okx":
        payload = client.get_json(
            base_url=OKX_BASE_URL,
            path=_okx_candles_path(window),
            params={
                "instId": provider_symbol(normalized, provider),
                "bar": map_interval(timeframe, provider),
                "after": _millis(window.terminal_close_utc),
                "limit": window.bars + 2,
            },
            provider=provider,
        )
        return parse_okx_candles(payload, timeframe=timeframe)
    raise ProviderError("PROVIDER_DEGRADED", "Unsupported resolver provider.", provider=provider)


def _millis(dt: datetime) -> int:
    return (dt - EPOCH) // timedelta(milliseconds=1)


def _okx_candles_path(window: CandleWindow) -> str:
    interval = timedelta(seconds=TIMEFRAME_SECONDS[window.timeframe])
    bars_since = -((window.terminal_close_utc - window.now_utc) // interval)
    if bars_since + window.bars + 2 <= OKX_RECENT_MAX_BARS_BACK:
        return OKX_CANDLES_PATH
    return OKX_HISTORY_CANDLES_PATH


def _decision_band(prediction: dict) -> float:
    value = prediction.get("decision_band_frac")
    try:
        band = float(value)
    except (TypeError, ValueError):
        band = 0.0
    if band <= 0.0:
        return 2.0 * DEFAULT_PHASE1A.taker_fee_frac
    return band


def _realized_label(terminal_return_frac: float, decision_band_frac: float) -> str:
    if terminal_return_frac > decision_band_frac:
        return "UP"
    if terminal_return_frac < -decision_band_frac:
        return "DOWN"
    return "TIMEOUT"


def _parse_utc(value: Any) -> datetime:
    if isinstance(value, datetime):
        return _coerce_utc(value)
    return _coerce_utc(datetime.fromisoformat(str(value).replace("Z", "+00:00")))


def _coerce_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _iso_utc(value: datetime) -> str:
    return _coerce_utc(value).isoformat().replace("+00:00", "Z")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Resolve due UCPE prediction outcomes.")
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args(argv)
    settings = Settings.from_env()
    repository = build_resolver_repository(settings)
    repository_type = repository.repository_type()
    try:
        stats = resolve_due_predictions(repository, settings=settings, limit=args.limit)
    except Exception as exc:
        print(
            "resolved_outcomes "
            f"repository={repository_type} limit={args.limit} "
            "due=0 resolved=0 skipped=0 failed=1 "
            f"error={type(exc).__name__}: {exc}"
        )
        close = getattr(repository, "close", None)
        if callable(close):
            close()
        return 1
    print(
        "resolved_outcomes "
        f"repository={repository_type} limit={args.limit} "
        f"due={stats['due']} resolved={stats['resolved']} "
        f"skipped={stats['skipped']} failed={stats['failed']}"
    )
    close = getattr(repository, "close", None)
    if callable(close):
        close()
    return 1 if stats["failed"] > 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())
