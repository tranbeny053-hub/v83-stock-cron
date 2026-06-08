"""FRED macro observations adapter."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any

from crypto_probability_engine.adapters.http_client import PublicHttpClient
from crypto_probability_engine.adapters.types import ProviderError
from crypto_probability_engine.config.settings import Settings
from crypto_probability_engine.news.adapters.common import (
    NewsProviderError,
    fred_observation,
    provider_error_to_news,
)
from crypto_probability_engine.news.models import MacroObservation, NewsItem

FRED_BASE_URL = "https://api.stlouisfed.org"
FRED_OPERATION = "GET /fred/series/observations"
FRED_SERIES = {
    "CPIAUCSL": "Consumer Price Index",
    "FEDFUNDS": "Effective Federal Funds Rate",
    "DGS10": "10-Year Treasury Constant Maturity",
    "DTWEXBGS": "Broad Dollar Index",
}


class FredMacroAdapter:
    name = "fred"

    def __init__(self, *, settings: Settings, http_client: PublicHttpClient | None = None) -> None:
        self.settings = settings
        self.http_client = http_client or PublicHttpClient(
            timeout_seconds=settings.news_timeout_seconds,
            max_retries=settings.provider_max_retries,
            rate_limit_per_min=settings.provider_rate_limit_per_min,
        )
        self.last_diagnostics: dict = _empty_diagnostics(configured=self.is_configured())

    def is_configured(self) -> bool:
        return bool(self.settings.fred_api_key)

    def fetch_items(self, symbol: str) -> tuple[NewsItem, ...]:
        return ()

    def fetch_macro_observations(self) -> tuple[MacroObservation, ...]:
        if not self.settings.fred_api_key:
            self.last_diagnostics = _empty_diagnostics(configured=False)
            return ()
        fetched_at = datetime.now(UTC)
        start = time.perf_counter()
        observations: list[MacroObservation] = []
        for series_id, label in FRED_SERIES.items():
            try:
                payload = self.http_client.get_json(
                    base_url=FRED_BASE_URL,
                    path="/fred/series/observations",
                    params={
                        "series_id": series_id,
                        "api_key": self.settings.fred_api_key,
                        "file_type": "json",
                        "sort_order": "desc",
                        "limit": 1,
                    },
                    provider=self.name,
                )
            except ProviderError as exc:
                error = provider_error_to_news(exc, provider=self.name, operation=FRED_OPERATION)
                self.last_diagnostics = _failure_status(error, latency_ms=_latency_ms(start))
                raise error from exc
            observations.extend(
                parse_fred_observations(
                    payload,
                    series_id=series_id,
                    label=label,
                    fetched_at=fetched_at,
                )
            )
        self.last_diagnostics = {
            "provider": self.name,
            "configured": True,
            "healthy": True,
            "status": "OK",
            "item_count": 0,
            "macro_observation_count": len(observations),
            "last_failure_http_status": None,
            "last_failure_error_code": None,
            "last_failure_error_type": None,
            "last_failure_operation": None,
            "last_failure_at_utc": None,
            "retry_after_seconds": None,
            "cache_status": "BYPASS",
            "latency_ms": _latency_ms(start),
            "warnings": [],
        }
        return tuple(observations)


def parse_fred_observations(
    payload: Any,
    *,
    series_id: str,
    label: str,
    fetched_at: datetime,
) -> tuple[MacroObservation, ...]:
    if not isinstance(payload, dict) or not isinstance(payload.get("observations"), list):
        raise NewsProviderError(
            "SCHEMA_VALIDATION_FAILED",
            "FRED payload is invalid.",
            provider="fred",
        )
    for row in payload["observations"]:
        if isinstance(row, dict):
            return (
                fred_observation(
                    series_id=series_id,
                    label=label,
                    row=row,
                    fetched_at=fetched_at,
                ),
            )
    return ()


def _empty_diagnostics(*, configured: bool) -> dict:
    return {
        "provider": "fred",
        "configured": configured,
        "healthy": False,
        "status": "UNCONFIGURED" if not configured else "UNAVAILABLE",
        "item_count": 0,
        "macro_observation_count": 0,
        "last_failure_http_status": None,
        "last_failure_error_code": None,
        "last_failure_error_type": None,
        "last_failure_operation": None,
        "last_failure_at_utc": None,
        "retry_after_seconds": None,
        "cache_status": "BYPASS",
        "latency_ms": None,
        "warnings": [],
    }


def _failure_status(error: NewsProviderError, *, latency_ms: float | None) -> dict:
    return {
        "provider": "fred",
        "configured": True,
        "healthy": False,
        "status": "UNAVAILABLE",
        "item_count": 0,
        "macro_observation_count": 0,
        "last_failure_http_status": error.http_status,
        "last_failure_error_code": error.error_code,
        "last_failure_error_type": error.error_type,
        "last_failure_operation": error.operation or FRED_OPERATION,
        "last_failure_at_utc": error.failure_at_utc,
        "retry_after_seconds": error.retry_after_seconds,
        "cache_status": "BYPASS",
        "latency_ms": latency_ms,
        "warnings": ["fred: provider unavailable"],
    }


def _latency_ms(start: float) -> float:
    return round((time.perf_counter() - start) * 1000.0, 3)
