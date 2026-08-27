from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time

import pytest
from fastapi.testclient import TestClient

from crypto_probability_engine.api import app as app_module
from crypto_probability_engine.api.app import create_app
from crypto_probability_engine.api.auth import (
    DEV_SESSION_COOKIE,
    SESSION_COOKIE,
    dev_limiter,
    hash_code,
    session_limiter,
)
from crypto_probability_engine.config.settings import Settings

ACCESS_CODE = "operator-origin-code"
SMOKE_CODE = "controlled-smoke-code"
DEV_CODE = "origin-dev-code"
SIGNING_KEY = "origin-test-signing-key"


def _settings(*, smoke_configured: bool = True, dev_enabled: bool = True) -> Settings:
    return Settings(
        access_code_hash=hash_code(ACCESS_CODE),
        controlled_smoke_code_hash=hash_code(SMOKE_CODE) if smoke_configured else None,
        dev_mode_code_hash=hash_code(DEV_CODE),
        session_signing_key=SIGNING_KEY,
        dev_mode_enabled=dev_enabled,
        session_cookie_secure=False,
        data_mode="fixture",
    )


def _client(*, smoke_configured: bool = True, dev_enabled: bool = True) -> TestClient:
    session_limiter.reset()
    dev_limiter.reset()
    return TestClient(
        create_app(
            _settings(smoke_configured=smoke_configured, dev_enabled=dev_enabled)
        )
    )


def _signed_token(payload: dict) -> str:
    body = base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":")).encode()
    ).decode().rstrip("=")
    signature = hmac.new(SIGNING_KEY.encode(), body.encode(), hashlib.sha256).hexdigest()
    return f"{body}.{signature}"


def _login(client: TestClient, code: str) -> str:
    response = client.post("/v1/auth/login", json={"code": code})
    assert response.status_code == 200
    return response.cookies[SESSION_COOKIE]


def _record_analysis_origins(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    origins: list[str] = []

    def fake_analyze_request(_body, **kwargs):
        origins.append(kwargs["prediction_origin"])
        return {"run_id": f"run-{len(origins)}"}

    monkeypatch.setattr(app_module, "analyze_request", fake_analyze_request)
    monkeypatch.setattr(
        app_module,
        "schedule_best_effort_persist",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(app_module, "schedule_skill_evidence_refresh", lambda *_args: None)
    return origins


def test_normal_session_origin_reaches_analysis(monkeypatch: pytest.MonkeyPatch) -> None:
    origins = _record_analysis_origins(monkeypatch)
    client = _client()
    _login(client, ACCESS_CODE)

    response = client.post("/v1/analyze", json={"symbol": "BTC"})

    assert response.status_code == 200
    assert origins == ["USER_REQUESTED"]


@pytest.mark.parametrize(
    ("path", "body"),
    [
        ("/v1/analyze", {"symbol": "BTC"}),
        ("/v1/analyze_batch", {"requests": [{"symbol": "BTC"}]}),
    ],
)
def test_smoke_session_origin_reaches_all_analysis_routes(
    monkeypatch: pytest.MonkeyPatch,
    path: str,
    body: dict,
) -> None:
    origins = _record_analysis_origins(monkeypatch)
    client = _client()
    _login(client, SMOKE_CODE)

    response = client.post(path, json=body)

    assert response.status_code == 200
    assert origins == ["CONTROLLED_SMOKE"]


def test_unconfigured_smoke_code_is_rejected_like_any_wrong_code() -> None:
    client = _client(smoke_configured=False)

    smoke_response = client.post("/v1/auth/login", json={"code": SMOKE_CODE})
    wrong_response = client.post("/v1/auth/login", json={"code": "unrelated-wrong-code"})

    assert smoke_response.status_code == wrong_response.status_code == 401
    assert smoke_response.json() == wrong_response.json()
    assert smoke_response.json()["detail"]["error"]["message"] == "Invalid access code."


def test_wrong_code_error_is_identical_with_or_without_smoke_configuration() -> None:
    configured = _client().post("/v1/auth/login", json={"code": "wrong-code"})
    unconfigured = _client(smoke_configured=False).post(
        "/v1/auth/login", json={"code": "wrong-code"}
    )

    assert configured.status_code == unconfigured.status_code == 401
    assert configured.json() == unconfigured.json()


def test_tampered_session_cookie_is_rejected() -> None:
    client = _client()
    token = _login(client, SMOKE_CODE)

    response = client.get(
        "/v1/system_status",
        cookies={SESSION_COOKIE: f"{token}tampered"},
    )

    assert response.status_code == 401


def test_validly_signed_unsupported_origin_fails_closed() -> None:
    client = _client()
    token = _signed_token(
        {
            "sub": "operator",
            "dev": False,
            "exp": int(time.time()) + 3600,
            "prediction_origin": "UNSUPPORTED_ORIGIN",
        }
    )

    response = client.get("/v1/system_status", cookies={SESSION_COOKIE: token})

    assert response.status_code == 401
    assert response.json()["detail"]["error"]["message"] == "Valid session is required."


def test_legacy_session_without_origin_defaults_to_user_requested(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    origins = _record_analysis_origins(monkeypatch)
    client = _client()
    token = _signed_token(
        {"sub": "operator", "dev": False, "exp": int(time.time()) + 3600}
    )

    response = client.post(
        "/v1/analyze",
        json={"symbol": "BTC"},
        cookies={SESSION_COOKIE: token},
    )

    assert response.status_code == 200
    assert origins == ["USER_REQUESTED"]


def test_smoke_session_does_not_grant_dev_mode() -> None:
    client = _client()
    smoke_token = _login(client, SMOKE_CODE)

    response = client.get(
        "/v1/auth/dev",
        cookies={DEV_SESSION_COOKIE: smoke_token},
    )

    assert response.status_code == 401
    assert response.json()["detail"]["error"]["message"] == (
        "Dev Mode re-auth is required."
    )


def test_rate_limiter_bounds_smoke_login_path() -> None:
    client = _client()
    for index in range(5):
        response = client.post("/v1/auth/login", json={"code": f"wrong-smoke-{index}"})
        assert response.status_code == 401

    response = client.post("/v1/auth/login", json={"code": SMOKE_CODE})

    assert response.status_code == 429


def test_smoke_secrets_and_raw_payload_are_absent_from_response_and_debug_export() -> None:
    client = _client()
    token = _login(client, SMOKE_CODE)
    token_body = token.split(".", maxsplit=1)[0]

    status_response = client.get("/v1/system_status")
    assert status_response.status_code == 200

    analyze_response = client.post("/v1/analyze", json={"symbol": "BTC"})
    assert analyze_response.status_code == 200
    run_id = analyze_response.json()["run_id"]

    dev_response = client.post("/v1/auth/dev", json={"code": DEV_CODE})
    assert dev_response.status_code == 200
    export_response = client.get(f"/v1/debug/export/{run_id}")
    assert export_response.status_code == 200

    forbidden = (
        SMOKE_CODE,
        _settings().controlled_smoke_code_hash,
        SIGNING_KEY,
        token,
        token_body,
    )
    for response in (status_response, analyze_response, export_response):
        assert all(secret not in response.text for secret in forbidden)


def test_settings_reads_controlled_smoke_hash_without_repr_exposure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    smoke_hash = hash_code(SMOKE_CODE)
    monkeypatch.setenv("CONTROLLED_SMOKE_CODE_HASH", smoke_hash)

    settings = Settings.from_env()

    assert settings.controlled_smoke_code_hash == smoke_hash
    assert smoke_hash not in repr(settings)
