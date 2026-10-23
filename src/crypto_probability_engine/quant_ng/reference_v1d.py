"""PROPOSAL, UNWIRED; development only (the owner's OD-NG-6).

Nothing outside ``quant_ng`` imports this module. It never changes ``reference.py``
(spec v1). This implements 1D only; 1W is pending (see the spec's ``pending`` field).
The caller supplies pi0; it is never computed here.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from numbers import Real
from types import MappingProxyType

from crypto_probability_engine.adapters.types import MarketCandle
from crypto_probability_engine.quant_ng.reference import (
    Anchor,
    Label,
    ReferenceNotFrozenError,
    ReferenceUnavailable,
    ReferenceUnavailableReason,
    label,
)
from crypto_probability_engine.quant_ng.windows import WindowUnavailable
from crypto_probability_engine.utils.invariants import validate_probability_triplet

REFERENCE_SPEC_V1D_SHA256: str = "1c53d4a50388400627622002d5264dd119c14a10aa72debcb9b9817fd0283d9e"
_SPEC_KEYS = {
    "schema_version", "spec_id", "status", "formula", "timeframes", "day_types",
    "lattice_bars", "horizon_bars", "label_rule", "population", "counting_rule",
    "n0_rule", "prior", "pending", "provenance",
}
@dataclass(frozen=True)
class ReferenceSpecV1d:
    """Validated v1d constants for the single supported timeframe."""

    spec_id: str
    bar_seconds: Mapping[str, int]
    memory_days: Mapping[str, int]
    n0_rows: Mapping[str, float]
    lattice_bars: int
    horizon_bars: int
    _loaded: bool = field(default=False, repr=False, compare=False)


def _require_loaded(spec: ReferenceSpecV1d) -> None:
    if not isinstance(spec, ReferenceSpecV1d) or spec._loaded is not True:
        raise ValueError("build specs with load_reference_spec_v1d")


def _require_utc(value: datetime, name: str) -> None:
    if not isinstance(value, datetime) or value.utcoffset() != timedelta(0):
        raise ValueError(f"{name} must be an aware UTC datetime")


def _timeframe(spec: ReferenceSpecV1d, timeframe: str) -> int:
    _require_loaded(spec)
    if timeframe != "1D":
        raise ValueError(f"Unsupported reference timeframe {timeframe!r}; 1W is pending")
    return spec.bar_seconds[timeframe]


def load_reference_spec_v1d(payload: Mapping[str, object]) -> ReferenceSpecV1d:
    """Strictly validate a parsed v1d spec mapping."""

    if not isinstance(payload, Mapping) or set(payload) != _SPEC_KEYS:
        raise ValueError("Reference spec has unknown or missing keys")
    if payload["schema_version"] != "quant-ng-reference-spec.v1d":
        raise ValueError("Unsupported reference spec schema_version")
    if payload["spec_id"] != "reference-daytype-v1d":
        raise ValueError("Unsupported spec_id")
    frames = payload["timeframes"]
    if not isinstance(frames, Mapping) or set(frames) != {"1D"}:
        raise ValueError("Reference spec must contain exactly 1D")
    frame = frames["1D"]
    if not isinstance(frame, Mapping) or set(frame) != {"bar_seconds", "memory_days", "n0_rows"}:
        raise ValueError("Invalid timeframe mapping for 1D")
    for key, expected in (("bar_seconds", 86_400), ("memory_days", 365)):
        value = frame[key]
        if isinstance(value, bool) or value != expected:
            raise ValueError(f"{key} mismatch for 1D")
    n0 = frame["n0_rows"]
    if isinstance(n0, bool) or not isinstance(n0, Real) or float(n0) != 1.0:
        raise ValueError("n0_rows mismatch for 1D")
    for key, expected in (("day_types", "single"), ("lattice_bars", 3), ("horizon_bars", 6)):
        value = payload[key]
        if isinstance(value, bool) or value != expected:
            raise ValueError(f"{key} mismatch")
    spec = ReferenceSpecV1d(
        spec_id="reference-daytype-v1d",
        bar_seconds=MappingProxyType({"1D": 86_400}),
        memory_days=MappingProxyType({"1D": 365}),
        n0_rows=MappingProxyType({"1D": 1.0}),
        lattice_bars=3,
        horizon_bars=6,
        _loaded=True,
    )
    return spec


def _finite_real(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite non-bool number")
    return float(value)


@dataclass(frozen=True)
class ReferenceTripletV1d:
    p_up_frac: float
    p_down_frac: float
    p_timeout_frac: float
    k: int
    t: int
    n0_rows: float
    memory_days: int
    deployment_start_utc: datetime | None
    window_covers_memory: bool | None


def reference_from_anchors_v1d(
    anchors: Sequence[Anchor],
    *,
    reference_close_utc: datetime,
    timeframe: str,
    spec: ReferenceSpecV1d,
    prior: float | None,
    deployment_start_utc: datetime | None = None,
) -> ReferenceTripletV1d:
    """Compute the single-type 1D reference over the supplied anchor population."""

    _timeframe(spec, timeframe)
    _require_utc(reference_close_utc, "reference_close_utc")
    if deployment_start_utc is not None:
        _require_utc(deployment_start_utc, "deployment_start_utc")
    if prior is None:
        raise ReferenceNotFrozenError("Caller-frozen prior is required")
    pi0 = _finite_real(prior, "prior")
    if not 0.0 <= pi0 <= 1.0:
        raise ValueError("prior must be in [0, 1]")
    memory_start = reference_close_utc - timedelta(days=spec.memory_days[timeframe])
    selected = [
        anchor for anchor in anchors
        if anchor.horizon_end_utc <= reference_close_utc
        and anchor.horizon_end_utc > memory_start
        and (deployment_start_utc is None
             or anchor.reference_close_utc >= deployment_start_utc)
    ]
    k = len(selected)
    t = sum(anchor.label is Label.TIMEOUT for anchor in selected)
    n0 = spec.n0_rows[timeframe]
    p_timeout = pi0 if k == 0 else (n0 * pi0 + t) / (n0 + k)
    side = (1.0 - p_timeout) / 2.0
    validate_probability_triplet(side, side, p_timeout)
    return ReferenceTripletV1d(
        side, side, p_timeout, k, t, n0, spec.memory_days[timeframe],
        deployment_start_utc, None,
    )


def require_well_formed_1d(candles: Sequence[MarketCandle]) -> None:
    """Require UTC, adjacent, exact one-day candles with valid positive prices."""

    from crypto_probability_engine.quant_ng.windows import UnavailableReason

    if not candles:
        raise WindowUnavailable(UnavailableReason.WINDOW_MALFORMED, "Window is empty.")
    previous: MarketCandle | None = None
    for candle in candles:
        opened, closed = candle.open_time_utc, candle.close_time_utc
        if any(moment.utcoffset() != timedelta(0) for moment in (opened, closed)):
            raise WindowUnavailable(UnavailableReason.WINDOW_MALFORMED, "Candle times must be UTC.")
        if (closed - opened).total_seconds() != 86_400:
            raise WindowUnavailable(
                UnavailableReason.WINDOW_MALFORMED, "Candles must span exactly one bar."
            )
        if int(opened.timestamp()) % 86_400:
            raise WindowUnavailable(
                UnavailableReason.WINDOW_MALFORMED,
                "Candles must open on a UTC day boundary.",
            )
        if previous is not None and opened != previous.close_time_utc:
            raise WindowUnavailable(
                UnavailableReason.WINDOW_MALFORMED,
                "Candles must be ordered and exactly adjacent.",
            )
        prices = (candle.open, candle.high, candle.low, candle.close)
        if not all(math.isfinite(price) and price > 0.0 for price in prices):
            raise WindowUnavailable(
                UnavailableReason.WINDOW_MALFORMED,
                "Candle prices must be finite and positive.",
            )
        if candle.low > candle.high:
            raise WindowUnavailable(
                UnavailableReason.WINDOW_MALFORMED, "Candle low exceeds high."
            )
        previous = candle


def anchors_from_candles_v1d(
    candles: Sequence[MarketCandle], *, timeframe: str, band_frac: float,
    spec: ReferenceSpecV1d,
) -> tuple[Anchor, ...]:
    seconds = _timeframe(spec, timeframe)
    band = _finite_real(band_frac, "band_frac")
    if band < 0.0:
        raise ValueError("band_frac must be non-negative")
    require_well_formed_1d(candles)
    lattice_seconds = spec.lattice_bars * seconds
    anchors = []
    for index, candle in enumerate(candles):
        end_index = index + spec.horizon_bars
        if end_index >= len(candles):
            break
        if int(candle.close_time_utc.timestamp()) % lattice_seconds:
            continue
        end = candles[end_index]
        anchors.append(Anchor(candle.close_time_utc, end.close_time_utc,
                              label(end.close / candle.close - 1.0, band)))
    return tuple(anchors)


def compute_reference_v1d(
    candles: Sequence[MarketCandle], *, timeframe: str, band_frac: float,
    spec: ReferenceSpecV1d, prior: float | None,
    deployment_start_utc: datetime | None = None,
    allow_partial_memory: bool = False,
) -> ReferenceTripletV1d:
    _timeframe(spec, timeframe)
    require_well_formed_1d(candles)
    reference_close = candles[-1].close_time_utc
    anchors = anchors_from_candles_v1d(
        candles, timeframe=timeframe, band_frac=band_frac, spec=spec
    )
    result = reference_from_anchors_v1d(
        anchors, reference_close_utc=reference_close, timeframe=timeframe,
        spec=spec, prior=prior, deployment_start_utc=deployment_start_utc,
    )
    earliest = reference_close - timedelta(days=spec.memory_days[timeframe]) - timedelta(
        seconds=(spec.horizon_bars - 1) * spec.bar_seconds[timeframe]
    )
    covers_memory = candles[0].close_time_utc <= earliest
    if not covers_memory and not allow_partial_memory:
        raise ReferenceUnavailable(
            ReferenceUnavailableReason.WINDOW_SHORT,
            "Candle window does not cover the full reference memory.",
        )
    return ReferenceTripletV1d(
        result.p_up_frac, result.p_down_frac, result.p_timeout_frac,
        result.k, result.t, result.n0_rows, result.memory_days,
        result.deployment_start_utc, covers_memory,
    )
