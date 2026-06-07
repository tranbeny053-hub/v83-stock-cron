"""Historical CVaR baseline."""

from __future__ import annotations

from math import log

from crypto_probability_engine.adapters.types import MarketCandle
from crypto_probability_engine.config.defaults import DEFAULT_PHASE1A


def compute_tail_cvar(candles: tuple[MarketCandle, ...]) -> dict:
    returns: list[float] = []
    for prev, cur in zip(candles, candles[1:], strict=False):
        if prev.close > 0 and cur.close > 0:
            returns.append(log(cur.close / prev.close))
    if not returns:
        cvar = 0.0
    else:
        losses = sorted([-value for value in returns], reverse=True)
        cutoff = max(1, int(len(losses) * (1.0 - DEFAULT_PHASE1A.tail_confidence_frac)))
        cvar = sum(losses[:cutoff]) / cutoff
    return {
        "status": "OK",
        "tail_method": DEFAULT_PHASE1A.tail_method,
        "tail_confidence_frac": DEFAULT_PHASE1A.tail_confidence_frac,
        "cvar_loss": max(cvar, 0.0),
        "evt_status": DEFAULT_PHASE1A.evt_status,
    }
