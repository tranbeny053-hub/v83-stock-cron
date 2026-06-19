"""Pure, read-only decision synthesis derived from an analysis payload."""

from __future__ import annotations

from typing import Any

SCHEMA_VERSION = "1.0"
DECISION_LABELS = frozenset(
    {
        "AVOID",
        "NO_TRADE",
        "WAIT",
        "WATCH",
        "LONG_CANDIDATE",
        "SHORT_CANDIDATE",
    }
)

_CONSTRUCTIVE_DISPOSITIONS = frozenset({"CONSTRUCTIVE", "CONSTRUCTIVE_CAUTIOUS"})
_TIMEFRAME_ROLES = {
    "15m": ("TACTICAL_TIMING", True, False),
    "1H": ("TACTICAL_SWING_BRIDGE", True, False),
    "4H": ("SETUP_QUALITY", True, False),
    "1D": ("SWING_CONTEXT", False, False),
    "1W": ("REGIME_CONTEXT", False, True),
    "1M": ("MACRO_BACKDROP", False, True),
}
_TRADE_PLAN_NULL_FIELDS = (
    "preferred_entry_zone",
    "acceptable_entry_zone",
    "chase_zone",
    "breakout_trigger",
    "pullback_trigger",
    "stop_invalidation",
    "take_profit_plan",
    "risk_reward_summary",
)


def build_decision_synthesis(
    *,
    timeframe: str,
    quant_result: dict,
    data_quality: dict,
    provider_state: dict,
    decision_brief: dict,
) -> dict:
    """Build an additive interpretation block without querying or mutating state."""
    gate = quant_result.get("gate_result") or {}
    score = quant_result.get("score_stack") or {}
    epistemic = quant_result.get("epistemic_sufficiency_state") or {}
    calibration = quant_result.get("calibration_state") or {}
    probability = _probability_interpretation(
        probability_state=quant_result.get("probability_state") or {},
        gate=gate,
        calibration=calibration,
        decision_brief=decision_brief,
    )
    hard_gate_active = _hard_gate_active(gate)
    reliability_status = _reliability_status(calibration, decision_brief)
    label = _decision_label(
        gate=gate,
        score=score,
        epistemic=epistemic,
        probability=probability,
        provider_state=provider_state,
        data_quality=data_quality,
    )
    can_plan_trade = label in {"LONG_CANDIDATE", "SHORT_CANDIDATE"}
    timeframe_role = _timeframe_role(timeframe)
    model_quality = _model_quality_summary(calibration, reliability_status)

    result = {
        "schema_version": SCHEMA_VERSION,
        "decision_synthesis": {
            "label": label,
            "decision_strength": _decision_strength(label, reliability_status),
            "plain_english": _decision_plain_english(label),
            "source_disposition": str(score.get("disposition") or "UNKNOWN"),
            "source_gate_action": str(gate.get("action") or "UNKNOWN"),
            "candidate_is_not_entry_permission": True,
        },
        "probability_interpretation": probability,
        "timeframe_role": timeframe_role,
        "action_permission": {
            "can_plan_trade": can_plan_trade,
            "can_enter_now": False,
            "can_chase": False,
            "observe_only": not can_plan_trade,
            "plain_english": (
                "Candidate planning only; current entry and chase permissions are disabled."
                if can_plan_trade
                else "Observe only; current entry, chase, and numeric planning are disabled."
            ),
        },
        "actionability_stack": _actionability_stack(
            label=label,
            gate=gate,
            data_quality=data_quality,
            provider_state=provider_state,
            epistemic=epistemic,
            probability=probability,
            quant_result=quant_result,
            reliability_status=reliability_status,
        ),
        "model_quality_summary": model_quality,
        "what_would_change_decision": _what_would_change_decision(
            label=label,
            gate=gate,
            data_quality=data_quality,
            provider_state=provider_state,
            reliability_status=reliability_status,
        ),
        "advisor_explanations": _advisor_explanations(
            label=label,
            hard_gate_active=hard_gate_active,
            reliability_status=reliability_status,
            timeframe_role=timeframe_role,
        ),
        "trade_plan_skeleton": {
            "status": "STRUCTURAL_ONLY_D1_1",
            "can_plan_trade": can_plan_trade,
            "can_enter_now": False,
            "can_chase": False,
            **{field: None for field in _TRADE_PLAN_NULL_FIELDS},
            "disabled_reason": (
                "UI-D1.1 exposes structure only; validated numeric planning is not available."
            ),
        },
        "future_quant_v2_hooks": {
            "status": "PLACEHOLDER",
            "influence_mode": "SHADOW_ONLY",
            "decision_influence_frac": 0.0,
            "plain_english": "Future quant hooks are shadow-only and do not affect this result.",
        },
    }
    return result


