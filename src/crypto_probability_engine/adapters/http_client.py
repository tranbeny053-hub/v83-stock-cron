"""Safe public HTTP client for keyless market-data providers.

Provider coalescing (governing plan §9.1; owner ruling DP-B as narrowed on 2026-10-05). Every
request, retry, error and freshness semantic of a client is exactly what it was. Two things change
underneath:
- **one connection pool per process.** A client that is not handed its own ``httpx.Client`` builds
  one as before (its own cookies, timeout and rate-limit history), on the process's one shared
  transport, so connections are reused across analyses. A client closing never closes the pool;
  the app closes it once, at shutdown (``close_pool``). Only where httpx would route no request
  through a proxy (none in the environment or the system settings): otherwise the client is built
  exactly as before, unpooled and uncoalesced, because httpx mounts proxies only on a transport it
  builds itself.
- **one exchange for identical in-flight requests (single-flight).** When such a client sends a
  request that is byte-identical to one already in flight (method, URL with its query, every header
  including any cookie, and the timeout), it waits for that exchange, for no longer than its own
  deadline, instead of sending its own. Only a success is shared: a response below 400, with a JSON
  body and no cookie. On any other outcome (an error status, a malformed body, a cookie, a timeout,
  a bound or deadline, a transport or unexpected failure), or no answer within its own deadline, the
  caller sends its own request, with its own fresh deadline, exactly as it would have alone; the
  wait is its only difference. No failure is ever passed on. Each caller still checks its own rate
  limit, makes its own attempts and maps its own outcome exactly as before.
No retry, retry policy, failure cache, data cache or freshness change is added. The only other
addition is passive measurement: counts and timings for the current analysis, in telemetry.
"""

from __future__ import annotations

import json
import threading
import time
from collections import defaultdict, deque
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx

try:  # How httpx.Client itself decides whether the environment routes a request through a proxy.
    from httpx._utils import get_environment_proxies as _environment_proxies
except ImportError:  # pragma: no cover - another httpx: never pool rather than guess
    _environment_proxies = None

from crypto_probability_engine.adapters.types import ProviderError
from crypto_probability_engine.config.settings import Settings
from crypto_probability_engine.telemetry.events import CURRENT_PROVIDER_STATS

MAX_RESPONSE_BYTES = 10 * 1024 * 1024
REQUEST_DEADLINE_SECONDS = 10.0

ALLOWED_PUBLIC_HOSTS = frozenset(
    {
        "data-api.binance.vision",
        "www.okx.com",
        "api.gdeltproject.org",
        "api.stlouisfed.org",
        "newsapi.org",
    }
)


