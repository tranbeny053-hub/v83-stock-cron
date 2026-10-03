"""WB3's R-1a, wired: analysis_service._reconcile_unknown_commits over read_core_strict.

The owner's rulings (2026-10-03): R-1a authorized ("wire it into analysis_service.py"); S8 =
Option 1 ("honest NOT_SAVED during the open-circuit/outage window; no payload retry, no durable
outbox"). Deterministic: a fake repository answers read_core_strict; events are captured.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from crypto_probability_engine.api import analysis_service
from crypto_probability_engine.api import commit_reconciliation as reconcile


def _work(run_id: str = "run-1", analysis_hash: str = "hash-1") -> SimpleNamespace:
    return SimpleNamespace(
        run_summary={"run_id": run_id, "analysis_hash": analysis_hash},
        prediction_rows=({"prediction_id": f"{run_id}-4H"},),
    )


class Reader:
    """A repository with read_core_strict: scripted answers, every read kept."""

    def __init__(self, *answers) -> None:
        self.answers = list(answers)
        self.reads: list[tuple[str, tuple[str, ...]]] = []

    def read_core_strict(self, run_id: str, prediction_ids) -> dict | None:
        self.reads.append((run_id, tuple(prediction_ids)))
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer


def _stored(run_id: str = "run-1", analysis_hash: str = "hash-1") -> dict:
    return {"run": {"run_id": run_id, "analysis_hash": analysis_hash},
            "prediction_ids": [f"{run_id}-4H"]}


@pytest.fixture(autouse=True)
def fresh(monkeypatch) -> list[tuple[str, dict]]:
    events: list[tuple[str, dict]] = []
    monkeypatch.setattr(analysis_service, "_UNKNOWN_COMMITS", reconcile.UnknownCommits(capacity=2))
    monkeypatch.setattr(analysis_service, "emit", lambda event, **fields: events.append(
        (event, fields)))
    return events


def _reconciled(events) -> list[tuple]:
    return [(f["run_id"], f["receipt"], f["receipt_reason"], f["attempts"]) for event, f in events
            if event == "persistence_reconciled"]


def test_a_commit_unknown_is_kept_as_an_identity_and_nothing_is_read() -> None:
    reader = Reader()
    analysis_service._reconcile_unknown_commits(_work(), reader, "COMMIT_UNKNOWN")
    assert analysis_service._UNKNOWN_COMMITS.due() == (
        reconcile.UnknownCommit("run-1", "hash-1", ("run-1-4H",),
                                analysis_service._UNKNOWN_COMMITS.due()[0].first_seen),)
    assert reader.reads == []


def test_the_next_saved_receipt_reconciles_it_by_one_strict_read(fresh) -> None:
    reader = Reader(_stored())
    analysis_service._reconcile_unknown_commits(_work(), reader, "COMMIT_UNKNOWN")
    analysis_service._reconcile_unknown_commits(_work("run-2"), reader, "SAVED")
    assert reader.reads == [("run-1", ("run-1-4H",))]
    assert _reconciled(fresh) == [("run-1", "SAVED", reconcile.RECONCILED_COMMITTED, 1)]
    assert len(analysis_service._UNKNOWN_COMMITS) == 0


def test_a_rolled_back_bundle_reconciles_to_not_saved(fresh) -> None:
    reader = Reader({"run": None, "prediction_ids": []})
    analysis_service._reconcile_unknown_commits(_work(), reader, "COMMIT_UNKNOWN")
    analysis_service._reconcile_unknown_commits(_work("run-2"), reader, "SAVED")
    assert _reconciled(fresh) == [("run-1", "NOT_SAVED", reconcile.RECONCILED_NOT_COMMITTED, 1)]


def test_an_unreadable_store_keeps_it_and_ends_the_round(fresh) -> None:
    reader = Reader(None)
    analysis_service._reconcile_unknown_commits(_work("run-1"), reader, "COMMIT_UNKNOWN")
    analysis_service._reconcile_unknown_commits(_work("run-2"), reader, "COMMIT_UNKNOWN")
    analysis_service._reconcile_unknown_commits(_work("run-3"), reader, "SAVED")
    assert reader.reads == [("run-1", ("run-1-4H",))], "the round stops at the first unreadable"
    assert [c.attempts for c in analysis_service._UNKNOWN_COMMITS.due()] == [1, 0]
    assert _reconciled(fresh) == []


def test_eviction_over_capacity_is_reported_as_expired(fresh) -> None:
    reader = Reader()
    for run_id in ("run-1", "run-2", "run-3"):
        analysis_service._reconcile_unknown_commits(_work(run_id), reader, "COMMIT_UNKNOWN")
    assert _reconciled(fresh) == [("run-1", "COMMIT_UNKNOWN", reconcile.RECONCILE_EXPIRED, 0)]
    assert [c.run_id for c in analysis_service._UNKNOWN_COMMITS.due()] == ["run-2", "run-3"]


@pytest.mark.parametrize("receipt", ["NOT_SAVED", None, "SOMETHING_ELSE"])
def test_s8_option_1_a_not_saved_is_never_kept_or_retried(receipt, fresh) -> None:
    reader = Reader()
    analysis_service._reconcile_unknown_commits(_work(), reader, receipt)
    assert len(analysis_service._UNKNOWN_COMMITS) == 0 and reader.reads == [] and fresh == []


@pytest.mark.parametrize("receipt", ["NOT_SAVED", None, "COMMIT_UNKNOWN"])
def test_only_a_saved_receipt_starts_a_round_of_reads(receipt, fresh) -> None:
    """After a NOT_SAVED (an outage) or another unknown, the store may not answer: reading then
    would only spend the pending entries' attempts. Only SAVED proves it answers."""

    reader = Reader()
    analysis_service._reconcile_unknown_commits(_work("run-1"), reader, "COMMIT_UNKNOWN")
    analysis_service._reconcile_unknown_commits(_work("run-2"), reader, receipt)
    assert reader.reads == [], f"{receipt} must not read"
    assert [c.attempts for c in analysis_service._UNKNOWN_COMMITS.due()][0] == 0


