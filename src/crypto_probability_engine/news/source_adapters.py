"""News source adapter protocols and test helpers."""

from __future__ import annotations

from typing import Protocol

from crypto_probability_engine.news.models import MacroObservation, NewsItem


class NewsSourceAdapter(Protocol):
    name: str

    def is_configured(self) -> bool:
        """Return whether the source has been explicitly configured."""

    def fetch_items(self, symbol: str) -> tuple[NewsItem, ...]:
        """Fetch sanitized metadata only."""

    def fetch_macro_observations(self) -> tuple[MacroObservation, ...]:
        """Fetch compact macro observations when supported."""


class UnconfiguredNewsSource:
    name = "unconfigured"

    def is_configured(self) -> bool:
        return False

    def fetch_items(self, symbol: str) -> tuple[NewsItem, ...]:
        return ()

    def fetch_macro_observations(self) -> tuple[MacroObservation, ...]:
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

    def fetch_macro_observations(self) -> tuple[MacroObservation, ...]:
        return ()
