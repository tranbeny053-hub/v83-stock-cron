from __future__ import annotations

import json

from fastapi.testclient import TestClient

from crypto_probability_engine.adapters.provider_selection import (
    ProviderSelectionError,
    ProviderSelectionResult,
)
from crypto_probability_engine.api.app import create_app
from crypto_probability_engine.api.auth import hash_code, session_limiter
from crypto_probability_engine.api.schemas import ErrorCode, validate_analysis_response
from crypto_probability_engine.config.settings import Settings
from tests.fixtures.market_data import (
    make_downtrend_snapshot,
    make_high_volatility_snapshot,
    make_snapshot,
)


def make_live_client(monkeypatch) -> TestClient:
    session_limiter.reset()
    settings = Settings(
        access_code_hash=hash_code("operator-test-code"),
        session_signing_key="test-signing-key",
        session_cookie_secure=False,
        data_mode="live",
        candle_cache_ttl_seconds=0,
    )
    return TestClient(create_app(settings))


def login(client: TestClient) -> None:
    response = client.post("/v1/auth/login", json={"code": "operator-test-code"})
    assert response.status_code == 200


def test_live_selection_data_quality_reaches_response(monkeypatch) -> None:
    def fake_select(symbol, timeframe, *, settings):
        return ProviderSelectionResult(
            snapshot=make_snapshot(provider="binance"),
            provider_state={
                "status": "OK",
                "active_provider": "binance",
                "providers": {"binance": {"status": "OK"}},
            },
            data_quality={
                "status": "OK",
                "warnings": ["single-source, cross-check unavailable"],
                "freshness_budget": "DEFAULT_PHASE1A",
                "is_live_data": True,
                "data_source": "BINANCE_PUBLIC",
                "latest_candle_age_seconds": 120,
                "provider_failures": {"okx": "PROVIDER_DEGRADED: timeout"},
            },
        )

    monkeypatch.setattr(
        "crypto_probability_engine.api.analysis_service.select_market_data",
        fake_select,
    )
    client = make_live_client(monkeypatch)
    login(client)

    response = client.post("/v1/analyze", json={"symbol": "BTC", "analysis_mode": "METRICS_ONLY"})
    assert response.status_code == 200
    payload = response.json()
    validate_analysis_response(payload)
    assert payload["data_quality"]["is_live_data"] is True
    assert payload["data_quality"]["data_source"] == "BINANCE_PUBLIC"
    assert payload["frontend_display"]["is_live_data"] is True
    assert payload["frontend_display"]["data_source"] == "BINANCE_PUBLIC"
    assert payload["frontend_display"]["data_quality_warnings"]


def test_down_market_live_response_validates_with_signed_negative_fields(monkeypatch) -> None:
    def fake_select(symbol, timeframe, *, settings):
        return ProviderSelectionResult(
            snapshot=make_downtrend_snapshot(provider="binance", symbol=symbol.display),
            provider_state={
                "status": "OK",
                "active_provider": "binance",
                "providers": {"binance": {"status": "OK"}},
            },
            data_quality={
                "status": "OK",
                "warnings": ["single-source, cross-check unavailable"],
                "freshness_budget": "DEFAULT_PHASE1A",
                "is_live_data": True,
                "data_source": "BINANCE_PUBLIC",
                "latest_candle_age_seconds": 120,
                "provider_failures": {},
            },
        )

    monkeypatch.setattr(
        "crypto_probability_engine.api.analysis_service.select_market_data",
        fake_select,
    )
    client = make_live_client(monkeypatch)
    login(client)

    response = client.post("/v1/analyze", json={"symbol": "BTC", "analysis_mode": "METRICS_ONLY"})
    assert response.status_code == 200
    payload = response.json()
    validate_analysis_response(payload)
    trend = payload["market_features"]["trend_mtf"]
    risk = payload["risk_arbiter_state"]
    score = payload["score_stack"]
    assert trend["primary_return"] < 0.0
    assert trend["extended_return"] < 0.0
    assert risk["alpha_signal"] < 0.0
    assert risk["net_signal"] < 0.0
    assert score["directional_edge"] < 0.0
    horizon = payload["probability_state"]["horizons"]["H_primary"]
    assert horizon["p_up_frac"] + horizon["p_down_frac"] + horizon["p_timeout_frac"] == 1.0
    serialized = json.dumps(payload)
    for forbidden_base in ("primary_return", "net_signal", "directional_edge"):
        assert forbidden_base + "_frac" not in serialized


