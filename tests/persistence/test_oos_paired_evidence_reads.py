"""The paired-evidence read: Tier-1 fidelity and the readiness safety boundary.

No live database is touched anywhere in this file.
"""

from __future__ import annotations

import inspect
from datetime import UTC, datetime, timedelta

import pytest

from crypto_probability_engine.persistence import repository as repo_module
from crypto_probability_engine.persistence.repository import (
    InMemoryPersistenceRepository,
)

REFERENCE = datetime(2026, 8, 21, 4, 0, 0, tzinfo=UTC)
RUN = "oosb-" + "a" * 32


def _prediction(
    run_id: str,
    arm: str,
    *,
    methodology: str,
    timeframe: str = "4H",
    reference: datetime | None = None,
    origin: str = "SCHEDULED_SHADOW_EVIDENCE",
) -> dict:
    reference = reference or REFERENCE
    return {
        "prediction_id": f"{run_id}:{timeframe}:{arm}",
        "run_id": run_id,
        "symbol": "BTC",
        "normalized_symbol": "BTC/USDT",
        "timeframe": timeframe,
        "horizon_bars": 6,
        "predicted_at_utc": reference,
        "reference_close_utc": reference,
        "horizon_end_utc": reference + timedelta(hours=24),
        "p_up_frac": 0.6,
        "p_down_frac": 0.25,
        "p_timeout_frac": 0.15,
        "methodology_version": methodology,
        "prediction_origin": origin,
    }


def _pair(repo, run_id: str, **kwargs) -> None:
    repo.save_prediction(
        _prediction(run_id, "BASELINE", methodology="heuristic-v1-wave4b0", **kwargs)
    )
    repo.save_prediction(
        _prediction(run_id, "CANDIDATE", methodology="distributional-v1", **kwargs)
    )


def _outcome(prediction_id: str, label: str = "UP") -> dict:
    return {
        "prediction_id": prediction_id,
        "resolved_at_utc": "2026-08-22T04:00:00Z",
        "outcome_close_utc": "2026-08-22T04:00:00Z",
        "outcome_reference_price": 101.0,
        "terminal_return_frac": 0.01,
        "realized_label": label,
    }


def test_readiness_projection_omits_every_probability() -> None:
    """The structural safety boundary: no probability reaches a readiness run."""

    repo = InMemoryPersistenceRepository()
    _pair(repo, RUN)
    rows = repo.fetch_oos_paired_evidence(include_probabilities=False)
    assert len(rows) == 1
    assert not [key for key in rows[0] if "p_up" in key or "p_down" in key or "p_timeout" in key]


def test_consumption_projection_carries_both_arms_probabilities() -> None:
    repo = InMemoryPersistenceRepository()
    _pair(repo, RUN)
    row = repo.fetch_oos_paired_evidence(include_probabilities=True)[0]
    for arm in ("baseline", "candidate"):
        for field in ("p_up_frac", "p_down_frac", "p_timeout_frac"):
            assert f"{arm}_{field}" in row


def test_readiness_sql_selects_no_probability_column() -> None:
    """Assert on the generated SQL, not only on the returned dict."""

    source = inspect.getsource(repo_module._fetch_oos_prediction_rows)
    assert "OOS_EVIDENCE_BASE_COLUMNS" in source
    assert "p_up_frac" not in [c for c in repo_module.OOS_EVIDENCE_BASE_COLUMNS]
    captured: dict[str, str] = {}

    class _Cursor:
        def execute(self, sql, params=None):
            captured["sql"] = sql

        def fetchall(self):
            return []

    repo_module._fetch_oos_prediction_rows(_Cursor(), include_probabilities=False)
    for column in repo_module.OOS_PROBABILITY_FIELDS:
        assert column not in captured["sql"]

    repo_module._fetch_oos_prediction_rows(_Cursor(), include_probabilities=True)
    for column in repo_module.OOS_PROBABILITY_FIELDS:
        assert column in captured["sql"]


def test_tier1_population_is_identical_to_the_one_that_fixed_T0() -> None:
    """Anything the paired read returns must also be a T0 candidate, and vice versa."""

    repo = InMemoryPersistenceRepository()
    _pair(repo, RUN)
    _pair(repo, "oosb-" + "b" * 32, reference=REFERENCE + timedelta(days=1))
    # a non-qualifying group: wrong candidate methodology
    odd = "oosb-" + "c" * 32
    repo.save_prediction(_prediction(odd, "BASELINE", methodology="heuristic-v1-wave4b0"))
    repo.save_prediction(_prediction(odd, "CANDIDATE", methodology="something-else"))

    rows = repo.fetch_oos_paired_evidence(include_probabilities=False)
    assert len(rows) == 2
    assert repo.fetch_oos_t0() == min(row["reference_close_utc"] for row in rows)


