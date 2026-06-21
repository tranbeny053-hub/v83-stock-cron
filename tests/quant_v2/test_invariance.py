from __future__ import annotations

import inspect
import json
from copy import deepcopy

import crypto_probability_engine.api.analysis_service as analysis_service
from crypto_probability_engine.api.schemas import AnalysisMode, AnalysisRequest
from crypto_probability_engine.config.settings import Settings
from crypto_probability_engine.detail.decision_brief import build_decision_brief
from crypto_probability_engine.detail.decision_synthesis import build_decision_synthesis
from crypto_probability_engine.persistence.run_store import InMemoryRunStore
from crypto_probability_engine.quant.pipeline import run_quant_pipeline, stable_hash
from crypto_probability_engine.quant_v2.contract import build_quant_v2_shadow
from tests.fixtures.market_data import make_snapshot
from tests.fixtures.sample_payloads import sample_analysis_payload

NULL_PLAN_FIELDS = (
    "preferred_entry_zone",
    "acceptable_entry_zone",
    "chase_zone",
    "breakout_trigger",
    "pullback_trigger",
    "stop_invalidation",
    "take_profit_plan",
    "risk_reward_summary",
)


def _provider_state() -> dict:
    return {"status": "OK", "active_provider": "binance"}


def _build(snapshot, quant_result) -> dict:
    return build_quant_v2_shadow(
        quant_result=quant_result,
        snapshot=snapshot,
        provider_state=_provider_state(),
        symbol="BTC",
        normalized_symbol="BTC/USDT",
        timeframe="4H",
        enabled=True,
    )


def test_builder_does_not_mutate_full_decision_relevant_outputs() -> None:
    snapshot = make_snapshot(provider="binance")
    quant_result = run_quant_pipeline(snapshot, _provider_state())
    before = deepcopy(quant_result)
    decision_brief = build_decision_brief(
        symbol="BTC",
        normalized_symbol="BTC/USDT",
        timeframe="4H",
        quant_result=quant_result,
        data_quality={"status": "OK", "is_live_data": True},
    )
    decision_before = build_decision_synthesis(
        timeframe="4H",
        quant_result=quant_result,
        data_quality={"status": "OK", "is_live_data": True},
        provider_state=_provider_state(),
        decision_brief=decision_brief,
    )

    _build(snapshot, quant_result)

    assert quant_result == before
    assert quant_result["probability_state"] == before["probability_state"]
    assert quant_result["score_stack"] == before["score_stack"]
    assert quant_result["gate_result"] == before["gate_result"]
    assert quant_result["gate_result"]["action"] == before["gate_result"]["action"]
    assert quant_result["gate_result"]["hard_blocks"] == before["gate_result"]["hard_blocks"]
    primary = quant_result["probability_state"]["horizons"]["H_primary"]
    assert primary["p_up_frac"] + primary["p_down_frac"] + primary["p_timeout_frac"] == 1.0
    decision_after = build_decision_synthesis(
        timeframe="4H",
        quant_result=quant_result,
        data_quality={"status": "OK", "is_live_data": True},
        provider_state=_provider_state(),
        decision_brief=decision_brief,
    )
    assert decision_after == decision_before
    assert decision_after["decision_synthesis"]["label"] == decision_before[
        "decision_synthesis"
    ]["label"]
    assert decision_after["action_permission"] == decision_before["action_permission"]
    assert decision_after["action_permission"]["can_enter_now"] is False
    assert decision_after["action_permission"]["can_chase"] is False
    plan = decision_after["trade_plan_skeleton"]
    assert all(plan[field] is None for field in NULL_PLAN_FIELDS)
    assert plan["not_trade_command"] is True
    assert plan["not_financial_advice"] is True
    assert decision_after["future_quant_v2_hooks"]["decision_influence_frac"] == 0.0
    assert decision_after["future_quant_v2_hooks"]["influence_mode"] == "SHADOW_ONLY"


