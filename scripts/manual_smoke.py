"""Offline manual smoke for local app behavior."""

from __future__ import annotations

import re

from fastapi.testclient import TestClient

from crypto_probability_engine.api.app import create_app
from crypto_probability_engine.api.auth import hash_code
from crypto_probability_engine.config.settings import Settings

STALE_FRONTEND_MARKERS = (
    "uncalibrated" + " — see Detail",
    "Open Detail for full probability" + " breakdown",
)


def assert_served_frontend_bundle(client: TestClient) -> str:
    html_response = client.get("/")
    assert html_response.status_code == 200, html_response.text
    match = re.search(r'<script[^>]+src="([^"]*app\.js[^"]*)"', html_response.text)
    assert match, "app.js script tag not found in served HTML"
    app_js_path = match.group(1)
    app_js_response = client.get(app_js_path)
    assert app_js_response.status_code == 200, app_js_response.text
    served_js = app_js_response.text
    for marker in ("prob_up_pct", "prob_down_pct", "prob_timeout_pct"):
        assert marker in served_js, f"served app.js missing {marker}"
    for stale_marker in STALE_FRONTEND_MARKERS:
        assert stale_marker not in served_js, f"served app.js contains stale marker: {stale_marker}"
    return app_js_path


def main() -> int:
    settings = Settings(
        access_code_hash=hash_code("operator-smoke-code"),
        dev_mode_code_hash=hash_code("dev-smoke-code"),
        session_signing_key="smoke-signing-key",
        dev_mode_enabled=True,
        session_cookie_secure=False,
        data_mode="fixture",
    )
    client = TestClient(create_app(settings))
    app_js_path = assert_served_frontend_bundle(client)
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
    print(
        "PASS: offline manual smoke succeeded; "
        f"served frontend bundle verified at {app_js_path}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
