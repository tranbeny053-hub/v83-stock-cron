"""PROPOSAL, UNWIRED: nothing outside this package imports this module; it changes no served
number, gate, row, or response. It decides nothing: every tolerance, cap, and threshold is
caller-supplied and PROPOSED-REQUIRES-OWNER-APPROVAL. `check_row_classes` implements the S-E1,
S-E2, and S-E4 population/timing matrix; `claim_admissible` the S-E1/S-E2 isolation and S-E3
window check; `check_reclassification` S-E2 immutability; `E3Clocks`/`classify_e3` S-C1/S-C2;
and `vector_sha256`, `ReplayRecord`, and `replay_parity_claimable` S-R1. See
docs/NG_SCALE_CONTRACTS.md.
"""

from __future__ import annotations

import hashlib
import math
import re
import struct
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from types import MappingProxyType


class Population(StrEnum):
    E1_OPERATIONAL = "E1_OPERATIONAL"
    E2_RECONSTRUCTION = "E2_RECONSTRUCTION"
    E3_SPACE_ISSUED = "E3_SPACE_ISSUED"
    E4_USER_REQUESTED = "E4_USER_REQUESTED"


class Timing(StrEnum):
    ON_TIME = "ON_TIME"
    LATE = "LATE"
    MISSED = "MISSED"
    RECONSTRUCTED = "RECONSTRUCTED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


ALLOWED_TIMINGS: Mapping[Population, frozenset[Timing]] = MappingProxyType({
    Population.E1_OPERATIONAL: frozenset({Timing.NOT_APPLICABLE}),
    Population.E2_RECONSTRUCTION: frozenset({Timing.RECONSTRUCTED}),
    Population.E3_SPACE_ISSUED: frozenset({Timing.ON_TIME, Timing.LATE, Timing.MISSED}),
    Population.E4_USER_REQUESTED: frozenset({Timing.NOT_APPLICABLE}),
})


def check_row_classes(population: Population, timing: Timing) -> None:
    """Refuse a population and timing class pair outside the contract."""
    try:
        allowed = ALLOWED_TIMINGS[population]
    except (KeyError, TypeError) as exc:
        raise ValueError("population is invalid") from exc
    if timing not in allowed:
        raise ValueError("timing is not allowed for population")


def _require_utc(value: object, field: str) -> datetime:
    if (not isinstance(value, datetime) or value.tzinfo is None
            or value.utcoffset() != timedelta(0)):
        raise ValueError(f"{field} must be a timezone-aware UTC datetime")
    return value


@dataclass(frozen=True)
class IssueTolerances:
    max_issue_delay: timedelta
    max_commit_delay: timedelta

    def __post_init__(self) -> None:
        for field in ("max_issue_delay", "max_commit_delay"):
            value = getattr(self, field)
            if not isinstance(value, timedelta) or value <= timedelta(0):
                raise ValueError(f"{field} must be a positive timedelta")


@dataclass(frozen=True)
class E3Clocks:
    lattice_instant_utc: datetime
    expected_reference_close_utc: datetime
    reference_close_utc: datetime
    source_as_of_utc: datetime
    core_computed_at_utc: datetime
    issued_at_utc: datetime
    commit_db_utc: datetime | None
    horizon_end_utc: datetime

    def __post_init__(self) -> None:
        for field in ("lattice_instant_utc", "expected_reference_close_utc",
                      "reference_close_utc", "source_as_of_utc", "core_computed_at_utc",
                      "issued_at_utc", "horizon_end_utc"):
            _require_utc(getattr(self, field), field)
        if self.commit_db_utc is not None:
            _require_utc(self.commit_db_utc, "commit_db_utc")
        if not (self.reference_close_utc <= self.source_as_of_utc
                <= self.core_computed_at_utc <= self.issued_at_utc < self.horizon_end_utc):
            raise ValueError("app-clock chronology is invalid")


