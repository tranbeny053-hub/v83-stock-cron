"""Pure calibration metric functions for resolved prediction/outcome rows."""

from __future__ import annotations

import math
from statistics import median
from typing import Any

from crypto_probability_engine.calibration.schemas import (
    OUTCOME_LABELS,
    RELIABILITY_BUCKETS,
    TOP_LABEL_TIE_ORDER,
    OutcomeLabel,
)

EPS = 1e-12


def compute_calibration_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute read-only diagnostics from resolved prediction/outcome rows."""

    valid_rows: list[dict[str, Any]] = []
    invalid_count = 0
    for row in rows:
        normalized = _normalize_row(row)
        if normalized is None:
            invalid_count += 1
            continue
        valid_rows.append(normalized)

    outcome_distribution = {label: 0 for label in OUTCOME_LABELS}
    bucket_rows: dict[str, list[dict[str, Any]]] = {
        _bucket_label(start, end): [] for start, end in RELIABILITY_BUCKETS
    }
    brier_values: list[float] = []
    log_loss_values: list[float] = []
    top_label_hits = 0
    directional_hits = 0
    directional_count = 0
    terminal_returns: list[float] = []

    for row in valid_rows:
        probs = row["probs"]
        label = row["realized_label"]
        outcome_distribution[label] += 1
        one_hot = {outcome: 1.0 if outcome == label else 0.0 for outcome in OUTCOME_LABELS}
        brier_values.append(
            sum((probs[outcome] - one_hot[outcome]) ** 2 for outcome in OUTCOME_LABELS)
        )
        log_loss_values.append(-math.log(max(probs[label], EPS)))
        top_label = top_prediction_label(probs)
        if top_label == label:
            top_label_hits += 1
        if label in {"UP", "DOWN"}:
            directional_count += 1
            if top_label == label:
                directional_hits += 1
        bucket_rows[_bucket_for_probability(probs[top_label])].append(
            {"top_probability": probs[top_label], "hit": top_label == label}
        )
        if row["terminal_return_frac"] is not None:
            terminal_returns.append(row["terminal_return_frac"])

    valid_count = len(valid_rows)
    return {
        "sample_count": len(rows),
        "valid_count": valid_count,
        "invalid_row_count": invalid_count,
        "metrics": {
            "brier_score": _mean(brier_values),
            "log_loss": _mean(log_loss_values),
            "top_label_hit_rate": _ratio(top_label_hits, valid_count),
            "directional_hit_rate": _ratio(directional_hits, directional_count),
            "directional_subset_count": directional_count,
            "directional_subset_note": "Directional subset excludes TIMEOUT outcomes.",
        },
        "reliability_buckets": [
            _summarize_bucket(_bucket_label(start, end), bucket_rows[_bucket_label(start, end)])
            for start, end in RELIABILITY_BUCKETS
        ],
        "outcome_distribution": outcome_distribution,
        "terminal_return_diagnostics": _terminal_return_diagnostics(terminal_returns),
    }


def top_prediction_label(probs: dict[OutcomeLabel, float]) -> OutcomeLabel:
    """Return top label using deterministic UP > DOWN > TIMEOUT tie-break."""

    best = TOP_LABEL_TIE_ORDER[0]
    best_prob = probs[best]
    for label in TOP_LABEL_TIE_ORDER[1:]:
        if probs[label] > best_prob:
            best = label
            best_prob = probs[label]
    return best


def _normalize_row(row: dict[str, Any]) -> dict[str, Any] | None:
    label = str(row.get("realized_label", ""))
    if label not in OUTCOME_LABELS:
        return None
    raw_probs = {}
    for key, label_name in (
        ("p_up_frac", "UP"),
        ("p_down_frac", "DOWN"),
        ("p_timeout_frac", "TIMEOUT"),
    ):
        try:
            value = float(row[key])
        except (KeyError, TypeError, ValueError):
            return None
        if not math.isfinite(value) or value < 0.0 or value > 1.0:
            return None
        raw_probs[label_name] = value
    total = sum(raw_probs.values())
    if not math.isfinite(total) or total <= 0.0:
        return None
    terminal_return = None
    if row.get("terminal_return_frac") is not None:
        try:
            terminal_return = float(row["terminal_return_frac"])
        except (TypeError, ValueError):
            terminal_return = None
        if terminal_return is not None and not math.isfinite(terminal_return):
            terminal_return = None
    return {
        "probs": {label_name: raw_probs[label_name] / total for label_name in OUTCOME_LABELS},
        "realized_label": label,
        "terminal_return_frac": terminal_return,
    }


def _bucket_for_probability(probability: float) -> str:
    for start, end in RELIABILITY_BUCKETS:
        if start <= probability < end:
            return _bucket_label(start, end)
    return _bucket_label(0.90, 1.00)


def _bucket_label(start: float, end: float) -> str:
    return f"{start:.2f}-{end:.2f}"


def _summarize_bucket(label: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    count = len(rows)
    avg_predicted = _mean([row["top_probability"] for row in rows])
    empirical = _mean([1.0 if row["hit"] else 0.0 for row in rows])
    gap = None if avg_predicted is None or empirical is None else avg_predicted - empirical
    return {
        "bucket": label,
        "bucket_count": count,
        "avg_predicted_max_prob": avg_predicted,
        "empirical_hit_rate": empirical,
        "calibration_gap": gap,
        "bucket_sample_status": "LOW_BUCKET_SAMPLE" if count < 30 else "OK",
    }


def _terminal_return_diagnostics(values: list[float]) -> dict[str, Any]:
    return {
        "count": len(values),
        "mean_terminal_return": _mean(values),
        "median_terminal_return": median(values) if values else None,
        "min_terminal_return": min(values) if values else None,
        "max_terminal_return": max(values) if values else None,
        "note": "Terminal return diagnostics only; NOT trade EV.",
    }


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def _ratio(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return numerator / denominator
