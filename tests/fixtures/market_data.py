"""Offline market-data fixtures."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from crypto_probability_engine.adapters.types import (
    MarketCandle,
    MarketSnapshot,
    OrderBookLevel,
    OrderBookSnapshot,
    ProviderStatus,
)

FIXED_NOW = datetime(2026, 6, 6, 12, 0, tzinfo=UTC)


def make_candles(
    *,
    count: int = 210,
    timeframe_seconds: int = 14_400,
    start_price: float = 100.0,
    as_of_utc: datetime = FIXED_NOW,
) -> tuple[MarketCandle, ...]:
    candles: list[MarketCandle] = []
    start = as_of_utc - timedelta(seconds=count * timeframe_seconds)
    for idx in range(count):
        open_time = start + timedelta(seconds=idx * timeframe_seconds)
        close_time = open_time + timedelta(seconds=timeframe_seconds)
        open_price = start_price + idx * 0.1
        close_price = open_price + 0.05
        candles.append(
            MarketCandle(
                open_time_utc=open_time,
                close_time_utc=close_time,
                open=open_price,
                high=close_price + 1.0,
                low=open_price - 1.0,
                close=close_price,
                volume=1_000.0 + idx,
            )
        )
    return tuple(candles)


def make_downtrend_candles(
    *,
    count: int = 210,
    timeframe_seconds: int = 14_400,
    start_price: float = 180.0,
    as_of_utc: datetime = FIXED_NOW,
) -> tuple[MarketCandle, ...]:
    candles: list[MarketCandle] = []
    start = as_of_utc - timedelta(seconds=count * timeframe_seconds)
    for idx in range(count):
        open_time = start + timedelta(seconds=idx * timeframe_seconds)
        close_time = open_time + timedelta(seconds=timeframe_seconds)
        drift = idx * 0.12
        wobble = (idx % 5) * 0.08
        open_price = start_price - drift + wobble
        close_price = open_price - 0.35 - ((idx % 3) * 0.06)
        high = max(open_price, close_price) + 1.8 + ((idx % 4) * 0.12)
        low = min(open_price, close_price) - 2.2 - ((idx % 6) * 0.10)
        candles.append(
            MarketCandle(
                open_time_utc=open_time,
                close_time_utc=close_time,
                open=open_price,
                high=high,
                low=low,
                close=close_price,
                volume=1_300.0 + (idx % 11) * 25.0,
            )
        )
    return tuple(candles)


def make_order_book(*, bid: float = 120.0, ask: float = 120.5) -> OrderBookSnapshot:
    return OrderBookSnapshot(
        bids=(OrderBookLevel(price=bid, size=2.0),),
        asks=(OrderBookLevel(price=ask, size=2.5),),
        as_of_utc=FIXED_NOW,
    )


def make_downtrend_snapshot(
    *,
    provider: str = "fixture",
    symbol: str = "BTC/USDT",
    timeframe: str = "4H",
) -> MarketSnapshot:
    candles = make_downtrend_candles()
    last_close = candles[-1].close
    return MarketSnapshot(
        provider=provider,
        normalized_symbol=symbol,
        timeframe=timeframe,
        candles=candles,
        order_book=make_order_book(bid=last_close - 0.25, ask=last_close + 0.25),
        as_of_utc=FIXED_NOW,
        source_status=ProviderStatus.OK,
    )


def make_snapshot(
    *,
    provider: str = "fixture",
    symbol: str = "BTC/USDT",
    timeframe: str = "4H",
    close_shift: float = 0.0,
) -> MarketSnapshot:
    candles = list(make_candles())
    last = candles[-1]
    candles[-1] = MarketCandle(
        open_time_utc=last.open_time_utc,
        close_time_utc=last.close_time_utc,
        open=last.open,
        high=last.high + close_shift,
        low=last.low,
        close=last.close + close_shift,
        volume=last.volume,
    )
    return MarketSnapshot(
        provider=provider,
        normalized_symbol=symbol,
        timeframe=timeframe,
        candles=tuple(candles),
        order_book=make_order_book(),
        as_of_utc=FIXED_NOW,
        source_status=ProviderStatus.OK,
    )
