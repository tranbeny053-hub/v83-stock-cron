"""Canonical prediction-origin contract for cohort separation."""

from __future__ import annotations

from enum import StrEnum


class PredictionOrigin(StrEnum):
    """Supported immutable prediction provenance values."""

    USER_REQUESTED = "USER_REQUESTED"
    CONTROLLED_SMOKE = "CONTROLLED_SMOKE"
    SCHEDULED_SHADOW_EVIDENCE = "SCHEDULED_SHADOW_EVIDENCE"


DEFAULT_PREDICTION_ORIGIN = PredictionOrigin.USER_REQUESTED.value
ALLOWED_PREDICTION_ORIGINS = frozenset(origin.value for origin in PredictionOrigin)


def validate_prediction_origin(value: str | PredictionOrigin) -> str:
    """Return the canonical exact origin or reject unknown/empty values."""

    candidate = value.value if isinstance(value, PredictionOrigin) else value
    if not isinstance(candidate, str) or not candidate:
        raise ValueError("Prediction origin must be a non-empty supported value.")
    if candidate not in ALLOWED_PREDICTION_ORIGINS:
        raise ValueError("Unsupported prediction origin.")
    return candidate
