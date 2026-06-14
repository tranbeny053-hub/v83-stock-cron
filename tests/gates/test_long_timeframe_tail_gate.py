from __future__ import annotations

from crypto_probability_engine.config.defaults import tail_cvar_breach_threshold_for
from crypto_probability_engine.gates.composite import apply_composite_gates


def _gate_for_tail(cvar_loss: float, threshold: float) -> dict:
    return apply_composite_gates(
        epistemic_state={"action": "ALLOW"},
        provider_state={"status": "OK"},
        score_state={"disposition": "CONSTRUCTIVE_CAUTIOUS", "total_score": 99},
        liquidity_state={"status": "OK", "spread_frac": 0.001, "top_depth_quote": 10_000.0},
        tail_risk_state={
            "status": "OK",
            "cvar_loss": cvar_loss,
            "cvar_breach_threshold": threshold,
        },
        execution_state={"status": "OK", "round_trip_cost_frac": 0.001},
    )


def test_horizon_aware_tail_threshold_allows_normal_long_timeframe_case() -> None:
    threshold = tail_cvar_breach_threshold_for("1D")
    gate = _gate_for_tail(cvar_loss=threshold * 0.80, threshold=threshold)

    assert "TAIL_RISK_BREACH" not in gate["hard_blocks"]
    assert gate["hard_gate_passed"] is True


def test_horizon_aware_tail_threshold_still_blocks_extreme_long_timeframe_case() -> None:
    threshold = tail_cvar_breach_threshold_for("1W")
    gate = _gate_for_tail(cvar_loss=threshold * 1.50, threshold=threshold)

    assert gate["action"] == "NO_TRADE"
    assert "TAIL_RISK_BREACH" in gate["hard_blocks"]
    assert gate["forced_score_disposition"] == "ELEVATED_RISK_AVOID"
