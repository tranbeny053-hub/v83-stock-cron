"""SEC-1 (governing plan §13): the request guard's early refusals and browser security headers.

Refusals are proven to happen before any route runs: the analysis entry point is replaced by a stub
that records each call and answers 400, so reaching a route is visible and a refusal leaves the
record empty.
"""

from __future__ import annotations

import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from crypto_probability_engine.api import app as app_module
from crypto_probability_engine.api.app import create_app
from crypto_probability_engine.api.auth import dev_limiter, hash_code, session_limiter
from crypto_probability_engine.api.errors import api_error
from crypto_probability_engine.api.request_guard import (
    CONTENT_SECURITY_POLICY,
    HUMAN_BODY_MAX_BYTES,
    RequestGuardMiddleware,
)
from crypto_probability_engine.api.schemas import BatchAnalysisRequest, ErrorCode
from crypto_probability_engine.config.settings import Settings
from crypto_probability_engine.telemetry.events import EVENTS_SINK

ALLOWED_ORIGIN = "https://operator.example"
ANALYZE = {"symbol": "BTCUSDT", "timeframe": "1H"}
JSON_TYPE = {"Content-Type": "application/json"}


def make_client() -> TestClient:
    session_limiter.reset()
    dev_limiter.reset()
    settings = Settings(
        access_code_hash=hash_code("operator-test-code"),
        session_signing_key="test-signing-key",
        session_cookie_secure=False,
        strict_cors_origins=(ALLOWED_ORIGIN,),
    )
    return TestClient(create_app(settings))


def logged_in() -> TestClient:
    client = make_client()
    assert client.post("/v1/auth/login", json={"code": "operator-test-code"}).status_code == 200
    return client


@pytest.fixture
def analyses(monkeypatch: pytest.MonkeyPatch) -> list[object]:
    calls: list[object] = []

    def stub(body: object, **_: object) -> dict:
        calls.append(body)
        raise api_error(400, ErrorCode.QUANT_COMPUTE_FAILED, "stub reached")

    monkeypatch.setattr(app_module, "analyze_request", stub)
    return calls


def error_code(response) -> str:
    return response.json()["detail"]["error"]["code"]


# ------------------------------------------------------------------------------------- headers


@pytest.mark.parametrize("path", ["/", "/index.html", "/app.js", "/styles.css", "/healthcheck",
                                  "/v1/build-info", "/v1/system_status", "/no-such-path"])
def test_every_response_carries_the_browser_security_headers(path: str) -> None:
    response = make_client().get(path)
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["content-security-policy"] == CONTENT_SECURITY_POLICY


def test_the_policy_is_self_only_and_framing_is_the_app_or_the_hugging_face_page() -> None:
    directives = dict(part.strip().split(" ", 1) for part in CONTENT_SECURITY_POLICY.split(";"))
    assert directives["frame-ancestors"] == "'self' https://huggingface.co"
    assert directives["object-src"] == "'none'"
    for name, value in directives.items():
        if name not in ("frame-ancestors", "object-src"):
            assert value == "'self'", name
    assert "unsafe" not in CONTENT_SECURITY_POLICY and "data:" not in CONTENT_SECURITY_POLICY


def test_the_frontend_needs_nothing_the_policy_forbids() -> None:
    root = app_module.FRONTEND_DIR
    index = (root / "index.html").read_text(encoding="utf-8")
    script = (root / "app.js").read_text(encoding="utf-8")
    styles = (root / "styles.css").read_text(encoding="utf-8")
    assert "<script>" not in index and "<style" not in index and " style=" not in index
    assert index.count("<script ") == 1 and 'src="/app.js' in index
    for text in (index, script, styles):
        assert "http://" not in text and "https://" not in text, "no external resource"
    for forbidden in ("eval(", "new Function", "setAttribute(\"style", "document.write"):
        assert forbidden not in script


def test_api_responses_are_no_store_and_the_static_frontend_keeps_its_caching() -> None:
    client = make_client()
    assert client.get("/v1/system_status").headers.get_list("cache-control") == ["no-store"]
    # A route that sets its own Cache-Control keeps exactly one.
    assert client.get("/v1/build-info").headers.get_list("cache-control") == ["no-store"]
    assert "no-store" not in client.get("/app.js").headers.get("cache-control", "")
    assert "no-store" not in client.get("/styles.css").headers.get("cache-control", "")


