"""Fair selection, a bounded run, and one reason per unresolved row, for the outcome resolver.

The due query returns the oldest horizons first, so rows that never resolve could fill every slot
of every run, and a run that met a slow provider could outlive its job and print nothing. Fresh
rows now go first, stuck rows share a quota that rotates hourly, a run stops STARTING rows once its
time budget is spent (the rest are deferred, never failed), and every attempted row that stays
unresolved is counted under exactly one reason. Outcome VALUES do not change: the last tests here
pin a whole outcome row, computed by the resolver as it was before this change.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta

import pytest

from crypto_probability_engine.adapters.types import MarketCandle, ProviderError
from crypto_probability_engine.config.settings import Settings
from crypto_probability_engine.resolution.status_store import DueScan
from scripts import resolve_outcomes

NOW = datetime(2026, 6, 8, 0, 5, tzinfo=UTC)
HOUR_BUCKET = int(NOW.timestamp()) // 3600
FOUR_HOURS = timedelta(hours=4)
FILTERS = {
    "data_sources": ("BINANCE_PUBLIC", "OKX_PUBLIC"),
    "timeframes": ("15m", "1D", "1H", "1W", "4H"),
    "prediction_origins": ("USER_REQUESTED",),
}
REASON_KEYS = (
    "skip_ineligible", "skip_invalid_target", "skip_not_due", "skip_terminal_bar_missing",
    "error_row_unreadable", "error_provider_rejected", "error_provider_unavailable",
    "error_candle_invalid", "error_save_not_ok", "error_save_exception",
    "error_outcome_conflict", "error_other",
)
STATUS_COUNT_KEYS = (
    "status_written", "status_quarantined", "status_resolved", "status_outage_suppressed",
    "status_error",
)
DETAIL_KEYS = (
    "scanned", "selected", "fresh", "stuck", "deferred", "budget_s", *REASON_KEYS,
    "route", "status_store", *STATUS_COUNT_KEYS,
)
STATS_KEYS = (
    "due", "resolved", "skipped", "failed", "deferred", "scanned", "selected", "fresh", "stuck",
    *REASON_KEYS, *STATUS_COUNT_KEYS,
)


@pytest.fixture(autouse=True)
def block_public_network(monkeypatch: pytest.MonkeyPatch) -> None:
    class NoNetworkClient:
        @classmethod
        def from_settings(cls, settings):
            return cls()

        def get_json(self, **kwargs):
            raise AssertionError("network")

    monkeypatch.setattr(resolve_outcomes, "PublicHttpClient", NoNetworkClient)


class Repository:
    """Serves rows in the order given (the due query's), honouring the limit; records all calls."""

    def __init__(self, rows, *, status="OK"):
        self.rows = list(rows)
        self.status = status
        self.due_calls = []
        self.saved = []
        self.closed = False

    def fetch_due_unresolved_predictions(self, now_utc, limit, **kwargs):
        self.due_calls.append({"now_utc": now_utc, "limit": limit, **kwargs})
        return self.rows[: max(0, limit)]

    def save_prediction_outcome(self, row):
        self.saved.append(row["prediction_id"])
        if isinstance(self.status, Exception):
            raise self.status
        return self.status

    def repository_type(self):
        return "SYNTHETIC"

    def close(self):
        self.closed = True


class Clock:
    """A fake monotonic clock. It moves only when a fake provider call spends time."""

    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


class Fetch:
    """A fake provider. A row's symbol is its id, so ``calls`` lists the rows fetched, in order."""

    def __init__(self, clock=None, *, seconds=0.0, behaviour=None, by_row=None):
        self.clock = clock
        self.seconds = seconds
        self.behaviour = behaviour
        self.by_row = by_row or {}
        self.calls = []

    def __call__(self, window, settings):
        self.calls.append(window.normalized_symbol)
        if self.clock is not None:
            self.clock.now += self.seconds
        behaviour = self.by_row.get(window.normalized_symbol, self.behaviour)
        if behaviour is None:
            return (_candle(window.terminal_close_utc),)
        return behaviour(window)


def _row(prediction_id, *, age=timedelta(minutes=5), **overrides):
    horizon = NOW - age
    return {
        "prediction_id": prediction_id,
        "normalized_symbol": prediction_id,
        "data_source": "BINANCE_PUBLIC",
        "timeframe": "4H",
        "horizon_bars": 6,
        "reference_close_utc": _iso(horizon - 6 * FOUR_HOURS),
        "reference_price": 100.0,
        "horizon_end_utc": _iso(horizon),
        "decision_band_frac": 0.003,
        **overrides,
    }


def _candle(close_time, *, span=FOUR_HOURS, close=101.0):
    return MarketCandle(
        open_time_utc=close_time - span,
        close_time_utc=close_time,
        open=close,
        high=close,
        low=close,
        close=close,
        volume=1.0,
    )


def _iso(value):
    return value.isoformat().replace("+00:00", "Z")


def _rotated(ids, bucket=HOUR_BUCKET):
    """The rotation, derived independently: ascending sha256 hex of "<id>|<hour bucket>"."""

    return sorted(ids, key=lambda i: hashlib.sha256(f"{i}|{bucket}".encode()).hexdigest())


def _ids(rows):
    return [row["prediction_id"] for row in rows]


def _resolve(repo, *, limit=10, now=NOW, fetch=None, clock=None, budget=600, status_store=None):
    return resolve_outcomes.resolve_due_predictions(
        repo,
        settings=Settings(),
        now_utc=now,
        limit=limit,
        fetch_candles=fetch if fetch is not None else Fetch(),
        time_budget_seconds=budget,
        monotonic=clock if clock is not None else Clock(),
        status_store=status_store,
    )


class NoOutcomeStore:
    """A Route C store that serves the rows given and never finds the saved outcome."""

    def __init__(self, rows):
        self.rows = list(rows)

    def fetch_due(self, now_utc, limit, **filters):
        return DueScan(rows=tuple(self.rows[:limit]), statuses={})

    def read_outcome(self, prediction_id):
        return None

    def write_batch(self, writes):
        raise AssertionError("an outcome conflict writes no status")


def _expected(*, scanned, fresh, stuck, selected, resolved=0, deferred=0, **reasons):
    expected = dict.fromkeys(STATS_KEYS, 0)
    expected.update(
        due=selected, selected=selected, scanned=scanned, fresh=fresh, stuck=stuck,
        resolved=resolved, deferred=deferred,
        skipped=sum(n for key, n in reasons.items() if key.startswith("skip_")),
        failed=sum(n for key, n in reasons.items() if key.startswith("error_")),
    )
    expected.update(reasons)  # a misspelt reason adds a key, so the comparison fails
    return expected


def _assert_consistent(stats):
    assert set(stats) == set(STATS_KEYS)
    assert stats["due"] == stats["selected"]
    assert stats["due"] == (
        stats["resolved"] + stats["skipped"] + stats["failed"] + stats["deferred"]
    )
    assert stats["skipped"] == sum(stats[key] for key in REASON_KEYS if key.startswith("skip_"))
    assert stats["failed"] == sum(stats[key] for key in REASON_KEYS if key.startswith("error_"))
    assert stats["scanned"] == stats["fresh"] + stats["stuck"]


# ----------------------------------------------------------------------------- fair selection


def test_fresh_rows_are_attempted_first_then_the_rotated_stuck_quota() -> None:
    stuck = [_row(f"stuck-{i:02d}", age=timedelta(days=30, minutes=-i)) for i in range(60)]
    fresh = [_row(f"fresh-{i}", age=timedelta(minutes=30 - i)) for i in range(3)]
    repo = Repository(stuck + fresh)  # the due query's order: oldest horizon first
    fetch = Fetch()

    stats = _resolve(repo, limit=10, fetch=fetch)

    # limit 10: stuck quota max(5, 10 // 5) = 5, fresh share 5; the 2 fresh slots left unused
    # go to stuck rows, which are taken in this hour's rotated order, not oldest-first.
    expected = ["fresh-0", "fresh-1", "fresh-2", *_rotated(_ids(stuck))[:7]]
    assert fetch.calls == expected
    assert repo.saved == expected
    assert _rotated(_ids(stuck))[:7] != _ids(stuck)[:7]
    assert stats == _expected(scanned=63, fresh=3, stuck=60, selected=10, resolved=10)
    _assert_consistent(stats)


def test_rotated_stuck_order_is_fixed_within_an_hour_and_changes_with_the_hour() -> None:
    stuck = [_row(f"stuck-{i:02d}", age=timedelta(days=10, minutes=-i)) for i in range(30)]

    def attempted(rows, now):
        fetch = Fetch()
        _resolve(Repository(rows), limit=10, now=now, fetch=fetch)
        return fetch.calls

    first = attempted(stuck, NOW)  # 00:05
    assert first == _rotated(_ids(stuck))[:10]  # no fresh rows: every slot goes to stuck rows
    assert attempted(stuck, NOW) == first  # deterministic, no randomness
    assert attempted(list(reversed(stuck)), NOW) == first  # by id, not by query position
    assert attempted(stuck, NOW + timedelta(minutes=50)) == first  # 00:55, the same hour
    next_hour = attempted(stuck, NOW + timedelta(hours=1))  # 01:05, the next hour bucket
    assert next_hour == _rotated(_ids(stuck), HOUR_BUCKET + 1)[:10]
    assert next_hour != first


@pytest.mark.parametrize(
    ("limit", "fresh_rows", "stuck_rows", "fresh_taken", "stuck_taken"),
    [
        (10, 3, 60, 3, 7),  # fresh short: its unused slots go to stuck rows
        (10, 20, 2, 8, 2),  # stuck short: its unused quota goes to fresh rows
        (10, 2, 3, 2, 3),  # both short: everything is selected
        (10, 0, 30, 0, 10),
        (10, 30, 0, 10, 0),
        (50, 100, 100, 40, 10),  # the workflow's limit: stuck quota max(5, 50 // 5) = 10
        (100, 200, 200, 80, 20),
        (24, 30, 30, 19, 5),  # the quota floor: max(5, 24 // 5 = 4) = 5
        (3, 10, 10, 0, 3),  # the quota is capped at the limit: min(3, 5) = 3 ...
        (3, 10, 0, 3, 0),  # ... and still goes to fresh rows when no row is stuck
        (1, 1, 1, 0, 1),
    ],
)
def test_quotas_and_unused_capacity_fill_in_both_directions(
    limit, fresh_rows, stuck_rows, fresh_taken, stuck_taken
) -> None:
    stuck = [_row(f"s{i:03d}", age=timedelta(days=5, minutes=-i)) for i in range(stuck_rows)]
    fresh = [_row(f"f{i:03d}", age=timedelta(hours=12, minutes=-i)) for i in range(fresh_rows)]
    fetch = Fetch()

    stats = _resolve(Repository(stuck + fresh), limit=limit, fetch=fetch)

    assert fetch.calls == _ids(fresh)[:fresh_taken] + _rotated(_ids(stuck))[:stuck_taken]
    assert stats["selected"] == stats["due"] == fresh_taken + stuck_taken
    assert (stats["scanned"], stats["fresh"], stats["stuck"]) == (
        fresh_rows + stuck_rows, fresh_rows, stuck_rows,
    )
    _assert_consistent(stats)


def test_fresh_window_boundary_and_unreadable_horizons_count_as_stuck() -> None:
    missing = _row("missing")
    del missing["horizon_end_utc"]
    rows = [
        _row("older", age=timedelta(hours=48, microseconds=1)),
        _row("boundary", age=timedelta(hours=48)),  # exactly 48 h old is still fresh
        _row("unreadable", horizon_end_utc="not-a-time"),
        missing,
    ]
    fetch = Fetch()

    stats = _resolve(Repository(rows), fetch=fetch)

    assert fetch.calls == ["boundary", "older"]  # the unreadable rows fail before any fetch
    assert stats == _expected(
        scanned=4, fresh=1, stuck=3, selected=4, resolved=2, error_row_unreadable=2
    )


def test_a_malformed_row_is_counted_and_never_stops_the_run() -> None:
    fetch = Fetch()

    stats = _resolve(Repository([None, "not-a-row", _row("good")]), fetch=fetch)

    assert fetch.calls == ["good"]
    assert stats == _expected(
        scanned=3, fresh=1, stuck=2, selected=3, resolved=1, error_row_unreadable=2
    )


@pytest.mark.parametrize(
    ("limit", "scan"),
    [(1, 20), (10, 200), (49, 980), (50, 1000), (51, 1000), (100, 1000), (0, 0)],
)
def test_the_due_query_gets_the_scan_limit_and_unchanged_filters(limit, scan) -> None:
    repo = Repository([])

    stats = _resolve(repo, limit=limit)

    assert repo.due_calls == [{"now_utc": NOW, "limit": scan, **FILTERS}]
    assert stats == _expected(scanned=0, fresh=0, stuck=0, selected=0)


def test_no_more_than_limit_rows_are_selected_from_a_large_scan() -> None:
    rows = [_row(f"r{i:03d}", age=timedelta(minutes=900 - i)) for i in range(300)]
    fetch = Fetch()

    stats = _resolve(Repository(rows), limit=50, fetch=fetch)

    assert fetch.calls == _ids(rows)[:50]
    assert stats == _expected(scanned=300, fresh=300, stuck=0, selected=50, resolved=50)


# ----------------------------------------------------------------------------- time budget


def test_rows_past_the_time_budget_are_deferred_without_provider_call_or_write() -> None:
    stuck = [_row(f"stuck-{i}", age=timedelta(days=9, minutes=-i)) for i in range(2)]
    fresh = [_row(f"fresh-{i}", age=timedelta(minutes=30 - i)) for i in range(4)]
    clock = Clock()
    fetch = Fetch(clock, seconds=100)
    repo = Repository(stuck + fresh)

    stats = _resolve(repo, fetch=fetch, clock=clock, budget=250)

    # Rows start at t = 0, 100 and 200. At t = 300 the budget is spent, so the rest of the attempt
    # order (the last fresh row, then both stuck rows) is deferred: never fetched, never written.
    assert fetch.calls == ["fresh-0", "fresh-1", "fresh-2"]
    assert repo.saved == ["fresh-0", "fresh-1", "fresh-2"]
    assert stats == _expected(scanned=6, fresh=4, stuck=2, selected=6, resolved=3, deferred=3)
    _assert_consistent(stats)


def test_no_row_starts_once_elapsed_time_equals_the_budget() -> None:
    clock = Clock()
    fetch = Fetch(clock, seconds=100)

    stats = _resolve(
        Repository([_row(f"r{i}", age=timedelta(minutes=9 - i)) for i in range(4)]),
        fetch=fetch,
        clock=clock,
        budget=200,
    )

    assert fetch.calls == ["r0", "r1"]  # started at t = 0 and t = 100; at t = 200 none starts
    assert stats == _expected(scanned=4, fresh=4, stuck=0, selected=4, resolved=2, deferred=2)


def test_the_budget_runs_from_the_start_of_the_run_including_the_due_query() -> None:
    clock = Clock()

    class SlowQuery(Repository):
        def fetch_due_unresolved_predictions(self, now_utc, limit, **kwargs):
            clock.now += 700
            return super().fetch_due_unresolved_predictions(now_utc, limit, **kwargs)

    repo = SlowQuery([_row(f"r{i}", age=timedelta(minutes=9 - i)) for i in range(3)])
    fetch = Fetch(clock)

    stats = _resolve(repo, fetch=fetch, clock=clock, budget=600)

    assert fetch.calls == []
    assert repo.saved == []
    assert stats == _expected(scanned=3, fresh=3, stuck=0, selected=3, deferred=3)


@pytest.mark.parametrize("budget", [0, -1, float("nan")])
def test_a_budget_that_is_not_positive_is_refused_before_any_query(budget) -> None:
    repo = Repository([_row("r")])

    with pytest.raises(ValueError, match="^time_budget_seconds must be > 0.$"):
        _resolve(repo, budget=budget)
    assert repo.due_calls == []


# ----------------------------------------------------------------------------- reasons


def _raising(error):
    def behaviour(window):
        raise error

    return behaviour


def _conflicting(window):
    terminal = _candle(window.terminal_close_utc)
    return (terminal, _candle(window.terminal_close_utc, close=55.0))


def _wrong_duration(window):
    return (_candle(window.terminal_close_utc, span=timedelta(hours=1)),)


FUTURE = NOW + timedelta(hours=1)
REASON_CASES = [
    # (reason, row overrides, provider behaviour, save status, provider called)
    ("skip_ineligible", {"data_source": "CROSS_PROVIDER"}, None, "OK", False),
    ("skip_ineligible", {"timeframe": "1M"}, None, "OK", False),
    ("skip_invalid_target", {"reference_price": 0}, None, "OK", False),
    ("skip_invalid_target", {"horizon_bars": 5}, None, "OK", False),
    (
        "skip_not_due",
        {"horizon_end_utc": _iso(FUTURE), "reference_close_utc": _iso(FUTURE - 6 * FOUR_HOURS)},
        None,
        "OK",
        False,
    ),
    ("skip_terminal_bar_missing", {}, lambda window: (), "OK", True),
    ("error_row_unreadable", {"horizon_end_utc": "not-a-time"}, None, "OK", False),
    ("error_row_unreadable", {"reference_price": "abc"}, None, "OK", False),
    (
        "error_provider_rejected",
        {},
        _raising(ProviderError("INVALID_SYMBOL", "Provider rejected symbol.", provider="binance")),
        "OK",
        True,
    ),
    (
        "error_provider_unavailable",
        {},
        _raising(ProviderError("PROVIDER_DEGRADED", "synthetic outage", provider="binance")),
        "OK",
        True,
    ),
    (
        "error_provider_unavailable",
        {},
        _raising(ProviderError("SCHEMA_VALIDATION_FAILED", "bad payload", provider="okx")),
        "OK",
        True,
    ),
    ("error_candle_invalid", {}, _conflicting, "OK", True),
    ("error_candle_invalid", {}, _wrong_duration, "OK", True),
    ("error_save_not_ok", {}, None, "UNAVAILABLE", True),
    ("error_save_exception", {}, None, RuntimeError("synthetic save failure"), True),
    # Route C only: the save returned OK, but reading the outcome back finds no row.
    ("error_outcome_conflict", {}, None, "OK", True),
    ("error_other", {}, _raising(RuntimeError("synthetic unexpected failure")), "OK", True),
    ("error_other", {}, lambda window: (object(),), "OK", True),  # not a candle at all
    # A ValueError from the provider side is not one of the resolver's own candle checks.
    ("error_other", {}, _raising(ValueError("provider-side value error")), "OK", True),
]


@pytest.mark.parametrize(
    ("reason", "overrides", "behaviour", "status", "fetched"),
    REASON_CASES,
    ids=[f"{case[0]}-{index}" for index, case in enumerate(REASON_CASES)],
)
def test_each_unresolved_row_is_counted_under_exactly_one_reason(
    reason, overrides, behaviour, status, fetched
) -> None:
    repo = Repository([_row("r", **overrides)], status=status)
    fetch = Fetch(behaviour=behaviour)
    conflict = reason == "error_outcome_conflict"
    store = NoOutcomeStore(repo.rows) if conflict else None

    stats = _resolve(repo, fetch=fetch, status_store=store)

    stuck = 1 if overrides.get("horizon_end_utc") == "not-a-time" else 0
    assert stats == _expected(
        scanned=1, fresh=1 - stuck, stuck=stuck, selected=1, **{reason: 1}
    )
    assert fetch.calls == (["r"] if fetched else [])
    assert repo.saved == (["r"] if reason.startswith("error_save") or conflict else [])
    _assert_consistent(stats)


def test_every_reason_has_a_case_and_the_resolver_lists_them_in_order() -> None:
    assert {case[0] for case in REASON_CASES} == set(REASON_KEYS)
    assert resolve_outcomes.REASON_KEYS == REASON_KEYS


@pytest.mark.parametrize(
    ("symbol", "error", "reason", "requests"),
    [
        (  # the HTTP client maps every 400/404 to INVALID_SYMBOL
            "BTC/USDT",
            ProviderError("INVALID_SYMBOL", "rejected", provider="binance", http_status=404),
            "error_provider_rejected",
            1,
        ),
        (  # timeouts, 5xx and 429 arrive as other codes
            "BTC/USDT",
            ProviderError("PROVIDER_DEGRADED", "timed out", provider="binance"),
            "error_provider_unavailable",
            1,
        ),
        ("NOT A SYMBOL", None, "error_other", 0),  # refused by the symbol normalizer first
    ],
)
def test_the_default_fetch_errors_are_classified(
    monkeypatch, symbol, error, reason, requests
) -> None:
    calls = []

    class FailingClient:
        @classmethod
        def from_settings(cls, settings):
            return cls()

        def get_json(self, **kwargs):
            calls.append(kwargs)
            raise error

    monkeypatch.setattr(resolve_outcomes, "PublicHttpClient", FailingClient)
    repo = Repository([_row("r", normalized_symbol=symbol)])

    stats = resolve_outcomes.resolve_due_predictions(
        repo, settings=Settings(), now_utc=NOW, limit=10, monotonic=Clock()
    )

    assert stats == _expected(scanned=1, fresh=1, stuck=0, selected=1, **{reason: 1})
    assert len(calls) == requests
    assert repo.saved == []


# ----------------------------------------------------------------------------- main() output


def _run_main(monkeypatch, capsys, repo, argv, *, fetch, clock):
    real = resolve_outcomes.resolve_due_predictions

    def with_fakes(repository, **kwargs):
        return real(repository, now_utc=NOW, fetch_candles=fetch, monotonic=clock, **kwargs)

    monkeypatch.setattr(resolve_outcomes, "build_resolver_repository", lambda settings: repo)
    monkeypatch.setattr(resolve_outcomes, "resolve_due_predictions", with_fakes)
    code = resolve_outcomes.main(argv)
    return code, capsys.readouterr().out.splitlines()


def _pairs(detail_line):
    head, *pairs = detail_line.split(" ")
    assert head == "resolver_detail"
    return [tuple(pair.split("=")) for pair in pairs]


def test_main_keeps_the_summary_line_and_adds_a_fixed_order_detail_line(
    monkeypatch, capsys
) -> None:
    clock = Clock()
    fetch = Fetch(clock, seconds=100, behaviour=lambda window: ())  # every terminal bar missing
    repo = Repository([_row(f"r{i}", age=timedelta(minutes=9 - i)) for i in range(5)])

    code, lines = _run_main(
        monkeypatch, capsys, repo, ["--limit", "10", "--time-budget-seconds", "250"],
        fetch=fetch, clock=clock,
    )

    # Three rows were skipped and two deferred; neither ever fails the run.
    assert code == 0
    assert fetch.calls == ["r0", "r1", "r2"]  # the deferred rows were never fetched
    assert lines == [
        "resolved_outcomes repository=SYNTHETIC limit=10 due=5 resolved=0 skipped=3 failed=0",
        "resolver_detail scanned=5 selected=5 fresh=5 stuck=0 deferred=2 budget_s=250 "
        "skip_ineligible=0 skip_invalid_target=0 skip_not_due=0 skip_terminal_bar_missing=3 "
        "error_row_unreadable=0 error_provider_rejected=0 error_provider_unavailable=0 "
        "error_candle_invalid=0 error_save_not_ok=0 error_save_exception=0 "
        "error_outcome_conflict=0 error_other=0 "
        "route=legacy status_store=absent status_written=0 status_quarantined=0 "
        "status_resolved=0 status_outage_suppressed=0 status_error=0",
    ]
    assert repo.closed


def test_main_detail_line_never_contains_failed_even_when_rows_fail(monkeypatch, capsys) -> None:
    fetch = Fetch(
        by_row={
            "r0": _raising(ProviderError("PROVIDER_DEGRADED", "outage", provider="binance")),
            "r1": _raising(ProviderError("INVALID_SYMBOL", "rejected", provider="binance")),
        }
    )
    repo = Repository(
        [_row(f"r{i}", age=timedelta(minutes=9 - i)) for i in range(3)], status="UNAVAILABLE"
    )

    code, lines = _run_main(
        monkeypatch, capsys, repo, ["--limit", "10"], fetch=fetch, clock=Clock()
    )

    assert code == 1
    summary, detail = lines
    assert summary == (
        "resolved_outcomes repository=SYNTHETIC limit=10 due=3 resolved=0 skipped=0 failed=3"
    )
    assert "failed=" not in detail
    pairs = _pairs(detail)
    assert [key for key, _ in pairs] == list(DETAIL_KEYS)
    counts = dict(pairs)
    assert counts["budget_s"] == "600"  # the default budget
    assert (
        counts["error_provider_unavailable"],
        counts["error_provider_rejected"],
        counts["error_save_not_ok"],
    ) == ("1", "1", "1")


def test_the_detail_line_lists_every_key_in_order_and_no_key_contains_failed() -> None:
    every_count = dict.fromkeys(STATS_KEYS, 7)

    line = resolve_outcomes.format_detail_line(every_count, budget_s=600)

    assert [key for key, _ in _pairs(line)] == list(DETAIL_KEYS)
    assert "failed" not in line
    old_shape = {"due": 1, "resolved": 1, "skipped": 0, "failed": 0}
    assert {value for _, value in _pairs(
        resolve_outcomes.format_detail_line(old_shape, budget_s=9)
    )} == {"0", "9", "legacy", "absent"}  # route= and status_store= default to the legacy path


def test_main_database_failure_still_prints_only_its_single_line(monkeypatch, capsys) -> None:
    class FailingQuery(Repository):
        def fetch_due_unresolved_predictions(self, now_utc, limit, **kwargs):
            raise RuntimeError("SYNTHETIC due query failed or unavailable.")

    repo = FailingQuery([])
    monkeypatch.setattr(resolve_outcomes, "build_resolver_repository", lambda settings: repo)

    code = resolve_outcomes.main(["--limit", "10"])
    lines = capsys.readouterr().out.splitlines()

    assert code == 1
    assert lines == [
        "resolved_outcomes repository=SYNTHETIC limit=10 due=0 resolved=0 skipped=0 failed=1 "
        "error=RuntimeError: SYNTHETIC due query failed or unavailable."
    ]
    assert repo.closed


@pytest.mark.parametrize(("argv", "budget"), [([], 600), (["--time-budget-seconds", "90"], 90)])
def test_main_passes_the_time_budget(monkeypatch, capsys, argv, budget) -> None:
    seen = {}

    def fake_resolve(repository, **kwargs):
        seen.update(kwargs)
        return {"due": 0, "resolved": 0, "skipped": 0, "failed": 0}

    monkeypatch.setattr(resolve_outcomes, "build_resolver_repository", lambda s: Repository([]))
    monkeypatch.setattr(resolve_outcomes, "resolve_due_predictions", fake_resolve)

    assert resolve_outcomes.main(["--limit", "50", *argv]) == 0
    assert seen["time_budget_seconds"] == budget
    assert resolve_outcomes.DEFAULT_TIME_BUDGET_SECONDS == 600
    assert f" budget_s={budget} " in capsys.readouterr().out


@pytest.mark.parametrize("value", ["0", "-5", "abc", "1.5", ""])
def test_main_refuses_a_budget_that_is_not_a_positive_whole_number(
    monkeypatch, capsys, value
) -> None:
    def no_repository(settings):
        raise AssertionError("argument errors must stop before any repository is built")

    monkeypatch.setattr(resolve_outcomes, "build_resolver_repository", no_repository)

    with pytest.raises(SystemExit) as exited:
        resolve_outcomes.main(["--time-budget-seconds", value])

    assert exited.value.code == 2
    assert "--time-budget-seconds" in capsys.readouterr().err


# ----------------------------------------------------------------------------- outcome values


GOLDEN_OUTCOME = {  # computed by the resolver as it was before fair selection and the budget
    "prediction_id": "golden",
    "resolved_at_utc": "2026-06-08T00:05:00Z",
    "outcome_close_utc": "2026-06-08T00:00:00Z",
    "outcome_reference_price": 103.0,
    "terminal_return_frac": 0.03,
    "realized_label": "UP",
    "decision_band_frac": 0.003,
    "max_favorable_frac": 0.07,
    "max_adverse_frac": -0.06,
    "candles_observed": 6,
    "resolver_version": "resolver-v2b-tc-v1-rq-v1",
    "data_source": "BINANCE_PUBLIC",
    "is_live_data": True,
}


def _golden_window(window):
    reference = window.first_open_utc
    return tuple(
        MarketCandle(
            open_time_utc=reference + (k - 1) * FOUR_HOURS,
            close_time_utc=reference + k * FOUR_HOURS,
            open=100.0,
            high=100.0 + k + 1,
            low=100.0 - k,
            close=100.0 + 0.5 * k,
            volume=1.0,
        )
        for k in range(1, 7)
    )


def test_outcome_row_values_are_unchanged() -> None:
    row = resolve_outcomes.build_outcome_row(
        _row("golden"),
        now_utc=NOW,
        settings=Settings(),
        fetch_candles=lambda window, settings: _golden_window(window),
    )

    assert row == GOLDEN_OUTCOME
    assert resolve_outcomes.RESOLVER_VERSION == "resolver-v2b-tc-v1-rq-v1"


def test_a_run_writes_exactly_that_outcome_row() -> None:
    written = []

    class Capturing(Repository):
        def save_prediction_outcome(self, row):
            written.append(row)
            return super().save_prediction_outcome(row)

    stats = _resolve(Capturing([_row("golden")]), fetch=Fetch(behaviour=_golden_window))

    assert written == [GOLDEN_OUTCOME]
    assert stats == _expected(scanned=1, fresh=1, stuck=0, selected=1, resolved=1)
