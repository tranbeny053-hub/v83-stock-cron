"""Pure provider-native derivatives metric provenance builders."""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta
from typing import Any

from crypto_probability_engine.derivatives_intel.instruments import (
    InstrumentResolution,
    InstrumentResolutionStatus,
)
from crypto_probability_engine.derivatives_intel.schemas import (
    DerivativesFamily,
    DerivativesMetric,
    DerivativesMetricStatus,
    DerivativesUnit,
)

INFLUENCE_MODE = "SHADOW_ONLY"
METHODOLOGY_VERSION = "deriv-intel-shadow-v0"
CURRENT_FUNDING_MAX_STALENESS_SECONDS = 3600
CURRENT_OPEN_INTEREST_MAX_STALENESS_SECONDS = 300
PROVIDER_PRIORITY = {"BINANCE_USDM": 1, "OKX_SWAP": 2}
PERIOD_SECONDS = {
    "5m": 300,
    "15m": 900,
    "30m": 1800,
    "1h": 3600,
    "2h": 7200,
    "4h": 14_400,
    "6h": 21_600,
    "12h": 43_200,
    "1d": 86_400,
}


def build_binance_current_funding_metric(
    payload: Any,
    resolution: InstrumentResolution,
    *,
    fetched_at_utc: datetime,
    prediction_as_of_utc: datetime,
) -> dict[str, Any]:
    return _build_current_metric(
        payload,
        resolution,
        metric_id="binance.funding.current_estimate",
        family=DerivativesFamily.FUNDING,
        endpoint="/fapi/v1/premiumIndex",
        raw_field="lastFundingRate",
        timestamp_field="time",
        unit=DerivativesUnit.FRACTION_PER_INTERVAL,
        fetched_at_utc=fetched_at_utc,
        prediction_as_of_utc=prediction_as_of_utc,
        max_staleness_seconds=CURRENT_FUNDING_MAX_STALENESS_SECONDS,
    )


def build_binance_settled_funding_metric(
    row: Any,
    resolution: InstrumentResolution,
    *,
    fetched_at_utc: datetime,
    prediction_as_of_utc: datetime,
) -> dict[str, Any]:
    return _build_historical_point_metric(
        row,
        resolution,
        metric_id="binance.funding.settled",
        family=DerivativesFamily.FUNDING,
        endpoint="/fapi/v1/fundingRate",
        raw_field="fundingRate",
        timestamp_field="fundingTime",
        unit=DerivativesUnit.FRACTION_PER_INTERVAL,
        fetched_at_utc=fetched_at_utc,
        prediction_as_of_utc=prediction_as_of_utc,
    )


def binance_funding_interval_from_info(rows: Any, symbol: str) -> str | None:
    """Return an explicit modified interval only; omitted symbols retain unknown/default."""
    if not isinstance(rows, list):
        return None
    row = next(
        (item for item in rows if isinstance(item, dict) and item.get("symbol") == symbol),
        None,
    )
    if row is None:
        return None
    value = row.get("fundingIntervalHours")
    if isinstance(value, int) and not isinstance(value, bool) and value > 0:
        return f"{value}h"
    return None


def build_binance_current_open_interest_metric(
    payload: Any,
    resolution: InstrumentResolution,
    *,
    fetched_at_utc: datetime,
    prediction_as_of_utc: datetime,
) -> dict[str, Any]:
    return _build_current_metric(
        payload,
        resolution,
        metric_id="binance.open_interest.current",
        family=DerivativesFamily.OPEN_INTEREST,
        endpoint="/fapi/v1/openInterest",
        raw_field="openInterest",
        timestamp_field="time",
        unit=DerivativesUnit.PROVIDER_NATIVE_CONTRACT_QUANTITY,
        fetched_at_utc=fetched_at_utc,
        prediction_as_of_utc=prediction_as_of_utc,
        max_staleness_seconds=CURRENT_OPEN_INTEREST_MAX_STALENESS_SECONDS,
    )


