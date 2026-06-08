"""Market-data provider selection and data-honesty rules."""

from __future__ import annotations

import time
from dataclasses import dataclass

from crypto_probability_engine.adapters.fixtures import build_fixture_snapshot
from crypto_probability_engine.adapters.market_metrics import (
    cross_provider_price_disagreement_metric,
)
from crypto_probability_engine.adapters.public_market import (
    BinancePublicAdapter,
    FixturePublicAdapter,
    OkxPublicAdapter,
    ProviderRouter,
    PublicMarketAdapter,
)
from crypto_probability_engine.adapters.symbol_universe import (
    clear_symbol_universe_cache,
    resolve_symbol_availability,
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
    snapshot_coherence_report,
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
    clear_symbol_universe_cache()


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
    symbol_resolution = resolve_symbol_availability(
        symbol,
        providers,
        ttl_seconds=settings.symbol_universe_cache_ttl_seconds,
    )
    providers = _providers_for_symbol_resolution(
        providers,
        symbol_resolution=symbol_resolution,
        settings=settings,
    )
    states = {provider.name: ProviderState(name=provider.name) for provider in providers}
    successes: list[MarketSnapshot] = []
    failures: dict[str, str] = {}
    symbol_warnings = list(symbol_resolution.warnings)
    if symbol_resolution.availability in {"BINANCE_ONLY", "OKX_ONLY"}:
        symbol_warnings.append(
            "Single-provider live data; cross-provider confirmation unavailable."
        )
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
            states[provider.name].warnings.extend(snapshot.warnings)
            states[provider.name].resources = dict(snapshot.resource_statuses)
            states[provider.name].derived_metrics = dict(snapshot.derived_metrics)
            successes.append(snapshot)

    if len(successes) >= 2:
        coherence_reports: list[dict] = []
        try:
            for snapshot in successes[1:]:
                report = snapshot_coherence_report(successes[0], snapshot)
                coherence_reports.append(report)
                if report["status"] != "OK":
                    raise DataValidationError(ErrorCode.DATA_CONFLICT, report["reason"])
        except DataValidationError as exc:
            conflict_report = coherence_reports[-1] if coherence_reports else {}
            warning = _coherence_warning(exc, conflict_report)
            for state in states.values():
                state.warnings.append(warning)
            data_quality = _failed_data_quality("DEGRADED", warning, failures)
            data_quality["status"] = "DATA_CONFLICT"
            data_quality["cross_provider_state"] = "DATA_CONFLICT"
            data_quality["fallback_to_single_provider"] = False
            data_quality["symbol_availability"] = symbol_resolution.availability
            data_quality["provider_resources"] = _provider_resources(successes)
            data_quality["derived_market_metrics"] = _combined_derived_metrics(
                successes,
                coherence_reports,
            )
            if conflict_report.get("disagreement_bps") is not None:
                data_quality["disagreement_bps"] = conflict_report["disagreement_bps"]
            if settings.cross_provider_required:
                raise ProviderSelectionError(
                    code=ErrorCode.DATA_CONFLICT,
                    message="Live public providers disagree beyond tolerance.",
                    provider_state=_public_provider_state(
                        states,
                        status="DATA_CONFLICT",
                        cross_provider_state="DATA_CONFLICT",
                        fallback_to_single_provider=False,
                        cross_provider_reason=warning,
                        disagreement_bps=conflict_report.get("disagreement_bps"),
                        cross_provider_checks=coherence_reports,
                        symbol_availability=symbol_resolution.availability,
                    ),
                    data_quality=data_quality,
                ) from exc
            snapshot = successes[0]
            fallback_warning = (
                f"{warning}; using {snapshot.provider} public live data because "
                "cross-provider confirmation is optional."
            )
            states[snapshot.provider].warnings.append("fallback_to_single_provider: true")
            return ProviderSelectionResult(
                snapshot=snapshot,
                provider_state=_public_provider_state(
                    states,
                    status="DEGRADED",
                    active_provider=snapshot.provider,
                    cross_provider_state="DATA_CONFLICT",
                    fallback_to_single_provider=True,
                    cross_provider_reason=fallback_warning,
                    disagreement_bps=conflict_report.get("disagreement_bps"),
                    cross_provider_checks=coherence_reports,
                    symbol_availability=symbol_resolution.availability,
                ),
                data_quality=_success_data_quality(
                    snapshot,
                    data_source=DATA_SOURCE_BY_PROVIDER.get(snapshot.provider, "DEGRADED"),
                    warnings=[*symbol_warnings, fallback_warning],
                    failures=failures,
                    cross_provider_state="DATA_CONFLICT",
                    fallback_to_single_provider=True,
                    disagreement_bps=conflict_report.get("disagreement_bps"),
                    symbol_availability=symbol_resolution.availability,
                    successes=successes,
                    coherence_reports=coherence_reports,
                ),
            )
        snapshot = successes[0]
        return ProviderSelectionResult(
            snapshot=snapshot,
            provider_state=_public_provider_state(
                states,
                status="OK",
                active_provider="cross_provider",
                cross_provider_state="COHERENT",
                fallback_to_single_provider=False,
                cross_provider_checks=coherence_reports,
                symbol_availability=symbol_resolution.availability,
            ),
            data_quality=_success_data_quality(
                snapshot,
                data_source="CROSS_PROVIDER",
                warnings=symbol_warnings,
                failures=failures,
                cross_provider_state="COHERENT",
                fallback_to_single_provider=False,
                symbol_availability=symbol_resolution.availability,
                successes=successes,
                coherence_reports=coherence_reports,
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
                provider_state=_public_provider_state(
                    states,
                    status="PROVIDER_DEGRADED",
                    cross_provider_state="UNAVAILABLE",
                    fallback_to_single_provider=False,
                    cross_provider_reason=warning,
                ),
                data_quality=data_quality,
            )
        warning = "Single-provider live data; cross-provider confirmation unavailable."
        return ProviderSelectionResult(
            snapshot=snapshot,
            provider_state=_public_provider_state(
                states,
                status="OK",
                active_provider=snapshot.provider,
                cross_provider_state="UNAVAILABLE",
                fallback_to_single_provider=True,
                cross_provider_reason=warning,
                symbol_availability=symbol_resolution.availability,
            ),
            data_quality=_success_data_quality(
                snapshot,
                data_source=DATA_SOURCE_BY_PROVIDER.get(snapshot.provider, "DEGRADED"),
                warnings=[*symbol_warnings, warning],
                failures=failures,
                cross_provider_state="UNAVAILABLE",
                fallback_to_single_provider=True,
                symbol_availability=symbol_resolution.availability,
                successes=successes,
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
        data_quality=_failed_data_quality(
            "UNAVAILABLE",
            warning,
            failures,
            symbol_availability=symbol_resolution.availability,
        ),
    )


def _providers_for_symbol_resolution(
    providers: list[PublicMarketAdapter],
    *,
    symbol_resolution,
    settings: Settings,
) -> list[PublicMarketAdapter]:
    if symbol_resolution.availability in {"TO_VERIFY", "BOTH_PROVIDERS"}:
        return providers
    if symbol_resolution.availability == "UNSUPPORTED":
        failures = {
            getattr(provider, "name", "unknown"): "INVALID_SYMBOL: unsupported spot USDT symbol"
            for provider in providers
        }
        raise ProviderSelectionError(
            code=ErrorCode.INVALID_SYMBOL,
            message="Unsupported spot USDT symbol.",
            provider_state={
                "status": "INVALID_SYMBOL",
                "active_provider": None,
                "cross_provider_state": "UNSUPPORTED",
                "fallback_to_single_provider": False,
                "symbol_availability": "UNSUPPORTED",
                "providers": {},
            },
            data_quality=_failed_data_quality(
                "UNAVAILABLE",
                "Unsupported spot USDT symbol.",
                failures,
                symbol_availability="UNSUPPORTED",
            ),
        )
    if settings.cross_provider_required:
        required_message = (
            "Cross-provider confirmation required but symbol is available on only one provider."
        )
        raise ProviderSelectionError(
            code=ErrorCode.PROVIDER_DEGRADED,
            message=required_message,
            provider_state={
                "status": "PROVIDER_DEGRADED",
                "active_provider": None,
                "cross_provider_state": "UNAVAILABLE",
                "fallback_to_single_provider": False,
                "symbol_availability": symbol_resolution.availability,
                "providers": {},
            },
            data_quality=_failed_data_quality(
                "DEGRADED",
                required_message,
                {},
                symbol_availability=symbol_resolution.availability,
            ),
        )
    allowed = set(symbol_resolution.providers)
    return [provider for provider in providers if provider.name in allowed]


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
    cross_provider_state: str = "NOT_REQUIRED",
    fallback_to_single_provider: bool = False,
    cross_provider_reason: str | None = None,
    disagreement_bps: float | None = None,
    cross_provider_checks: list[dict] | None = None,
    symbol_availability: str | None = None,
) -> dict:
    provider_state = {
        "status": status,
        "active_provider": active_provider,
        "cross_provider_state": cross_provider_state,
        "fallback_to_single_provider": fallback_to_single_provider,
        "providers": {name: state.to_public_dict() for name, state in sorted(states.items())},
    }
    if cross_provider_reason:
        provider_state["cross_provider_reason"] = cross_provider_reason
    if disagreement_bps is not None:
        provider_state["disagreement_bps"] = disagreement_bps
    if cross_provider_checks is not None:
        provider_state["cross_provider_checks"] = cross_provider_checks
    if symbol_availability is not None:
        provider_state["symbol_availability"] = symbol_availability
    return provider_state


def _success_data_quality(
    snapshot: MarketSnapshot,
    *,
    data_source: str,
    warnings: list[str],
    failures: dict[str, str],
    cross_provider_state: str = "NOT_REQUIRED",
    fallback_to_single_provider: bool = False,
    disagreement_bps: float | None = None,
    symbol_availability: str | None = None,
    successes: list[MarketSnapshot] | None = None,
    coherence_reports: list[dict] | None = None,
) -> dict:
    latest_age = max(
        0,
        int((snapshot.as_of_utc - snapshot.candles[-1].close_time_utc).total_seconds()),
    )
    data_quality = {
        "status": "OK",
        "warnings": warnings,
        "freshness_budget": "DEFAULT_PHASE1A",
        "is_live_data": True,
        "data_source": data_source,
        "latest_candle_age_seconds": latest_age,
        "provider_failures": failures,
        "cross_provider_state": cross_provider_state,
        "fallback_to_single_provider": fallback_to_single_provider,
        "symbol_availability": symbol_availability,
        "provider_resources": _provider_resources(successes or [snapshot]),
        "derived_market_metrics": _combined_derived_metrics(
            successes or [snapshot],
            coherence_reports or [],
        ),
    }
    if disagreement_bps is not None:
        data_quality["disagreement_bps"] = disagreement_bps
    return data_quality


def _coherence_warning(exc: DataValidationError, report: dict) -> str:
    parts = [f"{exc.code.value}: {exc}"]
    if report.get("disagreement_bps") is not None:
        parts.append(f"disagreement_bps={report['disagreement_bps']}")
    if report.get("aligned_close_time_utc"):
        parts.append(f"aligned_close_time_utc={report['aligned_close_time_utc']}")
    return "; ".join(parts)


def _failed_data_quality(
    data_source: str,
    warning: str,
    failures: dict[str, str],
    *,
    symbol_availability: str | None = None,
) -> dict:
    return {
        "status": "UNAVAILABLE" if data_source == "UNAVAILABLE" else "DEGRADED",
        "warnings": [warning],
        "freshness_budget": "DEFAULT_PHASE1A",
        "is_live_data": False,
        "data_source": data_source,
        "latest_candle_age_seconds": None,
        "provider_failures": failures,
        "symbol_availability": symbol_availability,
        "provider_resources": {},
        "derived_market_metrics": {},
    }


def _all_failures_are_invalid(failures: dict[str, str]) -> bool:
    return bool(failures) and all(
        message.startswith("INVALID_SYMBOL") for message in failures.values()
    )


def _provider_resources(snapshots: list[MarketSnapshot]) -> dict[str, dict]:
    return {snapshot.provider: dict(snapshot.resource_statuses) for snapshot in snapshots}


def _combined_derived_metrics(
    snapshots: list[MarketSnapshot],
    coherence_reports: list[dict],
) -> dict:
    metrics = {snapshot.provider: dict(snapshot.derived_metrics) for snapshot in snapshots}
    if len(snapshots) >= 2 or coherence_reports:
        metrics["cross_provider_price_disagreement_bps"] = cross_provider_price_disagreement_metric(
            coherence_reports
        )
    return metrics
