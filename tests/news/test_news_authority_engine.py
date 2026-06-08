from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from crypto_probability_engine.adapters.types import ProviderError
from crypto_probability_engine.api.schemas import AnalysisMode
from crypto_probability_engine.config.settings import Settings
from crypto_probability_engine.news.adapters.common import NewsProviderError
from crypto_probability_engine.news.adapters.fred import parse_fred_observations
from crypto_probability_engine.news.adapters.gdelt import GdeltDocAdapter, parse_gdelt_items
from crypto_probability_engine.news.adapters.newsapi import NewsApiAdapter, parse_newsapi_items
from crypto_probability_engine.news.authority import score_and_classify_items, summarize_clusters
from crypto_probability_engine.news.contract import build_news_blocks
from crypto_probability_engine.news.models import MacroObservation, NewsItem, make_news_item

FETCHED_AT = datetime(2026, 6, 8, 12, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def clear_gdelt_cache() -> None:
    import crypto_probability_engine.news.adapters.gdelt as gdelt_module

    with gdelt_module._CACHE_LOCK:
        gdelt_module._CACHE_BY_QUERY.clear()
        gdelt_module._LAST_OUTBOUND_BY_QUERY.clear()
        gdelt_module._COOLDOWN_UNTIL_BY_QUERY.clear()


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


class FakeNewsHttpClient:
    def __init__(self, payloads_or_errors: list[object]) -> None:
        self.payloads_or_errors = payloads_or_errors
        self.calls = 0

    def get_json(self, **kwargs):
        self.calls += 1
        result = self.payloads_or_errors.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def _settings_with_newsapi(value: str | None) -> Settings:
    return Settings.model_validate({"newsapi" + "_key": value})


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


def test_gdelt_429_sets_sanitized_rate_limit_diagnostics() -> None:
    client = FakeNewsHttpClient(
        [
            ProviderError(
                "PROVIDER_DEGRADED",
                "rate limited",
                provider="gdelt",
                http_status=429,
                error_code="RATE_LIMITED",
                error_type="RATE_LIMIT",
                retry_after_seconds=42,
                operation="GET /api/v2/doc/doc",
            )
        ]
    )
    adapter = GdeltDocAdapter(settings=Settings(), http_client=client)

    with pytest.raises(NewsProviderError):
        adapter.fetch_items("BTC/USDT")

    status = adapter.last_diagnostics
    assert status["last_failure_http_status"] == 429
    assert status["last_failure_error_code"] == "RATE_LIMITED"
    assert status["last_failure_error_type"] == "RATE_LIMIT"
    assert status["retry_after_seconds"] == 42


def test_gdelt_local_throttle_prevents_immediate_second_outbound_call() -> None:
    client = FakeNewsHttpClient(
        [
            {
                "articles": [
                    {
                        "title": "Bitcoin ETF flows rise",
                        "url": "https://example.com/btc",
                        "domain": "example.com",
                        "seendate": "20260608T093000Z",
                    }
                ]
            }
        ]
    )
    adapter = GdeltDocAdapter(
        settings=Settings(gdelt_min_interval_seconds=6, news_cache_ttl_seconds=180),
        http_client=client,
    )

    first = adapter.fetch_items("BTC/USDT")
    second = adapter.fetch_items("BTC/USDT")

    assert first == second
    assert client.calls == 1
    assert adapter.last_diagnostics["cache_status"] == "HIT_THROTTLED"


def test_gdelt_cached_response_is_reused_when_provider_rate_limited() -> None:
    client = FakeNewsHttpClient(
        [
            {
                "articles": [
                    {
                        "title": "Solana liquidity improves",
                        "url": "https://example.com/sol",
                        "domain": "example.com",
                        "seendate": "20260608T093000Z",
                    }
                ]
            },
            ProviderError(
                "PROVIDER_DEGRADED",
                "rate limited",
                provider="gdelt",
                http_status=429,
                error_code="RATE_LIMITED",
                error_type="RATE_LIMIT",
                retry_after_seconds=60,
                operation="GET /api/v2/doc/doc",
            ),
        ]
    )
    adapter = GdeltDocAdapter(
        settings=Settings(gdelt_min_interval_seconds=0, news_cache_ttl_seconds=180),
        http_client=client,
    )

    first = adapter.fetch_items("SOL/USDT")
    second = adapter.fetch_items("SOL/USDT")

    assert first == second
    assert client.calls == 2
    assert adapter.last_diagnostics["status"] == "DEGRADED_WITH_CACHE"
    assert adapter.last_diagnostics["cache_status"] == "HIT_RATE_LIMIT"


def test_gdelt_zero_articles_is_ok_with_zero_item_count() -> None:
    adapter = GdeltDocAdapter(
        settings=Settings(),
        http_client=FakeNewsHttpClient([{"articles": []}]),
    )

    assert adapter.fetch_items("BTC/USDT") == ()
    assert adapter.last_diagnostics["status"] == "OK"
    assert adapter.last_diagnostics["item_count"] == 0


def test_newsapi_401_invalid_key_is_sanitized() -> None:
    secret_key = "newsapi-secret-value"
    client = FakeNewsHttpClient(
        [
            ProviderError(
                "PROVIDER_DEGRADED",
                "auth failed",
                provider="newsapi",
                http_status=401,
                error_code="apiKeyInvalid",
                error_type="AUTH",
                operation="GET /v2/everything",
            )
        ]
    )
    adapter = NewsApiAdapter(settings=_settings_with_newsapi(secret_key), http_client=client)

    with pytest.raises(NewsProviderError):
        adapter.fetch_items("BTC/USDT")

    status = adapter.last_diagnostics
    assert status["last_failure_http_status"] == 401
    assert status["last_failure_error_code"] == "apiKeyInvalid"
    assert status["last_failure_error_type"] == "AUTH"
    assert status["warnings"] == ["newsapi: api key invalid or inactive"]
    assert secret_key not in str(status)


def test_newsapi_429_rate_limited_is_sanitized() -> None:
    client = FakeNewsHttpClient(
        [
            ProviderError(
                "PROVIDER_DEGRADED",
                "rate limited",
                provider="newsapi",
                http_status=429,
                error_code="rateLimited",
                error_type="RATE_LIMIT",
                retry_after_seconds=30,
                operation="GET /v2/everything",
            )
        ]
    )
    adapter = NewsApiAdapter(settings=_settings_with_newsapi("configured"), http_client=client)

    with pytest.raises(NewsProviderError):
        adapter.fetch_items("BTC/USDT")

    assert adapter.last_diagnostics["last_failure_http_status"] == 429
    assert adapter.last_diagnostics["last_failure_error_code"] == "rateLimited"
    assert adapter.last_diagnostics["last_failure_error_type"] == "RATE_LIMIT"


def test_newsapi_absent_key_is_unconfigured_not_invalid() -> None:
    adapter = NewsApiAdapter(
        settings=_settings_with_newsapi(None),
        http_client=FakeNewsHttpClient([]),
    )

    assert adapter.is_configured() is False
    assert adapter.fetch_items("BTC/USDT") == ()
    assert adapter.last_diagnostics["configured"] is False
    assert adapter.last_diagnostics["status"] == "UNCONFIGURED"


def test_fred_ok_with_gdelt_and_newsapi_failures_is_degraded_not_failed() -> None:
    observation = MacroObservation(
        provider="fred",
        series_id="FEDFUNDS",
        label="Effective Federal Funds Rate",
        observation_date="2026-06-01",
        value=4.25,
        fetched_at="2026-06-08T12:00:00Z",
    )
    blocks = build_news_blocks(
        analysis_mode=AnalysisMode.NEWS_ADDON,
        symbol="BTC/USDT",
        sources=[
            FixtureNewsSource(observations=(observation,)),
            FixtureNewsSource(fail=True),
            FixtureNewsSource(fail=True),
        ],
    )

    assert blocks["news_addon_state"]["status"] == "DEGRADED"
    assert blocks["news_addon_state"]["news_influence_frac"] == 0.0
    assert blocks["news_addon_state"]["influence_mode"] == "ADVISORY_DISPLAY_ONLY"


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