def test_prediction_id_and_prediction_row_bytes_are_unchanged() -> None:
    snapshot = make_snapshot(provider="binance")
    quant_result = run_quant_pipeline(snapshot, _provider_state())
    kwargs = {
        "run_id": "run_quant_v2_identity",
        "request_symbol": "BTC",
        "normalized_symbol": "BTC/USDT",
        "timeframe": "4H",
        "snapshot": snapshot,
        "quant_result": quant_result,
        "data_quality": {
            "is_live_data": True,
            "data_source": "BINANCE_PUBLIC",
            "cross_provider_state": "UNAVAILABLE",
        },
        "provider_state": _provider_state(),
    }
    before = analysis_service._prediction_row(**kwargs)
    before_bytes = json.dumps(before, sort_keys=True, separators=(",", ":")).encode()

    _build(snapshot, quant_result)

    after = analysis_service._prediction_row(**kwargs)
    after_bytes = json.dumps(after, sort_keys=True, separators=(",", ":")).encode()
    assert before == after
    assert before_bytes == after_bytes
    assert before["prediction_id"] == "run_quant_v2_identity:4H"
    assert "quant_v2" not in before


def test_analysis_hash_and_prediction_row_are_built_before_shadow_attachment(monkeypatch) -> None:
    captured_hash_inputs: list[dict] = []
    events: list[str] = []
    real_prediction_row = analysis_service._prediction_row
    real_builder = analysis_service.build_quant_v2_shadow

    def capture_hash(payload):
        captured_hash_inputs.append(deepcopy(payload))
        return stable_hash(payload)

    def capture_prediction(**kwargs):
        events.append("prediction_row")
        return real_prediction_row(**kwargs)

    def capture_shadow(**kwargs):
        events.append("quant_v2")
        return real_builder(**kwargs)

    monkeypatch.setattr(analysis_service, "stable_hash", capture_hash)
    monkeypatch.setattr(analysis_service, "_prediction_row", capture_prediction)
    monkeypatch.setattr(analysis_service, "build_quant_v2_shadow", capture_shadow)
    payload = analysis_service.analyze_request(
        AnalysisRequest(symbol="BTC", timeframe="4H", analysis_mode=AnalysisMode.METRICS_ONLY),
        settings=Settings(data_mode="fixture"),
        run_store=InMemoryRunStore(),
    )

    assert events == ["prediction_row", "quant_v2"]
    assert len(captured_hash_inputs) == 1
    assert "quant_v2" not in captured_hash_inputs[0]
    assert payload["analysis_hash"] == stable_hash(captured_hash_inputs[0])
    assert payload["quant_v2"]["influence_mode"] == "SHADOW_ONLY"


def test_disabled_flag_still_attaches_full_valid_response_block(monkeypatch) -> None:
    monkeypatch.setattr(analysis_service, "QUANT_V2_SHADOW_ENABLED", False)

    payload = analysis_service.analyze_request(
        AnalysisRequest(symbol="BTC", timeframe="4H", analysis_mode=AnalysisMode.METRICS_ONLY),
        settings=Settings(data_mode="fixture"),
        run_store=InMemoryRunStore(),
    )

    block = payload["quant_v2"]
    assert block["status"] == "DISABLED"
    assert block["influence_mode"] == "SHADOW_ONLY"
    assert block["features"] == []
    assert block["feature_count"] == 0
    assert block["not_trade_command"] is True
    assert block["not_financial_advice"] is True


def test_quant_v2_is_excluded_from_every_persistence_mapper() -> None:
    payload = sample_analysis_payload()
    baseline = deepcopy(payload)
    baseline.pop("quant_v2")

    assert analysis_service._run_summary(payload) == analysis_service._run_summary(baseline)
    assert analysis_service._timeframe_result(payload) == analysis_service._timeframe_result(
        baseline
    )
    assert analysis_service._provider_observations(
        payload
    ) == analysis_service._provider_observations(baseline)
    for mapped in (
        analysis_service._run_summary(payload),
        analysis_service._timeframe_result(payload),
        *analysis_service._provider_observations(payload),
    ):
        assert "quant_v2" not in mapped


def test_shadow_module_has_no_repository_calibration_or_resolver_dependency() -> None:
    module = __import__("crypto_probability_engine.quant_v2.contract", fromlist=["*"])
    source = inspect.getsource(module)
    for forbidden in (
        "persistence",
        "calibration",
        "resolver",
        "save_prediction",
        "save_prediction_outcome",
    ):
        assert forbidden not in source