def test_unresolved_and_disagreeing_arms_survive_the_read_and_are_judged_later() -> None:
    """The read is a faithful dump; Tier-2 admission is the layer that rejects."""

    repo = InMemoryPersistenceRepository()
    _pair(repo, RUN)
    repo.save_prediction_outcome(_outcome(f"{RUN}:4H:BASELINE", "UP"))
    row = repo.fetch_oos_paired_evidence(include_probabilities=False)[0]
    assert row["baseline_realized_label"] == "UP"
    assert row["candidate_realized_label"] is None


def test_the_write_path_already_refuses_a_non_shadow_oos_origin() -> None:
    """The stronger property: the anomaly cannot be created through save_prediction."""

    repo = InMemoryPersistenceRepository()
    with pytest.raises(ValueError, match="shadow-evidence origin"):
        repo.save_prediction(
            _prediction(RUN, "BASELINE", methodology="heuristic-v1-wave4b0",
                        origin="USER_REQUESTED")
        )


def test_origin_anomalies_are_counted_and_never_filtered() -> None:
    """Defence in depth for rows the guarded write path did not create.

    save_prediction fails closed on a non-shadow OOS origin, so an anomaly can only
    arrive from somewhere else — a direct database write, a migration, or a build
    predating that guard. The store is therefore seeded directly here, which is the
    only way to exercise a detector whose whole purpose is catching rows the write
    path never saw.
    """

    repo = InMemoryPersistenceRepository()
    _pair(repo, RUN)
    for prediction_id in (f"{RUN}:4H:BASELINE", f"{RUN}:4H:CANDIDATE"):
        repo._predictions[prediction_id]["prediction_origin"] = "USER_REQUESTED"

    assert repo.count_oos_origin_anomalies() == 2
    assert len(repo.fetch_oos_paired_evidence(include_probabilities=False)) == 1, (
        "an origin anomaly must be reported, not silently removed from the population"
    )


def test_evidence_order_is_deterministic() -> None:
    """Snapshot identity depends on a stable order."""

    rows_a = []
    for insertion in ([0, 1, 2], [2, 0, 1]):
        repo = InMemoryPersistenceRepository()
        for index in insertion:
            _pair(repo, f"oosb-{index:032x}", reference=REFERENCE + timedelta(days=index))
        evidence = repo.fetch_oos_paired_evidence(include_probabilities=False)
        rows_a.append([r["reference_close_utc"] for r in evidence])
    assert rows_a[0] == rows_a[1]


def test_feature_diagnostics_tolerate_a_missing_snapshot() -> None:
    repo = InMemoryPersistenceRepository()
    _pair(repo, RUN)
    rows = repo.fetch_oos_feature_diagnostics()
    assert len(rows) == 2
    assert all(row["regime"] is None for row in rows)


def test_the_rest_fallback_refuses_to_claim_the_one_look_seal() -> None:
    """Only Postgres can provide an atomic durable claim, so only Postgres may seal."""

    from crypto_probability_engine.persistence import repository as module

    for name in (
        "claim_section_5a_seal",
        "fetch_section_5a_seal",
        "advance_section_5a_seal_state",
    ):
        method = getattr(module.SupabaseRestRepository, name)
        source = inspect.getsource(method)
        assert "_SEAL_POSTGRES_ONLY" in source, name
    assert "must never be used to spend the look" in module._SEAL_POSTGRES_ONLY


def test_the_seal_claim_is_a_single_conditional_insert() -> None:
    """Claim and raw capture must be ONE write: an INSERT that conflicts on a singleton."""

    from crypto_probability_engine.persistence import repository as module

    sql = inspect.getsource(module._claim_section_5a_seal_row)
    assert "INSERT INTO public.section_5a_evaluation_seal" in sql
    assert "ON CONFLICT (seal_id) DO NOTHING" in sql
    assert "snapshot_payload" in sql, "the raw evidence rides along with the claim"
    assert sql.count("cursor.execute") == 1, "one statement, no window between two writes"


def test_in_memory_seal_is_claimed_exactly_once() -> None:
    repo = InMemoryPersistenceRepository()
    assert repo.fetch_section_5a_seal() is None
    assert repo.claim_section_5a_seal({"evidence_snapshot_id": "abc"}) is True
    assert repo.claim_section_5a_seal({"evidence_snapshot_id": "def"}) is False
    assert repo.fetch_section_5a_seal()["evidence_snapshot_id"] == "abc"
