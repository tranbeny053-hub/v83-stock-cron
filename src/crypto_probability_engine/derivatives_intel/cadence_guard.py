"""Pure cadence admission guard for derivatives evidence collection.

This module is intentionally side-effect free: no clocks, environment reads,
network access, external calls, database access, or persistence.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from types import MappingProxyType

from crypto_probability_engine.derivatives_intel.schemas import METHODOLOGY_VERSION_V1

CUTOVER_POLICY_ID = "cadence-cutover-okx-v1"
CUTOVER_CLOSE_UTC = datetime(2100, 1, 1, tzinfo=UTC)


class CadenceAdmissionClassification(StrEnum):
    """Stable admission classifications for the manual cadence collector."""

    ADMITTED = "ADMITTED"
    REJECTED_METHODOLOGY_CUTOVER = "REJECTED_METHODOLOGY_CUTOVER"
    REJECTED_OUTSIDE_WINDOW = "REJECTED_OUTSIDE_WINDOW"
    CONFIGURATION_ERROR = "CONFIGURATION_ERROR"


class CadenceAdmissionReason(StrEnum):
    """Stable sanitized admission reasons."""

    ADMITTED = "ADMITTED"
    AT_OR_BEFORE_CUTOVER = "AT_OR_BEFORE_CUTOVER"
    TOO_EARLY = "TOO_EARLY"
    TOO_LATE = "TOO_LATE"
    UNSUPPORTED_TIMEFRAME = "UNSUPPORTED_TIMEFRAME"
    UNSUPPORTED_METHODOLOGY = "UNSUPPORTED_METHODOLOGY"
    NAIVE_REFERENCE_CLOSE = "NAIVE_REFERENCE_CLOSE"
    NAIVE_NOW = "NAIVE_NOW"
    INVALID_WINDOW_CONFIGURATION = "INVALID_WINDOW_CONFIGURATION"


@dataclass(frozen=True, slots=True)
class CadenceWindow:
    """Allowed collection window after a fully closed reference candle."""

    post_close_delay_seconds: int
    max_lateness_seconds: int


@dataclass(frozen=True, slots=True)
class CadenceAdmissionResult:
    """Pure, allowlisted result from cadence admission evaluation."""

    classification: CadenceAdmissionClassification
    reason: CadenceAdmissionReason
    cutover_policy_id: str
    cutover_close_utc: str | None
    reference_close_utc: str | None
    guard_evaluated_at_utc: str | None
    earliest_collection_utc: str | None
    latest_collection_utc: str | None
    window_post_close_delay_seconds: int | None
    window_max_lateness_seconds: int | None
    derivatives_methodology_version: str | None


CADENCE_WINDOWS: Mapping[str, CadenceWindow] = MappingProxyType(
    {
        "1H": CadenceWindow(post_close_delay_seconds=300, max_lateness_seconds=1200),
        "4H": CadenceWindow(post_close_delay_seconds=300, max_lateness_seconds=1800),
    }
)


def evaluate_cadence_admission(
    *,
    methodology_version: object,
    timeframe: str,
    reference_close_utc: datetime,
    now_utc: datetime,
    windows: Mapping[str, CadenceWindow] = CADENCE_WINDOWS,
    cutover_close_utc: datetime = CUTOVER_CLOSE_UTC,
    cutover_policy_id: str = CUTOVER_POLICY_ID,
) -> CadenceAdmissionResult:
    """Return deterministic admission for a candidate cadence observation."""

    methodology = methodology_version if isinstance(methodology_version, str) else None
    if methodology != METHODOLOGY_VERSION_V1:
        return _result(
            CadenceAdmissionClassification.CONFIGURATION_ERROR,
            CadenceAdmissionReason.UNSUPPORTED_METHODOLOGY,
            cutover_policy_id=cutover_policy_id,
            cutover_close_utc=cutover_close_utc,
            methodology_version=methodology,
        )

    window = windows.get(timeframe)
    if window is None:
        return _result(
            CadenceAdmissionClassification.CONFIGURATION_ERROR,
            CadenceAdmissionReason.UNSUPPORTED_TIMEFRAME,
            cutover_policy_id=cutover_policy_id,
            cutover_close_utc=cutover_close_utc,
            methodology_version=methodology,
        )
    if not _valid_window(window):
        return _result(
            CadenceAdmissionClassification.CONFIGURATION_ERROR,
            CadenceAdmissionReason.INVALID_WINDOW_CONFIGURATION,
            cutover_policy_id=cutover_policy_id,
            cutover_close_utc=cutover_close_utc,
            methodology_version=methodology,
        )

    cutover_normalized = _normalize_aware_utc(cutover_close_utc)
    if cutover_normalized is None:
        return _result(
            CadenceAdmissionClassification.CONFIGURATION_ERROR,
            CadenceAdmissionReason.INVALID_WINDOW_CONFIGURATION,
            cutover_policy_id=cutover_policy_id,
            cutover_close_utc=cutover_close_utc,
            methodology_version=methodology,
            window=window,
        )

    reference_normalized = _normalize_aware_utc(reference_close_utc)
    if reference_normalized is None:
        return _result(
            CadenceAdmissionClassification.CONFIGURATION_ERROR,
            CadenceAdmissionReason.NAIVE_REFERENCE_CLOSE,
            cutover_policy_id=cutover_policy_id,
            cutover_close_utc=cutover_normalized,
            methodology_version=methodology,
            window=window,
        )

    now_normalized = _normalize_aware_utc(now_utc)
    if now_normalized is None:
        return _result(
            CadenceAdmissionClassification.CONFIGURATION_ERROR,
            CadenceAdmissionReason.NAIVE_NOW,
            cutover_policy_id=cutover_policy_id,
            cutover_close_utc=cutover_normalized,
            methodology_version=methodology,
            reference_close_utc=reference_normalized,
            window=window,
        )

    earliest = reference_normalized + timedelta(seconds=window.post_close_delay_seconds)
    latest = reference_normalized + timedelta(seconds=window.max_lateness_seconds)

    if reference_normalized <= cutover_normalized:
        return _result(
            CadenceAdmissionClassification.REJECTED_METHODOLOGY_CUTOVER,
            CadenceAdmissionReason.AT_OR_BEFORE_CUTOVER,
            cutover_policy_id=cutover_policy_id,
            cutover_close_utc=cutover_normalized,
            methodology_version=methodology,
            reference_close_utc=reference_normalized,
            guard_evaluated_at_utc=now_normalized,
            window=window,
            earliest_collection_utc=earliest,
            latest_collection_utc=latest,
        )

    if now_normalized < earliest:
        return _result(
            CadenceAdmissionClassification.REJECTED_OUTSIDE_WINDOW,
            CadenceAdmissionReason.TOO_EARLY,
            cutover_policy_id=cutover_policy_id,
            cutover_close_utc=cutover_normalized,
            methodology_version=methodology,
            reference_close_utc=reference_normalized,
            guard_evaluated_at_utc=now_normalized,
            window=window,
            earliest_collection_utc=earliest,
            latest_collection_utc=latest,
        )

    if now_normalized > latest:
        return _result(
            CadenceAdmissionClassification.REJECTED_OUTSIDE_WINDOW,
            CadenceAdmissionReason.TOO_LATE,
            cutover_policy_id=cutover_policy_id,
            cutover_close_utc=cutover_normalized,
            methodology_version=methodology,
            reference_close_utc=reference_normalized,
            guard_evaluated_at_utc=now_normalized,
            window=window,
            earliest_collection_utc=earliest,
            latest_collection_utc=latest,
        )

    return _result(
        CadenceAdmissionClassification.ADMITTED,
        CadenceAdmissionReason.ADMITTED,
        cutover_policy_id=cutover_policy_id,
        cutover_close_utc=cutover_normalized,
        methodology_version=methodology,
        reference_close_utc=reference_normalized,
        guard_evaluated_at_utc=now_normalized,
        window=window,
        earliest_collection_utc=earliest,
        latest_collection_utc=latest,
    )


def _valid_window(window: CadenceWindow) -> bool:
    return (
        isinstance(window.post_close_delay_seconds, int)
        and isinstance(window.max_lateness_seconds, int)
        and window.post_close_delay_seconds >= 0
        and window.max_lateness_seconds >= window.post_close_delay_seconds
    )


def _normalize_aware_utc(value: datetime) -> datetime | None:
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        return None
    return value.astimezone(UTC)


def _format_utc(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _result(
    classification: CadenceAdmissionClassification,
    reason: CadenceAdmissionReason,
    *,
    cutover_policy_id: str,
    cutover_close_utc: datetime,
    methodology_version: str | None,
    reference_close_utc: datetime | None = None,
    guard_evaluated_at_utc: datetime | None = None,
    window: CadenceWindow | None = None,
    earliest_collection_utc: datetime | None = None,
    latest_collection_utc: datetime | None = None,
) -> CadenceAdmissionResult:
    return CadenceAdmissionResult(
        classification=classification,
        reason=reason,
        cutover_policy_id=cutover_policy_id,
        cutover_close_utc=_format_utc(_normalize_aware_utc(cutover_close_utc)),
        reference_close_utc=_format_utc(reference_close_utc),
        guard_evaluated_at_utc=_format_utc(guard_evaluated_at_utc),
        earliest_collection_utc=_format_utc(earliest_collection_utc),
        latest_collection_utc=_format_utc(latest_collection_utc),
        window_post_close_delay_seconds=(
            window.post_close_delay_seconds if window is not None else None
        ),
        window_max_lateness_seconds=(
            window.max_lateness_seconds if window is not None else None
        ),
        derivatives_methodology_version=methodology_version,
    )
