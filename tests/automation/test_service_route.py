"""HTTP behavior of the governed machine route, using only synthetic fixture data."""

import json
from datetime import timedelta
from threading import Event
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

from crypto_probability_engine.api.app import create_app
from crypto_probability_engine.api.errors import api_error
from crypto_probability_engine.api.schemas import ErrorCode as ApiErrorCode
from crypto_probability_engine.automation.config import (
    ENV_ENABLED,
    ENV_QUOTA_PER_5MIN,
    ENV_QUOTA_PER_DAY,
)
from crypto_probability_engine.automation.contract import (
    ERROR_SCHEMA_FILE,
    RADAR_EVIDENCE_SCHEMA_FILE,
    parse_request,
)
from crypto_probability_engine.automation.credentials import (
    CREDENTIAL_HEADER,
    RegistryUnavailable,
)
from crypto_probability_engine.automation.ledger import LedgerUnavailable, Outcome
from crypto_probability_engine.config.build_info import build_info_payload
from crypto_probability_engine.config.settings import Settings
from tests.automation.conftest import (
    AUTOMATION_PATH,
    CREDENTIAL_ID,
    SYNTHETIC_SECRET,
    active_record,
    credential_env,
    registry,
    request_body,
    token,
    utc,
)

NOW = utc(2026, 9, 30)
ERROR_VALIDATOR = Draft202012Validator(json.loads(ERROR_SCHEMA_FILE.read_text()))
SUCCESS_VALIDATOR = Draft202012Validator(json.loads(RADAR_EVIDENCE_SCHEMA_FILE.read_text()))


def assert_private(response, presented=None):
    assert response.headers["cache-control"] == "no-store"
    text = response.text + repr(dict(response.headers))
    assert token() not in text and SYNTHETIC_SECRET not in text
    if presented:
        assert presented not in text


def assert_error(response, code, status, *, presented=None):
    assert_private(response, presented)
    assert response.status_code == status, response.text
    body = response.json()
    ERROR_VALIDATOR.validate(body)
    assert body["error"]["code"] == code
    assert set(body) == {"schema_version", "error"}
    if status == 429:
        retry = body["error"]["retry_after_seconds"]
        assert retry >= 1 and response.headers["retry-after"] == str(retry)
    return body


def seed(harness, *, body=None, now=NOW, outcome=None):
    parsed = parse_request(json.dumps(body or request_body()).encode())
    result = harness.ledger.reserve(
        credential_id=CREDENTIAL_ID,
        client_request_id=parsed.client_request_id,
        request_fingerprint=parsed.fingerprint,
        release_id=build_info_payload()["release_id"],
        deadline_ms=parsed.deadline_ms,
        now=now,
    )
    if outcome:
        harness.ledger.complete(
            credential_id=CREDENTIAL_ID,
            client_request_id=parsed.client_request_id,
            outcome=outcome,
            now=now,
        )
    return result


def test_plain_app_kill_switch_defaults_off(monkeypatch):
    for name in (ENV_ENABLED, ENV_QUOTA_PER_5MIN, ENV_QUOTA_PER_DAY):
        monkeypatch.delenv(name, raising=False)
    # Explicit fixture Settings avoids reading any real environment configuration.
    with TestClient(create_app(Settings(data_mode="fixture"))) as client:
        response = client.post(
            AUTOMATION_PATH, json=request_body(), headers={CREDENTIAL_HEADER: token()}
        )
    assert_error(response, "AUTOMATION_DISABLED", 503)


def test_enabled_with_an_empty_registry_refuses_every_credential(harness_factory):
    harness = harness_factory(credential_registry=registry(active_record("someone-else")))
    assert_error(harness.post(), "CREDENTIAL_INVALID", 401)
    assert harness.ledger.entries() == []


class _DownRegistry:
    def __init__(self):
        self.lookups = 0

    def lookup(self, credential_id):
        self.lookups += 1
        raise RegistryUnavailable("synthetic outage")


