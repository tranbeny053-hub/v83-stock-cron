"""Endpoint-level Binance USD-M public derivatives adapter."""

from __future__ import annotations

from typing import Any

from crypto_probability_engine.adapters.derivatives.errors import (
    PublicDerivativesAdapterError,
)
from crypto_probability_engine.adapters.derivatives_endpoints import (
    BINANCE_CURRENT_FUNDING_PATH,
    BINANCE_CURRENT_OPEN_INTEREST_PATH,
    BINANCE_EXCHANGE_INFO_PATH,
    BINANCE_FUNDING_HISTORY_PATH,
    BINANCE_FUNDING_INFO_PATH,
    BINANCE_OPEN_INTEREST_HISTORY_PATH,
    BINANCE_USDM_BASE_URL,
    DerivativesPublicHttpClient,
)
from crypto_probability_engine.adapters.http_client import PublicHttpClient
from crypto_probability_engine.adapters.types import ProviderError

BINANCE_FUNDING_HISTORY_MAX_LIMIT = 1000
BINANCE_OPEN_INTEREST_HISTORY_MAX_LIMIT = 500
MAX_HISTORY_RANGE_MILLISECONDS = 31 * 24 * 60 * 60 * 1000
BINANCE_OPEN_INTEREST_PERIODS = frozenset({"5m", "15m", "30m", "1h", "2h", "4h", "6h", "12h", "1d"})
DEFAULT_TIMEOUT_SECONDS = 10.0
DEFAULT_MAX_RETRIES = 2
DEFAULT_RATE_LIMIT_PER_MINUTE = 120


