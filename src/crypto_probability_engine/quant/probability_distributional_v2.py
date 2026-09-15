"""distributional-v2 probability construction (R2 arm CB). PREP ONLY.

NOT WIRED, NOT FROZEN, NOT A METHODOLOGY VERSION. Nothing selects this module: the methodology
selector (``quant/pipeline.py``) and the version constants (``config/defaults.py``) are pinned by
the section 5A evaluator, and wiring, freezing and a new pre-registered holdout are owner decisions.
It exists so that a future freeze decision can inspect a complete, tested implementation.

THE RECIPE is the one R2 evaluated and attested (docs/R2_FRONTIER_REPORT.md §5-6): the contract of
``probability_distributional.py`` (one standardized empirical CDF at the live band, ``mu = 0``, no
runtime fitting) with its single EWMA scale replaced by

- a HAR log-variance regression: ``sigma_h = sqrt(exp(clip(b . x, -60, 20)))`` with ``x`` = 1, the
  logs of the trailing mean squared close-to-close return over 1, 6, 24 bars, one day and one week,
  the logs of the trailing mean Parkinson range variance over 6 and 24 bars, and the log of ``M``,
  the mean calendar-profile multiplier over the next six bar slots; each log is ``log(max(v, 0) +
  EPS)``;
- the calendar profile: UTC hour x weekend on 15m and 1H (48 cells), bar-of-day x weekday on 4H
  (42 cells);
- the empirical shape: one 101-knot table (15m, 4H), or one per UTC session on 1H (hour // 8:
  Asia, Europe, US), with the exact tail clamps ``1/(n+1)`` and ``n/(n+1)``.

Constants are per (symbol, timeframe) for BTC/USDT and ETH/USDT, exactly as R2 fit them. Any other
symbol or timeframe fails closed, as does any window that is not the full required run of closed,
adjacent, well-formed candles: unlike the research code, a served row never falls back to another
scale.
"""

from __future__ import annotations

from bisect import bisect_right
from collections.abc import Sequence
from dataclasses import dataclass
from math import exp, fsum, isfinite, log, sqrt

from crypto_probability_engine.adapters.types import MarketCandle
from crypto_probability_engine.quant.distributional_v2_tables import (
    CELLS,
    DAY_BARS,
    EPS,
    HAR_FEATURES,
    HORIZON_BARS,
    REQUIRED_CANDLES,
    WEEK_BARS,
)
from crypto_probability_engine.utils.invariants import validate_probability_triplet

CANDIDATE_NAME = "distributional-v2"
SUPPORTED_SYMBOLS = frozenset(CELLS)
SUPPORTED_TIMEFRAMES = frozenset(REQUIRED_CANDLES)
BAR_SECONDS = {"15m": 900, "1H": 3_600, "4H": 14_400}
_DAY_SECONDS = 86_400
_SCALE_FLOOR = 1e-9
_LOG_VARIANCE_BOUNDS = (-60.0, 20.0)
_PARKINSON_DENOMINATOR = 4.0 * log(2.0)


@dataclass(frozen=True)
class DistributionalV2Probability:
    p_up_frac: float
    p_down_frac: float
    p_timeout_frac: float
    sigma_h: float
    band_frac: float
    profile_mean: float
    session: int | None
    candles_used: int


