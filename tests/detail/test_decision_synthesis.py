from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, RefResolver

from crypto_probability_engine.api.schemas import AnalysisResponse
from crypto_probability_engine.detail.decision_synthesis import build_decision_synthesis
from tests.fixtures.sample_payloads import sample_analysis_payload

ROOT = Path(__file__).resolve().parents[2]
TRADE_PLAN_NULL_FIELDS = (
    "preferred_entry_zone",
    "acceptable_entry_zone",
    "chase_zone",
    "breakout_trigger",
    "pullback_trigger",
    "stop_invalidation",
    "take_profit_plan",
    "risk_reward_summary",
)
ACTIONABILITY_KEYS = [
    "data_quality",
    "provider_coherence",
    "sufficient_history",
    "hard_gates",
    "tail_risk",
    "liquidity_execution",
    "directional_edge",
    "mtf_alignment",
    "regime_context",
    "entry_quality",
    "calibration_reliability",
    "final_decision",
]


def _inputs(*, p_up: float = 0.55, p_down: float = 0.25, p_timeout: float = 0.20):
    quant_result = {
        "gate_result": {
            "action": "CONSTRUCTIVE",
            "hard_gate_passed": True,
            "hard_blocks": [],
        },
        "score_stack": {
            "status": "OK",
            "disposition": "CONSTRUCTIVE",
            "directional_edge": p_up - p_down,
            "news_influence_frac": 0.0,
        },
        "epistemic_sufficiency_state": {
            "sufficiency_level": "SUFFICIENT",
            "action": "ALLOW",
        },
        "probability_state": {
            "horizons": {
                "H_primary": {
                    "p_up_frac": p_up,
                    "p_down_frac": p_down,
                    "p_timeout_frac": p_timeout,
                    "status": "OK",
                }
            }
        },
        "calibration_state": {
            "calibration_status": "DEFAULT_PHASE1A",
            "reliability_status": "INSUFFICIENT_SAMPLE",
            "profitability_claim": False,
        },
        "tail_risk_state": {"status": "OK", "cvar_loss": 0.01},
        "liquidity_state": {"status": "OK"},
        "execution_realism": {"status": "OK"},
        "market_features": {
            "trend_mtf": {"status": "OK", "label": "UP"},
            "regime_2state": {"status": "OK", "regime": "NORMAL_VARIANCE"},
        },
    }
    return {
        "timeframe": "4H",
        "quant_result": quant_result,
        "data_quality": {
            "status": "OK",
            "is_live_data": True,
            "cross_provider_state": "AGREE",
            "warnings": [],
        },
        "provider_state": {"status": "OK", "cross_provider_state": "AGREE"},
        "decision_brief": {
            "action": "SPOT_WATCH",
            "reliability_status": "INSUFFICIENT_SAMPLE",
            "profitability_claim": False,
        },
    }


def _build(**changes) -> dict:
    inputs = _inputs()
    inputs.update(changes)
    return build_decision_synthesis(**inputs)


def _assert_plan_disabled(result: dict) -> None:
    assert result["action_permission"]["can_enter_now"] is False
    assert result["action_permission"]["can_chase"] is False
    plan = result["trade_plan_skeleton"]
    assert plan["can_enter_now"] is False
    assert plan["can_chase"] is False
    assert plan["disabled_reason"]
    assert all(plan[field] is None for field in TRADE_PLAN_NULL_FIELDS)


def _all_strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, child in value.items():
            yield key
            yield from _all_strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from _all_strings(child)


def test_hard_gate_active_is_avoid_and_probability_is_informational_only() -> None:
    inputs = _inputs()
    inputs["quant_result"]["gate_result"] = {
        "action": "ABORT",
        "hard_gate_passed": False,
        "hard_blocks": ["EPISTEMIC_VOID"],
    }

    result = build_decision_synthesis(**inputs)

    assert result["decision_synthesis"]["label"] in {"AVOID", "NO_TRADE"}
    assert result["probability_interpretation"]["informational_only"] is True
    _assert_plan_disabled(result)


def test_elevated_risk_avoid_maps_to_no_trade() -> None:
    inputs = _inputs()
    inputs["quant_result"]["score_stack"]["disposition"] = "ELEVATED_RISK_AVOID"

    result = build_decision_synthesis(**inputs)

    assert result["decision_synthesis"]["label"] == "NO_TRADE"


def test_watch_disposition_maps_to_watch() -> None:
    inputs = _inputs()
    inputs["quant_result"]["score_stack"]["disposition"] = "WATCH"
    inputs["quant_result"]["gate_result"]["action"] = "WATCH"

    result = build_decision_synthesis(**inputs)

    assert result["decision_synthesis"]["label"] == "WATCH"


def test_transient_low_sample_or_live_provider_degradation_maps_to_wait() -> None:
    low_sample = _inputs()
    low_sample["quant_result"]["epistemic_sufficiency_state"][
        "sufficiency_level"
    ] = "LOW_SAMPLE"
    degraded = _inputs()
    degraded["provider_state"]["status"] = "DEGRADED"

    assert build_decision_synthesis(**low_sample)["decision_synthesis"]["label"] == "WAIT"
    assert build_decision_synthesis(**degraded)["decision_synthesis"]["label"] == "WAIT"