def _probability_interpretation(
    *,
    probability_state: dict,
    gate: dict,
    calibration: dict,
    decision_brief: dict,
) -> dict:
    horizon = (probability_state.get("horizons") or {}).get("H_primary") or {}
    p_up = _optional_float(horizon.get("p_up_frac"))
    p_down = _optional_float(horizon.get("p_down_frac"))
    p_timeout = _optional_float(horizon.get("p_timeout_frac"))
    directional_edge = None if p_up is None or p_down is None else p_up - p_down
    resolution_probability = None if p_timeout is None else 1.0 - p_timeout
    directional_denominator = None if p_up is None or p_down is None else p_up + p_down
    directional_balance = (
        None
        if directional_denominator is None or directional_denominator <= 0.0
        else p_up / directional_denominator
    )
    reliability_status = _reliability_status(calibration, decision_brief)
    informational_only = (
        _hard_gate_active(gate)
        or reliability_status != "MEASURED"
        or str(horizon.get("status") or "UNKNOWN") != "OK"
    )
    if directional_edge is None:
        interpretation_label = "UNAVAILABLE"
        plain_english = "Directional probability values are unavailable for interpretation."
    elif directional_edge > 0.0:
        interpretation_label = "UP_LEAN"
        plain_english = (
            "The heuristic probability leans upward, but it is context rather than an action."
        )
    elif directional_edge < 0.0:
        interpretation_label = "DOWN_LEAN"
        plain_english = (
            "The heuristic probability leans downward, but it is context rather than an action."
        )
    else:
        interpretation_label = "BALANCED"
        plain_english = "The heuristic probability has no directional lean."
    reliability_warning = (
        "Reliability is measured in the supplied payload; probability remains non-executable."
        if reliability_status == "MEASURED"
        else (
            "Reliability is not measured from sufficient resolved samples; treat probability "
            "as informational only."
        )
    )
    return {
        "p_up": p_up,
        "p_down": p_down,
        "p_timeout": p_timeout,
        "directional_edge": directional_edge,
        "resolution_probability": resolution_probability,
        "directional_balance": directional_balance,
        "interpretation_label": interpretation_label,
        "plain_english": plain_english,
        "reliability_warning": reliability_warning,
        "informational_only": informational_only,
    }


def _decision_label(
    *,
    gate: dict,
    score: dict,
    epistemic: dict,
    probability: dict,
    provider_state: dict,
    data_quality: dict,
) -> str:
    disposition = str(score.get("disposition") or "")
    gate_action = str(gate.get("action") or "")
    if disposition == "ELEVATED_RISK_AVOID":
        return "NO_TRADE"
    if _hard_gate_active(gate):
        return "NO_TRADE" if gate_action == "NO_TRADE" else "AVOID"
    if _transient_wait_state(epistemic, provider_state, data_quality):
        return "WAIT"
    if disposition == "WATCH" or gate_action == "WATCH":
        return "WATCH"
    edge = probability.get("directional_edge")
    if (
        disposition in _CONSTRUCTIVE_DISPOSITIONS
        and epistemic.get("sufficiency_level") == "SUFFICIENT"
        and isinstance(edge, int | float)
    ):
        if edge > 0.0:
            return "LONG_CANDIDATE"
        if edge < 0.0:
            return "SHORT_CANDIDATE"
    return "WATCH"


def _hard_gate_active(gate: dict) -> bool:
    action = str(gate.get("action") or "")
    return (
        bool(gate.get("hard_blocks"))
        or gate.get("hard_gate_passed") is False
        or action.startswith("ABORT")
    )


def _transient_wait_state(epistemic: dict, provider_state: dict, data_quality: dict) -> bool:
    if epistemic.get("sufficiency_level") == "LOW_SAMPLE":
        return True
    live_data = data_quality.get("is_live_data") is True
    provider_degraded = str(provider_state.get("status") or "") == "DEGRADED"
    quality_degraded = str(data_quality.get("status") or "") == "DEGRADED"
    return live_data and (provider_degraded or quality_degraded)


