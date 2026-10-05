"""Passive provider measurement (plan §9.1, §9.4; owner ruling DP-B as narrowed, 2026-10-05).

Each analysis_completed event carries its own provider exchange counts and its slowest exchange, in
telemetry only: never in the payload, and reset at the start of every analysis, so no count outlives
the analysis it belongs to.
"""

from __future__ import annotations

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
    CURRENT_PROVIDER_STATS,
    EVENTS_SINK,
    FIELDS,
    PROVIDER_FIELDS,
    new_provider_stats,
    sanitize,
)


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


def test_every_analysis_event_carries_its_provider_measurement() -> None:
    client = _client()
    EVENTS_SINK.events.clear()
    response = client.post("/v1/analyze", json={"symbol": "BTC/USDT", "timeframe": "4H"})
    assert response.status_code == 200, response.text
    (event,) = [item for item in EVENTS_SINK.events if item["event"] == "analysis_completed"]
    assert {field: event[field] for field in PROVIDER_FIELDS} == new_provider_stats(), (
        "fixture data calls no provider"
    )
    assert not any(field in response.text for field in PROVIDER_FIELDS)


def test_the_measurement_fields_are_allowlisted_scalars() -> None:
    assert set(PROVIDER_FIELDS) <= FIELDS
    clean = sanitize(
        "analysis_completed",
        {**new_provider_stats(), "provider_exchanges": 3, "provider_exchange_max_ms": 12.34567},
    )
    assert clean is not None
    assert clean["provider_exchanges"] == 3 and clean["provider_exchange_max_ms"] == 12.346


def test_each_analysis_resets_its_provider_measurement_first() -> None:
    # In this thread's own context, so the reset is observable here.
    stale = CURRENT_PROVIDER_STATS.set({"provider_exchanges": 99})
    try:
        with pytest.raises(HTTPException):
            analyze_request(
                AnalysisRequest(symbol="BTC/USDT", timeframe="7H"),
                settings=Settings(data_mode="fixture"),
                run_store=InMemoryRunStore(limit=10),
            )
        assert CURRENT_PROVIDER_STATS.get() == new_provider_stats()
    finally:
        CURRENT_PROVIDER_STATS.reset(stale)


def test_the_app_closes_the_provider_pool_once_at_shutdown(monkeypatch: pytest.MonkeyPatch) -> None:
    from crypto_probability_engine.api import app as app_module

    closed: list[int] = []
    monkeypatch.setattr(app_module, "close_pool", lambda: closed.append(1))
    with TestClient(create_app(Settings(data_mode="fixture"))) as client:
        client.get("/v1/build-info")
        assert closed == []
    assert closed == [1]
