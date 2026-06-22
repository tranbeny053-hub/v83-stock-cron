from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

from crypto_probability_engine.shadow_validation.service import (
    build_shadow_validation_report,
)
from tests.shadow_validation.conftest import (
    ReadOnlyRepository,
    make_coverage,
    make_feature,
    make_validation_row,
)

GENERATED_AT = "2026-06-21T00:00:00Z"
ROOT = Path(__file__).resolve().parents[2]


def _report(rows: list[dict]) -> dict:
    return build_shadow_validation_report(
        ReadOnlyRepository(rows),
        generated_at_utc=GENERATED_AT,
    )


def test_report_uses_only_two_read_methods_and_is_deterministic() -> None:
    rows = [make_validation_row(index) for index in range(12)]
    repository = ReadOnlyRepository(rows)

    first = build_shadow_validation_report(
        repository,
        generated_at_utc=GENERATED_AT,
    )
    second = build_shadow_validation_report(
        ReadOnlyRepository(deepcopy(rows)),
        generated_at_utc=GENERATED_AT,
    )

    assert json.dumps(first, sort_keys=True, separators=(",", ":")) == json.dumps(
        second, sort_keys=True, separators=(",", ":")
    )
    assert [call[0] for call in repository.calls] == ["coverage", "rows"]
    assert first["read_only"] is True
    assert first["framework_mode"] == "FRAMEWORK_ONLY"


def test_report_passes_requested_prediction_origin_to_both_reads() -> None:
    repository = ReadOnlyRepository([])

    build_shadow_validation_report(
        repository,
        generated_at_utc=GENERATED_AT,
        prediction_origin="CONTROLLED_SMOKE",
    )

    assert [call[1]["prediction_origin"] for call in repository.calls] == [
        "CONTROLLED_SMOKE",
        "CONTROLLED_SMOKE",
    ]


def test_framework_and_cli_source_contain_no_write_path() -> None:
    sources = [
        path.read_text()
        for path in (ROOT / "src" / "crypto_probability_engine" / "shadow_validation").glob(
            "*.py"
        )
    ]
    sources.append((ROOT / "scripts" / "quant_v2_validation_report.py").read_text())
    forbidden = (
        "INSERT" + " INTO",
        "UPDATE" + " ",
        "DELETE" + " FROM",
        "ON " + "CONFLICT",
        "save_" + "prediction",
        "mark_" + "unavailable",
    )
    assert not any(term in source for source in sources for term in forbidden)


def test_low_sample_report_is_honest_and_statistically_dormant() -> None:
    report = _report([make_validation_row(index) for index in range(10)])

    assert report["overall_status"] == "INSUFFICIENT_SAMPLE"
    assert all(item["sample_gate"] == "INSUFFICIENT_SAMPLE" for item in report["feature_reports"])
    assert all(not item["feature_conditioned_diagnostics"] for item in report["feature_reports"])
    assert report["uncertainty_policy"]["applied"] is False
    assert report["uncertainty_policy"]["interval"] is None
    assert report["multiple_testing_summary"]["applied"] is False
    assert report["multiple_testing_summary"]["selected_method"] is None


def test_missing_join_rows_with_eligible_activity_is_coverage_failure() -> None:
    coverage = make_coverage(1)
    coverage["snapshot_outcome_joins_eligible_era"] = 0
    repository = ReadOnlyRepository([], coverage=coverage)

    report = build_shadow_validation_report(
        repository,
        generated_at_utc=GENERATED_AT,
    )

    assert report["overall_status"] == "COVERAGE_FAILURE"


def test_cohort_versions_separate_and_invalid_row_affects_only_its_cohort() -> None:
    valid_a = make_validation_row(1, model_version="model-a")
    valid_b = make_validation_row(2, model_version="model-b")
    malformed = make_validation_row(3, model_version="model-c")
    malformed["resolver_version"] = None

    report = _report([valid_a, valid_b, malformed])

    assert len(report["cohort_summary"]) == 3
    statuses = [item["evidence_status"] for item in report["cohort_summary"]]
    assert statuses.count("INVALID_COHORT") == 1
    assert statuses.count("INSUFFICIENT_SAMPLE") == 2


def test_false_no_lookahead_and_disabled_rows_are_not_feature_evidence() -> None:
    false_row = make_validation_row(1, no_lookahead=False)
    for feature in false_row["snapshot_payload"]["features"]:
        feature["no_lookahead_assertion"] = False
    disabled = make_validation_row(2, block_status="DISABLED", features=[])
    report = _report([false_row, disabled])

    block_counts = {
        entry["key"]: entry["count"]
        for cohort in report["cohort_summary"]
        for entry in cohort["block_status_distribution"]
    }
    assert block_counts["DISABLED"] == 1
    assert all(item["effective_n"] == 0 for item in report["feature_reports"])
    assert all(item["promotion_eligible"] is False for item in report["feature_reports"])
    false_cohort = next(
        item
        for item in report["cohort_summary"]
        if item["cohort_keys"]["no_lookahead_assertion"] is False
    )
    assert false_cohort["evidence_status"] == "NEGATIVE_EVIDENCE"


