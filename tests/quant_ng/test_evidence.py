from __future__ import annotations

import hashlib
import struct
from datetime import UTC, datetime, timedelta, timezone

import pytest

from crypto_probability_engine.quant_ng import evidence as ev

T0 = datetime(2025, 1, 1, tzinfo=UTC)
TOL = ev.IssueTolerances(timedelta(seconds=10), timedelta(seconds=2))


def clocks(**changes) -> ev.E3Clocks:
    values = dict(lattice_instant_utc=T0, expected_reference_close_utc=T0,
                  reference_close_utc=T0, source_as_of_utc=T0,
                  core_computed_at_utc=T0 + timedelta(seconds=1),
                  issued_at_utc=T0 + timedelta(seconds=2),
                  commit_db_utc=T0 + timedelta(seconds=3),
                  horizon_end_utc=T0 + timedelta(hours=1))
    values.update(changes)
    return ev.E3Clocks(**values)


def test_population_names_are_explicit_and_timing_matrix_is_exhaustive() -> None:
    assert set(ev.Population) == {ev.Population.E1_OPERATIONAL, ev.Population.E2_RECONSTRUCTION,
                                 ev.Population.E3_SPACE_ISSUED, ev.Population.E4_USER_REQUESTED}
    assert set(ev.Timing) == {ev.Timing.ON_TIME, ev.Timing.LATE, ev.Timing.MISSED,
                              ev.Timing.RECONSTRUCTED, ev.Timing.NOT_APPLICABLE}
    assert set(ev.StoragePrecision) == {ev.StoragePrecision.FLOAT64_EXACT,
                                       ev.StoragePrecision.DECIMAL_EXACT,
                                       ev.StoragePrecision.LOSSY}
    assert all(value not in {"E1", "E2", "E3", "E4"} for value in ev.Population)
    expected = {
        ev.Population.E1_OPERATIONAL: {ev.Timing.NOT_APPLICABLE},
        ev.Population.E2_RECONSTRUCTION: {ev.Timing.RECONSTRUCTED},
        ev.Population.E3_SPACE_ISSUED: {ev.Timing.ON_TIME, ev.Timing.LATE, ev.Timing.MISSED},
        ev.Population.E4_USER_REQUESTED: {ev.Timing.NOT_APPLICABLE},
    }
    assert dict(ev.ALLOWED_TIMINGS) == {k: frozenset(v) for k, v in expected.items()}
    for population in ev.Population:
        for timing in ev.Timing:
            if timing in expected[population]:
                assert ev.check_row_classes(population, timing) is None
            else:
                with pytest.raises(ValueError):
                    ev.check_row_classes(population, timing)


@pytest.mark.parametrize("values", [(0, timedelta(seconds=1)),
                                     (timedelta(seconds=-1), timedelta(seconds=1)),
                                     (timedelta(seconds=1), 2)])
def test_tolerances_must_be_positive_timedeltas(values) -> None:
    with pytest.raises(ValueError):
        ev.IssueTolerances(*values)


def test_each_zero_tolerance_is_refused() -> None:
    with pytest.raises(ValueError, match="max_issue_delay"):
        ev.IssueTolerances(timedelta(0), timedelta(seconds=1))
    with pytest.raises(ValueError, match="max_commit_delay"):
        ev.IssueTolerances(timedelta(seconds=1), timedelta(0))


def test_e3_clocks_refuse_naive_and_bad_chronology() -> None:
    with pytest.raises(ValueError, match="timezone-aware UTC"):
        clocks(source_as_of_utc=datetime(2025, 1, 1))
    with pytest.raises(ValueError, match="timezone-aware UTC"):
        clocks(commit_db_utc=datetime(2025, 1, 1, tzinfo=timezone(timedelta(hours=1))))
    with pytest.raises(ValueError, match="lattice_instant_utc"):
        clocks(lattice_instant_utc=datetime(2025, 1, 1))
    with pytest.raises(ValueError, match="expected_reference_close_utc"):
        clocks(expected_reference_close_utc=datetime(2025, 1, 1))
    for changes in (
        {"source_as_of_utc": T0 - timedelta(seconds=1)},
        {"core_computed_at_utc": T0 - timedelta(seconds=1)},
        {"issued_at_utc": T0 - timedelta(seconds=1)},
        {"horizon_end_utc": T0 + timedelta(seconds=2)},
    ):
        with pytest.raises(ValueError, match="chronology"):
            clocks(**changes)


