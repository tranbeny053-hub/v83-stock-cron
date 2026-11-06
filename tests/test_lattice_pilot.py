import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from crypto_probability_engine import lattice_pilot
from crypto_probability_engine.quant_ng import lattice
from crypto_probability_engine.telemetry.events import TelemetrySink, sanitize


class Untouchable:
    def __getattribute__(self, name):
        raise AssertionError(f"environment accessed: {name}")


def test_constants_and_off_start_is_silent(monkeypatch):
    assert lattice_pilot.WRITER_DB_URL_ENV is None
    assert lattice.PILOT_START_UTC is None  # named by the owner only in the switch-ON change
    assert lattice.LATTICE_ENABLED is False
    assert lattice_pilot.GRACE_SECONDS == 20
    assert lattice_pilot.STEP_TIMEOUT_SECONDS == 120
    sink = TelemetrySink()
    monkeypatch.setattr(lattice, "LATTICE_ENABLED", False)
    assert lattice_pilot.start(object(), environ=Untouchable(), sink=sink) is None
    assert not sink.events


def test_pilot_events_use_real_sanitizer():
    assert sanitize("lattice_pilot_error", {"exception_class": "StepTimeout"}) == {
        "event": "lattice_pilot_error", "exception_class": "StepTimeout"
    }
    assert sanitize("lattice_pilot_checkpoint", {"scope": "since_process_start", "errors": 2}) == {
        "event": "lattice_pilot_checkpoint", "errors": 2, "scope": "since_process_start"
    }


def test_window_clip_excludes_end_and_before_start():
    start = datetime(2026, 11, 9, tzinfo=UTC)
    end = start + timedelta(hours=1)
    grid = lattice.lattice_instants(
        "15m", start - timedelta(minutes=15), end + timedelta(minutes=15)
    )
    clipped = tuple(point for point in grid if start <= point < end)
    # The 15m lattice steps every 3 bars (45 minutes); 2026-11-09T00:00Z is on it.
    assert clipped == (start, start + timedelta(minutes=45))


class FakeClock:
    def __init__(self, now):
        self.now = now

    def __call__(self):
        return self.now


class RecordingStore:
    def __init__(self):
        self.entries = []

    def record_missed(self, entry):
        instant = datetime.fromisoformat(entry["lattice_instant_utc"])
        self.entries.append((entry["timeframe"], instant))
        return "LOGGED"

    def record_row(self, row):
        self.entries.append((row["timeframe"], datetime.fromisoformat(row["lattice_instant_utc"])))
        return "INSERTED"

    def capture_commit_receipts(self, limit):
        return 0


def _fake_config():
    return SimpleNamespace(cells=lattice.PILOT_CELLS)


def test_run_processes_each_in_window_instant_once_and_final_step(monkeypatch):
    start = datetime(2026, 11, 9, tzinfo=UTC)
    end = start + timedelta(hours=6)
    clock = FakeClock(start)
    store = RecordingStore()
    sleep_calls = []

    async def fake_sleep(seconds):
        sleep_calls.append(seconds)
        clock.now += timedelta(seconds=seconds)

    class FakeAdapter:
        def __init__(self, settings):
            self.http_client = object()

        def fetch_market_snapshot(self, symbol, timeframe):
            from crypto_probability_engine.adapters import http_client
            assert http_client.PROVIDER_COALESCING.get() is False
            raise RuntimeError("synthetic unavailable")

    from crypto_probability_engine.adapters import public_market
    monkeypatch.setattr(public_market, "BinancePublicAdapter", FakeAdapter)
    from crypto_probability_engine.persistence import lattice_store
    monkeypatch.setattr(lattice_store, "LatticeStore", lambda connect: store)
    monkeypatch.setattr(lattice, "LATTICE_ENABLED", True)
    monkeypatch.setattr(lattice_pilot.asyncio, "sleep", fake_sleep)
    asyncio.run(lattice_pilot._run(object(), start, end, _fake_config(), None, TelemetrySink(),
                                   clock, start))
    for timeframe in lattice.PILOT_TIMEFRAMES:
        expected = tuple(i for i in lattice.lattice_instants(timeframe, start, end) if i < end)
        actual = [instant for tf, instant in store.entries if tf == timeframe]
        assert actual == list(expected)
        assert len(actual) == len(set(actual))
    assert all(start <= instant < end for _, instant in store.entries)
    assert sleep_calls and clock.now >= end


def test_start_gate_and_load_error_are_sanitized(monkeypatch):
    sink = TelemetrySink()
    monkeypatch.setattr(lattice, "LATTICE_ENABLED", True)
    monkeypatch.setattr(lattice, "PILOT_START_UTC", None)
    assert lattice_pilot.start(object(), sink=sink, environ=Untouchable()) is None
    assert sink.events[-1] == {"event": "lattice_pilot_state", "state": "NOT_CONFIGURED"}
    sink = TelemetrySink()
    monkeypatch.setattr(lattice, "PILOT_START_UTC", datetime(2026, 11, 9, tzinfo=UTC))
    monkeypatch.setattr(lattice_pilot, "WRITER_DB_URL_ENV", "DB_URL")
    monkeypatch.setattr(lattice_pilot, "_load_specs", lambda: (_ for _ in ()).throw(RuntimeError()))
    assert lattice_pilot.start(object(), clock=lambda: datetime(2026, 11, 9, tzinfo=UTC),
                               environ={"DB_URL": "synthetic"}, sink=sink) is None
    assert sink.events[-1] == {"event": "lattice_pilot_state", "exception_class": "RuntimeError",
                               "state": "ERROR"}
