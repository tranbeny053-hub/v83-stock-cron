"""PROPOSAL, UNWIRED: nothing outside this package imports this module; it changes no served
number, gate, row, or response. It decides nothing: tolerances, caps, and thresholds are
caller-supplied and PROPOSED-REQUIRES-OWNER-APPROVAL. `load_manifest` validates the S-R3 anchor
kind and explicit custody statements, plus recipe/cell identity; `claim_ready` recognizes only
the declared anchor kind; `artifact_status` checks cell, staleness, and caller-supplied band.
See docs/NG_SCALE_CONTRACTS.md.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from types import MappingProxyType

from crypto_probability_engine.quant import candidate_r4_c1

SCHEMA_VERSION = "quant-ng-artifact.v1"
VENUES = ("BINANCE_PUBLIC", "OKX_PUBLIC")
RECIPES = MappingProxyType({
    candidate_r4_c1.CANDIDATE_NAME: (
        candidate_r4_c1.RECIPE_SHA256,
        candidate_r4_c1.validate_constants,
        candidate_r4_c1.HORIZON_BARS,
        # candidate_r4_c1.RECIPE["venue"] is "BINANCE_PUBLIC spot, same-venue resolution".
        ("BINANCE_PUBLIC",),
    ),
})


class AnchorKind(StrEnum):
    REMOTE_COMMIT = "REMOTE_COMMIT"
    OWNER_APPROVED_ANCHOR = "OWNER_APPROVED_ANCHOR"
    NONE = "NONE"


class IndependentCopy(StrEnum):
    CONFIRMED = "CONFIRMED"
    NONE_PENDING_OWNER_CUSTODY_RULING = "NONE_PENDING_OWNER_CUSTODY_RULING"


class ArtifactStatus(StrEnum):
    ELIGIBLE = "ELIGIBLE"
    CELL_MISMATCH = "CELL_MISMATCH"
    ARTIFACT_STALE = "ARTIFACT_STALE"
    BAND_OUT_OF_RANGE = "BAND_OUT_OF_RANGE"


@dataclass(frozen=True)
class ArtifactManifest:
    artifact_id: str
    recipe_id: str
    recipe_sha256: str
    symbol: str
    venue: str
    timeframe: str
    horizon_bars: int
    training_start_utc: datetime
    training_end_utc: datetime
    band_low: float
    band_high: float
    staleness_cap_days: int
    fitted_at_utc: datetime
    fit_code_sha256: str
    corpus_manifest_sha256: str
    central_quantile: float
    exposures: tuple[str, ...]
    custody_location: str
    independent_copy: IndependentCopy
    freeze_anchor_kind: AnchorKind
    freeze_anchor_ref: str | None
    freeze_anchor_utc: datetime | None
    constants: Mapping[str, object]
    _loaded: bool = field(default=False, repr=False, compare=False)


_FIELDS = frozenset({
    "schema_version", "artifact_id", "recipe_id", "recipe_sha256", "symbol", "venue",
    "timeframe", "horizon_bars", "training_start_utc", "training_end_utc", "band_low",
    "band_high", "staleness_cap_days", "fitted_at_utc", "fit_code_sha256",
    "corpus_manifest_sha256", "central_quantile", "exposures", "custody_location",
    "independent_copy", "freeze_anchor_kind", "freeze_anchor_ref", "freeze_anchor_utc",
    "constants",
})
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_INSTANT = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z\Z")


def _freeze(value: object) -> object:
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


def _field_string(payload: Mapping[str, object], field: str) -> str:
    value = payload[field]
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value


def _sha(payload: Mapping[str, object], field: str) -> str:
    value = _field_string(payload, field)
    if not _SHA256.fullmatch(value):
        raise ValueError(f"{field} must be 64 lowercase hexadecimal characters")
    return value


def _instant(payload: Mapping[str, object], field: str) -> datetime:
    value = payload[field]
    if not isinstance(value, str) or not _INSTANT.fullmatch(value):
        raise ValueError(f"{field} must use YYYY-MM-DDTHH:MM:SSZ")
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError as exc:
        raise ValueError(f"{field} is not a valid UTC instant") from exc


def _number(payload: Mapping[str, object], field: str) -> float:
    value = payload[field]
    if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value):
        raise ValueError(f"{field} must be a finite number")
    return float(value)


def load_manifest(payload: Mapping[str, object]) -> ArtifactManifest:
    """Parse the exact v1 shape, refusing unknown, missing, and invalid fields."""
    if not isinstance(payload, Mapping):
        raise ValueError("manifest must be a mapping")
    unknown = set(payload) - _FIELDS
    if unknown:
        raise ValueError(f"unknown key: {sorted(unknown, key=str)[0]}")
    missing = _FIELDS - set(payload)
    if missing:
        raise ValueError(f"missing field: {sorted(missing)[0]}")
    if payload["schema_version"] != SCHEMA_VERSION:
        raise ValueError("schema_version is unsupported")

    artifact_id = _field_string(payload, "artifact_id")
    recipe_id = _field_string(payload, "recipe_id")
    if recipe_id not in RECIPES:
        raise ValueError("recipe_id is unsupported")
    recipe_sha, validator, recipe_horizon, recipe_venues = RECIPES[recipe_id]
    recipe_digest = _sha(payload, "recipe_sha256")
    if recipe_digest != recipe_sha:
        raise ValueError("recipe_sha256 does not match recipe_id")
    symbol = _field_string(payload, "symbol")
    venue = _field_string(payload, "venue")
    if venue not in VENUES:
        raise ValueError("venue is unsupported")
    if venue not in recipe_venues:
        raise ValueError("venue is not allowed for recipe_id")
    timeframe = _field_string(payload, "timeframe")
    horizon = payload["horizon_bars"]
    if isinstance(horizon, bool) or not isinstance(horizon, int) or horizon != recipe_horizon:
        raise ValueError("horizon_bars does not match recipe")

    constants = payload["constants"]
    if not isinstance(constants, Mapping):
        raise ValueError("constants must be a mapping")
    frozen_constants = _freeze(constants)
    try:
        cells = validator(frozen_constants)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"constants are invalid: {exc}") from exc
    if (symbol, timeframe) not in cells:
        raise ValueError("constants do not contain manifest symbol and timeframe cell")

    training_start = _instant(payload, "training_start_utc")
    training_end = _instant(payload, "training_end_utc")
    fitted_at = _instant(payload, "fitted_at_utc")
    if not training_start < training_end <= fitted_at:
        raise ValueError("training_start_utc/training_end_utc/fitted_at_utc chronology is invalid")
    anchor_kind_raw = payload["freeze_anchor_kind"]
    try:
        anchor_kind = AnchorKind(anchor_kind_raw)
    except (ValueError, TypeError) as exc:
        raise ValueError("freeze_anchor_kind is invalid") from exc
    anchor_ref = payload["freeze_anchor_ref"]
    anchor_time_raw = payload["freeze_anchor_utc"]
    if anchor_kind == AnchorKind.NONE:
        if anchor_ref is not None or anchor_time_raw is not None:
            raise ValueError("freeze_anchor_ref and freeze_anchor_utc must be null for NONE")
        anchor_time = None
    else:
        if not isinstance(anchor_ref, str) or not anchor_ref.strip():
            raise ValueError("freeze_anchor_ref must be non-empty for an anchor")
        anchor_time = _instant(payload, "freeze_anchor_utc")
        if anchor_time < fitted_at:
            raise ValueError("freeze_anchor_utc must be at or after fitted_at_utc")

    low = _number(payload, "band_low")
    high = _number(payload, "band_high")
    if not 0.0 < low <= high < 1.0:
        raise ValueError("band_low/band_high must satisfy 0 < low <= high < 1")
    quantile = _number(payload, "central_quantile")
    if not 0.5 < quantile < 1.0:
        raise ValueError("central_quantile must satisfy 0.5 < value < 1")
    cap = payload["staleness_cap_days"]
    if isinstance(cap, bool) or not isinstance(cap, int) or cap <= 0:
        raise ValueError("staleness_cap_days must be an int greater than zero")
    try:
        timedelta(days=cap)
    except OverflowError as exc:
        raise ValueError("staleness_cap_days cannot be represented as a timedelta") from exc
    exposures_raw = payload["exposures"]
    if (not isinstance(exposures_raw, list)
            or any(not isinstance(item, str) or not item.strip() for item in exposures_raw)):
        raise ValueError("exposures must be a list of non-empty strings")
    custody = _field_string(payload, "custody_location")
    try:
        independent_copy = IndependentCopy(payload["independent_copy"])
    except (ValueError, TypeError) as exc:
        raise ValueError("independent_copy is invalid") from exc

    return ArtifactManifest(
        artifact_id=artifact_id, recipe_id=recipe_id, recipe_sha256=recipe_digest,
        symbol=symbol, venue=venue, timeframe=timeframe, horizon_bars=horizon,
        training_start_utc=training_start, training_end_utc=training_end, band_low=low,
        band_high=high, staleness_cap_days=cap, fitted_at_utc=fitted_at,
        fit_code_sha256=_sha(payload, "fit_code_sha256"),
        corpus_manifest_sha256=_sha(payload, "corpus_manifest_sha256"),
        central_quantile=quantile, exposures=tuple(exposures_raw), custody_location=custody,
        independent_copy=independent_copy, freeze_anchor_kind=anchor_kind,
        freeze_anchor_ref=anchor_ref, freeze_anchor_utc=anchor_time,
        constants=frozen_constants,
        _loaded=True,
    )


def artifact_status(manifest: ArtifactManifest, *, now_utc: datetime, symbol: str,
                    venue: str, timeframe: str, band_frac: float) -> ArtifactStatus:
    """Return cell, age, then band status in contract order (S-R3; see the contract doc)."""
    if not manifest._loaded:
        raise ValueError("build manifests with load_manifest")
    if (not isinstance(now_utc, datetime) or now_utc.tzinfo is None
            or now_utc.utcoffset() != timedelta(0)):
        raise ValueError("now_utc must be a timezone-aware UTC datetime")
    if (isinstance(band_frac, bool) or not isinstance(band_frac, int | float)
            or not math.isfinite(band_frac)):
        raise ValueError("band_frac must be a finite non-boolean number")
    if now_utc < manifest.fitted_at_utc:
        raise ValueError("now_utc cannot precede fitted_at_utc")
    if (symbol != manifest.symbol or venue != manifest.venue or timeframe != manifest.timeframe):
        return ArtifactStatus.CELL_MISMATCH
    if now_utc - manifest.training_end_utc > timedelta(days=manifest.staleness_cap_days):
        return ArtifactStatus.ARTIFACT_STALE
    if (isinstance(band_frac, bool) or not isinstance(band_frac, int | float)
            or not math.isfinite(band_frac)
            or not manifest.band_low <= band_frac <= manifest.band_high):
        return ArtifactStatus.BAND_OUT_OF_RANGE
    return ArtifactStatus.ELIGIBLE


def claim_ready(manifest: ArtifactManifest) -> bool:
    if not manifest._loaded:
        raise ValueError("build manifests with load_manifest")
    return manifest.freeze_anchor_kind != AnchorKind.NONE
