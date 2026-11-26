"""Pure pooled reference over a validated candle window."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from numbers import Real
from types import MappingProxyType

from crypto_probability_engine.adapters.types import MarketCandle
from crypto_probability_engine.config.defaults import DEFAULT_PHASE1A
from crypto_probability_engine.quant_ng.reference import Label, label
from crypto_probability_engine.quant_ng.windows import (
    TIMEFRAME_SECONDS,
    WindowUnavailable,
    require_well_formed,
)
from crypto_probability_engine.utils.invariants import validate_probability_triplet

METHODOLOGY_VERSION = "reference-pooled-tk-v1"
REFERENCE_METHODOLOGY_VERSION = METHODOLOGY_VERSION
NAMED_CELLS = frozenset(
    (symbol, timeframe)
    for symbol in ("BTC/USDT", "ETH/USDT", "SOL/USDT")
    for timeframe in ("15m", "1H", "4H")
)
HORIZON_BARS = 6
LATTICE_BARS = 3
MEMORY_DAYS = MappingProxyType({"15m": 7, "1H": 28, "4H": 28})
OUTCOME_OVERLAP = "HALF"
SEMANTICS = "TERMINAL_INSIDE_BAND"

if HORIZON_BARS != DEFAULT_PHASE1A.h_primary_bars:
    raise RuntimeError("the pooled reference horizon must equal H_primary")
if not all(
    days * 86_400 % (LATTICE_BARS * TIMEFRAME_SECONDS[timeframe]) == 0
    for timeframe, days in MEMORY_DAYS.items()
):
    raise RuntimeError("every memory must hold a whole number of lattice steps")


class RefusalReason(StrEnum):
    TIMEFRAME_UNSUPPORTED = "TIMEFRAME_UNSUPPORTED"
    BAND_UNAVAILABLE = "BAND_UNAVAILABLE"
    WINDOW_SHORT = "WINDOW_SHORT"
    WINDOW_MALFORMED = "WINDOW_MALFORMED"
    K_MISMATCH = "K_MISMATCH"


class PooledReferenceUnavailable(Exception):
    def __init__(self, reason: RefusalReason, detail: str) -> None:
        self.reason = reason
        self.detail = detail
        super().__init__(f"{reason.value}: {detail}")


def build_reference_probability_state(ref: PooledReference, *, epistemic_state: dict) -> dict:
    """Build the standard probability payload for the pooled reference."""
    status = "OK" if epistemic_state.get("action") == "ALLOW" else "NULL"
    null_reason = None if status == "OK" else epistemic_state.get("reason", "EPISTEMIC_VOID")
    horizons = {}
    for horizon in ("H_primary",):
        validate_probability_triplet(ref.p_up_frac, ref.p_down_frac, ref.p_timeout_frac)
        horizons[horizon] = {
            "p_up_frac": ref.p_up_frac,
            "p_down_frac": ref.p_down_frac,
            "p_timeout_frac": ref.p_timeout_frac,
            "p_up_user_norm_frac": 0.5,
            "p_down_user_norm_frac": 0.5,
            "confidence_frac": 0.0,
            "news_confidence_adj_frac": 0.0,
            "status": status,
            "null_reason": null_reason,
        }
    return {
        "schema_version": "1.1-crypto-probability",
        "horizons": horizons,
        "calibration_status": DEFAULT_PHASE1A.calibration_status,
        "null_reason": null_reason,
    }


def build_reference_timeout_state(ref: PooledReference, *, window_source: str) -> dict:
    """Build the horizon timeout payload for the pooled reference."""
    return {
        "status": "OK",
        "method": METHODOLOGY_VERSION,
        "p_timeout_frac": ref.p_timeout_frac,
        "timeout_is_directional": False,
        "timeframe": ref.timeframe,
        "band_frac": ref.band_frac,
        "inside_band_count": ref.inside_band_count,
        "matured_outcome_count": ref.matured_outcome_count,
        "memory_days": ref.memory_days,
        "lattice_bars": ref.lattice_bars,
        "horizon_bars": ref.horizon_bars,
        "outcome_overlap": ref.outcome_overlap,
        "window_first_close_utc": ref.window_first_close_utc.isoformat().replace("+00:00", "Z"),
        "window_last_close_utc": ref.window_last_close_utc.isoformat().replace("+00:00", "Z"),
        "window_source": window_source,
        "semantics": SEMANTICS,
    }


def bars_required(timeframe: str) -> int:
    if timeframe not in MEMORY_DAYS:
        raise PooledReferenceUnavailable(
            RefusalReason.TIMEFRAME_UNSUPPORTED, f"Unsupported timeframe {timeframe!r}."
        )
    return MEMORY_DAYS[timeframe] * 86_400 // TIMEFRAME_SECONDS[timeframe] + HORIZON_BARS


def expected_k(timeframe: str) -> int:
    if timeframe not in MEMORY_DAYS:
        raise PooledReferenceUnavailable(
            RefusalReason.TIMEFRAME_UNSUPPORTED, f"Unsupported timeframe {timeframe!r}."
        )
    return MEMORY_DAYS[timeframe] * 86_400 // (LATTICE_BARS * TIMEFRAME_SECONDS[timeframe])


@dataclass(frozen=True)
class PooledReference:
    p_up_frac: float
    p_down_frac: float
    p_timeout_frac: float
    inside_band_count: int
    matured_outcome_count: int
    memory_days: int
    lattice_bars: int
    horizon_bars: int
    band_frac: float
    timeframe: str
    window_first_close_utc: datetime
    window_last_close_utc: datetime
    outcome_overlap: str
    semantics: str
    methodology_version: str


def compute_pooled_reference(
    candles: Sequence[MarketCandle], *, timeframe: str, band_frac: object
) -> PooledReference:
    if timeframe not in MEMORY_DAYS:
        raise PooledReferenceUnavailable(
            RefusalReason.TIMEFRAME_UNSUPPORTED, f"Unsupported timeframe {timeframe!r}."
        )
    try:
        valid_band = (
            not isinstance(band_frac, bool)
            and isinstance(band_frac, Real)
            and math.isfinite(band_frac)
            and band_frac >= 0
        )
    except (OverflowError, TypeError, ValueError):
        valid_band = False
    if not valid_band:
        raise PooledReferenceUnavailable(
            RefusalReason.BAND_UNAVAILABLE,
            "band_frac must be a finite non-bool number greater than or equal to zero.",
        )
    band = float(band_frac)
    try:
        require_well_formed(candles, timeframe)
    except WindowUnavailable as exc:
        raise PooledReferenceUnavailable(RefusalReason.WINDOW_MALFORMED, exc.detail) from exc

    needed = bars_required(timeframe)
    if len(candles) < needed:
        raise PooledReferenceUnavailable(
            RefusalReason.WINDOW_SHORT,
            f"Window has {len(candles)} candles; {needed} are required.",
        )
    window = candles[-needed:]
    ref = window[-1].close_time_utc
    memory = timedelta(days=MEMORY_DAYS[timeframe])
    lattice_seconds = LATTICE_BARS * TIMEFRAME_SECONDS[timeframe]
    matured = 0
    inside = 0
    for index in range(len(window)):
        if index + HORIZON_BARS >= len(window):
            continue
        anchor = window[index]
        if int(anchor.close_time_utc.timestamp()) % lattice_seconds != 0:
            continue
        end = window[index + HORIZON_BARS]
        if end.close_time_utc <= ref and end.close_time_utc > ref - memory:
            matured += 1
            result = label(end.close / anchor.close - 1.0, band)
            if result is Label.TIMEOUT:
                inside += 1

    expected = expected_k(timeframe)
    if matured != expected:
        raise PooledReferenceUnavailable(
            RefusalReason.K_MISMATCH,
            f"Selected matured outcome count {matured} does not match expected {expected}.",
        )
    p_timeout = inside / matured
    side = (1.0 - p_timeout) / 2.0
    validate_probability_triplet(side, side, p_timeout)
    return PooledReference(
        p_up_frac=side,
        p_down_frac=side,
        p_timeout_frac=p_timeout,
        inside_band_count=inside,
        matured_outcome_count=matured,
        memory_days=MEMORY_DAYS[timeframe],
        lattice_bars=LATTICE_BARS,
        horizon_bars=HORIZON_BARS,
        band_frac=band,
        timeframe=timeframe,
        window_first_close_utc=window[0].close_time_utc,
        window_last_close_utc=window[-1].close_time_utc,
        outcome_overlap=OUTCOME_OVERLAP,
        semantics=SEMANTICS,
        methodology_version=METHODOLOGY_VERSION,
    )
