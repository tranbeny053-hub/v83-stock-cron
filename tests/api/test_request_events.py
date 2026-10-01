"""Plan §10: one sanitized `http_request` event per request; `analysis_completed` per analysis.

The F1 automation route, a 200 liveness probe and a successful static asset are not recorded; a
body, a header, a cookie, the query string and the client address never are. Telemetry failure
never changes a response or a probability.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from fastapi import BackgroundTasks, FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.testclient import TestClient

from crypto_probability_engine.api import analysis_service
from crypto_probability_engine.api.app import create_app
from crypto_probability_engine.api.auth import dev_limiter, hash_code, session_limiter
from crypto_probability_engine.api.request_events import RequestEventMiddleware
from crypto_probability_engine.config.build_info import RELEASE_ID
from crypto_probability_engine.config.settings import Settings
from crypto_probability_engine.telemetry.events import (
    CURRENT_REQUEST_ID,
    EVENTS_SINK,
    TelemetrySink,
)

REQUEST_FIELDS = {"event", "request_id", "release_id", "method", "route", "status", "duration_ms",
                  "error_class"}


def _small_app(tmp_path: Path) -> tuple[TestClient, TelemetrySink]:
    sink = TelemetrySink()
    app = FastAPI()

    @app.get("/v1/items/{item_id}")
    def item(item_id: str) -> dict:
        return {"id": item_id}

    @app.get("/healthcheck")
    def health() -> dict:
        return {"status": "OK"}

    @app.post("/v1/automation/radar-evidence")
    def automation() -> dict:
        return {"ok": True, "request_id": CURRENT_REQUEST_ID.get()}

    @app.get("/v1/whoami")
    def whoami() -> dict:
        return {"request_id": CURRENT_REQUEST_ID.get()}

    @app.get("/v1/slow-background")
    def slow_background(background_tasks: BackgroundTasks) -> dict:
        background_tasks.add_task(time.sleep, 0.4)
        return {"ok": True}

    @app.get("/v1/boom")
    def boom() -> dict:
        raise RuntimeError("boom")

    (tmp_path / "app.js").write_text("console.log(1);\n", encoding="utf-8")
    app.mount("/", StaticFiles(directory=tmp_path), name="frontend")
    app.add_middleware(RequestEventMiddleware, sink=sink)
    return TestClient(app, raise_server_exceptions=False), sink


def test_a_request_is_one_event_with_the_route_template_and_nothing_private(tmp_path: Path) -> None:
    client, sink = _small_app(tmp_path)
    client.cookies.set("ucpe", "cookie-value")
    response = client.get("/v1/items/private-looking?token=abc",
                          headers={"Authorization": "Bearer xyz"})
    assert response.status_code == 200
    (event,) = sink.events
    assert set(event) == REQUEST_FIELDS
    assert (event["method"], event["route"], event["status"]) == ("GET", "/v1/items/{item_id}", 200)
    assert event["release_id"] == RELEASE_ID and len(str(event["request_id"])) == 16
    assert event["error_class"] is None and isinstance(event["duration_ms"], float)
    text = repr(event)
    leaks = ("private-looking", "token", "abc", "Bearer", "xyz", "cookie-value", "testclient")
    for leaked in leaks:
        assert leaked not in text, leaked


def test_the_automation_route_quiet_probes_and_static_assets_are_not_recorded(
    tmp_path: Path,
) -> None:
    client, sink = _small_app(tmp_path)
    # F1's route is untouched: no event, and no request id is even set for it.
    assert client.post("/v1/automation/radar-evidence").json() == {"ok": True, "request_id": None}
    assert client.get("/healthcheck").status_code == 200
    assert client.get("/app.js").status_code == 200
    assert list(sink.events) == []
    assert client.get("/missing.css").status_code == 404
    assert [(event["route"], event["status"]) for event in sink.events] == [("static", 404)]


def test_an_unhandled_error_is_recorded_and_still_answers_500(tmp_path: Path) -> None:
    client, sink = _small_app(tmp_path)
    assert client.get("/v1/boom").status_code == 500
    (event,) = sink.events
    assert (event["route"], event["status"], event["error_class"]) == ("/v1/boom", 500,
                                                                       "RuntimeError")


def test_a_failing_sink_never_changes_the_response(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, sink = _small_app(tmp_path)

    def broken(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("telemetry down")

    monkeypatch.setattr(sink, "record", broken)
    assert client.get("/v1/items/7").json() == {"id": "7"}


def test_the_request_id_is_fresh_per_request_and_shared_with_the_endpoint(tmp_path: Path) -> None:
    client, sink = _small_app(tmp_path)
    first = client.get("/v1/whoami").json()["request_id"]
    second = client.get("/v1/whoami").json()["request_id"]
    assert [event["request_id"] for event in sink.events] == [first, second]
    assert first != second and CURRENT_REQUEST_ID.get() is None


def test_the_duration_ends_at_the_last_response_byte_not_after_background_work(
    tmp_path: Path,
) -> None:
    client, sink = _small_app(tmp_path)
    started = time.perf_counter()
    assert client.get("/v1/slow-background").json() == {"ok": True}
    waited_ms = (time.perf_counter() - started) * 1000
    (event,) = sink.events
    assert waited_ms >= 380, "the test client also waits for the background task"
    assert event["duration_ms"] < 200, event["duration_ms"]


def _real_client() -> TestClient:
    session_limiter.reset()
    dev_limiter.reset()
    settings = Settings(
        access_code_hash=hash_code("operator-test-code"),
        session_signing_key="test-signing-key",
        session_cookie_secure=False,
        data_mode="fixture",
    )
    client = TestClient(create_app(settings))
    assert client.post("/v1/auth/login", json={"code": "operator-test-code"}).status_code == 200
    return client


def _analyze(client: TestClient) -> dict:
    response = client.post("/v1/analyze", json={"symbol": "BTC/USDT", "timeframe": "4H"})
    assert response.status_code == 200, response.text
    return response.json()


def test_the_real_app_records_requests_and_analyses_but_never_the_automation_route() -> None:
    client = _real_client()
    EVENTS_SINK.events.clear()
    assert client.get("/v1/build-info").status_code == 200
    assert client.get("/healthcheck").status_code == 200
    client.post("/v1/automation/radar-evidence", json={})
    result = _analyze(client)
    requests = [event for event in EVENTS_SINK.events if event["event"] == "http_request"]
    assert [event["route"] for event in requests] == ["/v1/build-info", "/v1/analyze"]
    (analysis,) = [event for event in EVENTS_SINK.events if event["event"] == "analysis_completed"]
    assert analysis["run_id"] == result["run_id"]
    assert analysis["request_id"] == requests[-1]["request_id"], "one id links the two events"
    assert (analysis["symbol"], analysis["timeframe"]) == ("BTC/USDT", "4H")
    assert analysis["prediction_origin"] == "USER_REQUESTED"
    assert analysis["is_live_data"] is False


def test_telemetry_failure_never_changes_an_analysis(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _real_client()
    baseline = _analyze(client)

    def broken(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("telemetry down")

    monkeypatch.setattr(analysis_service, "emit", broken)
    monkeypatch.setattr(EVENTS_SINK, "record", broken)
    degraded = _analyze(client)
    for key in ("probability_state", "gate_result", "score_stack", "decision_brief"):
        assert degraded[key] == baseline[key], key
