"""NewsAPI metadata adapter."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any

from crypto_probability_engine.adapters.http_client import PublicHttpClient
from crypto_probability_engine.adapters.types import ProviderError
from crypto_probability_engine.config.settings import Settings
from crypto_probability_engine.news.adapters.common import (
    NewsProviderError,
    compact_item,
    provider_error_to_news,
)
from crypto_probability_engine.news.models import MacroObservation, NewsItem

NEWSAPI_BASE_URL = "https://newsapi.org"
NEWSAPI_OPERATION = "GET /v2/everything"


class NewsApiAdapter:
    name = "newsapi"

    def __init__(self, *, settings: Settings, http_client: PublicHttpClient | None = None) -> None:
        self.settings = settings
        self.http_client = http_client or PublicHttpClient(
            timeout_seconds=settings.news_timeout_seconds,
            max_retries=settings.provider_max_retries,
            rate_limit_per_min=settings.provider_rate_limit_per_min,
        )
        self.last_diagnostics: dict = _empty_diagnostics(configured=self.is_configured())

    def is_configured(self) -> bool:
        return bool(self.settings.newsapi_key)

    def fetch_macro_observations(self) -> tuple[MacroObservation, ...]:
        return ()

    def fetch_items(self, symbol: str) -> tuple[NewsItem, ...]:
        if not self.settings.newsapi_key:
            self.last_diagnostics = _empty_diagnostics(configured=False)
            return ()
        fetched_at = datetime.now(UTC)
        start = time.perf_counter()
        try:
            payload = self.http_client.get_json(
                base_url=NEWSAPI_BASE_URL,
                path="/v2/everything",
                params={
                    "q": _query_for_symbol(symbol),
                    "searchIn": "title,description",
                    "language": "en",
                    "sortBy": "publishedAt",
                    "pageSize": self.settings.news_item_limit,
                    "page": 1,
                },
                provider=self.name,
                headers={"X-Api-Key": self.settings.newsapi_key},
            )
        except ProviderError as exc:
            error = provider_error_to_news(exc, provider=self.name, operation=NEWSAPI_OPERATION)
            self.last_diagnostics = _failure_status(error, latency_ms=_latency_ms(start))
            raise error from exc
        try:
            items = parse_newsapi_items(payload, fetched_at=fetched_at)
        except NewsProviderError as exc:
            self.last_diagnostics = _failure_status(exc, latency_ms=_latency_ms(start))
            raise
        self.last_diagnostics = {
            "provider": self.name,
            "configured": True,
            "healthy": True,
            "status": "OK",
            "item_count": len(items),
            "macro_observation_count": 0,
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
        return items


def parse_newsapi_items(payload: Any, *, fetched_at: datetime) -> tuple[NewsItem, ...]:
    if isinstance(payload, dict) and payload.get("status") == "error":
        provider_code = str(payload.get("code") or "NEWSAPI_ERROR")
        error_type = _newsapi_error_type(provider_code)
        raise NewsProviderError(
            "PROVIDER_DEGRADED",
            _newsapi_warning(provider_code),
            provider="newsapi",
            error_code=provider_code,
            error_type=error_type,
            operation=NEWSAPI_OPERATION,
        )
    if not isinstance(payload, dict) or payload.get("status") not in {None, "ok"}:
        raise NewsProviderError(
            "SCHEMA_VALIDATION_FAILED",
            "NewsAPI payload is invalid.",
            provider="newsapi",
        )
    rows = payload.get("articles")
    if not isinstance(rows, list):
        return ()
    items: list[NewsItem] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        source = row.get("source") if isinstance(row.get("source"), dict) else {}
        item = compact_item(
            provider="newsapi",
            source_name=str(source.get("name") or "NewsAPI"),
            title=row.get("title"),
            snippet=row.get("description"),
            url=row.get("url"),
            fetched_at=fetched_at,
            published_at=row.get("publishedAt"),
            language="en",
        )
        if item is not None:
            items.append(item)
    return tuple(items)


def _query_for_symbol(symbol: str) -> str:
    base = symbol.split("/", maxsplit=1)[0].upper()
    aliases = {
        "BTC": '(bitcoin OR BTC OR XBT)',
        "ETH": '(ethereum OR ETH OR ether)',
        "SOL": '(solana OR SOL)',
        "USDT": '(tether OR USDT OR stablecoin)',
    }
    asset = aliases.get(base, f"({base})")
    return f"{asset} OR (Federal Reserve OR CPI OR inflation OR SEC OR ETF OR dollar OR yields)"


def _empty_diagnostics(*, configured: bool) -> dict:
    return {
        "provider": "newsapi",
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
    warning = _newsapi_warning(error.error_code)
    return {
        "provider": "newsapi",
        "configured": True,
        "healthy": False,
        "status": "UNAVAILABLE",
        "item_count": 0,
        "macro_observation_count": 0,
        "last_failure_http_status": error.http_status,
        "last_failure_error_code": error.error_code,
        "last_failure_error_type": error.error_type,
        "last_failure_operation": error.operation or NEWSAPI_OPERATION,
        "last_failure_at_utc": error.failure_at_utc,
        "retry_after_seconds": error.retry_after_seconds,
        "cache_status": "BYPASS",
        "latency_ms": latency_ms,
        "warnings": [warning],
    }


def _newsapi_error_type(provider_code: str | None) -> str:
    if provider_code in {"apiKeyInvalid", "apiKeyMissing"}:
        return "AUTH"
    if provider_code in {"rateLimited"}:
        return "RATE_LIMIT"
    if provider_code in {"parameterInvalid", "parametersMissing"}:
        return "REQUEST"
    return "PROVIDER"


def _newsapi_warning(provider_code: str | None) -> str:
    if provider_code == "apiKeyInvalid":
        return "newsapi: api key invalid or inactive"
    if provider_code == "rateLimited":
        return "newsapi: rate limited"
    if provider_code == "parameterInvalid":
        return "newsapi: parameter invalid"
    return "newsapi: provider unavailable"


def _latency_ms(start: float) -> float:
    return round((time.perf_counter() - start) * 1000.0, 3)
