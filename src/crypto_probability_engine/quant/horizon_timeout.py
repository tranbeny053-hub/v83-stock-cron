"""Timeout probability baseline."""

from __future__ import annotations

from crypto_probability_engine.config.defaults import (
    DEFAULT_PHASE1A,
    timeout_vol_reference_for,
)


def compute_timeout_probability(
    volatility_state: dict,
    liquidity_state: dict,
    *,
    timeframe: str = DEFAULT_PHASE1A.primary_timeframe,
) -> float:
    vol = float(volatility_state.get("realized_vol") or 0.0)
    spread = float(liquidity_state.get("spread_frac") or 0.0)
    vol_reference = max(timeout_vol_reference_for(timeframe), 1e-12)
    vol_component = min(vol / vol_reference, 1.0) * DEFAULT_PHASE1A.timeout_vol_cap_frac
    raw = (
        DEFAULT_PHASE1A.timeout_base_frac
        + vol_component
        + min(
            spread * DEFAULT_PHASE1A.timeout_spread_multiplier,
            DEFAULT_PHASE1A.timeout_spread_cap_frac,
        )
    )
    return min(max(raw, DEFAULT_PHASE1A.timeout_min_frac), DEFAULT_PHASE1A.timeout_max_frac)


def horizon_timeout_state(
    p_timeout_frac: float,
    *,
    timeframe: str = DEFAULT_PHASE1A.primary_timeframe,
) -> dict:
    return {
        "status": "OK",
        "method": DEFAULT_PHASE1A.probability_version,
        "p_timeout_frac": p_timeout_frac,
        "timeout_is_directional": False,
        "timeframe": timeframe,
        "vol_reference": timeout_vol_reference_for(timeframe),
    }