def build_binance_open_interest_history_metrics(
    row: Any,
    resolution: InstrumentResolution,
    *,
    period: str,
    fetched_at_utc: datetime,
    prediction_as_of_utc: datetime,
) -> list[dict[str, Any]]:
    return [
        _build_historical_bucket_metric(
            row,
            resolution,
            metric_id="binance.open_interest.history.quantity",
            endpoint="/futures/data/openInterestHist",
            raw_field="sumOpenInterest",
            unit=DerivativesUnit.PROVIDER_NATIVE_CONTRACT_QUANTITY,
            period=period,
            fetched_at_utc=fetched_at_utc,
            prediction_as_of_utc=prediction_as_of_utc,
        ),
        _build_historical_bucket_metric(
            row,
            resolution,
            metric_id="binance.open_interest.history.quote_value",
            endpoint="/futures/data/openInterestHist",
            raw_field="sumOpenInterestValue",
            unit=DerivativesUnit.USDT_NOTIONAL,
            period=period,
            fetched_at_utc=fetched_at_utc,
            prediction_as_of_utc=prediction_as_of_utc,
        ),
    ]


def build_okx_current_funding_metric(
    payload: Any,
    resolution: InstrumentResolution,
    *,
    fetched_at_utc: datetime,
    prediction_as_of_utc: datetime,
) -> dict[str, Any]:
    row = _first_okx_row(payload)
    return _build_current_metric(
        row,
        resolution,
        metric_id="okx.funding.current_estimate",
        family=DerivativesFamily.FUNDING,
        endpoint="/api/v5/public/funding-rate",
        raw_field="fundingRate",
        timestamp_field="ts",
        unit=DerivativesUnit.FRACTION_PER_INTERVAL,
        fetched_at_utc=fetched_at_utc,
        prediction_as_of_utc=prediction_as_of_utc,
        max_staleness_seconds=CURRENT_FUNDING_MAX_STALENESS_SECONDS,
    )


def build_okx_settled_funding_metric(
    row: Any,
    resolution: InstrumentResolution,
    *,
    fetched_at_utc: datetime,
    prediction_as_of_utc: datetime,
) -> dict[str, Any]:
    return _build_historical_point_metric(
        row,
        resolution,
        metric_id="okx.funding.settled",
        family=DerivativesFamily.FUNDING,
        endpoint="/api/v5/public/funding-rate-history",
        raw_field="fundingRate",
        timestamp_field="fundingTime",
        unit=DerivativesUnit.FRACTION_PER_INTERVAL,
        fetched_at_utc=fetched_at_utc,
        prediction_as_of_utc=prediction_as_of_utc,
    )


def build_okx_current_open_interest_metrics(
    payload: Any,
    resolution: InstrumentResolution,
    *,
    fetched_at_utc: datetime,
    prediction_as_of_utc: datetime,
) -> list[dict[str, Any]]:
    row = _first_okx_row(payload)
    definitions = (
        ("okx.open_interest.current.contracts", "oi", DerivativesUnit.CONTRACTS),
        ("okx.open_interest.current.base", "oiCcy", DerivativesUnit.BASE_ASSET_QUANTITY),
        ("okx.open_interest.current.usd", "oiUsd", DerivativesUnit.USD_NOTIONAL),
    )
    return [
        _build_current_metric(
            row,
            resolution,
            metric_id=metric_id,
            family=DerivativesFamily.OPEN_INTEREST,
            endpoint="/api/v5/public/open-interest",
            raw_field=field,
            timestamp_field="ts",
            unit=unit,
            fetched_at_utc=fetched_at_utc,
            prediction_as_of_utc=prediction_as_of_utc,
            max_staleness_seconds=CURRENT_OPEN_INTEREST_MAX_STALENESS_SECONDS,
        )
        for metric_id, field, unit in definitions
    ]


def build_provider_unavailable_metric(
    *,
    metric_id: str,
    family: DerivativesFamily,
    provider: str,
    endpoint: str,
    provider_instrument: str,
    normalized_symbol: str,
    unit: DerivativesUnit,
    fetched_at_utc: datetime,
    prediction_as_of_utc: datetime,
) -> dict[str, Any]:
    return _metric(
        metric_id=metric_id,
        family=family,
        provider=provider,
        endpoint=endpoint,
        provider_instrument=provider_instrument,
        normalized_symbol=normalized_symbol,
        contract_type="USDT_LINEAR_PERPETUAL",
        margin_asset="USDT",
        settlement_asset="USDT",
        timeframe_or_period=None,
        event_time=None,
        interval_start=None,
        interval_end=None,
        interval_final=True,
        fetched_at_utc=fetched_at_utc,
        prediction_as_of_utc=prediction_as_of_utc,
        input_staleness_seconds=None,
        status=DerivativesMetricStatus.PROVIDER_UNAVAILABLE,
        reason="Public provider resource was unavailable.",
        raw_value=None,
        unit=unit,
        no_lookahead=False,
    )


