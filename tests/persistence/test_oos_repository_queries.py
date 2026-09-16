from __future__ import annotations

from datetime import UTC, datetime, timedelta

from crypto_probability_engine.persistence.repository import (
    InMemoryPersistenceRepository,
)

REFERENCE = datetime(2026, 8, 20, 8, tzinfo=UTC)
T0 = datetime(2026, 8, 21, 4, tzinfo=UTC)


def _row(
    run_suffix: str,
    arm: str,
    methodology: str,
    *,
    origin: str = "SCHEDULED_SHADOW_EVIDENCE",
    reference_close: datetime = REFERENCE,
) -> dict:
    run_id = f"oosb-{run_suffix * 32}"
    return {
        "prediction_id": f"{run_id}:1H:{arm}",
        "run_id": run_id,
        "normalized_symbol": "BTC/USDT",
        "timeframe": "1H",
        "reference_close_utc": reference_close,
        "methodology_version": methodology,
        "prediction_origin": origin,
    }


def test_occasion_guard_is_strictly_oos_scoped_and_counts_orphan() -> None:
    repository = InMemoryPersistenceRepository()
    repository.save_prediction(
        {
            "prediction_id": "ordinary:1H",
            "run_id": "ordinary",
            "normalized_symbol": "BTC/USDT",
            "timeframe": "1H",
            "reference_close_utc": REFERENCE,
            "prediction_origin": "USER_REQUESTED",
        }
    )
    assert not repository.oos_occasion_exists("BTC/USDT", "1H", REFERENCE)

    repository.save_prediction(_row("a", "BASELINE", "heuristic-v1-wave4b0"))
    assert repository.oos_occasion_exists("BTC/USDT", "1H", REFERENCE)
    assert repository.count_oos_occasion_rows("BTC/USDT", "1H", REFERENCE) == 1


def test_t0_requires_exact_same_run_pair_and_is_idempotent() -> None:
    repository = InMemoryPersistenceRepository()
    repository.save_prediction(_row("a", "BASELINE", "heuristic-v1-wave4b0"))
    repository.save_prediction(_row("b", "CANDIDATE", "distributional-v1"))
    assert repository.fetch_oos_t0() is None

    repository.save_prediction(_row("a", "CANDIDATE", "wrong-version"))
    assert repository.fetch_oos_t0() is None

    exact = InMemoryPersistenceRepository()
    exact.save_prediction(_row("c", "BASELINE", "heuristic-v1-wave4b0"))
    exact.save_prediction(_row("c", "CANDIDATE", "distributional-v1"))
    assert exact.fetch_oos_t0() == REFERENCE
    assert exact.fetch_oos_t0() == REFERENCE


def test_t0_rejects_candidate_methodology_on_baseline_arm() -> None:
    repository = InMemoryPersistenceRepository()
    repository.save_prediction(_row("d", "BASELINE", "distributional-v1"))
    repository.save_prediction(_row("d", "CANDIDATE", "distributional-v1"))

    assert repository.fetch_oos_t0() is None


def test_t0_does_not_move_when_later_qualifying_pairs_are_inserted() -> None:
    repository = InMemoryPersistenceRepository()

    for arm, methodology in (
        ("BASELINE", "heuristic-v1-wave4b0"),
        ("CANDIDATE", "distributional-v1"),
    ):
        repository.save_prediction(
            _row("e", arm, methodology, reference_close=T0)
        )
    assert repository.fetch_oos_t0() == T0

    for suffix, later_reference in (
        ("f", T0 + timedelta(minutes=15)),
        ("0", T0 + timedelta(hours=1)),
    ):
        for arm, methodology in (
            ("BASELINE", "heuristic-v1-wave4b0"),
            ("CANDIDATE", "distributional-v1"),
        ):
            repository.save_prediction(
                _row(
                    suffix,
                    arm,
                    methodology,
                    reference_close=later_reference,
                )
            )
        assert repository.fetch_oos_t0() == T0
