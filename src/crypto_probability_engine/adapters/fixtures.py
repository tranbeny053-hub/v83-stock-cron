"""Deterministic fixture market data for Sprint 1 local analysis."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from crypto_probability_engine.adapters.types import (
    MarketCandle,
    MarketSnapshot,
    OrderBookLevel,
    OrderBookSnapshot,
    ProviderStatus,
)
from crypto_probability_engine.config.defaults import TIMEFRAME_SECONDS


def fixture_now() -> datetime:
    return datetime(2026, 6, 6, 12, 0, tzinfo=UTC)


def build_fixture_candles(
    *,
    count: int = 240,
    timeframe: str = "4H",
    start_price: float = 100.0,
    as_of_utc: datetime | None = None,
) -> tuple[MarketCandle, ...]:
    now = as_of_utc or fixture_now()
    timeframe_seconds = TIMEFRAME_SECONDS[timeframe]
    start = now - timedelta(seconds=count * timeframe_seconds)
    candles: list[MarketCandle] = []
    for idx in range(count):
        open_time = start + timedelta(seconds=idx * timeframe_seconds)
        close_time = open_time + timedelta(seconds=timeframe_seconds)
        drift = idx * 0.08
        cycle = ((idx % 7) - 3) * 0.03
        open_price = start_price + drift + cycle
        close_price = open_price + 0.04
        candles.append(
            MarketCandle(
                open_time_utc=open_time,
                close_time_utc=close_time,
                open=open_price,
                high=close_price + 0.9,
                low=open_price - 0.9,
                close=close_price,
                volume=1_000.0 + (idx % 24) * 12.0,
            )
        )
    return tuple(candles)


def build_fixture_book(as_of_utc: datetime | None = None) -> OrderBookSnapshot:
    now = as_of_utc or fixture_now()
    return OrderBookSnapshot(
        bids=(
            OrderBookLevel(price=119.8, size=2.0),
            OrderBookLevel(price=119.6, size=3.0),
        ),
        asks=(
            OrderBookLevel(price=120.2, size=2.5),
            OrderBookLevel(price=120.4, size=3.5),
        ),
        as_of_utc=now,
    )


def build_fixture_snapshot(
    *,
    normalized_symbol: str,
    timeframe: str,
    provider: str = "fixture",
) -> MarketSnapshot:
    now = fixture_now()
    return MarketSnapshot(
        provider=provider,
        normalized_symbol=normalized_symbol,
        timeframe=timeframe,
        candles=build_fixture_candles(timeframe=timeframe, as_of_utc=now),
        order_book=build_fixture_book(now),
        as_of_utc=now,
        source_status=ProviderStatus.OK,
    )

