"""Epistemic sufficiency checks."""

from __future__ import annotations

from crypto_probability_engine.adapters.types import MarketSnapshot
from crypto_probability_engine.config.defaults import low_sample_threshold_for, min_history_for


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
    low_sample_threshold = low_sample_threshold_for(snapshot.timeframe)
    if low_sample_threshold is not None and len(snapshot.candles) < low_sample_threshold:
        return {
            "sufficiency_level": "LOW_SAMPLE",
            "action": "ALLOW",
            "reason": "LOW_SAMPLE_HISTORY",
            "min_history_bars": min_history_bars,
            "minimum_reliable_bars": low_sample_threshold,
            "observed_bars": len(snapshot.candles),
        }
    return {
        "sufficiency_level": "SUFFICIENT",
        "action": "ALLOW",
        "reason": None,
        "min_history_bars": min_history_bars,
        "observed_bars": len(snapshot.candles),
    }
