from __future__ import annotations

import json
from copy import deepcopy
from datetime import timedelta
from uuid import UUID

import crypto_probability_engine.api.analysis_service as analysis_service
import crypto_probability_engine.derivatives_intel.block as block_module
from crypto_probability_engine.api.analysis_service import _pop_prediction_persistence
from crypto_probability_engine.api.schemas import AnalysisRequest
from crypto_probability_engine.config.settings import Settings
from crypto_probability_engine.derivatives_intel.block import build_derivatives_intelligence
from crypto_probability_engine.persistence.feature_snapshot import build_feature_snapshot
from crypto_probability_engine.persistence.run_store import InMemoryRunStore
from crypto_probability_engine.quant.pipeline import run_quant_pipeline
from crypto_probability_engine.quant_v2.contract import build_quant_v2_shadow
from tests.fixtures.market_data import make_snapshot


def analyze(*, enabled: bool) -> tuple[dict, list[dict], list[dict]]:
    payload = analysis_service.analyze_request(
        AnalysisRequest(symbol="BTC", timeframe="4H"),
        settings=Settings(data_mode="fixture", enable_derivatives_intel=enabled),
        run_store=InMemoryRunStore(),
    )
    predictions, snapshots, failed, _, derivatives_failed = (
        _pop_prediction_persistence(payload)
    )
    assert not failed
    assert not derivatives_failed
    return payload, predictions, snapshots


def test_default_off_response_is_strict_and_zero_observation() -> None:
    payload, _, _ = analyze(enabled=False)
    block = payload["derivatives_intelligence"]
    assert block["block_status"] == "DISABLED"
    assert block["observation_as_of_utc"] is None
    assert block["core_prediction_as_of_utc"] == payload["as_of_utc"]


def test_enabled_runtime_failure_never_fails_core_analysis(monkeypatch) -> None:
    def fail_runtime(*args, **kwargs):
        raise RuntimeError("fixture outage")

    monkeypatch.setattr(block_module, "get_raw_derivatives_bundle", fail_runtime)
    payload, _, _ = analyze(enabled=True)
    assert payload["derivatives_intelligence"]["block_status"] == "UNAVAILABLE"
    assert payload["probability_state"]
    assert payload["decision_synthesis"]["action_permission"]["can_enter_now"] is False


def test_post_identity_attachment_preserves_every_protected_artifact(monkeypatch) -> None:
    monkeypatch.setattr(analysis_service, "uuid4", lambda: UUID(int=7))
    baseline, baseline_predictions, baseline_snapshots = analyze(enabled=False)

    def unavailable_block(**kwargs):
        core = kwargs["core_prediction_as_of_utc"]
        return {
            **build_derivatives_intelligence(
                normalized_symbol=kwargs["normalized_symbol"],
                core_prediction_as_of_utc=core,
                enabled=False,
            ),
            "observation_as_of_utc": (core + timedelta(seconds=1)).isoformat(),
            "block_status": "UNAVAILABLE",
            "provider_summary": [
                {
                    "provider": provider,
                    "status": "PROVIDER_UNAVAILABLE",
                    "valid_metric_count": 0,
                    "total_metric_count": 0,
                    "reason": "Fixture provider unavailable.",
                }
                for provider in ("BINANCE_USDM", "OKX_SWAP")
            ],
            "comparability": [
                {
                    "semantic_class": semantic,
                    "left_provider": "BINANCE_USDM",
                    "right_provider": "OKX_SWAP",
                    "comparable": False,
                    "reason": "Both provider-native metrics are required for comparison.",
                }
                for semantic in ("CURRENT_FUNDING", "CURRENT_OPEN_INTEREST")
            ],
            "warnings": ["Fixture derivatives context unavailable."],
        }

    monkeypatch.setattr(analysis_service, "build_derivatives_intelligence", unavailable_block)
    enabled, enabled_predictions, enabled_snapshots = analyze(enabled=True)

    protected_keys = (
        "analysis_hash",
        "probability_state",
        "score_stack",
        "gate_result",
        "decision_brief",
        "decision_synthesis",
        "quant_v2",
    )
    for key in protected_keys:
        assert enabled[key] == baseline[key]
    assert (
        enabled["decision_synthesis"]["action_permission"]
        == baseline["decision_synthesis"]["action_permission"]
    )
    assert (
        enabled["decision_synthesis"]["trade_plan_skeleton"]
        == baseline["decision_synthesis"]["trade_plan_skeleton"]
    )
    assert enabled_predictions == baseline_predictions
    assert enabled_snapshots == baseline_snapshots
    assert enabled != baseline


def test_prediction_row_and_feature_snapshot_are_byte_invariant() -> None:
    snapshot = make_snapshot(provider="binance")
    provider_state = {"status": "OK", "active_provider": "binance"}
    data_quality = {"is_live_data": True, "data_source": "BINANCE_PUBLIC"}
    quant_result = run_quant_pipeline(snapshot, provider_state)
    kwargs = {
        "run_id": "run_derivatives_invariance",
        "request_symbol": "BTC",
        "normalized_symbol": "BTC/USDT",
        "timeframe": "4H",
        "snapshot": snapshot,
        "quant_result": quant_result,
        "data_quality": data_quality,
        "provider_state": provider_state,
    }
    before = analysis_service._prediction_row(**kwargs)
    assert before is not None
    quant_v2 = build_quant_v2_shadow(
        quant_result=quant_result,
        snapshot=snapshot,
        provider_state=provider_state,
        symbol="BTC",
        normalized_symbol="BTC/USDT",
        timeframe="4H",
    )
    snapshot_before = build_feature_snapshot(before, quant_v2)

    build_derivatives_intelligence(
        normalized_symbol="BTC/USDT",
        core_prediction_as_of_utc=snapshot.as_of_utc,
        enabled=False,
    )

    after = analysis_service._prediction_row(**deepcopy(kwargs))
    snapshot_after = build_feature_snapshot(after, deepcopy(quant_v2))
    assert json.dumps(before, sort_keys=True) == json.dumps(after, sort_keys=True)
    assert before["prediction_id"] == after["prediction_id"]
    assert json.dumps(snapshot_before, sort_keys=True) == json.dumps(snapshot_after, sort_keys=True)
