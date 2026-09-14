"""Readiness vs consumption, the five guards, and the one-shot failure states.

No database is contacted: the repository is a fake built from synthetic evidence.
"""

from __future__ import annotations

import json
import re
from datetime import timedelta
from pathlib import Path

import pytest

from crypto_probability_engine.oos.evaluation import runner
from crypto_probability_engine.runtime_isolation import ProvenanceRefused
from tests.oos.evaluation.conftest import (
    T0,
    T_CLOSE,
    daily_4h_evidence,
    evidence_row,
    verified_provenance,
)

AFTER_CLOSE = T_CLOSE + timedelta(hours=2)


@pytest.fixture(autouse=True)
def _clear_durable_seal():
    FakeRepository.durable_seal = None
    yield
    FakeRepository.durable_seal = None


class FakeRepository:
    """A faithful model of the DURABLE POSTGRES seal contract. Never touches a database.

    It enforces what migration 0009 and the Postgres repository enforce, so the runner is
    tested against the real rules rather than a permissive stand-in:

    - it declares itself ``POSTGRES_DURABLE``;
    - the seal is a singleton shared ACROSS instances (the class attribute), because the
      original defect was that a fresh runner got a fresh filesystem;
    - a claim carries no evidence (the table's CHECK refuses it);
    - probabilities are returned ONLY under a CLAIMED, uncaptured seal, and are captured into it
      BEFORE they are returned — capture-before-exposure;
    - the snapshot can only be recorded after that raw capture, once, under the claimed pin;
    - state transitions are restricted exactly as the trigger restricts them.
    """

    # ONE durable authority for every instance AND every subclass. Referencing it as
    # FakeRepository.durable_seal (never type(self).durable_seal) matters: a subclass writing
    # type(self).durable_seal would create its own private seal, silently making assertions
    # like "FakeRepository.durable_seal is None" vacuous and leaking state between tests.
    durable_seal: dict | None = None
    _LEGAL = {
        "CLAIMED": {"CLAIMED", "SEALED_RAW_CAPTURED", "CAPTURE_FAILED"},
        "SEALED_RAW_CAPTURED": {"SEALED_RAW_CAPTURED", "COMPLETE", "SEALED_NO_RESULT"},
        "SEALED_NO_RESULT": {"SEALED_NO_RESULT", "COMPLETE"},
        "COMPLETE": {"COMPLETE"},
        "CAPTURE_FAILED": {"CAPTURE_FAILED"},
    }

    def __init__(self, rows=None, *, origin_anomalies: int = 0, features=()):
        self._rows = list(rows if rows is not None else daily_4h_evidence())
        self._origin_anomalies = origin_anomalies
        self._features = list(features)
        self.calls: list[bool] = []
        self.events: list[str] = []

    def section_5a_seal_authority(self) -> str:
        return runner.SEAL_AUTHORITY_POSTGRES

    def fetch_oos_paired_evidence(self, *, include_probabilities: bool):
        self.calls.append(include_probabilities)
        if not include_probabilities:
            self.events.append("read_projection")
            return [
                {
                    key: value
                    for key, value in row.items()
                    if not key.endswith(("_p_up_frac", "_p_down_frac", "_p_timeout_frac"))
                }
                for row in self._rows
            ]
        seal = FakeRepository.durable_seal
        if seal is None or seal["state"] != "CLAIMED" or seal.get("raw_evidence") is not None:
            raise RuntimeError(
                "section 5A probabilities may be read only under a CLAIMED, uncaptured seal"
            )
        rows = [dict(row) for row in self._rows]
        seal["raw_evidence"] = [dict(row) for row in rows]  # captured BEFORE it is returned
        self.events.append("read_probabilities")
        return rows

    def count_oos_origin_anomalies(self) -> int:
        return self._origin_anomalies

    def fetch_oos_feature_diagnostics(self):
        return list(self._features)

    def claim_section_5a_seal(self, payload) -> bool:
        if payload.get("snapshot_payload") is not None:
            raise RuntimeError("CHECK section_5a_claimed_has_no_snapshot violated")
        if FakeRepository.durable_seal is not None:
            return False
        FakeRepository.durable_seal = {**dict(payload), "state": "CLAIMED", "state_detail": ""}
        self.events.append("claim")
        return True

    def capture_section_5a_snapshot(self, snapshot) -> None:
        seal = FakeRepository.durable_seal
        if (
            seal is None
            or seal["state"] != "CLAIMED"
            or seal.get("raw_evidence") is None
            or seal.get("snapshot_payload") is not None
            or seal["evaluator_pin_digest"] != snapshot["evaluator_pin_digest"]
        ):
            raise RuntimeError("section 5A snapshot capture did not land")
        seal.update(
            snapshot_payload=dict(snapshot),
            evidence_snapshot_id=snapshot["evidence_snapshot_id"],
            result_inputs_digest=snapshot["result_inputs_digest"],
            state="SEALED_RAW_CAPTURED",
        )
        self.events.append("capture")

    def fetch_section_5a_seal(self):
        seal = FakeRepository.durable_seal
        if seal is None:
            return None
        copy = dict(seal)
        raw = copy.pop("raw_evidence", None)
        if raw is not None:
            copy["captured_rows"] = [dict(row) for row in raw]
        return copy

    def advance_section_5a_seal_state(self, state: str, detail: str = "") -> None:
        seal = FakeRepository.durable_seal
        if seal is None:
            raise RuntimeError("no seal to advance")
        if state not in self._LEGAL[seal["state"]]:
            raise RuntimeError(f"illegal section 5A seal transition {seal['state']} -> {state}")
        seal["state"] = state
        seal["state_detail"] = detail


# --------------------------- readiness ---------------------------


def test_readiness_never_requests_probabilities() -> None:
    repo = FakeRepository()
    runner.run_readiness(repo)
    assert repo.calls == [False]


