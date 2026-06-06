from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest

from crypto_probability_engine.adapters.http_client import PublicHttpClient
from crypto_probability_engine.adapters.mappers import (
    map_interval,
    parse_binance_candles,
    parse_okx_candles,
)
from crypto_probability_engine.adapters.public_market import BinancePublicAdapter, OkxPublicAdapter
from crypto_probability_engine.adapters.types import ProviderError
from crypto_probability_engine.config.settings import Settings
from crypto_probability_engine.normalizers.symbols import normalize_symbol
from crypto_probability_engine.validation.market_data import validate_market_snapshot


def public_client(handler: httpx.MockTransport) -> PublicHttpClient:
    return PublicHttpClient(
        timeout_seconds=8.0,
        max_retries=0,
        rate_limit_per_min=60,
        client=httpx.Client(transport=handler),
        sleep_func=lambda _: None,
    )


def epoch_millis(value: datetime) -> int:
    return int(value.timestamp() * 1000)


def binance_rows(*, count: int = 202, timeframe_seconds: int = 14_400) -> list[list[Any]]:
    start = datetime.now(UTC) - timedelta(seconds=count * timeframe_seconds)
    rows: list[list[Any]] = []
    for idx in range(count):
        open_time = start + timedelta(seconds=idx * timeframe_seconds)
        close_time = open_time + timedelta(seconds=timeframe_seconds)
        close = "99999.0" if idx == count - 1 else str(100.05 + idx * 0.1)
        rows.append(
            [
                epoch_millis(open_time),
                str(100.0 + idx * 0.1),
                str(101.0 + idx * 0.1),
                str(99.0 + idx * 0.1),
                close,
                str(1000.0 + idx),
                epoch_millis(close_time) - 1,
                "0",
                0,
                "0",
                "0",
                "0",
            ]
        )
    return rows


def okx_payload(*, count: int = 202, timeframe_seconds: int = 14_400) -> dict:
    start = datetime.now(UTC) - timedelta(seconds=count * timeframe_seconds)
    rows: list[list[Any]] = []
    for idx in range(count):
        open_time = start + timedelta(seconds=idx * timeframe_seconds)
        confirm = "0" if idx == count - 1 else "1"
        close = "99999.0" if confirm == "0" else str(100.05 + idx * 0.1)
        rows.append(
            [
                str(epoch_millis(open_time)),
                str(100.0 + idx * 0.1),
                str(101.0 + idx * 0.1),
                str(99.0 + idx * 0.1),
                close,
                str(1000.0 + idx),
                "0",
                "0",
                confirm,
            ]
        )
    return {"code": "0", "data": list(reversed(rows))}


def test_interval_mapping_is_provider_specific() -> None:
    assert map_interval("1H", "binance") == "1h"
    assert map_interval("4H", "binance") == "4h"
    assert map_interval("1H", "okx") == "1H"
    assert map_interval("4H", "okx") == "4H"
    with pytest.raises(ProviderError):
        map_interval("2H", "binance")


def test_binance_mapper_drops_last_in_progress_row() -> None:
    candles = parse_binance_candles(binance_rows(), timeframe="4H")
    assert len(candles) == 201
    assert candles[-1].close != 99999.0
    assert candles[-1].close_time_utc == candles[-1].open_time_utc + timedelta(hours=4)


def test_okx_mapper_reverses_and_drops_unconfirmed_row() -> None:
    candles = parse_okx_candles(okx_payload(), timeframe="4H")
    assert len(candles) == 201
    assert candles[-1].close != 99999.0
    assert candles == tuple(sorted(candles, key=lambda candle: candle.open_time_utc))
    assert candles[-1].close_time_utc == candles[-1].open_time_utc + timedelta(hours=4)


