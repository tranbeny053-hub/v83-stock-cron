"""Endpoint-level OKX public SWAP derivatives adapter."""

from __future__ import annotations

from typing import Any

from crypto_probability_engine.adapters.derivatives.binance_usdm import (
    DEFAULT_MAX_RETRIES,
    DEFAULT_RATE_LIMIT_PER_MINUTE,
    DEFAULT_TIMEOUT_SECONDS,
    MAX_HISTORY_RANGE_MILLISECONDS,
)
from crypto_probability_engine.adapters.derivatives.errors import (
    PublicDerivativesAdapterError,
)
from crypto_probability_engine.adapters.derivatives_endpoints import (
    OKX_CURRENT_FUNDING_PATH,
    OKX_CURRENT_OPEN_INTEREST_PATH,
    OKX_FUNDING_HISTORY_PATH,
    OKX_INSTRUMENTS_PATH,
    OKX_PUBLIC_BASE_URL,
    DerivativesPublicHttpClient,
)
from crypto_probability_engine.adapters.http_client import PublicHttpClient
from crypto_probability_engine.adapters.types import ProviderError

OKX_FUNDING_HISTORY_MAX_LIMIT = 100


class OkxSwapDerivativesAdapter:
    """One-request methods for OKX public SWAP resources."""

    provider = "OKX_SWAP"

    def __init__(self, *, http_client: PublicHttpClient | None = None) -> None:
        self.http_client = http_client or DerivativesPublicHttpClient(
            timeout_seconds=DEFAULT_TIMEOUT_SECONDS,
            max_retries=DEFAULT_MAX_RETRIES,
            rate_limit_per_min=DEFAULT_RATE_LIMIT_PER_MINUTE,
        )

    def fetch_instruments(self) -> list[dict[str, Any]]:
        return self._get_data(OKX_INSTRUMENTS_PATH, {"instType": "SWAP"})

    def fetch_current_funding(self, inst_id: str) -> list[dict[str, Any]]:
        return self._get_data(
            OKX_CURRENT_FUNDING_PATH,
            {"instId": _required_inst_id(inst_id, self.provider, OKX_CURRENT_FUNDING_PATH)},
        )

    def fetch_funding_history(
        self,
        inst_id: str,
        *,
        start_time_ms: int,
        end_time_ms: int,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        _validate_limit(limit, self.provider, OKX_FUNDING_HISTORY_PATH)
        _validate_time_range(start_time_ms, end_time_ms, self.provider, OKX_FUNDING_HISTORY_PATH)
        return self._get_data(
            OKX_FUNDING_HISTORY_PATH,
            {
                "instId": _required_inst_id(inst_id, self.provider, OKX_FUNDING_HISTORY_PATH),
                "after": end_time_ms,
                "before": start_time_ms,
                "limit": limit,
            },
        )

    def fetch_current_open_interest(self, inst_id: str) -> list[dict[str, Any]]:
        return self._get_data(
            OKX_CURRENT_OPEN_INTEREST_PATH,
            {
                "instType": "SWAP",
                "instId": _required_inst_id(inst_id, self.provider, OKX_CURRENT_OPEN_INTEREST_PATH),
            },
        )

    def _get_data(self, path: str, params: dict[str, object]) -> list[dict[str, Any]]:
        try:
            payload = self.http_client.get_json(
                base_url=OKX_PUBLIC_BASE_URL,
                path=path,
                params=params,
                provider=self.provider,
            )
        except ProviderError as exc:
            raise PublicDerivativesAdapterError(
                "PUBLIC_REQUEST_FAILED",
                "OKX public SWAP request failed.",
                provider=self.provider,
                endpoint=path,
            ) from exc
        if (
            not isinstance(payload, dict)
            or payload.get("code") != "0"
            or not isinstance(payload.get("data"), list)
            or not all(isinstance(row, dict) for row in payload["data"])
        ):
            raise PublicDerivativesAdapterError(
                "MALFORMED_ENVELOPE",
                "OKX returned a malformed public payload.",
                provider=self.provider,
                endpoint=path,
            )
        return payload["data"]


def _required_inst_id(inst_id: str, provider: str, endpoint: str) -> str:
    value = str(inst_id).strip().upper()
    parts = value.split("-")
    if len(parts) != 3 or any(not part.isalnum() for part in parts):
        raise PublicDerivativesAdapterError(
            "INVALID_PARAMETER",
            "Instrument identifier is invalid.",
            provider=provider,
            endpoint=endpoint,
        )
    return value


def _validate_limit(limit: int, provider: str, endpoint: str) -> None:
    if (
        isinstance(limit, bool)
        or not isinstance(limit, int)
        or not 1 <= limit <= OKX_FUNDING_HISTORY_MAX_LIMIT
    ):
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
