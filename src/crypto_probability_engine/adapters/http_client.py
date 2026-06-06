"""Safe public HTTP client for keyless market-data providers."""

from __future__ import annotations

import time
from collections import defaultdict, deque
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx

from crypto_probability_engine.adapters.types import ProviderError
from crypto_probability_engine.config.settings import Settings

ALLOWED_PUBLIC_HOSTS = frozenset({"data-api.binance.vision", "www.okx.com"})


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
    ) -> Any:
        url = self._build_url(base_url, path)
        host = urlparse(url).netloc
        last_error: ProviderError | None = None
        for attempt in range(self.max_retries + 1):
            self._check_rate_limit(host, provider)
            try:
                response = self._client().get(url, params=dict(params))
            except httpx.TimeoutException as exc:
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
            else:
                if response.status_code in {400, 404}:
                    raise ProviderError(
                        "INVALID_SYMBOL",
                        "Provider rejected symbol.",
                        provider=provider,
                    )
                if response.status_code in {418, 429} or response.status_code >= 500:
                    last_error = ProviderError(
                        "PROVIDER_DEGRADED",
                        f"Provider throttled or degraded: HTTP {response.status_code}.",
                        provider=provider,
                    )
                    if attempt >= self.max_retries:
                        raise last_error
                elif response.status_code >= 400:
                    raise ProviderError(
                        "PROVIDER_DEGRADED",
                        f"Provider public request failed: HTTP {response.status_code}.",
                        provider=provider,
                    )
                else:
                    try:
                        return response.json()
                    except ValueError as exc:
                        raise ProviderError(
                            "SCHEMA_VALIDATION_FAILED",
                            "Provider returned malformed JSON.",
                            provider=provider,
                        ) from exc
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
