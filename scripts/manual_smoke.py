"""Offline manual smoke for local app behavior."""

from __future__ import annotations

from fastapi.testclient import TestClient

from crypto_probability_engine.api.app import create_app
from crypto_probability_engine.api.auth import hash_code
from crypto_probability_engine.config.settings import Settings


def main() -> int:
    settings = Settings(
        access_code_hash=hash_code("operator-smoke-code"),
        dev_mode_code_hash=hash_code("dev-smoke-code"),
        session_signing_key="smoke-signing-key",
        dev_mode_enabled=True,
        session_cookie_secure=False,
    )
    client = TestClient(create_app(settings))
    health = client.get("/healthcheck")
    assert health.status_code == 200, health.text
    login = client.post("/v1/auth/login", json={"code": "operator-smoke-code"})
    assert login.status_code == 200, login.text
    metrics = client.post("/v1/analyze", json={"symbol": "BTC", "analysis_mode": "METRICS_ONLY"})
    addon = client.post("/v1/analyze", json={"symbol": "BTC", "analysis_mode": "NEWS_ADDON"})
    assert metrics.status_code == 200, metrics.text
    assert addon.status_code == 200, addon.text
    metrics_payload = metrics.json()
    addon_payload = addon.json()
    assert addon_payload["news_addon_state"]["status"] == "UNAVAILABLE"
    assert metrics_payload["probability_state"] == addon_payload["probability_state"]
    dev = client.post("/v1/auth/dev", json={"code": "dev-smoke-code"})
    assert dev.status_code == 200, dev.text
    export = client.get(f"/v1/debug/export/{addon_payload['run_id']}")
    assert export.status_code == 200, export.text
    print("PASS: offline manual smoke succeeded.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