def _build_current_metric(
    payload: Any,
    resolution: InstrumentResolution,
    *,
    metric_id: str,
    family: DerivativesFamily,
    endpoint: str,
    raw_field: str,
    timestamp_field: str,
    unit: DerivativesUnit,
    fetched_at_utc: datetime,
    prediction_as_of_utc: datetime,
    max_staleness_seconds: int,
) -> dict[str, Any]:
    invalid = _resolution_status(resolution)
    raw_value = _finite_value(payload.get(raw_field)) if isinstance(payload, dict) else None
    event_time = (
        _millis_timestamp(payload.get(timestamp_field)) if isinstance(payload, dict) else None
    )
    status, reason, no_lookahead, staleness = _current_status(
        raw_value,
        event_time,
        fetched_at_utc,
        prediction_as_of_utc,
        max_staleness_seconds,
    )
    if _negative_quantity(raw_value, unit):
        status = DerivativesMetricStatus.INVALID_UNIT
        reason = "Provider quantity or notional must not be negative."
        raw_value = None
        no_lookahead = False
    if invalid is not None:
        status, reason = invalid
        raw_value = None
        no_lookahead = False
    return _metric_from_resolution(
        resolution,
        metric_id=metric_id,
        family=family,
        endpoint=endpoint,
        timeframe_or_period=None,
        event_time=event_time,
        interval_start=None,
        interval_end=None,
        interval_final=True,
        fetched_at_utc=fetched_at_utc,
        prediction_as_of_utc=prediction_as_of_utc,
        input_staleness_seconds=staleness,
        status=status,
        reason=reason,
        raw_value=raw_value,
        unit=unit,
        no_lookahead=no_lookahead,
    )


def _build_historical_point_metric(
    payload: Any,
    resolution: InstrumentResolution,
    *,
    metric_id: str,
    family: DerivativesFamily,
    endpoint: str,
    raw_field: str,
    timestamp_field: str,
    unit: DerivativesUnit,
    fetched_at_utc: datetime,
    prediction_as_of_utc: datetime,
) -> dict[str, Any]:
    raw_value = _finite_value(payload.get(raw_field)) if isinstance(payload, dict) else None
    event_time = (
        _millis_timestamp(payload.get(timestamp_field)) if isinstance(payload, dict) else None
    )
    status, reason, no_lookahead = _historical_status(
        raw_value, event_time, fetched_at_utc, prediction_as_of_utc
    )
    invalid = _resolution_status(resolution)
    if invalid is not None:
        status, reason = invalid
        raw_value = None
        no_lookahead = False
    return _metric_from_resolution(
        resolution,
        metric_id=metric_id,
        family=family,
        endpoint=endpoint,
        timeframe_or_period=None,
        event_time=event_time,
        interval_start=None,
        interval_end=None,
        interval_final=True,
        fetched_at_utc=fetched_at_utc,
        prediction_as_of_utc=prediction_as_of_utc,
        input_staleness_seconds=None,
        status=status,
        reason=reason,
        raw_value=raw_value,
        unit=unit,
        no_lookahead=no_lookahead,
    )


