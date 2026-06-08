"""GDELT DOC 2.0 metadata adapter."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
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

GDELT_BASE_URL = "https://api.gdeltproject.org"
GDELT_OPERATION = "GET /api/v2/doc/doc"
DEFAULT_RATE_LIMIT_COOLDOWN_SECONDS = 60.0


@dataclass(frozen=True)
class _GdeltCacheEntry:
    items: tuple[NewsItem, ...]
    stored_at: float


_CACHE_LOCK = threading.Lock()
_CACHE_BY_QUERY: dict[str, _GdeltCacheEntry] = {}
_LAST_OUTBOUND_BY_QUERY: dict[str, float] = {}
_COOLDOWN_UNTIL_BY_QUERY: dict[str, float] = {}


class GdeltDocAdapter:
    name = "gdelt"

    def __init__(self, *, settings: Settings, http_client: PublicHttpClient | None = None) -> None:
        self.settings = settings
        self.http_client = http_client or PublicHttpClient(
            timeout_seconds=settings.news_timeout_seconds,
            max_retries=settings.provider_max_retries,
            rate_limit_per_min=settings.provider_rate_limit_per_min,
        )
        self.last_diagnostics: dict = _empty_diagnostics(self.name, configured=True)

    def is_configured(self) -> bool:
        return True

    def fetch_macro_observations(self) -> tuple[MacroObservation, ...]:
        return ()

    def fetch_items(self, symbol: str) -> tuple[NewsItem, ...]:
        fetched_at = datetime.now(UTC)
        query = _query_for_symbol(symbol)
        cache_key = _cache_key(query)
        cached = _cached_items(cache_key, ttl_seconds=self.settings.news_cache_ttl_seconds)
        now = time.monotonic()
        wait_seconds = _cooldown_wait(cache_key, now)
        if wait_seconds is not None:
            if cached is not None:
                self.last_diagnostics = _status(
                    status="DEGRADED_WITH_CACHE",
                    healthy=True,
                    item_count=len(cached),
                    cache_status="HIT_RATE_LIMIT",
                    http_status=429,
                    error_code="RATE_LIMITED",
                    error_type="RATE_LIMIT",
                    retry_after_seconds=wait_seconds,
                    warning="gdelt: using cached headlines due to rate limit",
                )
                return cached
            self.last_diagnostics = _status(
                status="UNAVAILABLE",
                healthy=False,
                cache_status="MISS_RATE_LIMIT",
                http_status=429,
                error_code="RATE_LIMITED",
                error_type="RATE_LIMIT",
                retry_after_seconds=wait_seconds,
            )
            raise NewsProviderError(
                "RATE_LIMITED",
                "gdelt: rate limited",
                provider=self.name,
                http_status=429,
                error_code="RATE_LIMITED",
                error_type="RATE_LIMIT",
                operation=GDELT_OPERATION,
                retry_after_seconds=wait_seconds,
                cache_status="MISS_RATE_LIMIT",
            )
        local_wait = _local_interval_wait(
            cache_key,
            now,
            min_interval_seconds=self.settings.gdelt_min_interval_seconds,
        )
        if local_wait is not None:
            if cached is not None:
                self.last_diagnostics = _status(
                    status="DEGRADED_WITH_CACHE",
                    healthy=True,
                    item_count=len(cached),
                    cache_status="HIT_THROTTLED",
                    error_code="RATE_LIMITED",
                    error_type="RATE_LIMIT",
                    retry_after_seconds=local_wait,
                    warning="gdelt: using cached headlines due to local throttle",
                )
                return cached
            self.last_diagnostics = _status(
                status="UNAVAILABLE",
                healthy=False,
                cache_status="MISS_THROTTLED",
                error_code="RATE_LIMITED",
                error_type="RATE_LIMIT",
                retry_after_seconds=local_wait,
            )
            raise NewsProviderError(
                "RATE_LIMITED",
                "gdelt: local throttle active",
                provider=self.name,
                error_code="RATE_LIMITED",
                error_type="RATE_LIMIT",
                operation=GDELT_OPERATION,
                retry_after_seconds=local_wait,
                cache_status="MISS_THROTTLED",
            )
        _record_outbound(cache_key, now)
        start = time.perf_counter()
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
            error = provider_error_to_news(exc, provider=self.name, operation=GDELT_OPERATION)
            retry_after = error.retry_after_seconds or DEFAULT_RATE_LIMIT_COOLDOWN_SECONDS
            if error.error_type == "RATE_LIMIT":
                _set_cooldown(cache_key, retry_after)
                if cached is not None:
                    self.last_diagnostics = _status(
                        status="DEGRADED_WITH_CACHE",
                        healthy=True,
                        item_count=len(cached),
                        cache_status="HIT_RATE_LIMIT",
                        http_status=error.http_status,
                        error_code="RATE_LIMITED",
                        error_type="RATE_LIMIT",
                        retry_after_seconds=retry_after,
                        latency_ms=_latency_ms(start),
                        warning="gdelt: using cached headlines due to rate limit",
                    )
                    return cached
            self.last_diagnostics = _status(
                status="UNAVAILABLE",
                healthy=False,
                cache_status="MISS",
                http_status=error.http_status,
                error_code=error.error_code,
                error_type=error.error_type,
                retry_after_seconds=error.retry_after_seconds,
                latency_ms=_latency_ms(start),
            )
            raise error from exc
        items = parse_gdelt_items(payload, fetched_at=fetched_at)
        _store_cache(cache_key, items)
        self.last_diagnostics = _status(
            status="OK",
            healthy=True,
            item_count=len(items),
            cache_status="REFRESHED",
            latency_ms=_latency_ms(start),
        )
        return items


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


def _cache_key(query: str) -> str:
    return " ".join(query.lower().split())


def _cached_items(cache_key: str, *, ttl_seconds: int) -> tuple[NewsItem, ...] | None:
    now = time.monotonic()
    with _CACHE_LOCK:
        entry = _CACHE_BY_QUERY.get(cache_key)
        if entry is None:
            return None
        if now - entry.stored_at > ttl_seconds:
            _CACHE_BY_QUERY.pop(cache_key, None)
            return None
        return entry.items


def _store_cache(cache_key: str, items: tuple[NewsItem, ...]) -> None:
    with _CACHE_LOCK:
        _CACHE_BY_QUERY[cache_key] = _GdeltCacheEntry(items=items, stored_at=time.monotonic())


def _record_outbound(cache_key: str, now: float) -> None:
    with _CACHE_LOCK:
        _LAST_OUTBOUND_BY_QUERY[cache_key] = now


def _set_cooldown(cache_key: str, retry_after_seconds: float) -> None:
    with _CACHE_LOCK:
        _COOLDOWN_UNTIL_BY_QUERY[cache_key] = time.monotonic() + max(
            0.0,
            retry_after_seconds,
        )


def _cooldown_wait(cache_key: str, now: float) -> float | None:
    with _CACHE_LOCK:
        until = _COOLDOWN_UNTIL_BY_QUERY.get(cache_key)
        if until is None:
            return None
        remaining = until - now
        if remaining <= 0:
            _COOLDOWN_UNTIL_BY_QUERY.pop(cache_key, None)
            return None
        return remaining


def _local_interval_wait(
    cache_key: str,
    now: float,
    *,
    min_interval_seconds: float,
) -> float | None:
    if min_interval_seconds <= 0:
        return None
    with _CACHE_LOCK:
        last = _LAST_OUTBOUND_BY_QUERY.get(cache_key)
    if last is None:
        return None
    remaining = min_interval_seconds - (now - last)
    return remaining if remaining > 0 else None


def _latency_ms(start: float) -> float:
    return round((time.perf_counter() - start) * 1000.0, 3)


def _empty_diagnostics(provider: str, *, configured: bool) -> dict:
    return {
        "provider": provider,
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


def _status(
    *,
    status: str,
    healthy: bool,
    item_count: int = 0,
    cache_status: str,
    http_status: int | None = None,
    error_code: str | None = None,
    error_type: str | None = None,
    retry_after_seconds: float | None = None,
    latency_ms: float | None = None,
    warning: str | None = None,
) -> dict:
    return {
        "provider": "gdelt",
        "configured": True,
        "healthy": healthy,
        "status": status,
        "item_count": item_count,
        "macro_observation_count": 0,
        "last_failure_http_status": http_status,
        "last_failure_error_code": error_code,
        "last_failure_error_type": error_type,
        "last_failure_operation": GDELT_OPERATION if error_code else None,
        "last_failure_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z")
        if error_code
        else None,
        "retry_after_seconds": retry_after_seconds,
        "cache_status": cache_status,
        "latency_ms": latency_ms,
        "warnings": [warning] if warning else [],
    }
