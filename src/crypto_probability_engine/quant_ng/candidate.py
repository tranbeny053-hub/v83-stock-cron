"""PROPOSAL, UNWIRED: C1 candidate triplet behind an eligible artifact manifest.

Nothing outside ``quant_ng`` imports this module. It decides nothing and contains no constants;
the manifest supplies them. C1 only. The zero-probability clip is an evaluation contract only;
this module never clips. The table tail clamp keeps p_up and p_down at least 1/(n+1), while
p_timeout is 0 at band 0 and an evaluator must clip it.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from numbers import Real
from types import MappingProxyType

from crypto_probability_engine.quant import candidate_r4_c1
from crypto_probability_engine.quant_ng import artifact, windows

PROVIDER_VENUES = MappingProxyType({"binance": "BINANCE_PUBLIC", "okx": "OKX_PUBLIC"})
# Evaluation clip of the zero-probability contract (plan v2 §H); this module never clips.
ZERO_PROBABILITY_EPS = 1e-12


class CandidateUnavailableReason(StrEnum):
    RECIPE_UNSUPPORTED = "RECIPE_UNSUPPORTED"
    VENUE_UNKNOWN = "VENUE_UNKNOWN"
    CELL_MISMATCH = "CELL_MISMATCH"
    ARTIFACT_STALE = "ARTIFACT_STALE"
    BAND_OUT_OF_RANGE = "BAND_OUT_OF_RANGE"
    SIGMA_GUARD = "SIGMA_GUARD"
    CENTRAL_QUANTILE_OUT_OF_TABLE = "CENTRAL_QUANTILE_OUT_OF_TABLE"
    CENTRAL_RANGE_DOMAIN = "CENTRAL_RANGE_DOMAIN"


class CandidateUnavailable(Exception):
    """A manifest or C1 candidate cannot provide the requested triplet."""

    def __init__(self, reason: CandidateUnavailableReason, detail: str) -> None:
        self.reason = reason
        self.detail = detail
        super().__init__(f"{reason.value}: {detail}")


@dataclass(frozen=True)
class CandidateTriplet:
    p_up_frac: float
    p_down_frac: float
    p_timeout_frac: float
    sigma_h: float
    band_frac: float
    central_quantile: float
    central_half_width_frac: float
    profile_mean: float
    candles_used: int
    artifact_id: str
    recipe_id: str


def sigma_guard(knots: Sequence[float], sigma_h: float) -> None:
    """Apply the proposed reading: refuse σ_h large enough for −q·σ_h <= −1.

    Here q is the reflected table's extreme knot, in simple-return units. This interpretation
    of the plan's guard is PROPOSED.
    """
    if knots[0] * sigma_h <= -1.0:
        raise CandidateUnavailable(
            CandidateUnavailableReason.SIGMA_GUARD,
            "the reflected table's lowest point reaches or crosses -100%",
        )


def central_half_width(
    knots: Sequence[float], sample_size: int, sigma_h: float, quantile: float
) -> float:
    """Interpolate the named central table range and enforce its simple-return domain."""
    if (isinstance(quantile, bool) or not isinstance(quantile, Real)
            or not math.isfinite(quantile) or not 0.5 < quantile < 1.0):
        raise ValueError("quantile must be a finite non-bool number in (0.5, 1)")
    quantile = float(quantile)
    if quantile > sample_size / (sample_size + 1):
        raise CandidateUnavailable(
            CandidateUnavailableReason.CENTRAL_QUANTILE_OUT_OF_TABLE,
            "quantile exceeds the table's upper tail clamp",
        )
    scaled = quantile * 100
    nearest = round(scaled)
    if abs(scaled - nearest) <= 1e-9:
        z = knots[nearest]
    else:
        lower = math.floor(scaled)
        fraction = scaled - lower
        z = knots[lower] + fraction * (knots[lower + 1] - knots[lower])
    half = z * sigma_h
    if not 0 < half < 1:
        raise CandidateUnavailable(
            CandidateUnavailableReason.CENTRAL_RANGE_DOMAIN,
            "central range must be positive and remain below a 100% simple return",
        )
    return half


def compute_candidate(
    window: windows.Window,
    *,
    manifest: artifact.ArtifactManifest,
    now_utc: datetime,
    band_frac: float,
) -> CandidateTriplet:
    """Delegate C1 arithmetic after the manifest, venue, σ, and central-range guards."""
    if manifest.recipe_id != candidate_r4_c1.CANDIDATE_NAME:
        raise CandidateUnavailable(CandidateUnavailableReason.RECIPE_UNSUPPORTED,
                                   "manifest recipe is not C1")
    venue = PROVIDER_VENUES.get(window.provider)
    if venue is None:
        raise CandidateUnavailable(CandidateUnavailableReason.VENUE_UNKNOWN,
                                   f"unknown provider {window.provider!r}")
    status = artifact.artifact_status(
        manifest, now_utc=now_utc, symbol=window.normalized_symbol, venue=venue,
        timeframe=window.timeframe, band_frac=band_frac,
    )
    if status is not artifact.ArtifactStatus.ELIGIBLE:
        raise CandidateUnavailable(CandidateUnavailableReason(status.value), status.value)
    cells = candidate_r4_c1.validate_constants(manifest.constants)
    cell = cells[(window.normalized_symbol, window.timeframe)]
    result = candidate_r4_c1.compute_r4_c1_probabilities(
        window.candles, symbol=window.normalized_symbol, timeframe=window.timeframe,
        band_frac=band_frac, constants=cells,
    )
    sigma_guard(cell.knots, result.sigma_h)
    central = central_half_width(
        cell.knots, cell.sample_size, result.sigma_h, manifest.central_quantile
    )
    return CandidateTriplet(
        p_up_frac=result.p_up_frac, p_down_frac=result.p_down_frac,
        p_timeout_frac=result.p_timeout_frac, sigma_h=result.sigma_h,
        band_frac=result.band_frac, central_quantile=manifest.central_quantile,
        central_half_width_frac=central, profile_mean=result.profile_mean,
        candles_used=result.candles_used, artifact_id=manifest.artifact_id,
        recipe_id=manifest.recipe_id,
    )
