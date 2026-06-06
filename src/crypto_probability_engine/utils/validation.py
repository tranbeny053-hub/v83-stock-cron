"""Sentinel and JSON value validation helpers."""

from __future__ import annotations

from datetime import datetime
from math import isfinite
from typing import Any


def ensure_utc_datetime(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware UTC")
    if value.utcoffset().total_seconds() != 0:
        raise ValueError(f"{field_name} must be UTC")
    return value


def ensure_no_nan_inf(value: Any, path: str = "payload") -> Any:
    if isinstance(value, float) and not isfinite(value):
        raise ValueError(f"{path} contains non-finite float")
    if isinstance(value, dict):
        for key, item in value.items():
            ensure_no_nan_inf(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            ensure_no_nan_inf(item, f"{path}[{index}]")
    return value


def ensure_frac_fields(value: Any, path: str = "payload") -> Any:
    if isinstance(value, dict):
        for key, item in value.items():
            item_path = f"{path}.{key}"
            if key.endswith("_frac") and item is not None:
                if not isinstance(item, int | float):
                    raise ValueError(f"{item_path} must be numeric")
                if not 0.0 <= float(item) <= 1.0:
                    raise ValueError(f"{item_path} must be in [0, 1]")
            ensure_frac_fields(item, item_path)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            ensure_frac_fields(item, f"{path}[{index}]")
    return value


def ensure_json_sentinel_rules(value: Any) -> Any:
    ensure_no_nan_inf(value)
    ensure_frac_fields(value)
    return value

