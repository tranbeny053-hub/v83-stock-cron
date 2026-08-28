from __future__ import annotations

import pytest
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
from crypto_probability_engine.persistence.repository import InMemoryPersistenceRepository


def make_client(
    *,
    session_cookie_secure: bool = False,
    session_ttl_seconds: int = 3600,
) -> TestClient:
    session_limiter.reset()
    dev_limiter.reset()
    settings = Settings(
        access_code_hash=hash_code("operator-test-code"),
        dev_mode_code_hash=hash_code("dev-test-code"),
        session_signing_key="test-signing-key",
        dev_mode_enabled=True,
        session_cookie_secure=session_cookie_secure,
        session_ttl_seconds=session_ttl_seconds,
    )
    app = create_app(settings)
    base_url = "https://testserver" if session_cookie_secure else "http://testserver"
    return TestClient(app, base_url=base_url)


def login(client: TestClient) -> None:
    response = client.post("/v1/auth/login", json={"code": "operator-test-code"})
    assert response.status_code == 200


def test_logout_requires_session() -> None:
    assert make_client().post("/v1/auth/logout").status_code == 401


def test_logout_get_does_not_end_session_or_clear_session_cookies() -> None:
    client = make_client()
    login(client)

    response = client.get("/v1/auth/logout")

    # GET is 404 because unmatched requests reach the StaticFiles mount; no middleware is needed.
    assert not 200 <= response.status_code < 300
    assert client.get("/v1/system_status").status_code == 200
    clearing_session_cookies = [
        cookie
        for cookie in response.headers.get_list("set-cookie")
        if cookie.startswith((f"{SESSION_COOKIE}=", f"{DEV_SESSION_COOKIE}="))
        and (
            "max-age=0" in cookie.lower()
            or "expires=thu, 01 jan 1970" in cookie.lower()
        )
    ]
    assert clearing_session_cookies == []


@pytest.mark.parametrize("method", ["PUT", "DELETE", "PATCH"])
def test_logout_router_rejects_non_post_methods(method: str) -> None:
    client = make_client()
    login(client)

    assert client.request(method, "/v1/auth/logout").status_code == 405


def test_logout_deletes_both_session_cookies_with_matching_attributes() -> None:
    client = make_client()
    login(client)

    response = client.post("/v1/auth/logout")

    assert response.status_code == 200
    cookies = response.headers.get_list("set-cookie")
    assert len(cookies) == 2
    for name in (SESSION_COOKIE, DEV_SESSION_COOKIE):
        cookie = next(item for item in cookies if item.startswith(f"{name}="))
        lower = cookie.lower()
        assert "max-age=0" in lower or "expires=thu, 01 jan 1970" in lower
        assert "path=/" in lower
        assert "httponly" in lower
        assert "samesite=lax" in lower


def test_logout_removes_operator_session_from_client() -> None:
    client = make_client()
    login(client)

    assert client.post("/v1/auth/logout").status_code == 200
    assert client.get("/v1/system_status").status_code == 401


def test_logout_removes_elevated_dev_session_from_client() -> None:
    client = make_client()
    login(client)
    assert client.post("/v1/auth/dev", json={"code": "dev-test-code"}).status_code == 200

    assert client.post("/v1/auth/logout").status_code == 200
    assert client.get("/v1/auth/dev").status_code == 401


@pytest.mark.parametrize("secure", [False, True])
def test_logout_deletion_cookies_follow_secure_setting(secure: bool) -> None:
    client = make_client(session_cookie_secure=secure)
    login(client)

    cookies = client.post("/v1/auth/logout").headers.get_list("set-cookie")

    assert len(cookies) == 2
    assert all(("; secure" in cookie.lower()) is secure for cookie in cookies)


@pytest.mark.parametrize("ttl", [900, 7200])
def test_login_cookie_uses_configured_session_ttl(ttl: int) -> None:
    response = make_client(session_ttl_seconds=ttl).post(
        "/v1/auth/login",
        json={"code": "operator-test-code"},
    )

    assert response.status_code == 200
    assert f"max-age={ttl}" in response.headers["set-cookie"].lower()


def test_logout_has_no_persistence_side_effect() -> None:
    client = make_client()
    repository = client.app.state.persistence_repository
    assert isinstance(repository, InMemoryPersistenceRepository)

    login(client)
    assert client.post("/v1/auth/logout").status_code == 200

    assert repository.recent_runs(limit=10) == []
    assert repository._predictions == {}
