from __future__ import annotations

from datetime import timedelta

import pytest

from crypto_probability_engine.config.defaults import DEFAULT_METHODOLOGY_VERSION
from crypto_probability_engine.quant.pipeline import run_quant_pipeline, stable_hash
from crypto_probability_engine.quant_ng import pipeline_ng
from crypto_probability_engine.quant_ng.pipeline_ng import run_pipeline_reference
from crypto_probability_engine.quant_ng.reference_pooled import (
    PooledReferenceUnavailable,
    RefusalReason,
    compute_pooled_reference,
)
from crypto_probability_engine.score_stack.score import compute_score_stack
from tests.fixtures.market_data import make_candles, make_snapshot


def _legacy(snapshot):
    return run_quant_pipeline(
        snapshot, {"status": "OK"}, methodology_version=DEFAULT_METHODOLOGY_VERSION
    )


def _assert_hash(result):
    payload = {key: value for key, value in result.items() if key != "analysis_hash"}
    assert result["analysis_hash"] == stable_hash(payload)


def test_reference_4h_composes_shared_pipeline_tail():
    snapshot = make_snapshot(timeframe="4H", count=210)
    result = run_pipeline_reference(
        snapshot, {"status": "OK"}, window_candles=snapshot.candles, window_source="SNAPSHOT"
    )
    legacy = _legacy(snapshot)
    band = result["execution_realism"]["round_trip_cost_frac"]
    ref = compute_pooled_reference(snapshot.candles, timeframe="4H", band_frac=band)
    primary = result["probability_state"]["horizons"]["H_primary"]
    assert (primary["p_up_frac"], primary["p_down_frac"], primary["p_timeout_frac"]) == (
        ref.p_up_frac,
        ref.p_down_frac,
        ref.p_timeout_frac,
    )
    assert primary["p_up_frac"] == primary["p_down_frac"]
    assert primary["confidence_frac"] == 0.0
    assert result["horizon_timeout_state"]["method"] == "reference-pooled-tk-v1"
    assert result["horizon_timeout_state"]["semantics"] == "TERMINAL_INSIDE_BAND"
    assert "reference_pooled_tk" in result["quant_compute_state"]["models_run"]
    _assert_hash(result)
    score = compute_score_stack(result["probability_state"], result["risk_arbiter_state"])
    if result["gate_result"].get("forced_score_disposition"):
        score = {
            **score,
            "disposition": result["gate_result"]["forced_score_disposition"],
            "risk_guard_applied": True,
        }
    assert result["score_stack"] == score
    for key in (
        "market_features",
        "liquidity_state",
        "execution_realism",
        "risk_arbiter_state",
        "tail_risk_state",
    ):
        assert result[key] == legacy[key]


@pytest.mark.parametrize("mock_risk_pressure", [0.0, 0.25, 0.75, 1.0])
def test_reference_score_has_zero_edge_and_never_exceeds_neutral_under_mock_risk(
    monkeypatch, mock_risk_pressure
):
    snapshot = make_snapshot(timeframe="4H", count=210)
    compute_risk = pipeline_ng.compute_risk_arbiter

    def mock_risk(*args):
        state = compute_risk(*args)
        return {**state, "risk_pressure": mock_risk_pressure}

    monkeypatch.setattr(pipeline_ng, "compute_risk_arbiter", mock_risk)
    result = run_pipeline_reference(
        snapshot, {"status": "OK"}, window_candles=snapshot.candles, window_source="SNAPSHOT"
    )
    assert result["score_stack"]["directional_edge"] == 0.0
    assert result["score_stack"]["total_score"] <= 50


def test_reference_15m_uses_history_only_for_pooled_estimate():
    snapshot = make_snapshot(timeframe="15m", count=205)
    prefix = make_candles(
        count=473,
        timeframe_seconds=900,
        as_of_utc=snapshot.candles[0].close_time_utc - timedelta(seconds=900),
    )
    window = prefix + snapshot.candles
    assert len(window) == 678
    assert window[-205:] == snapshot.candles
    result = run_pipeline_reference(
        snapshot, {"status": "OK"}, window_candles=window, window_source="HISTORY"
    )
    legacy = _legacy(snapshot)
    ref = compute_pooled_reference(
        window, timeframe="15m", band_frac=result["execution_realism"]["round_trip_cost_frac"]
    )
    primary = result["probability_state"]["horizons"]["H_primary"]
    assert primary["p_timeout_frac"] == ref.p_timeout_frac
    assert result["market_features"] == legacy["market_features"]
    for key in (
        "liquidity_state",
        "execution_realism",
        "risk_arbiter_state",
        "tail_risk_state",
        "trend_summary",
        "global_risk_state",
        "calibration_state",
        "epistemic_sufficiency_state",
    ):
        assert result[key] == legacy[key]
    _assert_hash(result)


def test_reference_refusals_propagate(monkeypatch):
    snapshot = make_snapshot(timeframe="4H", count=210)
    malformed = snapshot.candles[:-1] + (make_candles(count=1)[0],)
    with pytest.raises(PooledReferenceUnavailable) as exc:
        run_pipeline_reference(
            snapshot, {}, window_candles=malformed, window_source="SNAPSHOT"
        )
    assert exc.value.reason == RefusalReason.WINDOW_MALFORMED

    with pytest.raises(PooledReferenceUnavailable) as exc:
        run_pipeline_reference(
            snapshot,
            {},
            window_candles=snapshot.candles[-100:],
            window_source="SNAPSHOT",
        )
    assert exc.value.reason == RefusalReason.WINDOW_SHORT

    monkeypatch.setattr(
        pipeline_ng,
        "compute_execution_realism",
        lambda _liquidity: {"round_trip_cost_frac": None},
    )
    with pytest.raises(PooledReferenceUnavailable) as exc:
        run_pipeline_reference(
            snapshot, {}, window_candles=snapshot.candles, window_source="SNAPSHOT"
        )
    assert exc.value.reason == RefusalReason.BAND_UNAVAILABLE


def test_reference_epistemic_null_keeps_triplet_and_runs_gates(monkeypatch):
    snapshot = make_snapshot(timeframe="4H", count=210)
    monkeypatch.setattr(
        pipeline_ng,
        "assess_epistemic_sufficiency",
        lambda _snapshot: {"action": "ABORT", "reason": "MOCK_VOID"},
    )
    result = run_pipeline_reference(
        snapshot,
        {"status": "OK"},
        window_candles=snapshot.candles,
        window_source="SNAPSHOT",
    )
    state = result["probability_state"]
    primary = state["horizons"]["H_primary"]
    assert primary["status"] == "NULL"
    assert primary["null_reason"] == "MOCK_VOID"
    assert primary["p_up_frac"] == primary["p_down_frac"]
    assert primary["p_up_frac"] + primary["p_down_frac"] + primary["p_timeout_frac"] == 1.0
    assert result["gate_result"]


def test_reference_is_deterministic():
    snapshot = make_snapshot(timeframe="4H", count=210)
    args = {
        "snapshot": snapshot,
        "provider_state": {"status": "OK"},
        "window_candles": snapshot.candles,
        "window_source": "SNAPSHOT",
    }
    first = run_pipeline_reference(**args)
    second = run_pipeline_reference(**args)
    assert first == second
