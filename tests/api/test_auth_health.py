from __future__ import annotations

from fastapi.testclient import TestClient

from crypto_probability_engine.api.app import create_app
from crypto_probability_engine.api.auth import (
    DEV_SESSION_COOKIE,
    SESSION_COOKIE,
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
