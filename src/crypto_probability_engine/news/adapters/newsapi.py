"""NewsAPI metadata adapter."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from crypto_probability_engine.adapters.http_client import PublicHttpClient
from crypto_probability_engine.adapters.types import ProviderError
from crypto_probability_engine.config.settings import Settings
from crypto_probability_engine.news.adapters.common import NewsProviderError, compact_item
from crypto_probability_engine.news.models import MacroObservation, NewsItem

NEWSAPI_BASE_URL = "https://newsapi.org"


class NewsApiAdapter:
    name = "newsapi"

    def __init__(self, *, settings: Settings, http_client: PublicHttpClient | None = None) -> None:
        self.settings = settings
        self.http_client = http_client or PublicHttpClient(
            timeout_seconds=settings.news_timeout_seconds,
            max_retries=settings.provider_max_retries,
            rate_limit_per_min=settings.provider_rate_limit_per_min,
        )

    def is_configured(self) -> bool:
        return bool(self.settings.newsapi_key)

    def fetch_macro_observations(self) -> tuple[MacroObservation, ...]:
        return ()

    def fetch_items(self, symbol: str) -> tuple[NewsItem, ...]:
        if not self.settings.newsapi_key:
            return ()
        fetched_at = datetime.now(UTC)
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
            raise NewsProviderError(exc.code, exc.message, provider=self.name) from exc
        return parse_newsapi_items(payload, fetched_at=fetched_at)


def parse_newsapi_items(payload: Any, *, fetched_at: datetime) -> tuple[NewsItem, ...]:
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
