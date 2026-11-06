"""The NG4 pilot runner's loop (spec draft 3 §3): restart, capacity stop, errors, no overlap,
cache bypass, the 1D fetch and the checkpoint. Offline: fake clock, fake sleep, fake adapter,
fake store; the lattice switch is turned on inside each test only."""

from __future__ import annotations

import asyncio
import threading
import time
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from crypto_probability_engine import lattice_pilot
from crypto_probability_engine.adapters import provider_selection, public_market
from crypto_probability_engine.persistence import lattice_store
from crypto_probability_engine.quant_ng import lattice, windows
from crypto_probability_engine.telemetry.events import TelemetrySink

START = datetime(2026, 11, 9, tzinfo=UTC)  # on the 15m, 1H and 4H lattices


class Clock:
    def __init__(self, now):
        self.now = now

    def __call__(self):
        return self.now


class Store:
    def __init__(self, row_status="INSERTED", missed_status="LOGGED", raise_once=False):
        self.entries, self.row_status, self.missed_status = [], row_status, missed_status
        self.raise_once = raise_once

    def record_missed(self, entry):
        if self.raise_once:
            self.raise_once = False
            raise RuntimeError("synthetic database failure")
        self.entries.append((entry["timeframe"], entry["lattice_instant_utc"]))
        return self.missed_status

    def record_row(self, row):
        self.entries.append((row["timeframe"], row["lattice_instant_utc"]))
        return self.row_status

    def capture_commit_receipts(self, limit):
        return 0


class Adapter:
    """Every snapshot fetch fails, so each due instant becomes one FETCH_FAILED missed entry."""

    def __init__(self, settings):
        self.http_client = SimpleNamespace(get_json=None)

    def fetch_market_snapshot(self, symbol, timeframe):
        raise RuntimeError("synthetic unavailable")


def _wire(monkeypatch, store, clock, adapter=Adapter):
    async def fake_sleep(seconds):
        clock.now += timedelta(seconds=seconds)

    monkeypatch.setattr(lattice, "LATTICE_ENABLED", True)
    monkeypatch.setattr(public_market, "BinancePublicAdapter", adapter)
    monkeypatch.setattr(lattice_store, "LatticeStore", lambda connect: store)
    monkeypatch.setattr(lattice_pilot.asyncio, "sleep", fake_sleep)


def _config():
    return SimpleNamespace(cells=lattice.PILOT_CELLS)


def _run(clock, end, sink, started_at, start=START):
    asyncio.run(lattice_pilot._run(object(), start, end, _config(), None, sink, clock, started_at))


def test_a_restart_never_repeats_an_instant_a_previous_process_handled(monkeypatch):
    first = START  # a 15m, 1H and 4H instant
    store, clock = Store(), Clock(first + timedelta(seconds=lattice_pilot.GRACE_SECONDS + 1))
    _wire(monkeypatch, store, clock)
    # This process began after `first`'s wake: a previous process may have handled it.
    _run(clock, START + timedelta(hours=2), TelemetrySink(), started_at=clock.now)
    assert ("15m", first.isoformat()) not in store.entries
    assert ("15m", (first + timedelta(minutes=45)).isoformat()) in store.entries
    # One that began before `first`'s wake handles it.
    store2, clock2 = Store(), Clock(first - timedelta(seconds=5))
    _wire(monkeypatch, store2, clock2)
    _run(clock2, START + timedelta(hours=2), TelemetrySink(), started_at=clock2.now)
    assert ("15m", first.isoformat()) in store2.entries
    assert len(store2.entries) == len(set(store2.entries))


def test_a_capacity_stop_ends_the_loop(monkeypatch):
    store, clock = Store(missed_status="CAPACITY_STOP"), Clock(START - timedelta(seconds=5))
    sink = TelemetrySink()
    _wire(monkeypatch, store, clock)
    _run(clock, START + timedelta(days=1), sink, started_at=clock.now)
    assert len(store.entries) == 1  # the first entry answered CAPACITY_STOP; nothing after it
    assert sink.events[-1] == {"event": "lattice_pilot_state", "state": "CAPACITY_STOP"}


def test_a_failing_step_is_reported_by_class_only_and_the_loop_continues(monkeypatch):
    store, clock = Store(raise_once=True), Clock(START - timedelta(seconds=5))
    sink = TelemetrySink()
    _wire(monkeypatch, store, clock)
    _run(clock, START + timedelta(hours=3), sink, started_at=clock.now)
    errors = [e for e in sink.events if e["event"] == "lattice_pilot_error"]
    assert errors == [{"event": "lattice_pilot_error", "exception_class": "RuntimeError"}]
    assert store.entries  # later instants were still processed


