"""GDELT DOC 2.0 metadata adapter."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from crypto_probability_engine.adapters.http_client import PublicHttpClient
from crypto_probability_engine.adapters.types import ProviderError
from crypto_probability_engine.config.settings import Settings
from crypto_probability_engine.news.adapters.common import NewsProviderError, compact_item
from crypto_probability_engine.news.models import MacroObservation, NewsItem

GDELT_BASE_URL = "https://api.gdeltproject.org"


class GdeltDocAdapter:
    name = "gdelt"

    def __init__(self, *, settings: Settings, http_client: PublicHttpClient | None = None) -> None:
        self.settings = settings
        self.http_client = http_client or PublicHttpClient(
            timeout_seconds=settings.news_timeout_seconds,
            max_retries=settings.provider_max_retries,
            rate_limit_per_min=settings.provider_rate_limit_per_min,
        )

    def is_configured(self) -> bool:
        return True

    def fetch_macro_observations(self) -> tuple[MacroObservation, ...]:
        return ()

    def fetch_items(self, symbol: str) -> tuple[NewsItem, ...]:
        fetched_at = datetime.now(UTC)
        query = _query_for_symbol(symbol)
        try:
            payload = self.http_client.get_json(
                base_url=GDELT_BASE_URL,
                path="/api/v2/doc/doc",
                params={
                    "format": "json",
                    "mode": "artlist",
                    "query": query,
                    "maxrecords": self.settings.news_item_limit,
                    "timespan": "24h",
                    "sort": "datedesc",
                },
                provider=self.name,
            )
        except ProviderError as exc:
            raise NewsProviderError(exc.code, exc.message, provider=self.name) from exc
        return parse_gdelt_items(payload, fetched_at=fetched_at)


def parse_gdelt_items(payload: Any, *, fetched_at: datetime) -> tuple[NewsItem, ...]:
    if not isinstance(payload, dict):
        raise NewsProviderError(
            "SCHEMA_VALIDATION_FAILED",
            "GDELT payload is invalid.",
            provider="gdelt",
        )
    rows = payload.get("articles")
    if not isinstance(rows, list):
        return ()
    items: list[NewsItem] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        item = compact_item(
            provider="gdelt",
            source_name=str(row.get("source") or row.get("domain") or "GDELT"),
            title=row.get("title"),
            url=row.get("url"),
            fetched_at=fetched_at,
            published_at=row.get("seendate"),
            language=row.get("language"),
            domain=row.get("domain"),
        )
        if item is not None:
            items.append(item)
    return tuple(items)


def _query_for_symbol(symbol: str) -> str:
    base = symbol.split("/", maxsplit=1)[0].upper()
    aliases = {
        "BTC": '("bitcoin" OR "BTC" OR "$BTC" OR "XBT")',
        "ETH": '("ethereum" OR "ETH" OR "$ETH" OR "ether")',
        "SOL": '("solana" OR "SOL" OR "$SOL")',
        "USDT": '("tether" OR "USDT" OR "$USDT" OR "stablecoin")',
    }
    asset = aliases.get(base, f'("{base}" OR "${base}")')
    macro = '("Federal Reserve" OR CPI OR inflation OR SEC OR ETF OR liquidity OR dollar OR yields)'
    return f"({asset} OR {macro})"
