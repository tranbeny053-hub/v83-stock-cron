"""OBS-2 (plan §9.4, §10): per-stage analysis timings, in telemetry only, never in the payload."""

from __future__ import annotations

import json

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from crypto_probability_engine.api.analysis_service import analyze_request
from crypto_probability_engine.api.app import create_app
from crypto_probability_engine.api.auth import dev_limiter, hash_code, session_limiter
from crypto_probability_engine.api.schemas import AnalysisRequest
from crypto_probability_engine.config.settings import Settings
from crypto_probability_engine.persistence.run_store import InMemoryRunStore
from crypto_probability_engine.telemetry.events import (
    CURRENT_STAGE_MS,
    EVENTS_SINK,
    STAGE_FIELDS,
    sanitize,
)

STAGES = ("provider_ms", "quant_ms", "gate_ms", "news_ms", "present_ms")


def _client() -> TestClient:
    session_limiter.reset()
    dev_limiter.reset()
    settings = Settings(
        access_code_hash=hash_code("operator-test-code"),
        session_signing_key="test-signing-key",
        session_cookie_secure=False,
        data_mode="fixture",
    )
    client = TestClient(create_app(settings))
    assert client.post("/v1/auth/login", json={"code": "operator-test-code"}).status_code == 200
    return client


def _analysis_events() -> list[dict]:
    return [event for event in EVENTS_SINK.events if event["event"] == "analysis_completed"]


def test_every_analysis_event_carries_its_stage_timings() -> None:
    client = _client()
    EVENTS_SINK.events.clear()
    response = client.post("/v1/analyze", json={"symbol": "BTC/USDT", "timeframe": "4H"})
    assert response.status_code == 200, response.text
    (event,) = _analysis_events()
    assert set(STAGE_FIELDS) == {*STAGES, "total_ms"}
    for field in STAGE_FIELDS:
        assert isinstance(event[field], float) and event[field] >= 0.0, (field, event.get(field))
    # Rounded to 3 decimals each, so allow the rounding of six values.
    assert event["total_ms"] + 0.01 >= sum(event[stage] for stage in STAGES)


def test_the_timings_never_enter_the_analysis_payload() -> None:
    client = _client()
    response = client.post("/v1/analyze", json={"symbol": "BTC/USDT", "timeframe": "4H"})
    text = json.dumps(response.json())
    for field in STAGE_FIELDS:
        assert field not in text, field


def test_each_batch_item_gets_its_own_timings() -> None:
    client = _client()
    EVENTS_SINK.events.clear()
    body = {"requests": [{"symbol": "BTC/USDT", "timeframe": "4H"},
                         {"symbol": "ETH/USDT", "timeframe": "1H"}]}
    response = client.post("/v1/analyze_batch", json=body)
    assert response.status_code == 200, response.text
    events = _analysis_events()
    pairs = [(event["symbol"], event["timeframe"]) for event in events]
    assert pairs == [("BTC/USDT", "4H"), ("ETH/USDT", "1H")]
    assert all(set(STAGE_FIELDS) <= set(event) for event in events)


def test_a_failed_analysis_leaves_no_stale_timings() -> None:
    # In this thread's own context, so the reset is observable here.
    stale = CURRENT_STAGE_MS.set({"total_ms": 123.0})
    try:
        with pytest.raises(HTTPException):
            analyze_request(AnalysisRequest(symbol="BTC/USDT", timeframe="7H"),
                            settings=Settings(data_mode="fixture"),
                            run_store=InMemoryRunStore(limit=10))
        assert CURRENT_STAGE_MS.get() is None, "the analysis resets them before anything else"
        analyze_request(AnalysisRequest(symbol="BTC/USDT", timeframe="4H"),
                        settings=Settings(data_mode="fixture"),
                        run_store=InMemoryRunStore(limit=10))
        assert set(CURRENT_STAGE_MS.get() or {}) == set(STAGE_FIELDS)
    finally:
        CURRENT_STAGE_MS.reset(stale)


def test_sanitize_keeps_the_stage_fields_and_drops_containers() -> None:
    fields = {name: 1.23456 for name in STAGE_FIELDS} | {"provider_ms_detail": {"x": 1}}
    clean = sanitize("analysis_completed", fields)
    assert clean is not None
    assert {name: clean[name] for name in STAGE_FIELDS} == {name: 1.235 for name in STAGE_FIELDS}
    assert "provider_ms_detail" not in clean