def test_classify_e3_boundaries_and_late_cases() -> None:
    assert ev.classify_e3(clocks(), TOL) == ev.Timing.ON_TIME
    stale = clocks(reference_close_utc=T0 - timedelta(seconds=1))
    before_instant = clocks(reference_close_utc=T0 - timedelta(seconds=2),
                            source_as_of_utc=T0 - timedelta(seconds=1))
    assert ev.classify_e3(stale, TOL) == ev.Timing.MISSED
    assert ev.classify_e3(before_instant, TOL) == ev.Timing.MISSED
    source_clock_only = clocks(lattice_instant_utc=T0 + timedelta(seconds=1),
                               core_computed_at_utc=T0 + timedelta(seconds=2),
                               issued_at_utc=T0 + timedelta(seconds=3),
                               commit_db_utc=T0 + timedelta(seconds=4))
    assert ev.classify_e3(source_clock_only, TOL) == ev.Timing.MISSED
    assert ev.classify_e3(clocks(reference_close_utc=T0 - timedelta(seconds=1),
                                 commit_db_utc=None), TOL) == ev.Timing.MISSED
    assert ev.classify_e3(clocks(commit_db_utc=None), TOL) == ev.Timing.LATE
    issue_exact = clocks(issued_at_utc=T0 + timedelta(seconds=10),
                         commit_db_utc=T0 + timedelta(seconds=10))
    assert ev.classify_e3(issue_exact, TOL) == ev.Timing.ON_TIME
    issue_late = clocks(issued_at_utc=T0 + timedelta(seconds=10, microseconds=1),
                        commit_db_utc=T0 + timedelta(seconds=10, microseconds=1))
    assert ev.classify_e3(issue_late, TOL) == ev.Timing.LATE
    commit_exact = clocks(commit_db_utc=T0 + timedelta(seconds=4))
    assert ev.classify_e3(commit_exact, TOL) == ev.Timing.ON_TIME
    commit_late = clocks(commit_db_utc=T0 + timedelta(seconds=4, microseconds=1))
    assert ev.classify_e3(commit_late, TOL) == ev.Timing.LATE
    at_horizon = clocks(commit_db_utc=T0 + timedelta(hours=1))
    assert ev.classify_e3(at_horizon, TOL) == ev.Timing.LATE
    wide = ev.IssueTolerances(timedelta(hours=2), timedelta(hours=2))
    horizon_exact = clocks(commit_db_utc=T0 + timedelta(hours=1))
    horizon_before = clocks(commit_db_utc=T0 + timedelta(hours=1) - timedelta(microseconds=1))
    assert ev.classify_e3(horizon_exact, wide) == ev.Timing.LATE
    assert ev.classify_e3(horizon_before, wide) == ev.Timing.ON_TIME


def test_claim_admissibility_population_matrix_and_freeze_window() -> None:
    for row_population in ev.Population:
        for claim_population in (ev.Population.E2_RECONSTRUCTION, ev.Population.E3_SPACE_ISSUED):
            expected = (row_population == claim_population
                        and row_population != ev.Population.E1_OPERATIONAL)
            assert ev.claim_admissible(row_population=row_population,
                                       claim_population=claim_population,
                                       row_reference_close_utc=T0 + timedelta(seconds=1),
                                       freeze_anchor_utc=T0) is expected
    with pytest.raises(ValueError, match="claim_population"):
        ev.claim_admissible(row_population=ev.Population.E2_RECONSTRUCTION,
                            claim_population=ev.Population.E4_USER_REQUESTED,
                            row_reference_close_utc=T0, freeze_anchor_utc=T0)
    with pytest.raises(ValueError, match="claim_population"):
        ev.claim_admissible(row_population=ev.Population.E1_OPERATIONAL,
                            claim_population=ev.Population.E1_OPERATIONAL,
                            row_reference_close_utc=T0, freeze_anchor_utc=T0)
    with pytest.raises(ValueError, match="row_reference_close_utc"):
        ev.claim_admissible(row_population=ev.Population.E2_RECONSTRUCTION,
                            claim_population=ev.Population.E2_RECONSTRUCTION,
                            row_reference_close_utc=datetime(2025, 1, 1), freeze_anchor_utc=T0)
    with pytest.raises(ValueError, match="freeze_anchor_utc"):
        ev.claim_admissible(row_population=ev.Population.E2_RECONSTRUCTION,
                            claim_population=ev.Population.E2_RECONSTRUCTION,
                            row_reference_close_utc=T0 + timedelta(seconds=1),
                            freeze_anchor_utc=datetime(2025, 1, 1))
    assert not ev.claim_admissible(row_population=ev.Population.E2_RECONSTRUCTION,
                                   claim_population=ev.Population.E2_RECONSTRUCTION,
                                   row_reference_close_utc=T0, freeze_anchor_utc=T0)
    assert not ev.claim_admissible(row_population=ev.Population.E2_RECONSTRUCTION,
                                   claim_population=ev.Population.E2_RECONSTRUCTION,
                                   row_reference_close_utc=T0 + timedelta(seconds=1),
                                   freeze_anchor_utc=None)
    assert ev.claim_admissible(row_population=ev.Population.E2_RECONSTRUCTION,
                               claim_population=ev.Population.E2_RECONSTRUCTION,
                               row_reference_close_utc=T0 + timedelta(seconds=1),
                               freeze_anchor_utc=T0)


