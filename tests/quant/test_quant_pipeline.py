from __future__ import annotations

from dataclasses import replace

from crypto_probability_engine.adapters.types import MarketSnapshot
from crypto_probability_engine.gates.composite import apply_composite_gates
from crypto_probability_engine.quant.pipeline import run_quant_pipeline
from crypto_probability_engine.quant.tail_cvar import compute_tail_cvar
from crypto_probability_engine.score_stack.score import ALLOWED_DISPOSITIONS, compute_score_stack
from tests.fixtures.market_data import make_candles, make_downtrend_snapshot, make_snapshot


def test_probability_invariant_for_pipeline() -> None:
    result = run_quant_pipeline(make_snapshot(), {"status": "OK"})
    for horizon in result["probability_state"]["horizons"].values():
        total = horizon["p_up_frac"] + horizon["p_down_frac"] + horizon["p_timeout_frac"]
        assert total == 1.0
        assert 0.0 <= horizon["p_up_frac"] <= 1.0
        assert 0.0 <= horizon["p_down_frac"] <= 1.0
        assert 0.0 <= horizon["p_timeout_frac"] <= 1.0


def test_down_market_fixture_allows_negative_signed_fields() -> None:
    result = run_quant_pipeline(make_downtrend_snapshot(), {"status": "OK"})
    trend = result["market_features"]["trend_mtf"]
    risk = result["risk_arbiter_state"]
    score = result["score_stack"]
    assert trend["primary_return"] < 0.0
    assert trend["extended_return"] < 0.0
    assert risk["alpha_signal"] < 0.0
    assert risk["net_signal"] < 0.0
    assert score["directional_edge"] < 0.0
    assert not any(key.endswith("_return_frac") for key in trend)
    assert not any(key.endswith("_signal_frac") for key in risk)
    assert "directional_edge" + "_frac" not in score
    horizon = result["probability_state"]["horizons"]["H_primary"]
    assert horizon["p_up_frac"] + horizon["p_down_frac"] + horizon["p_timeout_frac"] == 1.0


def test_pipeline_is_deterministic_under_fixed_fixture() -> None:
    first = run_quant_pipeline(make_snapshot(), {"status": "OK"})
    second = run_quant_pipeline(make_snapshot(), {"status": "OK"})
    assert first["analysis_hash"] == second["analysis_hash"]


def test_hard_gate_beats_high_score() -> None:
    gate = apply_composite_gates(
        epistemic_state={"action": "ABORT"},
        provider_state={"status": "OK"},
        score_state={"disposition": "CONSTRUCTIVE_CAUTIOUS", "total_score": 99},
    )
    assert gate["action"] == "ABORT"
    assert gate["score_ignored"] is True


def test_score_disposition_is_blueprint_allowed() -> None:
    probability = {
        "horizons": {
            "H_primary": {
                "p_up_frac": 0.10,
                "p_down_frac": 0.70,
                "p_timeout_frac": 0.20,
            }
        }
    }
    score = compute_score_stack(probability, {"risk_pressure_frac": 0.0})
    assert score["disposition"] in ALLOWED_DISPOSITIONS
    assert score["disposition"] == "ELEVATED_RISK_AVOID"


def test_timeout_is_not_directional() -> None:
    result = run_quant_pipeline(make_snapshot(), {"status": "OK"})
    timeout = result["probability_state"]["horizons"]["H_primary"]["p_timeout_frac"]
    up = result["probability_state"]["horizons"]["H_primary"]["p_up_frac"]
    down = result["probability_state"]["horizons"]["H_primary"]["p_down_frac"]
    assert timeout > 0.0
    assert result["horizon_timeout_state"]["timeout_is_directional"] is False
    assert up + down + timeout == 1.0


def test_tail_cvar_baseline_is_historical_and_evt_disabled() -> None:
    state = compute_tail_cvar(make_candles())
    assert state["tail_method"] == "HISTORICAL_CVAR"
    assert state["evt_status"] == "DISABLED_PHASE1A"
    assert state["cvar_loss_frac"] >= 0.0


def test_epistemic_void_aborts_pipeline() -> None:
    short_snapshot = make_snapshot()
    short_snapshot = MarketSnapshot(
        provider=short_snapshot.provider,
        normalized_symbol=short_snapshot.normalized_symbol,
        timeframe=short_snapshot.timeframe,
        candles=make_candles(count=10),
        order_book=short_snapshot.order_book,
        as_of_utc=short_snapshot.as_of_utc,
        source_status=short_snapshot.source_status,
    )
    result = run_quant_pipeline(short_snapshot, {"status": "OK"})
    assert result["epistemic_sufficiency_state"]["sufficiency_level"] == "VOID"
    assert result["gate_result"]["action"] == "ABORT"
    assert result["probability_state"]["null_reason"] == "INSUFFICIENT_DATA"


def test_net_of_cost_binding_removes_tiny_signal() -> None:
    snapshot = make_snapshot()
    candles = list(snapshot.candles)
    last = candles[-1]
    candles[-1] = replace(last, close=last.open + 0.0001)
    tiny_snapshot = MarketSnapshot(
        provider=snapshot.provider,
        normalized_symbol=snapshot.normalized_symbol,
        timeframe=snapshot.timeframe,
        candles=tuple(candles),
        order_book=snapshot.order_book,
        as_of_utc=snapshot.as_of_utc,
        source_status=snapshot.source_status,
    )
    result = run_quant_pipeline(tiny_snapshot, {"status": "OK"})
    assert result["execution_realism"]["net_of_cost_binding"] is True


def test_bad_liquidity_forces_non_constructive() -> None:
    snapshot = make_snapshot()
    bad_snapshot = MarketSnapshot(
        provider=snapshot.provider,
        normalized_symbol=snapshot.normalized_symbol,
        timeframe=snapshot.timeframe,
        candles=snapshot.candles,
        order_book=None,
        as_of_utc=snapshot.as_of_utc,
        source_status=snapshot.source_status,
    )
    result = run_quant_pipeline(bad_snapshot, {"status": "OK"})
    assert result["gate_result"]["action"] == "NO_TRADE"
    assert result["score_stack"]["disposition"] == "ELEVATED_RISK_AVOID"
    assert result["score_stack"]["disposition"] not in {
        "CONSTRUCTIVE",
        "CONSTRUCTIVE_CAUTIOUS",
    }


def test_high_tail_forces_non_constructive() -> None:
    gate = apply_composite_gates(
        epistemic_state={"action": "ALLOW"},
        provider_state={"status": "OK"},
        score_state={"disposition": "CONSTRUCTIVE_CAUTIOUS", "total_score": 99},
        liquidity_state={"status": "OK", "spread_frac": 0.001, "top_depth_quote": 10_000.0},
        tail_risk_state={"status": "OK", "cvar_loss_frac": 0.99},
        execution_state={"status": "OK", "round_trip_cost_frac": 0.001},
    )
    assert gate["action"] == "NO_TRADE"
    assert gate["forced_score_disposition"] == "ELEVATED_RISK_AVOID"
    assert gate["action"] not in {"CONSTRUCTIVE", "CONSTRUCTIVE_CAUTIOUS"}
