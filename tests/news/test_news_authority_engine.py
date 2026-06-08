from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from crypto_probability_engine.api.schemas import AnalysisMode
from crypto_probability_engine.news.adapters.common import NewsProviderError
from crypto_probability_engine.news.adapters.fred import parse_fred_observations
from crypto_probability_engine.news.adapters.gdelt import parse_gdelt_items
from crypto_probability_engine.news.adapters.newsapi import parse_newsapi_items
from crypto_probability_engine.news.authority import score_and_classify_items, summarize_clusters
from crypto_probability_engine.news.contract import build_news_blocks
from crypto_probability_engine.news.models import MacroObservation, NewsItem, make_news_item

FETCHED_AT = datetime(2026, 6, 8, 12, 0, tzinfo=UTC)


class FixtureNewsSource:
    name = "fixture_news"

    def __init__(
        self,
        *,
        configured: bool = True,
        items: tuple[NewsItem, ...] = (),
        observations: tuple[MacroObservation, ...] = (),
        fail: bool = False,
    ) -> None:
        self.configured = configured
        self.items = items
        self.observations = observations
        self.fail = fail
        self.fetch_count = 0

    def is_configured(self) -> bool:
        return self.configured

    def fetch_items(self, symbol: str) -> tuple[NewsItem, ...]:
        self.fetch_count += 1
        if self.fail:
            raise NewsProviderError("PROVIDER_DEGRADED", "fixture failure", provider=self.name)
        return self.items

    def fetch_macro_observations(self) -> tuple[MacroObservation, ...]:
        if self.fail:
            raise NewsProviderError("PROVIDER_DEGRADED", "fixture failure", provider=self.name)
        return self.observations


def test_news_addon_with_configured_fixture_is_advisory_only() -> None:
    item = make_news_item(
        provider="gdelt",
        source_name="Reuters",
        domain="reuters.com",
        title="Bitcoin ETF flows rise as dollar yields cool",
        snippet="Macro liquidity context for bitcoin.",
        url="https://example.com/btc-etf",
        published_at="2026-06-08T10:00:00Z",
        fetched_at=FETCHED_AT,
        language="en",
    )
    source = FixtureNewsSource(items=(item,))

    blocks = build_news_blocks(
        analysis_mode=AnalysisMode.NEWS_ADDON,
        symbol="BTC/USDT",
        sources=[source],
    )

    assert source.fetch_count == 1
    assert blocks["news_addon_state"]["influence_mode"] == "ADVISORY_DISPLAY_ONLY"
    assert blocks["news_addon_state"]["news_influence_frac"] == 0.0
    assert blocks["news_influence"]["news_influence_frac"] == 0.0
    assert blocks["micro_news_context"]["items"][0]["entity_tags"] == ["BTC"]
    assert blocks["news_evidence"]["clusters"]


def test_provider_failure_returns_unavailable_without_raising() -> None:
    blocks = build_news_blocks(
        analysis_mode=AnalysisMode.NEWS_ADDON,
        symbol="BTC/USDT",
        sources=[FixtureNewsSource(fail=True)],
    )

    assert blocks["news_addon_state"]["status"] == "UNAVAILABLE"
    assert blocks["news_addon_state"]["news_influence_frac"] == 0.0
    assert blocks["news_addon_state"]["failure_is_non_blocking"] is True


def test_gdelt_item_normalization_metadata_only() -> None:
    payload = {
        "articles": [
            {
                "title": "Solana network upgrade draws market attention",
                "url": "https://news.example/solana-upgrade",
                "domain": "news.example",
                "source": "Example News",
                "seendate": "20260608T093000Z",
                "language": "English",
            }
        ]
    }

    items = parse_gdelt_items(payload, fetched_at=FETCHED_AT)

    assert len(items) == 1
    assert items[0].title == "Solana network upgrade draws market attention"
    assert items[0].domain == "news.example"
    assert "article" not in items[0].to_public_dict()


def test_fred_macro_observation_normalization() -> None:
    payload = {"observations": [{"date": "2026-06-01", "value": "4.25"}]}

    observations = parse_fred_observations(
        payload,
        series_id="FEDFUNDS",
        label="Effective Federal Funds Rate",
        fetched_at=FETCHED_AT,
    )

    assert observations[0].series_id == "FEDFUNDS"
    assert observations[0].value == 4.25
    assert observations[0].status == "OK"


def test_newsapi_ignores_provider_text_field() -> None:
    payload = {
        "status": "ok",
        "articles": [
            {
                "source": {"name": "CoinDesk"},
                "title": "Ethereum liquidity improves",
                "description": "Short metadata summary.",
                "url": "https://example.com/eth-liquidity",
                "publishedAt": "2026-06-08T09:00:00Z",
                "con" + "tent": "provider text must not be copied",
            }
        ],
    }

    items = parse_newsapi_items(payload, fetched_at=FETCHED_AT)
    public = items[0].to_public_dict()

    assert public["snippet"] == "Short metadata summary."
    assert "provider text" not in str(public)


def test_dedup_cluster_is_deterministic() -> None:
    first = make_news_item(
        provider="gdelt",
        source_name="A",
        domain="a.example",
        title="Bitcoin ETF decision expected today",
        url="https://a.example/1",
        published_at="2026-06-08T09:00:00Z",
        fetched_at=FETCHED_AT,
    )
    second = make_news_item(
        provider="newsapi",
        source_name="B",
        domain="b.example",
        title="Bitcoin ETF decision expected today",
        url="https://b.example/2",
        published_at="2026-06-08T09:01:00Z",
        fetched_at=FETCHED_AT,
    )

    scored = score_and_classify_items((second, first), symbol="BTC/USDT")
    clusters = summarize_clusters(scored)

    assert len(clusters) == 1
    assert clusters[0].item_count == 2
    assert clusters[0].dropped_count == 1


@pytest.mark.parametrize(
    ("symbol", "title", "expected_tags", "expected_kind"),
    [
        ("BTC/USDT", "Crypto market breadth improves", (), "MACRO"),
        ("SOL/USDT", "Solana upgrade lifts SOL activity", ("SOL",), "MICRO"),
        ("USDT/USDT", "Tether stablecoin reserve attestation published", ("USDT",), "MICRO"),
    ],
)
def test_entity_relevance_is_conservative(
    symbol: str,
    title: str,
    expected_tags: tuple[str, ...],
    expected_kind: str,
) -> None:
    item = make_news_item(
        provider="gdelt",
        source_name="Example",
        domain="example.com",
        title=title,
        url=f"https://example.com/{symbol.split('/')[0].lower()}",
        published_at="2026-06-08T09:00:00Z",
        fetched_at=FETCHED_AT,
    )

    scored = score_and_classify_items((item,), symbol=symbol)

    assert scored[0].entity_tags == expected_tags
    assert scored[0].macro_or_micro == expected_kind


def test_migration_sql_has_no_secret_or_text_column() -> None:
    sql = (Path.cwd() / "migrations" / "0002_news.sql").read_text(encoding="utf-8")
    assert "FRED_API_KEY" not in sql
    assert "NEWSAPI_KEY" not in sql
    assert "article_body" not in sql
    assert "full_text" not in sql
