"""Provider coalescing (plan §9.1; owner ruling DP-B as narrowed on 2026-10-05).

A pooled client (one handed no httpx.Client) shares the process's one connection pool and coalesces
identical requests in flight; every request, retry, error and freshness semantic stays what it was.
These tests prove that:
- the pool is shared, while cookies and rate limits stay each client's own;
- identical requests in flight make one exchange, and any difference (query, header, cookie,
  timeout) makes its own;
- a response that sets a cookie, and an unexpected failure, are never shared;
- a shared timeout or transport failure maps exactly as the caller's own would, and each caller
  keeps its own attempts and rate-limit history;
- the pooled path answers byte for byte like the unpooled one, for every outcome;
- an injected client is never pooled or coalesced;
- closing a client leaves the pool open, and only close_pool closes it;
- the passive measurement counts and changes nothing.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterator
from typing import Any

import httpx
import pytest

from crypto_probability_engine.adapters import http_client
from crypto_probability_engine.adapters.http_client import PublicHttpClient
from crypto_probability_engine.adapters.types import ProviderError
from crypto_probability_engine.telemetry.events import CURRENT_PROVIDER_STATS, new_provider_stats

BASE = "https://data-api.binance.vision"
PATH = "/api/v3/klines"
PAYLOAD = [[1, "2", "3"]]
Handler = Callable[[httpx.Request], httpx.Response]


@pytest.fixture(autouse=True)
def fresh_pool() -> Iterator[None]:
    http_client.close_pool()
    yield
    http_client.close_pool()


def install(monkeypatch: pytest.MonkeyPatch, handler: Handler) -> list[httpx.Request]:
    """Make the process pool a mock transport; return the requests it receives, in order."""

    seen: list[httpx.Request] = []
    lock = threading.Lock()

    def record(request: httpx.Request) -> httpx.Response:
        with lock:
            seen.append(request)
        return handler(request)

    monkeypatch.setattr(http_client, "_POOL_FACTORY", lambda: httpx.MockTransport(record))
    return seen


def pooled(*, max_retries: int = 0, rate_limit_per_min: int = 60) -> PublicHttpClient:
    return PublicHttpClient(
        timeout_seconds=8.0,
        max_retries=max_retries,
        rate_limit_per_min=rate_limit_per_min,
        sleep_func=lambda _: None,
    )


def injected(handler: Handler, *, max_retries: int = 0) -> PublicHttpClient:
    return PublicHttpClient(
        timeout_seconds=8.0,
        max_retries=max_retries,
        rate_limit_per_min=60,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleep_func=lambda _: None,
    )


def get(
    client: PublicHttpClient,
    *,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    provider: str = "binance",
) -> Any:
    return client.get_json(
        base_url=BASE,
        path=PATH,
        params=params if params is not None else {"symbol": "BTCUSDT"},
        provider=provider,
        headers=headers,
    )


def outcome(call: Callable[[], Any]) -> tuple[Any, ...]:
    """A comparable outcome: the payload, or every attribute of the provider error."""

    try:
        return ("ok", call())
    except ProviderError as exc:
        return (
            "error",
            exc.code,
            str(exc),
            exc.provider,
            exc.http_status,
            exc.error_code,
            exc.error_type,
            exc.retry_after_seconds,
            exc.operation,
        )


class Gate:
    """Holds the first exchange open until every follower waits on it, so the overlap is certain."""

    def __init__(self, followers: int) -> None:
        self.followers = followers
        self.lock = threading.Lock()
        self.waiting = 0
        self.all_waiting = threading.Event()

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        gate = self

        class GatedEvent(threading.Event):
            def wait(self, timeout: float | None = None) -> bool:
                with gate.lock:
                    gate.waiting += 1
                    if gate.waiting >= gate.followers:
                        gate.all_waiting.set()
                return super().wait(timeout)

        class GatedCall(http_client._Call):
            def __init__(self) -> None:
                super().__init__()
                self.done = GatedEvent()

        monkeypatch.setattr(http_client, "_Call", GatedCall)

    def hold(self) -> None:
        self.all_waiting.wait(5)


def run_together(n: int, target: Callable[[int], Any]) -> list[tuple[Any, ...]]:
    results: list[tuple[Any, ...]] = [("missing",)] * n

    def worker(index: int) -> None:
        try:
            results[index] = outcome(lambda: target(index))
        except BaseException as exc:  # noqa: BLE001 - recorded for the assertion
            results[index] = ("raised", type(exc).__name__)

    threads = [threading.Thread(target=worker, args=(index,)) for index in range(n)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(30)
    return results


def ok_json(payload: Any = PAYLOAD, **kwargs: Any) -> httpx.Response:
    return httpx.Response(200, json=payload, **kwargs)


# --------------------------------------------------------------------------- the shared pool
def test_pooled_clients_share_one_pool_but_keep_their_own_cookies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    built: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("set") == "1":
            return ok_json(headers={"Set-Cookie": "venue=a; Path=/"})
        return ok_json()

    seen = install(monkeypatch, handler)
    factory = http_client._POOL_FACTORY
    monkeypatch.setattr(http_client, "_POOL_FACTORY", lambda: built.append(1) or factory())
    first, second = pooled(), pooled()
    get(first, params={"set": "1"})
    get(first)
    get(second)
    assert built == [1], "one pool for the process"
    assert first._pooled and second._pooled
    assert first.client is not second.client, "each client keeps its own httpx.Client"
    cookies = [request.headers.get("cookie") for request in seen]
    assert cookies == [None, "venue=a", None], "a cookie stays with the client that received it"


def test_rate_limits_stay_each_clients_own(monkeypatch: pytest.MonkeyPatch) -> None:
    install(monkeypatch, lambda request: ok_json())
    first, second = pooled(rate_limit_per_min=1), pooled(rate_limit_per_min=1)
    assert get(first) == PAYLOAD
    with pytest.raises(ProviderError, match="Local provider rate limit exceeded."):
        get(first)
    assert get(second) == PAYLOAD


def test_closing_a_client_leaves_the_pool_open_and_close_pool_closes_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    closed: list[int] = []

    class Tracked(httpx.MockTransport):
        def close(self) -> None:
            closed.append(1)

    monkeypatch.setattr(http_client, "_POOL_FACTORY", lambda: Tracked(lambda request: ok_json()))
    first = pooled()
    get(first)
    assert first.client is not None
    first.client.close()
    assert closed == []
    assert get(pooled()) == PAYLOAD
    http_client.close_pool()
    assert closed == [1]


def test_an_injected_client_is_never_pooled_or_coalesced() -> None:
    arrived = threading.Barrier(2, timeout=5)
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        arrived.wait()  # both in flight at once, or this breaks
        return ok_json()

    transport = httpx.MockTransport(handler)
    clients = [
        PublicHttpClient(
            timeout_seconds=8.0,
            max_retries=0,
            rate_limit_per_min=60,
            client=httpx.Client(transport=transport),
            sleep_func=lambda _: None,
        )
        for _ in range(2)
    ]
    results = run_together(2, lambda index: get(clients[index]))
    assert results == [("ok", PAYLOAD)] * 2
    assert calls == [1, 1]
    assert not any(client._pooled for client in clients)


# --------------------------------------------------------------------------- single-flight
def test_identical_requests_in_flight_make_one_exchange(monkeypatch: pytest.MonkeyPatch) -> None:
    gate = Gate(followers=3)
    gate.install(monkeypatch)

    def handler(request: httpx.Request) -> httpx.Response:
        gate.hold()
        return ok_json()

    seen = install(monkeypatch, handler)
    clients = [pooled() for _ in range(4)]
    results = run_together(4, lambda index: get(clients[index]))
    assert results == [("ok", PAYLOAD)] * 4
    assert len(seen) == 1


@pytest.mark.parametrize(
    "difference",
    [
        {"params": ({"symbol": "BTCUSDT"}, {"symbol": "ETHUSDT"})},
        {"headers": ({"X-Venue": "a"}, {"X-Venue": "b"})},
        {"timeouts": (8.0, 7.0)},
        {"cookies": ("venue=a", None)},
    ],
    ids=["query", "header", "timeout", "cookie"],
)
def test_requests_that_differ_in_anything_make_their_own_exchange(
    monkeypatch: pytest.MonkeyPatch, difference: dict[str, Any]
) -> None:
    arrived = threading.Barrier(2, timeout=5)

    def handler(request: httpx.Request) -> httpx.Response:
        arrived.wait()  # both in flight at once: one exchange alone would break this
        return ok_json()

    seen = install(monkeypatch, handler)
    clients = [pooled(), pooled()]
    params: tuple[Any, ...] = ({"symbol": "BTCUSDT"}, {"symbol": "BTCUSDT"})
    headers: tuple[Any, ...] = (None, None)
    if "params" in difference:
        params = difference["params"]
    if "headers" in difference:
        headers = difference["headers"]
    if "timeouts" in difference:
        for client, seconds in zip(clients, difference["timeouts"], strict=True):
            client.timeout_seconds = seconds
    if "cookies" in difference:
        clients[0]._client().cookies.set("venue", "a", domain="data-api.binance.vision")
    results = run_together(
        2, lambda index: get(clients[index], params=params[index], headers=headers[index])
    )
    assert results == [("ok", PAYLOAD)] * 2
    assert len(seen) == 2


def test_a_response_that_sets_a_cookie_is_never_shared(monkeypatch: pytest.MonkeyPatch) -> None:
    gate = Gate(followers=1)
    gate.install(monkeypatch)
    first = threading.Event()

    def handler(request: httpx.Request) -> httpx.Response:
        if not first.is_set():
            first.set()
            gate.hold()
        return ok_json(headers={"Set-Cookie": "venue=a; Path=/"})

    seen = install(monkeypatch, handler)
    clients = [pooled(), pooled()]
    results = run_together(2, lambda index: get(clients[index]))
    assert results == [("ok", PAYLOAD)] * 2
    assert len(seen) == 2, "the follower sent its own request"
    assert all(client.client.cookies.get("venue") == "a" for client in clients if client.client)


@pytest.mark.parametrize(
    ("failure", "message"),
    [
        (httpx.ReadTimeout, "Provider public request timed out."),
        (httpx.ConnectError, "Provider public request failed."),
    ],
    ids=["timeout", "transport"],
)
def test_a_shared_failure_maps_exactly_as_the_callers_own(
    monkeypatch: pytest.MonkeyPatch, failure: type[httpx.HTTPError], message: str
) -> None:
    gate = Gate(followers=2)
    gate.install(monkeypatch)

    def handler(request: httpx.Request) -> httpx.Response:
        gate.hold()
        raise failure("upstream failed", request=request)

    seen = install(monkeypatch, handler)
    clients = [pooled() for _ in range(3)]
    results = run_together(3, lambda index: get(clients[index]))
    reference = outcome(
        lambda: get(
            injected(
                lambda request: (_ for _ in ()).throw(failure("upstream failed", request=request))
            )
        )
    )
    assert reference[2] == message
    assert results == [reference] * 3
    assert len(seen) == 1


def test_each_caller_keeps_its_own_attempts_after_a_shared_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gate = Gate(followers=1)
    gate.install(monkeypatch)
    failed = threading.Event()

    def handler(request: httpx.Request) -> httpx.Response:
        if not failed.is_set():
            failed.set()
            gate.hold()
            return httpx.Response(503, json={"code": "busy"})
        return ok_json()

    install(monkeypatch, handler)
    clients = [pooled(max_retries=1), pooled(max_retries=1)]
    stats = [new_provider_stats(), new_provider_stats()]

    def target(index: int) -> Any:
        CURRENT_PROVIDER_STATS.set(stats[index])
        return get(clients[index])

    results = run_together(2, target)
    assert results == [("ok", PAYLOAD)] * 2
    hits = [len(client._hits_by_host["data-api.binance.vision"]) for client in clients]
    assert hits == [2, 2], "each caller checked its own rate limit on both of its attempts"
    assert [item["provider_retries"] for item in stats] == [1, 1]
    assert sum(item["provider_coalesced"] for item in stats) >= 1


def test_an_unexpected_failure_is_never_shared(monkeypatch: pytest.MonkeyPatch) -> None:
    gate = Gate(followers=1)
    gate.install(monkeypatch)
    first = threading.Event()

    def handler(request: httpx.Request) -> httpx.Response:
        if not first.is_set():
            first.set()
            gate.hold()
        raise RuntimeError("not a transport failure")

    seen = install(monkeypatch, handler)
    clients = [pooled(), pooled()]
    results = run_together(2, lambda index: get(clients[index]))
    assert results == [("raised", "RuntimeError")] * 2
    assert len(seen) == 2, "the follower sent its own request"


# --------------------------------------------------------------------------- parity
def _oversized(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, content=b"[" + b"1," * 40 + b"1]")


SCENARIOS: dict[str, tuple[Handler, str]] = {
    "json": (lambda request: ok_json(), "binance"),
    "malformed json": (lambda request: httpx.Response(200, content=b"{not json"), "binance"),
    "symbol rejected": (lambda request: httpx.Response(404, json={"code": -1121}), "binance"),
    "parameters rejected": (lambda request: httpx.Response(400, json={"code": "P1"}), "fred"),
    "rate limited": (
        lambda request: httpx.Response(429, json={"code": "-1003"}, headers={"Retry-After": "7"}),
        "okx",
    ),
    "rate limited, bad retry-after": (
        lambda request: httpx.Response(418, headers={"Retry-After": "soon"}),
        "okx",
    ),
    "forbidden": (lambda request: httpx.Response(403, json={"code": "denied"}), "binance"),
    "server error": (lambda request: httpx.Response(500, content=b"oops"), "binance"),
    "timeout": (
        lambda request: (_ for _ in ()).throw(httpx.ReadTimeout("slow", request=request)),
        "binance",
    ),
    "transport": (
        lambda request: (_ for _ in ()).throw(httpx.ConnectError("down", request=request)),
        "binance",
    ),
    "oversized": (_oversized, "binance"),
}


_OP = "GET /api/v3/klines"
_DEGRADED = "PROVIDER_DEGRADED"
# What the client answered before this change (origin/main fc03be8e's http_client.py, run on these
# scenarios with no retry and with one): the same outcome for both, field for field.
GOLDEN: dict[str, tuple[Any, ...]] = {
    "json": ("ok", PAYLOAD),
    "malformed json": (
        "error",
        "SCHEMA_VALIDATION_FAILED",
        "Provider returned malformed JSON.",
        "binance",
        200,
        "MALFORMED_JSON",
        "SCHEMA",
        None,
        _OP,
    ),
    "symbol rejected": (
        "error",
        "INVALID_SYMBOL",
        "Provider rejected symbol.",
        "binance",
        404,
        "INVALID_SYMBOL",
        "REQUEST",
        None,
        _OP,
    ),
    "parameters rejected": (
        "error",
        _DEGRADED,
        "Provider rejected request parameters.",
        "fred",
        400,
        "P1",
        "REQUEST",
        None,
        _OP,
    ),
    "rate limited": (
        "error",
        _DEGRADED,
        "Provider rate limited the public request.",
        "okx",
        429,
        "-1003",
        "RATE_LIMIT",
        7.0,
        _OP,
    ),
    "rate limited, bad retry-after": (
        "error",
        _DEGRADED,
        "Provider rate limited the public request.",
        "okx",
        418,
        "RATE_LIMITED",
        "RATE_LIMIT",
        None,
        _OP,
    ),
    "forbidden": (
        "error",
        _DEGRADED,
        "Provider authentication failed.",
        "binance",
        403,
        "denied",
        "AUTH",
        None,
        _OP,
    ),
    "server error": (
        "error",
        _DEGRADED,
        "Provider public request failed: HTTP 500.",
        "binance",
        500,
        "HTTP_ERROR",
        "PROVIDER",
        None,
        _OP,
    ),
    "timeout": ("error", _DEGRADED, "Provider public request timed out.", "binance") + (None,) * 5,
    "transport": ("error", _DEGRADED, "Provider public request failed.", "binance") + (None,) * 5,
    "oversized": ("error", _DEGRADED, "Provider public request timed out.", "binance")
    + (None,) * 5,
}


@pytest.mark.parametrize("name", sorted(SCENARIOS))
def test_both_paths_answer_exactly_as_before(monkeypatch: pytest.MonkeyPatch, name: str) -> None:
    handler, provider = SCENARIOS[name]
    monkeypatch.setattr(http_client, "MAX_RESPONSE_BYTES", 64)
    install(monkeypatch, handler)
    for retries in (0, 1):
        unpooled = outcome(
            lambda retries=retries: get(injected(handler, max_retries=retries), provider=provider)
        )
        pooled_outcome = outcome(
            lambda retries=retries: get(pooled(max_retries=retries), provider=provider)
        )
        assert unpooled == pooled_outcome == GOLDEN[name]


# --------------------------------------------------------------------------- measurement
def test_the_measurement_counts_and_changes_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    responses = iter([httpx.Response(500), ok_json()])
    install(monkeypatch, lambda request: next(responses))
    stats = new_provider_stats()
    token = CURRENT_PROVIDER_STATS.set(stats)
    try:
        assert get(pooled(max_retries=1)) == PAYLOAD
    finally:
        CURRENT_PROVIDER_STATS.reset(token)
    assert stats["provider_exchanges"] == 2
    assert stats["provider_retries"] == 1
    assert stats["provider_coalesced"] == 0
    assert stats["provider_deadline_hits"] == 0
    assert stats["provider_exchange_max_ms"] >= 0.0


def test_a_timeout_is_counted_as_a_deadline_hit(monkeypatch: pytest.MonkeyPatch) -> None:
    install(
        monkeypatch,
        lambda request: (_ for _ in ()).throw(httpx.ReadTimeout("slow", request=request)),
    )
    stats = new_provider_stats()
    token = CURRENT_PROVIDER_STATS.set(stats)
    try:
        with pytest.raises(ProviderError, match="timed out"):
            get(pooled())
    finally:
        CURRENT_PROVIDER_STATS.reset(token)
    assert stats["provider_deadline_hits"] == 1
    assert stats["provider_exchanges"] == 1


def test_without_a_current_analysis_nothing_is_measured(monkeypatch: pytest.MonkeyPatch) -> None:
    install(monkeypatch, lambda request: ok_json())
    token = CURRENT_PROVIDER_STATS.set(None)
    try:
        assert get(pooled()) == PAYLOAD
        assert CURRENT_PROVIDER_STATS.get() is None
    finally:
        CURRENT_PROVIDER_STATS.reset(token)
