"""Official public symbol universe resolution for spot USDT pairs."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Protocol

from crypto_probability_engine.adapters.types import ProviderError
from crypto_probability_engine.normalizers.symbols import NormalizedSymbol


@dataclass(frozen=True)
class ProviderSymbolUniverse:
    provider: str
    symbols: frozenset[str]


@dataclass(frozen=True)
class SymbolResolution:
    symbol: NormalizedSymbol
    availability: str
    providers: tuple[str, ...]
    warnings: tuple[str, ...] = ()


class SymbolUniverseProvider(Protocol):
    name: str

    def fetch_symbol_universe(self) -> ProviderSymbolUniverse:
        """Return supported canonical symbols for this provider."""


@dataclass(frozen=True)
class _CachedUniverse:
    expires_at: float
    universe: ProviderSymbolUniverse


_UNIVERSE_CACHE: dict[str, _CachedUniverse] = {}


def clear_symbol_universe_cache() -> None:
    _UNIVERSE_CACHE.clear()


def resolve_symbol_availability(
    symbol: NormalizedSymbol,
    providers: list[object],
    *,
    ttl_seconds: int,
) -> SymbolResolution:
    """Resolve whether a canonical symbol exists on Binance, OKX, both, or neither."""

    supported_providers: list[str] = []
    warnings: list[str] = []
    universe_capable = [
        provider for provider in providers if hasattr(provider, "fetch_symbol_universe")
    ]
    if not universe_capable:
        return SymbolResolution(
            symbol=symbol,
            availability="TO_VERIFY",
            providers=tuple(getattr(provider, "name", "unknown") for provider in providers),
        )
    for provider in universe_capable:
        provider_name = getattr(provider, "name", "unknown")
        try:
            universe = _fetch_universe_with_cache(provider, ttl_seconds=ttl_seconds)
        except ProviderError as exc:
            warnings.append(f"{provider_name}:{exc.code}: {exc}")
            continue
        if symbol.display in universe.symbols:
            supported_providers.append(provider_name)
    if set(supported_providers) >= {"binance", "okx"}:
        availability = "BOTH_PROVIDERS"
    elif supported_providers == ["binance"] or set(supported_providers) == {"binance"}:
        availability = "BINANCE_ONLY"
    elif supported_providers == ["okx"] or set(supported_providers) == {"okx"}:
        availability = "OKX_ONLY"
    elif warnings:
        availability = "TO_VERIFY"
    else:
        availability = "UNSUPPORTED"
    return SymbolResolution(
        symbol=symbol,
        availability=availability,
        providers=tuple(supported_providers),
        warnings=tuple(warnings),
    )


def _fetch_universe_with_cache(
    provider: SymbolUniverseProvider,
    *,
    ttl_seconds: int,
) -> ProviderSymbolUniverse:
    now = time.monotonic()
    cached = _UNIVERSE_CACHE.get(provider.name)
    if ttl_seconds > 0 and cached and cached.expires_at > now:
        return cached.universe
    universe = provider.fetch_symbol_universe()
    if ttl_seconds > 0:
        _UNIVERSE_CACHE[provider.name] = _CachedUniverse(now + ttl_seconds, universe)
    return universe