def test_readiness_output_contains_no_score_of_any_kind() -> None:
    """Scan the DATA, not the prose: the explanatory note names what is absent."""

    report = runner.run_readiness(FakeRepository())
    payload = {key: value for key, value in report.items() if key != "note"}
    # Identities are hex digests of hash-seeded synthetic rows, and a digest can spell "ece" by
    # chance, which made this scan flaky. Scan everything else.
    rendered = re.sub(r"\b[0-9a-f]{64}\b", "<digest>", json.dumps(payload).lower())
    for forbidden in (
        "brier", "ece", "d_bar", "boundary_statistic",
        "a1_holds", "a2_holds", "b1_holds", "authorized_cells",
    ):
        assert forbidden not in rendered, forbidden
    assert report["consumes_one_look"] is False


def test_readiness_emits_no_verdict_key_anywhere_in_its_structure() -> None:
    report = runner.run_readiness(FakeRepository())

    def keys(node):
        if isinstance(node, dict):
            for key, value in node.items():
                yield key
                yield from keys(value)
        elif isinstance(node, list):
            for item in node:
                yield from keys(item)

    emitted = set(keys(report))
    assert not emitted & {"state", "per_timeframe_state", "authorized_cells", "b_holds"}


def test_readiness_reports_attainability_from_the_frame_alone() -> None:
    report = runner.run_readiness(FakeRepository())
    assert report["attainability"]["4H"]["verdict"] == "ATTAINABLE"
    assert report["attainability"]["4H"]["usable_windows_c4"] == 5
    assert report["attainability"]["15m"]["verdict"] == "PASS_UNATTAINABLE"


def test_readiness_is_repeatable_and_leaves_no_seal(tmp_path: Path) -> None:
    repo = FakeRepository()
    first = runner.run_readiness(repo)
    second = runner.run_readiness(repo)
    assert first["evidence_snapshot_id"] == second["evidence_snapshot_id"]
    assert runner.read_state(tmp_path) == runner.STATE_NOT_STARTED
    runner.refuse_existing(tmp_path)  # must not raise


def test_readiness_refuses_if_a_probability_ever_leaks_through() -> None:
    class LeakyRepository(FakeRepository):
        def fetch_oos_paired_evidence(self, *, include_probabilities: bool):
            return list(self._rows)  # ignores the flag

    with pytest.raises(RuntimeError, match="structural boundary"):
        runner.run_readiness(LeakyRepository())


# --------------------------- consumption guards ---------------------------


def _consume(repo, tmp_path, **kwargs):
    # As production runs it: the CLI always hands consumption a verified dispatch record (E2=A).
    params = {
        "confirmation": runner.CONFIRMATION_TOKEN,
        "artifact_dir": tmp_path,
        "now_utc": AFTER_CLOSE,
        "provenance": verified_provenance(),
        # Addendum 10: a verified consumption names the readiness population of what it will read.
        "expected_population_id": runner.decision_population_id(getattr(repo, "_rows", [])),
    }
    params.update(kwargs)
    return runner.run_consumption(repo, **params)


def test_G5_refuses_before_t_close(tmp_path: Path) -> None:
    repo = FakeRepository()
    with pytest.raises(runner.ConsumptionRefused, match="T_close has not passed"):
        _consume(repo, tmp_path, now_utc=T_CLOSE - timedelta(seconds=1))
    assert repo.calls == [], "nothing may be read before the guards pass"


@pytest.mark.parametrize("token", ["", "wrong", runner.CONFIRMATION_TOKEN.lower()])
def test_G3_refuses_without_the_exact_token(tmp_path: Path, token: str) -> None:
    repo = FakeRepository()
    with pytest.raises(runner.ConsumptionRefused, match="confirmation token"):
        _consume(repo, tmp_path, confirmation=token)
    assert repo.calls == []


def test_G1_pin_mismatch_refuses_before_anything_is_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from crypto_probability_engine.oos.evaluation import evaluator_pin

    def _mismatch():
        raise evaluator_pin.EvaluatorPinMismatch("simulated drift")

    monkeypatch.setattr(runner, "assert_evaluator_pin", _mismatch)
    repo = FakeRepository()
    with pytest.raises(evaluator_pin.EvaluatorPinMismatch, match="simulated drift"):
        runner.run_consumption(
            repo,
            confirmation=runner.CONFIRMATION_TOKEN,
            artifact_dir=tmp_path,
            now_utc=AFTER_CLOSE,
        )
    assert repo.calls == [], "the pin is verified before the holdout is touched"
    assert not (tmp_path / runner.SNAPSHOT_FILENAME).exists()


def test_the_real_committed_pin_lets_consumption_proceed(tmp_path: Path) -> None:
    """Guard the guard: mandatory pin verification must not be permanently broken."""

    result = runner.run_consumption(
        FakeRepository(),
        confirmation=runner.CONFIRMATION_TOKEN,
        artifact_dir=tmp_path,
        now_utc=AFTER_CLOSE,
    )
    assert result["consumes_one_look"] is True


def test_G2_refuses_a_second_look(tmp_path: Path) -> None:
    _consume(FakeRepository(), tmp_path)
    with pytest.raises(runner.OneLookAlreadyConsumed, match="durable section 5A seal"):
        _consume(FakeRepository(), tmp_path)


def test_G2_refuses_across_a_FRESH_workspace(tmp_path: Path) -> None:
    """FINDING F2. The workflow gets a new runner per dispatch, so a filesystem seal is
    always empty. The refusal must come from the durable authority, not the disk."""

    first = tmp_path / "run-one"
    second = tmp_path / "run-two"
    _consume(FakeRepository(), first)
    assert not (second / runner.SNAPSHOT_FILENAME).exists(), "second workspace is clean"
    with pytest.raises(runner.OneLookAlreadyConsumed, match="durable section 5A seal"):
        _consume(FakeRepository(), second)


