"""Bounded process-local raw derivatives acquisition and single-flight caching.

The single-flight guarantee is per process. Multiple worker processes maintain
independent caches. The nine-second budget is a new-call start deadline; with a
three-second request timeout, a cold path may complete near twelve seconds.
"""

from __future__ import annotations

import hashlib
import threading
import time
from collections import OrderedDict
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from crypto_probability_engine.adapters.derivatives.binance_usdm import (
    BinanceUsdmDerivativesAdapter,
)
from crypto_probability_engine.adapters.derivatives.okx_swap import (
    OkxSwapDerivativesAdapter,
)
from crypto_probability_engine.adapters.derivatives_endpoints import (
    DerivativesPublicHttpClient,
)
from crypto_probability_engine.adapters.http_client import PublicHttpClient
from crypto_probability_engine.config.unit_discipline import utc_now
from crypto_probability_engine.derivatives_intel.instruments import (
    InstrumentResolution,
    derivatives_candidates,
    resolve_binance_usdm_instrument,
    resolve_okx_swap_instrument,
)

REGISTRY_CACHE_MAX_ENTRIES = 2
REGISTRY_CACHE_TTL_SECONDS = 6 * 60 * 60
SYMBOL_CACHE_MAX_ENTRIES = 256
SYMBOL_CACHE_TTL_SECONDS = 60
LOCK_STRIPE_COUNT = 64
NEW_CALL_START_DEADLINE_SECONDS = 9.0
REQUEST_TIMEOUT_SECONDS = 3.0
REQUEST_MAX_RETRIES = 0

_PROVIDERS = ("BINANCE_USDM", "OKX_SWAP")
_BINANCE_REGISTRY_FIELDS = (
    "symbol",
    "status",
    "contractType",
    "pair",
    "baseAsset",
    "quoteAsset",
    "marginAsset",
)
_OKX_REGISTRY_FIELDS = (
    "instId",
    "instType",
    "settleCcy",
    "ctType",
    "state",
    "ctVal",
    "ctMult",
    "ctValCcy",
)
_BINANCE_FUNDING_FIELDS = ("symbol", "lastFundingRate", "time")
_BINANCE_OI_FIELDS = ("symbol", "openInterest", "time")
_OKX_FUNDING_FIELDS = ("instId", "fundingRate", "ts")
_OKX_OI_FIELDS = ("instId", "instType", "oi", "oiCcy", "oiUsd", "ts")

FrozenPairs = tuple[tuple[str, str | int | float | bool | None], ...]


@dataclass(frozen=True)
class CachedInstrumentResolution:
    normalized_symbol: str
    provider: str
    candidate: str | None
    status: str
    reason: str | None
    contract_type: str | None
    margin_asset: str | None
    settlement_asset: str | None
    metadata: FrozenPairs

    @classmethod
    def from_resolution(cls, value: InstrumentResolution) -> CachedInstrumentResolution:
        return cls(
            normalized_symbol=value.normalized_symbol,
            provider=value.provider,
            candidate=value.candidate,
            status=value.status.value,
            reason=value.reason,
            contract_type=value.contract_type,
            margin_asset=value.margin_asset,
            settlement_asset=value.settlement_asset,
            metadata=_freeze_mapping(value.metadata, tuple(value.metadata)),
        )

    def thaw(self) -> InstrumentResolution:
        from crypto_probability_engine.derivatives_intel.instruments import (
            InstrumentResolutionStatus,
        )

        return InstrumentResolution(
            normalized_symbol=self.normalized_symbol,
            provider=self.provider,
            candidate=self.candidate,
            status=InstrumentResolutionStatus(self.status),
            reason=self.reason,
            contract_type=self.contract_type,
            margin_asset=self.margin_asset,
            settlement_asset=self.settlement_asset,
            metadata=dict(self.metadata),
        )


@dataclass(frozen=True)
class RawProviderBundle:
    provider: str
    normalized_symbol: str
    instrument: CachedInstrumentResolution | None
    funding_payload: FrozenPairs | None
    open_interest_payload: FrozenPairs | None
    funding_event_time: datetime | None
    open_interest_event_time: datetime | None
    funding_fetched_at_utc: datetime | None
    open_interest_fetched_at_utc: datetime | None
    fetch_status: str
    reason: str | None

    def thaw_funding(self) -> dict[str, Any] | list[dict[str, Any]] | None:
        if self.funding_payload is None:
            return None
        row = dict(self.funding_payload)
        return [row] if self.provider == "OKX_SWAP" else row

    def thaw_open_interest(self) -> dict[str, Any] | list[dict[str, Any]] | None:
        if self.open_interest_payload is None:
            return None
        row = dict(self.open_interest_payload)
        return [row] if self.provider == "OKX_SWAP" else row


