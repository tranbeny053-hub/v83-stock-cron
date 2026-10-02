"""PERS-0 (plan §22 item 7; §23 Persistence): the fault-rehearsal harness, without a database.

The rehearsal itself runs only in CI, against scratch PostgreSQL. Here: the §23 verdicts derived
from observations, the scratch-only guard, and the fault injection.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
_SPEC = importlib.util.spec_from_file_location(
    "fault_injection", ROOT / "scripts/persistence_rehearsal/fault_injection.py"
)
fi = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(fi)


def _obs(overall: str, predictions: int, snapshots: int, **extra: object) -> dict:
    return {
        "result": {"overall": overall},
        "db": {"predictions": predictions, "snapshots": snapshots},
        **extra,
    }


def _ideal() -> dict:
    return {
        "S1": _obs("OK", 1, 1),
        "S2": _obs("UNAVAILABLE", 0, 0),
        "S3": _obs("OK", 1, 1),
        "S4": _obs("OK", 1, 1),
        "S5": _obs("UNAVAILABLE", 1, 1, conflict_reported_ok=False, stored_unchanged=True),
        "S6": _obs("PARTIAL", 1, 1, conflict_reported_ok=False, stored_unchanged=True),
        "S7a": _obs("UNAVAILABLE", 0, 0),
        "S7b": _obs("OK", 1, 1),
        "S8": _obs("UNAVAILABLE", 0, 0),
    }


def test_an_atomic_idempotent_writer_passes_every_criterion() -> None:
    result = fi.verdicts(_ideal())
    assert {name: result[name]["verdict"] for name in fi.CRITERIA} == dict.fromkeys(
        fi.CRITERIA, "PASS"
    )


def test_a_persisted_partial_bundle_fails_atomicity_only() -> None:
    observations = _ideal() | {"S2": _obs("UNAVAILABLE", 1, 0)}
    result = fi.verdicts(observations)
    assert result["C1b"] == {"verdict": "FAIL", "partial_bundles_persisted": ["S2"]}
    assert result["C1a"]["verdict"] == "PASS", "not acknowledged, so C1a holds"


def test_an_acknowledged_incomplete_bundle_fails_c1a() -> None:
    observations = _ideal() | {"S1": _obs("OK", 1, 0)}
    assert fi.verdicts(observations)["C1a"]["acknowledged_but_incomplete"] == ["S1"]


def test_a_conflict_reported_ok_or_overwriting_fails_c3() -> None:
    reported = _ideal() | {"S5": _obs("OK", 1, 1, conflict_reported_ok=True, stored_unchanged=True)}
    assert fi.verdicts(reported)["C3"] == {
        "verdict": "FAIL",
        "conflicts": ["S5", "S6"],
        "not_refused": ["S5"],
    }
    overwritten = _ideal() | {
        "S6": _obs("PARTIAL", 1, 1, conflict_reported_ok=False, stored_unchanged=False)
    }
    assert fi.verdicts(overwritten)["C3"]["not_refused"] == ["S6"]


def test_retries_must_leave_one_complete_acknowledged_bundle() -> None:
    assert fi.verdicts(_ideal() | {"S3": _obs("PARTIAL", 1, 0)})["C2"]["not_idempotent"] == ["S3"]
    assert fi.verdicts(_ideal() | {"S7b": _obs("UNAVAILABLE", 1, 0)})["C4"]["verdict"] == "FAIL"


def test_missing_scenarios_never_pass() -> None:
    result = fi.verdicts({"S1": _obs("OK", 1, 1)})
    assert result["C2"]["verdict"] == "FAIL" and result["C3"]["verdict"] == "FAIL"
    assert result["C4"]["verdict"] == "FAIL"


@pytest.mark.parametrize(
    "url",
    ["", "postgresql://user@db.example:5432/postgres", "postgresql:///x?host=/tmp", "sqlite:///x"],
)
def test_only_the_scratch_socket_database_is_accepted(url: str) -> None:
    with pytest.raises(SystemExit):
        fi.require_scratch(url)


def test_the_scratch_socket_database_is_accepted() -> None:
    fi.require_scratch("postgresql:///persistence_rehearsal?host=/var/run/postgresql")


class _Real:
    def __init__(self) -> None:
        self.saved: list[str] = []

    def save_prediction(self, row: dict) -> str:
        self.saved.append(row["prediction_id"])
        return "OK"

    def save_feature_snapshot(self, row: dict) -> str:
        self.saved.append("snapshot")
        return "INSERTED"

    def persistence_status(self) -> str:
        return "OK"


def test_the_injected_faults_happen_exactly_where_declared() -> None:
    lost = fi.Faulty(_Real(), prediction_lost=True)
    with pytest.raises(fi.InjectedFault):
        lost.save_prediction({"prediction_id": "p1"})
    assert lost._real.saved == ["p1"], "the commit happened before the response was lost"
    crash = fi.Faulty(_Real(), snapshot_raises=True)
    assert crash.save_prediction({"prediction_id": "p2"}) == "OK"
    with pytest.raises(fi.InjectedFault):
        crash.save_feature_snapshot({})
    assert crash._real.saved == ["p2"]
    assert crash.persistence_status() == "OK", "every other call goes straight through"