def _build_historical_bucket_metric(
    payload: Any,
    resolution: InstrumentResolution,
    *,
    metric_id: str,
    endpoint: str,
    raw_field: str,
    unit: DerivativesUnit,
    period: str,
    fetched_at_utc: datetime,
    prediction_as_of_utc: datetime,
) -> dict[str, Any]:
    raw_value = _finite_value(payload.get(raw_field)) if isinstance(payload, dict) else None
    interval_end = (
        _millis_timestamp(payload.get("timestamp")) if isinstance(payload, dict) else None
    )
    seconds = PERIOD_SECONDS.get(period)
    interval_start = interval_end - timedelta(seconds=seconds) if interval_end and seconds else None
    status, reason, no_lookahead = _historical_status(
        raw_value, interval_end, fetched_at_utc, prediction_as_of_utc
    )
    if _negative_quantity(raw_value, unit):
        status = DerivativesMetricStatus.INVALID_UNIT
        reason = "Provider quantity or notional must not be negative."
        raw_value = None
        no_lookahead = False
    interval_final = status == DerivativesMetricStatus.VALID
    if seconds is None:
        status = DerivativesMetricStatus.COMPUTE_ERROR
        reason = "Historical period is unsupported."
        no_lookahead = False
        interval_final = False
    elif (
        interval_end is not None
        and _is_utc(prediction_as_of_utc)
        and interval_end > prediction_as_of_utc
    ):
        status = DerivativesMetricStatus.PARTIAL_INTERVAL
        reason = "Historical interval extends beyond the prediction cutoff."
        no_lookahead = False
        interval_final = False
    invalid = _resolution_status(resolution)
    if invalid is not None:
        status, reason = invalid
        raw_value = None
        no_lookahead = False
        interval_final = False
    return _metric_from_resolution(
        resolution,
        metric_id=metric_id,
        family=DerivativesFamily.OPEN_INTEREST,
        endpoint=endpoint,
        timeframe_or_period=period,
        event_time=interval_end,
        interval_start=interval_start,
        interval_end=interval_end,
        interval_final=interval_final,
        fetched_at_utc=fetched_at_utc,
        prediction_as_of_utc=prediction_as_of_utc,
        input_staleness_seconds=None,
        status=status,
        reason=reason,
        raw_value=raw_value,
        unit=unit,
        no_lookahead=no_lookahead,
    )


def _current_status(
    raw_value: float | None,
    event_time: datetime | None,
    fetched_at_utc: datetime,
    prediction_as_of_utc: datetime,
    max_staleness_seconds: int,
) -> tuple[DerivativesMetricStatus, str | None, bool, float | None]:
    if raw_value is None:
        return (
            DerivativesMetricStatus.COMPUTE_ERROR,
            "Provider value is missing or non-finite.",
            False,
            None,
        )
    if not all(_is_utc(value) for value in (event_time, fetched_at_utc, prediction_as_of_utc)):
        return (
            DerivativesMetricStatus.COMPUTE_ERROR,
            "Timezone-aware UTC timestamps are required.",
            False,
            None,
        )
    assert event_time is not None
    if event_time > prediction_as_of_utc or fetched_at_utc > prediction_as_of_utc:
        return (
            DerivativesMetricStatus.DEGRADED,
            "Provider or fetch timestamp exceeds the prediction cutoff.",
            False,
            None,
        )
    staleness = (prediction_as_of_utc - event_time).total_seconds()
    if staleness > max_staleness_seconds:
        return (
            DerivativesMetricStatus.STALE_INPUT,
            "Current provider value exceeds its freshness threshold.",
            True,
            staleness,
        )
    return DerivativesMetricStatus.VALID, None, True, staleness


def _historical_status(
    raw_value: float | None,
    event_time: datetime | None,
    fetched_at_utc: datetime,
    prediction_as_of_utc: datetime,
) -> tuple[DerivativesMetricStatus, str | None, bool]:
    if raw_value is None:
        return (
            DerivativesMetricStatus.COMPUTE_ERROR,
            "Provider value is missing or non-finite.",
            False,
        )
    if not all(_is_utc(value) for value in (event_time, fetched_at_utc, prediction_as_of_utc)):
        return (
            DerivativesMetricStatus.COMPUTE_ERROR,
            "Timezone-aware UTC timestamps are required.",
            False,
        )
    assert event_time is not None
    if event_time > prediction_as_of_utc or fetched_at_utc > prediction_as_of_utc:
        return (
            DerivativesMetricStatus.DEGRADED,
            "Historical evidence exceeds the prediction cutoff.",
            False,
        )
    return DerivativesMetricStatus.VALID, None, True