@dataclass
class PublicHttpClient:
    """Small synchronous client with host allow-listing and bounded retries."""

    timeout_seconds: float
    max_retries: int
    rate_limit_per_min: int
    client: httpx.Client | None = None
    sleep_func: Callable[[float], None] = time.sleep
    _hits_by_host: dict[str, deque[float]] = field(default_factory=lambda: defaultdict(deque))
    # True once this client built its own httpx.Client on the shared pool (it was handed none).
    _pooled: bool = field(default=False, init=False, repr=False)

    @classmethod
    def from_settings(cls, settings: Settings) -> PublicHttpClient:
        return cls(
            timeout_seconds=settings.provider_timeout_seconds,
            max_retries=settings.provider_max_retries,
            rate_limit_per_min=settings.provider_rate_limit_per_min,
        )

    def get_json(
        self,
        *,
        base_url: str,
        path: str,
        params: Mapping[str, Any],
        provider: str,
        headers: Mapping[str, str] | None = None,
    ) -> Any:
        url = self._build_url(base_url, path)
        host = urlparse(url).netloc
        last_error: ProviderError | None = None
        for attempt in range(self.max_retries + 1):
            self._check_rate_limit(host, provider)
            if attempt:
                _measure_count("provider_retries")
            attempt_started = time.monotonic()
            try:
                # The start of the attempt this exchange answers: a caller that ends up sending its
                # own request after waiting gets a fresh one, exactly as if it had not waited.
                exchange, attempt_started = self._exchange(
                    url,
                    params=params,
                    headers=headers,
                    attempt_started=attempt_started,
                )
                if exchange.status_code in {400, 404} and provider not in {
                    "gdelt",
                    "fred",
                    "newsapi",
                }:
                    raise ProviderError(
                        "INVALID_SYMBOL",
                        "Provider rejected symbol.",
                        provider=provider,
                        http_status=exchange.status_code,
                        error_code="INVALID_SYMBOL",
                        error_type="REQUEST",
                        operation=f"GET {path}",
                    )
                if exchange.status_code >= 400:
                    last_error = _provider_error_from_exchange(
                        exchange,
                        provider=provider,
                        operation=f"GET {path}",
                    )
                    _raise_if_deadline_exceeded(attempt_started)
                    if attempt >= self.max_retries:
                        raise last_error
                else:
                    try:
                        payload = json.loads(exchange.body)
                    except ValueError as exc:
                        _raise_if_deadline_exceeded(attempt_started)
                        raise ProviderError(
                            "SCHEMA_VALIDATION_FAILED",
                            "Provider returned malformed JSON.",
                            provider=provider,
                            http_status=exchange.status_code,
                            error_code="MALFORMED_JSON",
                            error_type="SCHEMA",
                            operation=f"GET {path}",
                        ) from exc
                    _raise_if_deadline_exceeded(attempt_started)
                    return payload
            except (httpx.TimeoutException, _ResponseBoundExceeded) as exc:
                if isinstance(exc, httpx.TimeoutException | _DeadlineExceeded):
                    _measure_count("provider_deadline_hits")
                last_error = ProviderError(
                    "PROVIDER_DEGRADED",
                    "Provider public request timed out.",
                    provider=provider,
                )
                if attempt >= self.max_retries:
                    raise last_error from exc
            except httpx.HTTPError as exc:
                last_error = ProviderError(
                    "PROVIDER_DEGRADED",
                    "Provider public request failed.",
                    provider=provider,
                )
                if attempt >= self.max_retries:
                    raise last_error from exc
            self.sleep_func(0.25 * (attempt + 1))
        if last_error is not None:
            raise last_error
        raise ProviderError(
            "PROVIDER_DEGRADED",
            "Provider public request failed.",
            provider=provider,
        )

    def _exchange(
        self,
        url: str,
        *,
        params: Mapping[str, Any],
        headers: Mapping[str, str] | None,
        attempt_started: float,
    ) -> tuple[_Exchange, float]:
        """One request and its whole bounded body, exactly as ``httpx.Client.stream`` sends it, and
        the start of the attempt it answers; on the shared pool, one successful exchange serves
        every identical request in flight."""

        client = self._client()
        request = client.build_request(
            "GET",
            url,
            params=dict(params),
            headers=dict(headers or {}),
            timeout=min(self.timeout_seconds, REQUEST_DEADLINE_SECONDS),
        )

        def send(started: float) -> _Exchange:
            return _send(client, request, attempt_started=started)

        measured = time.perf_counter()
        try:
            if not self._pooled:
                return send(attempt_started), attempt_started
            return _SINGLE_FLIGHT.run(_request_identity(request), send, attempt_started)
        finally:
            _measure_exchange((time.perf_counter() - measured) * 1000)

    def _client(self) -> httpx.Client:
        if self.client is None:
            if _environment_routes_through_a_proxy():
                # Exactly the original client: httpx mounts the environment's proxies only on a
                # transport it builds itself.
                self.client = httpx.Client(timeout=self.timeout_seconds)
            else:
                self.client = httpx.Client(
                    timeout=self.timeout_seconds, transport=pooled_transport()
                )
                self._pooled = True
        return self.client

    def _build_url(self, base_url: str, path: str) -> str:
        parsed_base = urlparse(base_url)
        if parsed_base.scheme != "https" or parsed_base.netloc not in ALLOWED_PUBLIC_HOSTS:
            raise ProviderError(
                "PROVIDER_DEGRADED",
                "Provider host is not allow-listed.",
                provider="http_client",
            )
        if not path.startswith("/") or "://" in path:
            raise ProviderError(
                "PROVIDER_DEGRADED",
                "Provider path is invalid.",
                provider="http_client",
            )
        url = urljoin(base_url, path)
        if urlparse(url).netloc not in ALLOWED_PUBLIC_HOSTS:
            raise ProviderError(
                "PROVIDER_DEGRADED",
                "Provider URL escaped the allow-list.",
                provider="http_client",
            )
        return url

    def _check_rate_limit(self, host: str, provider: str) -> None:
        if self.rate_limit_per_min <= 0:
            raise ProviderError(
                "PROVIDER_DEGRADED",
                "Local provider rate limit disabled.",
                provider=provider,
            )
        now = time.monotonic()
        hits = self._hits_by_host[host]
        cutoff = now - 60.0
        while hits and hits[0] < cutoff:
            hits.popleft()
        if len(hits) >= self.rate_limit_per_min:
            raise ProviderError(
                "PROVIDER_DEGRADED",
                "Local provider rate limit exceeded.",
                provider=provider,
            )
        hits.append(now)


