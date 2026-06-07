"""Net-of-cost and depth-aware realism state."""

from __future__ import annotations

from crypto_probability_engine.config.defaults import DEFAULT_PHASE1A


def compute_execution_realism(liquidity_state: dict) -> dict:
    spread_frac = liquidity_state.get("spread_frac")
    if spread_frac is None:
        slippage_frac = 0.0
        status = "DEGRADED"
        warnings = ["Depth-aware slippage unavailable without order book."]
    elif not 0.0 <= float(spread_frac) <= 1.0:
        slippage_frac = 0.0
        status = "DEGRADED"
        warnings = ["Depth-aware slippage unavailable because spread is not bounded."]
    else:
        slippage_frac = max(float(spread_frac) / 2.0, 0.0)
        status = "OK"
        warnings = []
    round_trip_cost_frac = (DEFAULT_PHASE1A.taker_fee_frac * 2.0) + slippage_frac
    return {
        "status": status,
        "taker_fee_frac": DEFAULT_PHASE1A.taker_fee_frac,
        "maker_fee_frac": DEFAULT_PHASE1A.maker_fee_frac,
        "slippage_model": "DEPTH_AWARE_PHASE1A",
        "slippage_frac": slippage_frac,
        "round_trip_cost_frac": round_trip_cost_frac,
        "net_of_cost_binding": True,
        "warnings": warnings,
    }
