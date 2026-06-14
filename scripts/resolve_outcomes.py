"""Resolve due prediction-ledger rows into immutable no-lookahead outcomes."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
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
from crypto_probability_engine.config.defaults import DEFAULT_PHASE1A, RESOLVER_VERSION
from crypto_probability_engine.config.settings import Settings
from crypto_probability_engine.normalizers.symbols import normalize_symbol
from crypto_probability_engine.persistence.repository import (
    PersistenceRepository,
    build_persistence_repository,
)

FetchCandles = Callable[[dict, Settings], tuple[Sequence[MarketCandle], str]]


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
    due_predictions = repository.fetch_due_unresolved_predictions(now, limit)
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
            repository.save_prediction_outcome(outcome)
            stats["resolved"] += 1
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
    reference_close_utc = _parse_utc(prediction["reference_close_utc"])
    reference_price = float(prediction["reference_price"])
    horizon_end_utc = _parse_utc(prediction["horizon_end_utc"])
    if reference_price <= 0.0:
        return None
    candles, data_source = fetch_candles(prediction, settings)
    post_anchor = [
        candle
        for candle in sorted(candles, key=lambda item: item.close_time_utc)
        if _coerce_utc(candle.close_time_utc) > reference_close_utc
    ]
    outcome_candle = next(
        (
            candle
            for candle in post_anchor
            if _coerce_utc(candle.close_time_utc) >= horizon_end_utc
        ),
        None,
    )
    if outcome_candle is None:
        return None
    outcome_close_utc = _coerce_utc(outcome_candle.close_time_utc)
    observed = [
        candle
        for candle in post_anchor
        if _coerce_utc(candle.close_time_utc) <= outcome_close_utc
    ]
    if not observed:
        return None
    terminal_return_frac = (float(outcome_candle.close) - reference_price) / reference_price
    decision_band_frac = _decision_band(prediction)
    return {
        "prediction_id": str(prediction["prediction_id"]),
        "resolved_at_utc": _iso_utc(now_utc),
        "outcome_close_utc": _iso_utc(outcome_close_utc),
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
        "data_source": data_source,
        "is_live_data": True,
    }


def fetch_public_candles(
    prediction: dict,
    settings: Settings,
) -> tuple[Sequence[MarketCandle], str]:
    """Fetch closed public candles from keyless Binance/OKX endpoints."""

    normalized = normalize_symbol(str(prediction["normalized_symbol"]))
    timeframe = str(prediction["timeframe"])
    providers = _provider_order(str(prediction.get("data_source") or ""), settings)
    for provider in providers:
        try:
            return _fetch_provider_candles(provider, normalized, timeframe, settings)
        except ProviderError:
            pass
    raise RuntimeError("Public candle fetch failed for resolver.")


def _fetch_provider_candles(provider: str, symbol, timeframe: str, settings: Settings):
    client = PublicHttpClient.from_settings(settings)
    horizon_bars = int(DEFAULT_PHASE1A.h_primary_bars)
    limit = max(horizon_bars + 10, 50)
    if provider == "binance":
        payload = client.get_json(
            base_url=BINANCE_BASE_URL,
            path="/api/v3/klines",
            params={
                "symbol": provider_symbol(symbol, provider),
                "interval": map_interval(timeframe, provider),
                "limit": min(limit, 1000),
            },
            provider=provider,
        )
        return parse_binance_candles(payload, timeframe=timeframe), "BINANCE_PUBLIC"
    if provider == "okx":
        payload = client.get_json(
            base_url=OKX_BASE_URL,
            path="/api/v5/market/candles",
            params={
                "instId": provider_symbol(symbol, provider),
                "bar": map_interval(timeframe, provider),
                "limit": min(limit, 300),
            },
            provider=provider,
        )
        return parse_okx_candles(payload, timeframe=timeframe), "OKX_PUBLIC"
    raise ProviderError("PROVIDER_DEGRADED", "Unsupported resolver provider.", provider=provider)


def _provider_order(data_source: str, settings: Settings) -> tuple[str, ...]:
    if data_source == "OKX_PUBLIC":
        preferred = ("okx", "binance")
    elif data_source == "BINANCE_PUBLIC":
        preferred = ("binance", "okx")
    else:
        preferred = tuple(settings.provider_priority)
    return tuple(provider for provider in preferred if provider in {"binance", "okx"})


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
    repository = build_persistence_repository(settings)
    stats = resolve_due_predictions(repository, settings=settings, limit=args.limit)
    print(
        "resolved_outcomes "
        f"due={stats['due']} resolved={stats['resolved']} "
        f"skipped={stats['skipped']} failed={stats['failed']}"
    )
    close = getattr(repository, "close", None)
    if callable(close):
        close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
