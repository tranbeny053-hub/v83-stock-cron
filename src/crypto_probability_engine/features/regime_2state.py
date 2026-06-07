"""Deterministic two-state regime proxy."""

from __future__ import annotations


def classify_regime(volatility_state: dict) -> dict:
    vol = float(volatility_state.get("realized_vol") or 0.0)
    state = "HIGH_VARIANCE" if vol > 0.05 else "NORMAL_VARIANCE"
    return {
        "status": "OK",
        "regime": state,
        "deterministic_proxy": True,
    }
