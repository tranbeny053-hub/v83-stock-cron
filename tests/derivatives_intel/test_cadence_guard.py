from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest

from crypto_probability_engine.derivatives_intel.cadence_guard import (
    CADENCE_WINDOWS,
    CUTOVER_CLOSE_UTC,
    CUTOVER_POLICY_ID,
    CadenceAdmissionClassification,
    CadenceAdmissionReason,
    CadenceWindow,
    evaluate_cadence_admission,
)
from crypto_probability_engine.derivatives_intel.schemas import METHODOLOGY_VERSION_V1

REFERENCE_AFTER_CUTOVER = datetime(2100, 1, 1, 1, 0, tzinfo=UTC)


def test_frozen_cadence_policy_2d2f_contract() -> None:
    assert CUTOVER_POLICY_ID == "cadence-cutover-okx-v1"
    assert CUTOVER_CLOSE_UTC == datetime(2026, 7, 14, 8, 0, tzinfo=UTC)
    assert CADENCE_WINDOWS["1H"] == CadenceWindow(
        post_close_delay_seconds=300,
        max_lateness_seconds=1200,
    )
    assert CADENCE_WINDOWS["4H"] == CadenceWindow(
        post_close_delay_seconds=300,
        max_lateness_seconds=1800,
    )
    assert set(CADENCE_WINDOWS) == {"1H", "4H"}


def test_cutover_activation_is_utc_and_four_hour_aligned() -> None:
    assert CUTOVER_CLOSE_UTC.hour % 4 == 0
    assert CUTOVER_CLOSE_UTC.minute == 0
    assert CUTOVER_CLOSE_UTC.second == 0
    assert CUTOVER_CLOSE_UTC.microsecond == 0
    assert CUTOVER_CLOSE_UTC.utcoffset() == timedelta(0)


def _admit(**overrides):
    values = {
        "methodology_version": METHODOLOGY_VERSION_V1,
        "timeframe": "1H",
        "reference_close_utc": REFERENCE_AFTER_CUTOVER,
        "now_utc": REFERENCE_AFTER_CUTOVER + timedelta(minutes=5),
    }
    values.update(overrides)
    return evaluate_cadence_admission(**values)


def test_admits_only_after_cutover_inside_timeframe_window() -> None:
    result = _admit()

    assert result.classification == CadenceAdmissionClassification.ADMITTED
    assert result.reason == CadenceAdmissionReason.ADMITTED
    assert result.cutover_policy_id == CUTOVER_POLICY_ID
    assert result.cutover_close_utc == "2026-07-14T08:00:00Z"
    assert result.reference_close_utc == "2100-01-01T01:00:00Z"
    assert result.guard_evaluated_at_utc == "2100-01-01T01:05:00Z"
    assert result.earliest_collection_utc == "2100-01-01T01:05:00Z"
    assert result.latest_collection_utc == "2100-01-01T01:20:00Z"
    assert result.window_post_close_delay_seconds == 300
    assert result.window_max_lateness_seconds == 1200
    assert result.derivatives_methodology_version == METHODOLOGY_VERSION_V1


def test_rejects_reference_at_or_before_cutover_before_window_checks() -> None:
    result = _admit(
        reference_close_utc=CUTOVER_CLOSE_UTC,
        now_utc=CUTOVER_CLOSE_UTC + timedelta(minutes=5),
    )

    assert result.classification == (CadenceAdmissionClassification.REJECTED_METHODOLOGY_CUTOVER)
    assert result.reason == CadenceAdmissionReason.AT_OR_BEFORE_CUTOVER
    assert result.earliest_collection_utc == "2026-07-14T08:05:00Z"
    assert result.latest_collection_utc == "2026-07-14T08:20:00Z"


@pytest.mark.parametrize("timeframe", ["1H", "4H"])
@pytest.mark.parametrize(
    "reference_close_utc",
    [
        datetime(2026, 7, 14, 8, 0, tzinfo=UTC),
        datetime(2026, 7, 14, 7, 0, tzinfo=UTC),
        datetime(2026, 1, 1, 0, 0, tzinfo=UTC),
    ],
)
def test_cutover_rejects_boundary_and_historical_backfill(
    timeframe: str,
    reference_close_utc: datetime,
) -> None:
    result = _admit(
        timeframe=timeframe,
        reference_close_utc=reference_close_utc,
        now_utc=datetime(2026, 7, 14, 12, 5, tzinfo=UTC),
    )

    assert result.classification == (CadenceAdmissionClassification.REJECTED_METHODOLOGY_CUTOVER)
    assert result.reason == CadenceAdmissionReason.AT_OR_BEFORE_CUTOVER


