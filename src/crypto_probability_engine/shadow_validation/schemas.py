"""Stable constants for the framework-only shadow validation report."""

from __future__ import annotations

from typing import Literal

REPORT_SCHEMA_VERSION = "quant-v2-validation.v0"
FRAMEWORK_MODE = "FRAMEWORK_ONLY"
HOLDOUT_STATUS = "SEALED_NOT_EVALUATED"
MAX_VALIDATION_ROWS = 50_000
MIN_CELL_COUNT = 30
TEMPORAL_SPLIT_MINIMUM = 100

SampleGate = Literal[
    "NO_SAMPLES",
    "INSUFFICIENT_SAMPLE",
    "WARMING_UP",
    "PRELIMINARY_MEASURED",
    "MEASURED",
]

EVIDENCE_STATUSES = (
    "NO_DATA",
    "INSUFFICIENT_SAMPLE",
    "COVERAGE_FAILURE",
    "INVALID_COHORT",
    "TEMPORAL_SPLIT_NOT_AVAILABLE",
    "SPARSE_CELL",
    "SPARSE_CLASS",
    "UNSTABLE_OVER_TIME",
    "PROVIDER_DEPENDENT",
    "SYMBOL_DEPENDENT",
    "NO_DETECTABLE_ASSOCIATION",
    "NEGATIVE_EVIDENCE",
    "EXPLORATORY_SIGNAL_ONLY",
    "PROMISING_SHADOW_EVIDENCE",
    "NOT_ELIGIBLE_FOR_PROMOTION_REVIEW",
)

FRAMEWORK_EMITTABLE_STATUSES = {
    "NO_DATA",
    "INSUFFICIENT_SAMPLE",
    "COVERAGE_FAILURE",
    "INVALID_COHORT",
    "TEMPORAL_SPLIT_NOT_AVAILABLE",
    "SPARSE_CELL",
    "SPARSE_CLASS",
    "UNSTABLE_OVER_TIME",
    "PROVIDER_DEPENDENT",
    "SYMBOL_DEPENDENT",
    "NO_DETECTABLE_ASSOCIATION",
    "NEGATIVE_EVIDENCE",
    "EXPLORATORY_SIGNAL_ONLY",
    "NOT_ELIGIBLE_FOR_PROMOTION_REVIEW",
}

COHORT_KEYS = (
    "timeframe",
    "feature_methodology_version",
    "quant_v2_schema_version",
    "methodology_version",
    "model_version",
    "resolver_version",
    "prediction_is_live_data",
    "outcome_is_live_data",
    "no_lookahead_assertion",
)

FEATURE_FIELDS = (
    "feature_id",
    "family",
    "status",
    "raw_value",
    "direction_hint",
    "lookback",
    "candle_count",
    "source_provider",
    "no_lookahead_assertion",
    "data_quality",
)

FEATURE_DATA_QUALITY_FIELDS = (
    "upstream_status",
    "provider_state_status",
    "snapshot_source_status",
    "timestamp_evidence_complete",
)

FEATURE_FAMILIES = ("VOLATILITY", "TREND", "VOLUME", "REGIME")


def sample_gate(effective_n: int) -> SampleGate:
    if effective_n <= 0:
        return "NO_SAMPLES"
    if effective_n < 100:
        return "INSUFFICIENT_SAMPLE"
    if effective_n < 300:
        return "WARMING_UP"
    if effective_n < 500:
        return "PRELIMINARY_MEASURED"
    return "MEASURED"


def uncertainty_policy(reason: str) -> dict:
    return {
        "planned_method": "DEPENDENCE_AWARE_BLOCK_BOOTSTRAP",
        "applied": False,
        "interval": None,
        "reason": reason,
    }


def multiple_testing_policy(reason: str) -> dict:
    return {
        "planned_methods": ["BH", "BY"],
        "selected_method": None,
        "applied": False,
        "reason": reason,
    }
