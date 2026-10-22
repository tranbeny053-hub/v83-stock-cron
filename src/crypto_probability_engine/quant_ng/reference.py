"""PROPOSAL, UNWIRED; this spec-pinned reference decides nothing and computes no prior.

Nothing outside ``quant_ng`` imports this module. Spec v1 covers 15m, 1H, and 4H;
1D/1W (spec v1d) wait on the owner's OD-NG-6.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import IntEnum
from numbers import Real
from types import MappingProxyType

from crypto_probability_engine.adapters.types import MarketCandle
from crypto_probability_engine.quant_ng import windows
from crypto_probability_engine.utils.invariants import validate_probability_triplet

REFERENCE_SPEC_V1_SHA256: str = "af8a385bbd5c6c5474801b0ab792546cc5031f6ccb99576dc713708ae99d12b9"
_SPEC_KEYS = {
    "schema_version", "spec_id", "status", "formula", "timeframes", "n0_days",
    "lattice_bars", "horizon_bars", "label_rule", "population", "day_type_rule",
    "counting_rule", "prior", "provenance",
}
_TIMEFRAMES = ("15m", "1H", "4H")
_PROVENANCE_KEYS = {
    "r4_reference_py_sha256", "r4_reference_spec_v2_sha256",
    "wave2_reference_spec_sha256", "where",
}
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")


class DayType(IntEnum):
    """UTC calendar day class used to select a caller-supplied prior."""

    WEEKDAY = 0
    SATURDAY = 1
    SUNDAY = 2


class Label(IntEnum):
    """Three-way outcome label; band edges are TIMEOUT."""

    UP = 0
    DOWN = 1
    TIMEOUT = 2


def _require_utc(value: datetime, name: str) -> None:
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ValueError(f"{name} must be an aware UTC datetime")
    if value.utcoffset() != timedelta(0):
        raise ValueError(f"{name} must be an aware UTC datetime")


def _timeframe(spec: ReferenceSpec, timeframe: str) -> int:
    if timeframe not in spec.bar_seconds or timeframe not in spec.memory_days:
        raise ValueError(f"Unsupported reference timeframe {timeframe!r}")
    return spec.bar_seconds[timeframe]


def day_type(instant_utc: datetime) -> DayType:
    """Classify the UTC calendar date as weekday, Saturday, or Sunday."""

    _require_utc(instant_utc, "instant_utc")
    weekday = instant_utc.astimezone(UTC).weekday()
    if weekday == 5:
        return DayType.SATURDAY
    if weekday == 6:
        return DayType.SUNDAY
    return DayType.WEEKDAY


def _finite_real(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite non-bool number")
    return float(value)


def label(r: float, band_frac: float) -> Label:
    """Apply the R2 return threshold rule, assigning both band edges to TIMEOUT."""

    result = _finite_real(r, "r")
    band = _finite_real(band_frac, "band_frac")
    if band < 0.0:
        raise ValueError("band_frac must be non-negative")
    if result > band:
        return Label.UP
    if result < -band:
        return Label.DOWN
    return Label.TIMEOUT


@dataclass(frozen=True)
class ReferenceSpec:
    """Validated v1 timeframe and smoothing constants."""

    spec_id: str
    bar_seconds: Mapping[str, int]
    memory_days: Mapping[str, int]
    n0_days: int
    lattice_bars: int
    horizon_bars: int


def _positive_int(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def load_reference_spec(payload: Mapping[str, object]) -> ReferenceSpec:
    """Validate a parsed v1 spec mapping without reading files."""

    if not isinstance(payload, Mapping) or set(payload) != _SPEC_KEYS:
        raise ValueError("Reference spec has unknown or missing keys")
    if payload["schema_version"] != "quant-ng-reference-spec.v1":
        raise ValueError("Unsupported reference spec schema_version")
    frames = payload["timeframes"]
    if not isinstance(frames, Mapping) or set(frames) != set(_TIMEFRAMES):
        raise ValueError("Reference spec must contain exactly 15m, 1H, and 4H")
    bars: dict[str, int] = {}
    memories: dict[str, int] = {}
    for timeframe in _TIMEFRAMES:
        frame = frames[timeframe]
        if not isinstance(frame, Mapping) or set(frame) != {"bar_seconds", "memory_days"}:
            raise ValueError(f"Invalid timeframe mapping for {timeframe}")
        bars[timeframe] = _positive_int(frame["bar_seconds"], "bar_seconds")
        memories[timeframe] = _positive_int(frame["memory_days"], "memory_days")
        if bars[timeframe] != windows.TIMEFRAME_SECONDS[timeframe]:
            raise ValueError(f"bar_seconds mismatch for {timeframe}")
    provenance = payload["provenance"]
    if not isinstance(provenance, Mapping) or set(provenance) != _PROVENANCE_KEYS:
        raise ValueError("Invalid provenance mapping")
    for key in _PROVENANCE_KEYS - {"where"}:
        digest = provenance[key]
        if not isinstance(digest, str) or _DIGEST.fullmatch(digest) is None:
            raise ValueError(f"Invalid provenance digest: {key}")
    if not isinstance(provenance["where"], str) or not provenance["where"].strip():
        raise ValueError("provenance.where must be non-empty")
    spec_id = payload["spec_id"]
    if not isinstance(spec_id, str) or not spec_id:
        raise ValueError("spec_id must be non-empty")
    return ReferenceSpec(
        spec_id=spec_id,
        bar_seconds=MappingProxyType(bars),
        memory_days=MappingProxyType(memories),
        n0_days=_positive_int(payload["n0_days"], "n0_days"),
        lattice_bars=_positive_int(payload["lattice_bars"], "lattice_bars"),
        horizon_bars=_positive_int(payload["horizon_bars"], "horizon_bars"),
    )


def n0_rows(spec: ReferenceSpec, timeframe: str) -> int:
    """Return the baseline count at the timeframe's reference lattice."""

    seconds = _timeframe(spec, timeframe)
    return spec.n0_days * (86_400 // (spec.lattice_bars * seconds))


@dataclass(frozen=True)
class ReferencePriors:
    """Caller-frozen timeout priors indexed by DayType."""

    pi0: tuple[float, float, float]

    def __post_init__(self) -> None:
        if not isinstance(self.pi0, tuple) or len(self.pi0) != 3:
            raise ValueError("pi0 must be a three-item tuple indexed by DayType")
        for value in self.pi0:
            number = _finite_real(value, "pi0")
            if not 0.0 <= number <= 1.0:
                raise ValueError("pi0 values must be in [0, 1]")


class ReferenceNotFrozenError(RuntimeError):
    """Raised when caller-frozen priors are absent."""


@dataclass(frozen=True)
class Anchor:
    """A lattice reference close, its known horizon end, and its label."""

    reference_close_utc: datetime
    horizon_end_utc: datetime
    label: Label

    def __post_init__(self) -> None:
        _require_utc(self.reference_close_utc, "reference_close_utc")
        _require_utc(self.horizon_end_utc, "horizon_end_utc")
        if self.horizon_end_utc <= self.reference_close_utc:
            raise ValueError("horizon_end_utc must follow reference_close_utc")
        if not isinstance(self.label, Label):
            raise ValueError("label must be a Label")


@dataclass(frozen=True)
class ReferenceTriplet:
    """Reference probabilities and the counts used to compute them."""

    p_up_frac: float
    p_down_frac: float
    p_timeout_frac: float
    day_type: DayType
    k_same_type: int
    t_same_type: int
    n0_rows: int
    memory_days: int
    deployment_start_utc: datetime | None
    window_covers_memory: bool | None


def reference_from_anchors(
    anchors: Sequence[Anchor],
    *,
    reference_close_utc: datetime,
    timeframe: str,
    spec: ReferenceSpec,
    priors: ReferencePriors | None,
    deployment_start_utc: datetime | None = None,
) -> ReferenceTriplet:
    """Compute one day-type reference from the supplied anchor population."""

    _require_utc(reference_close_utc, "reference_close_utc")
    if deployment_start_utc is not None:
        _require_utc(deployment_start_utc, "deployment_start_utc")
    _timeframe(spec, timeframe)
    if priors is None:
        raise ReferenceNotFrozenError("Caller-frozen priors are required")
    current_type = day_type(reference_close_utc)
    memory = spec.memory_days[timeframe]
    memory_start = reference_close_utc - timedelta(days=memory)
    selected = [
        anchor for anchor in anchors
        if day_type(anchor.reference_close_utc) == current_type
        and anchor.horizon_end_utc <= reference_close_utc
        and anchor.horizon_end_utc > memory_start
        and (deployment_start_utc is None
             or anchor.reference_close_utc >= deployment_start_utc)
    ]
    k_same_type = len(selected)
    t_same_type = sum(anchor.label is Label.TIMEOUT for anchor in selected)
    baseline = n0_rows(spec, timeframe)
    pi0 = priors.pi0[int(current_type)]
    p_timeout = pi0 if k_same_type == 0 else (
        baseline * pi0 + t_same_type
    ) / (baseline + k_same_type)
    side = (1.0 - p_timeout) / 2.0
    validate_probability_triplet(side, side, p_timeout)
    return ReferenceTriplet(
        p_up_frac=side,
        p_down_frac=side,
        p_timeout_frac=p_timeout,
        day_type=current_type,
        k_same_type=k_same_type,
        t_same_type=t_same_type,
        n0_rows=baseline,
        memory_days=memory,
        deployment_start_utc=deployment_start_utc,
        window_covers_memory=None,
    )


def anchors_from_candles(
    candles: Sequence[MarketCandle],
    *,
    timeframe: str,
    band_frac: float,
    spec: ReferenceSpec,
) -> tuple[Anchor, ...]:
    """Build every six-bar outcome whose close is on the spec lattice."""

    seconds = _timeframe(spec, timeframe)
    band = _finite_real(band_frac, "band_frac")
    if band < 0.0:
        raise ValueError("band_frac must be non-negative")
    windows.require_well_formed(candles, timeframe)
    lattice_seconds = spec.lattice_bars * seconds
    anchors: list[Anchor] = []
    for index, candle in enumerate(candles):
        end_index = index + spec.horizon_bars
        if end_index >= len(candles):
            break
        if int(candle.close_time_utc.timestamp()) % lattice_seconds:
            continue
        end = candles[end_index]
        result = end.close / candle.close - 1.0
        anchors.append(Anchor(candle.close_time_utc, end.close_time_utc, label(result, band)))
    return tuple(anchors)


def compute_reference(
    candles: Sequence[MarketCandle],
    *,
    timeframe: str,
    band_frac: float,
    spec: ReferenceSpec,
    priors: ReferencePriors | None,
    deployment_start_utc: datetime | None = None,
) -> ReferenceTriplet:
    """Compute a reference and mark whether the candle window covers its memory."""

    _timeframe(spec, timeframe)
    windows.require_well_formed(candles, timeframe)
    reference_close = candles[-1].close_time_utc
    anchors = anchors_from_candles(
        candles, timeframe=timeframe, band_frac=band_frac, spec=spec
    )
    result = reference_from_anchors(
        anchors,
        reference_close_utc=reference_close,
        timeframe=timeframe,
        spec=spec,
        priors=priors,
        deployment_start_utc=deployment_start_utc,
    )
    earliest = reference_close - timedelta(
        days=spec.memory_days[timeframe]
    ) - timedelta(seconds=(spec.horizon_bars - 1) * spec.bar_seconds[timeframe])
    return ReferenceTriplet(
        **{
            **result.__dict__,
            "window_covers_memory": candles[0].close_time_utc <= earliest,
        }
    )
