"""R-1 (WB3): reconciling COMMIT_UNKNOWN by an idempotent read (api/commit_reconciliation.py).

Deterministic and dependency-free: no database, no network, no clock. These tests pin the rules the
wiring keeps. SAVED only from a strict read that shows the run
as sent and every forecast prediction; NOT_SAVED only when the read proves the transaction did not
commit; anything unread stays COMMIT_UNKNOWN; and no payload is ever kept.
"""

from __future__ import annotations

import dataclasses
import itertools

import pytest

from crypto_probability_engine.api import analysis_service
from crypto_probability_engine.api import commit_reconciliation as reconcile

RUN = {"run_id": "run-1", "analysis_hash": "hash-1", "symbol": "BTC"}
ROWS = [{"prediction_id": "run-1-4H"}, {"prediction_id": "run-1-1D"},
        {"prediction_id": "oosb-run-1-4H"}]


def _pending(**changes) -> reconcile.UnknownCommit:
    return dataclasses.replace(reconcile.unknown_commit(RUN, ROWS, now=100.0), **changes)


def _stored(run=RUN, predictions=("run-1-1D", "run-1-4H")) -> reconcile.StoredCore:
    return reconcile.StoredCore(run=run, prediction_ids=frozenset(predictions))


def test_the_receipt_states_are_analysis_service_s() -> None:
    assert (reconcile.RECEIPT_SAVED, reconcile.RECEIPT_NOT_SAVED,
            reconcile.RECEIPT_COMMIT_UNKNOWN) == (analysis_service.RECEIPT_SAVED,
                                                  analysis_service.RECEIPT_NOT_SAVED,
                                                  analysis_service.RECEIPT_COMMIT_UNKNOWN)


def test_the_identity_is_the_run_its_hash_and_the_forecast_predictions_only() -> None:
    pending = reconcile.unknown_commit(RUN, ROWS, now=100.0)
    assert pending == reconcile.UnknownCommit("run-1", "hash-1", ("run-1-1D", "run-1-4H"), 100.0)
    assert {field.name for field in dataclasses.fields(pending)} == {
        "run_id", "analysis_hash", "prediction_ids", "first_seen", "attempts",
    }, "an identity, never a payload"


@pytest.mark.parametrize(
    ("run", "rows"),
    [
        ({"analysis_hash": "hash-1"}, ROWS),
        ({"run_id": "run-1"}, ROWS),
        ({"run_id": "", "analysis_hash": "hash-1"}, ROWS),
        (RUN, [{"prediction_id": "oosb-run-1-4H"}]),
        (RUN, []),
    ],
    ids=["no-run-id", "no-hash", "empty-run-id", "only-oos-rows", "no-rows"],
)
def test_without_a_decidable_identity_nothing_is_queued(run, rows) -> None:
    assert reconcile.unknown_commit(run, rows, now=100.0) is None


def test_the_run_as_sent_and_every_prediction_is_saved() -> None:
    assert reconcile.decide(_pending(), _stored(), now=101.0) == reconcile.Decision(
        "SAVED", reconcile.RECONCILED_COMMITTED, final=True)


def test_no_run_means_the_transaction_did_not_commit() -> None:
    assert reconcile.decide(_pending(), _stored(run=None, predictions=()), now=101.0) == (
        reconcile.Decision("NOT_SAVED", reconcile.RECONCILED_NOT_COMMITTED, final=True))


@pytest.mark.parametrize(
    "run",
    [{"run_id": "run-1", "analysis_hash": "another-hash"},
     {"run_id": "another-run", "analysis_hash": "hash-1"}],
    ids=["another-hash", "another-run"],
)
def test_another_stored_core_is_a_conflict(run) -> None:
    assert reconcile.decide(_pending(), _stored(run=run), now=101.0) == reconcile.Decision(
        "NOT_SAVED", reconcile.CONFLICT, final=True)


def test_the_run_without_every_prediction_is_an_incomplete_bundle() -> None:
    assert reconcile.decide(_pending(), _stored(predictions=("run-1-4H",)), now=101.0) == (
        reconcile.Decision("NOT_SAVED", reconcile.INCOMPLETE_BUNDLE, final=True))


