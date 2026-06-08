"""Schema-valid advisory news blocks."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime

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
    configured_source_count = sum(1 for source in source_list if _safe_is_configured(source))
    if configured_source_count == 0:
        provider_status = [_unconfigured_status(source) for source in source_list]
        return _unavailable_blocks(
            analysis_mode=analysis_mode,
            symbol=symbol,
            configured_source_count=0,
            warnings=["News providers unavailable."],
            provider_status=provider_status,
        )

    provider_status: list[dict] = []
    warnings: list[str] = []
    fetched_items: list[NewsItem] = []
    macro_observations: list[MacroObservation] = []
    for source in source_list:
        if not _safe_is_configured(source):
            provider_status.append(_unconfigured_status(source))
            continue
        try:
            items = tuple(source.fetch_items(symbol))
            observations = tuple(_fetch_macro_observations(source))
        except Exception as exc:
            status = _failure_status(source, exc)
            warnings.extend(status.get("warnings", []))
        else:
            fetched_items.extend(items)
            macro_observations.extend(observations)
            status = _success_status(source, item_count=len(items), macro_count=len(observations))
            warnings.extend(status.get("warnings", []))
        provider_status.append(status)

    scored_items = score_and_classify_items(tuple(fetched_items), symbol=symbol)
    clusters = summarize_clusters(scored_items)
    macro_items = [item for item in scored_items if item.macro_or_micro == "MACRO"]
    micro_items = [item for item in scored_items if item.macro_or_micro == "MICRO"]
    has_successful_provider = _has_successful_provider(provider_status)
    evidence_status = (
        "OK" if (scored_items or macro_observations or has_successful_provider) else "UNAVAILABLE"
    )
    evidence = {
        "status": evidence_status,
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
        if not has_successful_provider:
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
        "configured_source_count": configured_source_count,
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
    provider_status: list[dict] | None = None,
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
        provider_status=provider_status or [],
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


def _provider_base(source: NewsSourceAdapter, *, configured: bool) -> dict:
    return {
        "provider": getattr(source, "name", "unknown"),
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


def _unconfigured_status(source: NewsSourceAdapter) -> dict:
    diagnostics = _safe_diagnostics(source)
    status = _provider_base(source, configured=False)
    status.update({key: value for key, value in diagnostics.items() if key in status})
    status["configured"] = False
    status["status"] = "UNCONFIGURED"
    status["healthy"] = False
    status["warnings"] = []
    return status


def _success_status(source: NewsSourceAdapter, *, item_count: int, macro_count: int) -> dict:
    status = _provider_base(source, configured=True)
    diagnostics = _safe_diagnostics(source)
    status.update({key: value for key, value in diagnostics.items() if key in status})
    status["configured"] = True
    status["item_count"] = item_count
    status["macro_observation_count"] = macro_count
    status["healthy"] = bool(status.get("healthy")) or status.get("status") == "OK"
    if status["status"] in {"UNAVAILABLE", "UNCONFIGURED"}:
        status["healthy"] = True
        status["status"] = "OK"
    if status["status"] == "OK" and not status.get("cache_status"):
        status["cache_status"] = "BYPASS"
    status["warnings"] = _safe_warning_list(status.get("warnings"))
    return status


def _failure_status(source: NewsSourceAdapter, exc: Exception) -> dict:
    diagnostics = _safe_diagnostics(source)
    status = _provider_base(source, configured=True)
    status.update({key: value for key, value in diagnostics.items() if key in status})
    status["configured"] = True
    status["healthy"] = False
    status["status"] = status.get("status") if status.get("status") != "OK" else "UNAVAILABLE"
    status["last_failure_error_code"] = status.get("last_failure_error_code") or getattr(
        exc,
        "error_code",
        getattr(exc, "code", "PROVIDER_DEGRADED"),
    )
    status["last_failure_error_type"] = status.get("last_failure_error_type") or getattr(
        exc,
        "error_type",
        "PROVIDER",
    )
    status["last_failure_http_status"] = status.get("last_failure_http_status") or getattr(
        exc,
        "http_status",
        None,
    )
    status["last_failure_operation"] = status.get("last_failure_operation") or getattr(
        exc,
        "operation",
        None,
    )
    status["retry_after_seconds"] = status.get("retry_after_seconds") or getattr(
        exc,
        "retry_after_seconds",
        None,
    )
    status["last_failure_at_utc"] = status.get("last_failure_at_utc") or datetime.now(
        UTC
    ).isoformat().replace("+00:00", "Z")
    if status["status"] == "UNCONFIGURED":
        status["status"] = "UNAVAILABLE"
    status["warnings"] = _safe_warning_list(status.get("warnings")) or [
        _warning_for_status(status)
    ]
    return status


def _generic_failure_status(source: NewsSourceAdapter) -> dict:
    status = _provider_base(source, configured=True)
    status["last_failure_error_code"] = "PROVIDER_DEGRADED"
    status["last_failure_error_type"] = "PROVIDER"
    status["last_failure_at_utc"] = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    status["warnings"] = [f"{status['provider']}: provider unavailable"]
    return status


def _safe_diagnostics(source: NewsSourceAdapter) -> dict:
    diagnostics = getattr(source, "last_diagnostics", None)
    return diagnostics if isinstance(diagnostics, dict) else {}


def _safe_warning_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if item]


def _warning_for_status(status: dict) -> str:
    provider = str(status.get("provider") or "provider")
    error_code = status.get("last_failure_error_code")
    error_type = status.get("last_failure_error_type")
    if provider == "newsapi" and error_code == "apiKeyInvalid":
        return "newsapi: api key invalid or inactive"
    if error_type == "RATE_LIMIT" or error_code in {"RATE_LIMITED", "rateLimited"}:
        return f"{provider}: rate limited"
    if error_code == "parameterInvalid":
        return f"{provider}: parameter invalid"
    return f"{provider}: provider unavailable"


def _has_successful_provider(provider_status: list[dict]) -> bool:
    return any(
        item.get("configured")
        and item.get("status") in {"OK", "OK_WITH_WARNINGS", "DEGRADED_WITH_CACHE"}
        for item in provider_status
    )


def _fetch_macro_observations(source: NewsSourceAdapter) -> tuple[MacroObservation, ...]:
    fetcher = getattr(source, "fetch_macro_observations", None)
    if not callable(fetcher):
        return ()
    return tuple(fetcher())


def _overall_status(provider_status: list[dict], warnings: list[str], has_evidence: bool) -> str:
    configured = [item for item in provider_status if item.get("configured")]
    if not configured:
        return "UNAVAILABLE"
    if not has_evidence and not _has_successful_provider(configured):
        return "UNAVAILABLE"
    if warnings or any(item.get("status") != "OK" for item in configured):
        return "DEGRADED"
    return "OK"