def test_an_unavailable_registry_fails_closed_and_writes_no_row(harness_factory):
    down = _DownRegistry()
    harness = harness_factory(credential_registry=down)
    assert_error(harness.post(), "LEDGER_UNAVAILABLE", 503)
    assert down.lookups == 1 and harness.ledger.entries() == []
    response = harness.client.post(AUTOMATION_PATH, json=request_body())
    assert_error(response, "CREDENTIAL_REQUIRED", 401)
    assert down.lookups == 1, "a missing credential never reaches the registry"


def test_rotation_and_revocation_apply_to_the_next_request_with_no_restart(harness_factory):
    rotated_secret = "SYNTHETIC-rotated-secret-not-a-credential-1"
    harness = harness_factory()
    assert harness.post(body=request_body(client_request_id=str(uuid4()))).status_code == 200
    harness.registry.put(active_record("test-radar-2", rotated_secret))
    rotated = {CREDENTIAL_HEADER: token("test-radar-2", rotated_secret)}
    for headers in (None, rotated):
        response = harness.post(body=request_body(client_request_id=str(uuid4())), headers=headers)
        assert response.status_code == 200, "both credentials work during the overlap"
    harness.registry.put(active_record(status="REVOKED"))
    assert_error(
        harness.post(body=request_body(client_request_id=str(uuid4()))), "CREDENTIAL_INVALID", 401
    )
    response = harness.post(body=request_body(client_request_id=str(uuid4())), headers=rotated)
    assert response.status_code == 200
    assert harness.registry.lookups == 5, "the registry was read on every request: no cache"


def test_a_revoked_credential_cannot_replay_its_earlier_evidence(harness_factory):
    harness = harness_factory()
    first = harness.post()
    assert first.status_code == 200
    harness.registry.put(active_record(status="REVOKED"))
    assert_error(harness.post(), "CREDENTIAL_INVALID", 401)
    assert len(harness.ledger.entries()) == 1


@pytest.mark.parametrize("cookie", ["ucpe_session", "ucpe_dev_session"])
def test_human_cookie_is_refused_even_with_valid_credential(harness_factory, cookie):
    harness = harness_factory()
    harness.client.cookies.set(cookie, "synthetic-human-cookie")
    assert_error(harness.post(), "HUMAN_SESSION_REFUSED", 403)
    assert harness.ledger.entries() == []


@pytest.mark.parametrize("location", ["absent", "query", "body"])
def test_credential_must_be_in_its_header(harness_factory, location):
    harness = harness_factory()
    body = request_body()
    params = {}
    if location == "query":
        params[CREDENTIAL_HEADER] = token()
    if location == "body":
        body[CREDENTIAL_HEADER] = token()
    response = harness.client.post(AUTOMATION_PATH, json=body, params=params)
    assert_error(response, "CREDENTIAL_REQUIRED", 401)
    assert harness.ledger.entries() == []


@pytest.mark.parametrize("presented", ["synthetic-malformed", token("unknown-radar")])
def test_invalid_credential_writes_no_row(harness_factory, presented):
    harness = harness_factory()
    response = harness.post(headers={CREDENTIAL_HEADER: presented})
    assert_error(response, "CREDENTIAL_INVALID", 401, presented=presented)
    assert harness.ledger.entries() == []


@pytest.mark.parametrize(
    ("body", "code", "status"),
    [
        ({}, "MALFORMED_REQUEST", 400),
        (request_body(symbol="???"), "MALFORMED_REQUEST", 400),
        (request_body(symbol="BTC/XYZ"), "UNSUPPORTED_SYMBOL", 422),
        (request_body(primary_timeframe="1W"), "UNSUPPORTED_TIMEFRAME", 422),
    ],
)
def test_request_refusals_write_no_row(harness_factory, body, code, status):
    harness = harness_factory()
    assert_error(harness.post(body), code, status)
    assert harness.ledger.entries() == []


def test_oversized_http_body_is_refused(harness_factory):
    harness = harness_factory()
    assert_error(harness.post(raw=b" " * 1025), "MALFORMED_REQUEST", 400)
    assert harness.ledger.entries() == []


