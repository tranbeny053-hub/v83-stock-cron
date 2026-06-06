"""Multi-timeframe trend features from validated candles."""

from __future__ import annotations

from crypto_probability_engine.adapters.types import MarketCandle
from crypto_probability_engine.config.defaults import DEFAULT_PHASE1A


def _return_over_bars(candles: tuple[MarketCandle, ...], bars: int) -> float:
    if len(candles) <= bars:
        return 0.0
    start = candles[-bars - 1].close
    end = candles[-1].close
    if start <= 0:
        return 0.0
    return (end - start) / start


def compute_trend_mtf(candles: tuple[MarketCandle, ...]) -> dict:
    primary_return = _return_over_bars(candles, DEFAULT_PHASE1A.h_primary_bars)
    extended_return = _return_over_bars(candles, DEFAULT_PHASE1A.h_extended_bars)
    net_cost_floor = DEFAULT_PHASE1A.taker_fee_frac * 2.0
    if primary_return > net_cost_floor:
        label = "UP"
    elif primary_return < -net_cost_floor:
        label = "DOWN"
    else:
        label = "SIDEWAYS"
    return {
        "status": "OK",
        "trend_timeframes": list(DEFAULT_PHASE1A.trend_timeframes),
        "primary_return": primary_return,
        "extended_return": extended_return,
        "label": label,
    }