@dataclass(frozen=True)
class RawDerivativesBundle:
    normalized_symbol: str
    providers: tuple[RawProviderBundle, ...]


@dataclass(frozen=True)
class _RegistryEntry:
    rows: tuple[FrozenPairs, ...]
    fetched_at_utc: datetime
    expires_at: float


@dataclass(frozen=True)
class _SymbolEntry:
    bundle: RawProviderBundle
    expires_at: float


_CACHE_GUARD = threading.RLock()
_LOCK_STRIPES = tuple(threading.Lock() for _ in range(LOCK_STRIPE_COUNT))
_REGISTRY_CACHE: OrderedDict[str, _RegistryEntry] = OrderedDict()
_SYMBOL_CACHE: OrderedDict[tuple[str, str], _SymbolEntry] = OrderedDict()


def get_raw_derivatives_bundle(
    normalized_symbol: str,
    *,
    http_client: PublicHttpClient | None = None,
    rate_limit_per_min: int = 120,
    monotonic_func: Callable[[], float] = time.monotonic,
    utc_now_func: Callable[[], datetime] = utc_now,
) -> RawDerivativesBundle:
    """Return cached or freshly fetched allowlisted current raw evidence."""

    now_mono = monotonic_func()
    cached = _cached_providers(normalized_symbol, now_mono)
    if len(cached) == len(_PROVIDERS):
        return _bundle(normalized_symbol, cached)

    stripe = _LOCK_STRIPES[_stripe_index(normalized_symbol)]
    with stripe:
        now_mono = monotonic_func()
        cached = _cached_providers(normalized_symbol, now_mono)
        missing = [provider for provider in _PROVIDERS if provider not in cached]
        if not missing:
            return _bundle(normalized_symbol, cached)

        start = monotonic_func()
        client = http_client or DerivativesPublicHttpClient(
            timeout_seconds=REQUEST_TIMEOUT_SECONDS,
            max_retries=REQUEST_MAX_RETRIES,
            rate_limit_per_min=rate_limit_per_min,
        )
        binance = BinanceUsdmDerivativesAdapter(http_client=client)
        okx = OkxSwapDerivativesAdapter(http_client=client)
        for provider in missing:
            raw = _fetch_provider(
                provider,
                normalized_symbol,
                binance=binance,
                okx=okx,
                start=start,
                monotonic_func=monotonic_func,
                utc_now_func=utc_now_func,
            )
            _put_symbol(raw, monotonic_func())
            cached[provider] = raw
        return _bundle(normalized_symbol, cached)


def clear_runtime_caches() -> None:
    """Clear process-local raw caches for deterministic tests."""

    with _CACHE_GUARD:
        _REGISTRY_CACHE.clear()
        _SYMBOL_CACHE.clear()


def runtime_cache_sizes() -> dict[str, int]:
    with _CACHE_GUARD:
        return {
            "registry": len(_REGISTRY_CACHE),
            "symbols": len(_SYMBOL_CACHE),
            "lock_stripes": len(_LOCK_STRIPES),
        }


