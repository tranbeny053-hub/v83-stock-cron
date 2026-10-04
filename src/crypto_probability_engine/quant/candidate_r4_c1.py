"""R4-C1 (``r4-c1-symmetric-cb``): the Phase 4 identity of R4's exact C1 recipe. PREP ONLY.

NOT WIRED, NOT FROZEN, NOT A METHODOLOGY VERSION, NOT CHAMPION. The owner's P4-1 (2026-10-04):
"exact R4 C1 recipe gets a new separately named Phase-4 candidate identity; repository
distributional-v2 remains integration-feasibility only, not champion." Nothing selects this module.
Wiring it, freezing constants and any evidence window are owner decisions (plan §17 PHASE 4-5).

THE RECIPE is R4's C1, "plain symmetric CB" (.work/research3/r4/common4/candidates.py:
``arms.build_spec(tf, {}, start, symmetric=True, mf=False)``, fitted by
``.work/research3/common/cbvariant.fit``), as frozen by the R4 Stage-B commitment (154a75c4…2211):
- the scale: OLS of log(RV6 + EPS) on 1, the logs of the trailing mean squared close-to-close
  return over 1, 6, 24 bars, one day (15m only) and one week, the logs of the trailing mean
  Parkinson variance over 6 and 24 bars, and the log of M, the mean calendar-profile multiplier
  over the next six bar slots; ``sigma_h = sqrt(exp(clip(b . x, -60, 20)))``. On 1H the one-day
  term is dropped: it duplicates the 24-bar term;
- the calendar profile: UTC hour x weekend (48 cells), shrunk with a pseudo-count of 50;
- the shape: ONE table of the REFLECTED standardized sample (z and -z), 101 knots on R2's grid,
  with the tail clamps 1/(n+1) and n/(n+1), n being the original sample size. So p_up equals
  p_down, up to interpolation roundoff.

It is not distributional-v2 (.work/roadmap/phase4/CANDIDATE_IDENTITY.md, sealed): that is R2's arm
CB, with an asymmetric shape, per-session tables on 1H, rv_day kept and R2's own fitted constants.
This module shares no code with it, so a change there cannot reach this identity.

TIMEFRAMES: 15m and 1H, the ones R4 carried. 4H is refused: R4 did not score it.

CONSTANTS: none exist. They come only from a D4-authorized DEV refit (OP-1,
.work/roadmap/phase4/D4_CLASSIFICATION_NOTE.md). Until then every call fails closed with
CandidateNotFrozenError. ``validate_constants`` refuses anything that is not this recipe: another
name or recipe digest, a wrong coefficient count, a non-symmetric or non-monotone table, or a wrong
profile.
"""

from __future__ import annotations

import hashlib
import json
from bisect import bisect_right
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from math import exp, fsum, isfinite, log, sqrt
from types import MappingProxyType

from crypto_probability_engine.adapters.types import MarketCandle
from crypto_probability_engine.utils.invariants import validate_probability_triplet

CANDIDATE_NAME = "r4-c1-symmetric-cb"
SUPPORTED_SYMBOLS = ("BTC/USDT", "ETH/USDT")
SUPPORTED_TIMEFRAMES = ("15m", "1H")
HORIZON_BARS = 6
EPS = 1e-10
KNOTS = 101
# R2's grid, numpy.linspace(0.0, 1.0, 101), value for value: i * 0.01, and exactly 1.0 last.
PROBABILITY_GRID = tuple(index * 0.01 for index in range(KNOTS - 1)) + (1.0,)
PROFILE_CELLS = 48
PROFILE_PSEUDO_COUNT = 50.0
CENTRAL_RANGE = 0.80
BAR_SECONDS = MappingProxyType({"15m": 900, "1H": 3_600})
DAY_BARS = MappingProxyType({"15m": 96, "1H": 24})
WEEK_BARS = MappingProxyType({"15m": 672, "1H": 168})
# The one-week term needs WEEK_BARS returns, so WEEK_BARS + 1 closed candles.
REQUIRED_CANDLES = MappingProxyType({"15m": 673, "1H": 169})
HAR_FEATURES = MappingProxyType({
    "15m": ("rv_1", "rv_6", "rv_24", "rv_day", "rv_week", "parkrv_6", "parkrv_24"),
    "1H": ("rv_1", "rv_6", "rv_24", "rv_week", "parkrv_6", "parkrv_24"),
})