@pytest.mark.parametrize(
    ("now_utc", "classification", "reason"),
    [
        (
            datetime(2026, 7, 14, 9, 4, 59, tzinfo=UTC),
            CadenceAdmissionClassification.REJECTED_OUTSIDE_WINDOW,
            CadenceAdmissionReason.TOO_EARLY,
        ),
        (
            datetime(2026, 7, 14, 9, 5, tzinfo=UTC),
            CadenceAdmissionClassification.ADMITTED,
            CadenceAdmissionReason.ADMITTED,
        ),
        (
            datetime(2026, 7, 14, 9, 20, tzinfo=UTC),
            CadenceAdmissionClassification.ADMITTED,
            CadenceAdmissionReason.ADMITTED,
        ),
        (
            datetime(2026, 7, 14, 9, 20, 1, tzinfo=UTC),
            CadenceAdmissionClassification.REJECTED_OUTSIDE_WINDOW,
            CadenceAdmissionReason.TOO_LATE,
        ),
    ],
)
def test_first_one_hour_close_cadence_boundary(
    now_utc: datetime,
    classification: CadenceAdmissionClassification,
    reason: CadenceAdmissionReason,
) -> None:
    result = _admit(
        reference_close_utc=datetime(2026, 7, 14, 9, 0, tzinfo=UTC),
        now_utc=now_utc,
    )

    assert result.classification == classification
    assert result.reason == reason


@pytest.mark.parametrize(
    ("now_utc", "classification", "reason"),
    [
        (
            datetime(2026, 7, 14, 12, 4, 59, tzinfo=UTC),
            CadenceAdmissionClassification.REJECTED_OUTSIDE_WINDOW,
            CadenceAdmissionReason.TOO_EARLY,
        ),
        (
            datetime(2026, 7, 14, 12, 5, tzinfo=UTC),
            CadenceAdmissionClassification.ADMITTED,
            CadenceAdmissionReason.ADMITTED,
        ),
        (
            datetime(2026, 7, 14, 12, 30, tzinfo=UTC),
            CadenceAdmissionClassification.ADMITTED,
            CadenceAdmissionReason.ADMITTED,
        ),
        (
            datetime(2026, 7, 14, 12, 30, 1, tzinfo=UTC),
            CadenceAdmissionClassification.REJECTED_OUTSIDE_WINDOW,
            CadenceAdmissionReason.TOO_LATE,
        ),
    ],
)
def test_first_four_hour_close_cadence_boundary(
    now_utc: datetime,
    classification: CadenceAdmissionClassification,
    reason: CadenceAdmissionReason,
) -> None:
    result = _admit(
        timeframe="4H",
        reference_close_utc=datetime(2026, 7, 14, 12, 0, tzinfo=UTC),
        now_utc=now_utc,
    )

    assert result.classification == classification
    assert result.reason == reason


def test_first_joint_interval_is_bounded_by_one_hour_lateness() -> None:
    reference = datetime(2026, 7, 14, 12, 0, tzinfo=UTC)

    for now_utc in (
        datetime(2026, 7, 14, 12, 5, tzinfo=UTC),
        datetime(2026, 7, 14, 12, 20, tzinfo=UTC),
    ):
        for timeframe in ("1H", "4H"):
            result = _admit(
                timeframe=timeframe,
                reference_close_utc=reference,
                now_utc=now_utc,
            )
            assert result.classification == CadenceAdmissionClassification.ADMITTED
            assert result.reason == CadenceAdmissionReason.ADMITTED

    after_joint_interval = datetime(2026, 7, 14, 12, 20, 1, tzinfo=UTC)
    one_hour = _admit(
        timeframe="1H",
        reference_close_utc=reference,
        now_utc=after_joint_interval,
    )
    four_hour = _admit(
        timeframe="4H",
        reference_close_utc=reference,
        now_utc=after_joint_interval,
    )

    assert one_hour.classification == (CadenceAdmissionClassification.REJECTED_OUTSIDE_WINDOW)
    assert one_hour.reason == CadenceAdmissionReason.TOO_LATE
    assert four_hour.classification == CadenceAdmissionClassification.ADMITTED
    assert four_hour.reason == CadenceAdmissionReason.ADMITTED


