"""The automation route's database transport fails closed and assumes no connectivity.

Nothing connects at startup. A refused or missing credential never reaches the database. Every
connection is bounded and safe behind Supabase's transaction pooler. A missing, unreachable or
failing database answers 503 LEDGER_UNAVAILABLE and writes nothing anywhere else. Whether the
Space can reach the database is NOT assumed: it is unproven until the post-apply canary.
"""

import pytest
from fastapi.testclient import TestClient

from crypto_probability_engine.api.app import create_app
from crypto_probability_engine.automation.config import ENV_ENABLED
from crypto_probability_engine.automation.credentials import (
    CREDENTIAL_HEADER,
    PostgresCredentialRegistry,
)
from crypto_probability_engine.automation.ledger import PostgresAutomationLedger
from crypto_probability_engine.automation.service import RadarEvidenceService
from crypto_probability_engine.config.settings import Settings
from tests.automation.conftest import AUTOMATION_PATH, request_body, token

SYNTHETIC_URL = "postgresql://synthetic-never-contacted.invalid/none"


class RecordingDriver:
    def __init__(self, failure: Exception | None = None):
        self.failure = failure
        self.connects: list[tuple[tuple, dict]] = []

    def connect(self, *args, **kwargs):
        self.connects.append((args, kwargs))
        raise self.failure or OSError("synthetic: the host cannot be reached")


@pytest.fixture
def driver(monkeypatch):
    import psycopg

    recording = RecordingDriver()
    monkeypatch.setattr(psycopg, "connect", recording.connect)
    return recording


def production_wired_app(monkeypatch, *, enabled: bool):
    """The app exactly as production builds it, with the fixture analysis and no database URL."""

    monkeypatch.setenv(ENV_ENABLED, "1" if enabled else "0")
    return create_app(Settings(data_mode="fixture"))


def test_building_the_app_never_connects(monkeypatch, driver):
    app = production_wired_app(monkeypatch, enabled=True)
    with TestClient(app):
        pass
    assert driver.connects == []


@pytest.mark.parametrize(
    ("headers", "status"),
    [
        ({}, 401),
        ({CREDENTIAL_HEADER: "synthetic-malformed"}, 401),
        ({CREDENTIAL_HEADER: token(), "Cookie": "ucpe_session=synthetic"}, 403),
    ],
)
def test_refused_callers_never_reach_the_database(monkeypatch, driver, headers, status):
    with TestClient(production_wired_app(monkeypatch, enabled=True)) as client:
        response = client.post(AUTOMATION_PATH, json=request_body(), headers=headers)
    assert response.status_code == status
    assert driver.connects == []


def test_a_disabled_route_never_reaches_the_database(monkeypatch, driver):
    with TestClient(production_wired_app(monkeypatch, enabled=False)) as client:
        response = client.post(
            AUTOMATION_PATH, json=request_body(), headers={CREDENTIAL_HEADER: token()}
        )
    assert response.status_code == 503 and response.json()["error"]["code"] == (
        "AUTOMATION_DISABLED"
    )
    assert driver.connects == []


def test_no_database_url_answers_503_without_connecting(monkeypatch, driver):
    with TestClient(production_wired_app(monkeypatch, enabled=True)) as client:
        response = client.post(
            AUTOMATION_PATH, json=request_body(), headers={CREDENTIAL_HEADER: token()}
        )
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "LEDGER_UNAVAILABLE"
    assert response.headers["cache-control"] == "no-store"
    assert driver.connects == []


@pytest.mark.parametrize(
    "failure",
    [OSError("synthetic: no route to host"), TimeoutError("synthetic: connect timed out")],
)
def test_an_unreachable_database_answers_503_after_one_bounded_attempt(monkeypatch, failure):
    driver = RecordingDriver(failure)
    monkeypatch.setenv(ENV_ENABLED, "1")
    settings = Settings(data_mode="fixture")
    app = create_app(settings)
    app.state.automation_service = RadarEvidenceService(
        settings=settings,
        ledger=PostgresAutomationLedger(SYNTHETIC_URL, connect=driver.connect),
        registry=PostgresCredentialRegistry(SYNTHETIC_URL, connect=driver.connect),
    )
    with TestClient(app) as client:
        response = client.post(
            AUTOMATION_PATH, json=request_body(), headers={CREDENTIAL_HEADER: token()}
        )
    assert response.status_code == 503
    body = response.json()
    assert body["error"]["code"] == "LEDGER_UNAVAILABLE"
    assert "synthetic" not in response.text and SYNTHETIC_URL not in response.text
    assert len(driver.connects) == 1, "the registry's one attempt; the ledger is never reached"
    args, kwargs = driver.connects[0]
    assert args == (SYNTHETIC_URL,)
    assert kwargs["connect_timeout"] <= 3 and kwargs["prepare_threshold"] is None


def test_the_production_wiring_uses_the_postgres_registry_and_ledger_on_one_url():
    app = create_app(Settings(data_mode="fixture"))
    service = app.state.automation_service
    assert isinstance(service._registry, PostgresCredentialRegistry)
    assert isinstance(service._ledger, PostgresAutomationLedger)
    assert service._registry._database_url is None and service._ledger._database_url is None
