from __future__ import annotations

from crypto_probability_engine.shadow_validation.binning import (
    apply_frozen_edges,
    chronological_split,
    fit_frozen_quantile_edges,
)
from crypto_probability_engine.shadow_validation.metrics import baseline_diagnostics
from crypto_probability_engine.shadow_validation.schemas import sample_gate
from tests.shadow_validation.conftest import make_validation_row


def test_sample_gate_boundaries_use_effective_n() -> None:
    expected = {
        0: "NO_SAMPLES",
        1: "INSUFFICIENT_SAMPLE",
        99: "INSUFFICIENT_SAMPLE",
        100: "WARMING_UP",
        299: "WARMING_UP",
        300: "PRELIMINARY_MEASURED",
        499: "PRELIMINARY_MEASURED",
        500: "MEASURED",
    }
    assert {value: sample_gate(value) for value in expected} == expected


def test_temporal_split_is_chronological_and_unavailable_below_gate() -> None:
    low = chronological_split([make_validation_row(index) for index in range(99)])
    ready = chronological_split(
        [make_validation_row(index) for index in reversed(range(100))]
    )

    assert low.status == "NOT_AVAILABLE_INSUFFICIENT_EFFECTIVE_SAMPLE"
    assert low.development == low.validation == ()
    assert ready.status == "AVAILABLE_DEVELOPMENT_VALIDATION_ONLY"
    assert len(ready.development) == 70
    assert len(ready.validation) == 30
    assert ready.development[0]["prediction_id"] == "prediction-00000"
    assert ready.validation[0]["prediction_id"] == "prediction-00070"


def test_frozen_edges_use_development_values_only() -> None:
    development_values = list(range(70))
    first = fit_frozen_quantile_edges(development_values)
    second = fit_frozen_quantile_edges(list(development_values))

    assert first == second
    assert first is not None
    assert apply_frozen_edges(999, first).startswith("Q")
    assert fit_frozen_quantile_edges(list(range(29))) is None


def test_baseline_reuses_multiclass_metrics_and_rejects_bad_probability_sum() -> None:
    rows = [make_validation_row(index) for index in range(10)]
    rows[0]["p_timeout_frac"] = 0.9

    report = baseline_diagnostics(rows)

    assert report["valid_count"] == 9
    assert report["invalid_probability_count"] == 1
    assert report["brier_score"] is not None
    assert report["log_loss"] is not None
    assert report["confusion_matrix"] is None
    assert report["reliability_buckets"] == []
    assert "LOW_EFFECTIVE_SAMPLE_DESCRIPTIVE_ONLY" in report["warnings"]
