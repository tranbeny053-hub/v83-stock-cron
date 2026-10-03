"""PERS-0 (plan §22 item 7; §23 Persistence): the fault-rehearsal harness, without a database.

The rehearsal itself runs only in CI, against scratch PostgreSQL. Here: the §23 verdicts derived
from observations, the scratch-only guard, and the fault injection.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
_SPEC = importlib.util.spec_from_file_location(
    "fault_injection", ROOT / "scripts/persistence_rehearsal/fault_injection.py"
)
fi = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(fi)


def _obs(
    overall: str,
    predictions: int,
    snapshots: int,
    *,
    receipt: str | None = None,
    before: tuple[int, int] = (0, 0),
    runs: int | None = None,
    details: int | None = None,
    **extra: object,
) -> dict:
    # Unless a test says otherwise, the receipt is the always-truthful one for the outcome, and
    # the run and the detail went with the prediction, as one transaction writes them (W-A).
    receipt = receipt or ("SAVED" if overall == "OK" else "COMMIT_UNKNOWN")
    return {
        "result": {"overall": overall},
        "receipt": receipt,
        "db_before": {"predictions": before[0], "snapshots": before[1], "runs": before[0],
                      "details": before[0]},
        "db": {"predictions": predictions, "snapshots": snapshots,
               "runs": predictions if runs is None else runs,
               "details": predictions if details is None else details},
        **extra,
    }


def _ideal() -> dict:
    return {
        "S1": _obs("OK", 1, 1),
        "S2": _obs("UNAVAILABLE", 0, 0),
        "S3": _obs("OK", 1, 1),
        "S4": _obs("OK", 1, 1, before=(1, 1)),
        "S5": _obs("UNAVAILABLE", 1, 1, receipt="NOT_SAVED", before=(1, 1),
                   conflict_reported_ok=False, stored_unchanged=True),
        "S6": _obs("PARTIAL", 1, 1, receipt="NOT_SAVED", before=(1, 1),
                   conflict_reported_ok=False, stored_unchanged=True),
        "S7a": _obs("UNAVAILABLE", 0, 0),
        "S7b": _obs("OK", 1, 1),
        "S8": _obs("UNAVAILABLE", 0, 0, receipt="NOT_SAVED"),
        "S9": _obs("UNAVAILABLE", 1, 1, receipt="NOT_SAVED", before=(1, 1),
                   conflict_reported_ok=False, stored_unchanged=True),
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


@pytest.mark.parametrize(
    ("runs", "details", "predictions", "snapshots"),
    [(1, 1, 0, 0), (1, 0, 0, 0), (0, 0, 1, 1), (1, 0, 1, 1)],
    ids=["run-and-detail-only", "run-only", "bundle-without-run", "missing-detail"],
)
def test_the_run_and_the_detail_are_part_of_the_complete_core(
    runs: int, details: int, predictions: int, snapshots: int
) -> None:
    """W-A: a run or a detail left without its bundle, or a bundle without them, is partial."""

    observed = _obs("UNAVAILABLE", predictions, snapshots, runs=runs, details=details)
    result = fi.verdicts(_ideal() | {"S2": observed})
    assert result["C1b"]["partial_bundles_persisted"] == ["S2"]
    acknowledged = _obs("OK", predictions, snapshots, runs=runs, details=details)
    assert fi.verdicts(_ideal() | {"S1": acknowledged})["C1a"]["acknowledged_but_incomplete"] == [
        "S1"]


def test_an_acknowledged_incomplete_bundle_fails_c1a() -> None:
    observations = _ideal() | {"S1": _obs("OK", 1, 0)}
    assert fi.verdicts(observations)["C1a"]["acknowledged_but_incomplete"] == ["S1"]


def test_a_conflict_reported_ok_or_overwriting_fails_c3() -> None:
    reported = _ideal() | {"S5": _obs("OK", 1, 1, conflict_reported_ok=True, stored_unchanged=True)}
    assert fi.verdicts(reported)["C3"] == {
        "verdict": "FAIL",
        "conflicts": ["S5", "S6", "S9"],
        "not_refused": ["S5"],
    }
    overwritten = _ideal() | {
        "S6": _obs("PARTIAL", 1, 1, conflict_reported_ok=False, stored_unchanged=False)
    }
    assert fi.verdicts(overwritten)["C3"]["not_refused"] == ["S6"]
    # W-A: a conflicting run identity overwritten, as a separate upsert would, is not refused.
    run_overwritten = _ideal() | {
        "S9": _obs("OK", 1, 1, receipt="SAVED", before=(1, 1), conflict_reported_ok=True,
                   stored_unchanged=False)
    }
    assert fi.verdicts(run_overwritten)["C3"]["not_refused"] == ["S9"]
    assert fi.verdicts(run_overwritten)["C5"]["false_receipts"] == ["S9"]


def test_retries_must_leave_one_complete_acknowledged_bundle() -> None:
    assert fi.verdicts(_ideal() | {"S3": _obs("PARTIAL", 1, 0)})["C2"]["not_idempotent"] == ["S3"]
    assert fi.verdicts(_ideal() | {"S7b": _obs("UNAVAILABLE", 1, 0)})["C4"]["verdict"] == "FAIL"


def test_a_receipt_never_claims_more_than_the_database_shows() -> None:
    # SAVED without a complete bundle, or for a conflicting submission, is false.
    assert fi.verdicts(_ideal() | {"S1": _obs("UNAVAILABLE", 1, 0, receipt="SAVED")})[
        "C5"]["false_receipts"] == ["S1"]
    conflict_saved = _ideal() | {"S5": _obs("OK", 1, 1, receipt="SAVED", before=(1, 1),
                                            conflict_reported_ok=True, stored_unchanged=True)}
    assert fi.verdicts(conflict_saved)["C5"]["false_receipts"] == ["S5"]
    # NOT_SAVED while the submission made a complete bundle appear is false...
    lost = _ideal() | {"S7a": _obs("UNAVAILABLE", 1, 1, receipt="NOT_SAVED")}
    assert fi.verdicts(lost)["C5"]["false_receipts"] == ["S7a"]
    # ...but a refusal over an already complete bundle is truly NOT_SAVED, and COMMIT_UNKNOWN is
    # never false.
    unknown = _ideal() | {"S7a": _obs("UNAVAILABLE", 1, 1, receipt="COMMIT_UNKNOWN")}
    assert fi.verdicts(unknown)["C5"]["verdict"] == "PASS"
    assert fi.verdicts(_ideal() | {"S2": _obs("UNAVAILABLE", 0, 0, receipt="MAYBE")})[
        "C5"]["false_receipts"] == ["S2"]


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


# ------------------------------------------------------------------------ B9: the REST route


def test_the_emulator_executes_only_the_bundle_rpcs() -> None:
    import httpx

    from scripts.persistence_rehearsal import postgrest_emulator as pe

    assert set(pe.RPC_SQLS) == {pe.RPC_PATH, pe.FORECAST_PATH}
    emulator = pe.PostgrestEmulator("postgresql:///never?host=/var/run/postgresql")
    for path in ("/rest/v1/analysis_runs", "/rest/v1/analysis_run_details",
                 "/rest/v1/provider_observations"):
        answer = emulator(httpx.Request("POST", f"https://rehearsal.invalid{path}"))
        assert answer.status_code == 201, "outside the bundle: acknowledged, not stored"
    assert emulator(httpx.Request("GET", "https://rehearsal.invalid/rest/v1/x")).status_code == 404
    assert emulator.rpc_requests == 0, "no database was touched"


def test_the_rpc_is_called_as_postgrest_calls_it() -> None:
    from scripts.persistence_rehearsal import postgrest_emulator as pe

    assert pe.RPC_PATH == "/rest/v1/rpc/save_prediction_bundle"
    # The raw body, read by jsonb_to_record with the function's own parameter types, as named
    # arguments: PostgREST's own call, so JSON numbers keep their digits.
    assert "FROM pg_catalog.jsonb_to_record(%s::jsonb)" in pe.RPC_SQL
    assert ("AS b(p_prediction jsonb, p_feature_snapshot jsonb, p_derivatives_snapshot jsonb)"
            in pe.RPC_SQL)
    for name in ("p_prediction", "p_feature_snapshot", "p_derivatives_snapshot"):
        assert f"{name} => b.{name}" in pe.RPC_SQL
    with pytest.raises(ValueError):
        pe.PostgrestEmulator("postgresql:///x?host=/var/run/postgresql", fault="anything")


def test_the_forecast_rpc_is_called_as_postgrest_calls_it() -> None:
    from scripts.persistence_rehearsal import postgrest_emulator as pe

    assert pe.FORECAST_PATH == "/rest/v1/rpc/save_forecast_bundle"
    assert "FROM pg_catalog.jsonb_to_record(%s::jsonb)" in pe.FORECAST_SQL
    assert ("AS b(p_run jsonb, p_prediction jsonb, p_feature_snapshot jsonb, "
            "p_derivatives_snapshot jsonb, p_run_detail jsonb)") in pe.FORECAST_SQL
    for name in ("p_run", "p_prediction", "p_feature_snapshot", "p_derivatives_snapshot",
                 "p_run_detail"):
        assert f"{name} => b.{name}" in pe.FORECAST_SQL


def test_the_injected_fault_lives_only_in_the_scratch_rehearsal() -> None:
    from scripts.persistence_rehearsal import postgrest_emulator as pe

    root = Path(__file__).resolve().parents[2]
    setup = " ".join(pe.FAULT_SETUP_SQL)
    assert "ON public.prediction_feature_snapshots" in setup and "pers0_fault." in setup
    for migration in (root / "migrations").glob("*.sql"):
        assert "pers0" not in migration.read_text(encoding="utf-8"), migration.name


def test_only_known_routes_can_be_required() -> None:
    with pytest.raises(SystemExit):
        fi.main(["--report=x.json", "--require-route", "mystery"])
    assert fi.ROUTES == ("postgres", "rest_rpc")


def _route(**changes: Any) -> dict[str, Any]:
    report = {
        "criteria": fi.verdicts(_ideal()),
        "privileges": {"expected": {"security_definer_of_ucpe_bundle_owner": True,
                                    "execute_for_service_role": True}},
        "refusals": {"expected": {"anon_refused_42501": True, "refusals_write_nothing": True}},
    }
    report.update(changes)
    return report


def test_a_required_route_must_pass_every_criterion_privilege_and_refusal() -> None:
    assert fi.unmet_requirements({"rest_rpc": _route()}, ["rest_rpc"]) == []
    failing = fi.verdicts(_ideal() | {"S5": _obs("OK", 1, 1, conflict_reported_ok=True,
                                                 stored_unchanged=True)})
    # A conflict acknowledged OK is refused by C3, and its SAVED receipt is false (C5).
    assert fi.unmet_requirements({"rest_rpc": _route(criteria=failing)}, ["rest_rpc"]) == [
        "rest_rpc.C3", "rest_rpc.C5"]
    weak = _route(privileges={"expected": {"security_definer_of_ucpe_bundle_owner": False}})
    assert fi.unmet_requirements({"rest_rpc": weak}, ["rest_rpc"]) == [
        "rest_rpc.privileges.security_definer_of_ucpe_bundle_owner"]
    leaky = _route(refusals={"expected": {"refusals_write_nothing": False}})
    assert fi.unmet_requirements({"rest_rpc": leaky}, ["rest_rpc"]) == [
        "rest_rpc.refusals.refusals_write_nothing"]
    # A route that is not required is data, whatever it shows.
    assert fi.unmet_requirements({"postgres": _route(criteria=failing)}, []) == []