def test_a_failing_secondary_read_cannot_spend_the_look(tmp_path: Path) -> None:
    """FINDING F3. The non-consequential reads now precede the probabilities, so a
    failure there happens BEFORE consumption rather than inside an unsealed interval."""

    class BrokenDiagnostics(FakeRepository):
        def fetch_oos_feature_diagnostics(self):
            raise RuntimeError("diagnostics read failed")

    repo = BrokenDiagnostics()
    with pytest.raises(RuntimeError, match="diagnostics read failed"):
        _consume(repo, tmp_path)
    assert repo.calls == [], "the probabilities were never read"
    assert FakeRepository.durable_seal is None, "no seal, because no look was spent"
    assert not (tmp_path / runner.SNAPSHOT_FILENAME).exists()


def test_after_capture_the_durable_seal_carries_the_evidence_and_its_identity(
    tmp_path: Path,
) -> None:
    """The claim carries no evidence; the capture that follows the read records it."""

    _consume(FakeRepository(), tmp_path)
    seal = FakeRepository.durable_seal
    assert seal is not None
    assert seal["snapshot_payload"]["rows"], "the seal carries the raw evidence itself"
    assert seal["evidence_snapshot_id"] == seal["snapshot_payload"]["evidence_snapshot_id"]


def test_recompute_refuses_a_tampered_snapshot(tmp_path: Path) -> None:
    """FINDING F4. An edited row must not be silently rescored under a stale id."""

    _consume(FakeRepository(), tmp_path)
    path = tmp_path / runner.SNAPSHOT_FILENAME
    snapshot = json.loads(path.read_text())
    snapshot["rows"][0]["candidate_p_up_frac"] = 0.99
    snapshot["rows"][0]["candidate_p_down_frac"] = 0.005
    snapshot["rows"][0]["candidate_p_timeout_frac"] = 0.005
    path.write_text(json.dumps(snapshot))
    with pytest.raises(runner.SnapshotTampered, match="does not match its recorded snapshot id"):
        runner.recompute_from_snapshot(tmp_path, verify_pin=False)


def test_recompute_refuses_when_the_rules_have_drifted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """FINDING F4. Recomputing under a changed evaluator would be retuning."""

    _consume(FakeRepository(), tmp_path)
    monkeypatch.setattr(
        runner, "current_pin_artifacts", lambda: {"closure_digest": "drifted"}
    )
    with pytest.raises(runner.SnapshotTampered, match="evaluator has changed"):
        runner.recompute_from_snapshot(tmp_path, verify_pin=False)


def test_snapshot_identity_covers_diagnostics_inputs(tmp_path: Path) -> None:
    """FINDING F5. Two captures differing only in feature rows are different evidence."""

    rows = daily_4h_evidence()
    base = runner.evidence_snapshot_id(rows)
    with_features = runner.evidence_snapshot_id(
        rows, feature_rows=[{"prediction_id": "x", "regime": "CALM"}]
    )
    with_anomalies = runner.evidence_snapshot_id(rows, origin_anomalies=3)
    assert len({base, with_features, with_anomalies}) == 3


def test_result_binds_the_rules_as_well_as_the_evidence(tmp_path: Path) -> None:
    result = _consume(FakeRepository(), tmp_path)
    assert result["evaluator_pin_digest"]
    assert result["result_inputs_digest"]
    assert result["result_inputs_digest"] != result["evidence_snapshot_id"]


def test_readiness_also_verifies_the_pin(monkeypatch: pytest.MonkeyPatch) -> None:
    """The CLI reaches readiness directly, so the ordering must be enforced here."""

    from crypto_probability_engine.oos.evaluation import evaluator_pin

    def _mismatch():
        raise evaluator_pin.EvaluatorPinMismatch("simulated drift")

    monkeypatch.setattr(runner, "assert_evaluator_pin", _mismatch)
    repo = FakeRepository()
    with pytest.raises(evaluator_pin.EvaluatorPinMismatch):
        runner.run_readiness(repo)
    assert repo.calls == []


def test_G2_refuses_even_when_the_first_run_produced_no_result(tmp_path: Path) -> None:
    """A crashed run has still spent the look."""

    broken = FakeRepository([evidence_row(T_CLOSE - timedelta(days=1))])
    broken._rows[0].pop("candidate_p_up_frac")
    with pytest.raises(KeyError, match="no probabilities"):
        _consume(broken, tmp_path)
    assert runner.read_state(tmp_path) == runner.STATE_SEALED_NO_RESULT
    with pytest.raises(runner.OneLookAlreadyConsumed):
        _consume(FakeRepository(), tmp_path)


# --------------------------- one-shot states ---------------------------


def test_G4_raw_capture_survives_a_statistics_failure(tmp_path: Path) -> None:
    """Doctrine rule 1: a parser failure must never be a reason to read again."""

    broken = FakeRepository([evidence_row(T_CLOSE - timedelta(days=1))])
    broken._rows[0].pop("candidate_p_up_frac")
    with pytest.raises(KeyError, match="no probabilities"):
        _consume(broken, tmp_path)

    snapshot_path = tmp_path / runner.SNAPSHOT_FILENAME
    assert snapshot_path.exists(), "the raw capture must outlive the failure"
    snapshot = json.loads(snapshot_path.read_text())
    assert snapshot["rows"], "the raw rows must be recoverable"
    assert (tmp_path / runner.RESULT_FILENAME).exists() is False
    assert runner.read_state(tmp_path) == runner.STATE_SEALED_NO_RESULT


def test_recompute_from_snapshot_needs_no_database(tmp_path: Path) -> None:
    _consume(FakeRepository(), tmp_path)
    (tmp_path / runner.RESULT_FILENAME).unlink()

    first = runner.recompute_from_snapshot(tmp_path)
    second = runner.recompute_from_snapshot(tmp_path)
    assert first["per_timeframe"] == second["per_timeframe"]
    assert runner.read_state(tmp_path) == runner.STATE_COMPLETE


