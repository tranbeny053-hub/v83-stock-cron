"""Public-only market-data adapter interfaces and fixture implementations."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

from crypto_probability_engine.adapters.http_client import PublicHttpClient
from crypto_probability_engine.adapters.mappers import (
    BINANCE_BASE_URL,
    OKX_BASE_URL,
    map_interval,
    parse_binance_candles,
    parse_binance_order_book,
    parse_okx_candles,
    parse_okx_order_book,
    provider_symbol,
)
from crypto_probability_engine.adapters.types import (
    MarketSnapshot,
    ProviderError,
    ProviderState,
    ProviderStatus,
)
from crypto_probability_engine.config.defaults import DEFAULT_PHASE1A
from crypto_probability_engine.config.settings import Settings
from crypto_probability_engine.config.unit_discipline import utc_now
from crypto_probability_engine.normalizers.symbols import NormalizedSymbol
from crypto_probability_engine.validation.market_data import (
    DataValidationError,
    assert_snapshots_coherent,
    validate_market_snapshot,
)


class PublicMarketAdapter(Protocol):
    name: str

    def fetch_market_snapshot(self, symbol: NormalizedSymbol, timeframe: str) -> MarketSnapshot:
        """Fetch or provide public market data for a normalized spot symbol."""


class FixturePublicAdapter:
    """Offline adapter for tests and local smoke runs."""

    def __init__(
        self,
        name: str,
        snapshots: Mapping[tuple[str, str], MarketSnapshot],
        *,
        fail_code: str | None = None,
    ) -> None:
        self.name = name
        self._snapshots = dict(snapshots)
        self._fail_code = fail_code

    def fetch_market_snapshot(self, symbol: NormalizedSymbol, timeframe: str) -> MarketSnapshot:
        if self._fail_code:
            raise ProviderError(self._fail_code, "Fixture provider failure.", provider=self.name)
        key = (symbol.display, timeframe)
        try:
            return self._snapshots[key]
        except KeyError as exc:
            raise ProviderError(
                "DATA_UNAVAILABLE",
                "Fixture snapshot unavailable.",
                provider=self.name,
            ) from exc


class BinancePublicAdapter:
    """Keyless Binance spot market-data adapter."""

    name = "binance"

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        http_client: PublicHttpClient | None = None,
    ) -> None:
        self.settings = settings or Settings.from_env()
        self.http_client = http_client or PublicHttpClient.from_settings(self.settings)

    def fetch_market_snapshot(self, symbol: NormalizedSymbol, timeframe: str) -> MarketSnapshot:
        symbol_param = provider_symbol(symbol, self.name)
        interval = map_interval(timeframe, self.name)
        limit = min(DEFAULT_PHASE1A.min_history_bars + 5, 1000)
        klines = self.http_client.get_json(
            base_url=BINANCE_BASE_URL,
            path="/api/v3/klines",
            params={"symbol": symbol_param, "interval": interval, "limit": limit},
            provider=self.name,
        )
        depth = self.http_client.get_json(
            base_url=BINANCE_BASE_URL,
            path="/api/v3/depth",
            params={"symbol": symbol_param, "limit": 100},
            provider=self.name,
        )
        as_of_utc = utc_now()
        return MarketSnapshot(
            provider=self.name,
            normalized_symbol=symbol.display,
            timeframe=timeframe,
            candles=parse_binance_candles(klines, timeframe=timeframe),
            order_book=parse_binance_order_book(depth, as_of_utc=as_of_utc),
            as_of_utc=as_of_utc,
            source_status=ProviderStatus.OK,
        )


class OkxPublicAdapter:
    """Keyless OKX spot market-data adapter."""

    name = "okx"

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        http_client: PublicHttpClient | None = None,
    ) -> None:
        self.settings = settings or Settings.from_env()
        self.http_client = http_client or PublicHttpClient.from_settings(self.settings)

    def fetch_market_snapshot(self, symbol: NormalizedSymbol, timeframe: str) -> MarketSnapshot:
        inst_id = provider_symbol(symbol, self.name)
        bar = map_interval(timeframe, self.name)
        limit = min(DEFAULT_PHASE1A.min_history_bars + 5, 300)
        candles_payload = self.http_client.get_json(
            base_url=OKX_BASE_URL,
            path="/api/v5/market/candles",
            params={"instId": inst_id, "bar": bar, "limit": limit},
            provider=self.name,
        )
        books_payload = self.http_client.get_json(
            base_url=OKX_BASE_URL,
            path="/api/v5/market/books",
            params={"instId": inst_id, "sz": 100},
            provider=self.name,
        )
        as_of_utc = utc_now()
        return MarketSnapshot(
            provider=self.name,
            normalized_symbol=symbol.display,
            timeframe=timeframe,
            candles=parse_okx_candles(candles_payload, timeframe=timeframe),
            order_book=parse_okx_order_book(books_payload, as_of_utc=as_of_utc),
            as_of_utc=as_of_utc,
            source_status=ProviderStatus.OK,
        )


class ProviderRouter:
    """Failover/quarantine router for public market-data providers."""

    def __init__(self, providers: list[PublicMarketAdapter]) -> None:
        self.providers = providers
        self.provider_states = {
            provider.name: ProviderState(name=provider.name, status=ProviderStatus.TO_VERIFY)
            for provider in providers
        }

    def fetch_first_valid(self, symbol: NormalizedSymbol, timeframe: str) -> MarketSnapshot:
        errors: list[str] = []
        accepted: MarketSnapshot | None = None
        accepted_provider: str | None = None
        for provider in self.providers:
            try:
                snapshot = provider.fetch_market_snapshot(symbol, timeframe)
                validate_market_snapshot(snapshot, min_bars=3)
                self.provider_states[provider.name].status = ProviderStatus.OK
                if accepted is not None:
                    assert_snapshots_coherent(accepted, snapshot)
                accepted = snapshot
                accepted_provider = provider.name
            except (ProviderError, DataValidationError) as exc:
                message = str(exc)
                errors.append(f"{provider.name}:{message}")
                state = self.provider_states[provider.name]
                state.status = ProviderStatus.QUARANTINED
                state.quarantine_reason = message
                state.warnings.append(message)
        if accepted is not None:
            self.provider_states[accepted_provider or accepted.provider].status = ProviderStatus.OK
            return accepted
        raise ProviderError("PROVIDER_DEGRADED", "; ".join(errors), provider="router")

    def public_state(self) -> dict:
        active = next(
            (
                state.name
                for state in self.provider_states.values()
                if state.status == ProviderStatus.OK
            ),
            None,
        )
        return {
            "status": "OK" if active else "PROVIDER_DEGRADED",
            "active_provider": active,
            "providers": {
                name: state.to_public_dict() for name, state in sorted(self.provider_states.items())
            },
        }