def classify_e3(clocks: E3Clocks, tolerances: IssueTolerances) -> Timing:
    """Classify using DB commit time; tc-v1's two app-clock instants exclude that clock.

    COMMIT_UNKNOWN reconciliation keeps the original issued_at_utc and never re-stamps it;
    LATE rows are reported separately, never dropped and never upgraded.
    """
    if clocks.reference_close_utc != clocks.expected_reference_close_utc:
        return Timing.MISSED
    if clocks.source_as_of_utc < clocks.lattice_instant_utc:
        return Timing.MISSED
    if clocks.commit_db_utc is None:
        return Timing.LATE
    if clocks.issued_at_utc - clocks.lattice_instant_utc > tolerances.max_issue_delay:
        return Timing.LATE
    if clocks.commit_db_utc - clocks.issued_at_utc > tolerances.max_commit_delay:
        return Timing.LATE
    if clocks.commit_db_utc >= clocks.horizon_end_utc:
        return Timing.LATE
    return Timing.ON_TIME


def claim_admissible(*, row_population: Population, claim_population: Population,
                     row_reference_close_utc: datetime,
                     freeze_anchor_utc: datetime | None) -> bool:
    """Check the S-E3 window-after-anchor part for the caller-supplied anchor instant.

    E1 exclusion is defense in depth: claim populations are restricted to E2 or E3, and
    population equality already prevents E1 from matching either one.
    """
    if claim_population not in {Population.E2_RECONSTRUCTION, Population.E3_SPACE_ISSUED}:
        raise ValueError("claim_population must be E2_RECONSTRUCTION or E3_SPACE_ISSUED")
    row_close = _require_utc(row_reference_close_utc, "row_reference_close_utc")
    if freeze_anchor_utc is not None:
        freeze_anchor = _require_utc(freeze_anchor_utc, "freeze_anchor_utc")
    else:
        freeze_anchor = None
    if row_population == Population.E1_OPERATIONAL:
        return False
    if row_population != claim_population:
        return False
    if freeze_anchor is None:
        return False
    return row_close > freeze_anchor


def check_reclassification(old_population: Population, old_timing: Timing,
                           new_population: Population, new_timing: Timing) -> None:
    if old_population != new_population or old_timing != new_timing:
        raise ValueError("row population and timing class are immutable")


class StoragePrecision(StrEnum):
    FLOAT64_EXACT = "FLOAT64_EXACT"
    DECIMAL_EXACT = "DECIMAL_EXACT"
    LOSSY = "LOSSY"


def vector_sha256(values: Sequence[float]) -> str:
    if not isinstance(values, Sequence) or isinstance(values, str | bytes) or not values:
        raise ValueError("values must be a non-empty sequence")
    digest = hashlib.sha256()
    for value in values:
        if (isinstance(value, bool) or not isinstance(value, int | float)
                or not math.isfinite(value)):
            raise ValueError("values must contain finite non-boolean numbers")
        digest.update(struct.pack("<d", value))
    return digest.hexdigest()


_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


@dataclass(frozen=True)
class ReplayRecord:
    input_vector: tuple[float, ...] | None
    input_vector_sha256: str
    retained_bytes_manifest_sha256: str | None
    storage_precision: StoragePrecision

    def __post_init__(self) -> None:
        if not isinstance(self.input_vector_sha256, str) or not _SHA256.fullmatch(
                self.input_vector_sha256):
            raise ValueError("input_vector_sha256 must be 64 lowercase hexadecimal characters")
        if self.retained_bytes_manifest_sha256 is not None and (
                not isinstance(self.retained_bytes_manifest_sha256, str)
                or not _SHA256.fullmatch(self.retained_bytes_manifest_sha256)):
            raise ValueError("retained_bytes_manifest_sha256 must be 64 lowercase hex or None")
        if not isinstance(self.storage_precision, StoragePrecision):
            raise ValueError("storage_precision is invalid")
        if self.input_vector is not None and not isinstance(self.input_vector, tuple):
            raise ValueError("input_vector must be a tuple or None")
        if (self.input_vector is not None
                and vector_sha256(self.input_vector) != self.input_vector_sha256):
            raise ValueError("input_vector_sha256 does not match input_vector")


def replay_parity_claimable(record: ReplayRecord) -> bool:
    return (record.storage_precision != StoragePrecision.LOSSY
            and (record.input_vector is not None
                 or record.retained_bytes_manifest_sha256 is not None))