# -------------------------------------------------------------------------------------- cross-site


@pytest.mark.parametrize("site", ["cross-site", "same-site", "CROSS-SITE"])
def test_a_cross_site_write_is_refused_before_any_route_runs(site: str, analyses: list) -> None:
    client = logged_in()
    response = client.post("/v1/analyze", json=ANALYZE, headers={"Sec-Fetch-Site": site})
    assert response.status_code == 403 and error_code(response) == "CROSS_SITE_REFUSED"
    assert response.headers["cache-control"] == "no-store"
    assert analyses == []


def test_cross_site_login_logout_and_watchlist_writes_are_refused() -> None:
    client = logged_in()
    cross = {"Sec-Fetch-Site": "cross-site"}
    login = client.post("/v1/auth/login", json={"code": "operator-test-code"}, headers=cross)
    assert login.status_code == 403 and "set-cookie" not in login.headers
    assert client.post("/v1/auth/logout", headers=cross).status_code == 403
    watch = client.post("/v1/watchlist", json={"symbol": "BTCUSDT"}, headers=cross)
    assert watch.status_code == 403
    assert client.delete("/v1/watchlist/BTCUSDT", headers=cross).status_code == 403


@pytest.mark.parametrize("site", ["same-origin", "none", None])
def test_same_origin_navigation_and_headerless_writes_reach_the_route(site, analyses: list) -> None:
    client = logged_in()
    headers = {} if site is None else {"Sec-Fetch-Site": site}
    response = client.post("/v1/analyze", json=ANALYZE, headers=headers)
    assert response.status_code == 400
    assert response.json()["detail"]["error"]["message"] == "stub reached"
    assert len(analyses) == 1


def test_only_an_operator_allowed_origin_may_write_cross_site(analyses: list) -> None:
    client = logged_in()
    allowed = {"Sec-Fetch-Site": "cross-site", "Origin": ALLOWED_ORIGIN}
    assert client.post("/v1/analyze", json=ANALYZE, headers=allowed).status_code == 400
    other = {"Sec-Fetch-Site": "cross-site", "Origin": "https://attacker.example"}
    assert client.post("/v1/analyze", json=ANALYZE, headers=other).status_code == 403
    assert len(analyses) == 1


def test_reads_are_never_refused_for_their_site() -> None:
    client = make_client()
    response = client.get("/v1/build-info", headers={"Sec-Fetch-Site": "cross-site"})
    assert response.status_code == 200


