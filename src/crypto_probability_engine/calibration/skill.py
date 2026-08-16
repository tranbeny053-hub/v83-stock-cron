"""Deterministic directional-skill classification and in-process evidence cache."""

from __future__ import annotations

import time
from threading import Lock
from typing import cast

from crypto_probability_engine.calibration.schemas import SkillEvidence, SkillVerdict
from crypto_probability_engine.config.defaults import (
    DEFAULT_PHASE1A,
    MIN_DIRECTIONAL_SAMPLES,
    SKILL_EVIDENCE_CACHE_TTL_SECONDS,
    SKILL_Z_THRESHOLD,
)

_CacheEntry = tuple[float, SkillEvidence]
_cache: dict[str, _CacheEntry] = {}
_cache_lock = Lock()
_refresh_in_flight = False


def classify_directional_skill(
    n: int,
    h: int,
    *,
    min_directional_samples: int = MIN_DIRECTIONAL_SAMPLES,
    skill_z_threshold: float = SKILL_Z_THRESHOLD,
) -> SkillEvidence:
    """Classify observed directional hits against chance with a normal approximation."""

    if (
        isinstance(n, bool)
        or isinstance(h, bool)
        or not isinstance(n, int)
        or not isinstance(h, int)
        or n < 0
        or h < 0
        or h > n
    ):
        return insufficient_skill_evidence()

    observed_rate = h / n if n else None
    if n < min_directional_samples:
        return {
            "verdict": "INSUFFICIENT_EVIDENCE",
            "n": n,
            "observed_directional_rate": observed_rate,
        }

    # Algebraically identical to (p - 0.5) / sqrt(0.25 / n), while avoiding
    # cancellation at exact configured decision boundaries.
    z_score = (2 * h - n) / (n**0.5)
    verdict: SkillVerdict = (
        "SKILL_DEMONSTRATED"
        if z_score >= skill_z_threshold
        else "NO_DEMONSTRATED_SKILL"
    )
    return {
        "verdict": verdict,
        "n": n,
        "observed_directional_rate": observed_rate,
    }


def insufficient_skill_evidence() -> SkillEvidence:
    """Return the fail-safe verdict used for missing or unavailable evidence."""

    return {
        "verdict": "INSUFFICIENT_EVIDENCE",
        "n": 0,
        "observed_directional_rate": None,
    }


def get_cached_skill_evidence(
    timeframe: str,
    *,
    now: float | None = None,
) -> SkillEvidence:
    """Read evidence without I/O; misses, expiry, and cache errors fail safe."""

    try:
        checked_at = time.monotonic() if now is None else float(now)
        with _cache_lock:
            cached = _cache.get(timeframe)
            if (
                cached is not None
                and checked_at - cached[0] < SKILL_EVIDENCE_CACHE_TTL_SECONDS
            ):
                return {
                    "verdict": cached[1]["verdict"],
                    "n": cached[1]["n"],
                    "observed_directional_rate": cached[1]["observed_directional_rate"],
                }
    except Exception:
        pass
    return insufficient_skill_evidence()


def cache_skill_evidence(
    timeframe: str,
    evidence: SkillEvidence,
    *,
    now: float | None = None,
) -> None:
    """Store a computed verdict for one supported timeframe."""

    if timeframe not in DEFAULT_PHASE1A.timeframes:
        return
    stored_at = time.monotonic() if now is None else float(now)
    normalized = _normalize_skill_evidence(evidence)
    with _cache_lock:
        _cache[timeframe] = (stored_at, normalized)


def reserve_skill_evidence_refresh(*, now: float | None = None) -> bool:
    """Reserve one refresh when any timeframe is absent or expired."""

    global _refresh_in_flight
    try:
        checked_at = time.monotonic() if now is None else float(now)
        with _cache_lock:
            if _refresh_in_flight:
                return False
            refresh_due = any(
                timeframe not in _cache
                or checked_at - _cache[timeframe][0]
                >= SKILL_EVIDENCE_CACHE_TTL_SECONDS
                for timeframe in DEFAULT_PHASE1A.timeframes
            )
            if not refresh_due:
                return False
            _refresh_in_flight = True
            return True
    except Exception:
        return False


def finish_skill_evidence_refresh() -> None:
    """Release the single-refresh reservation."""

    global _refresh_in_flight
    with _cache_lock:
        _refresh_in_flight = False


def clear_skill_evidence_cache() -> None:
    """Clear process cache and refresh state for deterministic tests."""

    global _refresh_in_flight
    with _cache_lock:
        _cache.clear()
        _refresh_in_flight = False


def _normalize_skill_evidence(evidence: SkillEvidence) -> SkillEvidence:
    try:
        verdict = str(evidence["verdict"])
        n = int(evidence["n"])
        rate = evidence["observed_directional_rate"]
        if verdict not in {
            "INSUFFICIENT_EVIDENCE",
            "SKILL_DEMONSTRATED",
            "NO_DEMONSTRATED_SKILL",
        }:
            raise ValueError("unknown skill verdict")
        if n < 0 or (rate is not None and not 0.0 <= float(rate) <= 1.0):
            raise ValueError("invalid skill evidence")
        return {
            "verdict": cast(SkillVerdict, verdict),
            "n": n,
            "observed_directional_rate": None if rate is None else float(rate),
        }
    except (KeyError, TypeError, ValueError):
        return insufficient_skill_evidence()
