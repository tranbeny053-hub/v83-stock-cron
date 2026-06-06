"""Epistemic sufficiency checks."""

from __future__ import annotations

from crypto_probability_engine.adapters.types import MarketSnapshot
from crypto_probability_engine.config.defaults import DEFAULT_PHASE1A


def assess_epistemic_sufficiency(snapshot: MarketSnapshot) -> dict:
    if len(snapshot.candles) < DEFAULT_PHASE1A.min_history_bars:
        return {
            "sufficiency_level": "VOID",
            "action": "ABORT",
            "reason": "INSUFFICIENT_DATA",
            "min_history_bars": DEFAULT_PHASE1A.min_history_bars,
            "observed_bars": len(snapshot.candles),
        }
    return {
        "sufficiency_level": "SUFFICIENT",
        "action": "ALLOW",
        "reason": None,
        "min_history_bars": DEFAULT_PHASE1A.min_history_bars,
        "observed_bars": len(snapshot.candles),
    }

