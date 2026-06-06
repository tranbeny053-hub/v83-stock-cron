"""Unit and sentinel helpers shared across modules."""

from __future__ import annotations

from datetime import UTC, datetime
from math import isfinite


def utc_now() -> datetime:
    return datetime.now(UTC)


def ensure_finite(value: float, field_name: str) -> float:
    if not isfinite(value):
        raise ValueError(f"{field_name} must be finite")
    return value


def ensure_frac(value: float, field_name: str) -> float:
    ensure_finite(value, field_name)
    if not 0.0 <= value <= 1.0:
        raise ValueError(f"{field_name} must be in [0, 1]")
    return value
