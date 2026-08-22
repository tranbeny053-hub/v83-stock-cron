"""Backend-built display fields for the thin frontend."""

from __future__ import annotations

from crypto_probability_engine.config.defaults import MIN_DIRECTIONAL_SAMPLES

_BLOCKING_REASON_COPY = {
    "KILL_SWITCH": (
        "Safety shutdown is active",
        "Analysis is blocked because the system-wide safety shutdown is active.",
    ),
    "SHELTER_MODE_BLOCK": (
        "Protective mode is active",
        "Analysis is blocked while the system is in protective mode.",
    ),
    "PROVIDER_DEGRADED": (
        "A required data provider is degraded",
        "Analysis is blocked because a required data provider is not operating normally.",
    ),
    "EPISTEMIC_VOID": (
        "Required evidence is unavailable",
        "Analysis is blocked because the available inputs are not sufficient for an assessment.",
    ),
    "LIQUIDITY_NOT_VIABLE": (
        "Liquidity is not viable",
        "Analysis is blocked because current liquidity does not meet the required bar.",
    ),
    "TAIL_RISK_BREACH": (
        "Extreme-move risk is too high",
        "Analysis is blocked because extreme-move risk exceeds the permitted level.",
    ),
    "EXECUTION_COST_TOO_HIGH": (
        "Execution cost is too high",
        "Analysis is blocked because the estimated execution cost exceeds the permitted level.",
    ),
}


def _skill_blocking_reason(skill_evidence: dict | None) -> tuple[str, str]:
    evidence = skill_evidence if isinstance(skill_evidence, dict) else {}
    verdict = evidence.get("verdict")

    if verdict == "INSUFFICIENT_EVIDENCE":
        n = evidence.get("n")
        count = str(n) if n is not None else "unavailable"
        return (
            "Directional skill has not been evaluated",
            "The model has not been evaluated on this timeframe because fewer than "
            f"{MIN_DIRECTIONAL_SAMPLES} resolved outcomes are available. "
            f"Reported resolved outcomes: {count}.",
        )

    if verdict == "NO_DEMONSTRATED_SKILL":
        n = evidence.get("n")
        count = str(n) if n is not None else "an unavailable number of"
        observed_rate = evidence.get("observed_directional_rate")
        rate_text = ""
        if isinstance(observed_rate, (int, float)) and not isinstance(observed_rate, bool):
            rate_text = f" The observed directional accuracy was {observed_rate * 100:.1f}%."
        return (
            "Directional accuracy did not clear the evidence bar",
            f"On {count} resolved outcomes, the observed directional accuracy did not clear "
            f"the required evidence threshold — it was not strong enough to rule out "
            f"chance.{rate_text} This is not a finding that accuracy is at or below 50%.",
        )

    return (
        "Directional evidence check is active",
        "The directional-skill evidence gate is active, but its verdict is unavailable.",
    )


def _blocking_reasons(gate: dict, skill_evidence: dict | None) -> list[dict[str, str]]:
    reasons = []
    for raw_code in gate.get("hard_blocks", []):
        code = str(raw_code)
        if code == "SKILL_NOT_DEMONSTRATED":
            headline, detail = _skill_blocking_reason(skill_evidence)
        else:
            headline, detail = _BLOCKING_REASON_COPY.get(
                code,
                (
                    code,
                    "This is a hard gate, but its description is unavailable.",
                ),
            )
        reasons.append({"code": code, "headline": headline, "detail": detail})
    return reasons


def build_frontend_display(
    quant_result: dict,
    news_blocks: dict,
    analysis_mode: str,
    data_quality: dict,
    horizon_context: dict,
    *,
    skill_evidence: dict | None = None,
    include_blocking_reasons: bool = True,
) -> dict:
    horizon = quant_result["probability_state"]["horizons"]["H_primary"]
    score = quant_result["score_stack"]
    gate = quant_result["gate_result"]
    disposition = gate["action"] if not gate["hard_gate_passed"] else score["disposition"]
    display = {
        "prob_up_pct": horizon["p_up_frac"] * 100.0,
        "prob_down_pct": horizon["p_down_frac"] * 100.0,
        "prob_timeout_pct": horizon["p_timeout_frac"] * 100.0,
        "total_score": score["total_score"],
        "risk_level": "UNKNOWN",
        "disposition": disposition,
        "analysis_mode_badge": analysis_mode,
        "detail_available": True,
        "key_reasons": list(gate.get("hard_blocks", [])),
        "invalidation_conditions": list(gate.get("hard_blocks", [])),
        "blocking_reasons": _blocking_reasons(gate, skill_evidence),
        "data_quality_warnings": list(data_quality.get("warnings", [])),
        "execution_warnings": list(quant_result["execution_realism"].get("warnings", [])),
        "news_warnings": list(news_blocks["news_addon_state"].get("warnings", [])),
        "heat_legend": "Signal heat — not risk",
        "timeframe_label": horizon_context["timeframe_label"],
        "horizon_label": horizon_context["horizon_label"],
        "horizon_bars": horizon_context["horizon_bars"],
        "horizon_approx_label": horizon_context["horizon_approx_label"],
        "probability_explanation": horizon_context["probability_explanation"],
        "uncalibrated_banner": horizon_context["uncalibrated_banner"],
        "model_readiness_label": horizon_context["model_readiness_label"],
        "is_live_data": bool(data_quality.get("is_live_data", False)),
        "data_source": data_quality.get("data_source", "FIXTURE_DEMO"),
    }
    if not include_blocking_reasons:
        display.pop("blocking_reasons")
    return display