def test_success_schema_origin_and_build_identity(harness_factory):
    response = harness_factory().post()
    assert response.status_code == 200, response.text
    assert_private(response)
    body = response.json()
    SUCCESS_VALIDATOR.validate(body)
    assert body["evidence_origin"] == "AUTOMATED_RADAR"
    assert body["build_info"] == build_info_payload()


def test_build_info_equals_public_payload(harness_factory):
    response = harness_factory().post()
    assert response.status_code == 200
    assert response.json()["build_info"] == build_info_payload()


def test_replay_is_identical_and_does_not_analyze_twice(harness_factory, monkeypatch):
    harness = harness_factory()
    first = harness.post()
    assert first.status_code == 200

    def unexpected(_request):
        pytest.fail("replay must not run the analyzer")

    monkeypatch.setattr(harness.app.state.automation_service, "_analyzer", unexpected)
    replay = harness.post()
    assert_private(replay)
    assert replay.status_code == 200 and replay.content == first.content
    assert replay.headers["idempotent-replay"] == "true"
    assert len(harness.ledger.entries()) == 1


def test_idempotency_conflict(harness_factory):
    harness = harness_factory()
    assert harness.post().status_code == 200
    assert_error(harness.post(request_body(symbol="ETH")), "IDEMPOTENCY_CONFLICT", 409)
    assert len(harness.ledger.entries()) == 1


def test_preseeded_in_progress_refuses_without_new_row(harness_factory):
    harness = harness_factory(clock=lambda: NOW)
    seed(harness)
    assert_error(harness.post(), "REQUEST_IN_PROGRESS", 409)
    [entry] = harness.ledger.entries()
    assert entry.state == "IN_PROGRESS"


def test_abandoned_request_is_completed_as_deadline_exceeded(harness_factory):
    harness = harness_factory(clock=lambda: NOW)
    seed(harness, now=NOW - timedelta(seconds=91))
    first = harness.post()
    assert_error(first, "DEADLINE_EXCEEDED", 503)
    [entry] = harness.ledger.entries()
    assert entry.state == "COMPLETED" and entry.outcome_code == "DEADLINE_EXCEEDED"
    assert entry.response_body == first.json()
    replay = harness.post()
    assert_error(replay, "DEADLINE_EXCEEDED", 503)
    assert replay.content == first.content and replay.headers["idempotent-replay"] == "true"


@pytest.mark.parametrize(
    ("window", "age", "expected_retry"),
    [
        ("five", 1, 299),
        ("day", 301, 86099),
    ],
)
def test_quota_refusal_is_recorded_but_not_counted(harness_factory, window, age, expected_retry):
    harness = harness_factory(
        env=credential_env(
            **{ENV_QUOTA_PER_5MIN: "1", ENV_QUOTA_PER_DAY: ("1" if window == "day" else "120")}
        ),
        clock=lambda: NOW,
    )
    seed(harness, now=NOW - timedelta(seconds=age), outcome=Outcome("ANALYSIS_FAILED", 503, {}))
    body = request_body(client_request_id=str(uuid4()))
    response = harness.post(body)
    assert_error(response, "QUOTA_EXCEEDED", 429)
    assert response.headers["retry-after"] == str(expected_retry)
    refusal = next(
        e for e in harness.ledger.entries() if e.client_request_id == body["client_request_id"]
    )
    assert refusal.outcome_code == "QUOTA_EXCEEDED" and refusal.state == "COMPLETED"
    replay = harness.post(body)
    assert_error(replay, "QUOTA_EXCEEDED", 429)
    assert replay.content == response.content and replay.headers["idempotent-replay"] == "true"
    counted = seed(harness, body=request_body(client_request_id=str(uuid4())))
    assert counted.counted_day == 1
    assert counted.counted_5min == (1 if window == "five" else 0)


def test_concurrency_refusal_is_recorded_but_not_counted(harness_factory):
    harness = harness_factory(clock=lambda: NOW)
    gate = harness.app.state.automation_service._concurrency
    assert gate.try_acquire()
    try:
        assert_error(harness.post(), "CONCURRENCY_LIMIT", 429)
    finally:
        gate.release()
    [entry] = harness.ledger.entries()
    assert entry.outcome_code == "CONCURRENCY_LIMIT"
    counted = seed(harness, body=request_body(client_request_id=str(uuid4())))
    assert counted.counted_day == counted.counted_5min == 0


