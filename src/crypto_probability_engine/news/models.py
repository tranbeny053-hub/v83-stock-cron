"""Metadata-only news models for the advisory news authority foundation."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from urllib.parse import urlparse

NEWS_INFLUENCE_MODE = "ADVISORY_DISPLAY_ONLY"


@dataclass(frozen=True)
class NewsItem:
    provider: str
    source_name: str
    domain: str
    title: str
    snippet: str | None
    url: str
    url_hash: str
    title_hash: str
    published_at: str | None
    fetched_at: str
    language: str | None = None
    entity_tags: tuple[str, ...] = ()
    macro_or_micro: str = "MACRO"
    event_class: str = "GENERAL"
    relevance_score: float = 0.0
    freshness_score: float = 0.0
    source_authority_score: float = 0.0
    confidence_score: float = 0.0
    cluster_id: str = ""
    cluster_size: int = 1
    dropped_count: int = 0

    def with_scores(
        self,
        *,
        entity_tags: tuple[str, ...],
        macro_or_micro: str,
        event_class: str,
        relevance_score: float,
        freshness_score: float,
        source_authority_score: float,
        confidence_score: float,
    ) -> NewsItem:
        return replace(
            self,
            entity_tags=entity_tags,
            macro_or_micro=macro_or_micro,
            event_class=event_class,
            relevance_score=_bounded_score(relevance_score),
            freshness_score=_bounded_score(freshness_score),
            source_authority_score=_bounded_score(source_authority_score),
            confidence_score=_bounded_score(confidence_score),
        )

    def with_cluster(self, *, cluster_id: str, cluster_size: int, dropped_count: int) -> NewsItem:
        return replace(
            self,
            cluster_id=cluster_id,
            cluster_size=cluster_size,
            dropped_count=dropped_count,
        )

    def to_public_dict(self) -> dict:
        return {
            "provider": self.provider,
            "source_name": self.source_name,
            "domain": self.domain,
            "title": self.title,
            "snippet": self.snippet,
            "url": self.url,
            "url_hash": self.url_hash,
            "title_hash": self.title_hash,
            "published_at": self.published_at,
            "fetched_at": self.fetched_at,
            "language": self.language,
            "entity_tags": list(self.entity_tags),
            "macro_or_micro": self.macro_or_micro,
            "event_class": self.event_class,
            "relevance_score": self.relevance_score,
            "freshness_score": self.freshness_score,
            "source_authority_score": self.source_authority_score,
            "confidence_score": self.confidence_score,
            "cluster_id": self.cluster_id,
            "cluster_size": self.cluster_size,
            "dropped_count": self.dropped_count,
        }


@dataclass(frozen=True)
class MacroObservation:
    provider: str
    series_id: str
    label: str
    observation_date: str
    value: float | None
    fetched_at: str
    status: str = "OK"

    def to_public_dict(self) -> dict:
        return {
            "provider": self.provider,
            "series_id": self.series_id,
            "label": self.label,
            "observation_date": self.observation_date,
            "value": self.value,
            "fetched_at": self.fetched_at,
            "status": self.status,
        }


@dataclass(frozen=True)
class NewsCluster:
    cluster_id: str
    representative_title: str
    macro_or_micro: str
    event_class: str
    source_count: int
    item_count: int
    dropped_count: int
    max_relevance_score: float

    def to_public_dict(self) -> dict:
        return {
            "cluster_id": self.cluster_id,
            "representative_title": self.representative_title,
            "macro_or_micro": self.macro_or_micro,
            "event_class": self.event_class,
            "source_count": self.source_count,
            "item_count": self.item_count,
            "dropped_count": self.dropped_count,
            "max_relevance_score": self.max_relevance_score,
        }


def make_news_item(
    *,
    provider: str,
    source_name: str,
    title: str,
    url: str,
    fetched_at: datetime,
    snippet: str | None = None,
    published_at: datetime | str | None = None,
    language: str | None = None,
    domain: str | None = None,
) -> NewsItem:
    safe_title = _clean_text(title)
    safe_snippet = _clean_text(snippet) if snippet else None
    safe_url = str(url or "").strip()
    parsed_domain = domain or urlparse(safe_url).netloc.lower()
    published = _as_z(parse_datetime(published_at)) if published_at else None
    return NewsItem(
        provider=provider,
        source_name=_clean_text(source_name) or provider,
        domain=parsed_domain,
        title=safe_title,
        snippet=safe_snippet,
        url=safe_url,
        url_hash=stable_hash(safe_url),
        title_hash=stable_hash(normalize_title(safe_title)),
        published_at=published,
        fetched_at=_as_z(fetched_at),
        language=language,
    )


def parse_datetime(value: datetime | str | None) -> datetime | None:
    if value is None or isinstance(value, datetime):
        return value
    raw = str(value).strip()
    if not raw:
        return None
    try:
        if raw.endswith("Z") and "T" in raw and "-" in raw:
            return datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(UTC)
        if re.fullmatch(r"\d{8}T\d{6}Z", raw):
            return datetime.strptime(raw, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
        if re.fullmatch(r"\d{14}", raw):
            return datetime.strptime(raw, "%Y%m%d%H%M%S").replace(tzinfo=UTC)
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
            return datetime.fromisoformat(raw).replace(tzinfo=UTC)
        return datetime.fromisoformat(raw).astimezone(UTC)
    except ValueError:
        return None


def normalize_title(title: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", title.lower())).strip()


def stable_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]


def utc_now_z() -> str:
    return _as_z(datetime.now(UTC))


def _as_z(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _clean_text(value: str | None) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _bounded_score(value: float) -> float:
    return max(0.0, min(1.0, float(value)))
