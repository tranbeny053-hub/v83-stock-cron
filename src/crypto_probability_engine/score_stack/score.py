"""Backend-only score and disposition baseline."""

from __future__ import annotations

from crypto_probability_engine.config.defaults import DEFAULT_PHASE1A

ALLOWED_DISPOSITIONS = frozenset(
    {
        "ABORT_INSUFFICIENT_DATA",
        "ABORT_PROVIDER_DEGRADED",
        "ABORT_SYSTEM_RISK",
        "NO_TRADE",
        "WATCH",
        "CONSTRUCTIVE_CAUTIOUS",
        "CONSTRUCTIVE",
        "ELEVATED_RISK_AVOID",
        "DIRECTIONAL_SHORT_CONTEXT",
    }
)


def compute_score_stack(probability_state: dict, risk_arbiter_state: dict) -> dict:
    horizon = probability_state["horizons"]["H_primary"]
    directional_edge = horizon["p_up_frac"] - horizon["p_down_frac"]
    risk_pressure = float(risk_arbiter_state.get("risk_pressure") or 0.0)
    raw_score = (
        DEFAULT_PHASE1A.score_base
        + (directional_edge * DEFAULT_PHASE1A.score_directional_edge_multiplier)
        - min(
            risk_pressure * DEFAULT_PHASE1A.score_max,
            DEFAULT_PHASE1A.score_risk_pressure_cap,
        )
    )
    total_score = int(
        round(min(max(raw_score, DEFAULT_PHASE1A.score_min), DEFAULT_PHASE1A.score_max))
    )
    if total_score >= DEFAULT_PHASE1A.score_constructive_cautious_min:
        disposition = "CONSTRUCTIVE_CAUTIOUS"
    elif total_score <= DEFAULT_PHASE1A.score_elevated_risk_max:
        disposition = "ELEVATED_RISK_AVOID"
    else:
        disposition = "WATCH"
    return {
        "status": "OK",
        "total_score": total_score,
        "directional_edge": directional_edge,
        "disposition": disposition,
        "news_influence_frac": 0.0,
    }
