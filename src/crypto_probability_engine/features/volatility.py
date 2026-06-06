"""Realized volatility features."""

from __future__ import annotations

from math import log, sqrt
from statistics import pstdev

from crypto_probability_engine.adapters.types import MarketCandle


def compute_realized_volatility(candles: tuple[MarketCandle, ...]) -> dict:
    returns: list[float] = []
    for prev, cur in zip(candles, candles[1:], strict=False):
        if prev.close > 0 and cur.close > 0:
            returns.append(log(cur.close / prev.close))
    if not returns:
        return {"status": "DEGRADED", "realized_vol_frac": 0.0, "sample_size": 0}
    vol = pstdev(returns) * sqrt(len(returns))
    return {
        "status": "OK",
        "realized_vol_frac": vol,
        "sample_size": len(returns),
    }