def test_high_volatility_response_has_only_bounded_frac_fields(monkeypatch) -> None:
    def fake_select(symbol, timeframe, *, settings):
        return ProviderSelectionResult(
            snapshot=make_high_volatility_snapshot(provider="binance", symbol=symbol.display),
            provider_state={
                "status": "OK",
                "active_provider": "binance",
                "providers": {"binance": {"status": "OK"}},
            },
            data_quality={
                "status": "OK",
                "warnings": ["single-source, cross-check unavailable"],
                "freshness_budget": "DEFAULT_PHASE1A",
                "is_live_data": True,
                "data_source": "BINANCE_PUBLIC",
                "latest_candle_age_seconds": 120,
                "provider_failures": {},
            },
        )

    monkeypatch.setattr(
        "crypto_probability_engine.api.analysis_service.select_market_data",
        fake_select,
    )
    client = make_live_client(monkeypatch)
    login(client)

    response = client.post("/v1/analyze", json={"symbol": "BTC", "analysis_mode": "METRICS_ONLY"})
    assert response.status_code == 200
    payload = response.json()
    validate_analysis_response(payload)
    volatility = payload["market_features"]["volatility"]
    risk = payload["risk_arbiter_state"]
    tail = payload["tail_risk_state"]
    assert volatility["realized_vol"] > 1.0
    assert risk["risk_pressure"] > 1.0
    assert tail["cvar_loss"] > 1.0
    serialized = json.dumps(payload)
    for old_name in ("realized_vol", "risk_pressure", "cvar_loss"):
        assert old_name + "_frac" not in serialized
    for path, value in _iter_frac_fields(payload):
        assert isinstance(value, int | float), path
        assert 0.0 <= float(value) <= 1.0, path
    horizon = payload["probability_state"]["horizons"]["H_primary"]
    assert horizon["p_up_frac"] + horizon["p_down_frac"] + horizon["p_timeout_frac"] == 1.0


def test_live_failure_returns_visible_error_without_fixture(monkeypatch) -> None:
    def fake_select(symbol, timeframe, *, settings):
        raise ProviderSelectionError(
            code=ErrorCode.PROVIDER_DEGRADED,
            message="No live public provider produced valid data.",
            provider_state={
                "status": "PROVIDER_DEGRADED",
                "active_provider": None,
                "providers": {},
            },
            data_quality={
                "status": "UNAVAILABLE",
                "warnings": ["No live public provider produced valid data."],
                "freshness_budget": "DEFAULT_PHASE1A",
                "is_live_data": False,
                "data_source": "UNAVAILABLE",
                "latest_candle_age_seconds": None,
                "provider_failures": {"binance": "PROVIDER_DEGRADED"},
            },
        )

    monkeypatch.setattr(
        "crypto_probability_engine.api.analysis_service.select_market_data",
        fake_select,
    )
    client = make_live_client(monkeypatch)
    login(client)

    response = client.post("/v1/analyze", json={"symbol": "BTC"})
    assert response.status_code == 503
    payload = response.json()
    assert payload["detail"]["error"]["code"] == "PROVIDER_DEGRADED"
    assert payload["detail"]["error"]["provider_state_snapshot"]["data_quality"][
        "data_source"
    ] == "UNAVAILABLE"
    assert "FIXTURE_DEMO" not in json.dumps(payload)


def test_live_batch_keeps_partial_failure_isolated(monkeypatch) -> None:
    def fake_select(symbol, timeframe, *, settings):
        if symbol.base == "ETH":
            raise ProviderSelectionError(
                code=ErrorCode.PROVIDER_DEGRADED,
                message="No live public provider produced valid data.",
                provider_state={"status": "PROVIDER_DEGRADED", "providers": {}},
                data_quality={
                    "status": "UNAVAILABLE",
                    "warnings": ["provider failed"],
                    "freshness_budget": "DEFAULT_PHASE1A",
                    "is_live_data": False,
                    "data_source": "UNAVAILABLE",
                    "latest_candle_age_seconds": None,
                    "provider_failures": {"binance": "PROVIDER_DEGRADED"},
                },
            )
        return ProviderSelectionResult(
            snapshot=make_snapshot(provider="binance", symbol=symbol.display),
            provider_state={"status": "OK", "active_provider": "binance", "providers": {}},
            data_quality={
                "status": "OK",
                "warnings": [],
                "freshness_budget": "DEFAULT_PHASE1A",
                "is_live_data": True,
                "data_source": "BINANCE_PUBLIC",
                "latest_candle_age_seconds": 120,
                "provider_failures": {},
            },
        )

    monkeypatch.setattr(
        "crypto_probability_engine.api.analysis_service.select_market_data",
        fake_select,
    )
    client = make_live_client(monkeypatch)
    login(client)

    response = client.post(
        "/v1/analyze_batch",
        json={"requests": [{"symbol": "BTC"}, {"symbol": "ETH"}]},
    )
    assert response.status_code == 200
    payload = response.json()
    assert len(payload["results"]) == 1
    assert len(payload["errors"]) == 1
    assert payload["results"][0]["data_quality"]["data_source"] == "BINANCE_PUBLIC"
    assert payload["errors"][0]["detail"]["error"]["code"] == "PROVIDER_DEGRADED"


def _iter_frac_fields(value, path: str = "payload"):
    if isinstance(value, dict):
        for key, item in value.items():
            item_path = f"{path}.{key}"
            if key.endswith("_frac"):
                yield item_path, item
            yield from _iter_frac_fields(item, item_path)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _iter_frac_fields(item, f"{path}[{index}]")
