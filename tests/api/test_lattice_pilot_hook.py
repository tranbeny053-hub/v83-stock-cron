from fastapi.testclient import TestClient

from crypto_probability_engine import lattice_pilot
from crypto_probability_engine.api import app as app_module
from crypto_probability_engine.config.settings import Settings
from crypto_probability_engine.telemetry.events import EVENTS_SINK


def test_pilot_module_import_is_dormant():
    assert lattice_pilot.WRITER_DB_URL_ENV is None
    assert lattice_pilot.lattice.LATTICE_ENABLED is False
    assert not any(event["event"].startswith("lattice_pilot_") for event in EVENTS_SINK.events)


def test_off_lifespan_is_silent_and_closes_pool_once(monkeypatch):
    EVENTS_SINK.events.clear()
    calls = []
    monkeypatch.setattr(app_module.reader_identity, "start_report", lambda *args: None)
    monkeypatch.setattr(app_module, "close_pool", lambda: calls.append("close"))
    # The real OFF path: LATTICE_ENABLED is False by default, so start() returns None itself.
    with TestClient(app_module.create_app(Settings(data_mode="fixture"))):
        pass
    assert calls == ["close"]
    pilot_events = [event for event in EVENTS_SINK.events
                    if event["event"].startswith("lattice_pilot_")]
    assert not pilot_events


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
