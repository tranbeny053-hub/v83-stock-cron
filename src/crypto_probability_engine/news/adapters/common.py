"""Shared helpers for metadata-only public news adapters."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from crypto_probability_engine.adapters.types import ProviderError
from crypto_probability_engine.news.models import (
    MacroObservation,
    NewsItem,
    make_news_item,
    parse_datetime,
)


class NewsProviderError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        provider: str,
        http_status: int | None = None,
        error_code: str | None = None,
        error_type: str | None = None,
        operation: str | None = None,
        retry_after_seconds: float | None = None,
        cache_status: str | None = None,
        latency_ms: float | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.provider = provider
        self.message = message
        self.http_status = http_status
        self.error_code = error_code or code
        self.error_type = error_type or "PROVIDER"
        self.operation = operation
        self.retry_after_seconds = retry_after_seconds
        self.cache_status = cache_status
        self.latency_ms = latency_ms
        self.failure_at_utc = datetime.now(UTC).isoformat().replace("+00:00", "Z")


def provider_error_to_news(
    exc: ProviderError,
    *,
    provider: str,
    operation: str | None = None,
) -> NewsProviderError:
    http_status = exc.http_status
    error_code = exc.error_code or exc.code
    error_type = exc.error_type or "PROVIDER"
    if http_status in {418, 429}:
        error_code = error_code or "RATE_LIMITED"
        error_type = "RATE_LIMIT"
    elif http_status in {401, 403}:
        error_type = "AUTH"
    return NewsProviderError(
        exc.code,
        _safe_message(provider=provider, http_status=http_status, error_code=error_code),
        provider=provider,
        http_status=http_status,
        error_code=error_code,
        error_type=error_type,
        operation=operation or exc.operation,
        retry_after_seconds=exc.retry_after_seconds,
    )


def _safe_message(*, provider: str, http_status: int | None, error_code: str | None) -> str:
    if provider == "newsapi" and http_status in {401, 403}:
        return "newsapi: api key invalid or inactive"
    if http_status in {418, 429}:
        return f"{provider}: rate limited"
    if error_code:
        return f"{provider}: {error_code}"
    return f"{provider}: provider unavailable"


def parse_float(value: Any) -> float | None:
    if value in {None, "", "."}:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def compact_item(
    *,
    provider: str,
    source_name: str,
    title: str | None,
    url: str | None,
    fetched_at: datetime,
    snippet: str | None = None,
    published_at: str | datetime | None = None,
    language: str | None = None,
    domain: str | None = None,
) -> NewsItem | None:
    if not title or not url:
        return None
    return make_news_item(
        provider=provider,
        source_name=source_name,
        title=title,
        url=url,
        fetched_at=fetched_at,
        snippet=snippet,
        published_at=parse_datetime(published_at),
        language=language,
        domain=domain,
    )


def fred_observation(
    *,
    series_id: str,
    label: str,
    row: dict,
    fetched_at: datetime,
) -> MacroObservation:
    return MacroObservation(
        provider="fred",
        series_id=series_id,
        label=label,
        observation_date=str(row.get("date") or ""),
        value=parse_float(row.get("value")),
        fetched_at=fetched_at.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        status="OK" if parse_float(row.get("value")) is not None else "INSUFFICIENT_DATA",
    )
