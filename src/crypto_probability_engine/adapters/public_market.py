"""Public-only market-data adapter interfaces and fixture implementations."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

from crypto_probability_engine.adapters.types import (
    MarketSnapshot,
    ProviderError,
    ProviderState,
    ProviderStatus,
)
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
    """Public Binance adapter placeholder; source details remain TO_VERIFY in Sprint 1."""

    name = "binance"

    def fetch_market_snapshot(self, symbol: NormalizedSymbol, timeframe: str) -> MarketSnapshot:
        raise ProviderError(
            "PROVIDER_TO_VERIFY",
            "Binance public adapter details remain TO_VERIFY for Sprint 1.",
            provider=self.name,
        )


class OkxPublicAdapter:
    """Public OKX adapter placeholder; source details remain TO_VERIFY in Sprint 1."""

    name = "okx"

    def fetch_market_snapshot(self, symbol: NormalizedSymbol, timeframe: str) -> MarketSnapshot:
        raise ProviderError(
            "PROVIDER_TO_VERIFY",
            "OKX public adapter details remain TO_VERIFY for Sprint 1.",
            provider=self.name,
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
