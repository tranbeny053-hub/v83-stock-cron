"""Machine credentials grant no human route access and do not change human analysis."""

import re

from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from crypto_probability_engine.api import analysis_service
from crypto_probability_engine.api import app as app_module
from crypto_probability_engine.api.auth import SESSION_COOKIE, create_session_token
from crypto_probability_engine.api.schemas import validate_analysis_response
from crypto_probability_engine.automation.credentials import CREDENTIAL_HEADER
from crypto_probability_engine.config.settings import Settings
from tests.automation.conftest import AUTOMATION_PATH, token


def test_every_human_route_refuses_machine_only_authentication(harness_factory):
    harness = harness_factory()
    checked = set()
    for route in harness.app.routes:
        if not isinstance(route, APIRoute) or not route.path.startswith("/v1/"):
            continue
        for method in sorted(route.methods):
            if route.path in {"/v1/build-info", AUTOMATION_PATH} or (
                method == "POST" and route.path in {"/v1/auth/login", "/v1/auth/dev"}
            ):
                continue
            path = re.sub(r"\{[^}]+\}", "synthetic", route.path)
            response = harness.client.request(method, path, headers={CREDENTIAL_HEADER: token()})
            assert response.status_code == 401, (method, route.path, response.text)
            assert token() not in response.text + repr(dict(response.headers))
            checked.add((method, route.path))
    assert {("POST", "/v1/analyze"), ("GET", "/v1/auth/dev"), ("GET", "/v1/runs")} <= checked
    assert len(checked) == 14


def test_automation_is_absent_from_openapi(harness_factory):
    harness = harness_factory()
    assert any(isinstance(r, APIRoute) and r.path == AUTOMATION_PATH for r in harness.app.routes)
    response = harness.client.get("/openapi.json")
    assert response.status_code == 200
    assert AUTOMATION_PATH not in response.json()["paths"]


def test_cors_does_not_grant_machine_credential_header(harness_factory):
    response = harness_factory().client.options(
        AUTOMATION_PATH,
        headers={
            "Origin": "http://localhost:7860",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": CREDENTIAL_HEADER,
        },
    )
    assert response.status_code == 400
    allowed = response.headers.get("access-control-allow-headers", "").lower()
    assert CREDENTIAL_HEADER.lower() not in {value.strip() for value in allowed.split(",")}
    assert "*" not in allowed


def test_human_analysis_remains_valid_and_schedules_user_requested_persistence(
    fixture_market,
    monkeypatch,
):
    settings = Settings(session_signing_key="test-signing-key", data_mode="fixture")
    app = app_module.create_app(settings)
    scheduled = []

    def persist_spy(background_tasks, repository, result, *, prediction_origin):
        scheduled.append((repository, result, prediction_origin))
        # Consume the parked test rows because the real persistence scheduler is replaced.
        analysis_service._pop_prediction_persistence(result)

    monkeypatch.setattr(app_module, "schedule_best_effort_persist", persist_spy)
    monkeypatch.setattr(app_module, "schedule_skill_evidence_refresh", lambda *_args: None)
    with TestClient(app) as client:
        client.cookies.set(SESSION_COOKIE, create_session_token("synthetic-human", settings))
        response = client.post("/v1/analyze", json={"symbol": "BTC", "timeframe": "4H"})
    assert response.status_code == 200, response.text
    validate_analysis_response(response.json())
    assert len(scheduled) == 1
    repository, body, origin = scheduled[0]
    assert repository is app.state.persistence_repository
    assert body == response.json() and origin == "USER_REQUESTED"
