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
    def __init__(self, code: str, message: str, *, provider: str) -> None:
        super().__init__(message)
        self.code = code
        self.provider = provider
        self.message = message


def provider_error_to_news(exc: ProviderError, *, provider: str) -> NewsProviderError:
    return NewsProviderError(exc.code, exc.message, provider=provider)


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
