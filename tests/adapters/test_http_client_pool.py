"""Provider coalescing (plan §9.1; owner ruling DP-B as narrowed on 2026-10-05).

A pooled client (one handed no httpx.Client) shares the process's one connection pool and coalesces
identical requests in flight; every request, retry, error and freshness semantic stays what it was.
These tests prove that:
- the pool is shared, while cookies and rate limits stay each client's own;
- identical requests in flight make one exchange, and any difference (query, header, cookie,
  timeout) makes its own;
- only a success is shared: no failure of any kind, and no response that sets a cookie, is passed
  on; a follower then sends its own request, keeps its own attempts and rate-limit history, and
  answers exactly as it would have alone;
- a follower keeps its own deadline: it waits no longer than its own deadline, its own request gets
  a fresh one, and the first request's deadline is never its result;
- the pooled path answers byte for byte like the unpooled one, for every outcome;
- an injected client, and any client where httpx would mount a proxy, is never pooled or coalesced;
- closing a client leaves the pool open, and only close_pool closes it;
- the passive measurement counts and changes nothing.
"""

from __future__ import annotations

import json
import os
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


REAL_ENVIRONMENT_PROXIES = http_client._environment_proxies


@pytest.fixture(autouse=True)
def fresh_pool(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    # No proxy, whatever this machine's settings: the proxy tests below set their own.
    monkeypatch.setattr(http_client, "_environment_proxies", lambda: {})
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


class FakeTime:
    """The client's clock, moved only by the test: monotonic and perf_counter move together."""

    def __init__(self) -> None:
        self.now = 1_000.0
        self.lock = threading.Lock()

    def monotonic(self) -> float:
        with self.lock:
            return self.now

    perf_counter = monotonic

    def advance(self, seconds: float) -> None:
        with self.lock:
            self.now += seconds


def lead_then_follow(
    leader: PublicHttpClient, follower: PublicHttpClient, *, joined: Callable[[], None]
) -> dict[str, tuple[Any, ...]]:
    """The leader's request goes in flight first (its handler must set ``in_flight`` and hold on a
    Gate of one follower); then ``joined`` runs and the follower sends the identical request."""

    results: dict[str, tuple[Any, ...]] = {}
    thread = threading.Thread(target=lambda: results.update(leader=outcome(lambda: get(leader))))
    thread.start()
    assert IN_FLIGHT.wait(5)
    joined()
    results["follower"] = outcome(lambda: get(follower))
    thread.join(10)
    return results


IN_FLIGHT = threading.Event()
TIMED_OUT = ("error", "PROVIDER_DEGRADED", "Provider public request timed out.", "binance") + (
    None,
) * 5


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
    stats = [new_provider_stats() for _ in range(4)]

    def target(index: int) -> Any:
        CURRENT_PROVIDER_STATS.set(stats[index])
        return get(clients[index])

    results = run_together(4, target)
    assert results == [("ok", PAYLOAD)] * 4
    assert len(seen) == 1
    assert sorted(item["provider_coalesced"] for item in stats) == [0, 1, 1, 1]
    hits = [len(client._hits_by_host["data-api.binance.vision"]) for client in clients]
    assert hits == [1, 1, 1, 1], "a coalesced follower still spends its own rate-limit hit"


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


def _raise(failure: type[httpx.HTTPError]) -> Handler:
    def handler(request: httpx.Request) -> httpx.Response:
        raise failure("upstream failed", request=request)

    return handler


FAILURES: dict[str, Handler] = {
    "timeout": _raise(httpx.ReadTimeout),
    "transport": _raise(httpx.ConnectError),
    "oversized": lambda request: httpx.Response(200, content=b"[" + b"1," * 40 + b"1]"),
    "server error": lambda request: httpx.Response(503, json={"code": "busy"}),
    "rate limited": lambda request: httpx.Response(429, headers={"Retry-After": "3"}),
    "symbol rejected": lambda request: httpx.Response(404, json={"code": -1121}),
    "parameters rejected": lambda request: httpx.Response(400, json={"code": "P1"}),
    "malformed json": lambda request: httpx.Response(200, content=b"{not json"),
}


@pytest.mark.parametrize("name", sorted(FAILURES))
def test_no_failure_is_ever_shared(monkeypatch: pytest.MonkeyPatch, name: str) -> None:
    """Every follower of a failed exchange sends its own request and answers exactly as it would
    have alone; nothing it did not see itself is passed on."""

    failing = FAILURES[name]
    monkeypatch.setattr(http_client, "MAX_RESPONSE_BYTES", 64)
    gate = Gate(followers=2)
    gate.install(monkeypatch)
    first = threading.Event()

    def handler(request: httpx.Request) -> httpx.Response:
        if not first.is_set():
            first.set()
            gate.hold()
        return failing(request)

    seen = install(monkeypatch, handler)
    clients = [pooled() for _ in range(3)]
    stats = [new_provider_stats() for _ in range(3)]

    def target(index: int) -> Any:
        CURRENT_PROVIDER_STATS.set(stats[index])
        return get(clients[index])

    results = run_together(3, target)
    alone = outcome(lambda: get(injected(failing)))
    assert alone[0] == "error"
    assert results == [alone] * 3
    assert len(seen) == 3, "each follower sent its own request"
    assert [item["provider_coalesced"] for item in stats] == [0, 0, 0]


def test_a_follower_of_a_failure_keeps_its_own_attempts(monkeypatch: pytest.MonkeyPatch) -> None:
    gate = Gate(followers=1)
    gate.install(monkeypatch)
    failed = threading.Event()

    def handler(request: httpx.Request) -> httpx.Response:
        if not failed.is_set():
            failed.set()
            gate.hold()
            return httpx.Response(503, json={"code": "busy"})
        return ok_json()

    seen = install(monkeypatch, handler)
    clients = [pooled(max_retries=1), pooled(max_retries=1)]
    stats = [new_provider_stats(), new_provider_stats()]

    def target(index: int) -> Any:
        CURRENT_PROVIDER_STATS.set(stats[index])
        return get(clients[index])

    results = run_together(2, target)
    assert results == [("ok", PAYLOAD)] * 2
    # Whichever led met the 503 and retried; the follower's own request succeeded at once.
    hits = sorted(len(client._hits_by_host["data-api.binance.vision"]) for client in clients)
    assert hits == [1, 2], "each caller checked its own rate limit on each of its own attempts"
    assert sorted(item["provider_retries"] for item in stats) == [0, 1]
    assert [item["provider_coalesced"] for item in stats] == [0, 0]
    assert len(seen) == 3


def test_a_follower_sending_its_own_request_gets_a_fresh_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A venue that sets a cookie on every response and answers in six seconds; the follower joins
    one second later. Alone, each succeeds in six seconds; so must both here."""

    clock = FakeTime()
    monkeypatch.setattr(http_client, "time", clock)
    gate = Gate(followers=1)
    gate.install(monkeypatch)
    IN_FLIGHT.clear()

    def handler(request: httpx.Request) -> httpx.Response:
        if not IN_FLIGHT.is_set():
            IN_FLIGHT.set()
            gate.hold()
        clock.advance(6.0)
        return ok_json(headers={"Set-Cookie": "venue=a; Path=/"})

    seen = install(monkeypatch, handler)
    results = lead_then_follow(pooled(), pooled(), joined=lambda: clock.advance(1.0))
    assert results == {"leader": ("ok", PAYLOAD), "follower": ("ok", PAYLOAD)}
    assert len(seen) == 2


def test_the_first_requests_deadline_is_never_a_followers_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The first request trickles past its own deadline; the follower joined seven seconds in, and
    its own request is answered at once."""

    clock = FakeTime()
    monkeypatch.setattr(http_client, "time", clock)
    gate = Gate(followers=1)
    gate.install(monkeypatch)
    IN_FLIGHT.clear()
    stats = new_provider_stats()

    def handler(request: httpx.Request) -> httpx.Response:
        if not IN_FLIGHT.is_set():
            # In the first request's own thread and context, so its own counts land here.
            CURRENT_PROVIDER_STATS.set(stats)
            IN_FLIGHT.set()
            gate.hold()
            clock.advance(10.5)
        return ok_json()

    seen = install(monkeypatch, handler)
    results = lead_then_follow(pooled(), pooled(), joined=lambda: clock.advance(7.0))
    assert results == {"leader": TIMED_OUT, "follower": ("ok", PAYLOAD)}
    assert len(seen) == 2
    assert stats["provider_deadline_hits"] == 1, "the first request's deadline expiry is counted"


def test_a_follower_waits_no_longer_than_its_own_deadline(monkeypatch: pytest.MonkeyPatch) -> None:
    """The first request stalls until the follower is answered: the follower must stop waiting at
    its own deadline and answer with its own request."""

    monkeypatch.setattr(http_client, "REQUEST_DEADLINE_SECONDS", 0.3)
    IN_FLIGHT.clear()
    answered = threading.Event()
    order: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if not IN_FLIGHT.is_set():
            IN_FLIGHT.set()
            answered.wait(5)
            order.append("first")
            return ok_json()
        order.append("follower's own")
        answered.set()
        return ok_json()

    seen = install(monkeypatch, handler)
    results = lead_then_follow(pooled(), pooled(), joined=lambda: None)
    assert results["follower"] == ("ok", PAYLOAD)
    assert order == ["follower's own", "first"], "the follower stopped waiting at its own deadline"
    assert results["leader"] == TIMED_OUT, "the stalled request outlived its own deadline"
    assert len(seen) == 2


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


def test_the_slowest_exchange_is_the_one_kept(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = FakeTime()
    monkeypatch.setattr(http_client, "time", clock)
    answers = iter([(0.050, httpx.Response(500)), (0.005, ok_json())])

    def handler(request: httpx.Request) -> httpx.Response:
        seconds, response = next(answers)
        clock.advance(seconds)
        return response

    install(monkeypatch, handler)
    stats = new_provider_stats()
    token = CURRENT_PROVIDER_STATS.set(stats)
    try:
        assert get(pooled(max_retries=1)) == PAYLOAD
    finally:
        CURRENT_PROVIDER_STATS.reset(token)
    assert stats["provider_exchanges"] == 2
    assert stats["provider_exchange_max_ms"] == pytest.approx(50.0)


# --------------------------------------------------------------------------- proxies
@pytest.mark.parametrize(
    ("environment", "expected"),
    [
        ({}, None),
        ({"HTTPS_PROXY": "http://127.0.0.1:9"}, True),
        ({"ALL_PROXY": "http://127.0.0.1:9"}, True),
        ({"HTTP_PROXY": "http://127.0.0.1:9"}, True),
        ({"https_proxy": "http://127.0.0.1:9"}, True),
        ({"HTTPS_PROXY": "http://127.0.0.1:9", "NO_PROXY": "localhost"}, True),
        ({"HTTPS_PROXY": "http://127.0.0.1:9", "NO_PROXY": "*"}, False),
        ({"NO_PROXY": "example.com"}, False),
    ],
    ids=[
        "none",
        "https",
        "all",
        "http only",
        "lowercase",
        "a proxy and a no-proxy list",
        "no proxy at all",
        "no proxy for one host",
    ],
)
def test_the_pool_is_used_exactly_where_httpx_mounts_no_proxy(
    monkeypatch: pytest.MonkeyPatch, environment: dict[str, str], expected: bool | None
) -> None:
    for name in list(os.environ):
        if name.lower().endswith("_proxy"):
            monkeypatch.delenv(name)
    for name, value in environment.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(http_client, "_environment_proxies", REAL_ENVIRONMENT_PROXIES)
    original = httpx.Client(timeout=8.0)  # what the client built before this change
    client = pooled()
    try:
        proxied = any(transport is not None for transport in original._mounts.values())
        built = client._client()
        assert client._pooled is not proxied
        assert any(transport is not None for transport in built._mounts.values()) is proxied
        if expected is not None:  # "none" reads this machine's own system settings
            assert proxied is expected, "the case is what it says"
    finally:
        original.close()
        if client.client is not None:
            client.client.close()


def test_without_httpx_proxy_lookup_no_client_is_pooled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(http_client, "_environment_proxies", None)
    client = pooled()
    try:
        client._client()
        assert client._pooled is False
    finally:
        assert client.client is not None
        client.client.close()


# --------------------------------------------------------------------------- review 2 of 948edf75
class CountingJson:
    """json for the client under test: each loads costs the fake clock 30 ms, and is counted."""

    def __init__(self, clock: FakeTime) -> None:
        self.clock = clock
        self.loads_calls = 0
        self.lock = threading.Lock()

    def loads(self, body: bytes) -> Any:
        with self.lock:
            self.loads_calls += 1
        self.clock.advance(0.030)
        return json.loads(body)


def test_a_first_caller_parses_once_on_its_own_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    """A body done at 9.96 s with a 30 ms parse: alone it succeeds at 9.99 s, so pooled it must
    too. A second parse on the caller's clock would end it at 10.02 s, timed out."""

    clock = FakeTime()
    parser = CountingJson(clock)
    monkeypatch.setattr(http_client, "time", clock)
    monkeypatch.setattr(http_client, "json", parser)

    def handler(request: httpx.Request) -> httpx.Response:
        clock.advance(9.96)
        return ok_json()

    install(monkeypatch, handler)
    assert outcome(lambda: get(pooled(max_retries=1))) == ("ok", PAYLOAD)
    assert parser.loads_calls == 1


def test_each_follower_parses_its_own_copy_once(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = FakeTime()
    parser = CountingJson(clock)
    monkeypatch.setattr(http_client, "json", parser)
    gate = Gate(followers=2)
    gate.install(monkeypatch)

    def handler(request: httpx.Request) -> httpx.Response:
        gate.hold()
        return ok_json()

    seen = install(monkeypatch, handler)
    clients = [pooled() for _ in range(3)]
    results = run_together(3, lambda index: get(clients[index]))
    assert results == [("ok", PAYLOAD)] * 3 and len(seen) == 1
    assert parser.loads_calls == 3, "one parse per caller, the first caller's included"


def test_without_coalescing_identical_requests_make_their_own_exchange(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """F1's automated analysis turns coalescing off: it waits on no one, so two identical requests
    are both in flight at once (one exchange alone would break the barrier)."""

    arrived = threading.Barrier(2, timeout=5)

    def handler(request: httpx.Request) -> httpx.Response:
        arrived.wait()
        return ok_json()

    seen = install(monkeypatch, handler)
    clients = [pooled(), pooled()]

    def target(index: int) -> Any:
        http_client.PROVIDER_COALESCING.set(False)
        return get(clients[index])

    assert run_together(2, target) == [("ok", PAYLOAD)] * 2
    assert len(seen) == 2 and all(client._pooled for client in clients)


def test_a_response_over_the_bound_is_not_a_deadline_hit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(http_client, "MAX_RESPONSE_BYTES", 64)
    install(monkeypatch, FAILURES["oversized"])
    stats = new_provider_stats()
    token = CURRENT_PROVIDER_STATS.set(stats)
    try:
        assert outcome(lambda: get(pooled()))[2] == "Provider public request timed out."
    finally:
        CURRENT_PROVIDER_STATS.reset(token)
    assert stats["provider_deadline_hits"] == 0


class _TrackedStream(httpx.SyncByteStream):
    """A response body that records whether it was closed (so its connection went back)."""

    def __init__(self, body: bytes) -> None:
        self.body = body
        self.closed = False

    def __iter__(self) -> Iterator[bytes]:
        yield self.body

    def close(self) -> None:
        self.closed = True


@pytest.mark.parametrize(
    ("status", "body", "bound", "late", "raises"),
    [
        (200, json.dumps(PAYLOAD).encode(), None, False, None),
        (500, b'{"error": "upstream"}', None, False, None),
        (200, b"x" * 128, 64, False, http_client._ResponseBoundExceeded),  # noqa: SLF001
        (200, json.dumps(PAYLOAD).encode(), None, True, http_client._DeadlineExceeded),  # noqa: SLF001
    ],
    ids=["a success", "an error status", "a body over the bound", "a deadline hit mid-read"],
)
def test_every_streamed_response_is_closed(
    monkeypatch: pytest.MonkeyPatch,
    status: int,
    body: bytes,
    bound: int | None,
    late: bool,
    raises: type[BaseException] | None,
) -> None:
    """Review 3 of lane R (NIT, a test gap): _send streams each response over the process's shared
    pool, so a response it did not close would keep its connection out of the pool; enough of them
    would exhaust it. Every response is closed, however the read ends. (httpx closes a body read to
    its end by itself; the explicit close matters when the read is abandoned mid-stream, by the
    bound or by the deadline, which the last two cases pin.)"""

    if bound is not None:
        monkeypatch.setattr(http_client, "MAX_RESPONSE_BYTES", bound)
    stream = _TrackedStream(body)
    transport = httpx.MockTransport(lambda request: httpx.Response(status, stream=stream))
    with httpx.Client(transport=transport) as client:
        request = client.build_request("GET", BASE + PATH)
        started = http_client.time.monotonic()
        if late:  # the attempt began longer ago than the deadline: the first chunk trips it
            started -= http_client.REQUEST_DEADLINE_SECONDS + 1
        if raises is None:
            exchange = http_client._send(client, request, attempt_started=started)  # noqa: SLF001
            assert exchange.status_code == status
        else:
            with pytest.raises(raises):
                http_client._send(client, request, attempt_started=started)  # noqa: SLF001
    assert stream.closed, "the response's connection must go back to the pool"