def _reliability_status(calibration: dict, decision_brief: dict) -> str:
    return str(
        calibration.get("reliability_status")
        or decision_brief.get("reliability_status")
        or "INSUFFICIENT_SAMPLE"
    )


def _decision_strength(label: str, reliability_status: str) -> str:
    if label in {"AVOID", "NO_TRADE", "WAIT"}:
        return "LOW"
    if reliability_status == "MEASURED" and label in {
        "LONG_CANDIDATE",
        "SHORT_CANDIDATE",
    }:
        return "HIGH"
    return "MODERATE"


def _decision_plain_english(label: str) -> str:
    return {
        "AVOID": "Avoid this setup while a hard gate remains active.",
        "NO_TRADE": "No trade is supported by the current backend state.",
        "WAIT": "Wait for the temporary data, provider, or sample limitation to clear.",
        "WATCH": "Watch only; the current output does not support a directional candidate.",
        "LONG_CANDIDATE": (
            "Long candidate for planning only; current entry permission remains disabled."
        ),
        "SHORT_CANDIDATE": (
            "Short candidate for planning only; current entry permission remains disabled."
        ),
    }[label]


def _timeframe_role(timeframe: str) -> dict:
    role, tactical, hide_probability = _TIMEFRAME_ROLES.get(
        timeframe,
        ("UNSPECIFIED_CONTEXT", False, True),
    )
    return {
        "timeframe": timeframe,
        "role": role,
        "tactical": tactical,
        "raw_probability_hidden_by_default": hide_probability,
        "plain_english": (
            f"{timeframe} is interpreted as {role.lower().replace('_', ' ')}; "
            "it does not change the underlying probability values."
        ),
    }


def _model_quality_summary(calibration: dict, reliability_status: str) -> dict:
    measured = reliability_status == "MEASURED"
    return {
        "calibration_status": str(calibration.get("calibration_status") or "UNKNOWN"),
        "reliability_status": reliability_status,
        "sample_count": _optional_int(calibration.get("sample_count")) if measured else None,
        "sample_gate": _optional_str(calibration.get("sample_gate")) if measured else None,
        "brier_score": _optional_float(calibration.get("brier_score")) if measured else None,
        "log_loss": _optional_float(calibration.get("log_loss")) if measured else None,
        "top_label_hit_rate": (
            _optional_float(calibration.get("top_label_hit_rate")) if measured else None
        ),
        "reliability_available": measured,
        "not_win_rate": True,
        "warning": (
            "Probabilities remain heuristic until enough resolved samples exist; they do not "
            "establish realized outcomes or profitability evidence."
            if not measured
            else "Measured reliability is diagnostic and does not establish profitability."
        ),
    }


