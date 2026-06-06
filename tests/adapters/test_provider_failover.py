from __future__ import annotations

import pytest

from crypto_probability_engine.adapters.public_market import FixturePublicAdapter, ProviderRouter
from crypto_probability_engine.adapters.types import ProviderError
from crypto_probability_engine.normalizers.symbols import normalize_symbol
from tests.fixtures.market_data import make_snapshot


def test_router_uses_valid_provider_and_quarantines_failed_provider() -> None:
    symbol = normalize_symbol("BTC")
    snapshot = make_snapshot(provider="okx")
    router = ProviderRouter(
        [
            FixturePublicAdapter("binance", {}, fail_code="PROVIDER_DEGRADED"),
            FixturePublicAdapter("okx", {(symbol.display, "4H"): snapshot}),
        ]
    )

    result = router.fetch_first_valid(symbol, "4H")
    state = router.public_state()

    assert result.provider == "okx"
    assert state["status"] == "OK"
    assert state["active_provider"] == "okx"
    assert state["providers"]["binance"]["status"] == "QUARANTINED"


def test_router_fails_closed_when_all_providers_fail() -> None:
    symbol = normalize_symbol("BTC")
    router = ProviderRouter(
        [
            FixturePublicAdapter("binance", {}, fail_code="PROVIDER_DEGRADED"),
            FixturePublicAdapter("okx", {}, fail_code="PROVIDER_DEGRADED"),
        ]
    )

    with pytest.raises(ProviderError) as excinfo:
        router.fetch_first_valid(symbol, "4H")
    assert excinfo.value.code == "PROVIDER_DEGRADED"

