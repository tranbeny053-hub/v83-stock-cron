"""Timeout probability baseline."""

from __future__ import annotations

from crypto_probability_engine.config.defaults import DEFAULT_PHASE1A


def compute_timeout_probability(volatility_state: dict, liquidity_state: dict) -> float:
    vol = float(volatility_state.get("realized_vol_frac") or 0.0)
    spread = float(liquidity_state.get("spread_frac") or 0.0)
    raw = (
        DEFAULT_PHASE1A.timeout_base_frac
        + min(vol, DEFAULT_PHASE1A.timeout_vol_cap_frac)
        + min(
            spread * DEFAULT_PHASE1A.timeout_spread_multiplier,
            DEFAULT_PHASE1A.timeout_spread_cap_frac,
        )
    )
    return min(max(raw, DEFAULT_PHASE1A.timeout_min_frac), DEFAULT_PHASE1A.timeout_max_frac)


def horizon_timeout_state(p_timeout_frac: float) -> dict:
    return {
        "status": "OK",
        "method": DEFAULT_PHASE1A.probability_version,
        "p_timeout_frac": p_timeout_frac,
        "timeout_is_directional": False,
    }
