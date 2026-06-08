"""Schema-valid advisory news blocks."""

from __future__ import annotations

from collections.abc import Iterable

from crypto_probability_engine.api.schemas import AnalysisMode
from crypto_probability_engine.config.defaults import DEFAULT_PHASE1A
from crypto_probability_engine.config.settings import Settings
from crypto_probability_engine.news.adapters import (
    FredMacroAdapter,
    GdeltDocAdapter,
    NewsApiAdapter,
)
from crypto_probability_engine.news.authority import score_and_classify_items, summarize_clusters
from crypto_probability_engine.news.models import NEWS_INFLUENCE_MODE, MacroObservation, NewsItem
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
    sources: Iterable[NewsSourceAdapter] | None = None,
    settings: Settings | None = None,
) -> dict:
    if analysis_mode == AnalysisMode.METRICS_ONLY:
        return _disabled_blocks(analysis_mode=analysis_mode, symbol=symbol)

    source_list = list(sources) if sources is not None else build_live_news_sources(settings)
    configured = [source for source in source_list if _safe_is_configured(source)]
    if not configured:
        return _unavailable_blocks(
            analysis_mode=analysis_mode,
            symbol=symbol,
            configured_source_count=0,
            warnings=["News providers unavailable."],
        )

    provider_status: list[dict] = []
    warnings: list[str] = []
    fetched_items: list[NewsItem] = []
    macro_observations: list[MacroObservation] = []
    for source in configured:
        status = {
            "provider": source.name,
            "configured": True,
            "healthy": False,
            "status": "UNAVAILABLE",
            "item_count": 0,
            "macro_observation_count": 0,
        }
        try:
            items = tuple(source.fetch_items(symbol))
            observations = tuple(_fetch_macro_observations(source))
        except Exception:
            warnings.append(f"{source.name}: provider unavailable")
        else:
            fetched_items.extend(items)
            macro_observations.extend(observations)
            status["healthy"] = bool(items or observations)
            status["status"] = "OK" if status["healthy"] else "UNAVAILABLE"
            status["item_count"] = len(items)
            status["macro_observation_count"] = len(observations)
        provider_status.append(status)

    scored_items = score_and_classify_items(tuple(fetched_items), symbol=symbol)
    clusters = summarize_clusters(scored_items)
    macro_items = [item for item in scored_items if item.macro_or_micro == "MACRO"]
    micro_items = [item for item in scored_items if item.macro_or_micro == "MICRO"]
    evidence = {
        "status": "OK" if (scored_items or macro_observations) else "UNAVAILABLE",
        "influence_mode": NEWS_INFLUENCE_MODE,
        "news_influence_frac": 0.0,
        "clusters": [cluster.to_public_dict() for cluster in clusters[:8]],
        "links": [
            {
                "cluster_id": item.cluster_id,
                "url_hash": item.url_hash,
                "title_hash": item.title_hash,
                "relevance_score": item.relevance_score,
            }
            for item in scored_items[:12]
        ],
    }
    if not (scored_items or macro_observations):
        warnings.append("News providers returned no usable metadata.")
    overall_status = _overall_status(
        provider_status,
        warnings,
        bool(scored_items or macro_observations),
    )

    blocks = {key: _base_block(overall_status, mode=analysis_mode) for key in NEWS_BLOCK_KEYS}
    blocks["macro_context"]["items"] = [item.to_public_dict() for item in macro_items[:8]]
    blocks["macro_context"]["macro_observations"] = [
        observation.to_public_dict() for observation in macro_observations
    ]
    blocks["micro_news_context"]["items"] = [item.to_public_dict() for item in micro_items[:8]]
    blocks["news_materiality_state"]["items"] = evidence["clusters"]
    blocks["novelty_surprise_state"]["items"] = evidence["clusters"]
    blocks["source_confidence_state"]["items"] = provider_status
    blocks["information_state"]["items"] = [
        {
            "total_items": len(scored_items),
            "macro_items": len(macro_items),
            "micro_items": len(micro_items),
            "macro_observations": len(macro_observations),
            "cluster_count": len(clusters),
        }
    ]
    for block in blocks.values():
        block["warnings"] = list(warnings)
    blocks["news_addon_state"] = {
        "status": overall_status,
        "mode": analysis_mode.value,
        "symbol": symbol,
        "configured_source_count": len(configured),
        "fetch_attempted": True,
        "provider_status": provider_status,
        "warnings": list(warnings),
        "influence_mode": NEWS_INFLUENCE_MODE,
        "news_evidence_frac": DEFAULT_PHASE1A.news_evidence_frac,
        "news_influence_frac": 0.0,
        "failure_is_non_blocking": True,
        "authority_limits": {
            "can_force_constructive": False,
            "can_override_hard_gates": False,
            "sentiment_only_action": "FORBIDDEN",
        },
    }
    blocks["news_evidence"] = evidence
    blocks["news_influence"] = compute_news_influence(blocks["news_addon_state"])
    return blocks