def compute_distributional_v2_probabilities(
    candles: Sequence[MarketCandle],
    *,
    symbol: str,
    timeframe: str,
    band_frac: float,
) -> DistributionalV2Probability:
    """Probabilities for the six bars after the last candle, from exactly its trailing window."""

    try:
        cell = CELLS[symbol][timeframe]
    except KeyError as exc:
        raise ValueError(
            f"distributional-v2 does not support {symbol!r} {timeframe!r}; it serves "
            f"{sorted(SUPPORTED_SYMBOLS)} x {sorted(SUPPORTED_TIMEFRAMES)}"
        ) from exc
    # A bool is an int, and float(True) is 1.0: refuse it and any non-number (task-817, F-817-3).
    if isinstance(band_frac, bool) or not isinstance(band_frac, int | float):
        raise ValueError("distributional-v2 requires a real-number band")
    band = float(band_frac)
    if not isfinite(band) or band < 0.0:
        raise ValueError("distributional-v2 requires a finite non-negative band")
    required = REQUIRED_CANDLES[timeframe]
    if len(candles) < required:
        raise ValueError(
            f"distributional-v2 {timeframe} needs {required} closed candles, got {len(candles)}"
        )
    window = tuple(candles[-required:])
    _require_well_formed_window(window, timeframe)

    features = _har_features(window, timeframe)
    last_open = int(window[-1].open_time_utc.timestamp())
    profile_mean = _future_profile_mean(cell["profile"], last_open, timeframe)
    design = (
        1.0,
        *(log(max(features[name], 0.0) + EPS) for name in HAR_FEATURES),
        log(profile_mean + EPS),
    )
    coefficients = cell["coefficients"]
    if len(coefficients) != len(design):
        raise ValueError("distributional-v2 constants do not match the HAR design")
    log_variance = fsum(b * x for b, x in zip(coefficients, design, strict=True))
    log_variance = min(max(log_variance, _LOG_VARIANCE_BOUNDS[0]), _LOG_VARIANCE_BOUNDS[1])
    sigma_h = max(sqrt(exp(log_variance)), _SCALE_FLOOR)

    tables = cell["tables"]
    if cell["shape"] == "G4_session":
        session = min(max(window[-1].open_time_utc.hour // 8, 0), 2)
        knots, probabilities, sample_size = tables[session]
    elif cell["shape"] == "G1_emp101":
        session = None
        knots, probabilities, sample_size = tables[0]
    else:
        raise ValueError(f"unknown distributional-v2 shape {cell['shape']!r}")

    cdf_lo = _empirical_cdf(-band / sigma_h, knots, probabilities, sample_size)
    cdf_hi = _empirical_cdf(band / sigma_h, knots, probabilities, sample_size)
    lower_tail = 1.0 / (sample_size + 1)
    upper_tail = sample_size / (sample_size + 1)
    # v1's exact construction. cdf_hi >= cdf_lo because the band is non-negative and the CDF is
    # monotone, so no component can round below zero, and a zero band gives exactly zero timeout.
    p_down = cdf_lo
    p_up = lower_tail if cdf_hi == upper_tail else 1.0 - cdf_hi
    p_timeout = (
        (sample_size - 1) / (sample_size + 1)
        if cdf_lo == lower_tail and cdf_hi == upper_tail
        else cdf_hi - cdf_lo
    )
    validate_probability_triplet(p_up, p_down, p_timeout)
    return DistributionalV2Probability(
        p_up_frac=p_up,
        p_down_frac=p_down,
        p_timeout_frac=p_timeout,
        sigma_h=sigma_h,
        band_frac=band,
        profile_mean=profile_mean,
        session=session,
        candles_used=required,
    )


def _require_well_formed_window(window: tuple[MarketCandle, ...], timeframe: str) -> None:
    bar = BAR_SECONDS[timeframe]
    previous: MarketCandle | None = None
    for candle in window:
        opened = candle.open_time_utc
        closed = candle.close_time_utc
        for moment in (opened, closed):
            if moment.utcoffset() is None or moment.utcoffset().total_seconds() != 0:
                raise ValueError("distributional-v2 candles must carry UTC times")
        if (closed - opened).total_seconds() != bar:
            raise ValueError(f"distributional-v2 {timeframe} candles must span exactly one bar")
        if int(opened.timestamp()) % bar != 0:
            raise ValueError("distributional-v2 candles must open on a UTC bar boundary")
        if previous is not None and opened != previous.close_time_utc:
            raise ValueError("distributional-v2 candles must be ordered and exactly adjacent")
        prices = (candle.open, candle.high, candle.low, candle.close)
        if not all(isfinite(price) and price > 0.0 for price in prices):
            raise ValueError("distributional-v2 candle prices must be finite and positive")
        if candle.low > candle.high:
            raise ValueError("distributional-v2 candle low exceeds high")
        previous = candle


def _har_features(window: tuple[MarketCandle, ...], timeframe: str) -> dict[str, float]:
    closes = [candle.close for candle in window]
    returns = [closes[index] / closes[index - 1] - 1.0 for index in range(1, len(closes))]
    squared = [value * value for value in returns]
    parkinson = []
    for candle in window:
        log_range = log(candle.high / candle.low)
        parkinson.append(log_range * log_range / _PARKINSON_DENOMINATOR)

    def trailing_mean(values: list[float], count: int) -> float:
        if len(values) < count:
            raise ValueError("distributional-v2 window is shorter than a HAR term")
        return fsum(values[-count:]) / count

    return {
        "rv_1": trailing_mean(squared, 1),
        "rv_6": trailing_mean(squared, 6),
        "rv_24": trailing_mean(squared, 24),
        "rv_day": trailing_mean(squared, DAY_BARS[timeframe]),
        "rv_week": trailing_mean(squared, WEEK_BARS[timeframe]),
        "parkrv_6": trailing_mean(parkinson, 6),
        "parkrv_24": trailing_mean(parkinson, 24),
    }


def calendar_key(open_seconds: int, timeframe: str) -> int:
    """R2's calendar cell for a bar opening at ``open_seconds`` (UTC epoch seconds)."""

    days, seconds_of_day = divmod(open_seconds, _DAY_SECONDS)
    weekday = (days + 3) % 7  # 1970-01-01 was a Thursday; Monday is 0
    if timeframe == "4H":
        return (seconds_of_day // BAR_SECONDS["4H"]) * 7 + weekday
    return (seconds_of_day // 3_600) * 2 + (1 if weekday >= 5 else 0)


def _future_profile_mean(profile: Sequence[float], last_open: int, timeframe: str) -> float:
    bar = BAR_SECONDS[timeframe]
    return (
        fsum(
            profile[calendar_key(last_open + step * bar, timeframe)]
            for step in range(1, HORIZON_BARS + 1)
        )
        / HORIZON_BARS
    )


def _empirical_cdf(
    value: float,
    knots: Sequence[float],
    probabilities: Sequence[float],
    sample_size: int,
) -> float:
    lower_tail = 1.0 / (sample_size + 1)
    upper_tail = sample_size / (sample_size + 1)
    if value < knots[0]:
        return lower_tail
    if value >= knots[-1]:
        return upper_tail
    right = bisect_right(knots, value)
    left = right - 1
    slope = (probabilities[right] - probabilities[left]) / (knots[right] - knots[left])
    interpolated = slope * (value - knots[left]) + probabilities[left]
    return min(max(interpolated, lower_tail), upper_tail)