# The recipe's identity, canonical. RECIPE_SHA256 pins it, and a test recomputes it.
RECIPE = MappingProxyType({
    "candidate": CANDIDATE_NAME,
    "source": ("R4 C1, plain symmetric CB (common4/candidates.py spec_for('C1', tf); "
               "common/cbvariant.fit)"),
    "estimator": "ols on log(rv6_fut + eps)",
    "har": {tf: list(names) for tf, names in HAR_FEATURES.items()},
    "profile": {"keys": "utc_hour x weekend", "cells": PROFILE_CELLS,
                "pseudo_count": PROFILE_PSEUDO_COUNT},
    "shape": {"tables": 1, "symmetric": True, "knots": KNOTS, "grid": "linspace(0, 1, 101)",
              "tail_clamp": "1/(n+1), n/(n+1), n = the original sample size"},
    "train_from_index": "WEEK_BARS + 6",
    "horizon_bars": HORIZON_BARS,
    "log_variance_clip": [-60.0, 20.0],
    "timeframes": list(SUPPORTED_TIMEFRAMES),
    "venue": "BINANCE_PUBLIC spot, same-venue resolution",
})
RECIPE_SHA256 = hashlib.sha256(
    json.dumps(dict(RECIPE), sort_keys=True, separators=(",", ":")).encode("utf-8")
).hexdigest()
R4_PROVENANCE = MappingProxyType({
    "stage_b_commitment_sha256": "154a75c48d89bb3e9ff76914b4b1926d91fecc4a48bf9448c1e4f93b628e2211",
    "closure_record_sha256": "2d345356c3f281a55b04bcca3ae1cbfc88ff0027472098095713ce68bc6f2626",
    "carried": ("15m", "1H"),
    "status": ("HISTORICALLY CONFIRMED (R4, 15m and 1H). It attaches to the recipe under R4's "
               "refit protocol, never to a fitted table, and never transfers to another venue, "
               "timeframe or recipe"),
})

_SCALE_FLOOR = 1e-9
_LOG_VARIANCE_BOUNDS = (-60.0, 20.0)
_PARKINSON_DENOMINATOR = 4.0 * log(2.0)
_DAY_SECONDS = 86_400
_SYMMETRY_TOLERANCE = 1e-9


class CandidateNotFrozenError(RuntimeError):
    """R4-C1 has no frozen constants: a D4-authorized DEV refit (OP-1) must produce them first."""


@dataclass(frozen=True)
class R4C1Cell:
    coefficients: tuple[float, ...]
    profile: tuple[float, ...]
    knots: tuple[float, ...]
    sample_size: int


@dataclass(frozen=True)
class R4C1Probability:
    p_up_frac: float
    p_down_frac: float
    p_timeout_frac: float
    sigma_h: float
    band_frac: float
    central_range_half_width_frac: float
    profile_mean: float
    candles_used: int


def _finite_numbers(values: object, what: str) -> tuple[float, ...]:
    if not isinstance(values, Sequence) or isinstance(values, str | bytes):
        raise ValueError(f"R4-C1 {what} must be a sequence of numbers")
    out = []
    for value in values:
        if isinstance(value, bool) or not isinstance(value, int | float) or not isfinite(value):
            raise ValueError(f"R4-C1 {what} must be finite numbers")
        out.append(float(value))
    return tuple(out)


def validate_constants(payload: Mapping[str, object]) -> dict[tuple[str, str], R4C1Cell]:
    """The frozen constants as cells, or ValueError when they are not exactly this recipe's."""

    if not isinstance(payload, Mapping):
        raise ValueError("R4-C1 constants must be a mapping")
    if payload.get("candidate") != CANDIDATE_NAME:
        raise ValueError("R4-C1 constants name another candidate")
    if payload.get("recipe_sha256") != RECIPE_SHA256:
        raise ValueError("R4-C1 constants were fitted for another recipe")
    cells = payload.get("cells")
    if not isinstance(cells, Mapping) or not cells:
        raise ValueError("R4-C1 constants carry no cells")
    out: dict[tuple[str, str], R4C1Cell] = {}
    for symbol, by_timeframe in cells.items():
        if symbol not in SUPPORTED_SYMBOLS or not isinstance(by_timeframe, Mapping):
            raise ValueError(f"R4-C1 does not serve {symbol!r}")
        for timeframe, cell in by_timeframe.items():
            if timeframe not in SUPPORTED_TIMEFRAMES or not isinstance(cell, Mapping):
                raise ValueError(f"R4-C1 does not serve {timeframe!r}")
            out[(symbol, timeframe)] = _validated_cell(cell, timeframe)
    return out


