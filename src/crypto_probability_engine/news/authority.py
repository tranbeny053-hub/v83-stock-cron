"""Conservative advisory classification for metadata-only news items."""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import UTC, datetime

from crypto_probability_engine.news.models import NewsCluster, NewsItem, parse_datetime, stable_hash

MACRO_KEYWORDS = (
    "fed",
    "federal reserve",
    "cpi",
    "rates",
    "rate cut",
    "inflation",
    "sec",
    "etf",
    "regulation",
    "liquidity",
    "dollar",
    "yields",
    "geopolitics",
    "stablecoin",
)

SOURCE_AUTHORITY = {
    "sec.gov": 1.0,
    "federalreserve.gov": 1.0,
    "stlouisfed.org": 1.0,
    "treasury.gov": 1.0,
    "reuters.com": 0.85,
    "bloomberg.com": 0.85,
    "wsj.com": 0.8,
    "ft.com": 0.8,
    "cnbc.com": 0.7,
    "coindesk.com": 0.72,
    "cointelegraph.com": 0.62,
    "theblock.co": 0.72,
    "news.google.com": 0.3,
    "reddit.com": 0.25,
    "x.com": 0.2,
}


def score_and_classify_items(items: tuple[NewsItem, ...], *, symbol: str) -> tuple[NewsItem, ...]:
    scored = tuple(_score_item(item, symbol=symbol) for item in items)
    return assign_clusters(scored)


def assign_clusters(items: tuple[NewsItem, ...]) -> tuple[NewsItem, ...]:
    grouped: dict[str, list[NewsItem]] = defaultdict(list)
    for item in items:
        key = item.title_hash or item.url_hash
        grouped[key].append(item)
    output: list[NewsItem] = []
    for key in sorted(grouped):
        group = sorted(grouped[key], key=lambda item: (item.published_at or "", item.url_hash))
        cluster_id = f"cluster_{stable_hash(key)}"
        for item in group:
            output.append(
                item.with_cluster(
                    cluster_id=cluster_id,
                    cluster_size=len(group),
                    dropped_count=max(0, len(group) - 1),
                )
            )
    return tuple(output)


def summarize_clusters(items: tuple[NewsItem, ...]) -> tuple[NewsCluster, ...]:
    grouped: dict[str, list[NewsItem]] = defaultdict(list)
    for item in items:
        grouped[item.cluster_id or f"cluster_{item.title_hash}"].append(item)
    clusters: list[NewsCluster] = []
    for cluster_id, group in grouped.items():
        domains = {item.domain for item in group if item.domain}
        representative = max(group, key=lambda item: item.relevance_score)
        clusters.append(
            NewsCluster(
                cluster_id=cluster_id,
                representative_title=representative.title,
                macro_or_micro=representative.macro_or_micro,
                event_class=representative.event_class,
                source_count=len(domains),
                item_count=len(group),
                dropped_count=max(0, len(group) - 1),
                max_relevance_score=max(item.relevance_score for item in group),
            )
        )
    return tuple(sorted(clusters, key=lambda item: (-item.max_relevance_score, item.cluster_id)))


def _score_item(item: NewsItem, *, symbol: str) -> NewsItem:
    text = f"{item.title} {item.snippet or ''}".lower()
    tags = _entity_tags(text, symbol=symbol)
    macro_hit = any(keyword in text for keyword in MACRO_KEYWORDS)
    macro_or_micro = "MICRO" if tags else "MACRO"
    if macro_or_micro == "MACRO" and not macro_hit and "crypto" in text:
        event_class = "SYSTEMIC_CRYPTO"
    elif macro_hit:
        event_class = "MACRO_SYSTEMIC"
    elif tags:
        event_class = "ASSET_SPECIFIC"
    else:
        event_class = "GENERAL"
    relevance = 0.85 if tags else (0.55 if macro_hit or "crypto" in text else 0.2)
    freshness = freshness_score(item.published_at)
    authority = source_authority_score(item.domain)
    confidence = min(1.0, (relevance * 0.5) + (freshness * 0.25) + (authority * 0.25))
    return item.with_scores(
        entity_tags=tags,
        macro_or_micro=macro_or_micro,
        event_class=event_class,
        relevance_score=relevance,
        freshness_score=freshness,
        source_authority_score=authority,
        confidence_score=confidence,
    )


def _entity_tags(text: str, *, symbol: str) -> tuple[str, ...]:
    base = symbol.split("/", maxsplit=1)[0].upper()
    aliases = {
        "BTC": ("bitcoin", "btc", "$btc", "xbt"),
        "ETH": ("ethereum", "eth", "$eth", "ether"),
        "SOL": ("solana", "sol", "$sol"),
        "USDT": ("tether", "usdt", "$usdt", "stablecoin"),
    }
    terms = set(aliases.get(base, (base.lower(), f"${base.lower()}")))
    if base not in {"BTC", "ETH", "SOL", "USDT"} and len(base) <= 2:
        terms.discard(base.lower())
    tags: list[str] = []
    for term in sorted(terms, key=len, reverse=True):
        if term.startswith("$"):
            pattern = re.escape(term)
        else:
            pattern = rf"\b{re.escape(term)}\b"
        if re.search(pattern, text):
            tags.append(base)
            break
    return tuple(tags)


def freshness_score(published_at: str | None) -> float:
    parsed = parse_datetime(published_at)
    if parsed is None:
        return 0.2
    age_hours = max(0.0, (datetime.now(UTC) - parsed).total_seconds() / 3600.0)
    if age_hours <= 6:
        return 1.0
    if age_hours <= 24:
        return 0.75
    if age_hours <= 72:
        return 0.45
    return 0.2


def source_authority_score(domain: str | None) -> float:
    if not domain:
        return 0.4
    normalized = domain.lower().removeprefix("www.")
    for suffix, score in SOURCE_AUTHORITY.items():
        if normalized == suffix or normalized.endswith(f".{suffix}"):
            return score
    return 0.5