def test_spent_deadline_does_not_run_analyzer_and_releases_slot(harness_factory):
    calls = []
    ticks = iter([0.0, 0.0])  # arrival, then the deadline stamp; every later read is past it

    def monotonic():
        return next(ticks, 31.0)

    harness = harness_factory(monotonic=monotonic, analyzer=lambda req: calls.append(req))
    assert_error(harness.post(), "DEADLINE_EXCEEDED", 503)
    assert calls == []
    gate = harness.app.state.automation_service._concurrency
    assert gate.try_acquire()
    gate.release()
    assert harness.ledger.entries()[0].outcome_code == "DEADLINE_EXCEEDED"


def test_future_timeout_keeps_slot_until_worker_finishes(harness_factory):
    release = Event()
    entered = Event()
    ticks = iter([0.0, 0.0])  # arrival and the deadline stamp; then 3.9 s of a 5 s budget spent

    def monotonic():
        return next(ticks, 3.9)

    def blocked(_request):
        entered.set()
        release.wait()
        return {}

    harness = harness_factory(analyzer=blocked, monotonic=monotonic)
    service = harness.app.state.automation_service
    try:
        response = harness.post(request_body(deadline_ms=5000))
        assert_error(response, "DEADLINE_EXCEEDED", 503)
        assert entered.wait(0.2)
        assert not service._concurrency.try_acquire()
        assert_error(
            harness.post(request_body(client_request_id=str(uuid4()))), "CONCURRENCY_LIMIT", 429
        )
    finally:
        release.set()
        service._executor.shutdown(wait=True)
    assert service._concurrency.try_acquire()
    service._concurrency.release()
    [timed_out, busy] = harness.ledger.entries()
    assert timed_out.outcome_code == "DEADLINE_EXCEEDED"
    assert busy.outcome_code == "CONCURRENCY_LIMIT"


@pytest.mark.parametrize(
    ("failure", "code", "status"),
    [
        (
            api_error(503, ApiErrorCode.PROVIDER_DEGRADED, "synthetic provider failure"),
            "UPSTREAM_UNAVAILABLE",
            503,
        ),
        (
            api_error(400, ApiErrorCode.INVALID_SYMBOL, "synthetic invalid symbol"),
            "UNSUPPORTED_SYMBOL",
            422,
        ),
        (RuntimeError("synthetic " + token()), "ANALYSIS_FAILED", 503),
    ],
)
def test_analyzer_errors_are_mapped_recorded_and_redacted(harness_factory, failure, code, status):
    def fail(_request):
        raise failure

    harness = harness_factory(analyzer=fail)
    response = harness.post()
    assert_error(response, code, status)
    [entry] = harness.ledger.entries()
    assert entry.outcome_code == code and entry.response_body == response.json()


def test_invalid_analysis_contract_is_withheld(harness_factory):
    harness = harness_factory(analyzer=lambda _request: {})
    assert_error(harness.post(), "CONTRACT_VIOLATION", 503)
    [entry] = harness.ledger.entries()
    assert entry.outcome_code == "CONTRACT_VIOLATION" and entry.run_id is None


@pytest.mark.parametrize("operation", ["reserve", "complete"])
def test_ledger_failure_withholds_all_evidence(harness_factory, monkeypatch, operation):
    harness = harness_factory()

    def unavailable(**_kwargs):
        raise LedgerUnavailable("synthetic " + token())

    # "complete" is the success record: complete_success.
    name = "reserve" if operation == "reserve" else "complete_success"
    monkeypatch.setattr(harness.ledger, name, unavailable)
    response = harness.post()
    assert_error(response, "LEDGER_UNAVAILABLE", 503)
    assert "evidence_hash" not in response.text and "run_id" not in response.text
    if operation == "reserve":
        assert harness.ledger.entries() == []
    else:
        [entry] = harness.ledger.entries()
        assert entry.state == "IN_PROGRESS" and entry.response_body is None