def _resolution_status(
    resolution: InstrumentResolution,
) -> tuple[DerivativesMetricStatus, str] | None:
    mapping = {
        InstrumentResolutionStatus.UNSUPPORTED_INSTRUMENT: (
            DerivativesMetricStatus.UNSUPPORTED_INSTRUMENT
        ),
        InstrumentResolutionStatus.CONTRACT_MISMATCH: DerivativesMetricStatus.CONTRACT_MISMATCH,
        InstrumentResolutionStatus.INSTRUMENT_INACTIVE: DerivativesMetricStatus.INSTRUMENT_INACTIVE,
        InstrumentResolutionStatus.INVALID_SYMBOL: DerivativesMetricStatus.UNSUPPORTED_INSTRUMENT,
    }
    status = mapping.get(resolution.status)
    if status is None:
        return None
    return status, resolution.reason or "Provider instrument resolution failed."


def _metric_from_resolution(
    resolution: InstrumentResolution,
    **kwargs: Any,
) -> dict[str, Any]:
    return _metric(
        provider=resolution.provider,
        provider_instrument=resolution.candidate or "UNKNOWN",
        normalized_symbol=resolution.normalized_symbol,
        contract_type=resolution.contract_type or "UNKNOWN",
        margin_asset=resolution.margin_asset or "UNKNOWN",
        settlement_asset=resolution.settlement_asset or "UNKNOWN",
        **kwargs,
    )


def _metric(
    *,
    metric_id: str,
    family: DerivativesFamily,
    provider: str,
    endpoint: str,
    provider_instrument: str,
    normalized_symbol: str,
    contract_type: str,
    margin_asset: str,
    settlement_asset: str,
    timeframe_or_period: str | None,
    event_time: datetime | None,
    interval_start: datetime | None,
    interval_end: datetime | None,
    interval_final: bool,
    fetched_at_utc: datetime,
    prediction_as_of_utc: datetime,
    input_staleness_seconds: float | None,
    status: DerivativesMetricStatus,
    reason: str | None,
    raw_value: float | None,
    unit: DerivativesUnit,
    no_lookahead: bool,
) -> dict[str, Any]:
    if not _is_utc(fetched_at_utc) or not _is_utc(prediction_as_of_utc):
        raise ValueError("Caller timestamps must be timezone-aware UTC values.")
    return DerivativesMetric(
        metric_id=metric_id,
        family=family,
        provider=provider,
        provider_endpoint=endpoint,
        provider_instrument=provider_instrument,
        normalized_symbol=normalized_symbol,
        contract_type=contract_type,
        margin_asset=margin_asset,
        settlement_asset=settlement_asset,
        timeframe_or_period=timeframe_or_period,
        event_time=event_time,
        interval_start=interval_start,
        interval_end=interval_end,
        interval_final=interval_final,
        fetched_at_utc=fetched_at_utc,
        prediction_as_of_utc=prediction_as_of_utc,
        input_staleness_seconds=input_staleness_seconds,
        status=status,
        reason_if_invalid=reason,
        raw_value=raw_value,
        normalized_value=None,
        bucket=None,
        direction_hint=None,
        confidence_hint=None,
        risk_hint=None,
        unit=unit,
        source_count=1,
        provider_priority=PROVIDER_PRIORITY.get(provider, 99),
        influence_mode=INFLUENCE_MODE,
        methodology_version=METHODOLOGY_VERSION,
        no_lookahead_assertion=no_lookahead,
    ).to_dict()


def _first_okx_row(payload: Any) -> Any:
    rows = payload.get("data") if isinstance(payload, dict) else payload
    return rows[0] if isinstance(rows, list) and rows else None


def _finite_value(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _negative_quantity(raw_value: float | None, unit: DerivativesUnit) -> bool:
    return (
        raw_value is not None
        and raw_value < 0
        and unit != DerivativesUnit.FRACTION_PER_INTERVAL
    )


def _millis_timestamp(value: Any) -> datetime | None:
    if isinstance(value, bool):
        return None
    try:
        millis = int(value)
    except (TypeError, ValueError, OverflowError):
        return None
    try:
        return datetime.fromtimestamp(millis / 1000, tz=UTC)
    except (OSError, OverflowError, ValueError):
        return None


def _is_utc(value: datetime | None) -> bool:
    return value is not None and value.tzinfo is not None and value.utcoffset() == timedelta(0)
