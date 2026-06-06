"""Schema-valid news blocks with Sprint 1 no-fetch defaults."""

from __future__ import annotations

from collections.abc import Iterable

from crypto_probability_engine.api.schemas import AnalysisMode
from crypto_probability_engine.config.defaults import DEFAULT_PHASE1A
from crypto_probability_engine.news.news_influence import compute_news_influence
from crypto_probability_engine.news.source_adapters import NewsSourceAdapter

NEWS_BLOCK_KEYS = (
    "macro_context",
    "micro_news_context",
    "event_horizon_state",
    "news_materiality_state",
    "novelty_surprise_state",
    "source_confidence_state",
    "narrative_state",
    "catalyst_state",
    "information_state",
)


def _base_block(status: str, *, mode: AnalysisMode) -> dict:
    return {
        "status": status,
        "mode": mode.value,
        "items": [],
        "warnings": [],
        "full_article_bodies_stored": False,
        "sentiment_only_action": "FORBIDDEN",
    }


def build_news_blocks(
    *,
    analysis_mode: AnalysisMode,
    symbol: str,
    sources: Iterable[NewsSourceAdapter] = (),
) -> dict:
    source_list = list(sources)
    if analysis_mode == AnalysisMode.METRICS_ONLY:
        status = "DISABLED_METRICS_ONLY"
        fetch_attempted = False
    else:
        configured = [source for source in source_list if source.is_configured()]
        fetch_attempted = False
        status = "UNAVAILABLE" if not configured else "DEGRADED"

    blocks = {key: _base_block(status, mode=analysis_mode) for key in NEWS_BLOCK_KEYS}
    blocks["news_addon_state"] = {
        "status": status,
        "mode": analysis_mode.value,
        "symbol": symbol,
        "configured_source_count": 0
        if analysis_mode == AnalysisMode.METRICS_ONLY
        else sum(1 for source in source_list if source.is_configured()),
        "fetch_attempted": fetch_attempted,
        "news_evidence_frac": DEFAULT_PHASE1A.news_evidence_frac,
        "news_influence_frac": 0.0,
        "failure_is_non_blocking": True,
        "authority_limits": {
            "can_force_constructive": False,
            "can_override_hard_gates": False,
            "sentiment_only_action": "FORBIDDEN",
        },
    }
    blocks["news_influence"] = compute_news_influence(blocks["news_addon_state"])
    return blocks