def test_completed_run_records_state_and_snapshot_identity(tmp_path: Path) -> None:
    result = _consume(FakeRepository(), tmp_path)
    assert runner.read_state(tmp_path) == runner.STATE_COMPLETE
    snapshot = json.loads((tmp_path / runner.SNAPSHOT_FILENAME).read_text())
    assert result["evidence_snapshot_id"] == snapshot["evidence_snapshot_id"]


def test_snapshot_identity_changes_when_the_evidence_changes() -> None:
    base = daily_4h_evidence()
    changed = daily_4h_evidence() + [evidence_row(T_CLOSE - timedelta(hours=5))]
    assert runner.evidence_snapshot_id(base) != runner.evidence_snapshot_id(changed)


def test_snapshot_identity_is_stable_across_runs() -> None:
    assert runner.evidence_snapshot_id(daily_4h_evidence()) == runner.evidence_snapshot_id(
        daily_4h_evidence()
    )


# --------------------------- reporting discipline ---------------------------


def test_consumption_output_states_the_convention_and_the_licence(tmp_path: Path) -> None:
    result = _consume(FakeRepository(), tmp_path)
    rendered = json.dumps(result).lower()
    assert "significant" not in rendered
    assert "error rate" in rendered
    assert "no profitability claim" in rendered
    assert result["per_timeframe"]["4H"]["state"] == "A_AND_B_HELD_FAIL_UNVERIFIED"
    assert result["per_timeframe"]["4H"]["authorized"] is False
    assert result["authorized_cells"] == []
    assert result["diagnostics"]["per_timeframe"]["4H"]["admitted_pairs"] == 22


def test_diagnostics_accompany_a_not_pass_outcome_too(tmp_path: Path) -> None:
    losing = daily_4h_evidence(candidate_ups=[0.40, 0.41, 0.39, 0.42, 0.38, 0.43, 0.375])
    result = _consume(FakeRepository(losing), tmp_path)
    assert result["per_timeframe"]["4H"]["state"] == "NOT_PASS"
    assert result["diagnostics"]["per_timeframe"]["4H"]["admitted_pairs"] == 22
    assert result["authorized_cells"] == []


# --------------------------- claim before exposure ---------------------------


def test_the_durable_claim_precedes_the_probability_read(tmp_path: Path) -> None:
    """G1.1, G3.1. Order is the safety property: guard, CLAIM, then read, then capture."""

    repo = FakeRepository()
    _consume(repo, tmp_path)
    assert repo.events.index("claim") < repo.events.index("read_probabilities")
    assert repo.events.index("read_probabilities") < repo.events.index("capture")


def test_the_claim_itself_carries_no_evidence(tmp_path: Path) -> None:
    """Evidence handed to a claim would reintroduce read-before-claim; the fake's CHECK refuses."""

    repo = FakeRepository()
    _consume(repo, tmp_path)
    seal = FakeRepository.durable_seal
    assert seal["sealed_at_utc"] and seal["evaluator_pin_digest"]
    assert "contract_instants" in seal


def test_a_failure_after_the_claim_is_durably_recorded_and_spends_the_look(
    tmp_path: Path,
) -> None:
    """If capture fails, the look is still recorded as spent and cannot be taken again."""

    class CaptureFails(FakeRepository):
        def capture_section_5a_snapshot(self, snapshot) -> None:
            raise RuntimeError("capture write failed")

    repo = CaptureFails()
    with pytest.raises(RuntimeError, match="capture write failed"):
        _consume(repo, tmp_path / "one")
    assert repo.calls.count(True) == 1, "the probabilities were read exactly once"
    assert FakeRepository.durable_seal["state"] == runner.STATE_CAPTURE_FAILED
    with pytest.raises(runner.OneLookAlreadyConsumed):
        _consume(FakeRepository(), tmp_path / "two")


@pytest.mark.parametrize("authority", ["PROCESS_LOCAL", "REST_NOT_A_SEAL_AUTHORITY", "anything"])
def test_a_non_durable_authority_is_refused_before_any_claim_or_read(
    tmp_path: Path, authority: str
) -> None:
    """G8."""

    class Declares(FakeRepository):
        def section_5a_seal_authority(self) -> str:
            return authority

    repo = Declares()
    with pytest.raises(runner.ConsumptionRefused, match="durable Postgres"):
        _consume(repo, tmp_path)
    assert repo.calls == [] and repo.events == []
    assert FakeRepository.durable_seal is None


def test_an_unmeasured_anomaly_count_is_refused_before_the_claim(tmp_path: Path) -> None:
    repo = FakeRepository(origin_anomalies=None)
    with pytest.raises(runner.ConsumptionRefused, match="not a measured integer"):
        _consume(repo, tmp_path)
    assert FakeRepository.durable_seal is None


# --------------------------- anti-vacuity: valid evidence must pass ---------------------------


def test_a_valid_snapshot_written_to_disk_recomputes_successfully(tmp_path: Path) -> None:
    """Guards the tamper tests against passing VACUOUSLY.

    Built exactly as the pinned red tests build theirs: raw datetime and float rows, digests
    computed over the raw values, written with runner._pretty_json. If a valid snapshot could
    not survive that round trip, every "refuses tampering" test would pass for the wrong reason.
    """

    from crypto_probability_engine.oos.evaluation import evaluator_pin
    from tests.oos.evaluation.conftest import T0, T_FREEZE

    rows = daily_4h_evidence()
    features = [
        {"prediction_id": r["candidate_prediction_id"], "realized_vol": 0.2} for r in rows
    ]
    pin = str(evaluator_pin.current_pin_artifacts()["closure_digest"])
    evidence = runner.evidence_snapshot_id(rows, feature_rows=features, origin_anomalies=0)
    snapshot = {
        "evidence_snapshot_id": evidence,
        "result_inputs_digest": runner.result_inputs_digest(evidence, pin),
        "evaluator_pin_digest": pin,
        "t_freeze": T_FREEZE.isoformat(),
        "t0": T0.isoformat(),
        "t_close": T_CLOSE.isoformat(),
        "timeframes": list(runner.TIMEFRAMES),
        "origin_anomalies": 0,
        "feature_rows": features,
        "rows": rows,
    }
    tmp_path.mkdir(exist_ok=True)
    (tmp_path / runner.SNAPSHOT_FILENAME).write_bytes(runner._pretty_json(snapshot))

    result = runner.recompute_from_snapshot(tmp_path, verify_pin=False)
    assert result["evidence_snapshot_id"] == evidence
    direct = runner.compute_from_snapshot(snapshot, now_utc=AFTER_CLOSE)
    assert result["per_timeframe"] == direct["per_timeframe"], (
        "recomputing from disk must give the same decision as computing from memory"
    )
    assert result["diagnostics"]["per_timeframe"] == direct["diagnostics"]["per_timeframe"]


