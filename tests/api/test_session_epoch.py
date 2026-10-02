"""SEC-1 (governing plan §13): session issue time, token id and the operator's auth epoch."""

from __future__ import annotations

import json
import time

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from crypto_probability_engine.api import auth
from crypto_probability_engine.api.app import create_app
from crypto_probability_engine.api.auth import (
    AUTH_EPOCH_ENV,
    SESSION_COOKIE,
    create_session_token,
    current_auth_epoch,
    dev_limiter,
    hash_code,
    session_limiter,
    verify_session_token,
)
from crypto_probability_engine.config.settings import Settings

KEY = "test-signing-key"
SETTINGS = Settings(
    access_code_hash=hash_code("operator-test-code"),
    session_signing_key=KEY,
    session_cookie_secure=False,
)


@pytest.fixture
def epoch(monkeypatch: pytest.MonkeyPatch):
    """Sets (or with None, clears) the operator's epoch variable for one test."""

    def set_epoch(value: str | None) -> None:
        if value is None:
            monkeypatch.delenv(AUTH_EPOCH_ENV, raising=False)
        else:
            monkeypatch.setenv(AUTH_EPOCH_ENV, value)

    set_epoch(None)
    return set_epoch


def payload_of(token: str) -> dict:
    return json.loads(auth._b64_decode(token.split(".", 1)[0]))


def legacy_token(**extra: object) -> str:
    """A session as issued before SEC-1: no iat, no jti, no epoch."""

    body = {"sub": "operator", "dev": False, "exp": int(time.time()) + 600,
            "prediction_origin": "USER_REQUESTED", **extra}
    encoded = auth._b64_encode(json.dumps(body, separators=(",", ":")).encode())
    return f"{encoded}.{auth._sign(encoded, KEY)}"


def refusal(token: str) -> str:
    with pytest.raises(HTTPException) as caught:
        verify_session_token(token, SETTINGS)
    assert caught.value.status_code == 401
    return caught.value.detail["error"]["message"]


def test_a_new_session_carries_its_issue_time_a_fresh_id_and_the_epoch(epoch) -> None:
    epoch("2026-10-02-a")
    before = int(time.time())
    first = payload_of(create_session_token("operator", SETTINGS))
    second = payload_of(create_session_token("operator", SETTINGS))
    assert before <= first["iat"] <= int(time.time())
    assert first["exp"] - first["iat"] == SETTINGS.session_ttl_seconds
    assert first["epoch"] == "2026-10-02-a"
    assert isinstance(first["jti"], str) and len(first["jti"]) >= 16
    assert first["jti"] != second["jti"]


def test_without_an_epoch_every_unexpired_session_verifies_including_pre_sec1_ones(epoch) -> None:
    assert verify_session_token(legacy_token(), SETTINGS)["sub"] == "operator"
    fresh = create_session_token("operator", SETTINGS)
    assert verify_session_token(fresh, SETTINGS)["sub"] == "operator"


def test_once_the_operator_sets_an_epoch_every_other_session_is_revoked(epoch) -> None:
    epoch("e1")
    old = create_session_token("operator", SETTINGS)
    epoch(None)
    unepoched = create_session_token("operator", SETTINGS)
    epoch("e2")
    assert refusal(old) == "Session revoked."
    assert refusal(unepoched) == "Session revoked."
    assert refusal(legacy_token()) == "Session revoked."
    fresh = create_session_token("operator", SETTINGS)
    assert verify_session_token(fresh, SETTINGS)["epoch"] == "e2"


def test_expiry_and_signature_are_still_checked_first(epoch) -> None:
    epoch("e2")
    assert refusal(legacy_token(exp=1, epoch="e2")) == "Session expired."
    token = legacy_token(epoch="e2")
    forged = token[:-1] + ("1" if token[-1] == "0" else "0")  # always a different signature
    assert refusal(forged) == "Valid session is required."


def test_revocation_reaches_the_routes(epoch) -> None:
    session_limiter.reset()
    dev_limiter.reset()
    client = TestClient(create_app(SETTINGS))
    epoch("e1")
    assert client.post("/v1/auth/login", json={"code": "operator-test-code"}).status_code == 200
    assert client.get("/v1/system_status").status_code == 200
    epoch("e2")  # the operator changes the variable (on the Space, then restarts it)
    response = client.get("/v1/system_status")
    assert response.status_code == 401
    assert response.json()["detail"]["error"]["message"] == "Session revoked."
    assert client.cookies.get(SESSION_COOKIE)


def test_the_epoch_is_read_from_the_environment_and_stripped(epoch) -> None:
    assert current_auth_epoch() == ""
    epoch("  2026-10-02-a  ")
    assert current_auth_epoch() == "2026-10-02-a"
