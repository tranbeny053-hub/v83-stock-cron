"""Deterministic framework-only Quant V2 shadow validation report service."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from crypto_probability_engine.persistence.prediction_origin import (
    DEFAULT_PREDICTION_ORIGIN,
    validate_prediction_origin,
)
from crypto_probability_engine.persistence.repository import PersistenceRepository
from crypto_probability_engine.shadow_validation.binning import (
    apply_frozen_edges,
    categorical_state,
    chronological_split,
    fit_frozen_quantile_edges,
)
from crypto_probability_engine.shadow_validation.cohorts import (
    effective_n_thin,
    partition_cohorts,
    same_candle_deduplicate,
    sanitize_validation_rows,
)
from crypto_probability_engine.shadow_validation.metrics import (
    baseline_diagnostics,
    count_distribution,
    data_quality_distribution,
    feature_conditioned_diagnostics,
    ordered_monotonicity,
)
from crypto_probability_engine.shadow_validation.schemas import (
    COHORT_KEYS,
    FRAMEWORK_MODE,
    HOLDOUT_STATUS,
    MAX_VALIDATION_ROWS,
    MIN_CELL_COUNT,
    REPORT_SCHEMA_VERSION,
    TEMPORAL_SPLIT_MINIMUM,
    multiple_testing_policy,
    sample_gate,
    uncertainty_policy,
)


def build_shadow_validation_report(
    repository: PersistenceRepository,
    *,
    feature_methodology_version: str = "quant-v2-shadow-v0",
    timeframe: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = MAX_VALIDATION_ROWS,
    generated_at_utc: str,
    prediction_origin: str = DEFAULT_PREDICTION_ORIGIN,
) -> dict[str, Any]:
    prediction_origin = validate_prediction_origin(prediction_origin)
    bounded_limit = _bounded_limit(limit)
    generated_at = _required_utc_text(generated_at_utc)
    coverage = repository.fetch_feature_snapshot_validation_coverage(
        feature_methodology_version=feature_methodology_version,
        timeframe=timeframe,
        since=since,
        until=until,
        prediction_origin=prediction_origin,
    )
    raw_rows = repository.fetch_feature_snapshot_validation_rows(
        feature_methodology_version=feature_methodology_version,
        timeframe=timeframe,
        since=since,
        until=until,
        limit=bounded_limit,
        prediction_origin=prediction_origin,
    )
    rows = sanitize_validation_rows(raw_rows)
    cohort_summaries = []
    baseline_reports = []
    feature_reports = []
    cohort_partitions = partition_cohorts(rows)
    for index, (cohort_keys, cohort_rows) in enumerate(cohort_partitions, start=1):
        cohort_id = f"cohort-{index:04d}"
        valid_cohort = all(row.get("cohort_valid") for row in cohort_rows)
        deduplicated = same_candle_deduplicate(cohort_rows) if valid_cohort else []
        effective = effective_n_thin(deduplicated) if valid_cohort else []
        cohort_summaries.append(
            _cohort_summary(
                cohort_id,
                cohort_keys,
                cohort_rows,
                deduplicated,
                effective,
                valid_cohort,
            )
        )
        if not valid_cohort:
            continue
        baseline_rows = [
            row for row in effective if row.get("no_lookahead_assertion") is True
        ]
        baseline_reports.append(
            _baseline_report(cohort_id, cohort_keys, cohort_rows, deduplicated, baseline_rows)
        )
        feature_reports.extend(
            _feature_reports_for_cohort(cohort_id, cohort_keys, cohort_rows)
        )
    warnings = []
    if len(raw_rows) >= bounded_limit:
        warnings.append("ROW_LIMIT_REACHED_RESULTS_MAY_BE_TRUNCATED")
    if not rows:
        warnings.append("NO_RESOLVED_SNAPSHOT_OUTCOME_ROWS")
    if any(not row.get("cohort_valid") for row in rows):
        warnings.append("INVALID_COHORT_ROWS_ISOLATED")
    overall_status = _overall_status(cohort_summaries, coverage)
    report = {
        "report_schema_version": REPORT_SCHEMA_VERSION,
        "generated_at_utc": generated_at,
        "repository": _repository_name(repository),
        "read_only": True,
        "framework_mode": FRAMEWORK_MODE,
        "feature_methodology_version": feature_methodology_version,
        "model_methodology_versions": sorted(
            {
                f"{row['model_version']}|{row['methodology_version']}"
                for row in rows
                if row.get("model_version") and row.get("methodology_version")
            }
        ),
        "quant_v2_schema_versions": sorted(
            {
                str(row["quant_v2_schema_version"])
                for row in rows
                if row.get("quant_v2_schema_version")
            }
        ),
        "timeframes": sorted(
            {str(row["timeframe"]) for row in rows if row.get("timeframe")}
        ),
        "data_window": {
            "since": _optional_iso(since),
            "until": _optional_iso(until),
            "eligible_era_basis": (
                "requested_since" if since is not None else "first_observed_snapshot"
            ),
            "first_snapshot_as_of_utc": _optional_iso(
                coverage.get("first_snapshot_as_of_utc")
            ),
            "latest_snapshot_as_of_utc": _optional_iso(
                coverage.get("latest_snapshot_as_of_utc")
            ),
            "row_limit": bounded_limit,
            "limit_reached": len(raw_rows) >= bounded_limit,
        },
        "sample_gate_policy": _sample_gate_policy(),
        "overall_status": overall_status,
        "warnings": warnings,
        "coverage_summary": _coverage_summary(coverage, since),
        "cohort_summary": cohort_summaries,
        "baseline_metrics": baseline_reports,
        "feature_reports": feature_reports,
        "temporal_validation_policy": {
            "method": "CHRONOLOGICAL_DEVELOPMENT_VALIDATION",
            "minimum_effective_n": TEMPORAL_SPLIT_MINIMUM,
            "development_fraction": 0.70,
            "holdout_status": HOLDOUT_STATUS,
            "holdout_metrics": None,
        },
        "uncertainty_policy": uncertainty_policy(
            "Framework-only phase; live intervals are not calculated."
        ),
        "multiple_testing_summary": multiple_testing_policy(
            "Framework-only phase; multiplicity adjustment is not applied."
        ),
        "promotion_eligibility": {
            "promotion_eligible": False,
            "any_eligible": False,
            "reason": "Framework-only shadow evidence is not eligible for review.",
        },
        "safety_notes": [
            "Top-label hit is a diagnostic frequency, not accuracy.",
            "Terminal return is descriptive and not an expected-value measure.",
            "Brier score and log loss are diagnostic, not profitability evidence.",
            "Lower Brier score alone does not establish calibration.",
            "SHADOW_ONLY — not used in decisions.",
        ],
    }
    return report


def _cohort_summary(
    cohort_id: str,
    cohort_keys: dict,
    raw_rows: list[dict],
    deduplicated: list[dict],
    effective: list[dict],
    valid: bool,
) -> dict[str, Any]:
    invalid_reasons = sorted(
        {
            reason
            for row in raw_rows
            for reason in row.get("invalid_reasons", [])
        }
    )
    if not valid:
        evidence_status = "INVALID_COHORT"
    elif cohort_keys.get("no_lookahead_assertion") is not True:
        evidence_status = "NEGATIVE_EVIDENCE"
    else:
        evidence_status = _gate_evidence(len(effective))
    return {
        "cohort_id": cohort_id,
        "cohort_keys": _cohort_key_payload(cohort_keys),
        "valid": valid,
        "invalid_reasons": invalid_reasons,
        "raw_n": len(raw_rows),
        "deduplicated_n": len(deduplicated),
        "effective_n": len(effective),
        "sample_gate": sample_gate(len(effective)),
        "evidence_status": evidence_status,
        "block_status_distribution": count_distribution(
            row.get("block_status") for row in raw_rows
        ),
        "provider_distribution": count_distribution(
            row.get("provider_signature") for row in raw_rows
        ),
    }


def _baseline_report(
    cohort_id: str,
    cohort_keys: dict,
    raw_rows: list[dict],
    deduplicated: list[dict],
    effective_rows: list[dict],
) -> dict[str, Any]:
    metrics = baseline_diagnostics(effective_rows)
    return {
        "cohort_id": cohort_id,
        "timeframe": str(cohort_keys.get("timeframe") or "UNKNOWN"),
        "raw_n": len(raw_rows),
        "deduplicated_n": len(deduplicated),
        "effective_n": len(effective_rows),
        "sample_gate": sample_gate(len(effective_rows)),
        "valid_probability_count": metrics["valid_count"],
        "invalid_probability_count": metrics["invalid_probability_count"],
        "brier_score": metrics["brier_score"],
        "log_loss": metrics["log_loss"],
        "top_label_hit_diagnostic": metrics["top_label_hit_diagnostic"],
        "outcome_distribution": metrics["outcome_distribution"],
        "confusion_matrix": metrics["confusion_matrix"],
        "reliability_buckets": metrics["reliability_buckets"],
        "warnings": metrics["warnings"],
    }


def _feature_reports_for_cohort(
    cohort_id: str,
    cohort_keys: dict,
    cohort_rows: list[dict],
) -> list[dict[str, Any]]:
    specifications = sorted(
        {
            (
                str(feature.get("feature_id")),
                str(feature.get("family")),
                str(row.get("provider_signature") or "UNKNOWN"),
                (
                    str(row.get("normalized_symbol"))
                    if feature.get("family") == "VOLUME"
                    else "ALL_SYMBOLS"
                ),
            )
            for row in cohort_rows
            for feature in row.get("features", [])
            if feature.get("feature_valid")
        }
    )
    reports = []
    for feature_id, family, provider_signature, scope_symbol in specifications:
        scoped_rows = [
            row
            for row in cohort_rows
            if str(row.get("provider_signature") or "UNKNOWN") == provider_signature
            and (
                family != "VOLUME"
                or str(row.get("normalized_symbol")) == scope_symbol
            )
        ]
        reports.append(
            _one_feature_report(
                cohort_id,
                cohort_keys,
                scoped_rows,
                feature_id,
                family,
                provider_signature,
                scope_symbol,
            )
        )
    return reports


def _one_feature_report(
    cohort_id: str,
    cohort_keys: dict,
    scoped_rows: list[dict],
    feature_id: str,
    family: str,
    provider_signature: str,
    scope_symbol: str,
) -> dict[str, Any]:
    attached = []
    status_values = []
    disabled_rows = 0
    no_lookahead_excluded = 0
    for row in scoped_rows:
        feature = next(
            (
                item
                for item in row.get("features", [])
                if str(item.get("feature_id")) == feature_id
            ),
            None,
        )
        status_values.append(feature.get("status") if feature else "MISSING")
        if row.get("block_status") == "DISABLED":
            disabled_rows += 1
        if row.get("no_lookahead_assertion") is not True:
            no_lookahead_excluded += 1
        if feature is None:
            continue
        enriched = dict(row)
        enriched["feature"] = feature
        attached.append(enriched)
    valid_rows = [
        row
        for row in attached
        if row.get("block_status") != "DISABLED"
        and row.get("no_lookahead_assertion") is True
        and row["feature"].get("status") == "VALID"
        and row["feature"].get("no_lookahead_assertion") is True
        and row["feature"].get("feature_valid") is True
    ]
    deduplicated = same_candle_deduplicate(valid_rows)
    effective = effective_n_thin(deduplicated)
    gate = sample_gate(len(effective))
    split = chronological_split(effective)
    frozen_edges = None
    if family in {"VOLATILITY", "VOLUME"} and split.development:
        frozen_edges = fit_frozen_quantile_edges(
            [row["feature"].get("raw_value") for row in split.development]
        )
    represented = []
    for row in effective:
        represented_row = dict(row)
        if family in {"VOLATILITY", "VOLUME"}:
            represented_row["feature_state"] = apply_frozen_edges(
                row["feature"].get("raw_value"), frozen_edges
            )
        else:
            represented_row["feature_state"] = categorical_state(family, row["feature"])
        represented.append(represented_row)
    if len(effective) >= TEMPORAL_SPLIT_MINIMUM:
        diagnostics, sparse_cell, sparse_class = feature_conditioned_diagnostics(represented)
    else:
        diagnostics, sparse_cell, sparse_class = [], False, False
    evidence_status = _feature_evidence_status(
        effective_n=len(effective),
        valid_feature_count=len(valid_rows),
        sparse_cell=sparse_cell,
        sparse_class=sparse_class,
        split_status=split.status,
    )
    limitations = [
        "Framework-only descriptive evidence; no confirmatory inference is applied.",
        "Overlapping horizons are removed before sample gates are assigned.",
    ]
    if family == "REGIME":
        limitations.append(
            "REGIME and VOLATILITY share upstream origin and are not independent evidence."
        )
    if family == "VOLUME":
        limitations.append(
            "VOLUME representation is isolated by provider, symbol, and timeframe."
        )
    if family == "VOLATILITY":
        limitations.append("VOLATILITY is context-only and has no directional interpretation.")
    missing_count = len(scoped_rows) - len(attached)
    degraded_count = sum(
        row["feature"].get("status") != "VALID" for row in attached
    )
    temporal_stability = {
        "status": (
            "DEVELOPMENT_FIT_REPRESENTATION_FROZEN"
            if split.development
            else "NOT_EVALUATED_INSUFFICIENT_EFFECTIVE_SAMPLE"
        ),
        "development_n": len(split.development),
        "validation_n": len(split.validation),
        "frozen_edges": list(frozen_edges) if frozen_edges is not None else None,
        "ordered_bin_monotonicity": ordered_monotonicity(diagnostics),
    }
    return {
        "feature_id": feature_id,
        "family": family,
        "timeframe": str(cohort_keys.get("timeframe") or "UNKNOWN"),
        "cohort_keys": {
            **_cohort_key_payload(cohort_keys),
            "provider_signature": provider_signature,
            "scope_symbol": scope_symbol,
        },
        "total_snapshot_count": len(scoped_rows),
        "resolved_count": len(scoped_rows),
        "valid_feature_count": len(valid_rows),
        "raw_n": len(valid_rows),
        "deduplicated_n": len(deduplicated),
        "effective_n": len(effective),
        "sample_gate": gate,
        "coverage_fraction": len(attached) / len(scoped_rows) if scoped_rows else 0.0,
        "missingness": {
            "missing_or_malformed": missing_count,
            "degraded_or_invalid": degraded_count,
            "disabled_rows": disabled_rows,
            "no_lookahead_excluded": no_lookahead_excluded,
            "missing_fraction": (
                missing_count / len(scoped_rows) if scoped_rows else 0.0
            ),
            "degraded_fraction": (
                degraded_count / len(scoped_rows) if scoped_rows else 0.0
            ),
        },
        "status_distribution": count_distribution(status_values),
        "provider_distribution": count_distribution(
            row.get("provider_signature") for row in scoped_rows
        ),
        "symbol_distribution": count_distribution(
            row.get("normalized_symbol") for row in scoped_rows
        ),
        "value_or_bucket_distribution": count_distribution(
            row.get("feature_state") for row in represented
        ),
        "realized_outcome_distribution": count_distribution(
            row.get("realized_label") for row in effective
        ),
        "feature_conditioned_diagnostics": diagnostics,
        "data_quality_distribution": data_quality_distribution(attached),
        "temporal_split_status": split.status,
        "temporal_stability": temporal_stability,
        "uncertainty": uncertainty_policy(
            "Framework-only phase; feature intervals are not calculated."
        ),
        "adjusted_evidence": {
            "status": evidence_status,
            "multiplicity_adjustment_applied": False,
        },
        "limitations": limitations,
        "evidence_status": evidence_status,
        "promotion_eligible": False,
        "reason": _feature_reason(evidence_status),
    }


def _feature_evidence_status(
    *,
    effective_n: int,
    valid_feature_count: int,
    sparse_cell: bool,
    sparse_class: bool,
    split_status: str,
) -> str:
    if valid_feature_count <= 0:
        return "NEGATIVE_EVIDENCE"
    if effective_n < 100:
        return "INSUFFICIENT_SAMPLE"
    if split_status != "AVAILABLE_DEVELOPMENT_VALIDATION_ONLY":
        return "TEMPORAL_SPLIT_NOT_AVAILABLE"
    if sparse_class:
        return "SPARSE_CLASS"
    if sparse_cell:
        return "SPARSE_CELL"
    return "EXPLORATORY_SIGNAL_ONLY"


def _feature_reason(status: str) -> str:
    reasons = {
        "NEGATIVE_EVIDENCE": "No valid feature observations remain after safety filters.",
        "INSUFFICIENT_SAMPLE": "Effective sample is below the warming-up gate.",
        "TEMPORAL_SPLIT_NOT_AVAILABLE": "Chronological development/validation is unavailable.",
        "SPARSE_CLASS": "At least one realized outcome class is below the minimum cell.",
        "SPARSE_CELL": "At least one feature state is below the minimum cell.",
        "EXPLORATORY_SIGNAL_ONLY": "Descriptive shadow evidence only; confirmation is deferred.",
    }
    return reasons[status]


def _gate_evidence(effective_n: int) -> str:
    if effective_n <= 0:
        return "NO_DATA"
    if effective_n < 100:
        return "INSUFFICIENT_SAMPLE"
    return "EXPLORATORY_SIGNAL_ONLY"


def _overall_status(
    cohorts: list[dict[str, Any]], coverage: dict[str, Any]
) -> str:
    statuses = {cohort["evidence_status"] for cohort in cohorts}
    if not statuses:
        eligible_activity = int(coverage.get("live_predictions_eligible_era") or 0) + int(
            coverage.get("snapshots_eligible_era") or 0
        )
        if eligible_activity > 0:
            return "COVERAGE_FAILURE"
        return "NO_DATA"
    if statuses == {"INVALID_COHORT"}:
        return "INVALID_COHORT"
    if "EXPLORATORY_SIGNAL_ONLY" in statuses:
        return "EXPLORATORY_SIGNAL_ONLY"
    if statuses <= {"NEGATIVE_EVIDENCE", "INVALID_COHORT"}:
        return "NEGATIVE_EVIDENCE"
    return "INSUFFICIENT_SAMPLE"


def _coverage_summary(coverage: dict[str, Any], since: datetime | None) -> dict:
    return {
        "all_time": {
            "live_predictions": int(coverage.get("live_predictions_all_time") or 0),
            "snapshots": int(coverage.get("snapshots_all_time") or 0),
        },
        "eligible_era": {
            "basis": "requested_since" if since is not None else "first_observed_snapshot",
            "live_predictions": int(
                coverage.get("live_predictions_eligible_era") or 0
            ),
            "snapshots": int(coverage.get("snapshots_eligible_era") or 0),
            "resolved_outcomes": int(
                coverage.get("resolved_outcomes_eligible_era") or 0
            ),
            "snapshot_outcome_joins": int(
                coverage.get("snapshot_outcome_joins_eligible_era") or 0
            ),
            "predictions_missing_snapshot": int(
                coverage.get("predictions_missing_snapshot_eligible_era") or 0
            ),
            "snapshots_missing_outcome": int(
                coverage.get("snapshots_missing_outcome_eligible_era") or 0
            ),
        },
    }


def _sample_gate_policy() -> dict:
    return {
        "thresholds": [
            {"gate": "NO_SAMPLES", "minimum": 0, "maximum": 0},
            {"gate": "INSUFFICIENT_SAMPLE", "minimum": 1, "maximum": 99},
            {"gate": "WARMING_UP", "minimum": 100, "maximum": 299},
            {"gate": "PRELIMINARY_MEASURED", "minimum": 300, "maximum": 499},
            {"gate": "MEASURED", "minimum": 500, "maximum": None},
        ],
        "minimum_feature_bucket_cell": MIN_CELL_COUNT,
        "minimum_outcome_class_cell": MIN_CELL_COUNT,
        "sample_basis": "DETERMINISTIC_NON_OVERLAPPING_EFFECTIVE_N",
    }


def _cohort_key_payload(cohort_keys: dict) -> dict:
    return {field: cohort_keys.get(field) for field in COHORT_KEYS}


def _repository_name(repository: PersistenceRepository) -> str:
    value = getattr(repository, "repository_type", None)
    return str(value()) if callable(value) else type(repository).__name__


def _bounded_limit(limit: int) -> int:
    if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
        raise ValueError("Validation limit must be a positive integer.")
    return min(limit, MAX_VALIDATION_ROWS)


def _required_utc_text(value: str) -> str:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Generated time must include a timezone.")
    return parsed.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _optional_iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC).isoformat().replace("+00:00", "Z")
