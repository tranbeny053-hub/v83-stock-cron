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
class MarketSnapshot:
    provider: str
    normalized_symbol: str
    timeframe: str
    candles: tuple[MarketCandle, ...]
    order_book: OrderBookSnapshot | None
    as_of_utc: datetime
    source_status: ProviderStatus = ProviderStatus.TO_VERIFY
    warnings: tuple[str, ...] = ()


@dataclass
class ProviderState:
    name: str
    status: ProviderStatus = ProviderStatus.TO_VERIFY
    quarantine_reason: str | None = None
    warnings: list[str] = field(default_factory=list)

    def to_public_dict(self) -> dict:
        return {
            "name": self.name,
            "status": self.status.value,
            "quarantine_reason": self.quarantine_reason,
            "warnings": list(self.warnings),
        }


class ProviderError(RuntimeError):
    """Typed provider failure with a stable, API-facing code."""

    def __init__(self, code: str, message: str, *, provider: str) -> None:
        super().__init__(message)
        self.code = code
        self.provider = provider
        self.message = message

