"""Safe public HTTP client for keyless market-data providers."""

from __future__ import annotations

import json
import time
from collections import defaultdict, deque
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx

from crypto_probability_engine.adapters.types import ProviderError
from crypto_probability_engine.config.settings import Settings

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
            attempt_started = time.monotonic()
            try:
                with self._client().stream(
                    "GET",
                    url,
                    params=dict(params),
                    headers=dict(headers or {}),
                    timeout=min(self.timeout_seconds, REQUEST_DEADLINE_SECONDS),
                ) as response:
                    body = _read_bounded_body(response, attempt_started=attempt_started)
                    if response.status_code in {400, 404} and provider not in {
                        "gdelt",
                        "fred",
                        "newsapi",
                    }:
                        raise ProviderError(
                            "INVALID_SYMBOL",
                            "Provider rejected symbol.",
                            provider=provider,
                            http_status=response.status_code,
                            error_code="INVALID_SYMBOL",
                            error_type="REQUEST",
                            operation=f"GET {path}",
                        )
                    if response.status_code >= 400:
                        last_error = _provider_error_from_response(
                            response,
                            body=body,
                            provider=provider,
                            operation=f"GET {path}",
                        )
                        _raise_if_deadline_exceeded(attempt_started)
                        if attempt >= self.max_retries:
                            raise last_error
                    else:
                        try:
                            payload = json.loads(body)
                        except ValueError as exc:
                            _raise_if_deadline_exceeded(attempt_started)
                            raise ProviderError(
                                "SCHEMA_VALIDATION_FAILED",
                                "Provider returned malformed JSON.",
                                provider=provider,
                                http_status=response.status_code,
                                error_code="MALFORMED_JSON",
                                error_type="SCHEMA",
                                operation=f"GET {path}",
                            ) from exc
                        _raise_if_deadline_exceeded(attempt_started)
                        return payload
            except (httpx.TimeoutException, _ResponseBoundExceeded) as exc:
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

    def _client(self) -> httpx.Client:
        if self.client is None:
            self.client = httpx.Client(timeout=self.timeout_seconds)
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


def _provider_error_from_response(
    response: httpx.Response,
    *,
    body: bytes,
    provider: str,
    operation: str,
) -> ProviderError:
    status = response.status_code
    provider_code = _extract_provider_error_code(body)
    if status in {418, 429}:
        return ProviderError(
            "PROVIDER_DEGRADED",
            "Provider rate limited the public request.",
            provider=provider,
            http_status=status,
            error_code=provider_code or "RATE_LIMITED",
            error_type="RATE_LIMIT",
            retry_after_seconds=_retry_after_seconds(response),
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
        raise _ResponseBoundExceeded


def _retry_after_seconds(response: httpx.Response) -> float | None:
    raw = response.headers.get("Retry-After")
    if raw is None:
        return None
    try:
        return max(0.0, float(raw))
    except ValueError:
        return None
