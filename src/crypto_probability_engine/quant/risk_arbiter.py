"""Risk arbiter baseline."""

from __future__ import annotations

from crypto_probability_engine.config.defaults import DEFAULT_PHASE1A


def compute_risk_arbiter(
    trend_state: dict,
    volatility_state: dict,
    liquidity_state: dict,
    execution_state: dict,
) -> dict:
    alpha = float(trend_state.get("primary_return") or 0.0)
    omega = float(liquidity_state.get("spread_frac") or 0.0)
    sigma = float(volatility_state.get("realized_vol") or 0.0)
    cost = float(execution_state.get("round_trip_cost_frac") or 0.0)
    if abs(alpha) <= cost:
        net_signal = 0.0
    else:
        net_signal = alpha - cost if alpha > 0 else alpha + cost
    risk_pressure = (
        DEFAULT_PHASE1A.w_omega * omega
        + DEFAULT_PHASE1A.w_sigma * sigma
    )
    arbiter_value = DEFAULT_PHASE1A.w_alpha * net_signal - risk_pressure
    return {
        "status": "OK",
        "risk_arbiter_version": DEFAULT_PHASE1A.risk_arbiter_version,
        "w_alpha": DEFAULT_PHASE1A.w_alpha,
        "w_omega": DEFAULT_PHASE1A.w_omega,
        "w_sigma": DEFAULT_PHASE1A.w_sigma,
        "alpha_signal": alpha,
        "net_signal": net_signal,
        "risk_pressure": risk_pressure,
        "arbiter_value": arbiter_value,
    }
