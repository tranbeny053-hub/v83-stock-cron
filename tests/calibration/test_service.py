from __future__ import annotations

from crypto_probability_engine.calibration.service import build_calibration_report, sample_gate_for
from crypto_probability_engine.persistence.repository import InMemoryPersistenceRepository


def test_sample_gate_thresholds() -> None:
    assert sample_gate_for(0) == "NO_SAMPLES"
    assert sample_gate_for(99) == "INSUFFICIENT_SAMPLE"
    assert sample_gate_for(100) == "WARMING_UP"
    assert sample_gate_for(299) == "WARMING_UP"
    assert sample_gate_for(300) == "PRELIMINARY_MEASURED"
    assert sample_gate_for(499) == "PRELIMINARY_MEASURED"
    assert sample_gate_for(500) == "MEASURED"


def test_per_timeframe_sample_gate_is_isolated() -> None:
    repo = InMemoryPersistenceRepository()
    for index in range(120):
        _save_pair(repo, f"run_15m_{index}:15m", timeframe="15m")
    for index in range(20):
        _save_pair(repo, f"run_1h_{index}:1H", timeframe="1H")

    report_15m = build_calibration_report(repo, timeframe="15m")
    report_1h = build_calibration_report(repo, timeframe="1H")

    assert report_15m["valid_count"] == 120
    assert report_15m["sample_gate"] == "WARMING_UP"
    assert report_1h["valid_count"] == 20
    assert report_1h["sample_gate"] == "INSUFFICIENT_SAMPLE"


def test_version_mix_warning_and_versions_present() -> None:
    repo = InMemoryPersistenceRepository()
    _save_pair(repo, "run_a:15m", model_version="m1", methodology_version="x1")
    _save_pair(repo, "run_b:15m", model_version="m2", methodology_version="x1")

    report = build_calibration_report(repo, timeframe="15m")

    assert report["version_mix_warning"] is True
    assert report["versions_present"] == {
        "model_versions": ["m1", "m2"],
        "methodology_versions": ["x1"],
    }
    assert "VERSION_MIX_WARNING" in report["warnings"]


def test_symbol_scope_warns_when_insufficient() -> None:
    repo = InMemoryPersistenceRepository()
    _save_pair(repo, "run_sol:15m", symbol="SOL", normalized_symbol="SOL/USDT")

    report = build_calibration_report(repo, normalized_symbol="SOL/USDT")

    assert report["sample_gate"] == "INSUFFICIENT_SAMPLE"
    assert "SYMBOL_INSUFFICIENT_SAMPLE" in report["warnings"]


def test_no_samples_report_shape() -> None:
    report = build_calibration_report(InMemoryPersistenceRepository(), timeframe="15m")

    assert report["status"] == "OK"
    assert report["sample_count"] == 0
    assert report["valid_count"] == 0
    assert report["sample_gate"] == "NO_SAMPLES"
    assert report["metrics"]["brier_score"] is None


def _save_pair(
    repo: InMemoryPersistenceRepository,
    prediction_id: str,
    *,
    symbol: str = "BTC",
    normalized_symbol: str = "BTC/USDT",
    timeframe: str = "15m",
    model_version: str = "phase1a-wave4b0",
    methodology_version: str = "heuristic-v1-wave4b0",
) -> None:
    repo.save_prediction(
        {
            "prediction_id": prediction_id,
            "run_id": prediction_id.split(":")[0],
            "operator_id": "operator",
            "symbol": symbol,
            "normalized_symbol": normalized_symbol,
            "timeframe": timeframe,
            "horizon_bars": 6,
            "predicted_at_utc": "2026-06-07T00:00:00Z",
            "reference_close_utc": "2026-06-07T00:00:00Z",
            "reference_price": 100.0,
            "horizon_end_utc": "2026-06-07T01:30:00Z",
            "p_up_frac": 0.6,
            "p_down_frac": 0.2,
            "p_timeout_frac": 0.2,
            "decision_band_frac": 0.003,
            "model_version": model_version,
            "methodology_version": methodology_version,
            "calibration_status": "DEFAULT_PHASE1A",
            "reliability_status": "INSUFFICIENT_SAMPLE",
            "epistemic_sufficiency": "SUFFICIENT",
            "gate_action": "WATCH",
            "data_source": "BINANCE_PUBLIC",
            "is_live_data": True,
            "cross_provider_state": "UNAVAILABLE",
        }
    )
    repo.save_prediction_outcome(
        {
            "prediction_id": prediction_id,
            "resolved_at_utc": "2026-06-07T01:35:00Z",
            "outcome_close_utc": "2026-06-07T01:30:00Z",
            "outcome_reference_price": 101.0,
            "terminal_return_frac": 0.01,
            "realized_label": "UP",
            "decision_band_frac": 0.003,
            "max_favorable_frac": 0.015,
            "max_adverse_frac": -0.002,
            "candles_observed": 6,
            "resolver_version": "resolver-v1-wave4b2",
            "data_source": "BINANCE_PUBLIC",
            "is_live_data": True,
        }
    )