class BinanceUsdmDerivativesAdapter:
    """One-request methods for Binance USD-M public resources."""

    provider = "BINANCE_USDM"

    def __init__(self, *, http_client: PublicHttpClient | None = None) -> None:
        self.http_client = http_client or DerivativesPublicHttpClient(
            timeout_seconds=DEFAULT_TIMEOUT_SECONDS,
            max_retries=DEFAULT_MAX_RETRIES,
            rate_limit_per_min=DEFAULT_RATE_LIMIT_PER_MINUTE,
        )

    def fetch_exchange_info(self) -> dict[str, Any]:
        payload = self._get(BINANCE_EXCHANGE_INFO_PATH, {})
        if not isinstance(payload, dict) or not isinstance(payload.get("symbols"), list):
            self._malformed(BINANCE_EXCHANGE_INFO_PATH)
        return payload

    def fetch_current_funding(self, symbol: str) -> dict[str, Any]:
        payload = self._get(
            BINANCE_CURRENT_FUNDING_PATH,
            {"symbol": _required_symbol(symbol, self.provider, BINANCE_CURRENT_FUNDING_PATH)},
        )
        if not isinstance(payload, dict):
            self._malformed(BINANCE_CURRENT_FUNDING_PATH)
        return payload

    def fetch_funding_history(
        self,
        symbol: str,
        *,
        start_time_ms: int,
        end_time_ms: int,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        _validate_limit(
            limit, BINANCE_FUNDING_HISTORY_MAX_LIMIT, self.provider, BINANCE_FUNDING_HISTORY_PATH
        )
        _validate_time_range(
            start_time_ms, end_time_ms, self.provider, BINANCE_FUNDING_HISTORY_PATH
        )
        payload = self._get(
            BINANCE_FUNDING_HISTORY_PATH,
            {
                "symbol": _required_symbol(symbol, self.provider, BINANCE_FUNDING_HISTORY_PATH),
                "startTime": start_time_ms,
                "endTime": end_time_ms,
                "limit": limit,
            },
        )
        if not isinstance(payload, list) or not all(isinstance(row, dict) for row in payload):
            self._malformed(BINANCE_FUNDING_HISTORY_PATH)
        return payload

    def fetch_funding_info(self) -> list[dict[str, Any]]:
        payload = self._get(BINANCE_FUNDING_INFO_PATH, {})
        if not isinstance(payload, list) or not all(isinstance(row, dict) for row in payload):
            self._malformed(BINANCE_FUNDING_INFO_PATH)
        return payload

    def fetch_current_open_interest(self, symbol: str) -> dict[str, Any]:
        payload = self._get(
            BINANCE_CURRENT_OPEN_INTEREST_PATH,
            {"symbol": _required_symbol(symbol, self.provider, BINANCE_CURRENT_OPEN_INTEREST_PATH)},
        )
        if not isinstance(payload, dict):
            self._malformed(BINANCE_CURRENT_OPEN_INTEREST_PATH)
        return payload

    def fetch_open_interest_history(
        self,
        symbol: str,
        *,
        period: str,
        start_time_ms: int,
        end_time_ms: int,
        limit: int = 30,
    ) -> list[dict[str, Any]]:
        if period not in BINANCE_OPEN_INTEREST_PERIODS:
            raise PublicDerivativesAdapterError(
                "INVALID_PARAMETER",
                "Unsupported open-interest period.",
                provider=self.provider,
                endpoint=BINANCE_OPEN_INTEREST_HISTORY_PATH,
            )
        _validate_limit(
            limit,
            BINANCE_OPEN_INTEREST_HISTORY_MAX_LIMIT,
            self.provider,
            BINANCE_OPEN_INTEREST_HISTORY_PATH,
        )
        _validate_time_range(
            start_time_ms,
            end_time_ms,
            self.provider,
            BINANCE_OPEN_INTEREST_HISTORY_PATH,
        )
        payload = self._get(
            BINANCE_OPEN_INTEREST_HISTORY_PATH,
            {
                "symbol": _required_symbol(
                    symbol, self.provider, BINANCE_OPEN_INTEREST_HISTORY_PATH
                ),
                "period": period,
                "startTime": start_time_ms,
                "endTime": end_time_ms,
                "limit": limit,
            },
        )
        if not isinstance(payload, list) or not all(isinstance(row, dict) for row in payload):
            self._malformed(BINANCE_OPEN_INTEREST_HISTORY_PATH)
        return payload

    def _get(self, path: str, params: dict[str, object]) -> Any:
        try:
            return self.http_client.get_json(
                base_url=BINANCE_USDM_BASE_URL,
                path=path,
                params=params,
                provider=self.provider,
            )
        except ProviderError as exc:
            raise PublicDerivativesAdapterError(
                "PUBLIC_REQUEST_FAILED",
                "Binance USD-M public request failed.",
                provider=self.provider,
                endpoint=path,
            ) from exc

    def _malformed(self, path: str) -> None:
        raise PublicDerivativesAdapterError(
            "MALFORMED_ENVELOPE",
            "Binance USD-M returned a malformed public payload.",
            provider=self.provider,
            endpoint=path,
        )


def _required_symbol(symbol: str, provider: str, endpoint: str) -> str:
    value = str(symbol).strip().upper()
    if not value or not value.isalnum():
        raise PublicDerivativesAdapterError(
            "INVALID_PARAMETER", "Symbol is invalid.", provider=provider, endpoint=endpoint
        )
    return value


def _validate_limit(limit: int, maximum: int, provider: str, endpoint: str) -> None:
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= maximum:
        raise PublicDerivativesAdapterError(
            "INVALID_PARAMETER",
            "History limit is outside the bounded range.",
            provider=provider,
            endpoint=endpoint,
        )


def _validate_time_range(start_ms: int, end_ms: int, provider: str, endpoint: str) -> None:
    valid_ints = all(
        isinstance(value, int) and not isinstance(value, bool) for value in (start_ms, end_ms)
    )
    if (
        not valid_ints
        or start_ms < 0
        or end_ms <= start_ms
        or end_ms - start_ms > MAX_HISTORY_RANGE_MILLISECONDS
    ):
        raise PublicDerivativesAdapterError(
            "INVALID_PARAMETER",
            "History time range is invalid or exceeds the bounded window.",
            provider=provider,
            endpoint=endpoint,
        )
