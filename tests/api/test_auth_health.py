from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from time import perf_counter

import pytest
from fastapi.testclient import TestClient

from crypto_probability_engine.api import auth
from crypto_probability_engine.api.app import create_app
from crypto_probability_engine.api.auth import (
    DEV_SESSION_COOKIE,
    MAX_ACCESS_CODE_LENGTH,
    SESSION_COOKIE,
    AttemptLimiter,
    dev_limiter,
    hash_code,
    session_limiter,
)
from crypto_probability_engine.config.settings import Settings


def make_client(*, dev_enabled: bool = True) -> TestClient:
    session_limiter.reset()
    dev_limiter.reset()
    settings = Settings(
        access_code_hash=hash_code("operator-test-code"),
        dev_mode_code_hash=hash_code("dev-test-code"),
        session_signing_key="test-signing-key",
        dev_mode_enabled=dev_enabled,
        session_cookie_secure=False,
    )
    return TestClient(create_app(settings))


def test_healthcheck_is_public() -> None:
    client = make_client()
    response = client.get("/healthcheck")
    assert response.status_code == 200
    assert response.json()["status"] == "OK"


def test_system_status_requires_session() -> None:
    client = make_client()
    response = client.get("/v1/system_status")
    assert response.status_code == 401
    assert response.json()["detail"]["error"]["code"] == "UNAUTHORIZED"


def test_login_sets_httponly_session_cookie() -> None:
    client = make_client()
    response = client.post("/v1/auth/login", json={"code": "operator-test-code"})
    assert response.status_code == 200
    cookie = response.cookies.get(SESSION_COOKIE)
    assert cookie
    set_cookie = response.headers["set-cookie"].lower()
    assert "httponly" in set_cookie
    assert "samesite=lax" in set_cookie


