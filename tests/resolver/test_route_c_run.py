"""Route C end to end, with the in-memory status store: a stamped CROSS_PROVIDER row resolves on
its reference venue, the due scan's exclusions, quarantine, backoff, the outcome conflict, N2's
selection and budget, the outage guard, a failed status batch, and main()'s exit codes. The legacy
path is unchanged for the REST and in-memory repositories."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import psycopg
import pytest

from crypto_probability_engine.adapters.types import ProviderError
from crypto_probability_engine.config.settings import Settings
from crypto_probability_engine.persistence.repository import (
    InMemoryPersistenceRepository,
    SupabaseRestRepository,
)
from crypto_probability_engine.resolution import rq_v1
from crypto_probability_engine.resolution.status_store import (
    STATUS_COLUMNS,
    DueScan,
    InMemoryStatusStore,
)
from scripts import resolve_outcomes
from tests.resolver._route_c_rows import (
    NOW,
    PROVIDERS,
    Clock,
    Fetch,
    Ledger,
    missing,
    raising,
    tc_row,
    terminal,
    v0_row,
)

VERSION = resolve_outcomes.RESOLVER_VERSION
OUTAGE = ProviderError("PROVIDER_DEGRADED", "synthetic outage", provider="binance")


def _route_c(rows, *, statuses=None, **ledger):
    outcomes: dict = {}
    store = InMemoryStatusStore(rows, outcomes=outcomes, statuses=statuses)
    return store, Ledger(outcomes, **ledger)


def _run(store, repository, *, now=NOW, fetch=None, limit=10, budget=600, clock=None):
    return resolve_outcomes.resolve_due_predictions(
        repository,
        settings=Settings(),
        now_utc=now,
        limit=limit,
        fetch_candles=fetch if fetch is not None else Fetch(),
        time_budget_seconds=budget,
        monotonic=clock if clock is not None else Clock(),
        status_store=store,
    )


def _status(pid, state, *, count=1, first=NOW - timedelta(hours=2), reason=None, **stamps):
    reason = reason or "skip_terminal_bar_missing"
    return {
        "prediction_id": pid,
        "resolution_status": state,
        "attempt_count": count,
        "first_attempt_utc": first,
        "last_attempt_utc": first,
        "first_reason": reason,
        "last_reason": reason,
        "next_eligible_utc": stamps.get("next_eligible_utc"),
        "quarantined_at_utc": stamps.get("quarantined_at_utc"),
        "resolved_at_utc": stamps.get("resolved_at_utc"),
        "policy_version": "rq-v1",
        "resolver_version": VERSION,
    }


def _retryable(pid, *, next_eligible=NOW - timedelta(minutes=1), **kwargs):
    return _status(pid, "RETRYABLE", next_eligible_utc=next_eligible, **kwargs)


def _counts(stats, *keys):
    return tuple(stats[key] for key in keys)


# --------------------------------------------------------------------------- venue resolution


@pytest.mark.parametrize("venue", ["OKX_PUBLIC", "BINANCE_PUBLIC"])
def test_a_stamped_cross_provider_row_resolves_on_its_reference_venue(venue) -> None:
    store, ledger = _route_c([tc_row("tc", venue=venue)])
    fetch = Fetch()

    stats = _run(store, ledger, fetch=fetch)

    assert _counts(stats, "due", "resolved", "skipped", "failed") == (1, 1, 0, 0)
    (window,) = fetch.windows
    assert (window.provider, window.data_source) == (PROVIDERS[venue], venue)
    assert ledger.saved[0]["data_source"] == venue
    assert store.outcomes["tc"]["data_source"] == venue
    assert store.statuses == {} and store.batches == []  # resolved at its first attempt
    assert all(stats[key] == 0 for key in resolve_outcomes.STATUS_COUNT_KEYS)


def test_a_stamped_venue_row_resolves_on_its_venue_too() -> None:
    store, ledger = _route_c([tc_row("tc", venue="OKX_PUBLIC", source="OKX_PUBLIC")])
    fetch = Fetch()

    assert _run(store, ledger, fetch=fetch)["resolved"] == 1
    assert [window.data_source for window in fetch.windows] == ["OKX_PUBLIC"]


def test_the_due_scan_never_selects_what_route_c_cannot_or_must_not_resolve() -> None:
    rows = [
        v0_row("v0-cross", source="CROSS_PROVIDER", cross_provider_state="COHERENT"),
        {**tc_row("tc-other-source"), "data_source": "DEGRADED"},
        {**tc_row("tc-no-source"), "data_source": None},
        {**tc_row("tc-other-version"), "target_version": "tc-v2"},
        v0_row("shadow", prediction_origin="SCHEDULED_SHADOW_EVIDENCE"),
        v0_row("smoke", prediction_origin="CONTROLLED_SMOKE"),
        v0_row("not-live", is_live_data=False),
        v0_row("monthly", timeframe="1M"),
        v0_row("not-due", age=-timedelta(hours=1)),
        v0_row("resolved-already"),
    ]
    store, ledger = _route_c(rows)
    store.outcomes["resolved-already"] = {"prediction_id": "resolved-already"}
    fetch = Fetch()

    stats = _run(store, ledger, fetch=fetch)

    assert (stats["scanned"], fetch.windows, ledger.saved, store.batches) == (0, [], [], [])
    store.add_prediction(tc_row("tc-ok"))
    assert _run(store, ledger, fetch=fetch)["resolved"] == 1
    assert fetch.symbols == ["tc-ok"]


# --------------------------------------------------------------------------- quarantine, backoff


@pytest.mark.parametrize(
    "row",
    [
        {**tc_row("bad"), "cross_provider_state": "DIVERGENT"},
        {**tc_row("bad", venue="BINANCE_PUBLIC", source="BINANCE_PUBLIC"), "p_up_frac": 0.9},
        {**tc_row("bad"), "issued_at_utc": None},
    ],
    ids=["cross-provider-not-coherent", "probabilities-invalid", "partial-stamp"],
)
def test_a_tc_v1_invalid_row_is_quarantined_and_never_selected_again(row) -> None:
    store, ledger = _route_c([row])
    fetch = Fetch()

    stats = _run(store, ledger, fetch=fetch)

    assert _counts(stats, "skipped", "skip_invalid_target", "failed") == (1, 1, 0)
    assert (fetch.windows, ledger.saved) == ([], [])
    assert store.statuses == {
        "bad": _status("bad", "QUARANTINED", first=NOW, reason="skip_invalid_target",
                       quarantined_at_utc=NOW)
    }
    assert _counts(stats, "status_written", "status_quarantined") == (1, 1)
    assert _run(store, ledger, now=NOW + timedelta(days=30))["scanned"] == 0


def test_a_retry_waits_for_its_backoff_then_resolves_and_is_never_selected_again() -> None:
    store, ledger = _route_c([v0_row("slow")])

    first = _run(store, ledger, fetch=Fetch(default=missing))
    assert _counts(first, "skip_terminal_bar_missing", "status_written") == (1, 1)
    assert store.statuses["slow"]["next_eligible_utc"] == NOW + timedelta(hours=1)

    early = Fetch()
    assert _run(store, ledger, now=NOW + timedelta(minutes=59), fetch=early)["scanned"] == 0
    assert early.windows == []

    second = NOW + timedelta(hours=1)  # next_eligible_utc <= now: due again
    assert _run(store, ledger, now=second, fetch=Fetch(default=missing))["scanned"] == 1
    status = store.statuses["slow"]
    assert (status["attempt_count"], status["first_attempt_utc"], status["last_attempt_utc"]) == (
        2, NOW, second,
    )
    assert status["next_eligible_utc"] == second + timedelta(hours=2)

    third = second + timedelta(hours=2)
    resolved = _run(store, ledger, now=third)
    assert _counts(resolved, "resolved", "status_written", "status_resolved") == (1, 1, 1)
    assert store.statuses["slow"] == {
        **_status("slow", "RESOLVED", count=3, first=NOW, resolved_at_utc=third),
        "last_attempt_utc": third,
    }
    assert _run(store, ledger, now=third + timedelta(days=1))["scanned"] == 0


def test_only_rows_with_no_status_or_a_due_retry_are_selected() -> None:
    ids = ("none", "due", "waiting", "quarantined", "resolved")
    statuses = {
        "due": _retryable("due", next_eligible=NOW),
        "waiting": _retryable("waiting", next_eligible=NOW + timedelta(microseconds=1)),
        "quarantined": _status("quarantined", "QUARANTINED", quarantined_at_utc=NOW),
        "resolved": _status("resolved", "RESOLVED", resolved_at_utc=NOW),
    }
    store, ledger = _route_c([v0_row(pid) for pid in ids], statuses=statuses)
    fetch = Fetch()

    stats = _run(store, ledger, fetch=fetch)

    assert sorted(fetch.symbols) == ["due", "none"]
    assert stats["scanned"] == 2
    for pid in ("waiting", "quarantined", "resolved"):
        assert store.statuses[pid] == statuses[pid]


# --------------------------------------------------------------------------- outcome conflict

CONFLICTS = {
    "missing": {"write": False},
    "label": {"stored": lambda row: {**row, "realized_label": "DOWN"}},
    "version": {"stored": lambda row: {**row, "resolver_version": "resolver-v1-wave4b2"}},
    "close": {"stored": lambda row: {**row, "outcome_close_utc": "2026-10-01T12:12:00.000001Z"}},
}


@pytest.mark.parametrize("kind", sorted(CONFLICTS))
def test_an_outcome_conflict_is_failed_and_writes_no_status(kind) -> None:
    statuses = {"p": _retryable("p", count=2)}
    store, ledger = _route_c([v0_row("p")], statuses=statuses, **CONFLICTS[kind])

    stats = _run(store, ledger)

    assert _counts(stats, "resolved", "failed", "error_outcome_conflict") == (0, 1, 1)
    assert len(ledger.saved) == 1
    assert store.statuses == statuses and store.batches == []
    assert all(stats[key] == 0 for key in resolve_outcomes.STATUS_COUNT_KEYS)


@pytest.mark.parametrize(
    "close",
    [
        datetime(2026, 10, 1, 19, 12, tzinfo=timezone(timedelta(hours=7))),
        "2026-10-01T12:12:00+00:00",
        datetime(2026, 10, 1, 12, 12),  # naive means UTC
    ],
)
def test_the_same_instant_in_another_form_is_no_conflict(close) -> None:
    store, ledger = _route_c(
        [v0_row("p")], stored=lambda row: {**row, "outcome_close_utc": close}
    )

    stats = _run(store, ledger)

    assert _counts(stats, "resolved", "failed") == (1, 0)


def test_a_readback_that_fails_is_an_outcome_conflict() -> None:
    class Unreadable(InMemoryStatusStore):
        def read_outcome(self, prediction_id):
            raise RuntimeError("synthetic readback failure")

    outcomes: dict = {}
    store = Unreadable([v0_row("p")], outcomes=outcomes)

    stats = _run(store, Ledger(outcomes))

    assert _counts(stats, "failed", "error_outcome_conflict") == (1, 1)
    assert store.statuses == {}


# --------------------------------------------------------------------------- selection, outage


def test_n2_selection_and_budget_compose_and_deferred_rows_get_no_status() -> None:
    stuck = [v0_row(f"stuck-{i}", age=timedelta(days=30, minutes=-i)) for i in range(3)]
    fresh = [v0_row(f"fresh-{i}", age=timedelta(minutes=30 - i)) for i in range(4)]
    store, ledger = _route_c(stuck + fresh)
    clock = Clock()
    fetch = Fetch(clock, seconds=100, default=missing)

    stats = _run(store, ledger, fetch=fetch, clock=clock, budget=250)

    # Fresh rows go first in the scan's order; rows start at t = 0, 100 and 200; the last fresh
    # row and every stuck row are deferred: never fetched, and never given a status.
    assert fetch.symbols == ["fresh-0", "fresh-1", "fresh-2"]
    assert _counts(stats, "scanned", "fresh", "stuck", "selected", "deferred") == (7, 4, 3, 7, 4)
    assert _counts(stats, "skipped", "status_written") == (3, 3)
    assert sorted(store.statuses) == ["fresh-0", "fresh-1", "fresh-2"]


def test_a_venue_outage_suppresses_its_statuses_but_never_a_resolution() -> None:
    rows = [v0_row(f"b{i}") for i in range(5)]
    rows += [v0_row("b-back"), v0_row("o1", source="OKX_PUBLIC")]
    store, ledger = _route_c(rows, statuses={"b-back": _retryable("b-back", count=3)})
    fetch = Fetch(default=raising(OUTAGE), by_symbol={"b-back": terminal})

    stats = _run(store, ledger, fetch=fetch)

    # Binance: 5 of its 6 attempted rows failed the same way (83%), so it is an outage.
    assert _counts(stats, "resolved", "failed", "error_provider_unavailable") == (1, 6, 6)
    assert _counts(
        stats, "status_written", "status_resolved", "status_outage_suppressed"
    ) == (2, 1, 5)
    assert {pid: row["resolution_status"] for pid, row in store.statuses.items()} == {
        "b-back": "RESOLVED",
        "o1": "RETRYABLE",
    }


def test_a_failed_status_batch_writes_nothing_and_sets_status_error() -> None:
    # A stale clock: the stored first attempt is after this run's now, so the new last attempt
    # breaks prs_attempt_chronology and the whole batch fails, the valid write included.
    statuses = {"late": _retryable("late", first=NOW + timedelta(hours=1))}
    store, ledger = _route_c([v0_row("fine"), v0_row("late")], statuses=statuses)
    before = deepcopy(store.statuses)

    stats = _run(store, ledger, fetch=Fetch(default=missing))

    assert _counts(stats, "status_error", "status_written", "skipped", "failed") == (1, 0, 2, 0)
    assert store.statuses == before and store.batches == []


def test_a_stale_writer_cannot_count_twice_and_terminal_rows_never_change() -> None:
    statuses = {
        "p": _retryable("p"),
        "q": _status("q", "QUARANTINED", quarantined_at_utc=NOW),
        "r": _status("r", "RESOLVED", resolved_at_utc=NOW),
    }
    store = InMemoryStatusStore(statuses=deepcopy(statuses))
    read = {"p": rq_v1.ExistingStatus(**{key: statuses["p"][key] for key in STATUS_COLUMNS})}
    writes = rq_v1.plan_status_writes(
        [rq_v1.Attempt(pid, "error_other", "BINANCE_PUBLIC", NOW) for pid in ("p", "q", "r")],
        read,
        now=NOW,
        resolver_version=VERSION,
    ).writes
    assert [(write.prediction_id, write.attempt_count) for write in writes] == [
        ("p", 2), ("q", 1), ("r", 1),
    ]

    # p goes from 1 to 2 attempts; q and r are terminal: unchanged, and not reported as written
    assert store.write_batch(writes) == (writes[0],)
    first = deepcopy(store.statuses)
    # a stale or concurrent writer, planned from the same read: nothing is applied
    assert store.write_batch(writes) == ()

    assert store.statuses == first
    assert (first["p"]["attempt_count"], first["p"]["last_reason"]) == (2, "error_other")
    assert first["p"]["first_attempt_utc"] == statuses["p"]["first_attempt_utc"]
    assert first["q"] == statuses["q"] and first["r"] == statuses["r"]


class StaleRead(InMemoryStatusStore):
    """Its due scan reports every status one attempt behind the stored one: a stale read."""

    def fetch_due(self, now_utc, limit, **filters):
        scan = super().fetch_due(now_utc, limit, **filters)
        stale = {
            pid: replace(status, attempt_count=status.attempt_count - 1)
            for pid, status in scan.statuses.items()
        }
        return DueScan(rows=scan.rows, statuses=stale)


def test_a_write_the_compare_and_set_rejects_is_not_counted() -> None:
    outcomes: dict = {}
    store = StaleRead(
        [v0_row("p")], outcomes=outcomes, statuses={"p": _retryable("p", count=2)}
    )
    before = deepcopy(store.statuses)

    stats = _run(store, Ledger(outcomes), fetch=Fetch(default=missing))

    assert _counts(stats, "skip_terminal_bar_missing", "status_error") == (1, 0)
    assert len(store.batches) == 1  # the planned write was sent ...
    assert _counts(stats, "status_written", "status_quarantined", "status_resolved") == (0, 0, 0)
    assert store.statuses == before  # ... and the compare-and-set rejected it


# --------------------------------------------------------------------------- main()


class RaisingBatch(InMemoryStatusStore):
    def write_batch(self, writes):
        raise RuntimeError("synthetic batch failure")


class RaisingScan(InMemoryStatusStore):
    def fetch_due(self, now_utc, limit, **filters):
        raise RuntimeError("SYNTHETIC status due scan failed")


def _main(monkeypatch, capsys, store, repository, *, fetch=None, state="active"):
    real = resolve_outcomes.resolve_due_predictions

    def with_fakes(repo, **kwargs):
        return real(repo, now_utc=NOW, fetch_candles=fetch or Fetch(), monotonic=Clock(), **kwargs)

    monkeypatch.setattr(resolve_outcomes, "build_resolver_repository", lambda settings: repository)
    monkeypatch.setattr(
        resolve_outcomes, "build_status_store", lambda settings, repo: (store, state)
    )
    monkeypatch.setattr(resolve_outcomes, "resolve_due_predictions", with_fakes)
    code = resolve_outcomes.main(["--limit", "50"])
    return code, capsys.readouterr().out.splitlines()


@pytest.mark.parametrize(
    ("store_type", "fetch", "code", "summary", "tail"),
    [
        (InMemoryStatusStore, None, 0, "resolved=1 skipped=0 failed=0", "status_written=0"),
        (InMemoryStatusStore, missing, 0, "resolved=0 skipped=1 failed=0", "status_written=1"),
        (InMemoryStatusStore, raising(OUTAGE), 1, "resolved=0 skipped=0 failed=1",
         "status_written=1"),
        (RaisingBatch, missing, 1, "resolved=0 skipped=1 failed=0", "status_error=1"),
    ],
    ids=["resolved", "skipped", "failed-row", "failed-batch"],
)
def test_main_exit_codes_on_route_c(monkeypatch, capsys, store_type, fetch, code, summary, tail):
    outcomes: dict = {}
    store = store_type([v0_row("p")], outcomes=outcomes)
    fake = Fetch(default=fetch)

    exit_code, lines = _main(monkeypatch, capsys, store, Ledger(outcomes), fetch=fake)

    assert exit_code == code
    assert lines[0] == f"resolved_outcomes repository=SYNTHETIC limit=50 due=1 {summary}"
    assert " route=c status_store=active " in lines[1]
    assert tail in lines[1].split(" ")
    assert "failed=" not in lines[1]


def test_main_on_a_route_c_scan_failure_prints_its_single_line(monkeypatch, capsys) -> None:
    ledger = Ledger({})

    code, lines = _main(monkeypatch, capsys, RaisingScan([]), ledger)

    assert code == 1
    assert lines == [
        "resolved_outcomes repository=SYNTHETIC limit=50 due=0 resolved=0 skipped=0 failed=1 "
        "error=RuntimeError: SYNTHETIC status due scan failed"
    ]
    assert ledger.closed


@pytest.mark.parametrize("route", ["c", "legacy"])
@pytest.mark.parametrize("store", ["active", "absent", "error"])
def test_the_detail_line_never_contains_failed_on_any_route(route, store) -> None:
    every = dict.fromkeys(
        (
            *resolve_outcomes.DETAIL_COUNT_KEYS,
            *resolve_outcomes.REASON_KEYS,
            *resolve_outcomes.STATUS_COUNT_KEYS,
        ),
        1,
    )

    line = resolve_outcomes.format_detail_line(every, budget_s=600, route=route, store=store)

    assert "failed" not in line
    assert line.endswith(
        f" route={route} status_store={store} status_written=1 status_quarantined=1 "
        "status_resolved=1 status_outage_suppressed=1 status_error=1"
    )


@pytest.mark.parametrize("values", [{"route": "failed=1"}, {"store": "failed=1"}, {"route": ""}])
def test_the_detail_line_refuses_an_unknown_route_or_store(values) -> None:
    with pytest.raises(ValueError):
        resolve_outcomes.format_detail_line({}, budget_s=600, **values)


# --------------------------------------------------------------------------- the legacy path


def _legacy_main(monkeypatch, capsys, repository):
    real = resolve_outcomes.resolve_due_predictions

    def with_fakes(repo, **kwargs):
        assert kwargs["status_store"] is None
        return real(repo, now_utc=NOW, fetch_candles=Fetch(), monotonic=Clock(), **kwargs)

    def no_database(*args, **kwargs):
        raise AssertionError("the legacy path never connects for a status store")

    monkeypatch.setenv("SUPABASE_DB_URL", "postgresql://legacy.example.invalid/db")
    monkeypatch.setattr(psycopg, "connect", no_database)
    monkeypatch.setattr(resolve_outcomes, "build_resolver_repository", lambda settings: repository)
    monkeypatch.setattr(resolve_outcomes, "resolve_due_predictions", with_fakes)
    code = resolve_outcomes.main(["--limit", "50"])
    return code, capsys.readouterr().out.splitlines()


class SavingMemory(InMemoryPersistenceRepository):
    def save_prediction_outcome(self, row):
        super().save_prediction_outcome(row)
        return "OK"


class RecordingRest(SupabaseRestRepository):
    def __init__(self, rows):
        super().__init__("https://legacy-rest.example.invalid", "synthetic-test-key")
        self.rows = rows
        self.due_calls = []
        self.saved = []

    def fetch_due_unresolved_predictions(self, now_utc, limit, **filters):
        self.due_calls.append((now_utc, limit, filters))
        return list(self.rows)

    def save_prediction_outcome(self, row):
        self.saved.append(dict(row))
        return "OK"


LEGACY_TAIL = (
    " route=legacy status_store=absent status_written=0 status_quarantined=0 status_resolved=0 "
    "status_outage_suppressed=0 status_error=0"
)


def test_the_legacy_path_is_unchanged_for_the_in_memory_repository(monkeypatch, capsys) -> None:
    repository = SavingMemory()
    repository.save_prediction(v0_row("p"))
    repository.save_prediction(tc_row("tc-cross"))  # stamped CROSS_PROVIDER: never due here

    code, lines = _legacy_main(monkeypatch, capsys, repository)

    assert code == 0
    assert lines[0] == (
        "resolved_outcomes repository=IN_MEMORY limit=50 due=1 resolved=1 skipped=0 failed=0"
    )
    assert lines[1].endswith(LEGACY_TAIL)
    assert list(repository._prediction_outcomes) == ["p"]  # noqa: SLF001


def test_the_legacy_path_is_unchanged_for_the_rest_repository(monkeypatch, capsys) -> None:
    repository = RecordingRest([v0_row("p", source="OKX_PUBLIC")])
    try:
        code, lines = _legacy_main(monkeypatch, capsys, repository)
    finally:
        repository.close()

    assert code == 0
    assert lines[1].endswith(LEGACY_TAIL)
    assert repository.due_calls == [
        (
            NOW,
            1000,
            {
                "data_sources": ("BINANCE_PUBLIC", "OKX_PUBLIC"),
                "timeframes": ("15m", "1D", "1H", "1W", "4H"),
                "prediction_origins": ("USER_REQUESTED",),
            },
        )
    ]
    assert [row["data_source"] for row in repository.saved] == ["OKX_PUBLIC"]
    assert repository.saved[0]["resolver_version"] == VERSION


def test_a_legacy_run_writes_no_status_and_reads_nothing_back() -> None:
    repository = SavingMemory()
    repository.save_prediction(v0_row("p"))
    repository.save_prediction(v0_row("gone"))

    stats = resolve_outcomes.resolve_due_predictions(
        repository,
        settings=Settings(),
        now_utc=NOW,
        fetch_candles=Fetch(by_symbol={"gone": missing}),
        monotonic=Clock(),
    )

    assert _counts(stats, "resolved", "skipped", "failed") == (1, 1, 0)
    assert all(stats[key] == 0 for key in resolve_outcomes.STATUS_COUNT_KEYS)
    assert list(stats)[-5:] == list(resolve_outcomes.STATUS_COUNT_KEYS)
