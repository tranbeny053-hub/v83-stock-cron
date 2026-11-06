from crypto_probability_engine import lattice_pilot
from crypto_probability_engine.telemetry.events import EVENTS_SINK


def test_pilot_module_import_is_dormant():
    assert lattice_pilot.WRITER_DB_URL_ENV is None
    assert lattice_pilot.lattice.LATTICE_ENABLED is False
    assert not any(event["event"].startswith("lattice_pilot_") for event in EVENTS_SINK.events)
