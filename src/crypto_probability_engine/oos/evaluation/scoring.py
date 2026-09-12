"""Pure row, window, and calibration scoring for Section 5A."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from crypto_probability_engine.calibration.metrics import (
    brier_score,
    compute_calibration_metrics,
)
from crypto_probability_engine.calibration.schemas import OutcomeLabel


def per_row_d(
    candidate_probabilities: Mapping[OutcomeLabel, float],
    baseline_probabilities: Mapping[OutcomeLabel, float],
    realized_label: OutcomeLabel,
) -> float:
    """Return candidate Brier minus baseline Brier; negative favors candidate."""

    return brier_score(candidate_probabilities, realized_label) - brier_score(
        baseline_probabilities, realized_label
    )


def window_mean(d_values: Iterable[float]) -> float:
    """Return the arithmetic mean of admitted per-row differences in one window."""

    values = list(d_values)
    if not values:
        raise ValueError("a usable window must contain at least one admitted pair")
    return sum(values) / len(values)


def ece(rows: list[dict[str, Any]]) -> float:
    """Return ECE folded over every pre-fixed reliability bucket."""

    report = compute_calibration_metrics(rows)
    buckets = report["reliability_buckets"]
    total = sum(bucket["bucket_count"] for bucket in buckets)
    if total == 0:
        return 0.0

    result = 0.0
    for bucket in buckets:
        count = bucket["bucket_count"]
        gap = bucket["calibration_gap"]
        if count == 0:
            continue
        if gap is None:
            raise ValueError("non-empty reliability bucket has no calibration gap")
        result += (count / total) * abs(gap)
    return result