def _validated_cell(cell: Mapping[str, object], timeframe: str) -> R4C1Cell:
    coefficients = _finite_numbers(cell.get("coefficients"), "coefficients")
    wanted = len(HAR_FEATURES[timeframe]) + 2
    if len(coefficients) != wanted:
        raise ValueError(f"R4-C1 {timeframe} needs {wanted} coefficients")
    profile = _finite_numbers(cell.get("profile"), "profile")
    if len(profile) != PROFILE_CELLS or min(profile) <= 0.0:
        raise ValueError(f"R4-C1 needs {PROFILE_CELLS} positive profile multipliers")
    knots = _finite_numbers(cell.get("knots"), "knots")
    if len(knots) != KNOTS or any(b <= a for a, b in zip(knots, knots[1:], strict=False)):
        raise ValueError(f"R4-C1 needs {KNOTS} strictly increasing knots")
    scale = max(abs(knots[0]), abs(knots[-1]))
    if any(abs(knots[i] + knots[KNOTS - 1 - i]) > _SYMMETRY_TOLERANCE * scale
           for i in range(KNOTS)):
        raise ValueError("R4-C1 tables are symmetric by recipe; this one is not")
    sample_size = cell.get("sample_size")
    if isinstance(sample_size, bool) or not isinstance(sample_size, int) or sample_size < 1:
        raise ValueError("R4-C1 needs the table's original sample size")
    return R4C1Cell(coefficients, profile, knots, sample_size)


def compute_r4_c1_probabilities(
    candles: Sequence[MarketCandle],
    *,
    symbol: str,
    timeframe: str,
    band_frac: float,
    constants: Mapping[tuple[str, str], R4C1Cell] | None,
) -> R4C1Probability:
    """Probabilities and the central 80% range for the six bars after the last candle.

    Fails closed: no constants, an unserved symbol or timeframe, a bad band or a bad window all
    raise, and nothing falls back to another scale.
    """

    if constants is None:
        raise CandidateNotFrozenError(
            "R4-C1 constants are not frozen: a D4-authorized DEV refit (OP-1) must produce them"
        )
    if symbol not in SUPPORTED_SYMBOLS or timeframe not in SUPPORTED_TIMEFRAMES:
        raise ValueError(
            f"R4-C1 does not serve {symbol!r} {timeframe!r}; it serves "
            f"{list(SUPPORTED_SYMBOLS)} x {list(SUPPORTED_TIMEFRAMES)}"
        )
    cell = constants.get((symbol, timeframe))
    if not isinstance(cell, R4C1Cell):
        raise CandidateNotFrozenError(f"R4-C1 has no frozen constants for {symbol} {timeframe}")
    if isinstance(band_frac, bool) or not isinstance(band_frac, int | float):
        raise ValueError("R4-C1 requires a real-number band")
    band = float(band_frac)
    if not isfinite(band) or band < 0.0:
        raise ValueError("R4-C1 requires a finite non-negative band")
    required = REQUIRED_CANDLES[timeframe]
    if len(candles) < required:
        raise ValueError(f"R4-C1 {timeframe} needs {required} closed candles, got {len(candles)}")
    window = tuple(candles[-required:])
    _require_well_formed_window(window, timeframe)

    features = _har_features(window, timeframe)
    last_open = int(window[-1].open_time_utc.timestamp())
    profile_mean = _future_profile_mean(cell.profile, last_open, timeframe)
    design = (
        1.0,
        *(log(max(features[name], 0.0) + EPS) for name in HAR_FEATURES[timeframe]),
        log(profile_mean + EPS),
    )
    log_variance = fsum(b * x for b, x in zip(cell.coefficients, design, strict=True))
    log_variance = min(max(log_variance, _LOG_VARIANCE_BOUNDS[0]), _LOG_VARIANCE_BOUNDS[1])
    sigma_h = max(sqrt(exp(log_variance)), _SCALE_FLOOR)

    n = cell.sample_size
    lower_tail, upper_tail = 1.0 / (n + 1), n / (n + 1)
    cdf_lo = _cdf(-band / sigma_h, cell.knots, n)
    cdf_hi = _cdf(band / sigma_h, cell.knots, n)
    # R2's _triplets (r2/arms.py), exactly: p_down from the lower CDF, p_up from the upper one,
    # and the timeout closes the sum. The symmetric shape makes p_up equal p_down up to roundoff.
    p_down = cdf_lo
    p_up = lower_tail if cdf_hi == upper_tail else 1.0 - cdf_hi
    p_timeout = 1.0 - p_up - p_down
    validate_probability_triplet(p_up, p_down, p_timeout)
    central = round((0.5 + CENTRAL_RANGE / 2) * (KNOTS - 1))
    return R4C1Probability(
        p_up_frac=p_up,
        p_down_frac=p_down,
        p_timeout_frac=p_timeout,
        sigma_h=sigma_h,
        band_frac=band,
        central_range_half_width_frac=cell.knots[central] * sigma_h,
        profile_mean=profile_mean,
        candles_used=required,
    )


