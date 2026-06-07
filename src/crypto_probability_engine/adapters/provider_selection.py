"""Market-data provider selection and data-honesty rules."""

from __future__ import annotations

import time
from dataclasses import dataclass

from crypto_probability_engine.adapters.fixtures import build_fixture_snapshot
from crypto_probability_engine.adapters.public_market import (
    BinancePublicAdapter,
    FixturePublicAdapter,
    OkxPublicAdapter,
    ProviderRouter,
    PublicMarketAdapter,
)
from crypto_probability_engine.adapters.types import (
    MarketSnapshot,
    ProviderError,
    ProviderState,
    ProviderStatus,
)
from crypto_probability_engine.api.schemas import ErrorCode
from crypto_probability_engine.config.defaults import min_history_for
from crypto_probability_engine.config.settings import Settings
from crypto_probability_engine.normalizers.symbols import NormalizedSymbol
from crypto_probability_engine.validation.market_data import (
    DataValidationError,
    assert_snapshots_coherent,
    validate_market_snapshot,
)

DATA_SOURCE_BY_PROVIDER = {
    "binance": "BINANCE_PUBLIC",
    "okx": "OKX_PUBLIC",
}


@dataclass(frozen=True)
class ProviderSelectionResult:
    snapshot: MarketSnapshot
    provider_state: dict
    data_quality: dict


@dataclass(frozen=True)
class ProviderSelectionError(RuntimeError):
    code: ErrorCode
    message: str
    provider_state: dict
    data_quality: dict

    def __str__(self) -> str:
        return self.message


@dataclass(frozen=True)
class _CachedSnapshot:
    expires_at: float
    snapshot: MarketSnapshot


_SNAPSHOT_CACHE: dict[tuple[str, str, str], _CachedSnapshot] = {}


def clear_provider_cache() -> None:
    _SNAPSHOT_CACHE.clear()


def select_market_data(
    symbol: NormalizedSymbol,
    timeframe: str,
    *,
    settings: Settings,
    providers: list[PublicMarketAdapter] | None = None,
) -> ProviderSelectionResult:
    if settings.data_mode == "fixture":
        return _fixture_selection(symbol, timeframe)
    ordered_providers = _ordered_live_providers(settings, providers)
    return _live_selection(symbol, timeframe, settings=settings, providers=ordered_providers)


def _fixture_selection(symbol: NormalizedSymbol, timeframe: str) -> ProviderSelectionResult:
    snapshot = build_fixture_snapshot(normalized_symbol=symbol.display, timeframe=timeframe)
    router = ProviderRouter(
        [FixturePublicAdapter("fixture", {(symbol.display, timeframe): snapshot})]
    )
    snapshot = router.fetch_first_valid(symbol, timeframe)
    data_quality = {
        "status": "OK",
        "warnings": [],
        "freshness_budget": "DEFAULT_PHASE1A",
        "is_live_data": False,
        "data_source": "FIXTURE_DEMO",
        "latest_candle_age_seconds": 0,
        "provider_failures": {},
    }
    return ProviderSelectionResult(
        snapshot=snapshot,
        provider_state=router.public_state(),
        data_quality=data_quality,
    )


def _ordered_live_providers(
    settings: Settings,
    providers: list[PublicMarketAdapter] | None,
) -> list[PublicMarketAdapter]:
    provider_map = {
        provider.name: provider for provider in providers or _default_live_providers(settings)
    }
    ordered = [provider_map[name] for name in settings.provider_priority if name in provider_map]
    if not ordered:
        raise ProviderSelectionError(
            code=ErrorCode.PROVIDER_DEGRADED,
            message="No configured live public providers are available.",
            provider_state={
                "status": "PROVIDER_DEGRADED",
                "active_provider": None,
                "providers": {},
            },
            data_quality=_failed_data_quality("UNAVAILABLE", "No configured live providers.", {}),
        )
    return ordered


def _default_live_providers(settings: Settings) -> list[PublicMarketAdapter]:
    return [BinancePublicAdapter(settings=settings), OkxPublicAdapter(settings=settings)]


