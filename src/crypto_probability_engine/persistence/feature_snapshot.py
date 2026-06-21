"""Strict immutable projection for prediction-time Quant V2 evidence."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import datetime
from enum import StrEnum
from math import isfinite
from typing import Any


class FeatureSnapshotWriteStatus(StrEnum):
    INSERTED = "INSERTED"
    IDENTICAL_DUPLICATE = "IDENTICAL_DUPLICATE"
    CONFLICT = "CONFLICT"
    UNAVAILABLE = "UNAVAILABLE"


BLOCK_PAYLOAD_FIELDS = (
    "schema_version",
    "status",
    "influence_mode",
    "feature_methodology_version",
    "computed_at_utc",
    "symbol",
    "normalized_symbol",
    "timeframe",
    "reference_close_utc",
    "input_staleness_seconds",
    "no_lookahead_assertion",
    "feature_count",
    "degraded_count",
    "not_trade_command",
    "not_financial_advice",
    "features",
)

FEATURE_PAYLOAD_FIELDS = (
    "feature_name",
    "feature_id",
    "family",
    "timeframe",
    "symbol",
    "source_provider",
    "source_priority",
    "lookback",
    "candle_count",
    "computed_at",
    "input_start_time",
    "input_end_time",
    "input_staleness_seconds",
    "status",
    "reason_if_invalid",
    "raw_value",
    "normalized_value",
    "bucket",
    "direction_hint",
    "confidence_hint",
    "risk_hint",
    "influence_mode",
    "methodology_version",
    "data_quality",
    "no_lookahead_assertion",
)

DATA_QUALITY_FIELDS = (
    "upstream_status",
    "provider_state_status",
    "snapshot_source_status",
    "timestamp_evidence_complete",
)

_BLOCK_STATUSES = {"ACTIVE", "DEGRADED", "DISABLED"}
_FEATURE_STATUSES = {
    "VALID",
    "INSUFFICIENT_HISTORY",
    "STALE_INPUT",
    "PROVIDER_UNAVAILABLE",
    "COMPUTE_ERROR",
    "NOT_APPLICABLE",
    "DEGRADED",
}
_FEATURE_FAMILIES = {"VOLATILITY", "TREND", "VOLUME", "REGIME"}


def build_feature_snapshot(
    prediction_row: Mapping[str, Any] | None,
    quant_v2: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    """Return an allowlisted immutable evidence row, or ``None`` when unsafe."""

    if not isinstance(prediction_row, Mapping) or not isinstance(quant_v2, Mapping):
        return None
    try:
        payload = _project_block(quant_v2)
        row = {
            "prediction_id": _required_text(prediction_row, "prediction_id"),
            "run_id": _required_text(prediction_row, "run_id"),
            "symbol": _required_text(prediction_row, "symbol"),
            "normalized_symbol": _required_text(prediction_row, "normalized_symbol"),
            "timeframe": _required_text(prediction_row, "timeframe"),
            "prediction_as_of_utc": _required_timestamp(
                prediction_row, "predicted_at_utc"
            ),
            "reference_close_utc": _required_timestamp(
                prediction_row, "reference_close_utc"
            ),
            "quant_v2_schema_version": _required_text(payload, "schema_version"),
            "feature_methodology_version": _required_text(
                payload, "feature_methodology_version"
            ),
            "influence_mode": _required_text(payload, "influence_mode"),
            "no_lookahead_assertion": _required_bool(
                payload, "no_lookahead_assertion"
            ),
            "block_status": _required_text(payload, "status"),
            "feature_count": _required_nonnegative_int(payload, "feature_count"),
            "degraded_count": _required_nonnegative_int(payload, "degraded_count"),
            "provider_signature": _provider_signature(payload["features"]),
            "snapshot_payload": payload,
        }
        _validate_header(row, payload)
        row["snapshot_hash"] = _snapshot_hash(row)
        _canonical_json(row)
        return row
    except (KeyError, TypeError, ValueError, OverflowError):
        return None


def _project_block(block: Mapping[str, Any]) -> dict[str, Any]:
    _require_fields(block, BLOCK_PAYLOAD_FIELDS)
    if block["schema_version"] != "quant_v2.0":
        raise ValueError("Unsupported Quant V2 schema version.")
    if block["feature_methodology_version"] != "quant-v2-shadow-v0":
        raise ValueError("Unsupported feature methodology version.")
    if block["influence_mode"] != "SHADOW_ONLY":
        raise ValueError("Snapshot evidence must remain shadow-only.")
    features = block["features"]
    if not isinstance(features, list):
        raise TypeError("Features must be a list.")
    projected = {key: block[key] for key in BLOCK_PAYLOAD_FIELDS if key != "features"}
    projected["features"] = [_project_feature(feature) for feature in features]
    _validate_block(projected)
    _canonical_json(projected)
    return projected


def _project_feature(feature: Any) -> dict[str, Any]:
    if not isinstance(feature, Mapping):
        raise TypeError("Feature evidence must be an object.")
    _require_fields(feature, FEATURE_PAYLOAD_FIELDS)
    projected = {
        key: feature[key] for key in FEATURE_PAYLOAD_FIELDS if key != "data_quality"
    }
    data_quality = feature["data_quality"]
    if not isinstance(data_quality, Mapping):
        raise TypeError("Feature data quality must be an object.")
    _require_fields(data_quality, DATA_QUALITY_FIELDS)
    projected["data_quality"] = {key: data_quality[key] for key in DATA_QUALITY_FIELDS}
    _validate_feature(projected)
    return projected


def _validate_header(row: Mapping[str, Any], payload: Mapping[str, Any]) -> None:
    if row["influence_mode"] != "SHADOW_ONLY":
        raise ValueError("Snapshot evidence must remain shadow-only.")
    if row["block_status"] not in _BLOCK_STATUSES:
        raise ValueError("Invalid block status.")
    if row["degraded_count"] > row["feature_count"]:
        raise ValueError("Degraded count exceeds feature count.")
    for key in ("symbol", "normalized_symbol", "timeframe"):
        if row[key] != payload[key]:
            raise ValueError("Prediction and Quant V2 identity differ.")
    if not _same_timestamp(row["prediction_as_of_utc"], payload["computed_at_utc"]):
        raise ValueError("Prediction and Quant V2 as-of timestamps differ.")
    if not _same_timestamp(row["reference_close_utc"], payload["reference_close_utc"]):
        raise ValueError("Prediction and Quant V2 reference timestamps differ.")


def _validate_block(block: Mapping[str, Any]) -> None:
    status = _required_text(block, "status")
    if status not in _BLOCK_STATUSES:
        raise ValueError("Invalid block status.")
    if block["influence_mode"] != "SHADOW_ONLY":
        raise ValueError("Invalid governance mode.")
    if _required_text(block, "symbol") == "":
        raise ValueError("Symbol is required.")
    _required_text(block, "normalized_symbol")
    _required_text(block, "timeframe")
    _required_timestamp(block, "computed_at_utc")
    _required_timestamp(block, "reference_close_utc")
    _optional_nonnegative_number(block["input_staleness_seconds"])
    no_lookahead = _required_bool(block, "no_lookahead_assertion")
    feature_count = _required_nonnegative_int(block, "feature_count")
    degraded_count = _required_nonnegative_int(block, "degraded_count")
    features = block["features"]
    actual_degraded = sum(item["status"] != "VALID" for item in features)
    if feature_count != len(features) or degraded_count != actual_degraded:
        raise ValueError("Feature counts are inconsistent.")
    if status == "DISABLED" and (feature_count or degraded_count or features):
        raise ValueError("Disabled blocks must not contain features.")
    if status != "DISABLED" and feature_count != 4:
        raise ValueError("Enabled blocks require four features.")
    if status == "ACTIVE" and (degraded_count or not no_lookahead):
        raise ValueError("Active blocks require complete valid evidence.")
    if status == "DEGRADED" and degraded_count < 1:
        raise ValueError("Degraded blocks require degraded evidence.")
    if block["not_trade_command"] is not True or block["not_financial_advice"] is not True:
        raise ValueError("Snapshot safety assertions are required.")


def _validate_feature(feature: Mapping[str, Any]) -> None:
    for key in ("feature_name", "feature_id", "timeframe", "symbol"):
        _required_text(feature, key)
    if feature["family"] not in _FEATURE_FAMILIES:
        raise ValueError("Invalid feature family.")
    _optional_text(feature["source_provider"])
    _optional_positive_int(feature["source_priority"])
    _optional_positive_int(feature["lookback"])
    _required_nonnegative_int(feature, "candle_count")
    for key in ("computed_at", "input_start_time", "input_end_time"):
        _optional_timestamp(feature[key])
    _optional_nonnegative_number(feature["input_staleness_seconds"])
    status = _required_text(feature, "status")
    if status not in _FEATURE_STATUSES:
        raise ValueError("Invalid feature status.")
    reason = feature["reason_if_invalid"]
    if status == "VALID" and reason is not None:
        raise ValueError("Valid evidence cannot have an invalid reason.")
    if status != "VALID" and not isinstance(reason, str):
        raise ValueError("Degraded evidence requires a reason.")
    _optional_scalar(feature["raw_value"])
    for key in ("normalized_value", "bucket", "confidence_hint", "risk_hint"):
        if feature[key] is not None:
            raise ValueError("Unvalidated derived values cannot be persisted.")
    if feature["direction_hint"] not in {None, "UP", "DOWN", "SIDEWAYS"}:
        raise ValueError("Invalid direction hint.")
    if feature["influence_mode"] != "SHADOW_ONLY":
        raise ValueError("Feature evidence must remain shadow-only.")
    if feature["methodology_version"] != "quant-v2-shadow-v0":
        raise ValueError("Invalid feature methodology version.")
    quality = feature["data_quality"]
    for key in DATA_QUALITY_FIELDS[:-1]:
        _optional_text(quality[key])
    if not isinstance(quality["timestamp_evidence_complete"], bool):
        raise TypeError("Timestamp evidence flag must be boolean.")
    if not isinstance(feature["no_lookahead_assertion"], bool):
        raise TypeError("No-lookahead assertion must be boolean.")


def _provider_signature(features: list[dict[str, Any]]) -> str:
    providers = sorted(
        {
            provider.strip().upper()
            for feature in features
            if isinstance((provider := feature.get("source_provider")), str)
            and provider.strip()
        }
    )
    return "+".join(providers) if providers else "UNKNOWN"


def _snapshot_hash(row: Mapping[str, Any]) -> str:
    envelope = {
        key: value
        for key, value in row.items()
        if key not in {"snapshot_hash", "created_at"}
    }
    return hashlib.sha256(_canonical_json(envelope).encode("utf-8")).hexdigest()


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _require_fields(value: Mapping[str, Any], fields: tuple[str, ...]) -> None:
    missing = [field for field in fields if field not in value]
    if missing:
        raise KeyError(missing[0])


def _required_text(value: Mapping[str, Any], key: str) -> str:
    result = value[key]
    if not isinstance(result, str) or not result.strip():
        raise ValueError(f"{key} must be a non-empty string.")
    return result


def _optional_text(value: Any) -> None:
    if value is not None and not isinstance(value, str):
        raise TypeError("Optional text has an invalid type.")


def _required_bool(value: Mapping[str, Any], key: str) -> bool:
    result = value[key]
    if not isinstance(result, bool):
        raise TypeError(f"{key} must be boolean.")
    return result


def _required_nonnegative_int(value: Mapping[str, Any], key: str) -> int:
    result = value[key]
    if isinstance(result, bool) or not isinstance(result, int) or result < 0:
        raise ValueError(f"{key} must be a non-negative integer.")
    return result


def _optional_positive_int(value: Any) -> None:
    if value is not None and (
        isinstance(value, bool) or not isinstance(value, int) or value < 1
    ):
        raise ValueError("Optional count must be a positive integer.")


def _optional_nonnegative_number(value: Any) -> None:
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError("Optional numeric evidence has an invalid type.")
    if not isfinite(float(value)) or float(value) < 0:
        raise ValueError("Optional numeric evidence must be finite and non-negative.")


def _optional_scalar(value: Any) -> None:
    if value is None or isinstance(value, str):
        return
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError("Raw feature evidence must be a scalar.")
    if not isfinite(float(value)):
        raise ValueError("Raw feature evidence must be finite.")


def _required_timestamp(value: Mapping[str, Any], key: str) -> str:
    result = value[key]
    _parse_timestamp(result)
    return result


def _optional_timestamp(value: Any) -> None:
    if value is not None:
        _parse_timestamp(value)


def _parse_timestamp(value: Any) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Timestamp must be a non-empty string.")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("Timestamp must include a timezone.")
    return parsed


def _same_timestamp(left: Any, right: Any) -> bool:
    return _parse_timestamp(left) == _parse_timestamp(right)
