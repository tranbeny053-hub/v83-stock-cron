"""Chronological development-fit representations for shadow diagnostics."""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil, isfinite
from typing import Any

from crypto_probability_engine.shadow_validation.cohorts import parse_utc
from crypto_probability_engine.shadow_validation.schemas import (
    MIN_CELL_COUNT,
    TEMPORAL_SPLIT_MINIMUM,
)


@dataclass(frozen=True)
class TemporalSplit:
    status: str
    development: tuple[dict, ...]
    validation: tuple[dict, ...]


def chronological_split(rows: list[dict[str, Any]]) -> TemporalSplit:
    ordered = sorted(
        rows,
        key=lambda row: (
            parse_utc(row.get("predicted_at_utc")),
            str(row.get("prediction_id", "")),
        ),
    )
    if len(ordered) < TEMPORAL_SPLIT_MINIMUM:
        return TemporalSplit(
            "NOT_AVAILABLE_INSUFFICIENT_EFFECTIVE_SAMPLE",
            (),
            (),
        )
    development_count = max(1, min(len(ordered) - 1, int(len(ordered) * 0.70)))
    return TemporalSplit(
        "AVAILABLE_DEVELOPMENT_VALIDATION_ONLY",
        tuple(ordered[:development_count]),
        tuple(ordered[development_count:]),
    )


def fit_frozen_quantile_edges(values: list[Any]) -> tuple[float, ...] | None:
    numeric = sorted(
        float(value)
        for value in values
        if _is_finite_number(value) and float(value) >= 0.0
    )
    bin_count = min(4, len(numeric) // MIN_CELL_COUNT)
    if bin_count < 2:
        return None
    edges = []
    for index in range(1, bin_count):
        position = max(0, min(len(numeric) - 1, ceil(index * len(numeric) / bin_count) - 1))
        edges.append(numeric[position])
    unique = tuple(sorted(set(edges)))
    return unique if unique else None


def apply_frozen_edges(value: Any, edges: tuple[float, ...] | None) -> str:
    if not _is_finite_number(value) or edges is None:
        return "UNBINNED_OR_MISSING"
    numeric = float(value)
    for index, edge in enumerate(edges, start=1):
        if numeric <= edge:
            return f"Q{index}"
    return f"Q{len(edges) + 1}"


def categorical_state(family: str, feature: dict[str, Any]) -> str:
    if feature.get("status") != "VALID":
        return "MISSING_OR_DEGRADED"
    if family == "TREND":
        value = feature.get("direction_hint")
        return value if value in {"UP", "DOWN", "SIDEWAYS"} else "UNKNOWN"
    value = feature.get("raw_value")
    return str(value) if isinstance(value, str) and value else "UNKNOWN"


def _is_finite_number(value: Any) -> bool:
    return bool(
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and isfinite(float(value))
    )