def test_cors_preflight_still_answers_for_the_allowed_origin() -> None:
    response = make_client().options(
        "/v1/analyze",
        headers={"Origin": ALLOWED_ORIGIN, "Access-Control-Request-Method": "POST",
                 "Sec-Fetch-Site": "cross-site"},
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == ALLOWED_ORIGIN


# ------------------------------------------------------------------------------------------ bodies


def test_an_oversized_body_is_refused_before_any_route_runs(analyses: list) -> None:
    client = logged_in()
    body = json.dumps({**ANALYZE, "symbol": "X" * HUMAN_BODY_MAX_BYTES})
    response = client.post("/v1/analyze", content=body, headers=JSON_TYPE)
    assert response.status_code == 413 and error_code(response) == "REQUEST_TOO_LARGE"
    assert analyses == []


def test_an_oversized_chunked_body_is_refused_too(analyses: list) -> None:
    client = logged_in()
    chunks = (b"x" * 4096 for _ in range(5))  # no Content-Length: chunked transfer encoding
    response = client.post("/v1/analyze", content=chunks, headers=JSON_TYPE)
    assert response.status_code == 413 and error_code(response) == "REQUEST_TOO_LARGE"
    assert analyses == []


def test_the_largest_legitimate_batch_fits_with_a_wide_margin() -> None:
    item = {"symbol": "S" * 32, "analysis_mode": "METRICS_ONLY", "timeframe": "4H",
            "asset_class": "CRYPTO_SPOT", "include_detail": True}
    batch = {"requests": [item] * 5}
    BatchAnalysisRequest.model_validate(batch)
    assert len(json.dumps(batch).encode()) * 8 < HUMAN_BODY_MAX_BYTES


class _Harness:
    """Drives the middleware with exact ASGI messages; the inner app echoes the body it read."""

    def __init__(self, messages: list[dict], headers: list[tuple[bytes, bytes]]) -> None:
        self.messages = list(messages)
        self.received = 0
        self.app_calls: list[bytes] = []
        self.sent: list[dict] = []
        self.scope = {"type": "http", "method": "POST", "path": "/v1/analyze", "headers": headers}

    async def receive(self) -> dict:
        self.received += 1
        return self.messages.pop(0) if self.messages else {"type": "http.disconnect"}

    async def send(self, message: dict) -> None:
        self.sent.append(message)

    async def app(self, scope, receive, send) -> None:
        body = b""
        while True:
            message = await receive()
            body += message.get("body", b"")
            if not message.get("more_body"):
                break
        self.app_calls.append(body)
        after = await receive()  # the original stream continues behind the replay
        self.app_calls.append(after["type"].encode())
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    def run(self) -> _Harness:
        asyncio.run(RequestGuardMiddleware(self.app)(self.scope, self.receive, self.send))
        return self


def _status(harness: _Harness) -> int:
    return next(m["status"] for m in harness.sent if m["type"] == "http.response.start")


OVER_BOUND = str(HUMAN_BODY_MAX_BYTES + 1).encode()


@pytest.mark.parametrize("declared", [OVER_BOUND, b"abc", b"-1", b"9" * 11])
def test_a_declared_length_over_the_bound_or_malformed_is_refused_unread(declared: bytes) -> None:
    messages = [{"type": "http.request", "body": b"{}"}]
    harness = _Harness(messages, [(b"content-length", declared)]).run()
    assert _status(harness) == 413 and harness.received == 0 and harness.app_calls == []


def test_a_body_at_the_bound_is_replayed_whole_and_the_stream_continues() -> None:
    half = HUMAN_BODY_MAX_BYTES // 2
    messages = [{"type": "http.request", "body": b"a" * half, "more_body": True},
                {"type": "http.request", "body": b"b" * half, "more_body": False}]
    harness = _Harness(messages, []).run()
    assert _status(harness) == 200
    assert harness.app_calls == [b"a" * half + b"b" * half, b"http.disconnect"]


def test_a_streamed_body_one_byte_over_the_bound_is_refused() -> None:
    messages = [{"type": "http.request", "body": b"a" * HUMAN_BODY_MAX_BYTES, "more_body": True},
                {"type": "http.request", "body": b"b", "more_body": False}]
    harness = _Harness(messages, []).run()
    assert _status(harness) == 413 and harness.app_calls == []


def test_a_client_that_leaves_mid_body_gets_no_response_and_no_route() -> None:
    harness = _Harness([{"type": "http.request", "body": b"a", "more_body": True}], []).run()
    assert harness.sent == [] and harness.app_calls == []


# -------------------------------------------------------------------------------- F1 and telemetry


def test_the_f1_automation_route_is_passed_through_untouched() -> None:
    client = make_client()
    response = client.post(
        "/v1/automation/radar-evidence",
        content=b"x" * (HUMAN_BODY_MAX_BYTES + 1),
        headers={"Sec-Fetch-Site": "cross-site", "Content-Type": "application/json"},
    )
    # Whatever the route itself answers (it is off by default), none of the guard's refusals or
    # headers appear.
    assert "REQUEST_TOO_LARGE" not in response.text and "CROSS_SITE_REFUSED" not in response.text
    for header in ("content-security-policy", "referrer-policy", "x-content-type-options"):
        assert header not in response.headers


def test_a_refusal_is_still_recorded_as_a_request_event() -> None:
    client = logged_in()
    EVENTS_SINK.events.clear()
    client.post("/v1/analyze", json=ANALYZE, headers={"Sec-Fetch-Site": "cross-site"})
    statuses = [event["status"] for event in EVENTS_SINK.events if event["event"] == "http_request"]
    assert statuses == [403]