def test_steps_never_overlap_and_a_slow_step_reports_a_timeout(monkeypatch):
    clock = Clock(START - timedelta(seconds=5))
    sink, running, peak, lock = TelemetrySink(), [0], [0], threading.Lock()
    _wire(monkeypatch, Store(), clock)

    def slow_step(*_args, **_kwargs):
        with lock:
            running[0] += 1
            peak[0] = max(peak[0], running[0])
        time.sleep(0.05)
        with lock:
            running[0] -= 1
        return {"results": [], "stopped": False}

    monkeypatch.setattr(lattice, "lattice_step", slow_step)
    monkeypatch.setattr(lattice_pilot, "STEP_TIMEOUT_SECONDS", 0.01)
    _run(clock, START + timedelta(hours=1), sink, started_at=clock.now)
    assert peak[0] == 1
    assert {"event": "lattice_pilot_error", "exception_class": "StepTimeout"} in sink.events


def test_the_loop_never_uses_the_cached_selection_and_turns_coalescing_off(monkeypatch):
    from crypto_probability_engine.adapters import http_client

    seen = []

    class Recording(Adapter):
        def fetch_market_snapshot(self, symbol, timeframe):
            seen.append(http_client.PROVIDER_COALESCING.get())
            raise RuntimeError("synthetic unavailable")

    def forbidden(*_args, **_kwargs):
        raise AssertionError("the pilot must not use the cached provider selection")

    monkeypatch.setattr(provider_selection, "_fetch_with_cache", forbidden)
    monkeypatch.setattr(provider_selection, "select_market_data", forbidden)
    clock = Clock(START - timedelta(seconds=5))
    _wire(monkeypatch, Store(), clock, adapter=Recording)
    _run(clock, START + timedelta(hours=1), TelemetrySink(), started_at=clock.now)
    assert seen and all(value is False for value in seen)
    assert http_client.PROVIDER_COALESCING.get() is True


def _daily_rows(last_close: datetime, count: int, *, gap_at=None, hour=0):
    rows = []
    for i in range(count):
        opened = last_close - timedelta(days=count - i) + timedelta(hours=hour)
        if gap_at is not None and i >= gap_at:
            opened += timedelta(days=1)
        ms = int(opened.timestamp() * 1000)
        rows.append([ms, "100", "101", "99", "100.5", "10", ms + 86_399_999])
    forming = int((last_close + timedelta(hours=1)).timestamp() * 1000)
    return rows + [[forming, "100", "101", "99", "100.5", "1", forming + 86_399_999]]


def _one_d_instant():
    return next(i for i in lattice.lattice_instants("1D", START, START + timedelta(days=4))
                if i >= START)


@pytest.mark.parametrize(
    ("rows", "ok"),
    [
        (lambda t: _daily_rows(t, 375), True),
        (lambda t: _daily_rows(t, 375, gap_at=200), False),
        (lambda t: _daily_rows(t, 375, hour=3), False),
        (lambda t: _daily_rows(t, 300), False),
        (lambda t: _daily_rows(t - timedelta(days=1), 375), False),
    ],
    ids=["good", "gap", "not-midnight", "short", "last-close-not-the-instant"],
)
def test_the_1d_fetch(monkeypatch, rows, ok):
    instant = _one_d_instant()
    requests, outcomes = [], []

    class OneD(Adapter):
        def __init__(self, settings):
            def get_json(**kwargs):
                requests.append(kwargs["params"])
                return rows(instant)

            self.http_client = SimpleNamespace(get_json=get_json)

    def step(now, *, config, fetch_snapshot, fetch_window, **_kwargs):
        if lattice.latest_due_instant("1D", now) == instant and not outcomes:
            cell = next(c for c in lattice.PILOT_CELLS if c.timeframe == "1D")
            try:
                window = fetch_window(cell, SimpleNamespace(normalized_symbol="SOL/USDT"))
                outcomes.append((len(window.candles), window.last_close_utc))
            except windows.WindowUnavailable:
                outcomes.append("WINDOW_UNAVAILABLE")
        return {"results": [], "stopped": False}

    clock = Clock(instant - timedelta(seconds=5))
    _wire(monkeypatch, Store(), clock, adapter=OneD)
    monkeypatch.setattr(lattice, "lattice_step", step)
    _run(clock, instant + timedelta(hours=1), TelemetrySink(), started_at=clock.now,
         start=instant)
    assert requests[0] == {"symbol": "SOLUSDT", "interval": "1d", "limit": 376}
    assert outcomes == ([(371, instant)] if ok else ["WINDOW_UNAVAILABLE"])


def test_the_day_7_checkpoint_is_emitted_once_with_sanitized_counts(monkeypatch):
    clock, sink = Clock(START - timedelta(seconds=5)), TelemetrySink()
    _wire(monkeypatch, Store(), clock)
    monkeypatch.setattr(lattice, "lattice_step", lambda *a, **k: {
        "results": [{"status": "INSERTED"}], "stopped": False})
    _run(clock, START + timedelta(days=8), sink, started_at=clock.now)
    checkpoints = [e for e in sink.events if e["event"] == "lattice_pilot_checkpoint"]
    assert len(checkpoints) == 1
    clean = checkpoints[0]  # the sink holds the sanitized event
    assert clean["scope"] == "since_process_start"
    assert clean["inserted"] > 0 and clean["errors"] == 0


