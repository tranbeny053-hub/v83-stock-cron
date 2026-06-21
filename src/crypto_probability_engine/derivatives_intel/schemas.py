"""Strict Python contracts for raw derivatives evidence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any


class DerivativesFamily(StrEnum):
    FUNDING = "FUNDING"
    OPEN_INTEREST = "OPEN_INTEREST"


class DerivativesMetricStatus(StrEnum):
    VALID = "VALID"
    INSUFFICIENT_HISTORY = "INSUFFICIENT_HISTORY"
    STALE_INPUT = "STALE_INPUT"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    UNSUPPORTED_INSTRUMENT = "UNSUPPORTED_INSTRUMENT"
    CONTRACT_MISMATCH = "CONTRACT_MISMATCH"
    INSTRUMENT_INACTIVE = "INSTRUMENT_INACTIVE"
    PARTIAL_INTERVAL = "PARTIAL_INTERVAL"
    INVALID_UNIT = "INVALID_UNIT"
    COMPUTE_ERROR = "COMPUTE_ERROR"
    DEGRADED = "DEGRADED"


class DerivativesUnit(StrEnum):
    FRACTION_PER_INTERVAL = "FRACTION_PER_INTERVAL"
    PROVIDER_NATIVE_CONTRACT_QUANTITY = "PROVIDER_NATIVE_CONTRACT_QUANTITY"
    USDT_NOTIONAL = "USDT_NOTIONAL"
    CONTRACTS = "CONTRACTS"
    BASE_ASSET_QUANTITY = "BASE_ASSET_QUANTITY"
    USD_NOTIONAL = "USD_NOTIONAL"


@dataclass(frozen=True)
class DerivativesMetric:
    metric_id: str
    family: DerivativesFamily
    provider: str
    provider_endpoint: str
    provider_instrument: str
    normalized_symbol: str
    contract_type: str
    margin_asset: str
    settlement_asset: str
    timeframe_or_period: str | None
    event_time: datetime | None
    interval_start: datetime | None
    interval_end: datetime | None
    interval_final: bool
    fetched_at_utc: datetime
    prediction_as_of_utc: datetime
    input_staleness_seconds: float | None
    status: DerivativesMetricStatus
    reason_if_invalid: str | None
    raw_value: float | None
    normalized_value: None
    bucket: None
    direction_hint: None
    confidence_hint: None
    risk_hint: None
    unit: DerivativesUnit
    source_count: int
    provider_priority: int
    influence_mode: str
    methodology_version: str
    no_lookahead_assertion: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "metric_id": self.metric_id,
            "family": self.family.value,
            "provider": self.provider,
            "provider_endpoint": self.provider_endpoint,
            "provider_instrument": self.provider_instrument,
            "normalized_symbol": self.normalized_symbol,
            "contract_type": self.contract_type,
            "margin_asset": self.margin_asset,
            "settlement_asset": self.settlement_asset,
            "timeframe_or_period": self.timeframe_or_period,
            "event_time": _timestamp(self.event_time),
            "interval_start": _timestamp(self.interval_start),
            "interval_end": _timestamp(self.interval_end),
            "interval_final": self.interval_final,
            "fetched_at_utc": _timestamp(self.fetched_at_utc),
            "prediction_as_of_utc": _timestamp(self.prediction_as_of_utc),
            "input_staleness_seconds": self.input_staleness_seconds,
            "status": self.status.value,
            "reason_if_invalid": self.reason_if_invalid,
            "raw_value": self.raw_value,
            "normalized_value": None,
            "bucket": None,
            "direction_hint": None,
            "confidence_hint": None,
            "risk_hint": None,
            "unit": self.unit.value,
            "source_count": self.source_count,
            "provider_priority": self.provider_priority,
            "influence_mode": self.influence_mode,
            "methodology_version": self.methodology_version,
            "no_lookahead_assertion": self.no_lookahead_assertion,
        }


def _timestamp(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None
