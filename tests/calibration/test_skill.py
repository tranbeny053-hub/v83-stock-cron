from __future__ import annotations

import pytest

from crypto_probability_engine.calibration.service import refresh_skill_evidence_cache
from crypto_probability_engine.calibration.skill import (
    cache_skill_evidence,
    classify_directional_skill,
    clear_skill_evidence_cache,
    get_cached_skill_evidence,
)
from crypto_probability_engine.config.defaults import (
    METHODOLOGY_VERSION,
    MIN_DIRECTIONAL_SAMPLES,
    MODEL_VERSION,
    SKILL_EVIDENCE_CACHE_TTL_SECONDS,
    SKILL_Z_THRESHOLD,
)


@pytest.fixture(autouse=True)
def isolate_skill_cache() -> None:
    clear_skill_evidence_cache()
    yield
    clear_skill_evidence_cache()


@pytest.mark.parametrize(
    ("timeframe", "n", "hits", "expected"),
    [
        ("15m", 110, 54, "NO_DEMONSTRATED_SKILL"),
        ("1H", 142, 88, "SKILL_DEMONSTRATED"),
        ("4H", 151, 102, "SKILL_DEMONSTRATED"),
        ("1D", 161, 84, "NO_DEMONSTRATED_SKILL"),
        ("1W", 134, 62, "NO_DEMONSTRATED_SKILL"),
        ("1M", 0, 0, "INSUFFICIENT_EVIDENCE"),
    ],
)
def test_production_evidence_sanity_classifies_from_counts(
    timeframe: str,
    n: int,
    hits: int,
    expected: str,
) -> None:
    evidence = classify_directional_skill(n, hits)

    assert timeframe
    assert evidence["verdict"] == expected
    assert evidence["n"] == n
    assert evidence["observed_directional_rate"] == (hits / n if n else None)


def test_minimum_directional_sample_boundary_is_exact() -> None:
    below = classify_directional_skill(MIN_DIRECTIONAL_SAMPLES - 1, 99)
    at_no_skill = classify_directional_skill(MIN_DIRECTIONAL_SAMPLES, 59)
    at_skill = classify_directional_skill(MIN_DIRECTIONAL_SAMPLES, 60)

    assert below["verdict"] == "INSUFFICIENT_EVIDENCE"
    assert at_no_skill["verdict"] == "NO_DEMONSTRATED_SKILL"
    assert at_skill["verdict"] == "SKILL_DEMONSTRATED"


def test_z_threshold_boundary_is_inclusive_and_exact() -> None:
    # n=2500 and h=1299 gives z=(2h-n)/sqrt(n)=98/50=1.96 exactly.
    assert (2 * 1299 - 2500) / (2500**0.5) == SKILL_Z_THRESHOLD
    at_threshold = classify_directional_skill(2500, 1299)
    below_threshold = classify_directional_skill(2500, 1298)

    assert at_threshold["verdict"] == "SKILL_DEMONSTRATED"
    assert below_threshold["verdict"] == "NO_DEMONSTRATED_SKILL"


def test_zero_samples_is_distinct_from_observed_no_skill() -> None:
    zero = classify_directional_skill(0, 0)
    observed = classify_directional_skill(100, 50)

    assert zero == {
        "verdict": "INSUFFICIENT_EVIDENCE",
        "n": 0,
        "observed_directional_rate": None,
    }
    assert observed["verdict"] == "NO_DEMONSTRATED_SKILL"
    assert observed["observed_directional_rate"] == 0.5


def test_cache_miss_and_ttl_expiry_fail_safe() -> None:
    assert get_cached_skill_evidence("4H", now=1000.0)["verdict"] == (
        "INSUFFICIENT_EVIDENCE"
    )
    cache_skill_evidence("4H", classify_directional_skill(151, 102), now=1000.0)

    assert get_cached_skill_evidence(
        "4H",
        now=1000.0 + SKILL_EVIDENCE_CACHE_TTL_SECONDS - 0.01,
    )["verdict"] == "SKILL_DEMONSTRATED"
    assert get_cached_skill_evidence(
        "4H",
        now=1000.0 + SKILL_EVIDENCE_CACHE_TTL_SECONDS,
    )["verdict"] == "INSUFFICIENT_EVIDENCE"


def test_refresh_uses_current_calibration_cohort_and_computed_rows() -> None:
    class FixtureRepository:
        def __init__(self) -> None:
            self.calls: list[dict] = []

        def fetch_resolved_prediction_outcomes_for_calibration(self, **kwargs) -> list[dict]:
            self.calls.append(kwargs)
            if kwargs["timeframe"] == "4H":
                return _directional_rows(n=100, hits=60)
            return []

        def repository_type(self) -> str:
            return "SUPABASE_POSTGRES"

    repository = FixtureRepository()
    refresh_skill_evidence_cache(repository)  # type: ignore[arg-type]

    assert get_cached_skill_evidence("4H") == {
        "verdict": "SKILL_DEMONSTRATED",
        "n": 100,
        "observed_directional_rate": 0.6,
    }
    assert get_cached_skill_evidence("1M")["verdict"] == "INSUFFICIENT_EVIDENCE"
    assert all(call["model_version"] == MODEL_VERSION for call in repository.calls)
    assert all(
        call["methodology_version"] == METHODOLOGY_VERSION for call in repository.calls
    )


def test_refresh_repository_failure_caches_insufficient_without_raising() -> None:
    class BrokenRepository:
        def fetch_resolved_prediction_outcomes_for_calibration(self, **kwargs) -> list[dict]:
            raise TimeoutError("calibration unavailable")

    refresh_skill_evidence_cache(BrokenRepository())  # type: ignore[arg-type]

    assert get_cached_skill_evidence("15m") == {
        "verdict": "INSUFFICIENT_EVIDENCE",
        "n": 0,
        "observed_directional_rate": None,
    }


def _directional_rows(*, n: int, hits: int) -> list[dict]:
    hit = {
        "p_up_frac": 0.6,
        "p_down_frac": 0.3,
        "p_timeout_frac": 0.1,
        "realized_label": "UP",
    }
    miss = {**hit, "realized_label": "DOWN"}
    return [dict(hit) for _ in range(hits)] + [dict(miss) for _ in range(n - hits)]