def test_a_cold_start_inside_an_instants_grace_window_still_issues_it(monkeypatch):
    first = START
    store = Store()
    clock = Clock(first + timedelta(seconds=10))  # before first's wake at first + GRACE
    _wire(monkeypatch, store, clock)
    _run(clock, START + timedelta(hours=2), TelemetrySink(), started_at=clock.now)
    assert store.entries.count(("15m", first.isoformat())) == 1


def test_a_failed_last_wake_still_gives_every_slot_exactly_one_entry(monkeypatch):
    end = START + timedelta(hours=6)
    last_15m = max(i for i in lattice.lattice_instants("15m", START, end) if i < end)

    class FailsAtTheLastWake(Store):
        def record_missed(self, entry):
            key = (entry["timeframe"], entry["lattice_instant_utc"])
            if key == ("15m", last_15m.isoformat()) and not getattr(self, "failed", False):
                self.failed = True
                raise RuntimeError("synthetic database failure")
            return super().record_missed(entry)

    store, clock = FailsAtTheLastWake(), Clock(START - timedelta(seconds=5))
    _wire(monkeypatch, store, clock)
    _run(clock, end, TelemetrySink(), started_at=clock.now)
    assert len(store.entries) == len(set(store.entries))
    for timeframe in lattice.PILOT_TIMEFRAMES:
        grid = lattice.lattice_instants(timeframe, START, end)
        planned = [i.isoformat() for i in grid if i < end]
        assert sorted(i for tf, i in store.entries if tf == timeframe) == sorted(planned)


def test_no_checkpoint_from_a_process_that_starts_after_day_7(monkeypatch):
    late = START + lattice.PILOT_CHECKPOINT + timedelta(hours=1)
    clock, sink = Clock(late), TelemetrySink()
    _wire(monkeypatch, Store(), clock)
    _run(clock, late + timedelta(hours=1), sink, started_at=late)
    assert not [e for e in sink.events if e["event"] == "lattice_pilot_checkpoint"]


def test_the_end_is_reported(monkeypatch):
    clock, sink = Clock(START - timedelta(seconds=5)), TelemetrySink()
    _wire(monkeypatch, Store(), clock)
    _run(clock, START + timedelta(hours=1), sink, started_at=clock.now)
    assert sink.events[-1] == {"event": "lattice_pilot_state", "state": "ENDED"}


def test_the_store_connection_is_bounded_inside_its_own_transaction(monkeypatch):
    import sys

    calls = []

    class Conn:
        def execute(self, sql):
            calls.append(("execute", sql))

        def close(self):
            calls.append(("close",))

    def connect(url, **kwargs):
        calls.append(("connect", url, kwargs))
        return Conn()

    monkeypatch.setitem(sys.modules, "psycopg", SimpleNamespace(connect=connect))
    lattice_pilot._connect("postgresql://synthetic")
    assert calls[0] == ("connect", "postgresql://synthetic", {
        "connect_timeout": 10, "tcp_user_timeout": 10000, "prepare_threshold": None,
        "autocommit": False})
    assert calls[1] == ("execute", "SET LOCAL statement_timeout = '5000'")
    assert "options" not in calls[0][2]


def test_the_module_body_does_nothing_at_import():
    import ast
    from pathlib import Path

    source = Path(lattice_pilot.__file__).read_text(encoding="utf-8")
    for node in ast.parse(source).body:
        assert isinstance(node, (ast.Import, ast.ImportFrom, ast.FunctionDef, ast.AsyncFunctionDef,
                                 ast.ClassDef, ast.Assign, ast.AnnAssign, ast.Expr)), type(node)
        if isinstance(node, ast.Expr):
            assert isinstance(node.value, ast.Constant)  # the docstring only
        if isinstance(node, (ast.Assign, ast.AnnAssign)) and node.value is not None:
            assert isinstance(node.value, (ast.Constant, ast.Call)), ast.unparse(node)
            if isinstance(node.value, ast.Call):  # only timedelta(...) constants
                assert ast.unparse(node.value.func) == "timedelta", ast.unparse(node)
    assert "lattice.pilot_config(" in source and "PilotConfig(" not in source


def test_a_process_started_long_before_the_start_logs_nothing_before_it(monkeypatch):
    # The switch-ON deployed ahead of the named start (review R2-1): START is not on the 1D lattice,
    # whose last instant before it is 2026-11-08T00Z; without the window clip that instant would be
    # logged missed at the first wake, outside [start, end).
    store, clock = Store(), Clock(START - timedelta(hours=25))
    _wire(monkeypatch, store, clock)
    _run(clock, START + timedelta(hours=1), TelemetrySink(), started_at=clock.now)
    assert store.entries
    assert all(datetime.fromisoformat(i) >= START for _, i in store.entries)
    assert ("1D", "2026-11-08T00:00:00+00:00") not in store.entries