def _fetch_provider(
    provider: str,
    normalized_symbol: str,
    *,
    binance: BinanceUsdmDerivativesAdapter,
    okx: OkxSwapDerivativesAdapter,
    start: float,
    monotonic_func: Callable[[], float],
    utc_now_func: Callable[[], datetime],
) -> RawProviderBundle:
    registry = _get_registry(provider, monotonic_func())
    if registry is None:
        if not _can_start(start, monotonic_func):
            return _unavailable(provider, normalized_symbol, "New-call start deadline reached.")
        registry = _fetch_registry(
            provider,
            binance=binance,
            okx=okx,
            monotonic_func=monotonic_func,
            utc_now_func=utc_now_func,
        )
    if registry is None:
        return _unavailable(provider, normalized_symbol, "Public instrument registry unavailable.")

    resolution = _resolve(provider, normalized_symbol, registry)
    cached_resolution = CachedInstrumentResolution.from_resolution(resolution)
    if resolution.status.value != "SUPPORTED":
        return RawProviderBundle(
            provider=provider,
            normalized_symbol=normalized_symbol,
            instrument=cached_resolution,
            funding_payload=None,
            open_interest_payload=None,
            funding_event_time=None,
            open_interest_event_time=None,
            funding_fetched_at_utc=None,
            open_interest_fetched_at_utc=None,
            fetch_status=resolution.status.value,
            reason=resolution.reason,
        )

    funding_payload: FrozenPairs | None = None
    oi_payload: FrozenPairs | None = None
    funding_fetched: datetime | None = None
    oi_fetched: datetime | None = None
    reasons: list[str] = []

    if _can_start(start, monotonic_func):
        try:
            raw_funding = (
                binance.fetch_current_funding(resolution.candidate or "")
                if provider == "BINANCE_USDM"
                else okx.fetch_current_funding(resolution.candidate or "")
            )
            funding_fetched = _require_utc(utc_now_func())
            funding_payload = _freeze_current_payload(provider, "funding", raw_funding)
            if funding_payload is None:
                reasons.append("Current funding payload was malformed.")
        except Exception:
            reasons.append("Current funding resource unavailable.")
    else:
        reasons.append("Current funding skipped after new-call start deadline.")

    if _can_start(start, monotonic_func):
        try:
            raw_oi = (
                binance.fetch_current_open_interest(resolution.candidate or "")
                if provider == "BINANCE_USDM"
                else okx.fetch_current_open_interest(resolution.candidate or "")
            )
            oi_fetched = _require_utc(utc_now_func())
            oi_payload = _freeze_current_payload(provider, "open_interest", raw_oi)
            if oi_payload is None:
                reasons.append("Current open-interest payload was malformed.")
        except Exception:
            reasons.append("Current open-interest resource unavailable.")
    else:
        reasons.append("Current open-interest skipped after new-call start deadline.")

    available_count = int(funding_payload is not None) + int(oi_payload is not None)
    fetch_status = (
        "OK"
        if available_count == 2
        else "DEGRADED_PARTIAL"
        if available_count == 1
        else "PROVIDER_UNAVAILABLE"
    )
    return RawProviderBundle(
        provider=provider,
        normalized_symbol=normalized_symbol,
        instrument=cached_resolution,
        funding_payload=funding_payload,
        open_interest_payload=oi_payload,
        funding_event_time=_event_time(funding_payload, provider),
        open_interest_event_time=_event_time(oi_payload, provider),
        funding_fetched_at_utc=funding_fetched,
        open_interest_fetched_at_utc=oi_fetched,
        fetch_status=fetch_status,
        reason=" ".join(reasons) or None,
    )


def _fetch_registry(
    provider: str,
    *,
    binance: BinanceUsdmDerivativesAdapter,
    okx: OkxSwapDerivativesAdapter,
    monotonic_func: Callable[[], float],
    utc_now_func: Callable[[], datetime],
) -> _RegistryEntry | None:
    try:
        if provider == "BINANCE_USDM":
            payload = binance.fetch_exchange_info()
            rows = payload.get("symbols", [])
            fields = _BINANCE_REGISTRY_FIELDS
        else:
            rows = okx.fetch_instruments()
            fields = _OKX_REGISTRY_FIELDS
        frozen_rows = tuple(
            _freeze_mapping(row, fields) for row in rows if isinstance(row, Mapping)
        )
        fetched = _require_utc(utc_now_func())
        entry = _RegistryEntry(
            rows=frozen_rows,
            fetched_at_utc=fetched,
            expires_at=monotonic_func() + REGISTRY_CACHE_TTL_SECONDS,
        )
        _put_registry(provider, entry)
        return entry
    except Exception:
        return None


def _resolve(
    provider: str, normalized_symbol: str, registry: _RegistryEntry
) -> InstrumentResolution:
    rows = [dict(row) for row in registry.rows]
    if provider == "BINANCE_USDM":
        return resolve_binance_usdm_instrument(normalized_symbol, {"symbols": rows})
    return resolve_okx_swap_instrument(normalized_symbol, rows)


def _cached_providers(normalized_symbol: str, now_mono: float) -> dict[str, RawProviderBundle]:
    found: dict[str, RawProviderBundle] = {}
    with _CACHE_GUARD:
        _purge_expired(_SYMBOL_CACHE, now_mono)
        for provider in _PROVIDERS:
            key = (provider, normalized_symbol)
            entry = _SYMBOL_CACHE.get(key)
            if entry is not None:
                _SYMBOL_CACHE.move_to_end(key)
                found[provider] = entry.bundle
    return found


