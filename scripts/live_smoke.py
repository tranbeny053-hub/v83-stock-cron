"""Manual live public-provider smoke, gated by UCPE_LIVE_SMOKE_ENABLED=true."""

from __future__ import annotations

import os

from fastapi.testclient import TestClient

from crypto_probability_engine.api.app import create_app
from crypto_probability_engine.api.auth import hash_code
from crypto_probability_engine.api.schemas import validate_analysis_response
from crypto_probability_engine.config.env_flags import parse_bool
from crypto_probability_engine.config.settings import Settings

LIVE_SOURCES = {"BINANCE_PUBLIC", "OKX_PUBLIC", "CROSS_PROVIDER"}


def main() -> int:
    if not parse_bool(os.environ.get("UCPE_LIVE_SMOKE_ENABLED"), default=False):
        print("SKIP: UCPE_LIVE_SMOKE_ENABLED is not true; live smoke was not run.")
        return 0

    settings = Settings(
        access_code_hash=hash_code("operator-live-smoke-code"),
        session_signing_key="live-smoke-signing-key",
        session_cookie_secure=False,
        data_mode="live",
        live_smoke_enabled=True,
    )
    client = TestClient(create_app(settings))
    login = client.post("/v1/auth/login", json={"code": "operator-live-smoke-code"})
    if login.status_code != 200:
        print(f"FAIL: login failed with HTTP {login.status_code}")
        return 1

    metrics_payload = _analyze(client, "METRICS_ONLY")
    addon_payload = _analyze(client, "NEWS_ADDON")
    if metrics_payload is None or addon_payload is None:
        return 1
    if metrics_payload["data_quality"]["data_source"] not in LIVE_SOURCES:
        print("FAIL: METRICS_ONLY did not return a live public data source.")
        return 1
    if addon_payload["data_quality"]["data_source"] not in LIVE_SOURCES:
        print("FAIL: NEWS_ADDON did not return a live public data source.")
        return 1
    if addon_payload["news_addon_state"]["status"] != "UNAVAILABLE":
        print("FAIL: Sprint 2 live smoke expected NEWS_ADDON news state UNAVAILABLE.")
        return 1
    print("PASS: live public-provider smoke returned schema-valid live payloads.")
    return 0


def _analyze(client: TestClient, mode: str) -> dict | None:
    response = client.post("/v1/analyze", json={"symbol": "BTC", "analysis_mode": mode})
    if response.status_code != 200:
        print(f"FAIL: {mode} analyze returned HTTP {response.status_code}: {response.text}")
        return None
    payload = response.json()
    validate_analysis_response(payload)
    if payload["data_quality"]["is_live_data"] is not True:
        print(f"FAIL: {mode} did not report is_live_data=true.")
        return None
    return payload


if __name__ == "__main__":
    raise SystemExit(main())
