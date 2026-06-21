"""Descriptive metrics for compatible shadow-validation cohorts."""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from typing import Any

from crypto_probability_engine.calibration.metrics import (
    compute_calibration_metrics,
    top_prediction_label,
)
from crypto_probability_engine.shadow_validation.schemas import MIN_CELL_COUNT

_LABELS = ("UP", "DOWN", "TIMEOUT")
_EPSILON = 1e-12


def baseline_diagnostics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    calibration_input = [
        {
            "p_up_frac": row.get("p_up_frac"),
            "p_down_frac": row.get("p_down_frac"),
            "p_timeout_frac": row.get("p_timeout_frac"),
            "realized_label": row.get("realized_label"),
            "terminal_return_frac": row.get("terminal_return_frac"),
        }
        for row in rows
    ]
    computed = compute_calibration_metrics(calibration_input)
    valid_rows = [row for row in rows if normalized_probabilities(row) is not None]
    outcome = count_distribution(row.get("realized_label") for row in valid_rows)
    confusion = None
    cells = Counter()
    for row in valid_rows:
        probabilities = normalized_probabilities(row)
        if probabilities is None:
            continue
        cells[(top_prediction_label(probabilities), str(row["realized_label"]))] += 1
    if cells and all(
        cells[(predicted, actual)] >= MIN_CELL_COUNT
        for predicted in _LABELS
        for actual in _LABELS
    ):
        confusion = [
            {"predicted": predicted, "actual": actual, "count": cells[(predicted, actual)]}
            for predicted in _LABELS
            for actual in _LABELS
        ]
    metrics = computed["metrics"]
    reliability = [
        {
            "bucket": bucket["bucket"],
            "count": bucket["bucket_count"],
            "average_top_probability": bucket["avg_predicted_max_prob"],
            "top_label_frequency": bucket["empirical_hit_rate"],
            "calibration_gap": bucket["calibration_gap"],
        }
        for bucket in computed["reliability_buckets"]
        if bucket["bucket_count"] >= MIN_CELL_COUNT
    ]
    warnings = []
    if len(valid_rows) < 100:
        warnings.append("LOW_EFFECTIVE_SAMPLE_DESCRIPTIVE_ONLY")
    if confusion is None:
        warnings.append("CONFUSION_MATRIX_WITHHELD_SPARSE_CLASS")
    if not reliability:
        warnings.append("RELIABILITY_BUCKETS_WITHHELD_SPARSE_CELL")
    return {
        "valid_count": len(valid_rows),
        "invalid_probability_count": len(rows) - len(valid_rows),
        "brier_score": metrics["brier_score"],
        "log_loss": metrics["log_loss"],
        "top_label_hit_diagnostic": metrics["top_label_hit_rate"],
        "outcome_distribution": outcome,
        "confusion_matrix": confusion,
        "reliability_buckets": reliability,
        "warnings": warnings,
    }


def feature_conditioned_diagnostics(
    rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], bool, bool]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row.get("feature_state", "UNKNOWN"))].append(row)
    class_counts = Counter(str(row.get("realized_label")) for row in rows)
    sparse_class = bool(rows) and any(
        class_counts.get(label, 0) < MIN_CELL_COUNT for label in _LABELS
    )
    if sparse_class:
        return [], any(len(state_rows) < MIN_CELL_COUNT for state_rows in grouped.values()), True
    reports = []
    sparse_cell = False
    for state in sorted(grouped):
        state_rows = grouped[state]
        if len(state_rows) < MIN_CELL_COUNT:
            sparse_cell = True
            continue
        valid = [row for row in state_rows if normalized_probabilities(row) is not None]
        brier_values = []
        log_values = []
        realized_residuals = []
        top_probabilities = []
        top_hits = []
        for row in valid:
            probabilities = normalized_probabilities(row)
            if probabilities is None:
                continue
            realized = str(row["realized_label"])
            one_hot = {label: 1.0 if label == realized else 0.0 for label in _LABELS}
            brier_values.append(
                sum((probabilities[label] - one_hot[label]) ** 2 for label in _LABELS)
            )
            log_values.append(-math.log(max(probabilities[realized], _EPSILON)))
            realized_residuals.append(1.0 - probabilities[realized])
            top_label = top_prediction_label(probabilities)
            top_probabilities.append(probabilities[top_label])
            top_hits.append(1.0 if top_label == realized else 0.0)
        average_top = _mean(top_probabilities)
        top_frequency = _mean(top_hits)
        reports.append(
            {
                "state_or_bucket": state,
                "count": len(state_rows),
                "outcome_distribution": count_distribution(
                    row.get("realized_label") for row in state_rows
                ),
                "mean_brier_contribution": _mean(brier_values),
                "mean_log_loss_contribution": _mean(log_values),
                "mean_realized_probability_residual": _mean(realized_residuals),
                "calibration_gap": (
                    None
                    if average_top is None or top_frequency is None
                    else average_top - top_frequency
                ),
                "class_conditional_frequencies": _frequency_distribution(
                    row.get("realized_label") for row in state_rows
                ),
            }
        )
    return reports, sparse_cell, sparse_class


def ordered_monotonicity(diagnostics: list[dict[str, Any]]) -> bool | None:
    ordered = [item for item in diagnostics if item["state_or_bucket"].startswith("Q")]
    if len(ordered) < 2:
        return None
    ordered.sort(key=lambda item: int(item["state_or_bucket"][1:]))
    up_frequencies = []
    for item in ordered:
        frequencies = {
            entry["key"]: entry["fraction"]
            for entry in item["class_conditional_frequencies"]
        }
        up_frequencies.append(frequencies.get("UP", 0.0))
    return all(
        left <= right
        for left, right in zip(up_frequencies, up_frequencies[1:], strict=False)
    )


def normalized_probabilities(row: dict[str, Any]) -> dict[str, float] | None:
    values = {}
    for key, label in (
        ("p_up_frac", "UP"),
        ("p_down_frac", "DOWN"),
        ("p_timeout_frac", "TIMEOUT"),
    ):
        try:
            value = float(row[key])
        except (KeyError, TypeError, ValueError):
            return None
        if not math.isfinite(value) or not 0.0 <= value <= 1.0:
            return None
        values[label] = value
    total = sum(values.values())
    if not math.isclose(total, 1.0, abs_tol=1e-9):
        return None
    if row.get("realized_label") not in _LABELS:
        return None
    return values


def count_distribution(values) -> list[dict[str, Any]]:
    counts = Counter(str(value) for value in values)
    return [{"key": key, "count": counts[key]} for key in sorted(counts)]


def data_quality_distribution(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    values = []
    for row in rows:
        quality = row.get("feature", {}).get("data_quality", {})
        values.append(str(quality.get("upstream_status") or "UNKNOWN"))
    return count_distribution(values)


def _frequency_distribution(values) -> list[dict[str, Any]]:
    counts = Counter(str(value) for value in values)
    total = sum(counts.values())
    return [
        {"key": key, "count": counts[key], "fraction": counts[key] / total if total else None}
        for key in sorted(counts)
    ]


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None
