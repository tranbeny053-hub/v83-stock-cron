"""FRED macro observations adapter."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from crypto_probability_engine.adapters.http_client import PublicHttpClient
from crypto_probability_engine.adapters.types import ProviderError
from crypto_probability_engine.config.settings import Settings
from crypto_probability_engine.news.adapters.common import NewsProviderError, fred_observation
from crypto_probability_engine.news.models import MacroObservation, NewsItem

FRED_BASE_URL = "https://api.stlouisfed.org"
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

    def is_configured(self) -> bool:
        return bool(self.settings.fred_api_key)

    def fetch_items(self, symbol: str) -> tuple[NewsItem, ...]:
        return ()

    def fetch_macro_observations(self) -> tuple[MacroObservation, ...]:
        if not self.settings.fred_api_key:
            return ()
        fetched_at = datetime.now(UTC)
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
                raise NewsProviderError(exc.code, exc.message, provider=self.name) from exc
            observations.extend(
                parse_fred_observations(
                    payload,
                    series_id=series_id,
                    label=label,
                    fetched_at=fetched_at,
                )
            )
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
