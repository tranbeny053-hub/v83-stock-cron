from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx
import pytest

from crypto_probability_engine.adapters.derivatives import (
    BinanceUsdmDerivativesAdapter,
    OkxSwapDerivativesAdapter,
    PublicDerivativesAdapterError,
)
from crypto_probability_engine.adapters.derivatives_endpoints import (
    DerivativesPublicHttpClient,
)


def _client(handler: Callable[[httpx.Request], httpx.Response]) -> DerivativesPublicHttpClient:
    return DerivativesPublicHttpClient(
        timeout_seconds=4.0,
        max_retries=0,
        rate_limit_per_min=100,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleep_func=lambda _: None,
    )


def _binance_response(path: str) -> Any:
    return {
        "/fapi/v1/exchangeInfo": {"symbols": []},
        "/fapi/v1/premiumIndex": {"symbol": "BTCUSDT"},
        "/fapi/v1/fundingRate": [],
        "/fapi/v1/fundingInfo": [],
        "/fapi/v1/openInterest": {"symbol": "BTCUSDT"},
        "/futures/data/openInterestHist": [],
    }[path]


def test_binance_methods_use_exact_public_get_paths_once_without_headers() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.method == "GET"
        assert request.url.host == "fapi.binance.com"
        assert not request.headers.get("authorization")
        return httpx.Response(200, json=_binance_response(request.url.path))

    adapter = BinanceUsdmDerivativesAdapter(http_client=_client(handler))
    start, end = 1_700_000_000_000, 1_700_086_400_000
    adapter.fetch_exchange_info()
    adapter.fetch_current_funding("BTCUSDT")
    adapter.fetch_funding_history("BTCUSDT", start_time_ms=start, end_time_ms=end)
    adapter.fetch_funding_info()
    adapter.fetch_current_open_interest("BTCUSDT")
    adapter.fetch_open_interest_history(
        "BTCUSDT", period="5m", start_time_ms=start, end_time_ms=end
    )

    assert [request.url.path for request in requests] == [
        "/fapi/v1/exchangeInfo",
        "/fapi/v1/premiumIndex",
        "/fapi/v1/fundingRate",
        "/fapi/v1/fundingInfo",
        "/fapi/v1/openInterest",
        "/futures/data/openInterestHist",
    ]


def test_okx_methods_use_exact_public_get_paths_once_without_headers() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.method == "GET"
        assert request.url.host == "www.okx.com"
        assert not request.headers.get("authorization")
        return httpx.Response(200, json={"code": "0", "data": []})

    adapter = OkxSwapDerivativesAdapter(http_client=_client(handler))
    start, end = 1_700_000_000_000, 1_700_086_400_000
    adapter.fetch_instruments()
    adapter.fetch_current_funding("BTC-USDT-SWAP")
    adapter.fetch_funding_history("BTC-USDT-SWAP", start_time_ms=start, end_time_ms=end, limit=50)
    adapter.fetch_current_open_interest("BTC-USDT-SWAP")

    assert [request.url.path for request in requests] == [
        "/api/v5/public/instruments",
        "/api/v5/public/funding-rate",
        "/api/v5/public/funding-rate-history",
        "/api/v5/public/open-interest",
    ]
    assert requests[0].url.params["instType"] == "SWAP"
    assert requests[2].url.params["before"] == str(start)
    assert requests[2].url.params["after"] == str(end)


@pytest.mark.parametrize(
    "invoke",
    [
        lambda adapter: adapter.fetch_funding_history(
            "BTCUSDT", start_time_ms=1, end_time_ms=2, limit=1001
        ),
        lambda adapter: adapter.fetch_funding_history(
            "BTCUSDT", start_time_ms=2, end_time_ms=1, limit=10
        ),
        lambda adapter: adapter.fetch_open_interest_history(
            "BTCUSDT", period="7m", start_time_ms=1, end_time_ms=2, limit=10
        ),
        lambda adapter: adapter.fetch_open_interest_history(
            "BTCUSDT", period="5m", start_time_ms=1, end_time_ms=2, limit=501
        ),
    ],
)
def test_binance_invalid_history_bounds_fail_before_request(invoke) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json=[])

    with pytest.raises(PublicDerivativesAdapterError) as excinfo:
        invoke(BinanceUsdmDerivativesAdapter(http_client=_client(handler)))
    assert excinfo.value.code == "INVALID_PARAMETER"
    assert calls == 0


def test_okx_invalid_history_limit_fails_before_request() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"code": "0", "data": []})

    adapter = OkxSwapDerivativesAdapter(http_client=_client(handler))
    with pytest.raises(PublicDerivativesAdapterError):
        adapter.fetch_funding_history("BTC-USDT-SWAP", start_time_ms=1, end_time_ms=2, limit=101)
    assert calls == 0


@pytest.mark.parametrize("provider", ["binance", "okx"])
def test_malformed_provider_envelope_raises_typed_error(provider: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"unexpected": True})

    if provider == "binance":
        adapter = BinanceUsdmDerivativesAdapter(http_client=_client(handler))
        invoke = adapter.fetch_exchange_info
    else:
        adapter = OkxSwapDerivativesAdapter(http_client=_client(handler))
        invoke = adapter.fetch_instruments
    with pytest.raises(PublicDerivativesAdapterError) as excinfo:
        invoke()
    assert excinfo.value.code == "MALFORMED_ENVELOPE"


def test_transport_or_http_failure_is_wrapped_as_typed_public_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"code": "temporarily_unavailable"})

    adapter = OkxSwapDerivativesAdapter(http_client=_client(handler))
    with pytest.raises(PublicDerivativesAdapterError) as excinfo:
        adapter.fetch_current_funding("BTC-USDT-SWAP")
    assert excinfo.value.code == "PUBLIC_REQUEST_FAILED"
    assert excinfo.value.endpoint == "/api/v5/public/funding-rate"


def test_future_current_state_request_budget_is_four_and_excludes_history() -> None:
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        if request.url.host == "fapi.binance.com":
            return httpx.Response(200, json={"symbol": "BTCUSDT"})
        return httpx.Response(200, json={"code": "0", "data": [{}]})

    client = _client(handler)
    BinanceUsdmDerivativesAdapter(http_client=client).fetch_current_funding("BTCUSDT")
    BinanceUsdmDerivativesAdapter(http_client=client).fetch_current_open_interest("BTCUSDT")
    OkxSwapDerivativesAdapter(http_client=client).fetch_current_funding("BTC-USDT-SWAP")
    OkxSwapDerivativesAdapter(http_client=client).fetch_current_open_interest("BTC-USDT-SWAP")

    assert len(paths) == 4
    assert all("history" not in path.lower() for path in paths)