def test_binance_public_adapter_fetches_keyless_public_snapshot() -> None:
    rows = binance_rows()
    seen_paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_paths.append(request.url.path)
        assert request.url.host == "data-api.binance.vision"
        if request.url.path == "/api/v3/klines":
            assert request.url.params["symbol"] == "BTCUSDT"
            assert request.url.params["interval"] == "4h"
            return httpx.Response(200, json=rows)
        if request.url.path == "/api/v3/depth":
            assert request.url.params["symbol"] == "BTCUSDT"
            assert request.url.params["limit"] == "100"
            return httpx.Response(
                200,
                json={
                    "lastUpdateId": 1,
                    "bids": [["120.0", "2.0"]],
                    "asks": [["120.5", "2.5"]],
                },
            )
        return httpx.Response(404)

    adapter = BinancePublicAdapter(
        settings=Settings(data_mode="live"),
        http_client=public_client(httpx.MockTransport(handler)),
    )
    snapshot = adapter.fetch_market_snapshot(normalize_symbol("BTC"), "4H")
    validate_market_snapshot(snapshot, min_bars=200)

    assert snapshot.provider == "binance"
    assert snapshot.normalized_symbol == "BTC/USDT"
    assert seen_paths == ["/api/v3/klines", "/api/v3/depth"]


def test_okx_public_adapter_fetches_keyless_public_snapshot() -> None:
    payload = okx_payload()
    seen_paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_paths.append(request.url.path)
        assert request.url.host == "www.okx.com"
        if request.url.path == "/api/v5/market/candles":
            assert request.url.params["instId"] == "BTC-USDT"
            assert request.url.params["bar"] == "4H"
            return httpx.Response(200, json=payload)
        if request.url.path == "/api/v5/market/books":
            assert request.url.params["instId"] == "BTC-USDT"
            assert request.url.params["sz"] == "100"
            return httpx.Response(
                200,
                json={
                    "code": "0",
                    "data": [
                        {
                            "bids": [["120.0", "2.0", "0", "1"]],
                            "asks": [["120.5", "2.5", "0", "1"]],
                        }
                    ],
                },
            )
        return httpx.Response(404)

    adapter = OkxPublicAdapter(
        settings=Settings(data_mode="live"),
        http_client=public_client(httpx.MockTransport(handler)),
    )
    snapshot = adapter.fetch_market_snapshot(normalize_symbol("BTC"), "4H")
    validate_market_snapshot(snapshot, min_bars=200)

    assert snapshot.provider == "okx"
    assert snapshot.normalized_symbol == "BTC/USDT"
    assert seen_paths == ["/api/v5/market/candles", "/api/v5/market/books"]


def test_public_client_maps_429_to_typed_provider_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"msg": "too many requests"})

    client = public_client(httpx.MockTransport(handler))
    with pytest.raises(ProviderError) as excinfo:
        client.get_json(
            base_url="https://data-api.binance.vision",
            path="/api/v3/klines",
            params={"symbol": "BTCUSDT"},
            provider="binance",
        )
    assert excinfo.value.code == "PROVIDER_DEGRADED"


def test_public_client_maps_timeout_to_typed_provider_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timeout", request=request)

    client = public_client(httpx.MockTransport(handler))
    with pytest.raises(ProviderError) as excinfo:
        client.get_json(
            base_url="https://data-api.binance.vision",
            path="/api/v3/klines",
            params={"symbol": "BTCUSDT"},
            provider="binance",
        )
    assert excinfo.value.code == "PROVIDER_DEGRADED"


def test_binance_malformed_payload_maps_to_typed_error() -> None:
    with pytest.raises(ProviderError) as excinfo:
        parse_binance_candles([["not enough fields"], ["dropped as progress"]], timeframe="4H")
    assert excinfo.value.code == "SCHEMA_VALIDATION_FAILED"


def test_okx_invalid_payload_maps_to_typed_error() -> None:
    with pytest.raises(ProviderError) as excinfo:
        parse_okx_candles({"code": "51001", "data": []}, timeframe="4H")
    assert excinfo.value.code == "INVALID_SYMBOL"