def _require_well_formed_window(window: tuple[MarketCandle, ...], timeframe: str) -> None:
    bar = BAR_SECONDS[timeframe]
    previous: MarketCandle | None = None
    for candle in window:
        opened, closed = candle.open_time_utc, candle.close_time_utc
        for moment in (opened, closed):
            if moment.utcoffset() is None or moment.utcoffset().total_seconds() != 0:
                raise ValueError("R4-C1 candles must carry UTC times")
        if (closed - opened).total_seconds() != bar:
            raise ValueError(f"R4-C1 {timeframe} candles must span exactly one bar")
        if int(opened.timestamp()) % bar != 0:
            raise ValueError("R4-C1 candles must open on a UTC bar boundary")
        if previous is not None and opened != previous.close_time_utc:
            raise ValueError("R4-C1 candles must be ordered and exactly adjacent")
        prices = (candle.open, candle.high, candle.low, candle.close)
        if not all(isfinite(price) and price > 0.0 for price in prices):
            raise ValueError("R4-C1 candle prices must be finite and positive")
        if candle.low > candle.high:
            raise ValueError("R4-C1 candle low exceeds high")
        previous = candle


def _har_features(window: tuple[MarketCandle, ...], timeframe: str) -> dict[str, float]:
    closes = [candle.close for candle in window]
    squared = [(closes[i] / closes[i - 1] - 1.0) ** 2 for i in range(1, len(closes))]
    parkinson = [log(candle.high / candle.low) ** 2 / _PARKINSON_DENOMINATOR for candle in window]

    def trailing_mean(values: list[float], count: int) -> float:
        if len(values) < count:
            raise ValueError("R4-C1 window is shorter than a HAR term")
        return fsum(values[-count:]) / count

    every = {
        "rv_1": trailing_mean(squared, 1),
        "rv_6": trailing_mean(squared, 6),
        "rv_24": trailing_mean(squared, 24),
        "rv_day": trailing_mean(squared, DAY_BARS[timeframe]),
        "rv_week": trailing_mean(squared, WEEK_BARS[timeframe]),
        "parkrv_6": trailing_mean(parkinson, 6),
        "parkrv_24": trailing_mean(parkinson, 24),
    }
    return {name: every[name] for name in HAR_FEATURES[timeframe]}


def calendar_key(open_seconds: int) -> int:
    """The profile cell of a bar opening at ``open_seconds`` (UTC epoch seconds): hour x weekend."""

    days, seconds_of_day = divmod(open_seconds, _DAY_SECONDS)
    weekday = (days + 3) % 7  # 1970-01-01 was a Thursday; Monday is 0
    return (seconds_of_day // 3_600) * 2 + (1 if weekday >= 5 else 0)


def _future_profile_mean(profile: Sequence[float], last_open: int, timeframe: str) -> float:
    bar = BAR_SECONDS[timeframe]
    return fsum(
        profile[calendar_key(last_open + step * bar)] for step in range(1, HORIZON_BARS + 1)
    ) / HORIZON_BARS


def _cdf(value: float, knots: Sequence[float], sample_size: int) -> float:
    lower_tail, upper_tail = 1.0 / (sample_size + 1), sample_size / (sample_size + 1)
    if value < knots[0]:
        return lower_tail
    if value >= knots[-1]:
        return upper_tail
    right = bisect_right(knots, value)
    left = right - 1
    slope = (PROBABILITY_GRID[right] - PROBABILITY_GRID[left]) / (knots[right] - knots[left])
    interpolated = slope * (value - knots[left]) + PROBABILITY_GRID[left]
    return min(max(interpolated, lower_tail), upper_tail)