def test_system_status_with_session() -> None:
    client = make_client()
    login_response = client.post("/v1/auth/login", json={"code": "operator-test-code"})
    response = client.get(
        "/v1/system_status",
        cookies={SESSION_COOKIE: login_response.cookies[SESSION_COOKIE]},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["system"]["store_status"] == "STATELESS"
    assert payload["system"]["persistence_status"] == "STATELESS"
    assert payload["system"]["repository_type"] == "IN_MEMORY"
    assert payload["system"]["circuit_state"] == "STATELESS"
    assert payload["system"]["dev_mode"] == {"enabled": True, "configured": True}
    assert "test-signing-key" not in response.text


def test_system_status_reports_supabase_rest_without_secret_values() -> None:
    session_limiter.reset()
    dev_limiter.reset()
    settings = Settings(
        access_code_hash=hash_code("operator-test-code"),
        session_signing_key="test-signing-key",
        session_cookie_secure=False,
        **{
            "supabase_url": "https://project.example.supabase.co",
            "supabase_service_role_key": "test-service-role-key",
            "supabase_db_url": "postgresql://example.invalid/db",
        },
    )
    client = TestClient(create_app(settings))
    login_response = client.post("/v1/auth/login", json={"code": "operator-test-code"})

    response = client.get(
        "/v1/system_status",
        cookies={SESSION_COOKIE: login_response.cookies[SESSION_COOKIE]},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["system"]["repository_type"] == "SUPABASE_REST"
    assert payload["system"]["persistence_status"] == "OK"
    assert "test-service-role-key" not in response.text
    assert "project.example" not in response.text
    assert "postgresql://" not in response.text


def test_bad_login_does_not_set_session_cookie() -> None:
    client = make_client()
    response = client.post("/v1/auth/login", json={"code": "bad-code"})
    assert response.status_code == 401
    assert SESSION_COOKIE not in response.cookies


def test_rate_limit_after_repeated_failures() -> None:
    client = make_client()
    for _ in range(5):
        assert client.post("/v1/auth/login", json={"code": "bad-code"}).status_code == 401
    response = client.post("/v1/auth/login", json={"code": "bad-code"})
    assert response.status_code == 429


def test_dev_mode_requires_flag() -> None:
    client = make_client(dev_enabled=False)
    response = client.post("/v1/auth/dev", json={"code": "dev-test-code"})
    assert response.status_code == 403


def test_dev_mode_sets_separate_cookie() -> None:
    client = make_client(dev_enabled=True)
    response = client.post("/v1/auth/dev", json={"code": "dev-test-code"})
    assert response.status_code == 200
    assert response.cookies.get(DEV_SESSION_COOKIE)


def test_oversized_login_code_is_rejected_before_hashing(monkeypatch) -> None:
    client = make_client()
    submitted = "oversized-secret-" * MAX_ACCESS_CODE_LENGTH

    def fail_if_called(*args, **kwargs):
        raise AssertionError("PBKDF2 must not run for an oversized code")

    monkeypatch.setattr(auth, "pbkdf2_hash_code", fail_if_called)
    response = client.post("/v1/auth/login", json={"code": submitted})

    assert response.status_code == 422
    assert submitted not in response.text
    assert str(len(submitted)) not in response.text


@pytest.mark.parametrize(
    ("submitted", "submitted_text"),
    [
        pytest.param({"value": "operator-access-code"}, "operator-access-code", id="object"),
        pytest.param(["operator-access-code"], "operator-access-code", id="list"),
        pytest.param(8675309, "8675309", id="integer"),
        pytest.param(None, "null", id="null"),
    ],
)
def test_malformed_login_code_is_not_echoed(
    submitted: object, submitted_text: str
) -> None:
    client = make_client()

    response = client.post("/v1/auth/login", json={"code": submitted})

    assert response.status_code == 422
    assert submitted_text not in response.text


@pytest.mark.parametrize("path", ["/v1/auth/login", "/v1/auth/dev"])
@pytest.mark.parametrize(
    ("submitted", "submitted_text"),
    [
        pytest.param("top-level-access-value", "top-level-access-value", id="string"),
        pytest.param(8675309, "8675309", id="number"),
        pytest.param(
            ["top-level-list-access-value"],
            "top-level-list-access-value",
            id="list",
        ),
    ],
)
def test_top_level_auth_body_is_not_echoed(
    path: str, submitted: object, submitted_text: str
) -> None:
    client = make_client()

    response = client.post(path, json=submitted)

    assert response.status_code == 422
    assert submitted_text not in response.text


def test_non_auth_validation_error_still_echoes_input() -> None:
    client = make_client()
    login_response = client.post("/v1/auth/login", json={"code": "operator-test-code"})
    submitted = "non-auth-validation-input"

    response = client.post(
        "/v1/analyze",
        json=submitted,
        cookies={SESSION_COOKIE: login_response.cookies[SESSION_COOKIE]},
    )

    assert response.status_code == 422
    assert submitted in response.text


def test_login_code_at_maximum_length_still_works() -> None:
    code = "x" * MAX_ACCESS_CODE_LENGTH
    settings = Settings(
        access_code_hash=hash_code(code),
        session_signing_key="test-signing-key",
        session_cookie_secure=False,
    )
    client = TestClient(create_app(settings))

    response = client.post("/v1/auth/login", json={"code": code})

    assert response.status_code == 200
    assert response.cookies.get(SESSION_COOKIE)


def test_attempt_limiter_atomically_caps_interleaved_failures() -> None:
    limiter = AttemptLimiter(max_attempts=5)

    with ThreadPoolExecutor(max_workers=20) as executor:
        allowed = list(executor.map(limiter.check_and_record, ["host"] * 40))

    assert sum(reservation is not None for reservation in allowed) == limiter.max_attempts
    assert len(limiter.attempts["host"]) == limiter.max_attempts


def test_attempt_limiter_caps_distinct_keys() -> None:
    limiter = AttemptLimiter(max_keys=8)

    for index in range(100):
        assert limiter.record_failure(f"host-{index}")

    assert len(limiter.attempts) == limiter.max_keys


def test_attempt_limiter_cost_does_not_scale_with_distinct_keys() -> None:
    samples = 1_000

    def mean_attempt_cost(limiter: AttemptLimiter, key: str) -> float:
        started = perf_counter()
        for _ in range(samples):
            assert limiter.check_and_record(key) is not None
        return (perf_counter() - started) / samples

    near_empty = AttemptLimiter(max_attempts=samples + 1)
    empty_cost = mean_attempt_cost(near_empty, "probe")

    full = AttemptLimiter(max_attempts=samples + 1)
    for index in range(full.max_keys):
        assert full.check_and_record(f"host-{index}") is not None
    full_cost = mean_attempt_cost(full, "probe")

    # 25x is intentionally generous for noisy CI, while catching an O(n) sweep per call.
    assert full_cost < empty_cost * 25


def test_attempt_limiter_eventually_sweeps_expired_keys(monkeypatch) -> None:
    now = 100.0
    monkeypatch.setattr(auth.time, "time", lambda: now)
    limiter = AttemptLimiter(window_seconds=10)
    assert limiter.check_and_record("expired-host") is not None

    now = 111.0
    assert limiter.check_and_record("current-host") is not None

    assert "expired-host" not in limiter.attempts
    assert "current-host" in limiter.attempts


def test_attempt_limiter_discards_the_exact_interleaved_reservation(monkeypatch) -> None:
    timestamps = iter((100.0, 101.0))
    monkeypatch.setattr(auth.time, "time", lambda: next(timestamps))
    limiter = AttemptLimiter()
    first = limiter.check_and_record("host")
    second = limiter.check_and_record("host")
    assert first is not None
    assert second is not None

    limiter.discard_reserved_attempt("host", first)

    assert limiter.attempts["host"] == [second]