def _get_registry(provider: str, now_mono: float) -> _RegistryEntry | None:
    with _CACHE_GUARD:
        _purge_expired(_REGISTRY_CACHE, now_mono)
        entry = _REGISTRY_CACHE.get(provider)
        if entry is not None:
            _REGISTRY_CACHE.move_to_end(provider)
        return entry


def _put_registry(provider: str, entry: _RegistryEntry) -> None:
    with _CACHE_GUARD:
        _purge_expired(_REGISTRY_CACHE, entry.expires_at - REGISTRY_CACHE_TTL_SECONDS)
        _REGISTRY_CACHE[provider] = entry
        _REGISTRY_CACHE.move_to_end(provider)
        while len(_REGISTRY_CACHE) > REGISTRY_CACHE_MAX_ENTRIES:
            _REGISTRY_CACHE.popitem(last=False)


def _put_symbol(bundle: RawProviderBundle, now_mono: float) -> None:
    key = (bundle.provider, bundle.normalized_symbol)
    with _CACHE_GUARD:
        _purge_expired(_SYMBOL_CACHE, now_mono)
        _SYMBOL_CACHE[key] = _SymbolEntry(
            bundle=bundle,
            expires_at=now_mono + SYMBOL_CACHE_TTL_SECONDS,
        )
        _SYMBOL_CACHE.move_to_end(key)
        while len(_SYMBOL_CACHE) > SYMBOL_CACHE_MAX_ENTRIES:
            _SYMBOL_CACHE.popitem(last=False)


def _purge_expired(cache: OrderedDict[Any, Any], now_mono: float) -> None:
    expired = [key for key, entry in cache.items() if entry.expires_at <= now_mono]
    for key in expired:
        cache.pop(key, None)


def _freeze_current_payload(provider: str, kind: str, payload: Any) -> FrozenPairs | None:
    if provider == "OKX_SWAP":
        if not isinstance(payload, list) or not payload or not isinstance(payload[0], Mapping):
            return None
        row = payload[0]
        fields = _OKX_FUNDING_FIELDS if kind == "funding" else _OKX_OI_FIELDS
    else:
        if not isinstance(payload, Mapping):
            return None
        row = payload
        fields = _BINANCE_FUNDING_FIELDS if kind == "funding" else _BINANCE_OI_FIELDS
    return _freeze_mapping(row, fields)


def _freeze_mapping(payload: Mapping[str, Any], fields: tuple[str, ...]) -> FrozenPairs:
    pairs: list[tuple[str, str | int | float | bool | None]] = []
    for field in fields:
        value = payload.get(field)
        if value is None or isinstance(value, (str, int, float, bool)):
            pairs.append((field, value))
    return tuple(pairs)


def _event_time(payload: FrozenPairs | None, provider: str) -> datetime | None:
    if payload is None:
        return None
    raw = dict(payload).get("time" if provider == "BINANCE_USDM" else "ts")
    if isinstance(raw, bool):
        return None
    try:
        return datetime.fromtimestamp(int(raw) / 1000, tz=UTC)
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def _unavailable(provider: str, normalized_symbol: str, reason: str) -> RawProviderBundle:
    candidate = (derivatives_candidates(normalized_symbol) or {}).get(provider)
    return RawProviderBundle(
        provider=provider,
        normalized_symbol=normalized_symbol,
        instrument=None,
        funding_payload=None,
        open_interest_payload=None,
        funding_event_time=None,
        open_interest_event_time=None,
        funding_fetched_at_utc=None,
        open_interest_fetched_at_utc=None,
        fetch_status="PROVIDER_UNAVAILABLE",
        reason=f"{reason} Candidate: {candidate or 'UNKNOWN'}.",
    )


def _bundle(
    normalized_symbol: str, providers: Mapping[str, RawProviderBundle]
) -> RawDerivativesBundle:
    return RawDerivativesBundle(
        normalized_symbol=normalized_symbol,
        providers=tuple(providers[provider] for provider in _PROVIDERS),
    )


def _stripe_index(normalized_symbol: str) -> int:
    digest = hashlib.sha256(normalized_symbol.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") % LOCK_STRIPE_COUNT


def _can_start(start: float, monotonic_func: Callable[[], float]) -> bool:
    return monotonic_func() - start < NEW_CALL_START_DEADLINE_SECONDS


def _require_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None or value.utcoffset().total_seconds() != 0:
        raise ValueError("Runtime timestamps must be timezone-aware UTC values.")
    return value
