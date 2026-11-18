import importlib

from fastapi.testclient import TestClient

from crypto_probability_engine import lattice_pilot
from crypto_probability_engine.api import app as app_module
from crypto_probability_engine.config.settings import Settings
from crypto_probability_engine.telemetry.events import EVENTS_SINK


def test_pilot_module_import_emits_no_event():
    EVENTS_SINK.events.clear()
    importlib.reload(lattice_pilot)
    assert lattice_pilot.WRITER_DB_URL_ENV == "UCPE_LATTICE_DB_URL"
    assert lattice_pilot.lattice.LATTICE_ENABLED is True
    assert not any(event["event"].startswith("lattice_pilot_") for event in EVENTS_SINK.events)


def test_off_lifespan_is_silent_and_closes_pool_once(monkeypatch):
    EVENTS_SINK.events.clear()
    calls = []
    monkeypatch.setattr(app_module.reader_identity, "start_report", lambda *args: None)
    monkeypatch.setattr(app_module, "close_pool", lambda: calls.append("close"))
    # Keep explicit coverage of the OFF path after the default switch-ON change.
    monkeypatch.setattr(lattice_pilot.lattice, "LATTICE_ENABLED", False)
    with TestClient(app_module.create_app(Settings(data_mode="fixture"))):
        pass
    assert calls == ["close"]
    pilot_events = [event for event in EVENTS_SINK.events
                    if event["event"].startswith("lattice_pilot_")]
    assert not pilot_events


def test_on_lifespan_without_writer_url_is_not_configured(monkeypatch):
    from datetime import UTC, datetime

    class FixedDateTime:
        @staticmethod
        def now(tz):
            assert tz is UTC
            return datetime(2026, 11, 23, tzinfo=UTC)

    EVENTS_SINK.events.clear()
    monkeypatch.setattr(lattice_pilot, "datetime", FixedDateTime)
    monkeypatch.delenv("UCPE_LATTICE_DB_URL", raising=False)
    connections = []
    monkeypatch.setattr(lattice_pilot, "_connect", lambda url: connections.append(url))
    monkeypatch.setattr(app_module.reader_identity, "start_report", lambda *args: None)
    monkeypatch.setattr(app_module, "close_pool", lambda: None)
    with TestClient(app_module.create_app(Settings(data_mode="fixture"))):
        pass
    pilot_events = [event for event in EVENTS_SINK.events
                    if event["event"].startswith("lattice_pilot_")]
    assert pilot_events == [{"event": "lattice_pilot_state", "state": "NOT_CONFIGURED"}]
    assert connections == []


def test_on_lifespan_awaits_pilot_stop_before_pool_close(monkeypatch):
    order = []

    class Handle:
        async def stop(self):
            order.append("stop")

    monkeypatch.setattr(app_module.reader_identity, "start_report", lambda *args: None)
    monkeypatch.setattr(app_module, "close_pool", lambda: order.append("close"))
    monkeypatch.setattr(lattice_pilot, "start", lambda settings: Handle())
    with TestClient(app_module.create_app(Settings(data_mode="fixture"))):
        pass
    assert order == ["stop", "close"]
