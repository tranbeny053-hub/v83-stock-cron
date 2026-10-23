"""PROPOSAL, UNWIRED; development only (the owner's OD-NG-6).

Nothing outside ``quant_ng`` imports this module. It never changes ``reference.py``
(spec v1). This implements 1D and 1W. The owner's 2026-10-23 ruling makes 1W DEV-only
and grants no F3 access.
The caller supplies pi0; it is never computed here.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
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

REFERENCE_SPEC_V1D_SHA256: str = "91b8c6a23a568985627d6f8bc0987bc790d25b1fa4ab448ca1c797a86b261c1c"
_SPEC_KEYS = {
    "schema_version", "spec_id", "status", "formula", "timeframes", "day_types",
    "lattice_bars", "horizon_bars", "label_rule", "population", "counting_rule",
    "n0_rule", "prior", "pending", "provenance", "lattice_1w",
}
@dataclass(frozen=True)
class ReferenceSpecV1d:
    """Validated v1d constants for 1D and 1W."""

    spec_id: str
    bar_seconds: Mapping[str, int]
    memory_days: Mapping[str, int | None]
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
    if timeframe not in ("1D", "1W"):
        raise ValueError(f"Unsupported reference timeframe {timeframe!r}")
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
    if not isinstance(frames, Mapping) or set(frames) != {"1D", "1W"}:
        raise ValueError("Reference spec must contain exactly 1D and 1W")
    expected_frames = {
        "1D": (86_400, 365, 1.0),
        "1W": (604_800, None, 3 * 86_400 / (3 * 604_800)),
    }
    for name, (bar, memory, n0_expected) in expected_frames.items():
        frame = frames[name]
        if not isinstance(frame, Mapping) or set(frame) != {
            "bar_seconds", "memory_days", "n0_rows"
        }:
            raise ValueError(f"Invalid timeframe mapping for {name}")
        for key, expected in (("bar_seconds", bar), ("memory_days", memory)):
            value = frame[key]
            if isinstance(value, bool) or value != expected:
                raise ValueError(f"{key} mismatch for {name}")
        n0 = frame["n0_rows"]
        if isinstance(n0, bool) or not isinstance(n0, Real) or float(n0) != n0_expected:
            raise ValueError(f"n0_rows mismatch for {name}")
    if payload["lattice_1w"] != {
        "anchor_utc": "2026-09-21T00:00:00Z", "extends": "backward",
        "week_open": "Monday 00:00 UTC",
    }:
        raise ValueError("lattice_1w mismatch")
    for key, expected in (("day_types", "single"), ("lattice_bars", 3), ("horizon_bars", 6)):
        value = payload[key]
        if isinstance(value, bool) or value != expected:
            raise ValueError(f"{key} mismatch")
    spec = ReferenceSpecV1d(
        spec_id="reference-daytype-v1d",
        bar_seconds=MappingProxyType({"1D": 86_400, "1W": 604_800}),
        memory_days=MappingProxyType({"1D": 365, "1W": None}),
        n0_rows=MappingProxyType({"1D": 1.0, "1W": 3 * 86_400 / (3 * 604_800)}),
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
    memory_days: int | None
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
    """Compute the single-type 1D or 1W reference over the supplied anchor population."""

    _timeframe(spec, timeframe)
    _require_utc(reference_close_utc, "reference_close_utc")
    if deployment_start_utc is not None:
        _require_utc(deployment_start_utc, "deployment_start_utc")
    if prior is None:
        raise ReferenceNotFrozenError("Caller-frozen prior is required")
    pi0 = _finite_real(prior, "prior")
    if not 0.0 <= pi0 <= 1.0:
        raise ValueError("prior must be in [0, 1]")
    if timeframe == "1W":
        _require_weekly_not_after_anchor(reference_close_utc, "reference_close_utc")
        for anchor in anchors:
            _require_weekly_not_after_anchor(
                anchor.reference_close_utc,
                f"anchor reference_close_utc {anchor.reference_close_utc.isoformat()}",
            )
            _require_weekly_not_after_anchor(
                anchor.horizon_end_utc,
                f"anchor horizon_end_utc {anchor.horizon_end_utc.isoformat()}",
            )
        memory_start = None
    else:
        memory_start = reference_close_utc - timedelta(days=spec.memory_days[timeframe])
    selected = [
        anchor for anchor in anchors
        if anchor.horizon_end_utc <= reference_close_utc
        and (memory_start is None or anchor.horizon_end_utc > memory_start)
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


_WEEK_ANCHOR = datetime(2026, 9, 21, tzinfo=UTC)


def _require_weekly_not_after_anchor(value: datetime, name: str) -> None:
    if value > _WEEK_ANCHOR:
        raise ValueError(f"{name} is after 2026-09-21T00:00:00Z; 1W is defined only up to it")


def _on_lattice(close: datetime, timeframe: str, spec: ReferenceSpecV1d) -> bool:
    lattice_seconds = spec.lattice_bars * spec.bar_seconds[timeframe]
    if timeframe == "1D":
        return int(close.timestamp()) % lattice_seconds == 0
    _require_weekly_not_after_anchor(close, "1W candle close")
    delta = int((_WEEK_ANCHOR - close).total_seconds())
    return delta >= 0 and delta % lattice_seconds == 0


def _require_well_formed_1w(candles: Sequence[MarketCandle]) -> None:
    from crypto_probability_engine.quant_ng.windows import UnavailableReason

    if not candles:
        raise WindowUnavailable(UnavailableReason.WINDOW_MALFORMED, "Window is empty.")
    previous: MarketCandle | None = None
    for candle in candles:
        opened, closed = candle.open_time_utc, candle.close_time_utc
        if any(moment.utcoffset() != timedelta(0) for moment in (opened, closed)):
            raise WindowUnavailable(UnavailableReason.WINDOW_MALFORMED, "Candle times must be UTC.")
        if (closed - opened).total_seconds() != 604_800:
            raise WindowUnavailable(UnavailableReason.WINDOW_MALFORMED,
                                    "Candles must span exactly one bar.")
        if (int(opened.timestamp()) - 4 * 86_400) % 604_800:
            raise WindowUnavailable(UnavailableReason.WINDOW_MALFORMED,
                                    "Candles must open Monday 00:00 UTC.")
        _require_weekly_not_after_anchor(closed, "1W candle close")
        if previous is not None and opened != previous.close_time_utc:
            raise WindowUnavailable(UnavailableReason.WINDOW_MALFORMED,
                                    "Candles must be ordered and exactly adjacent.")
        prices = (candle.open, candle.high, candle.low, candle.close)
        if not all(math.isfinite(price) and price > 0.0 for price in prices):
            raise WindowUnavailable(UnavailableReason.WINDOW_MALFORMED,
                                    "Candle prices must be finite and positive.")
        if candle.low > candle.high:
            raise WindowUnavailable(UnavailableReason.WINDOW_MALFORMED, "Candle low exceeds high.")
        previous = candle


def anchors_from_candles_v1d(
    candles: Sequence[MarketCandle], *, timeframe: str, band_frac: float,
    spec: ReferenceSpecV1d,
) -> tuple[Anchor, ...]:
    _timeframe(spec, timeframe)
    band = _finite_real(band_frac, "band_frac")
    if band < 0.0:
        raise ValueError("band_frac must be non-negative")
    (require_well_formed_1d if timeframe == "1D" else _require_well_formed_1w)(candles)
    anchors = []
    for index, candle in enumerate(candles):
        end_index = index + spec.horizon_bars
        if end_index >= len(candles):
            break
        if not _on_lattice(candle.close_time_utc, timeframe, spec):
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
    (require_well_formed_1d if timeframe == "1D" else _require_well_formed_1w)(candles)
    reference_close = candles[-1].close_time_utc
    anchors = anchors_from_candles_v1d(
        candles, timeframe=timeframe, band_frac=band_frac, spec=spec
    )
    result = reference_from_anchors_v1d(
        anchors, reference_close_utc=reference_close, timeframe=timeframe,
        spec=spec, prior=prior, deployment_start_utc=deployment_start_utc,
    )
    if timeframe == "1W":
        return ReferenceTripletV1d(
            result.p_up_frac, result.p_down_frac, result.p_timeout_frac,
            result.k, result.t, result.n0_rows, result.memory_days,
            result.deployment_start_utc, None,
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