def build_live_news_sources(settings: Settings | None) -> list[NewsSourceAdapter]:
    if settings is None or settings.data_mode != "live":
        return []
    return [
        GdeltDocAdapter(settings=settings),
        FredMacroAdapter(settings=settings),
        NewsApiAdapter(settings=settings),
    ]


def _disabled_blocks(*, analysis_mode: AnalysisMode, symbol: str) -> dict:
    status = "DISABLED_METRICS_ONLY"
    blocks = {key: _base_block(status, mode=analysis_mode) for key in NEWS_BLOCK_KEYS}
    blocks["macro_context"]["message"] = "News analysis disabled for this run."
    blocks["micro_news_context"]["message"] = "News analysis disabled for this run."
    blocks["news_addon_state"] = _addon_state(
        status=status,
        analysis_mode=analysis_mode,
        symbol=symbol,
        configured_source_count=0,
        fetch_attempted=False,
        warnings=[],
        provider_status=[],
    )
    blocks["news_evidence"] = _empty_evidence(status=status)
    blocks["news_influence"] = compute_news_influence(blocks["news_addon_state"])
    return blocks


def _unavailable_blocks(
    *,
    analysis_mode: AnalysisMode,
    symbol: str,
    configured_source_count: int,
    warnings: list[str],
) -> dict:
    status = "UNAVAILABLE"
    blocks = {key: _base_block(status, mode=analysis_mode) for key in NEWS_BLOCK_KEYS}
    for block in blocks.values():
        block["warnings"] = list(warnings)
    blocks["news_addon_state"] = _addon_state(
        status=status,
        analysis_mode=analysis_mode,
        symbol=symbol,
        configured_source_count=configured_source_count,
        fetch_attempted=False,
        warnings=warnings,
        provider_status=[],
    )
    blocks["news_evidence"] = _empty_evidence(status=status)
    blocks["news_influence"] = compute_news_influence(blocks["news_addon_state"])
    return blocks


def _addon_state(
    *,
    status: str,
    analysis_mode: AnalysisMode,
    symbol: str,
    configured_source_count: int,
    fetch_attempted: bool,
    warnings: list[str],
    provider_status: list[dict],
) -> dict:
    return {
        "status": status,
        "mode": analysis_mode.value,
        "symbol": symbol,
        "configured_source_count": configured_source_count,
        "fetch_attempted": fetch_attempted,
        "provider_status": provider_status,
        "warnings": list(warnings),
        "influence_mode": NEWS_INFLUENCE_MODE,
        "news_evidence_frac": DEFAULT_PHASE1A.news_evidence_frac,
        "news_influence_frac": 0.0,
        "failure_is_non_blocking": True,
        "authority_limits": {
            "can_force_constructive": False,
            "can_override_hard_gates": False,
            "sentiment_only_action": "FORBIDDEN",
        },
    }


def _empty_evidence(*, status: str) -> dict:
    return {
        "status": status,
        "influence_mode": NEWS_INFLUENCE_MODE,
        "news_influence_frac": 0.0,
        "clusters": [],
        "links": [],
    }


def _safe_is_configured(source: NewsSourceAdapter) -> bool:
    try:
        return bool(source.is_configured())
    except Exception:
        return False


def _fetch_macro_observations(source: NewsSourceAdapter) -> tuple[MacroObservation, ...]:
    fetcher = getattr(source, "fetch_macro_observations", None)
    if not callable(fetcher):
        return ()
    return tuple(fetcher())


def _overall_status(provider_status: list[dict], warnings: list[str], has_evidence: bool) -> str:
    healthy_count = sum(1 for item in provider_status if item.get("healthy"))
    if not has_evidence:
        return "UNAVAILABLE"
    if warnings or healthy_count < len(provider_status):
        return "DEGRADED"
    return "OK"