def test_a_repository_without_the_strict_read_takes_no_part(fresh) -> None:
    analysis_service._reconcile_unknown_commits(_work(), object(), "COMMIT_UNKNOWN")
    analysis_service._reconcile_unknown_commits(_work(), None, "COMMIT_UNKNOWN")
    assert len(analysis_service._UNKNOWN_COMMITS) == 0


def test_a_failing_read_never_raises_and_changes_nothing(fresh) -> None:
    reader = Reader(RuntimeError("boom"))
    analysis_service._reconcile_unknown_commits(_work(), reader, "COMMIT_UNKNOWN")
    analysis_service._reconcile_unknown_commits(_work("run-2"), reader, "SAVED")
    assert len(analysis_service._UNKNOWN_COMMITS) == 1 and _reconciled(fresh) == []


def test_best_effort_persist_feeds_its_receipts_to_the_reconciler(monkeypatch, fresh) -> None:
    reader = Reader(_stored())
    work = SimpleNamespace(**vars(_work()), prediction_origin="USER_REQUESTED")
    confirmations = iter([
        SimpleNamespace(receipt="COMMIT_UNKNOWN", background_status="UNAVAILABLE"),
        SimpleNamespace(receipt="SAVED", background_status="OK"),
    ])
    monkeypatch.setattr(analysis_service, "_persist_work_confirmed",
                        lambda work, repository: next(confirmations))
    monkeypatch.setattr(analysis_service, "_emit_persistence_receipt", lambda *args: None)
    assert analysis_service._best_effort_persist(work, reader) == "UNAVAILABLE"
    assert analysis_service._best_effort_persist(_work("run-2"), reader) == "OK"
    assert _reconciled(fresh) == [("run-1", "SAVED", reconcile.RECONCILED_COMMITTED, 1)]


def test_an_exception_with_prediction_rows_is_an_unknown_commit(monkeypatch, fresh) -> None:
    def boom(work, repository):
        raise RuntimeError("lost")

    monkeypatch.setattr(analysis_service, "_persist_work_confirmed", boom)
    monkeypatch.setattr(analysis_service, "_emit_persistence_receipt", lambda *args: None)
    with pytest.raises(RuntimeError):
        analysis_service._best_effort_persist(_work(), Reader())
    assert [c.run_id for c in analysis_service._UNKNOWN_COMMITS.due()] == ["run-1"]


def test_the_reconciled_event_is_allowlisted() -> None:
    from crypto_probability_engine.telemetry import events

    clean = events.sanitize("persistence_reconciled", {"run_id": "r", "attempts": 2,
                                                        "receipt": "SAVED", "payload": "x"})
    assert clean == {"event": "persistence_reconciled", "attempts": 2, "receipt": "SAVED",
                     "run_id": "r"}
