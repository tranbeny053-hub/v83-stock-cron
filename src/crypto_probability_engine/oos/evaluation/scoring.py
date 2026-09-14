"""Pure row, window, and calibration scoring for Section 5A."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from crypto_probability_engine.calibration.metrics import (
    brier_score,
    compute_calibration_metrics,
    normalize_probabilities,
)
from crypto_probability_engine.calibration.schemas import OutcomeLabel


def per_row_d(
    candidate_probabilities: Mapping[OutcomeLabel, float],
    baseline_probabilities: Mapping[OutcomeLabel, float],
    realized_label: OutcomeLabel,
) -> float:
    """Return candidate Brier minus baseline Brier; negative favors candidate.

    Both arms are NORMALIZED first. §5A.4 defines Brier against one-hot on normalized
    probabilities, and the ECE path normalizes internally, so scoring raw values here
    would treat a tolerance-admitted row (sum within 1e-6 of 1.0) differently in the two
    statistics.
    """

    candidate = normalize_probabilities(candidate_probabilities)
    baseline = normalize_probabilities(baseline_probabilities)
    if candidate is None or baseline is None:
        raise ValueError("per-row d requires normalizable probabilities for both arms")
    return brier_score(candidate, realized_label) - brier_score(baseline, realized_label)


def window_mean(d_values: Iterable[float]) -> float:
    """Return the arithmetic mean of admitted per-row differences in one window."""

    values = list(d_values)
    if not values:
        raise ValueError("a usable window must contain at least one admitted pair")
    return sum(values) / len(values)


class EceEvidenceError(ValueError):
    """Raised when ECE would be computed over absent or narrowed evidence."""


def ece(rows: list[dict[str, Any]]) -> float:
    """Return ECE folded over every pre-fixed reliability bucket.

    Raises rather than returning a number when the evidence is empty or when the
    scored population is a strict subset of ``rows``.  Both are pinned in
    ``docs/SECTION_5A_EVALUATION_PREREGISTRATION.md`` §10: an empty input would let
    both arms tie and read as non-degradation satisfied on no evidence, and a
    silently narrowed population would change the estimand of a one-shot decision.
    """

    if not rows:
        raise EceEvidenceError("ECE is undefined on an empty evidence set")

    report = compute_calibration_metrics(rows)
    buckets = report["reliability_buckets"]
    total = sum(bucket["bucket_count"] for bucket in buckets)
    if total != len(rows):
        raise EceEvidenceError(
            "ECE population is a strict subset of the supplied evidence: "
            f"{total} of {len(rows)} rows were scored"
        )

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

