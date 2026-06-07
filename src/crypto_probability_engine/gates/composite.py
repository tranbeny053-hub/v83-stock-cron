"""Composite gate hierarchy for analysis-only output."""

from __future__ import annotations

from crypto_probability_engine.config.defaults import DEFAULT_PHASE1A


def _risk_viability_blocks(
    liquidity_state: dict | None,
    tail_risk_state: dict | None,
    execution_state: dict | None,
) -> list[str]:
    blocks: list[str] = []
    liquidity = liquidity_state or {}
    if liquidity:
        if liquidity.get("status") != "OK":
            blocks.append("LIQUIDITY_NOT_VIABLE")
        spread_frac = liquidity.get("spread_frac")
        depth_quote = float(liquidity.get("top_depth_quote") or 0.0)
        if spread_frac is None:
            blocks.append("LIQUIDITY_NOT_VIABLE")
        elif float(spread_frac) > DEFAULT_PHASE1A.liquidity_max_spread_frac:
            blocks.append("LIQUIDITY_NOT_VIABLE")
        if depth_quote < DEFAULT_PHASE1A.liquidity_min_top_depth_quote:
            blocks.append("LIQUIDITY_NOT_VIABLE")

    tail = tail_risk_state or {}
    if tail and float(tail.get("cvar_loss") or 0.0) > DEFAULT_PHASE1A.tail_cvar_breach_frac:
        blocks.append("TAIL_RISK_BREACH")

    execution = execution_state or {}
    if (
        execution
        and float(execution.get("round_trip_cost_frac") or 0.0)
        > DEFAULT_PHASE1A.execution_cost_hard_gate_frac
    ):
        blocks.append("EXECUTION_COST_TOO_HIGH")
    return sorted(set(blocks))


def apply_composite_gates(
    *,
    epistemic_state: dict,
    provider_state: dict,
    score_state: dict,
    liquidity_state: dict | None = None,
    tail_risk_state: dict | None = None,
    execution_state: dict | None = None,
    shelter_mode: bool = False,
    kill_switch: bool = False,
) -> dict:
    hard_blocks: list[str] = []
    if kill_switch:
        hard_blocks.append("KILL_SWITCH")
    if shelter_mode:
        hard_blocks.append("SHELTER_MODE_BLOCK")
    if provider_state.get("status") not in {"OK", "DEGRADED"}:
        hard_blocks.append("PROVIDER_DEGRADED")
    if epistemic_state.get("action") != "ALLOW":
        hard_blocks.append("EPISTEMIC_VOID")
    risk_blocks = _risk_viability_blocks(liquidity_state, tail_risk_state, execution_state)
    hard_blocks.extend(risk_blocks)

    if hard_blocks:
        risk_guard_applied = bool(risk_blocks)
        return {
            "action": "NO_TRADE" if risk_guard_applied else "ABORT",
            "hard_gate_passed": False,
            "hard_blocks": hard_blocks,
            "score_ignored": True,
            "news_ignored": True,
            "risk_guard_applied": risk_guard_applied,
            "forced_score_disposition": "ELEVATED_RISK_AVOID" if risk_guard_applied else None,
        }
    return {
        "action": score_state.get("disposition", "WATCH"),
        "hard_gate_passed": True,
        "hard_blocks": [],
        "score_ignored": False,
        "news_ignored": True,
        "risk_guard_applied": False,
        "forced_score_disposition": None,
    }