def test_an_unreadable_store_stays_unknown_until_it_expires() -> None:
    assert reconcile.decide(_pending(), reconcile.UNREADABLE, now=101.0) == reconcile.Decision(
        "COMMIT_UNKNOWN", reconcile.RECONCILE_UNREADABLE, final=False)
    by_attempts = _pending(attempts=reconcile.MAX_ATTEMPTS - 1)
    assert reconcile.decide(by_attempts, reconcile.UNREADABLE, now=101.0) == reconcile.Decision(
        "COMMIT_UNKNOWN", reconcile.RECONCILE_EXPIRED, final=True)
    later = 100.0 + reconcile.TTL_SECONDS
    assert reconcile.decide(_pending(), reconcile.UNREADABLE, now=later) == reconcile.Decision(
        "COMMIT_UNKNOWN", reconcile.RECONCILE_EXPIRED, final=True)


def test_saved_only_ever_comes_from_the_run_as_sent_with_every_prediction() -> None:
    """Exhaustive over a small domain of reads: no other answer yields SAVED, and only a read
    (never Unreadable) yields NOT_SAVED."""

    runs = [None, RUN, {"run_id": "run-1", "analysis_hash": "x"}, {"run_id": "x",
                                                                  "analysis_hash": "hash-1"}]
    subsets = [frozenset(combo) for size in range(3)
               for combo in itertools.combinations(("run-1-1D", "run-1-4H"), size)]
    for run, predictions in itertools.product(runs, subsets):
        decision = reconcile.decide(_pending(), reconcile.StoredCore(run, predictions), now=101.0)
        complete = run == RUN and predictions == {"run-1-1D", "run-1-4H"}
        assert (decision.receipt == "SAVED") == complete, (run, predictions)
        assert decision.final and decision.receipt in {"SAVED", "NOT_SAVED"}
    assert reconcile.decide(_pending(), reconcile.UNREADABLE, now=101.0).receipt == (
        "COMMIT_UNKNOWN")


def test_the_list_keeps_one_entry_per_run_the_earliest() -> None:
    commits = reconcile.UnknownCommits(capacity=4)
    assert commits.add(_pending()) is None
    assert commits.add(_pending(first_seen=500.0)) is None
    assert len(commits) == 1 and commits.due()[0].first_seen == 100.0


def test_over_capacity_the_oldest_is_evicted_for_the_caller_to_expire() -> None:
    commits = reconcile.UnknownCommits(capacity=2)
    first, second, third = (_pending(run_id=f"run-{n}") for n in (1, 2, 3))
    assert commits.add(first) is None and commits.add(second) is None
    assert commits.add(third) == first
    assert [commit.run_id for commit in commits.due()] == ["run-2", "run-3"]
    with pytest.raises(ValueError):
        reconcile.UnknownCommits(capacity=0)


def test_a_final_decision_removes_the_entry_and_a_retry_counts_an_attempt() -> None:
    commits = reconcile.UnknownCommits()
    pending = _pending()
    commits.add(pending)
    commits.apply(pending, reconcile.Decision("COMMIT_UNKNOWN", reconcile.RECONCILE_UNREADABLE,
                                              final=False))
    assert commits.due()[0].attempts == 1
    commits.apply(commits.due()[0], reconcile.Decision("SAVED", reconcile.RECONCILED_COMMITTED,
                                                       final=True))
    assert len(commits) == 0
    commits.apply(pending, reconcile.Decision("SAVED", reconcile.RECONCILED_COMMITTED, final=True))
    assert len(commits) == 0, "applying to an absent entry changes nothing"


def test_the_model_is_wired_through_the_strict_read_only() -> None:
    """The owner authorized the pinned crossing: the service feeds the model read_core_strict
    (never get_run, whose failures fall back to the in-memory mirror)."""

    with open(analysis_service.__file__, encoding="utf-8") as handle:
        source = handle.read()
    wiring = source.split("def _reconcile_unknown_commits(", 1)[1].split("\ndef ", 1)[0]
    assert 'getattr(repository, "read_core_strict", None)' in wiring
    assert "get_run" not in wiring
