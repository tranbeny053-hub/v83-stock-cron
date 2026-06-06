"""Backend-built display fields for the thin frontend."""

from __future__ import annotations


def build_frontend_display(
    quant_result: dict,
    news_blocks: dict,
    analysis_mode: str,
    data_quality: dict,
) -> dict:
    horizon = quant_result["probability_state"]["horizons"]["H_primary"]
    score = quant_result["score_stack"]
    gate = quant_result["gate_result"]
    disposition = gate["action"] if not gate["hard_gate_passed"] else score["disposition"]
    return {
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
        "data_quality_warnings": [],
        "execution_warnings": list(quant_result["execution_realism"].get("warnings", [])),
        "news_warnings": list(news_blocks["news_addon_state"].get("warnings", [])),
        "heat_legend": "Signal heat — not risk",
        "is_live_data": bool(data_quality.get("is_live_data", False)),
        "data_source": data_quality.get("data_source", "FIXTURE_DEMO"),
    }