def test_all_feature_families_and_required_limitations_are_preserved() -> None:
    report = _report([make_validation_row(index) for index in range(5)])
    by_family = {item["family"]: item for item in report["feature_reports"]}

    assert set(by_family) == {"VOLATILITY", "TREND", "VOLUME", "REGIME"}
    assert any("not independent evidence" in text for text in by_family["REGIME"]["limitations"])
    assert any(
        "provider, symbol, and timeframe" in text
        for text in by_family["VOLUME"]["limitations"]
    )
    assert any(
        "no directional interpretation" in text
        for text in by_family["VOLATILITY"]["limitations"]
    )


def test_volume_reports_are_separate_by_provider_and_symbol() -> None:
    first = make_validation_row(1, symbol="BTC/USDT", provider_signature="BINANCE")
    second = make_validation_row(2, symbol="ETH/USDT", provider_signature="BINANCE")
    third = make_validation_row(3, symbol="BTC/USDT", provider_signature="OKX")

    report = _report([first, second, third])
    volume = [item for item in report["feature_reports"] if item["family"] == "VOLUME"]

    assert len(volume) == 3
    assert {
        (item["cohort_keys"]["provider_signature"], item["cohort_keys"]["scope_symbol"])
        for item in volume
    } == {
        ("BINANCE", "BTC/USDT"),
        ("BINANCE", "ETH/USDT"),
        ("OKX", "BTC/USDT"),
    }


def test_warming_sample_freezes_development_bins_and_seals_holdout() -> None:
    rows = [make_validation_row(index) for index in range(100)]
    report = _report(rows)
    volatility = next(item for item in report["feature_reports"] if item["family"] == "VOLATILITY")

    assert volatility["temporal_split_status"] == "AVAILABLE_DEVELOPMENT_VALIDATION_ONLY"
    assert volatility["temporal_stability"]["development_n"] == 70
    assert volatility["temporal_stability"]["validation_n"] == 30
    assert volatility["temporal_stability"]["frozen_edges"] is not None
    assert all(
        item["evidence_status"] == "EXPLORATORY_SIGNAL_ONLY"
        for item in report["feature_reports"]
    )
    assert report["temporal_validation_policy"]["holdout_status"] == "SEALED_NOT_EVALUATED"
    assert report["temporal_validation_policy"]["holdout_metrics"] is None


def test_sparse_cells_and_classes_prevent_stronger_framework_status() -> None:
    rows = [make_validation_row(index, realized_label="UP") for index in range(100)]
    report = _report(rows)

    assert any(item["evidence_status"] == "SPARSE_CLASS" for item in report["feature_reports"])
    allowed = {
        "NO_DATA",
        "INSUFFICIENT_SAMPLE",
        "NEGATIVE_EVIDENCE",
        "SPARSE_CELL",
        "SPARSE_CLASS",
        "EXPLORATORY_SIGNAL_ONLY",
    }
    assert {item["evidence_status"] for item in report["feature_reports"]} <= allowed


def test_sparse_feature_state_is_reported_without_inference() -> None:
    rows = []
    for index in range(100):
        direction = "DOWN" if index < 10 else "UP"
        features = [
            make_feature("VOLATILITY", raw_value=0.01 + index * 0.0001),
            make_feature("TREND", raw_value=direction, direction_hint=direction),
            make_feature("VOLUME", raw_value=1.0 + index * 0.01),
            make_feature("REGIME", raw_value="LOW_VOL"),
        ]
        rows.append(make_validation_row(index, features=features))
    report = _report(rows)
    trend = next(item for item in report["feature_reports"] if item["family"] == "TREND")

    assert trend["evidence_status"] == "SPARSE_CELL"
    assert trend["uncertainty"]["applied"] is False


def test_degraded_and_missing_features_are_retained_as_negative_evidence() -> None:
    features = [
        make_feature("VOLATILITY", status="DEGRADED", raw_value=None),
        make_feature("TREND", status="COMPUTE_ERROR", raw_value=None),
        make_feature("VOLUME", status="PROVIDER_UNAVAILABLE", raw_value=None),
        make_feature("REGIME", status="INSUFFICIENT_HISTORY", raw_value=None),
    ]
    report = _report([make_validation_row(1, block_status="DEGRADED", features=features)])

    assert all(item["valid_feature_count"] == 0 for item in report["feature_reports"])
    assert all(item["evidence_status"] == "NEGATIVE_EVIDENCE" for item in report["feature_reports"])
    assert all(
        item["missingness"]["degraded_or_invalid"] == 1
        for item in report["feature_reports"]
    )


def test_report_never_exposes_source_payload_or_unknown_text() -> None:
    report = _report([make_validation_row(1)])
    serialized = json.dumps(report, sort_keys=True)

    assert "snapshot_payload" not in serialized
    assert "must be removed" not in serialized
    assert report["promotion_eligibility"] == {
        "promotion_eligible": False,
        "any_eligible": False,
        "reason": "Framework-only shadow evidence is not eligible for review.",
    }
    assert all(item["promotion_eligible"] is False for item in report["feature_reports"])


def test_report_contains_no_live_inferential_result_fields() -> None:
    report = _report([make_validation_row(index) for index in range(100)])
    serialized = json.dumps(report, sort_keys=True).lower()

    assert "p_value" not in serialized
    assert "pvalue" not in serialized
    assert "confidence_interval" not in serialized
    assert all(item["uncertainty"]["interval"] is None for item in report["feature_reports"])
