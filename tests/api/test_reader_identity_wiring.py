"""E2: the app's direct-Postgres consumers all take the evidence reader's URL, and each start
reports the reader's identity once.

UCPE_SPACE_DB_URL, when set, reaches every consumer: the skill-evidence repository, the calibration
endpoint, the F1 ledger and credential registry, and the persistence fallback. Without it everything
stays on SUPABASE_DB_URL, exactly as before. Nothing here connects anywhere.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from crypto_probability_engine.api import app as app_module
from crypto_probability_engine.api import automation_endpoint
from crypto_probability_engine.config.settings import Settings
from crypto_probability_engine.persistence import reader_identity
from crypto_probability_engine.telemetry.events import EVENTS_SINK

LEGACY = "postgresql://legacy-synthetic.invalid/none"
CUTOVER = "postgresql://cutover-synthetic.invalid/none"


@pytest.fixture
def consumers(monkeypatch) -> dict[str, list]:
    seen: dict[str, list] = {
        "operator": [], "persistence": [], "calibration": [], "ledger": [], "registry": [],
        "report": [],
    }

    def recording(name: str, result=None):
        def record(settings_or_url, *args, **kwargs):
            url = getattr(settings_or_url, "supabase_db_url", settings_or_url)
            seen[name].append(url)
            return result

        return record

    def calibration(_app, *, require_app_session, settings):
        seen["calibration"].append(settings.supabase_db_url)

    monkeypatch.setattr(app_module, "build_operator_repository", recording("operator"))
    monkeypatch.setattr(app_module, "build_persistence_repository", recording("persistence"))
    monkeypatch.setattr(app_module, "register_calibration_endpoint", calibration)
    monkeypatch.setattr(automation_endpoint, "PostgresAutomationLedger", recording("ledger"))
    monkeypatch.setattr(automation_endpoint, "PostgresCredentialRegistry", recording("registry"))
    monkeypatch.setattr(
        reader_identity, "start_report",
        lambda settings, source: seen["report"].append((settings.supabase_db_url, source)),
    )
    return seen


def _start(settings: Settings) -> None:
    with TestClient(app_module.create_app(settings)):
        pass


def test_the_cutover_secret_reaches_every_direct_postgres_consumer(monkeypatch, consumers):
    monkeypatch.setenv("UCPE_SPACE_DB_URL", CUTOVER)
    _start(Settings(**{"supabase_db_url": LEGACY}, data_mode="fixture"))
    assert consumers == {
        "operator": [CUTOVER], "persistence": [CUTOVER], "calibration": [CUTOVER],
        "ledger": [CUTOVER], "registry": [CUTOVER], "report": [(CUTOVER, "UCPE_SPACE_DB_URL")],
    }


def test_without_it_every_consumer_keeps_supabase_db_url(monkeypatch, consumers):
    monkeypatch.delenv("UCPE_SPACE_DB_URL", raising=False)
    _start(Settings(**{"supabase_db_url": LEGACY}, data_mode="fixture"))
    assert consumers == {
        "operator": [LEGACY], "persistence": [LEGACY], "calibration": [LEGACY],
        "ledger": [LEGACY], "registry": [LEGACY], "report": [(LEGACY, "SUPABASE_DB_URL")],
    }


def test_each_start_reports_once(monkeypatch, consumers):
    monkeypatch.delenv("UCPE_SPACE_DB_URL", raising=False)
    app = app_module.create_app(Settings(data_mode="fixture"))
    assert consumers["report"] == []  # building the app reports nothing; starting it does
    with TestClient(app):
        pass
    assert consumers["report"] == [(None, "none")]


def test_a_start_without_a_database_reports_not_configured_and_connects_nowhere(monkeypatch):
    import psycopg

    def refuse(*_args, **_kwargs):
        raise AssertionError("connected at startup")

    monkeypatch.delenv("UCPE_SPACE_DB_URL", raising=False)
    monkeypatch.setattr(psycopg, "connect", refuse)
    _start(Settings(data_mode="fixture"))
    assert EVENTS_SINK.events[-1] == {
        "event": "evidence_reader_identity", "db_role": "n/a", "verdict": "NOT_CONFIGURED",
        "db_url_source": "none", "release_id": reader_identity.RELEASE_ID,
    }
