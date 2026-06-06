from __future__ import annotations

from crypto_probability_engine.api.schemas import AnalysisMode
from crypto_probability_engine.news.contract import build_news_blocks
from crypto_probability_engine.news.news_influence import apply_news_to_score
from crypto_probability_engine.news.source_adapters import CountingNewsSource


def test_metrics_only_fetches_nothing() -> None:
    source = CountingNewsSource(configured=True)
    blocks = build_news_blocks(
        analysis_mode=AnalysisMode.METRICS_ONLY,
        symbol="BTC/USDT",
        sources=[source],
    )
    assert source.fetch_count == 0
    assert blocks["news_addon_state"]["status"] == "DISABLED_METRICS_ONLY"
    assert blocks["news_addon_state"]["fetch_attempted"] is False


def test_news_addon_without_source_is_schema_valid_unavailable() -> None:
    blocks = build_news_blocks(
        analysis_mode=AnalysisMode.NEWS_ADDON,
        symbol="BTC/USDT",
        sources=[CountingNewsSource(configured=False)],
    )
    assert blocks["news_addon_state"]["status"] == "UNAVAILABLE"
    for key in (
        "macro_context",
        "micro_news_context",
        "event_horizon_state",
        "news_materiality_state",
        "novelty_surprise_state",
        "source_confidence_state",
        "narrative_state",
        "catalyst_state",
        "information_state",
    ):
        assert blocks[key]["status"] == "UNAVAILABLE"


def test_influence_is_no_op_and_cannot_force_constructive() -> None:
    blocks = build_news_blocks(analysis_mode=AnalysisMode.NEWS_ADDON, symbol="BTC/USDT")
    influence = blocks["news_influence"]
    score = apply_news_to_score({"disposition": "WATCH", "total_score": 50}, influence)
    assert influence["news_influence_frac"] == 0.0
    assert influence["can_force_constructive"] is False
    assert score["disposition"] == "WATCH"


def test_news_cannot_override_hard_gate() -> None:
    blocks = build_news_blocks(analysis_mode=AnalysisMode.NEWS_ADDON, symbol="BTC/USDT")
    assert blocks["news_influence"]["can_override_hard_gates"] is False


def test_no_full_article_body_field_or_storage() -> None:
    blocks = build_news_blocks(analysis_mode=AnalysisMode.NEWS_ADDON, symbol="BTC/USDT")
    assert blocks["micro_news_context"]["items"] == []
    assert blocks["micro_news_context"]["full_article_bodies_stored"] is False

