from __future__ import annotations

import json

from fastapi.testclient import TestClient

from crypto_probability_engine.api.app import create_app
from crypto_probability_engine.api.auth import dev_limiter, hash_code, session_limiter
from crypto_probability_engine.api.schemas import validate_analysis_response
from crypto_probability_engine.config.settings import Settings


def make_client() -> TestClient:
    session_limiter.reset()
    dev_limiter.reset()
    settings = Settings(
        access_code_hash=hash_code("operator-test-code"),
        dev_mode_code_hash=hash_code("dev-test-code"),
        session_signing_key="test-signing-key",
        dev_mode_enabled=True,
        session_cookie_secure=False,
        data_mode="fixture",
    )
    return TestClient(create_app(settings))


def login(client: TestClient) -> None:
    response = client.post("/v1/auth/login", json={"code": "operator-test-code"})
    assert response.status_code == 200


def dev_login(client: TestClient) -> None:
    response = client.post("/v1/auth/dev", json={"code": "dev-test-code"})
    assert response.status_code == 200


def test_analyze_metrics_only_returns_schema_valid_payload() -> None:
    client = make_client()
    login(client)
    response = client.post("/v1/analyze", json={"symbol": "BTC", "analysis_mode": "METRICS_ONLY"})
    assert response.status_code == 200
    payload = response.json()
    validate_analysis_response(payload)
    assert payload["news_addon_state"]["status"] == "DISABLED_METRICS_ONLY"
    assert payload["frontend_display"]["heat_legend"] == "Signal heat — not risk"
    assert payload["data_quality"]["is_live_data"] is False
    assert payload["data_quality"]["data_source"] == "FIXTURE_DEMO"
    assert payload["frontend_display"]["data_source"] == "FIXTURE_DEMO"


def test_analyze_monthly_timeframe_returns_schema_valid_payload() -> None:
    client = make_client()
    login(client)
    response = client.post(
        "/v1/analyze",
        json={"symbol": "BTC", "analysis_mode": "METRICS_ONLY", "timeframe": "1M"},
    )
    assert response.status_code == 200
    payload = response.json()
    validate_analysis_response(payload)
    assert payload["timeframes"]["primary"] == "1M"
    horizon = payload["probability_state"]["horizons"]["H_primary"]
    assert horizon["p_up_frac"] + horizon["p_down_frac"] + horizon["p_timeout_frac"] == 1.0
    assert payload["epistemic_sufficiency_state"]["min_history_bars"] == 24


def test_news_addon_unavailable_and_metrics_unaffected() -> None:
    client = make_client()
    login(client)
    metrics = client.post("/v1/analyze", json={"symbol": "BTC", "analysis_mode": "METRICS_ONLY"})
    addon = client.post("/v1/analyze", json={"symbol": "BTC", "analysis_mode": "NEWS_ADDON"})
    assert metrics.status_code == 200
    assert addon.status_code == 200
    metrics_payload = metrics.json()
    addon_payload = addon.json()
    assert addon_payload["news_addon_state"]["status"] == "UNAVAILABLE"
    assert metrics_payload["probability_state"] == addon_payload["probability_state"]
    assert metrics_payload["score_stack"] == addon_payload["score_stack"]


def test_batch_partial_failure_is_isolated() -> None:
    client = make_client()
    login(client)
    response = client.post(
        "/v1/analyze_batch",
        json={
            "requests": [
                {"symbol": "BTC", "analysis_mode": "METRICS_ONLY"},
                {"symbol": "NOPE", "analysis_mode": "METRICS_ONLY"},
            ]
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert len(payload["results"]) == 1
    assert len(payload["errors"]) == 1
    assert payload["errors"][0]["detail"]["error"]["code"] == "INVALID_SYMBOL"


def test_detail_lookup_returns_detail_view() -> None:
    client = make_client()
    login(client)
    analyze = client.post("/v1/analyze", json={"symbol": "BTC"})
    run_id = analyze.json()["run_id"]
    detail = client.get(f"/v1/analyze/detail/{run_id}")
    assert detail.status_code == 200
    assert detail.json()["run_id"] == run_id


def test_debug_export_requires_dev_session_and_is_sanitized() -> None:
    client = make_client()
    login(client)
    analyze = client.post("/v1/analyze", json={"symbol": "BTC", "analysis_mode": "NEWS_ADDON"})
    run_id = analyze.json()["run_id"]

    unauthorized = client.get(f"/v1/debug/export/{run_id}")
    assert unauthorized.status_code == 401

    dev_login(client)
    exported = client.get(f"/v1/debug/export/{run_id}")
    assert exported.status_code == 200
    payload_text = json.dumps(exported.json())
    assert "operator-test-code" not in payload_text
    assert "dev-test-code" not in payload_text
    assert "test-signing-key" not in payload_text
    assert "full article" not in payload_text.lower()
    assert exported.json()["debug_pack_version"] == "sprint1"


def test_debug_run_listing_and_lookup_require_dev_session() -> None:
    client = make_client()
    login(client)
    analyze = client.post("/v1/analyze", json={"symbol": "BTC"})
    run_id = analyze.json()["run_id"]

    unauthorized = client.get("/v1/debug/runs")
    assert unauthorized.status_code == 401

    dev_login(client)
    listing = client.get("/v1/debug/runs")
    assert listing.status_code == 200
    assert listing.json()["runs"][0]["run_id"] == run_id

    lookup = client.get(f"/v1/debug/runs/{run_id}")
    assert lookup.status_code == 200
    assert lookup.json()["run_id"] == run_id
