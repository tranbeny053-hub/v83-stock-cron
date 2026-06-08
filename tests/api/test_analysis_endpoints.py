from __future__ import annotations

import json
import time
from datetime import UTC, datetime

import httpx
from fastapi.testclient import TestClient

from crypto_probability_engine.api.app import create_app
from crypto_probability_engine.api.auth import dev_limiter, hash_code, session_limiter
from crypto_probability_engine.api.schemas import validate_analysis_response
from crypto_probability_engine.config.settings import Settings
from crypto_probability_engine.persistence.repository import SupabaseRestRepository


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
    assert payload["debug"]["persistence_status"] == "STATELESS"


def test_persistence_failure_does_not_break_analysis() -> None:
    class BrokenRepository:
        def persistence_status(self) -> str:
            return "UNAVAILABLE"

        def save_run(self, summary: dict) -> str:
            raise RuntimeError("simulated persistence outage")

        def save_timeframe_result(self, row: dict) -> str:
            return "OK"

        def save_provider_observation(self, row: dict) -> str:
            return "OK"

    client = make_client()
    client.app.state.persistence_repository = BrokenRepository()
    login(client)
    started = time.perf_counter()
    response = client.post("/v1/analyze", json={"symbol": "BTC", "analysis_mode": "METRICS_ONLY"})
    elapsed = time.perf_counter() - started
    assert response.status_code == 200
    payload = response.json()
    validate_analysis_response(payload)
    assert payload["debug"]["persistence_status"] == "UNAVAILABLE"
    assert "simulated persistence outage" not in response.text
    assert elapsed < 0.5


def test_supabase_rest_unavailable_does_not_break_analysis() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"message": "database unavailable"})

    repo = SupabaseRestRepository(
        "https://project.example.supabase.co",
        "test-service-role-key",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    assert repo.save_run({"run_id": "probe"}) == "UNAVAILABLE"

    client = make_client()
    client.app.state.persistence_repository = repo
    login(client)
    response = client.post("/v1/analyze", json={"symbol": "BTC", "analysis_mode": "METRICS_ONLY"})

    assert response.status_code == 200
    payload = response.json()
    validate_analysis_response(payload)
    assert payload["debug"]["persistence_status"] == "UNAVAILABLE"
    assert "test-service-role-key" not in response.text
    assert "project.example" not in response.text


def test_slow_persistence_is_scheduled_without_blocking_response() -> None:
    class SlowRepository:
        def persistence_status(self) -> str:
            return "OK"

        def save_run(self, summary: dict) -> str:
            time.sleep(0.75)
            return "UNAVAILABLE"

        def save_timeframe_result(self, row: dict) -> str:
            return "UNAVAILABLE"

        def save_provider_observation(self, row: dict) -> str:
            return "UNAVAILABLE"

    client = make_client()
    client.app.state.persistence_repository = SlowRepository()
    login(client)
    started = time.perf_counter()
    response = client.post("/v1/analyze", json={"symbol": "BTC", "analysis_mode": "METRICS_ONLY"})
    elapsed = time.perf_counter() - started
    assert response.status_code == 200
    validate_analysis_response(response.json())
    assert elapsed < 0.5


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


def test_advisory_news_fixture_does_not_change_score_or_disposition(monkeypatch) -> None:
    from crypto_probability_engine.news.contract import build_news_blocks as real_build_news_blocks
    from crypto_probability_engine.news.models import make_news_item

    item = make_news_item(
        provider="gdelt",
        source_name="Reuters",
        domain="reuters.com",
        title="Bitcoin ETF flows rise as macro liquidity improves",
        snippet="Metadata-only advisory news fixture.",
        url="https://example.com/btc-advisory",
        published_at="2026-06-08T10:00:00Z",
        fetched_at=datetime(2026, 6, 8, 12, 0, tzinfo=UTC),
    )

    class FixtureSource:
        name = "fixture_news"

        def is_configured(self) -> bool:
            return True

        def fetch_items(self, symbol: str):
            return (item,)

        def fetch_macro_observations(self):
            return ()

    def fixture_news_blocks(*, analysis_mode, symbol, sources=None, settings=None):
        if analysis_mode.value == "NEWS_ADDON":
            return real_build_news_blocks(
                analysis_mode=analysis_mode,
                symbol=symbol,
                sources=[FixtureSource()],
            )
        return real_build_news_blocks(
            analysis_mode=analysis_mode,
            symbol=symbol,
            sources=sources,
            settings=settings,
        )

    monkeypatch.setattr(
        "crypto_probability_engine.api.analysis_service.build_news_blocks",
        fixture_news_blocks,
    )
    client = make_client()
    login(client)

    metrics = client.post("/v1/analyze", json={"symbol": "BTC", "analysis_mode": "METRICS_ONLY"})
    addon = client.post("/v1/analyze", json={"symbol": "BTC", "analysis_mode": "NEWS_ADDON"})

    assert metrics.status_code == 200
    assert addon.status_code == 200
    metrics_payload = metrics.json()
    addon_payload = addon.json()
    assert addon_payload["news_addon_state"]["status"] in {"OK", "DEGRADED"}
    assert addon_payload["news_addon_state"]["influence_mode"] == "ADVISORY_DISPLAY_ONLY"
    assert addon_payload["news_addon_state"]["news_influence_frac"] == 0.0
    assert metrics_payload["probability_state"] == addon_payload["probability_state"]
    assert metrics_payload["score_stack"] == addon_payload["score_stack"]
    assert metrics_payload["gate_result"] == addon_payload["gate_result"]


def test_batch_partial_failure_is_isolated() -> None:
    client = make_client()
    login(client)
    response = client.post(
        "/v1/analyze_batch",
        json={
            "requests": [
                {"symbol": "BTC", "analysis_mode": "METRICS_ONLY"},
                    {"symbol": "$NOPE", "analysis_mode": "METRICS_ONLY"},
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
