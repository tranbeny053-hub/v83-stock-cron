"""Pure row sanitization, cohorting, deduplication, and effective-N thinning."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from copy import deepcopy
from datetime import UTC, datetime
from math import isfinite
from typing import Any

from crypto_probability_engine.shadow_validation.schemas import (
    COHORT_KEYS,
    FEATURE_DATA_QUALITY_FIELDS,
)

_ROW_FIELDS = (
    "prediction_id",
    "run_id",
    "normalized_symbol",
    "symbol",
    "timeframe",
    "predicted_at_utc",
    "reference_close_utc",
    "horizon_end_utc",
    "horizon_bars",
    "p_up_frac",
    "p_down_frac",
    "p_timeout_frac",
    "model_version",
    "methodology_version",
    "prediction_is_live_data",
    "realized_label",
    "terminal_return_frac",
    "resolver_version",
    "outcome_is_live_data",
    "quant_v2_schema_version",
    "feature_methodology_version",
    "block_status",
    "no_lookahead_assertion",
    "provider_signature",
)


def sanitize_validation_row(row: Mapping[str, Any]) -> dict[str, Any]:
    """Project one joined row without retaining its source payload object."""

    sanitized = {field: deepcopy(row.get(field)) for field in _ROW_FIELDS}
    reasons = _row_validation_reasons(sanitized)
    source_payload = row.get("snapshot_payload")
    features: list[dict[str, Any]] = []
    if not isinstance(source_payload, Mapping):
        reasons.append("snapshot payload is missing or malformed")
    else:
        source_features = source_payload.get("features")
        if not isinstance(source_features, list):
            reasons.append("feature collection is missing or malformed")
        else:
            for source_feature in source_features:
                feature = _sanitize_feature(source_feature)
                if feature is not None:
                    features.append(feature)
    sanitized["features"] = features
    sanitized["cohort_valid"] = not reasons
    sanitized["invalid_reasons"] = reasons
    return sanitized


def sanitize_validation_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [sanitize_validation_row(row) for row in rows if isinstance(row, Mapping)]


def partition_cohorts(rows: list[dict[str, Any]]) -> list[tuple[dict, list[dict]]]:
    grouped: dict[tuple[Any, ...], list[dict]] = defaultdict(list)
    keys_by_group: dict[tuple[Any, ...], dict] = {}
    for row in rows:
        if row.get("cohort_valid"):
            key = tuple(row.get(field) for field in COHORT_KEYS)
            cohort_keys = {field: row.get(field) for field in COHORT_KEYS}
        else:
            key = ("INVALID", str(row.get("prediction_id", "")))
            cohort_keys = {field: row.get(field) for field in COHORT_KEYS}
        grouped[key].append(row)
        keys_by_group[key] = cohort_keys
    ordered = sorted(grouped, key=lambda key: tuple(str(value) for value in key))
    return [(keys_by_group[key], grouped[key]) for key in ordered]


def same_candle_deduplicate(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    earliest: dict[tuple[str, str, str], dict] = {}
    for row in sorted(rows, key=_observation_sort_key):
        key = (
            str(row.get("normalized_symbol", "")),
            str(row.get("timeframe", "")),
            str(row.get("reference_close_utc", "")),
        )
        earliest.setdefault(key, row)
    return sorted(earliest.values(), key=_observation_sort_key)


def effective_n_thin(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in rows:
        grouped[
            (
                str(row.get("normalized_symbol", "")),
                str(row.get("timeframe", "")),
            )
        ].append(row)
    kept: list[dict] = []
    for key in sorted(grouped):
        last_horizon_end: datetime | None = None
        for row in sorted(grouped[key], key=_observation_sort_key):
            predicted_at = parse_utc(row.get("predicted_at_utc"))
            horizon_end = parse_utc(row.get("horizon_end_utc"))
            if predicted_at is None or horizon_end is None:
                continue
            if last_horizon_end is None or predicted_at >= last_horizon_end:
                kept.append(row)
                last_horizon_end = horizon_end
    return sorted(kept, key=_observation_sort_key)


def observation_counts(rows: list[dict[str, Any]]) -> tuple[int, int, int]:
    deduplicated = same_candle_deduplicate(rows)
    effective = effective_n_thin(deduplicated)
    return len(rows), len(deduplicated), len(effective)


def parse_utc(value: Any) -> datetime | None:
    try:
        if isinstance(value, datetime):
            parsed = value
        elif isinstance(value, str):
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        else:
            return None
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _sanitize_feature(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    feature = {
        "feature_id": _safe_text(value.get("feature_id")),
        "family": _safe_text(value.get("family")),
        "status": _safe_text(value.get("status")),
        "raw_value": _safe_raw_value(value.get("raw_value")),
        "direction_hint": _safe_text(value.get("direction_hint")),
        "lookback": _safe_nonnegative_integer(value.get("lookback")),
        "candle_count": _safe_nonnegative_integer(value.get("candle_count")),
        "source_provider": _safe_text(value.get("source_provider")),
        "no_lookahead_assertion": (
            value.get("no_lookahead_assertion")
            if isinstance(value.get("no_lookahead_assertion"), bool)
            else None
        ),
    }
    quality = value.get("data_quality")
    feature["data_quality"] = (
        {
            field: (
                quality.get(field)
                if isinstance(quality.get(field), (str, bool))
                or quality.get(field) is None
                else None
            )
            for field in FEATURE_DATA_QUALITY_FIELDS
        }
        if isinstance(quality, Mapping)
        else {field: None for field in FEATURE_DATA_QUALITY_FIELDS}
    )
    feature["feature_valid"] = bool(
        isinstance(feature.get("feature_id"), str)
        and feature["feature_id"]
        and isinstance(feature.get("family"), str)
        and feature["family"]
        and isinstance(feature.get("status"), str)
        and feature["status"]
    )
    return feature


def _safe_text(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _safe_raw_value(value: Any) -> str | float | int | None:
    if isinstance(value, str) or value is None:
        return value
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value if isfinite(float(value)) else None


def _safe_nonnegative_integer(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _row_validation_reasons(row: Mapping[str, Any]) -> list[str]:
    reasons = []
    required_text = (
        "prediction_id",
        "run_id",
        "normalized_symbol",
        "symbol",
        "timeframe",
        "model_version",
        "methodology_version",
        "resolver_version",
        "quant_v2_schema_version",
        "feature_methodology_version",
        "block_status",
        "provider_signature",
    )
    for field in required_text:
        if not isinstance(row.get(field), str) or not str(row.get(field)).strip():
            reasons.append(f"missing required cohort field: {field}")
    for field in ("predicted_at_utc", "reference_close_utc", "horizon_end_utc"):
        if parse_utc(row.get(field)) is None:
            reasons.append(f"invalid timestamp: {field}")
    if row.get("prediction_is_live_data") is not True:
        reasons.append("prediction row is not live")
    if row.get("outcome_is_live_data") is not True:
        reasons.append("outcome row is not live")
    if row.get("realized_label") not in {"UP", "DOWN", "TIMEOUT"}:
        reasons.append("invalid realized label")
    if row.get("block_status") not in {"ACTIVE", "DEGRADED", "DISABLED"}:
        reasons.append("invalid block status")
    if not isinstance(row.get("no_lookahead_assertion"), bool):
        reasons.append("invalid no-lookahead assertion")
    return reasons


def _observation_sort_key(row: Mapping[str, Any]) -> tuple[datetime, str]:
    parsed = parse_utc(row.get("predicted_at_utc")) or datetime.min.replace(tzinfo=UTC)
    return parsed, str(row.get("prediction_id", ""))