@dataclass(frozen=True)
class _Exchange:
    """What a caller reads from one response: its status, its Retry-After and its bounded body."""

    status_code: int
    retry_after: str | None
    body: bytes
    sets_cookie: bool


def _send(client: httpx.Client, request: httpx.Request, *, attempt_started: float) -> _Exchange:
    response = client.send(request, stream=True)
    try:
        body = _read_bounded_body(response, attempt_started=attempt_started)
        return _Exchange(
            status_code=response.status_code,
            retry_after=response.headers.get("Retry-After"),
            body=body,
            sets_cookie="set-cookie" in response.headers,
        )
    finally:
        response.close()


def _request_identity(request: httpx.Request) -> tuple[object, ...]:
    """Everything that makes two requests the same request: method, URL with its query, every
    header in order (the cookie included) and the timeout."""

    timeout = request.extensions.get("timeout") or {}
    return (
        request.method,
        str(request.url),
        tuple(request.headers.raw),
        tuple(sorted(timeout.items())),
    )


class _PooledTransport(httpx.BaseTransport):
    """The process's one connection pool. A client that closes it leaves the pool open."""

    def __init__(self, inner: httpx.BaseTransport) -> None:
        self.inner = inner

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        return self.inner.handle_request(request)

    def close(self) -> None:
        return None


def _environment_routes_through_a_proxy() -> bool:
    """True when an httpx.Client built with no transport would mount a proxy (from HTTP_PROXY,
    HTTPS_PROXY, ALL_PROXY or the system settings, unless NO_PROXY is "*")."""

    if _environment_proxies is None:
        return True
    return any(url is not None for url in _environment_proxies().values())


# httpx.HTTPTransport() is exactly the transport an httpx.Client builds by default, when the
# environment mounts no proxy.
_POOL_FACTORY: Callable[[], httpx.BaseTransport] = httpx.HTTPTransport
_POOL_LOCK = threading.Lock()
_POOL: _PooledTransport | None = None


def pooled_transport() -> _PooledTransport:
    global _POOL
    with _POOL_LOCK:
        if _POOL is None:
            _POOL = _PooledTransport(_POOL_FACTORY())
        return _POOL


def close_pool() -> None:
    """Close the shared pool (once, at app shutdown); the next pooled client opens a new one."""

    global _POOL
    with _POOL_LOCK:
        pool, _POOL = _POOL, None
    if pool is not None:
        pool.inner.close()


class _Call:
    def __init__(self) -> None:
        self.done = threading.Event()
        self.exchange: _Exchange | None = None  # set only for a success that can be shared


class _SingleFlight:
    """One exchange for identical requests in flight. The first caller sends; the others wait, for
    no longer than their own deadline, and read its outcome only when it is a success that can be
    shared. Otherwise each sends its own request, with its own fresh deadline."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._calls: dict[tuple[object, ...], _Call] = {}

    def run(
        self,
        key: tuple[object, ...],
        send: Callable[[float], _Exchange],
        attempt_started: float,
    ) -> tuple[_Exchange, float]:
        with self._lock:
            call = self._calls.get(key)
            leader = call is None
            if leader:
                call = self._calls[key] = _Call()
        if leader:
            return self._lead(key, call, send, attempt_started), attempt_started
        remaining = REQUEST_DEADLINE_SECONDS - (time.monotonic() - attempt_started)
        if call.done.wait(max(0.0, remaining)) and call.exchange is not None:
            _measure_count("provider_coalesced")
            return call.exchange, attempt_started
        own_start = time.monotonic()
        return send(own_start), own_start

    def _lead(
        self,
        key: tuple[object, ...],
        call: _Call,
        send: Callable[[float], _Exchange],
        attempt_started: float,
    ) -> _Exchange:
        try:
            exchange = send(attempt_started)
            if _shareable(exchange):
                call.exchange = exchange
            return exchange
        finally:
            with self._lock:
                del self._calls[key]
            call.done.set()


def _shareable(exchange: _Exchange) -> bool:
    """A success the caller's own request would have read as one: a status below 400, a JSON body
    and no cookie. Any other outcome is each caller's own to meet with its own request."""

    if exchange.sets_cookie or exchange.status_code >= 400:
        return False
    try:
        json.loads(exchange.body)
    except ValueError:
        return False
    return True