def _actionability_stack(
    *,
    label: str,
    gate: dict,
    data_quality: dict,
    provider_state: dict,
    epistemic: dict,
    probability: dict,
    quant_result: dict,
    reliability_status: str,
) -> list[dict]:
    hard_blocks = set(gate.get("hard_blocks") or [])
    data_status = str(data_quality.get("status") or "UNKNOWN")
    provider_status = str(provider_state.get("status") or "UNKNOWN")
    cross_provider = str(
        data_quality.get("cross_provider_state")
        or provider_state.get("cross_provider_state")
        or "UNKNOWN"
    )
    sufficiency = str(epistemic.get("sufficiency_level") or "UNKNOWN")
    tail = quant_result.get("tail_risk_state") or {}
    liquidity = quant_result.get("liquidity_state") or {}
    execution = quant_result.get("execution_realism") or {}
    trend = (quant_result.get("market_features") or {}).get("trend_mtf") or {}
    regime = (quant_result.get("market_features") or {}).get("regime_2state") or {}

    data_check = _status_from_source(data_status, unavailable_is_block=True)
    provider_check = "BLOCK" if "PROVIDER_DEGRADED" in hard_blocks else _provider_status(
        provider_status,
        cross_provider,
    )
    history_check = {
        "SUFFICIENT": "PASS",
        "LOW_SAMPLE": "WARN",
        "VOID": "BLOCK",
    }.get(sufficiency, "UNKNOWN")
    tail_check = (
        "BLOCK"
        if "TAIL_RISK_BREACH" in hard_blocks
        else _status_from_source(str(tail.get("status") or "UNKNOWN"))
    )
    tail_plain_english = (
        "The existing gate result reports a tail-risk breach."
        if "TAIL_RISK_BREACH" in hard_blocks
        else f"Tail-risk status is {tail.get('status', 'UNKNOWN')}."
    )
    execution_blocks = {"LIQUIDITY_NOT_VIABLE", "EXECUTION_COST_TOO_HIGH"} & hard_blocks
    if execution_blocks:
        liquidity_check = "BLOCK"
    elif liquidity.get("status") == "OK" and execution.get("status") == "OK":
        liquidity_check = "PASS"
    elif liquidity or execution:
        liquidity_check = "WARN"
    else:
        liquidity_check = "UNKNOWN"
    edge = probability.get("directional_edge")
    edge_check = "UNKNOWN" if edge is None else "INFO"
    trend_check = "INFO" if trend.get("status") == "OK" else "UNKNOWN"
    regime_check = "INFO" if regime.get("status") == "OK" else "UNKNOWN"
    final_check = (
        "BLOCK"
        if label in {"AVOID", "NO_TRADE"}
        else "WARN"
        if label == "WAIT"
        else "INFO"
    )

    return [
        _check(
            1,
            "data_quality",
            data_check,
            "Data quality",
            f"Data quality status is {data_status}.",
            ["data_quality.status", "data_quality.warnings"],
        ),
        _check(
            2,
            "provider_coherence",
            provider_check,
            "Provider coherence",
            f"Provider status is {provider_status}; cross-provider state is {cross_provider}.",
            ["provider_state.status", "data_quality.cross_provider_state"],
        ),
        _check(
            3,
            "sufficient_history",
            history_check,
            "Sufficient history",
            f"History sufficiency is {sufficiency}.",
            ["epistemic_sufficiency_state.sufficiency_level"],
        ),
        _check(
            4,
            "hard_gates",
            "BLOCK" if _hard_gate_active(gate) else "PASS",
            "Hard gates",
            "One or more hard gates are active."
            if _hard_gate_active(gate)
            else "Hard gates are clear.",
            ["gate_result.hard_gate_passed", "gate_result.hard_blocks"],
        ),
        _check(
            5,
            "tail_risk",
            tail_check,
            "Tail risk",
            tail_plain_english,
            ["tail_risk_state.status", "tail_risk_state.cvar_loss"],
        ),
        _check(
            6,
            "liquidity_execution",
            liquidity_check,
            "Liquidity and execution",
            (
                f"Liquidity is {liquidity.get('status', 'UNKNOWN')}; execution realism is "
                f"{execution.get('status', 'UNKNOWN')}."
            ),
            ["liquidity_state.status", "execution_realism.status"],
        ),
        _check(
            7,
            "directional_edge",
            edge_check,
            "Directional edge",
            "Directional edge is unavailable."
            if edge is None
            else f"Directional edge is {edge:.6f} from existing probability values.",
            ["probability_state.horizons.H_primary"],
        ),
        _check(
            8,
            "mtf_alignment",
            trend_check,
            "Multi-timeframe alignment",
            f"Existing trend label is {trend.get('label', 'UNKNOWN')}.",
            ["market_features.trend_mtf"],
        ),
        _check(
            9,
            "regime_context",
            regime_check,
            "Regime context",
            f"Existing regime is {regime.get('regime', 'UNKNOWN')}.",
            ["market_features.regime_2state"],
        ),
        _check(
            10,
            "entry_quality",
            "UNKNOWN",
            "Entry quality",
            "Numeric entry quality is disabled in UI-D1.1.",
            ["trade_plan_skeleton.disabled_reason"],
        ),
        _check(
            11,
            "calibration_reliability",
            "PASS" if reliability_status == "MEASURED" else "WARN",
            "Calibration reliability",
            f"Reliability status is {reliability_status}.",
            ["calibration_state.reliability_status"],
        ),
        _check(
            12,
            "final_decision",
            final_check,
            "Final decision",
            f"Decision synthesis label is {label}.",
            ["decision_synthesis.decision_synthesis.label"],
        ),
    ]


