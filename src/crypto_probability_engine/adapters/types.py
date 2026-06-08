"""Typed public market-data objects used by adapters and validators."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum


class ProviderStatus(StrEnum):
    OK = "OK"
    DEGRADED = "DEGRADED"
    QUARANTINED = "QUARANTINED"
    TO_VERIFY = "TO_VERIFY"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True)
class MarketCandle:
    open_time_utc: datetime
    close_time_utc: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True)
class OrderBookLevel:
    price: float
    size: float


@dataclass(frozen=True)
class OrderBookSnapshot:
    bids: tuple[OrderBookLevel, ...]
    asks: tuple[OrderBookLevel, ...]
    as_of_utc: datetime


@dataclass(frozen=True)
class MarketTicker:
    provider: str
    last_price: float
    bid_price: float | None
    ask_price: float | None
    base_volume_24h: float | None
    quote_volume_24h: float | None
    as_of_utc: datetime


@dataclass(frozen=True)
class RecentTrade:
    provider: str
    price: float
    size: float
    side: str | None
    timestamp_utc: datetime


@dataclass(frozen=True)
class MarketSnapshot:
    provider: str
    normalized_symbol: str
    timeframe: str
    candles: tuple[MarketCandle, ...]
    order_book: OrderBookSnapshot | None
    as_of_utc: datetime
    source_status: ProviderStatus = ProviderStatus.TO_VERIFY
    warnings: tuple[str, ...] = ()
    ticker: MarketTicker | None = None
    recent_trades: tuple[RecentTrade, ...] = ()
    resource_statuses: dict[str, dict] = field(default_factory=dict)
    derived_metrics: dict[str, dict] = field(default_factory=dict)


@dataclass
class ProviderState:
    name: str
    status: ProviderStatus = ProviderStatus.TO_VERIFY
    quarantine_reason: str | None = None
    warnings: list[str] = field(default_factory=list)
    resources: dict[str, dict] = field(default_factory=dict)
    derived_metrics: dict[str, dict] = field(default_factory=dict)

    def to_public_dict(self) -> dict:
        return {
            "name": self.name,
            "status": self.status.value,
            "quarantine_reason": self.quarantine_reason,
            "warnings": list(self.warnings),
            "resources": dict(self.resources),
            "derived_metrics": dict(self.derived_metrics),
        }


class ProviderError(RuntimeError):
    """Typed provider failure with a stable, API-facing code."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        provider: str,
        http_status: int | None = None,
        error_code: str | None = None,
        error_type: str | None = None,
        retry_after_seconds: float | None = None,
        operation: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.provider = provider
        self.message = message
        self.http_status = http_status
        self.error_code = error_code
        self.error_type = error_type
        self.retry_after_seconds = retry_after_seconds
        self.operation = operation