def test_long_candidate_can_be_planned_but_never_entered_or_chased() -> None:
    result = build_decision_synthesis(**_inputs(p_up=0.60, p_down=0.20, p_timeout=0.20))

    assert result["decision_synthesis"]["label"] == "LONG_CANDIDATE"
    assert result["decision_synthesis"]["decision_strength"] == "MODERATE"
    assert result["action_permission"]["can_plan_trade"] is True
    assert result["trade_plan_skeleton"]["can_plan_trade"] is True
    _assert_plan_disabled(result)


def test_short_candidate_never_populates_numeric_plan() -> None:
    result = build_decision_synthesis(**_inputs(p_up=0.20, p_down=0.60, p_timeout=0.20))

    assert result["decision_synthesis"]["label"] == "SHORT_CANDIDATE"
    assert result["action_permission"]["can_plan_trade"] is True
    _assert_plan_disabled(result)


def test_probability_math_and_zero_directional_denominator() -> None:
    result = build_decision_synthesis(**_inputs(p_up=0.52, p_down=0.28, p_timeout=0.20))
    probability = result["probability_interpretation"]
    assert probability["directional_edge"] == pytest.approx(0.52 - 0.28)
    assert probability["resolution_probability"] == pytest.approx(1.0 - 0.20)
    assert probability["directional_balance"] == pytest.approx(0.52 / (0.52 + 0.28))

    zero_mass = build_decision_synthesis(**_inputs(p_up=0.0, p_down=0.0, p_timeout=1.0))
    assert zero_mass["probability_interpretation"]["directional_balance"] is None


@pytest.mark.parametrize(
    ("timeframe", "role", "tactical", "hidden"),
    [
        ("15m", "TACTICAL_TIMING", True, False),
        ("1H", "TACTICAL_SWING_BRIDGE", True, False),
        ("4H", "SETUP_QUALITY", True, False),
        ("1D", "SWING_CONTEXT", False, False),
        ("1W", "REGIME_CONTEXT", False, True),
        ("1M", "MACRO_BACKDROP", False, True),
    ],
)
def test_timeframe_role_mapping(timeframe: str, role: str, tactical: bool, hidden: bool) -> None:
    inputs = _inputs()
    inputs["timeframe"] = timeframe

    result = build_decision_synthesis(**inputs)

    assert result["timeframe_role"]["role"] == role
    assert result["timeframe_role"]["tactical"] is tactical
    assert result["timeframe_role"]["raw_probability_hidden_by_default"] is hidden


def test_model_quality_is_honest_without_measured_in_payload_calibration() -> None:
    result = _build()
    quality = result["model_quality_summary"]

    assert quality["reliability_available"] is False
    assert quality["not_win_rate"] is True
    assert "heuristic" in quality["warning"].lower()
    for field in (
        "sample_count",
        "sample_gate",
        "brier_score",
        "log_loss",
        "top_label_hit_rate",
    ):
        assert quality[field] is None


def test_actionability_stack_has_exact_keys_statuses_and_priority_order() -> None:
    stack = _build()["actionability_stack"]

    assert [item["key"] for item in stack] == ACTIONABILITY_KEYS
    assert [item["priority"] for item in stack] == list(range(1, 13))
    assert all(item["status"] in {"PASS", "WARN", "BLOCK", "INFO", "UNKNOWN"} for item in stack)


def test_builder_is_pure_and_preserves_profitability_and_news_inputs() -> None:
    inputs = _inputs()
    original = deepcopy(inputs)

    build_decision_synthesis(**inputs)

    assert inputs == original
    assert inputs["quant_result"]["calibration_state"]["profitability_claim"] is False
    assert inputs["quant_result"]["score_stack"]["news_influence_frac"] == 0.0


def test_no_emitted_string_contains_forbidden_wording() -> None:
    forbidden = (
        "buy " "now",
        "sell " "now",
        "guaran" "teed",
        "safe " "trade",
        "sure " "long",
        "sure " "short",
        "will " "pump",
        "will " "dump",
        "win " "rate",
        "profit" "able",
        "confidence is " "high",
        "accuracy " "proven",
        "guaran" "teed " "profit",
    )
    emitted = "\n".join(_all_strings(_build())).lower()

    assert not any(phrase in emitted for phrase in forbidden)


def test_analysis_response_and_json_schema_accept_decision_synthesis() -> None:
    payload = sample_analysis_payload()
    payload["decision_synthesis"] = _build()

    model = AnalysisResponse.model_validate(payload)
    assert model.decision_synthesis["decision_synthesis"]["label"] == "LONG_CANDIDATE"

    response_schema = json.loads((ROOT / "schemas" / "response.schema.json").read_text())
    store = {
        name: json.loads((ROOT / "schemas" / name).read_text())
        for name in ("quant.schema.json", "detail_view.schema.json")
    }
    validator = Draft202012Validator(
        response_schema,
        resolver=RefResolver.from_schema(response_schema, store=store),
    )
    validator.validate(payload)


def test_future_quant_hooks_are_shadow_only_with_zero_decision_influence() -> None:
    hooks = _build()["future_quant_v2_hooks"]

    assert hooks["influence_mode"] == "SHADOW_ONLY"
    assert hooks["decision_influence_frac"] == 0.0
