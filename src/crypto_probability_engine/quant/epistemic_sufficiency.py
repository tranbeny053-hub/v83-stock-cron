"""Epistemic sufficiency checks."""

from __future__ import annotations

from crypto_probability_engine.adapters.types import MarketSnapshot
from crypto_probability_engine.config.defaults import min_history_for


def assess_epistemic_sufficiency(snapshot: MarketSnapshot) -> dict:
    min_history_bars = min_history_for(snapshot.timeframe)
    if len(snapshot.candles) < min_history_bars:
        return {
            "sufficiency_level": "VOID",
            "action": "ABORT",
            "reason": "INSUFFICIENT_DATA",
            "min_history_bars": min_history_bars,
            "observed_bars": len(snapshot.candles),
        }
    return {
        "sufficiency_level": "SUFFICIENT",
        "action": "ALLOW",
        "reason": None,
        "min_history_bars": min_history_bars,
        "observed_bars": len(snapshot.candles),
    }