def test_consume_then_recompute_from_the_local_artifact_is_identical(tmp_path: Path) -> None:
    first = _consume(FakeRepository(), tmp_path)
    again = runner.recompute_from_snapshot(tmp_path, verify_pin=False)
    assert again["per_timeframe"] == first["per_timeframe"]
    assert again["evidence_snapshot_id"] == first["evidence_snapshot_id"]


# --------------------------- recovery from the durable seal ---------------------------


def test_recompute_from_seal_matches_consumption_and_never_rereads(tmp_path: Path) -> None:
    first = _consume(FakeRepository(), tmp_path)
    repo = FakeRepository()
    again = runner.recompute_from_seal(repo)
    assert again["per_timeframe"] == first["per_timeframe"]
    assert repo.calls == [], "recovery reads the captured evidence, never the predictions"


def test_recompute_from_seal_reverifies_loaded_code_after_its_read_and_before_advancing(
    tmp_path: Path,
) -> None:
    """M1=A. The read loads the driver; the guard runs before any result or durable write."""

    _consume(FakeRepository(), tmp_path)
    FakeRepository.durable_seal["state"] = runner.STATE_SEALED_RAW_CAPTURED
    order: list[str] = []

    class Recording(FakeRepository):
        def fetch_section_5a_seal(self):
            order.append("read")
            return super().fetch_section_5a_seal()

        def advance_section_5a_seal_state(self, state: str, detail: str = "") -> None:
            order.append(f"advance:{state}")
            super().advance_section_5a_seal_state(state, detail)

    runner.recompute_from_seal(Recording(), runtime_guard=lambda: order.append("guard"))
    assert order == ["read", "guard", f"advance:{runner.STATE_COMPLETE}"]


def test_a_recovery_guard_refusal_advances_nothing(tmp_path: Path) -> None:
    _consume(FakeRepository(), tmp_path)
    FakeRepository.durable_seal["state"] = runner.STATE_SEALED_RAW_CAPTURED

    def _refuse() -> None:
        raise ProvenanceRefused("a module came from an unverified origin")

    with pytest.raises(ProvenanceRefused, match="unverified origin"):
        runner.recompute_from_seal(FakeRepository(), runtime_guard=_refuse)
    assert FakeRepository.durable_seal["state"] == runner.STATE_SEALED_RAW_CAPTURED


def test_recompute_from_seal_refuses_a_snapshot_that_diverges_from_the_raw_capture(
    tmp_path: Path,
) -> None:
    _consume(FakeRepository(), tmp_path)
    FakeRepository.durable_seal["raw_evidence"][0]["candidate_p_up_frac"] = 0.11
    with pytest.raises(runner.SnapshotTampered, match="captured before exposure"):
        runner.recompute_from_seal(FakeRepository())


def test_recompute_from_seal_refuses_a_seal_without_its_raw_capture(tmp_path: Path) -> None:
    _consume(FakeRepository(), tmp_path)
    FakeRepository.durable_seal.pop("raw_evidence")
    with pytest.raises(runner.SnapshotTampered, match="lacks the raw capture"):
        runner.recompute_from_seal(FakeRepository())


def test_recompute_from_seal_refuses_disagreeing_seal_columns(tmp_path: Path) -> None:
    _consume(FakeRepository(), tmp_path)
    FakeRepository.durable_seal["evidence_snapshot_id"] = "f" * 64
    with pytest.raises(runner.SnapshotTampered, match="disagrees with its captured snapshot"):
        runner.recompute_from_seal(FakeRepository())


def test_a_seal_that_never_captured_cannot_be_recovered_by_rereading(tmp_path: Path) -> None:
    class CaptureFails(FakeRepository):
        def capture_section_5a_snapshot(self, snapshot) -> None:
            raise RuntimeError("capture write failed")

    with pytest.raises(RuntimeError):
        _consume(CaptureFails(), tmp_path)
    repo = FakeRepository()
    with pytest.raises(runner.ConsumptionRefused, match="owner decision"):
        runner.recompute_from_seal(repo)
    assert repo.calls == []


def test_recompute_from_seal_after_a_statistics_failure_completes_the_seal(
    tmp_path: Path,
) -> None:
    broken = FakeRepository([evidence_row(T_CLOSE - timedelta(days=1))])
    broken._rows[0].pop("candidate_p_up_frac")
    with pytest.raises(KeyError):
        _consume(broken, tmp_path)
    assert FakeRepository.durable_seal["state"] == runner.STATE_SEALED_NO_RESULT


# --------------------------- D3: fail closed unless positively verified ---------------------------


def test_an_undeclared_repository_is_refused_by_the_library_itself(tmp_path: Path) -> None:
    """V807-F4. Absence of a declaration is refusal, never permission."""

    class Undeclared(FakeRepository):
        section_5a_seal_authority = None  # no declaration at all

    repo = Undeclared()
    with pytest.raises(runner.ConsumptionRefused, match="does not declare a seal authority"):
        _consume(repo, tmp_path)
    assert repo.calls == [] and repo.events == []
    assert FakeRepository.durable_seal is None