def _live_selection(
    symbol: NormalizedSymbol,
    timeframe: str,
    *,
    settings: Settings,
    providers: list[PublicMarketAdapter],
) -> ProviderSelectionResult:
    states = {provider.name: ProviderState(name=provider.name) for provider in providers}
    successes: list[MarketSnapshot] = []
    failures: dict[str, str] = {}
    for provider in providers:
        try:
            snapshot = _fetch_with_cache(
                provider,
                symbol,
                timeframe,
                ttl_seconds=settings.candle_cache_ttl_seconds,
            )
            validate_market_snapshot(snapshot, min_bars=min_history_for(timeframe))
        except (ProviderError, DataValidationError) as exc:
            code = getattr(exc, "code", "PROVIDER_DEGRADED")
            message = f"{code}: {exc}"
            failures[provider.name] = message
            states[provider.name].status = ProviderStatus.QUARANTINED
            states[provider.name].quarantine_reason = message
            states[provider.name].warnings.append(message)
        else:
            states[provider.name].status = ProviderStatus.OK
            successes.append(snapshot)

    if len(successes) >= 2:
        try:
            for snapshot in successes[1:]:
                assert_snapshots_coherent(successes[0], snapshot)
        except DataValidationError as exc:
            warning = f"{exc.code.value}: {exc}"
            for state in states.values():
                state.warnings.append(warning)
            data_quality = _failed_data_quality("DEGRADED", warning, failures)
            data_quality["status"] = "DATA_CONFLICT"
            raise ProviderSelectionError(
                code=ErrorCode.DATA_CONFLICT,
                message="Live public providers disagree beyond tolerance.",
                provider_state=_public_provider_state(states, status="DATA_CONFLICT"),
                data_quality=data_quality,
            ) from exc
        snapshot = successes[0]
        return ProviderSelectionResult(
            snapshot=snapshot,
            provider_state=_public_provider_state(
                states,
                status="OK",
                active_provider="cross_provider",
            ),
            data_quality=_success_data_quality(
                snapshot,
                data_source="CROSS_PROVIDER",
                warnings=[],
                failures=failures,
            ),
        )

    if len(successes) == 1:
        snapshot = successes[0]
        if settings.cross_provider_required:
            warning = "Cross-provider confirmation required but unavailable."
            data_quality = _failed_data_quality("DEGRADED", warning, failures)
            raise ProviderSelectionError(
                code=ErrorCode.PROVIDER_DEGRADED,
                message=warning,
                provider_state=_public_provider_state(states, status="PROVIDER_DEGRADED"),
                data_quality=data_quality,
            )
        warning = "single-source, cross-check unavailable"
        return ProviderSelectionResult(
            snapshot=snapshot,
            provider_state=_public_provider_state(
                states,
                status="OK",
                active_provider=snapshot.provider,
            ),
            data_quality=_success_data_quality(
                snapshot,
                data_source=DATA_SOURCE_BY_PROVIDER.get(snapshot.provider, "DEGRADED"),
                warnings=[warning],
                failures=failures,
            ),
        )

    code = (
        ErrorCode.INVALID_SYMBOL
        if _all_failures_are_invalid(failures)
        else ErrorCode.PROVIDER_DEGRADED
    )
    warning = "No live public provider produced valid data."
    raise ProviderSelectionError(
        code=code,
        message=warning,
        provider_state=_public_provider_state(states, status="PROVIDER_DEGRADED"),
        data_quality=_failed_data_quality("UNAVAILABLE", warning, failures),
    )


def _fetch_with_cache(
    provider: PublicMarketAdapter,
    symbol: NormalizedSymbol,
    timeframe: str,
    *,
    ttl_seconds: int,
) -> MarketSnapshot:
    cache_key = (provider.name, symbol.display, timeframe)
    now = time.monotonic()
    cached = _SNAPSHOT_CACHE.get(cache_key)
    if ttl_seconds > 0 and cached and cached.expires_at > now:
        return cached.snapshot
    snapshot = provider.fetch_market_snapshot(symbol, timeframe)
    if ttl_seconds > 0:
        _SNAPSHOT_CACHE[cache_key] = _CachedSnapshot(now + ttl_seconds, snapshot)
    return snapshot


def _public_provider_state(
    states: dict[str, ProviderState],
    *,
    status: str,
    active_provider: str | None = None,
) -> dict:
    return {
        "status": status,
        "active_provider": active_provider,
        "providers": {name: state.to_public_dict() for name, state in sorted(states.items())},
    }


def _success_data_quality(
    snapshot: MarketSnapshot,
    *,
    data_source: str,
    warnings: list[str],
    failures: dict[str, str],
) -> dict:
    latest_age = max(
        0,
        int((snapshot.as_of_utc - snapshot.candles[-1].close_time_utc).total_seconds()),
    )
    return {
        "status": "OK",
        "warnings": warnings,
        "freshness_budget": "DEFAULT_PHASE1A",
        "is_live_data": True,
        "data_source": data_source,
        "latest_candle_age_seconds": latest_age,
        "provider_failures": failures,
    }


def _failed_data_quality(data_source: str, warning: str, failures: dict[str, str]) -> dict:
    return {
        "status": "UNAVAILABLE" if data_source == "UNAVAILABLE" else "DEGRADED",
        "warnings": [warning],
        "freshness_budget": "DEFAULT_PHASE1A",
        "is_live_data": False,
        "data_source": data_source,
        "latest_candle_age_seconds": None,
        "provider_failures": failures,
    }


def _all_failures_are_invalid(failures: dict[str, str]) -> bool:
    return bool(failures) and all(
        message.startswith("INVALID_SYMBOL") for message in failures.values()
    )
