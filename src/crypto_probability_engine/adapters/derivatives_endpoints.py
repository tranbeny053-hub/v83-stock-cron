"""Verified public endpoint constants for derivatives adapter fixtures."""

from __future__ import annotations

from urllib.parse import urljoin, urlparse

from crypto_probability_engine.adapters.http_client import PublicHttpClient
from crypto_probability_engine.adapters.types import ProviderError

BINANCE_USDM_BASE_URL = "https://fapi.binance.com"
OKX_PUBLIC_BASE_URL = "https://www.okx.com"

BINANCE_EXCHANGE_INFO_PATH = "/fapi/v1/exchangeInfo"
BINANCE_CURRENT_FUNDING_PATH = "/fapi/v1/premiumIndex"
BINANCE_FUNDING_HISTORY_PATH = "/fapi/v1/fundingRate"
BINANCE_FUNDING_INFO_PATH = "/fapi/v1/fundingInfo"
BINANCE_CURRENT_OPEN_INTEREST_PATH = "/fapi/v1/openInterest"
BINANCE_OPEN_INTEREST_HISTORY_PATH = "/futures/data/openInterestHist"

OKX_INSTRUMENTS_PATH = "/api/v5/public/instruments"
OKX_CURRENT_FUNDING_PATH = "/api/v5/public/funding-rate"
OKX_FUNDING_HISTORY_PATH = "/api/v5/public/funding-rate-history"
OKX_CURRENT_OPEN_INTEREST_PATH = "/api/v5/public/open-interest"

DERIVATIVES_PUBLIC_HOSTS = frozenset({"fapi.binance.com", "www.okx.com"})


class DerivativesPublicHttpClient(PublicHttpClient):
    """Bounded public client restricted to the two approved derivatives hosts."""

    def _build_url(self, base_url: str, path: str) -> str:
        parsed_base = urlparse(base_url)
        if parsed_base.scheme != "https" or parsed_base.netloc not in DERIVATIVES_PUBLIC_HOSTS:
            raise ProviderError(
                "PROVIDER_DEGRADED",
                "Derivatives provider host is not allow-listed.",
                provider="derivatives_http_client",
            )
        if not path.startswith("/") or "://" in path:
            raise ProviderError(
                "PROVIDER_DEGRADED",
                "Derivatives provider path is invalid.",
                provider="derivatives_http_client",
            )
        url = urljoin(base_url, path)
        if urlparse(url).netloc not in DERIVATIVES_PUBLIC_HOSTS:
            raise ProviderError(
                "PROVIDER_DEGRADED",
                "Derivatives provider URL escaped the allow-list.",
                provider="derivatives_http_client",
            )
        return url
