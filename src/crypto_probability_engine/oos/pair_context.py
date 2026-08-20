"""Fail-closed construction of identical-input OOS evaluation pairs."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from math import isfinite
from types import MappingProxyType
from typing import Any

from crypto_probability_engine.adapters.types import MarketSnapshot
from crypto_probability_engine.config.defaults import (
    DEFAULT_PHASE1A,
    TIMEFRAME_SECONDS,
)

OOS_RUN_ID_PATTERN = r"^oosb-[0-9a-f]{32}$"
DERIVATIVES_RUN_ID_PATTERN = r"^cadence-[0-9a-f]{32}$"
OOS_PREDICTION_ORIGIN = "SCHEDULED_SHADOW_EVIDENCE"


class PairInvalidError(ValueError):
    """The proposed pair cannot truthfully claim identical point-in-time inputs."""


class OOSArm(StrEnum):
    BASELINE = "BASELINE"
    CANDIDATE = "CANDIDATE"


@dataclass(frozen=True)
class PairTarget:
    reference_close_utc: datetime
    reference_price: float
    horizon_end_utc: datetime
    decision_band_frac: float


@dataclass(frozen=True)
class CandidateFeature:
    name: str
    value: Any
    point_in_time_utc: datetime


@dataclass(frozen=True)
class OOSArmContext:
    arm: OOSArm
    run_id: str
    market_snapshot: MarketSnapshot
    resolved_skill_evidence: Mapping[str, Any]
    information_cutoff: datetime
    target: PairTarget
    candidate_features: Mapping[str, CandidateFeature]
    decision_influence_frac: float = 0.0
    prediction_origin: str = OOS_PREDICTION_ORIGIN

    @property
    def snapshot(self) -> MarketSnapshot:
        return self.market_snapshot

    @property
    def reference_close_utc(self) -> datetime:
        return self.target.reference_close_utc

    @property
    def reference_price(self) -> float:
        return self.target.reference_price

    @property
    def horizon_end_utc(self) -> datetime:
        return self.target.horizon_end_utc

    @property
    def decision_band_frac(self) -> float:
        return self.target.decision_band_frac


@dataclass(frozen=True)
class OOSPairContext:
    """One atomic pair: target, snapshot, skill state, and cutoff are shared."""

    run_id: str
    market_snapshot: MarketSnapshot
    resolved_skill_evidence: Mapping[str, Any]
    information_cutoff: datetime
    target: PairTarget
    candidate_features: Mapping[str, CandidateFeature]
    decision_influence_frac: float = 0.0
    prediction_origin: str = OOS_PREDICTION_ORIGIN

    @property
    def snapshot(self) -> MarketSnapshot:
        return self.market_snapshot

    def for_arm(self, arm: OOSArm | str) -> OOSArmContext:
        try:
            resolved_arm = OOSArm(arm)
        except (TypeError, ValueError) as exc:
            raise PairInvalidError("OOS arm must be BASELINE or CANDIDATE.") from exc
        features = (
            self.candidate_features
            if resolved_arm is OOSArm.CANDIDATE
            else _EMPTY_FEATURES
        )
        return OOSArmContext(
            arm=resolved_arm,
            run_id=self.run_id,
            market_snapshot=self.market_snapshot,
            resolved_skill_evidence=self.resolved_skill_evidence,
            information_cutoff=self.information_cutoff,
            target=self.target,
            candidate_features=features,
        )


_EMPTY_FEATURES: Mapping[str, CandidateFeature] = MappingProxyType({})


def build_oos_pair_context(
    *,
    market_snapshot: MarketSnapshot,
    resolved_skill_evidence: Mapping[str, Any],
    information_cutoff: datetime,
    decision_band_frac: float,
    candidate_features: (
        Mapping[str, Mapping[str, Any] | CandidateFeature]
        | Iterable[CandidateFeature]
        | None
    ) = None,
) -> OOSPairContext:
    """Build an OOS pair atomically, rejecting any ambiguous feature timestamp."""

    if not isinstance(market_snapshot, MarketSnapshot):
        raise PairInvalidError("A MarketSnapshot is required for an OOS pair.")
    if not isinstance(resolved_skill_evidence, Mapping):
        raise PairInvalidError("Resolved skill evidence is required for an OOS pair.")
    cutoff = _aware_datetime(information_cutoff, "information cutoff")
    target = _derive_target(market_snapshot, decision_band_frac)
    if _aware_datetime(market_snapshot.as_of_utc, "snapshot as-of") > cutoff:
        raise PairInvalidError("Market snapshot is after the information cutoff.")
    admitted = _admit_candidate_features(candidate_features, cutoff)
    run_id = _oos_run_id(market_snapshot, cutoff)
    return OOSPairContext(
        run_id=run_id,
        market_snapshot=market_snapshot,
        resolved_skill_evidence=resolved_skill_evidence,
        information_cutoff=cutoff,
        target=target,
        candidate_features=MappingProxyType(admitted),
    )


def is_oos_run_id(value: object) -> bool:
    return _fullmatch(OOS_RUN_ID_PATTERN, value)


def is_derivatives_run_id(value: object) -> bool:
    return _fullmatch(DERIVATIVES_RUN_ID_PATTERN, value)


def _fullmatch(pattern: str, value: object) -> bool:
    import re

    return isinstance(value, str) and re.fullmatch(pattern, value) is not None


def _derive_target(snapshot: MarketSnapshot, decision_band_frac: float) -> PairTarget:
    if snapshot.timeframe not in TIMEFRAME_SECONDS or not snapshot.candles:
        raise PairInvalidError("Pair target requires a supported timeframe and candle.")
    reference_candle = snapshot.candles[-1]
    reference_close = _aware_datetime(
        reference_candle.close_time_utc, "reference close"
    )
    snapshot_as_of = _aware_datetime(snapshot.as_of_utc, "snapshot as-of")
    if reference_close > snapshot_as_of:
        raise PairInvalidError("Reference close cannot be after the snapshot as-of.")
    try:
        reference_price = float(reference_candle.close)
        band = float(decision_band_frac)
    except (TypeError, ValueError) as exc:
        raise PairInvalidError("Pair target values must be numeric.") from exc
    if (
        not isfinite(reference_price)
        or not isfinite(band)
        or reference_price <= 0.0
        or band < 0.0
    ):
        raise PairInvalidError("Pair target values are outside their valid range.")
    horizon_end = reference_close + timedelta(
        seconds=DEFAULT_PHASE1A.h_primary_bars * TIMEFRAME_SECONDS[snapshot.timeframe]
    )
    return PairTarget(reference_close, reference_price, horizon_end, band)


def _admit_candidate_features(
    raw_features: (
        Mapping[str, Mapping[str, Any] | CandidateFeature]
        | Iterable[CandidateFeature]
        | None
    ),
    cutoff: datetime,
) -> dict[str, CandidateFeature]:
    if raw_features is None:
        return {}
    if isinstance(raw_features, Mapping):
        entries: Iterable[tuple[str, Mapping[str, Any] | CandidateFeature]] = (
            raw_features.items()
        )
    else:
        try:
            entries = ((feature.name, feature) for feature in raw_features)
        except TypeError as exc:
            raise PairInvalidError("Candidate features must be a mapping or iterable.") from exc
    admitted: dict[str, CandidateFeature] = {}
    try:
        for supplied_name, raw in entries:
            feature = _candidate_feature(str(supplied_name), raw)
            if feature.point_in_time_utc > cutoff:
                raise PairInvalidError(
                    f"Candidate feature {feature.name!r} is after the information cutoff."
                )
            if feature.name in admitted:
                raise PairInvalidError("Candidate feature names must be unique.")
            admitted[feature.name] = feature
    except PairInvalidError:
        raise
    except Exception as exc:
        raise PairInvalidError("Candidate feature evidence is invalid.") from exc
    return admitted


def _candidate_feature(
    supplied_name: str,
    raw: Mapping[str, Any] | CandidateFeature,
) -> CandidateFeature:
    if isinstance(raw, CandidateFeature):
        name = raw.name
        value = raw.value
        point_in_time = raw.point_in_time_utc
    elif isinstance(raw, Mapping):
        name = str(raw.get("name") or supplied_name)
        value = raw.get("value")
        point_in_time = raw.get("point_in_time_utc", raw.get("point_in_time"))
    else:
        raise PairInvalidError("Each candidate feature requires timestamp evidence.")
    if not name:
        raise PairInvalidError("Candidate feature name is required.")
    return CandidateFeature(
        name=name,
        value=value,
        point_in_time_utc=_parse_point_in_time(point_in_time, name),
    )


def _parse_point_in_time(value: object, feature_name: str) -> datetime:
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise PairInvalidError(
                f"Candidate feature {feature_name!r} has unparseable point-in-time."
            ) from exc
    try:
        return _aware_datetime(value, f"candidate feature {feature_name!r} point-in-time")
    except PairInvalidError:
        raise


def _aware_datetime(value: object, label: str) -> datetime:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise PairInvalidError(f"{label.capitalize()} must be timezone-aware.")
    return value.astimezone(UTC)


def _oos_run_id(snapshot: MarketSnapshot, cutoff: datetime) -> str:
    reference_close = _aware_datetime(
        snapshot.candles[-1].close_time_utc, "reference close"
    )
    material = "|".join(
        (
            "oos-paired-evidence-v1",
            snapshot.normalized_symbol,
            snapshot.timeframe,
            reference_close.isoformat(),
            cutoff.isoformat(),
        )
    )
    return f"oosb-{hashlib.sha256(material.encode('utf-8')).hexdigest()[:32]}"
