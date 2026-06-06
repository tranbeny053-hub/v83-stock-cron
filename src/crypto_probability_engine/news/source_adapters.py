"""News source adapter stubs for Sprint 1."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class NewsItem:
    title: str
    url: str
    source: str
    published_at_utc: str
    snippet: str | None = None


class NewsSourceAdapter(Protocol):
    name: str

    def is_configured(self) -> bool:
        """Return whether the source has been explicitly configured."""

    def fetch_items(self, symbol: str) -> tuple[NewsItem, ...]:
        """Fetch sanitized metadata only; live fetching is not enabled in Sprint 1."""


class UnconfiguredNewsSource:
    name = "unconfigured"

    def is_configured(self) -> bool:
        return False

    def fetch_items(self, symbol: str) -> tuple[NewsItem, ...]:
        return ()


class CountingNewsSource:
    """Test helper source that records attempted fetches."""

    def __init__(self, *, configured: bool = False) -> None:
        self.name = "counting_fixture"
        self.configured = configured
        self.fetch_count = 0

    def is_configured(self) -> bool:
        return self.configured

    def fetch_items(self, symbol: str) -> tuple[NewsItem, ...]:
        self.fetch_count += 1
        return ()

