from datetime import UTC, datetime, timedelta

from crypto_probability_engine import lattice_pilot
from crypto_probability_engine.quant_ng import lattice
from crypto_probability_engine.telemetry.events import TelemetrySink, sanitize


class Untouchable:
    def __getattribute__(self, name):
        raise AssertionError(f"environment accessed: {name}")


def test_constants_and_off_start_is_silent(monkeypatch):
    assert lattice_pilot.WRITER_DB_URL_ENV is None
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
