from __future__ import annotations

from collections.abc import Iterator

import httpx
import pytest

from crypto_probability_engine.adapters import http_client
from crypto_probability_engine.adapters.http_client import PublicHttpClient
from crypto_probability_engine.adapters.types import ProviderError


class CountingStream(httpx.SyncByteStream):
    def __init__(self, chunks: list[bytes], *, clock: FakeClock | None = None) -> None:
        self.chunks = chunks
        self.clock = clock
        self.yielded = 0

    def __iter__(self) -> Iterator[bytes]:
        for chunk in self.chunks:
            self.yielded += 1
            if self.clock is not None:
                self.clock.now += 0.6
            yield chunk


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def monotonic(self) -> float:
        return self.now


def make_client(
    handler: httpx.MockTransport,
    *,
    max_retries: int = 0,
) -> PublicHttpClient:
    return PublicHttpClient(
        timeout_seconds=8.0,
        max_retries=max_retries,
        rate_limit_per_min=60,
        client=httpx.Client(transport=handler),
        sleep_func=lambda _: None,
    )


def get_json(client: PublicHttpClient) -> object:
    return client.get_json(
        base_url="https://data-api.binance.vision",
        path="/api/v3/test",
        params={},
        provider="binance",
    )


def test_response_over_byte_cap_stops_streaming_and_degrades(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(http_client, "MAX_RESPONSE_BYTES", 8)
    stream = CountingStream([b"1234"] * 100)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, stream=stream)

    with pytest.raises(ProviderError) as excinfo:
        get_json(make_client(httpx.MockTransport(handler)))

    assert excinfo.value.code == "PROVIDER_DEGRADED"
    assert excinfo.value.provider == "binance"
    assert stream.yielded == 3


def test_slow_trickle_over_wall_clock_deadline_degrades(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = FakeClock()
    monkeypatch.setattr(http_client, "REQUEST_DEADLINE_SECONDS", 1.0)
    monkeypatch.setattr(http_client.time, "monotonic", clock.monotonic)
    stream = CountingStream([b"{"] + [b" "] * 10 + [b"}"], clock=clock)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, stream=stream)

    with pytest.raises(ProviderError) as excinfo:
        get_json(make_client(httpx.MockTransport(handler)))

    assert excinfo.value.code == "PROVIDER_DEGRADED"
    assert excinfo.value.provider == "binance"
    assert stream.yielded == 2


def test_small_response_preserves_json_result() -> None:
    content = b'\xef\xbb\xbf{"text":"caf\\u00e9","number":1.25,"items":[true,null]}'
    expected = httpx.Response(200, content=content).json()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=content)

    assert get_json(make_client(httpx.MockTransport(handler))) == expected


def test_byte_cap_is_enforced_per_retry_attempt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(http_client, "MAX_RESPONSE_BYTES", 8)
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(200, stream=CountingStream([b"1234"] * 3))
        return httpx.Response(200, content=b'{"ok":1}')

    result = get_json(make_client(httpx.MockTransport(handler), max_retries=1))

    assert result == {"ok": 1}
    assert attempts == 2


def test_wall_clock_deadline_is_reset_for_retry_attempt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = FakeClock()
    monkeypatch.setattr(http_client, "REQUEST_DEADLINE_SECONDS", 1.0)
    monkeypatch.setattr(http_client.time, "monotonic", clock.monotonic)
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(
                200,
                stream=CountingStream([b"{"] + [b" "] * 3, clock=clock),
            )
        return httpx.Response(200, content=b'{"ok":1}')

    result = get_json(make_client(httpx.MockTransport(handler), max_retries=1))

    assert result == {"ok": 1}
    assert attempts == 2