def _what_would_change_decision(
    *,
    label: str,
    gate: dict,
    data_quality: dict,
    provider_state: dict,
    reliability_status: str,
) -> list[dict]:
    hard_blocks = set(gate.get("hard_blocks") or [])
    degraded = (
        str(data_quality.get("status") or "") != "OK"
        or str(provider_state.get("status") or "") != "OK"
    )
    return [
        _condition(
            "hard_gate_clears",
            _hard_gate_active(gate),
            "Re-evaluate after every active hard gate clears.",
            ["gate_result.hard_blocks"],
        ),
        _condition(
            "tail_risk_normalizes",
            "TAIL_RISK_BREACH" in hard_blocks,
            "Re-evaluate if the existing tail-risk state normalizes.",
            ["tail_risk_state", "gate_result.hard_blocks"],
        ),
        _condition(
            "directional_edge_widens",
            label in {"WAIT", "WATCH"},
            "A wider directional edge could change a watch state, subject to all gates.",
            ["probability_state.horizons.H_primary"],
        ),
        _condition(
            "provider_data_quality_improves",
            degraded,
            "Re-evaluate when provider and data-quality states improve.",
            ["provider_state.status", "data_quality.status"],
        ),
        _condition(
            "price_returns_to_acceptable_zone",
            False,
            "A future validated acceptable zone could support planning; none exists here.",
            ["trade_plan_skeleton.acceptable_entry_zone"],
        ),
        _condition(
            "higher_timeframe_context_aligns",
            label in {"WAIT", "WATCH"},
            "Re-evaluate if existing higher-timeframe context becomes aligned.",
            ["market_features.trend_mtf"],
        ),
        _condition(
            "calibration_sample_gate_improves",
            reliability_status != "MEASURED",
            "Interpretation can strengthen only after the in-payload sample gate improves.",
            ["calibration_state.reliability_status"],
        ),
    ]


def _advisor_explanations(
    *,
    label: str,
    hard_gate_active: bool,
    reliability_status: str,
    timeframe_role: dict,
) -> dict:
    if hard_gate_active:
        probability_reason = "Probability is muted because a hard gate is active."
    elif reliability_status != "MEASURED":
        probability_reason = (
            "Probability is muted because sufficient resolved-sample reliability is absent."
        )
    else:
        probability_reason = "Probability remains context and is not an action command."
    return {
        "why_this_decision": _decision_plain_english(label),
        "why_not_enter_now": (
            "UI-D1.1 has no validated numeric entry, invalidation, or target geometry."
        ),
        "why_probability_is_muted": probability_reason,
        "why_timeframe_matters": timeframe_role["plain_english"],
        "why_reliability_is_insufficient": (
            "The payload does not report measured reliability from sufficient resolved samples."
            if reliability_status != "MEASURED"
            else "The payload reports measured reliability, but it remains diagnostic only."
        ),
    }


def _check(
    priority: int,
    key: str,
    status: str,
    label: str,
    plain_english: str,
    evidence_refs: list[str],
) -> dict:
    return {
        "key": key,
        "status": status,
        "label": label,
        "plain_english": plain_english,
        "evidence_refs": evidence_refs,
        "priority": priority,
    }


def _condition(
    key: str,
    currently_relevant: bool,
    plain_english: str,
    evidence_refs: list[str],
) -> dict:
    return {
        "key": key,
        "currently_relevant": currently_relevant,
        "plain_english": plain_english,
        "evidence_refs": evidence_refs,
        "informational_only": True,
    }


def _status_from_source(status: str, *, unavailable_is_block: bool = False) -> str:
    if status == "OK":
        return "PASS"
    if status == "DEGRADED":
        return "WARN"
    if unavailable_is_block and status in {"UNAVAILABLE", "FAILED", "ERROR"}:
        return "BLOCK"
    if status in {"UNAVAILABLE", "FAILED", "ERROR"}:
        return "WARN"
    return "UNKNOWN"


def _provider_status(provider_status: str, cross_provider: str) -> str:
    if provider_status == "DEGRADED":
        return "WARN"
    if provider_status != "OK":
        return "UNKNOWN"
    if cross_provider in {"OK", "AGREE", "COHERENT"}:
        return "PASS"
    if cross_provider in {"UNKNOWN", "UNAVAILABLE"}:
        return "UNKNOWN"
    return "WARN"


def _optional_float(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value)


def _optional_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _optional_str(value: Any) -> str | None:
    return value if isinstance(value, str) else None
