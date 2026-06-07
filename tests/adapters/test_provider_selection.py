from __future__ import annotations

import pytest

from crypto_probability_engine.adapters.provider_selection import (
    ProviderSelectionError,
    clear_provider_cache,
    select_market_data,
)
from crypto_probability_engine.adapters.types import MarketSnapshot, ProviderError
from crypto_probability_engine.config.settings import Settings
from crypto_probability_engine.normalizers.symbols import normalize_symbol
from tests.fixtures.market_data import make_snapshot


class FakeAdapter:
    def __init__(
        self,
        name: str,
        snapshot: MarketSnapshot | None = None,
        *,
        fail_code: str | None = None,
    ) -> None:
        self.name = name
        self.snapshot = snapshot
        self.fail_code = fail_code
        self.calls = 0

    def fetch_market_snapshot(self, symbol, timeframe: str) -> MarketSnapshot:
        self.calls += 1
        if self.fail_code:
            raise ProviderError(self.fail_code, "fake provider failure", provider=self.name)
        assert self.snapshot is not None
        return self.snapshot


def live_settings(
    *,
    priority: tuple[str, ...] = ("binance", "okx"),
    cross_provider_required: bool = False,
) -> Settings:
    return Settings(
        data_mode="live",
        provider_priority=priority,
        candle_cache_ttl_seconds=0,
        cross_provider_required=cross_provider_required,
    )


def test_both_providers_ok_returns_cross_provider_live() -> None:
    symbol = normalize_symbol("BTC")
    result = select_market_data(
        symbol,
        "4H",
        settings=live_settings(),
        providers=[
            FakeAdapter("binance", make_snapshot(provider="binance")),
            FakeAdapter("okx", make_snapshot(provider="okx")),
        ],
    )

    assert result.snapshot.provider == "binance"
    assert result.data_quality["data_source"] == "CROSS_PROVIDER"
    assert result.data_quality["is_live_data"] is True
    assert result.provider_state["active_provider"] == "cross_provider"
    assert result.provider_state["cross_provider_state"] == "COHERENT"
    assert result.provider_state["fallback_to_single_provider"] is False


def test_single_provider_ok_returns_live_with_warning() -> None:
    symbol = normalize_symbol("BTC")
    result = select_market_data(
        symbol,
        "4H",
        settings=live_settings(),
        providers=[
            FakeAdapter("binance", make_snapshot(provider="binance")),
            FakeAdapter("okx", fail_code="PROVIDER_DEGRADED"),
        ],
    )

    assert result.data_quality["data_source"] == "BINANCE_PUBLIC"
    assert result.data_quality["is_live_data"] is True
    assert "single-source" in result.data_quality["warnings"][0]
    assert "okx" in result.data_quality["provider_failures"]


def test_both_providers_fail_returns_unavailable_without_fixture() -> None:
    symbol = normalize_symbol("BTC")
    with pytest.raises(ProviderSelectionError) as excinfo:
        select_market_data(
            symbol,
            "4H",
            settings=live_settings(),
            providers=[
                FakeAdapter("binance", fail_code="PROVIDER_DEGRADED"),
                FakeAdapter("okx", fail_code="PROVIDER_DEGRADED"),
            ],
        )

    assert excinfo.value.data_quality["data_source"] == "UNAVAILABLE"
    assert excinfo.value.data_quality["is_live_data"] is False
    assert "FIXTURE_DEMO" not in str(excinfo.value.data_quality)


def test_provider_disagreement_uses_single_live_provider_when_optional() -> None:
    symbol = normalize_symbol("BTC")
    result = select_market_data(
        symbol,
        "4H",
        settings=live_settings(cross_provider_required=False),
        providers=[
            FakeAdapter("binance", make_snapshot(provider="binance")),
            FakeAdapter("okx", make_snapshot(provider="okx", close_shift=10.0)),
        ],
    )

    assert result.snapshot.provider == "binance"
    assert result.data_quality["data_source"] == "BINANCE_PUBLIC"
    assert result.data_quality["is_live_data"] is True
    assert result.data_quality["cross_provider_state"] == "DATA_CONFLICT"
    assert result.data_quality["fallback_to_single_provider"] is True
    assert result.provider_state["status"] == "DEGRADED"
    assert result.provider_state["active_provider"] == "binance"
    assert result.provider_state["fallback_to_single_provider"] is True
    assert "cross-provider confirmation is optional" in result.data_quality["warnings"][0]


def test_provider_disagreement_blocks_when_cross_provider_required() -> None:
    symbol = normalize_symbol("BTC")
    with pytest.raises(ProviderSelectionError) as excinfo:
        select_market_data(
            symbol,
            "4H",
            settings=live_settings(cross_provider_required=True),
            providers=[
                FakeAdapter("binance", make_snapshot(provider="binance")),
                FakeAdapter("okx", make_snapshot(provider="okx", close_shift=10.0)),
            ],
        )

    assert excinfo.value.code.value == "DATA_CONFLICT"
    assert excinfo.value.data_quality["data_source"] == "DEGRADED"
    assert excinfo.value.data_quality["is_live_data"] is False
    assert excinfo.value.provider_state["fallback_to_single_provider"] is False


def test_fixture_mode_is_explicit_and_marked_demo() -> None:
    result = select_market_data(
        normalize_symbol("BTC"),
        "4H",
        settings=Settings(data_mode="fixture"),
    )

    assert result.snapshot.provider == "fixture"
    assert result.data_quality["data_source"] == "FIXTURE_DEMO"
    assert result.data_quality["is_live_data"] is False


def test_live_cache_reuses_provider_snapshot_within_ttl() -> None:
    clear_provider_cache()
    symbol = normalize_symbol("BTC")
    adapter = FakeAdapter("binance", make_snapshot(provider="binance"))
    settings = Settings(
        data_mode="live",
        provider_priority=("binance",),
        candle_cache_ttl_seconds=60,
    )

    first = select_market_data(symbol, "4H", settings=settings, providers=[adapter])
    second = select_market_data(symbol, "4H", settings=settings, providers=[adapter])

    assert first.snapshot == second.snapshot
    assert adapter.calls == 1