def test_there_is_no_switch_to_skip_pin_verification() -> None:
    """V807-F5. The bypass flag does not exist, so no caller can consume under unverified rules."""

    with pytest.raises(TypeError, match="verify_pin"):
        runner.run_consumption(
            FakeRepository(),
            confirmation=runner.CONFIRMATION_TOKEN,
            artifact_dir=Path("unused"),
            now_utc=AFTER_CLOSE,
            verify_pin=False,
        )
    with pytest.raises(TypeError, match="verify_pin"):
        runner.recompute_from_seal(FakeRepository(), verify_pin=False)


def test_seal_recovery_verifies_the_pin_positively(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from crypto_probability_engine.oos.evaluation import evaluator_pin

    _consume(FakeRepository(), tmp_path)

    def _mismatch():
        raise evaluator_pin.EvaluatorPinMismatch("simulated drift")

    monkeypatch.setattr(runner, "assert_evaluator_pin", _mismatch)
    with pytest.raises(evaluator_pin.EvaluatorPinMismatch):
        runner.recompute_from_seal(FakeRepository())


def test_seal_recovery_refuses_an_undeclared_repository(tmp_path: Path) -> None:
    class Undeclared(FakeRepository):
        section_5a_seal_authority = None

    with pytest.raises(runner.ConsumptionRefused, match="does not declare"):
        runner.recompute_from_seal(Undeclared())


# --------------------------- F1: scope enforced at admission ---------------------------


def _out_of_tranche_attack():
    """Codex V807-F1, reproduced: favourable SOL/USDT evidence beside losing BTC evidence."""

    from tests.oos.evaluation.conftest import T0

    days = range(22)
    losing_btc = [
        evidence_row(
            T0 + timedelta(days=d),
            symbol="BTC/USDT",
            candidate_up=[0.40, 0.41, 0.39, 0.42, 0.38, 0.43, 0.375][d % 7],
        )
        for d in days
    ]
    favourable_sol = [
        evidence_row(
            T0 + timedelta(days=d, minutes=m),
            symbol="SOL/USDT",
            candidate_up=[0.90, 0.91, 0.89, 0.92, 0.88, 0.93, 0.875][d % 7],
        )
        for d in days
        for m in (1, 2, 3, 4, 5)
    ]
    return losing_btc, favourable_sol


def test_an_out_of_tranche_asset_cannot_change_the_tranche_verdict() -> None:
    """V807-F1. The attack flipped A and B from False to True. It must change nothing now."""

    from crypto_probability_engine.oos.evaluation import decision
    from crypto_probability_engine.oos.evaluation.admission import admit
    from tests.oos.evaluation.conftest import T0

    losing_btc, favourable_sol = _out_of_tranche_attack()

    def verdict(rows):
        admission = admit(rows, t0=T0, t_close=T_CLOSE)
        result = decision.evaluate_timeframe("4H", admission, t0=T0, t_close=T_CLOSE)
        return result.state, result.a_holds, result.b_holds, result.admitted_pairs

    clean = verdict(losing_btc)
    attacked = verdict(losing_btc + favourable_sol)
    assert clean == attacked == ("NOT_PASS", False, False, 22)


def test_out_of_scope_rows_are_counted_not_silently_dropped() -> None:
    from crypto_probability_engine.oos.evaluation import diagnostics
    from crypto_probability_engine.oos.evaluation.admission import admit
    from tests.oos.evaluation.conftest import T0, T_FREEZE

    losing_btc, favourable_sol = _out_of_tranche_attack()
    admission = admit(losing_btc + favourable_sol, t0=T0, t_close=T_CLOSE)
    assert admission.tier1_out_of_scope == len(favourable_sol) == 110
    block = diagnostics.build(
        admission, t0=T0, t_close=T_CLOSE, t_freeze=T_FREEZE, timeframes=runner.TIMEFRAMES
    )
    assert block["tier1_out_of_scope"] == 110
    assert block["out_of_scope_breakdown"] == {"4H|SOL/USDT": 110}


def test_readiness_attainability_ignores_out_of_scope_evidence() -> None:
    """Scope at admission also stops a foreign asset manufacturing an ATTAINABLE verdict."""

    _, favourable_sol = _out_of_tranche_attack()
    report = runner.run_readiness(FakeRepository(favourable_sol), verify_pin=False)
    assert report["attainability"]["4H"]["verdict"] == "PASS_UNATTAINABLE"
    assert report["attainability"]["4H"]["usable_windows_c4"] == 0


# --------------------------- D4: decision_population_id ---------------------------


def test_decision_population_id_is_identical_in_readiness_and_consumption(tmp_path: Path) -> None:
    """The drift check §11 promised and never delivered: same state, same identity."""

    repo = FakeRepository()
    readiness = runner.run_readiness(repo, verify_pin=False)
    result = _consume(FakeRepository(), tmp_path)
    assert readiness["decision_population_id"] == result["decision_population_id"]
    assert readiness["evidence_snapshot_id"] != result["evidence_snapshot_id"], (
        "the integrity identity is not comparable across modes, by construction"
    )


def test_decision_population_id_changes_when_a_label_resolves() -> None:
    from tests.oos.evaluation.conftest import T0

    resolved = [evidence_row(T0 + timedelta(days=1))]
    unresolved = [evidence_row(T0 + timedelta(days=1), candidate_label=None)]
    assert runner.decision_population_id(resolved) != runner.decision_population_id(unresolved)


def test_decision_population_id_ignores_everything_that_cannot_affect_the_decision() -> None:
    """V807-F9. Post-close rows and other assets must not make the identity drift."""

    from tests.oos.evaluation.conftest import T0

    base = daily_4h_evidence()
    noise = [
        evidence_row(T_CLOSE + timedelta(hours=2)),
        evidence_row(T0 - timedelta(days=1)),
        evidence_row(T0 + timedelta(days=3), symbol="SOL/USDT"),
        evidence_row(T0 + timedelta(days=3), timeframe="1D"),
    ]
    assert runner.decision_population_id(base) == runner.decision_population_id(base + noise)
    assert runner.decision_population_id(base) == runner.decision_population_id(
        list(reversed(base))
    )


def test_decision_population_id_is_probability_free() -> None:
    from tests.oos.evaluation.conftest import T0

    a = [evidence_row(T0 + timedelta(days=1), candidate_up=0.60)]
    b = [evidence_row(T0 + timedelta(days=1), candidate_up=0.91)]
    assert runner.decision_population_id(a) == runner.decision_population_id(b)
    assert runner.evidence_snapshot_id(a) != runner.evidence_snapshot_id(b)


# --------------------------- F10, R2 ---------------------------


def test_seal_recovery_refuses_disagreeing_contract_instants(tmp_path: Path) -> None:
    """V807-F10."""

    _consume(FakeRepository(), tmp_path)
    FakeRepository.durable_seal["contract_instants"] = {
        **FakeRepository.durable_seal["contract_instants"],
        "t0": "2026-08-22T04:00:00+00:00",
    }
    with pytest.raises(runner.SnapshotTampered, match="contract instants disagree"):
        runner.recompute_from_seal(FakeRepository())


def test_readiness_refuses_with_a_readiness_error_not_a_consumption_error() -> None:
    """V807-R2."""

    with pytest.raises(runner.ReadinessRefused, match="not a measured integer"):
        runner.run_readiness(FakeRepository(origin_anomalies=None), verify_pin=False)


# --------------------------- E2=A: the verified run provenance ---------------------------


def test_consumption_records_the_verified_run_in_the_claim_and_the_snapshot(tmp_path: Path) -> None:
    record = verified_provenance()
    result = _consume(FakeRepository(), tmp_path, provenance=record)
    seal = FakeRepository.durable_seal
    assert seal["run_provenance"] == record, "the durable claim names the run that spent the look"
    assert seal["snapshot_payload"]["run_provenance"] == record
    assert result["run_provenance"] == record


def test_an_unverifiable_provenance_is_refused_before_the_repository_is_touched(
    tmp_path: Path,
) -> None:
    from crypto_probability_engine.oos.evaluation.provenance import ProvenanceRefused

    for tamper in (
        {"ref": "refs/heads/feature"},
        {"sha": "b" * 40},
        {"python_version": "3.12.11"},
        {"pin_digest": "0" * 64},
        {"dispatch_verified": False},
    ):
        repo = FakeRepository()
        with pytest.raises(ProvenanceRefused):
            _consume(repo, tmp_path, provenance={**verified_provenance(), **tamper})
        assert repo.calls == [] and repo.events == [], tamper
        assert FakeRepository.durable_seal is None, tamper


def test_a_look_taken_without_provenance_can_never_be_recovered(tmp_path: Path) -> None:
    """Declared doubles may omit the record (as D3 lets them declare the authority), but such a
    look is not a verified one: recovery refuses to bless it."""

    _consume(FakeRepository(), tmp_path, provenance=None)
    assert FakeRepository.durable_seal["run_provenance"] is None
    with pytest.raises(runner.SnapshotTampered, match="does not carry a verified run provenance"):
        runner.recompute_from_seal(FakeRepository())


def test_seal_recovery_refuses_a_snapshot_that_names_a_different_run(tmp_path: Path) -> None:
    _consume(FakeRepository(), tmp_path)
    FakeRepository.durable_seal["snapshot_payload"]["run_provenance"] = {
        **FakeRepository.durable_seal["run_provenance"],
        "run_id": "987654321",
    }
    with pytest.raises(runner.SnapshotTampered, match="differs from the durable claim"):
        runner.recompute_from_seal(FakeRepository())


def test_seal_recovery_refuses_a_claim_whose_provenance_was_rewritten(tmp_path: Path) -> None:
    _consume(FakeRepository(), tmp_path)
    FakeRepository.durable_seal["run_provenance"] = {
        **FakeRepository.durable_seal["run_provenance"],
        "ref": "refs/heads/elsewhere",
    }
    with pytest.raises(runner.SnapshotTampered, match="does not carry a verified run provenance"):
        runner.recompute_from_seal(FakeRepository())


# --------------------------------------------------------------------------- G1=A: loaded code


def test_the_runtime_guard_runs_after_the_pre_claim_reads_and_before_the_claim(
    tmp_path: Path,
) -> None:
    """The reads before the claim may import driver code; the guard sees all of it."""

    order: list[str] = []

    class Recording(FakeRepository):
        def fetch_oos_feature_diagnostics(self):
            order.append("reads")
            return super().fetch_oos_feature_diagnostics()

        def claim_section_5a_seal(self, payload) -> bool:
            order.append("claim")
            return super().claim_section_5a_seal(payload)

    _consume(Recording(), tmp_path, runtime_guard=lambda: order.append("guard"))
    assert order == ["reads", "guard", "claim"]


def test_a_refusing_runtime_guard_spends_nothing(tmp_path: Path) -> None:
    from crypto_probability_engine.runtime_isolation import IsolationRefused

    def _refuse() -> None:
        raise IsolationRefused("a loaded module came from an unverified origin")

    repo = FakeRepository()
    with pytest.raises(IsolationRefused):
        _consume(repo, tmp_path, runtime_guard=_refuse)
    assert FakeRepository.durable_seal is None, "no claim"
    assert True not in repo.calls, "no probability read"


# --------------------------- Addendum 10: the readiness population guard (§2.6) ---------------


def _population(rows) -> str:
    return runner.decision_population_id(rows)


def test_a_verified_consumption_that_names_no_population_refuses_before_any_read(
    tmp_path: Path,
) -> None:
    repo = FakeRepository()
    refusal = "must name the FULL decision_population_id"
    with pytest.raises(runner.ConsumptionRefused, match=refusal):
        _consume(repo, tmp_path, expected_population_id=None)
    assert repo.calls == [] and repo.events == []
    assert FakeRepository.durable_seal is None


@pytest.mark.parametrize(
    "malformed",
    [
        "f83c31f7bd5a9a4d",
        "F" * 64,
        "f" * 63,
        "f" * 65,
        " " + "f" * 64,
        f" {'f' * 64} ",
        "   ",
        "g" * 64,
        "",
        "\u0660" * 64,  # Arabic-Indic digits (task-814)
        "\uff46" * 64,  # full-width f (task-814)
    ],
)
def test_anything_but_the_full_identity_refuses_before_any_read(
    tmp_path: Path, malformed: str
) -> None:
    repo = FakeRepository()
    with pytest.raises(runner.ConsumptionRefused, match="FULL 64-character"):
        _consume(repo, tmp_path, expected_population_id=malformed)
    assert repo.calls == [] and repo.events == []
    assert FakeRepository.durable_seal is None


def test_a_population_mismatch_stops_unconsumed(tmp_path: Path) -> None:
    """The owner's condition: a mismatch spends nothing and exposes no probability."""

    repo = FakeRepository()
    other = _population(daily_4h_evidence()[:-1])
    assert other != _population(repo._rows)
    with pytest.raises(runner.ReadinessPopulationMismatch, match="STOPPED UNCONSUMED"):
        _consume(repo, tmp_path, expected_population_id=other)
    assert repo.calls == [False], "only the probability-free projection was read"
    assert "read_probabilities" not in repo.events
    assert FakeRepository.durable_seal is None, "nothing was claimed"
    assert not any(tmp_path.iterdir()), "no artifact was written"


def test_the_population_is_checked_before_the_guard_the_claim_and_any_probability(
    tmp_path: Path,
) -> None:
    order: list[str] = []

    class Recording(FakeRepository):
        def fetch_oos_paired_evidence(self, *, include_probabilities: bool):
            order.append("probabilities" if include_probabilities else "population")
            return super().fetch_oos_paired_evidence(include_probabilities=include_probabilities)

        def claim_section_5a_seal(self, payload) -> bool:
            order.append("claim")
            return super().claim_section_5a_seal(payload)

    _consume(Recording(), tmp_path, runtime_guard=lambda: order.append("guard"))
    assert order == ["population", "guard", "claim", "probabilities"]


def test_the_pre_claim_identity_is_exactly_readiness_s(tmp_path: Path) -> None:
    """Same function, same probability-free projection: readiness's ID is what consume accepts."""

    readiness = runner.run_readiness(FakeRepository())
    result = _consume(
        FakeRepository(), tmp_path, expected_population_id=readiness["decision_population_id"]
    )
    assert result["population_matches_readiness"] is True
    assert result["expected_decision_population_id"] == readiness["decision_population_id"]
    assert result["decision_population_id"] == readiness["decision_population_id"]


def _remove_a_pair(rows):
    return rows[:-1]


def _add_a_pair(rows):
    return [*rows, evidence_row(T0 + timedelta(hours=2))]


def _relabel_a_pair(rows):
    changed = [dict(row) for row in rows]
    changed[0]["baseline_realized_label"] = "DOWN"
    changed[0]["candidate_realized_label"] = "DOWN"
    return changed


@pytest.mark.parametrize("drift", [_remove_a_pair, _add_a_pair, _relabel_a_pair])
def test_population_drift_under_the_claim_computes_no_statistic(tmp_path: Path, drift) -> None:
    """The population actually read differs from what was checked: CAPTURE_FAILED, no result."""

    class DriftsAfterTheCheck(FakeRepository):
        def fetch_oos_paired_evidence(self, *, include_probabilities: bool):
            rows = super().fetch_oos_paired_evidence(include_probabilities=include_probabilities)
            return drift(rows) if include_probabilities else rows

    repo = DriftsAfterTheCheck()
    with pytest.raises(runner.ConsumedPopulationDrift, match="no statistic is computed"):
        _consume(repo, tmp_path)
    assert FakeRepository.durable_seal["state"] == runner.STATE_CAPTURE_FAILED
    assert FakeRepository.durable_seal.get("snapshot_payload") is None
    assert not (tmp_path / runner.RESULT_FILENAME).exists()
    assert not (tmp_path / runner.SNAPSHOT_FILENAME).exists()
    with pytest.raises(runner.ConsumptionRefused, match="owner decision"):
        runner.recompute_from_seal(FakeRepository())


def test_both_population_refusals_are_deliberate_consumption_refusals() -> None:
    assert issubclass(runner.ReadinessPopulationMismatch, runner.ConsumptionRefused)
    assert issubclass(runner.ConsumedPopulationDrift, runner.ConsumptionRefused)


def test_a_probability_column_in_the_pre_claim_projection_refuses_before_the_claim(
    tmp_path: Path,
) -> None:
    """task-814: the consumption projection is held to readiness's structural boundary."""

    class LeakyProjection(FakeRepository):
        def fetch_oos_paired_evidence(self, *, include_probabilities: bool):
            self.calls.append(include_probabilities)
            return [dict(row) for row in self._rows]  # ignores the flag

    repo = LeakyProjection()
    with pytest.raises(runner.ConsumptionRefused, match="structural boundary"):
        _consume(repo, tmp_path)
    assert repo.calls == [False]
    assert FakeRepository.durable_seal is None


def test_a_probability_only_difference_is_not_population_drift(tmp_path: Path) -> None:
    """By §26's definition the identity is probability-free, so only the population can drift."""

    class ProbabilityOnly(FakeRepository):
        def fetch_oos_paired_evidence(self, *, include_probabilities: bool):
            rows = super().fetch_oos_paired_evidence(include_probabilities=include_probabilities)
            if include_probabilities:
                rows[0]["candidate_p_up_frac"] = 0.2
                rows[0]["candidate_p_down_frac"] = 0.3
                rows[0]["candidate_p_timeout_frac"] = 0.5
            return rows

    result = _consume(ProbabilityOnly(), tmp_path)
    assert result["population_matches_readiness"] is True
    assert FakeRepository.durable_seal["state"] == runner.STATE_COMPLETE
