"""Plan §10: every background save leaves one persistence receipt, and the receipt changes nothing.

The receipt reports what the save confirmed. It never alters the returned status, never swallows an
exception that was raised before it existed, and refused or failed submissions are recorded too.
"""

from __future__ import annotations

import threading

import pytest

from crypto_probability_engine.api import analysis_service
from crypto_probability_engine.api.analysis_service import (
    PersistenceWork,
    _best_effort_persist,
    _submit_persistence_work,
)
from crypto_probability_engine.persistence.repository import (
    InMemoryPersistenceRepository,
    OOSArmIdentityConflict,
)
from crypto_probability_engine.telemetry.events import EVENTS_SINK


def _work(run_id: str, *, predictions: int = 1) -> PersistenceWork:
    ids = [f"{run_id}:{index}" for index in range(predictions)]
    return PersistenceWork(
        run_summary={"run_id": run_id},
        timeframe_result={"run_id": run_id, "timeframe": "4H"},
        provider_observations=({"run_id": run_id, "provider": "fixture"},),
        prediction_rows=tuple({"prediction_id": pid} for pid in ids),
        feature_snapshot_rows=tuple({"prediction_id": pid, "snapshot_hash": "h"} for pid in ids),
    )


def _events(name: str, run_id: str) -> list[dict]:
    return [e for e in EVENTS_SINK.events if e["event"] == name and e.get("run_id") == run_id]


def test_a_successful_save_leaves_one_receipt_matching_its_status() -> None:
    status = _best_effort_persist(_work("run-receipt-ok", predictions=2),
                                  InMemoryPersistenceRepository())
    (receipt,) = _events("persistence_receipt", "run-receipt-ok")
    assert receipt["repository"] == "InMemoryPersistenceRepository"
    assert receipt["background_status"] == status
    assert (receipt["overall"], receipt["prediction"], receipt["feature_snapshot"]) == (
        "OK", "STATELESS", "INSERTED")
    assert receipt["prediction_rows"] == 2 and receipt["error_class"] is None
    assert receipt["derivatives_snapshot"] is None and isinstance(receipt["duration_ms"], float)


class _FailingRepository:
    def __init__(self, error: Exception) -> None:
        self.error = error
        self.marked = False

    def persistence_status(self) -> str:
        return "OK"

    def mark_unavailable(self) -> str:
        self.marked = True
        return "UNAVAILABLE"

    def save_run(self, summary: dict) -> str:
        raise self.error

    def save_timeframe_result(self, row: dict) -> str:
        return "OK"

    def save_provider_observation(self, row: dict) -> str:
        return "OK"


def test_a_failed_save_is_receipted_unavailable_and_still_marks_the_repository() -> None:
    repository = _FailingRepository(RuntimeError("database unreachable"))
    assert _best_effort_persist(_work("run-receipt-down"), repository) == "UNAVAILABLE"
    assert repository.marked is True
    (receipt,) = _events("persistence_receipt", "run-receipt-down")
    assert (receipt["overall"], receipt["background_status"]) == ("UNAVAILABLE", "UNAVAILABLE")
    assert receipt["repository"] == "_FailingRepository"


def test_an_identity_conflict_is_receipted_and_still_raised() -> None:
    repository = _FailingRepository(OOSArmIdentityConflict("occupied"))
    with pytest.raises(OOSArmIdentityConflict):
        _best_effort_persist(_work("run-receipt-conflict"), repository)
    (receipt,) = _events("persistence_receipt", "run-receipt-conflict")
    assert receipt["error_class"] == "OOSArmIdentityConflict" and receipt["overall"] is None


def test_a_failing_receipt_never_changes_the_status(monkeypatch: pytest.MonkeyPatch) -> None:
    def broken(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("telemetry down")

    monkeypatch.setattr(analysis_service, "emit", broken)
    assert _best_effort_persist(_work("run-receipt-quiet"), InMemoryPersistenceRepository()) == (
        _best_effort_persist(_work("run-receipt-quiet-2"), InMemoryPersistenceRepository()))


def test_a_refused_admission_and_a_failed_submission_are_recorded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = _FailingRepository(RuntimeError("unused"))
    monkeypatch.setattr(analysis_service, "_PERSISTENCE_ADMISSION", threading.BoundedSemaphore(1))
    analysis_service._PERSISTENCE_ADMISSION.acquire()
    _submit_persistence_work(repository, _work("run-refused"))
    (refused,) = _events("persistence_admission_refused", "run-refused")
    assert refused["repository"] == "_FailingRepository" and repository.marked is True

    class _BrokenExecutor:
        def submit(self, *_args: object) -> None:
            raise RuntimeError("executor shut down")

    monkeypatch.setattr(analysis_service, "_PERSISTENCE_ADMISSION", threading.BoundedSemaphore(1))
    monkeypatch.setattr(analysis_service, "_PERSISTENCE_EXECUTOR", _BrokenExecutor())
    _submit_persistence_work(repository, _work("run-submit-failed"))
    (failed,) = _events("persistence_submit_failed", "run-submit-failed")
    assert failed["error_class"] == "RuntimeError"
    assert analysis_service._PERSISTENCE_ADMISSION.acquire(blocking=False), "the permit came back"