_SINGLE_FLIGHT = _SingleFlight()


def _provider_error_from_exchange(
    exchange: _Exchange,
    *,
    provider: str,
    operation: str,
) -> ProviderError:
    status = exchange.status_code
    provider_code = _extract_provider_error_code(exchange.body)
    if status in {418, 429}:
        return ProviderError(
            "PROVIDER_DEGRADED",
            "Provider rate limited the public request.",
            provider=provider,
            http_status=status,
            error_code=provider_code or "RATE_LIMITED",
            error_type="RATE_LIMIT",
            retry_after_seconds=_retry_after_seconds(exchange.retry_after),
            operation=operation,
        )
    if status in {401, 403}:
        return ProviderError(
            "PROVIDER_DEGRADED",
            "Provider authentication failed.",
            provider=provider,
            http_status=status,
            error_code=provider_code or "AUTH_FAILED",
            error_type="AUTH",
            operation=operation,
        )
    if status == 400:
        return ProviderError(
            "PROVIDER_DEGRADED",
            "Provider rejected request parameters.",
            provider=provider,
            http_status=status,
            error_code=provider_code or "PARAMETER_INVALID",
            error_type="REQUEST",
            operation=operation,
        )
    return ProviderError(
        "PROVIDER_DEGRADED",
        f"Provider public request failed: HTTP {status}.",
        provider=provider,
        http_status=status,
        error_code=provider_code or "HTTP_ERROR",
        error_type="PROVIDER",
        operation=operation,
    )


def _extract_provider_error_code(body: bytes) -> str | None:
    try:
        payload = json.loads(body)
    except ValueError:
        return None
    if not isinstance(payload, dict):
        return None
    code = payload.get("code")
    if isinstance(code, str) and code.strip():
        return code.strip()
    return None


class _ResponseBoundExceeded(Exception):
    pass


class _DeadlineExceeded(_ResponseBoundExceeded):
    """The per-attempt deadline passed: handled exactly as any bound, and counted as a deadline."""


def _read_bounded_body(response: httpx.Response, *, attempt_started: float) -> bytes:
    body = bytearray()
    for chunk in response.iter_bytes():
        if len(body) + len(chunk) > MAX_RESPONSE_BYTES:
            raise _ResponseBoundExceeded
        body.extend(chunk)
        _raise_if_deadline_exceeded(attempt_started)
    return bytes(body)


def _raise_if_deadline_exceeded(attempt_started: float) -> None:
    if time.monotonic() - attempt_started > REQUEST_DEADLINE_SECONDS:
        raise _DeadlineExceeded


def _retry_after_seconds(raw: str | None) -> float | None:
    if raw is None:
        return None
    try:
        return max(0.0, float(raw))
    except ValueError:
        return None


def _measure_count(name: str) -> None:
    """Passive measurement for the current analysis's telemetry; never raises, changes nothing."""

    try:
        stats = CURRENT_PROVIDER_STATS.get()
        if stats is not None:
            stats[name] = stats.get(name, 0) + 1
    except Exception:
        return


def _measure_exchange(duration_ms: float) -> None:
    try:
        stats = CURRENT_PROVIDER_STATS.get()
        if stats is not None:
            stats["provider_exchanges"] = stats.get("provider_exchanges", 0) + 1
            stats["provider_exchange_max_ms"] = max(
                float(stats.get("provider_exchange_max_ms", 0.0)), duration_ms
            )
    except Exception:
        return