@pytest.mark.parametrize(
    ("now_delta", "expected_reason"),
    [
        (timedelta(minutes=4, seconds=59), CadenceAdmissionReason.TOO_EARLY),
        (timedelta(minutes=20, seconds=1), CadenceAdmissionReason.TOO_LATE),
    ],
)
def test_rejects_outside_one_hour_collection_window(
    now_delta: timedelta,
    expected_reason: CadenceAdmissionReason,
) -> None:
    result = _admit(now_utc=REFERENCE_AFTER_CUTOVER + now_delta)

    assert result.classification == CadenceAdmissionClassification.REJECTED_OUTSIDE_WINDOW
    assert result.reason == expected_reason


def test_four_hour_window_uses_distinct_max_lateness() -> None:
    reference = datetime(2100, 1, 1, 4, 0, tzinfo=UTC)
    admitted = _admit(
        timeframe="4H",
        reference_close_utc=reference,
        now_utc=reference + timedelta(minutes=30),
    )
    late = _admit(
        timeframe="4H",
        reference_close_utc=reference,
        now_utc=reference + timedelta(minutes=30, seconds=1),
    )

    assert admitted.classification == CadenceAdmissionClassification.ADMITTED
    assert admitted.window_max_lateness_seconds == 1800
    assert late.classification == CadenceAdmissionClassification.REJECTED_OUTSIDE_WINDOW
    assert late.reason == CadenceAdmissionReason.TOO_LATE


@pytest.mark.parametrize(
    "methodology",
    [None, "", "deriv-intel-shadow-v0", "deriv-intel-okx-shadow-v2", 0, False],
)
def test_rejects_unapproved_methodologies(methodology: object) -> None:
    result = _admit(methodology_version=methodology)

    assert result.classification == CadenceAdmissionClassification.CONFIGURATION_ERROR
    assert result.reason == CadenceAdmissionReason.UNSUPPORTED_METHODOLOGY
    assert result.reference_close_utc is None
    assert result.guard_evaluated_at_utc is None


def test_rejects_unsupported_timeframes_and_bad_window_configuration() -> None:
    unsupported = _admit(timeframe="15M")
    bad_window = _admit(windows={"1H": CadenceWindow(600, 300)})

    assert unsupported.classification == CadenceAdmissionClassification.CONFIGURATION_ERROR
    assert unsupported.reason == CadenceAdmissionReason.UNSUPPORTED_TIMEFRAME
    assert bad_window.classification == CadenceAdmissionClassification.CONFIGURATION_ERROR
    assert bad_window.reason == CadenceAdmissionReason.INVALID_WINDOW_CONFIGURATION


def test_rejects_naive_timestamps_without_mutating_default_windows() -> None:
    naive_reference = _admit(reference_close_utc=datetime(2100, 1, 1, 1, 0))
    naive_now = _admit(now_utc=datetime(2100, 1, 1, 1, 5))

    assert naive_reference.classification == CadenceAdmissionClassification.CONFIGURATION_ERROR
    assert naive_reference.reason == CadenceAdmissionReason.NAIVE_REFERENCE_CLOSE
    assert naive_now.classification == CadenceAdmissionClassification.CONFIGURATION_ERROR
    assert naive_now.reason == CadenceAdmissionReason.NAIVE_NOW
    assert set(CADENCE_WINDOWS) == {"1H", "4H"}


def test_normalizes_aware_non_utc_inputs_to_canonical_utc() -> None:
    plus_seven = timezone(timedelta(hours=7))
    result = _admit(
        reference_close_utc=datetime(2100, 1, 1, 8, 0, tzinfo=plus_seven),
        now_utc=datetime(2100, 1, 1, 8, 5, tzinfo=plus_seven),
    )

    assert result.classification == CadenceAdmissionClassification.ADMITTED
    assert result.reference_close_utc == "2100-01-01T01:00:00Z"
    assert result.guard_evaluated_at_utc == "2100-01-01T01:05:00Z"
