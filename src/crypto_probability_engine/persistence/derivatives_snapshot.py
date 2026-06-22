"""Strict immutable projection for prediction-linked derivatives evidence."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import UTC, datetime
from enum import StrEnum
from math import isfinite
from typing import Any


class DerivativesSnapshotWriteStatus(StrEnum):
    INSERTED = "INSERTED"
    IDENTICAL_DUPLICATE = "IDENTICAL_DUPLICATE"
    CONFLICT = "CONFLICT"
    UNAVAILABLE = "UNAVAILABLE"


SNAPSHOT_PAYLOAD_FIELDS = (
    "schema_version",
    "methodology_version",
    "influence_mode",
    "decision_influence_frac",
    "normalized_symbol",
    "core_prediction_as_of_utc",
    "observation_as_of_utc",
    "block_status",
    "provider_summary",
    "metrics",
    "comparability",
    "disagreement",
    "warnings",
    "not_trade_command",
    "not_financial_advice",
)

PROVIDER_SUMMARY_FIELDS = (
    "provider",
    "status",
    "valid_metric_count",
    "total_metric_count",
    "reason",
)

METRIC_FIELDS = (
    "metric_id",
    "family",
    "provider",
    "provider_endpoint",
    "provider_instrument",
    "normalized_symbol",
    "contract_type",
    "margin_asset",
    "settlement_asset",
    "timeframe_or_period",
    "event_time",
    "interval_start",
    "interval_end",
    "interval_final",
    "fetched_at_utc",
    "prediction_as_of_utc",
    "input_staleness_seconds",
    "status",
    "reason_if_invalid",
    "raw_value",
    "normalized_value",
    "bucket",
    "direction_hint",
    "confidence_hint",
    "risk_hint",
    "unit",
    "source_count",
    "provider_priority",
    "influence_mode",
    "methodology_version",
    "no_lookahead_assertion",
)

COMPARABILITY_FIELDS = (
    "semantic_class",
    "left_provider",
    "right_provider",
    "comparable",
    "reason",
)

_ELIGIBLE_BLOCK_STATUSES = {"ACTIVE", "DEGRADED", "UNAVAILABLE"}
_PROVIDER_STATUSES = {
    "AVAILABLE",
    "DEGRADED_PARTIAL",
    "UNSUPPORTED_INSTRUMENT",
    "INSTRUMENT_INACTIVE",
    "PROVIDER_UNAVAILABLE",
    "NO_VALID_METRIC",
}
_METRIC_STATUSES = {
    "VALID",
    "INSUFFICIENT_HISTORY",
    "STALE_INPUT",
    "PROVIDER_UNAVAILABLE",
    "UNSUPPORTED_INSTRUMENT",
    "CONTRACT_MISMATCH",
    "INSTRUMENT_INACTIVE",
    "PARTIAL_INTERVAL",
    "INVALID_UNIT",
    "COMPUTE_ERROR",
    "DEGRADED",
}
_METRIC_FAMILIES = {"FUNDING", "OPEN_INTEREST"}
_PROVIDERS = {"BINANCE_USDM", "OKX_SWAP"}


def build_derivatives_snapshot(
    prediction_row: Mapping[str, Any] | None,
    derivatives_intelligence: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    """Return an allowlisted immutable row, or ``None`` when ineligible or unsafe."""

    if not isinstance(prediction_row, Mapping) or not isinstance(
        derivatives_intelligence, Mapping
    ):
        return None
    try:
        if derivatives_intelligence.get("block_status") not in _ELIGIBLE_BLOCK_STATUSES:
            return None
        payload = _project_payload(derivatives_intelligence)
        prediction_id = _required_text(prediction_row, "prediction_id")
        run_id = _required_text(prediction_row, "run_id")
        normalized_symbol = _required_text(prediction_row, "normalized_symbol")
        predicted_at = _required_timestamp(prediction_row, "predicted_at_utc")
        core_time = _required_timestamp(payload, "core_prediction_as_of_utc")
        observation_time = _required_timestamp(payload, "observation_as_of_utc")
        if payload["normalized_symbol"] != normalized_symbol:
            raise ValueError("Prediction and derivatives symbols differ.")
        if predicted_at != core_time:
            raise ValueError("Prediction and derivatives core timestamps differ.")
        if observation_time < core_time:
            raise ValueError("Observation timestamp precedes core prediction timestamp.")
        row = {
            "prediction_id": prediction_id,
            "run_id": run_id,
            "normalized_symbol": normalized_symbol,
            "derivatives_schema_version": payload["schema_version"],
            "derivatives_methodology_version": payload["methodology_version"],
            "influence_mode": payload["influence_mode"],
            "decision_influence_frac": payload["decision_influence_frac"],
            "block_status": payload["block_status"],
            "core_prediction_as_of_utc": _iso_utc(core_time),
            "observation_as_of_utc": _iso_utc(observation_time),
            "snapshot_payload": payload,
        }
        row["snapshot_payload"]["core_prediction_as_of_utc"] = row[
            "core_prediction_as_of_utc"
        ]
        row["snapshot_payload"]["observation_as_of_utc"] = row[
            "observation_as_of_utc"
        ]
        row["snapshot_hash"] = snapshot_hash(row)
        _canonical_json(row)
        return row
    except (KeyError, TypeError, ValueError, OverflowError):
        return None


def snapshot_hash(row: Mapping[str, Any]) -> str:
    """Hash every immutable stored field except the hash and database timestamp."""

    envelope = {
        key: value
        for key, value in row.items()
        if key not in {"snapshot_hash", "created_at"}
    }
    return hashlib.sha256(_canonical_json(envelope).encode("utf-8")).hexdigest()


def _project_payload(block: Mapping[str, Any]) -> dict[str, Any]:
    _require_fields(block, SNAPSHOT_PAYLOAD_FIELDS)
    projected = {
        key: block[key]
        for key in SNAPSHOT_PAYLOAD_FIELDS
        if key not in {"provider_summary", "metrics", "comparability", "warnings"}
    }
    projected["provider_summary"] = _project_list(
        block["provider_summary"], _project_provider_summary
    )
    projected["metrics"] = _project_list(block["metrics"], _project_metric)
    projected["comparability"] = _project_list(
        block["comparability"], _project_comparability
    )
    warnings = block["warnings"]
    if not isinstance(warnings, list) or not all(isinstance(item, str) for item in warnings):
        raise TypeError("Warnings must be a list of strings.")
    projected["warnings"] = list(warnings)
    _validate_payload(projected)
    _canonical_json(projected)
    return projected


def _project_list(value: Any, projector) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise TypeError("Evidence collection must be a list.")
    return [projector(item) for item in value]


def _project_provider_summary(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError("Provider summary must be an object.")
    _require_fields(value, PROVIDER_SUMMARY_FIELDS)
    projected = {key: value[key] for key in PROVIDER_SUMMARY_FIELDS}
    if projected["provider"] not in _PROVIDERS:
        raise ValueError("Invalid derivatives provider.")
    if projected["status"] not in _PROVIDER_STATUSES:
        raise ValueError("Invalid provider status.")
    valid_count = _nonnegative_int(projected["valid_metric_count"])
    total_count = _nonnegative_int(projected["total_metric_count"])
    if valid_count > total_count:
        raise ValueError("Valid metric count exceeds total metric count.")
    reason = projected["reason"]
    if projected["status"] == "AVAILABLE":
        if reason is not None or total_count == 0 or valid_count != total_count:
            raise ValueError("Available provider evidence is inconsistent.")
    elif not isinstance(reason, str) or not reason.strip():
        raise ValueError("Unavailable provider evidence requires a reason.")
    return projected


def _project_metric(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError("Derivative metric must be an object.")
    _require_fields(value, METRIC_FIELDS)
    metric = {key: value[key] for key in METRIC_FIELDS}
    for key in (
        "metric_id",
        "provider_endpoint",
        "provider_instrument",
        "normalized_symbol",
        "contract_type",
        "margin_asset",
        "settlement_asset",
        "unit",
    ):
        _required_text(metric, key)
    if metric["family"] not in _METRIC_FAMILIES:
        raise ValueError("Invalid metric family.")
    if metric["provider"] not in _PROVIDERS:
        raise ValueError("Invalid metric provider.")
    if metric["status"] not in _METRIC_STATUSES:
        raise ValueError("Invalid metric status.")
    if metric["influence_mode"] != "SHADOW_ONLY":
        raise ValueError("Derivative metrics must remain shadow-only.")
    if metric["methodology_version"] != "deriv-intel-shadow-v0":
        raise ValueError("Invalid derivatives methodology version.")
    for key in ("normalized_value", "bucket", "direction_hint", "confidence_hint", "risk_hint"):
        if metric[key] is not None:
            raise ValueError("Unvalidated interpretation cannot be persisted.")
    for key in (
        "event_time",
        "interval_start",
        "interval_end",
    ):
        if metric[key] is not None:
            _parse_timestamp(metric[key])
    _parse_timestamp(metric["fetched_at_utc"])
    _parse_timestamp(metric["prediction_as_of_utc"])
    _optional_finite_number(metric["input_staleness_seconds"], nonnegative=True)
    _optional_finite_number(metric["raw_value"])
    _nonnegative_int(metric["source_count"])
    if _nonnegative_int(metric["provider_priority"]) < 1:
        raise ValueError("Provider priority must be positive.")
    if not isinstance(metric["interval_final"], bool) or not isinstance(
        metric["no_lookahead_assertion"], bool
    ):
        raise TypeError("Metric provenance flags must be boolean.")
    reason = metric["reason_if_invalid"]
    if metric["status"] == "VALID":
        if reason is not None:
            raise ValueError("Valid metrics cannot have an invalid reason.")
    elif not isinstance(reason, str) or not reason.strip():
        raise ValueError("Invalid metrics require a reason.")
    if metric["timeframe_or_period"] is not None and not isinstance(
        metric["timeframe_or_period"], str
    ):
        raise TypeError("Metric period must be text or null.")
    return metric


def _project_comparability(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError("Comparability evidence must be an object.")
    _require_fields(value, COMPARABILITY_FIELDS)
    projected = {key: value[key] for key in COMPARABILITY_FIELDS}
    if projected["semantic_class"] not in {"CURRENT_FUNDING", "CURRENT_OPEN_INTEREST"}:
        raise ValueError("Invalid comparison class.")
    if projected["left_provider"] != "BINANCE_USDM" or projected[
        "right_provider"
    ] != "OKX_SWAP":
        raise ValueError("Invalid comparison providers.")
    if not isinstance(projected["comparable"], bool):
        raise TypeError("Comparability flag must be boolean.")
    _required_text(projected, "reason")
    return projected


def _validate_payload(payload: Mapping[str, Any]) -> None:
    if payload["schema_version"] != "deriv-intel.v0":
        raise ValueError("Unsupported derivatives schema version.")
    if payload["methodology_version"] != "deriv-intel-shadow-v0":
        raise ValueError("Unsupported derivatives methodology version.")
    if payload["influence_mode"] != "SHADOW_ONLY":
        raise ValueError("Derivatives evidence must remain shadow-only.")
    fraction = payload["decision_influence_frac"]
    if isinstance(fraction, bool) or not isinstance(fraction, (int, float)) or fraction != 0:
        raise ValueError("Decision influence must remain zero.")
    _required_text(payload, "normalized_symbol")
    core_time = _required_timestamp(payload, "core_prediction_as_of_utc")
    observation_time = _required_timestamp(payload, "observation_as_of_utc")
    if observation_time < core_time:
        raise ValueError("Observation timestamp precedes core prediction timestamp.")
    if payload["block_status"] not in _ELIGIBLE_BLOCK_STATUSES:
        raise ValueError("Block is not eligible for persistence.")
    summaries = payload["provider_summary"]
    if len(summaries) != 2 or {item["provider"] for item in summaries} != _PROVIDERS:
        raise ValueError("Eligible evidence requires both provider summaries.")
    available_count = sum(item["status"] == "AVAILABLE" for item in summaries)
    if payload["block_status"] == "ACTIVE" and available_count != 2:
        raise ValueError("Active evidence requires both providers available.")
    if payload["block_status"] == "DEGRADED" and available_count != 1:
        raise ValueError("Degraded evidence requires mixed provider availability.")
    if payload["block_status"] == "UNAVAILABLE" and available_count:
        raise ValueError("Unavailable evidence cannot contain an available provider.")
    for metric in payload["metrics"]:
        if metric["normalized_symbol"] != payload["normalized_symbol"]:
            raise ValueError("Metric and block symbols differ.")
        if _parse_timestamp(metric["prediction_as_of_utc"]) != observation_time:
            raise ValueError("Metric and block observation cutoffs differ.")
    if not isinstance(payload["disagreement"], list) or payload["disagreement"]:
        raise ValueError("Wave 4D.3 disagreement evidence must remain empty.")
    if payload["not_trade_command"] is not True or payload[
        "not_financial_advice"
    ] is not True:
        raise ValueError("Derivatives safety assertions are required.")


def _require_fields(value: Mapping[str, Any], fields: tuple[str, ...]) -> None:
    missing = [field for field in fields if field not in value]
    if missing:
        raise KeyError(missing[0])


def _required_text(value: Mapping[str, Any], key: str) -> str:
    result = value[key]
    if not isinstance(result, str) or not result.strip():
        raise ValueError(f"{key} must be a non-empty string.")
    return result


def _nonnegative_int(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("Count must be a non-negative integer.")
    return value


def _optional_finite_number(value: Any, *, nonnegative: bool = False) -> None:
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError("Evidence value must be numeric or null.")
    if not isfinite(float(value)) or (nonnegative and float(value) < 0):
        raise ValueError("Evidence value must be finite.")


def _required_timestamp(value: Mapping[str, Any], key: str) -> datetime:
    return _parse_timestamp(value[key])


def _parse_timestamp(value: Any) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Timestamp must be a non-empty string.")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("Timestamp must include a timezone.")
    return parsed.astimezone(UTC)


def _iso_utc(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