@pytest.mark.parametrize("old,new", [
    ((ev.Population.E3_SPACE_ISSUED, ev.Timing.LATE),
     (ev.Population.E3_SPACE_ISSUED, ev.Timing.ON_TIME)),
    ((ev.Population.E3_SPACE_ISSUED, ev.Timing.MISSED),
     (ev.Population.E3_SPACE_ISSUED, ev.Timing.LATE)),
    ((ev.Population.E2_RECONSTRUCTION, ev.Timing.RECONSTRUCTED),
     (ev.Population.E3_SPACE_ISSUED, ev.Timing.RECONSTRUCTED)),
    ((ev.Population.E1_OPERATIONAL, ev.Timing.NOT_APPLICABLE),
     (ev.Population.E3_SPACE_ISSUED, ev.Timing.NOT_APPLICABLE)),
])
def test_reclassification_refused(old, new) -> None:
    with pytest.raises(ValueError):
        ev.check_reclassification(*old, *new)


def test_reclassification_accepts_identity() -> None:
    assert ev.check_reclassification(ev.Population.E3_SPACE_ISSUED, ev.Timing.LATE,
                                     ev.Population.E3_SPACE_ISSUED, ev.Timing.LATE) is None


def test_vector_digest_and_invalid_inputs() -> None:
    values = (1.25, -2.0, 0.5)
    expected = hashlib.sha256(b"".join(struct.pack("<d", x) for x in values)).hexdigest()
    assert ev.vector_sha256(values) == expected
    for invalid in ((), (True,), (float("nan"),), (float("inf"),)):
        with pytest.raises(ValueError):
            ev.vector_sha256(invalid)


def test_replay_digest_validation_and_claimability_truth_table() -> None:
    digest = ev.vector_sha256((1.0, 2.0))
    with pytest.raises(ValueError, match="does not match"):
        ev.ReplayRecord((1.0,), "0" * 64, None, ev.StoragePrecision.FLOAT64_EXACT)
    for precision in ev.StoragePrecision:
        for vector, retained in ((None, None), (None, "a" * 64), ((1.0, 2.0), None)):
            record = ev.ReplayRecord(vector, digest, retained, precision)
            expected = (precision != ev.StoragePrecision.LOSSY
                        and (vector is not None or retained is not None))
            assert ev.replay_parity_claimable(record) is expected


@pytest.mark.parametrize("field,value", [
    ("input_vector_sha256", "A" * 64), ("input_vector_sha256", "abc"),
    ("input_vector_sha256", 123), ("retained_bytes_manifest_sha256", "A" * 64),
    ("retained_bytes_manifest_sha256", "abc"), ("retained_bytes_manifest_sha256", 123),
])
def test_replay_digest_fields_require_lowercase_sha256(field, value) -> None:
    args = {"input_vector": None, "input_vector_sha256": "a" * 64,
            "retained_bytes_manifest_sha256": None,
            "storage_precision": ev.StoragePrecision.FLOAT64_EXACT}
    args[field] = value
    with pytest.raises(ValueError, match=field):
        ev.ReplayRecord(**args)


def test_replay_input_vector_must_be_tuple_or_none_and_equal_clocks_are_valid() -> None:
    digest = ev.vector_sha256((1.0,))
    with pytest.raises(ValueError, match="input_vector"):
        ev.ReplayRecord([1.0], digest, None, ev.StoragePrecision.FLOAT64_EXACT)
    assert ev.E3Clocks(lattice_instant_utc=T0, expected_reference_close_utc=T0,
                       reference_close_utc=T0, source_as_of_utc=T0,
                       core_computed_at_utc=T0, issued_at_utc=T0, commit_db_utc=None,
                       horizon_end_utc=T0 + timedelta(seconds=1))
    assert ev.E3Clocks(lattice_instant_utc=T0, expected_reference_close_utc=T0,
                       reference_close_utc=T0, source_as_of_utc=T0,
                       core_computed_at_utc=T0, issued_at_utc=T0, commit_db_utc=T0,
                       horizon_end_utc=T0 + timedelta(seconds=1))
