"""Deterministic, downstream-only Quant V2 shadow evidence contract."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from math import isfinite
from typing import Any

from crypto_probability_engine.adapters.types import MarketSnapshot
from crypto_probability_engine.config.defaults import (
    DEFAULT_PHASE1A,
    FEATURE_METHODOLOGY_VERSION,
    TIMEFRAME_SECONDS,
)

SCHEMA_VERSION = "quant_v2.0"
INFLUENCE_MODE = "SHADOW_ONLY"
SAFETY_COPY = (
    "Shadow diagnostics — evidence only, not used in the decision yet. "
    "Not a trade command. Not financial advice. Not profitability evidence. Not accuracy."
)


@dataclass(frozen=True)
class _FeatureSpec:
    feature_name: str
    feature_id: str
    family: str
    upstream_key: str
    raw_key: str
    required_candles: int


@dataclass(frozen=True)
class _TimestampEvidence:
    computed_at: str | None
    reference_close: str | None
    input_start: str | None
    input_end: str | None
    staleness_seconds: float | None
    no_lookahead: bool
    reason: str | None
    candle_count: int
    stale: bool
    timeframe_supported: bool


# These history requirements mirror the existing audited feature implementations:
# volatility/regime need one return, trend needs H_extended + 1 closes, and volume
# anomaly needs its existing 20-bar baseline plus the current candle.
_FEATURE_SPECS = (
    _FeatureSpec(
        "Realized volatility",
        "quant_v2.realized_volatility",
        "VOLATILITY",
        "volatility",
        "realized_vol",
        2,
    ),
    _FeatureSpec(
        "Multi-timeframe trend",
        "quant_v2.trend_mtf",
        "TREND",
        "trend_mtf",
        "label",
        DEFAULT_PHASE1A.h_extended_bars + 1,
    ),
    _FeatureSpec(
        "Volume anomaly",
        "quant_v2.volume_anomaly",
        "VOLUME",
        "volume_anomaly",
        "volume_ratio",
        21,
    ),
    _FeatureSpec(
        "Regime state",
        "quant_v2.regime_2state",
        "REGIME",
        "regime_2state",
        "regime",
        2,
    ),
)


def build_quant_v2_shadow(
    *,
    quant_result: dict,
    snapshot: MarketSnapshot,
    provider_state: dict,
    symbol: str,
    normalized_symbol: str,
    timeframe: str,
    enabled: bool = True,
) -> dict:
    """Mirror existing feature outputs without recomputation, mutation, or I/O."""

    quant_result = quant_result if isinstance(quant_result, dict) else {}
    provider_state = provider_state if isinstance(provider_state, dict) else {}
    evidence = _timestamp_evidence(snapshot, timeframe)
    if not enabled:
        return _build_block(
            status="DISABLED",
            evidence=evidence,
            symbol=symbol,
            normalized_symbol=normalized_symbol,
            timeframe=timeframe,
            features=[],
        )

    features: list[dict] = []
    market_features = quant_result.get("market_features")
    if not isinstance(market_features, dict):
        market_features = {}
    for spec in _FEATURE_SPECS:
        try:
            features.append(
                _build_feature(
                    spec=spec,
                    market_features=market_features,
                    snapshot=snapshot,
                    provider_state=provider_state,
                    symbol=normalized_symbol or symbol,
                    timeframe=timeframe,
                    evidence=evidence,
                )
            )
        except Exception:
            features.append(
                _compute_error_feature(
                    spec=spec,
                    snapshot=snapshot,
                    provider_state=provider_state,
                    symbol=normalized_symbol or symbol,
                    timeframe=timeframe,
                    evidence=evidence,
                )
            )

    status = (
        "ACTIVE"
        if evidence.no_lookahead and all(item["status"] == "VALID" for item in features)
        else "DEGRADED"
    )
    return _build_block(
        status=status,
        evidence=evidence,
        symbol=symbol,
        normalized_symbol=normalized_symbol,
        timeframe=timeframe,
        features=features,
    )


def _build_block(
    *,
    status: str,
    evidence: _TimestampEvidence,
    symbol: str,
    normalized_symbol: str,
    timeframe: str,
    features: list[dict],
) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "influence_mode": INFLUENCE_MODE,
        "feature_methodology_version": FEATURE_METHODOLOGY_VERSION,
        "computed_at_utc": evidence.computed_at,
        "symbol": symbol,
        "normalized_symbol": normalized_symbol,
        "timeframe": timeframe,
        "reference_close_utc": evidence.reference_close,
        "input_staleness_seconds": evidence.staleness_seconds,
        "no_lookahead_assertion": evidence.no_lookahead,
        "feature_count": len(features),
        "degraded_count": sum(item["status"] != "VALID" for item in features),
        "features": features,
        "plain_english": SAFETY_COPY,
        "not_trade_command": True,
        "not_financial_advice": True,
    }


def _build_feature(
    *,
    spec: _FeatureSpec,
    market_features: dict,
    snapshot: MarketSnapshot,
    provider_state: dict,
    symbol: str,
    timeframe: str,
    evidence: _TimestampEvidence,
) -> dict:
    upstream = market_features.get(spec.upstream_key)
    upstream_status = upstream.get("status") if isinstance(upstream, dict) else None
    raw_value = _extract_raw_value(spec, upstream)
    source_provider = _source_provider(snapshot, provider_state)
    snapshot_status = _snapshot_source_status(snapshot)
    provider_status = _optional_text(provider_state.get("status"))
    status, reason = _feature_status(
        spec=spec,
        upstream=upstream,
        upstream_status=upstream_status,
        raw_value=raw_value,
        source_provider=source_provider,
        snapshot_status=snapshot_status,
        provider_status=provider_status,
        evidence=evidence,
    )
    direction_hint = None
    if spec.family == "TREND" and raw_value in {"UP", "DOWN", "SIDEWAYS"}:
        direction_hint = raw_value
    return _feature_payload(
        spec=spec,
        symbol=symbol,
        timeframe=timeframe,
        source_provider=source_provider,
        upstream_status=_optional_text(upstream_status),
        snapshot_status=snapshot_status,
        provider_status=provider_status,
        raw_value=raw_value if _valid_raw_value(raw_value) else None,
        direction_hint=direction_hint,
        status=status,
        reason=reason,
        evidence=evidence,
    )


def _compute_error_feature(
    *,
    spec: _FeatureSpec,
    snapshot: MarketSnapshot,
    provider_state: dict,
    symbol: str,
    timeframe: str,
    evidence: _TimestampEvidence,
) -> dict:
    return _feature_payload(
        spec=spec,
        symbol=symbol,
        timeframe=timeframe,
        source_provider=_source_provider(snapshot, provider_state),
        upstream_status=None,
        snapshot_status=_snapshot_source_status(snapshot),
        provider_status=_optional_text(provider_state.get("status")),
        raw_value=None,
        direction_hint=None,
        status="COMPUTE_ERROR",
        reason="Existing upstream feature could not be mirrored safely.",
        evidence=evidence,
    )


def _feature_payload(
    *,
    spec: _FeatureSpec,
    symbol: str,
    timeframe: str,
    source_provider: str | None,
    upstream_status: str | None,
    snapshot_status: str | None,
    provider_status: str | None,
    raw_value: float | str | None,
    direction_hint: str | None,
    status: str,
    reason: str | None,
    evidence: _TimestampEvidence,
) -> dict:
    detail = f"Read from quant_result.market_features.{spec.upstream_key} without recomputation."
    if reason:
        detail = f"{detail} {reason}"
    return {
        "feature_name": spec.feature_name,
        "feature_id": f"{spec.feature_id}:{timeframe}",
        "family": spec.family,
        "timeframe": timeframe,
        "symbol": symbol,
        "source_provider": source_provider,
        "source_priority": _source_priority(source_provider),
        "lookback": spec.required_candles,
        "candle_count": evidence.candle_count,
        "computed_at": evidence.computed_at,
        "input_start_time": evidence.input_start,
        "input_end_time": evidence.input_end,
        "input_staleness_seconds": evidence.staleness_seconds,
        "status": status,
        "reason_if_invalid": reason,
        "raw_value": raw_value,
        "normalized_value": None,
        "bucket": None,
        "direction_hint": direction_hint,
        "confidence_hint": None,
        "risk_hint": None,
        "explanation_short": "Existing feature mirrored for shadow diagnostics.",
        "explanation_detail": detail,
        "influence_mode": INFLUENCE_MODE,
        "methodology_version": FEATURE_METHODOLOGY_VERSION,
        "data_quality": {
            "upstream_status": upstream_status,
            "provider_state_status": provider_status,
            "snapshot_source_status": snapshot_status,
            "timestamp_evidence_complete": evidence.no_lookahead,
        },
        "no_lookahead_assertion": evidence.no_lookahead,
    }


def _feature_status(
    *,
    spec: _FeatureSpec,
    upstream: Any,
    upstream_status: Any,
    raw_value: Any,
    source_provider: str | None,
    snapshot_status: str | None,
    provider_status: str | None,
    evidence: _TimestampEvidence,
) -> tuple[str, str | None]:
    if not evidence.timeframe_supported:
        return "NOT_APPLICABLE", "No existing freshness rule applies to this timeframe."
    if evidence.candle_count < spec.required_candles:
        return (
            "INSUFFICIENT_HISTORY",
            f"Existing feature requires at least {spec.required_candles} closed candles.",
        )
    if not evidence.no_lookahead:
        return "COMPUTE_ERROR", evidence.reason or "Timestamp evidence is incomplete."
    if evidence.stale:
        return "STALE_INPUT", "Snapshot exceeds the existing timeframe freshness budget."
    if not source_provider:
        return "PROVIDER_UNAVAILABLE", "Snapshot provider provenance is unavailable."
    unavailable_states = {"UNAVAILABLE", "QUARANTINED"}
    if snapshot_status in unavailable_states or provider_status in unavailable_states:
        return "PROVIDER_UNAVAILABLE", "Source provider is unavailable for this snapshot."
    if not isinstance(upstream, dict):
        return "COMPUTE_ERROR", "Existing upstream feature is missing or malformed."
    if not _valid_raw_value(raw_value):
        return "COMPUTE_ERROR", "Existing upstream feature value is missing or non-finite."
    if upstream_status != "OK":
        return "DEGRADED", "Existing upstream feature reports a degraded status."
    degraded_states = {"DEGRADED", "TO_VERIFY"}
    if snapshot_status in degraded_states or provider_status in degraded_states:
        return "DEGRADED", "Provider metadata reports a degraded source state."
    return "VALID", None


def _extract_raw_value(spec: _FeatureSpec, upstream: Any) -> Any:
    if not isinstance(upstream, dict):
        return None
    return upstream.get(spec.raw_key)


def _valid_raw_value(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return isfinite(float(value))
    return isinstance(value, str) and bool(value.strip())


def _timestamp_evidence(snapshot: MarketSnapshot, timeframe: str) -> _TimestampEvidence:
    candles = tuple(getattr(snapshot, "candles", ()) or ())
    as_of = _utc_datetime(getattr(snapshot, "as_of_utc", None))
    computed_at = _iso_utc(as_of)
    timeframe_supported = timeframe in TIMEFRAME_SECONDS
    if not candles:
        return _TimestampEvidence(
            computed_at=computed_at,
            reference_close=None,
            input_start=None,
            input_end=None,
            staleness_seconds=None,
            no_lookahead=False,
            reason="No closed candle is available for timestamp evidence.",
            candle_count=0,
            stale=False,
            timeframe_supported=timeframe_supported,
        )

    opens = [_utc_datetime(getattr(candle, "open_time_utc", None)) for candle in candles]
    closes = [_utc_datetime(getattr(candle, "close_time_utc", None)) for candle in candles]
    input_start = _iso_utc(opens[0]) if opens else None
    input_end = _iso_utc(closes[-1]) if closes else None
    reference_close = input_end
    timestamps_complete = as_of is not None and all(opens) and all(closes)
    ordered = bool(
        timestamps_complete
        and all(opened < closed for opened, closed in zip(opens, closes, strict=True))
        and all(
            left_close <= right_open
            for left_close, right_open in zip(closes, opens[1:], strict=False)
        )
    )
    no_future_close = bool(timestamps_complete and all(closed <= as_of for closed in closes))
    no_lookahead = bool(timestamps_complete and ordered and no_future_close)
    reason = None
    if not timestamps_complete:
        reason = "Candle or snapshot timestamps are missing or not timezone-aware."
    elif not ordered:
        reason = "Candle input window boundaries are not ordered."
    elif not no_future_close:
        reason = "A candle closes after the prediction-time snapshot."

    staleness_seconds = None
    stale = False
    if no_lookahead and closes[-1] is not None and as_of is not None:
        staleness_seconds = (as_of - closes[-1]).total_seconds()
        if timeframe_supported:
            stale = (
                staleness_seconds
                > TIMEFRAME_SECONDS[timeframe] * DEFAULT_PHASE1A.freshness_multiplier
            )
    return _TimestampEvidence(
        computed_at=computed_at,
        reference_close=reference_close,
        input_start=input_start,
        input_end=input_end,
        staleness_seconds=staleness_seconds,
        no_lookahead=no_lookahead,
        reason=reason,
        candle_count=len(candles),
        stale=stale,
        timeframe_supported=timeframe_supported,
    )


def _utc_datetime(value: Any) -> datetime | None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        return None
    return value.astimezone(UTC)


def _iso_utc(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat().replace("+00:00", "Z")


def _source_provider(snapshot: MarketSnapshot, provider_state: dict) -> str | None:
    snapshot_provider = _optional_text(getattr(snapshot, "provider", None))
    return snapshot_provider or _optional_text(provider_state.get("active_provider"))


def _snapshot_source_status(snapshot: MarketSnapshot) -> str | None:
    value = getattr(snapshot, "source_status", None)
    return _optional_text(getattr(value, "value", value))


def _source_priority(provider: str | None) -> int | None:
    if not provider:
        return None
    normalized = provider.lower()
    try:
        return DEFAULT_PHASE1A.provider_priority.index(normalized) + 1
    except ValueError:
        return None


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
