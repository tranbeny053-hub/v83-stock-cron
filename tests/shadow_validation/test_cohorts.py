from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime, timedelta

from crypto_probability_engine.shadow_validation.cohorts import (
    effective_n_thin,
    partition_cohorts,
    same_candle_deduplicate,
    sanitize_validation_row,
)
from tests.shadow_validation.conftest import make_validation_row


def test_same_candle_dedup_keeps_earliest_prediction_then_identifier() -> None:
    close = datetime(2026, 1, 1, tzinfo=UTC)
    later = make_validation_row(
        2,
        predicted_at=close + timedelta(minutes=2),
        reference_close=close,
    )
    first_b = make_validation_row(3, predicted_at=close, reference_close=close)
    first_a = deepcopy(first_b)
    first_a["prediction_id"] = "prediction-00001"
    first_b["prediction_id"] = "prediction-00002"

    rows = [sanitize_validation_row(item) for item in (later, first_b, first_a)]
    deduplicated = same_candle_deduplicate(rows)

    assert len(deduplicated) == 1
    assert deduplicated[0]["prediction_id"] == "prediction-00001"


def test_effective_n_greedily_removes_overlapping_horizons() -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    rows = [
        make_validation_row(1, predicted_at=start, horizon_hours=24),
        make_validation_row(2, predicted_at=start + timedelta(hours=12), horizon_hours=24),
        make_validation_row(3, predicted_at=start + timedelta(hours=24), horizon_hours=24),
        make_validation_row(4, predicted_at=start + timedelta(hours=47), horizon_hours=24),
        make_validation_row(5, predicted_at=start + timedelta(hours=48), horizon_hours=24),
    ]
    sanitized = [sanitize_validation_row(row) for row in rows]

    effective = effective_n_thin(sanitized)

    assert [row["prediction_id"] for row in effective] == [
        "prediction-00001",
        "prediction-00003",
        "prediction-00005",
    ]


def test_mixed_versions_partition_without_invalidating_valid_cohorts() -> None:
    rows = [
        sanitize_validation_row(make_validation_row(1, model_version="model-a")),
        sanitize_validation_row(make_validation_row(2, model_version="model-b")),
    ]
    partitions = partition_cohorts(rows)

    assert len(partitions) == 2
    assert {keys["model_version"] for keys, _ in partitions} == {"model-a", "model-b"}


def test_malformed_cohort_is_isolated() -> None:
    valid = sanitize_validation_row(make_validation_row(1))
    malformed_source = make_validation_row(2)
    malformed_source["model_version"] = None
    malformed = sanitize_validation_row(malformed_source)

    partitions = partition_cohorts([valid, malformed])

    assert len(partitions) == 2
    assert sum(all(row["cohort_valid"] for row in rows) for _, rows in partitions) == 1
    assert malformed["cohort_valid"] is False


def test_payload_projection_excludes_unknown_and_explanation_fields() -> None:
    source = make_validation_row(1)
    source["snapshot_payload"]["features"][0]["raw_value"] = {
        "private_nested_marker": "must be removed"
    }
    sanitized = sanitize_validation_row(source)
    serialized = repr(sanitized)

    assert "snapshot_payload" not in sanitized
    assert "plain_english" not in serialized
    assert "explanation_short" not in serialized
    assert "unknown_future" not in serialized
    assert "private_nested_marker" not in serialized
