"""Realized volatility features."""

from __future__ import annotations

from math import log
from statistics import pstdev

from crypto_probability_engine.adapters.types import MarketCandle


def compute_realized_volatility(candles: tuple[MarketCandle, ...]) -> dict:
    returns: list[float] = []
    for prev, cur in zip(candles, candles[1:], strict=False):
        if prev.close > 0 and cur.close > 0:
            returns.append(log(cur.close / prev.close))
    if not returns:
        return {"status": "DEGRADED", "realized_vol": 0.0, "sample_size": 0}
    vol = pstdev(returns)
    return {
        "status": "OK",
        "realized_vol": vol,
        "method": "PER_BAR_LOG_RETURN_PSTDEV",
        "sample_size": len(returns),
    }
