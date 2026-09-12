"""Readiness vs consumption, the five guards, and the one-shot failure states.

No database is contacted: the repository is a fake built from synthetic evidence.
"""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import pytest

from crypto_probability_engine.oos.evaluation import runner
from tests.oos.evaluation.conftest import T_CLOSE, daily_4h_evidence, evidence_row

AFTER_CLOSE = T_CLOSE + timedelta(hours=2)


@pytest.fixture(autouse=True)
def _clear_durable_seal():
    FakeRepository.durable_seal = None
    yield
    FakeRepository.durable_seal = None


class FakeRepository:
    """Records how it was called. Never touches a database."""

    durable_seal: dict | None = None

    def __init__(self, rows=None, *, origin_anomalies: int = 0, features=()):
        self._rows = list(rows if rows is not None else daily_4h_evidence())
        self._origin_anomalies = origin_anomalies
        self._features = list(features)
        self.calls: list[bool] = []
        self.seal: dict | None = None

    def fetch_oos_paired_evidence(self, *, include_probabilities: bool):
        self.calls.append(include_probabilities)
        rows = []
        for row in self._rows:
            copy = dict(row)
            if not include_probabilities:
                for key in list(copy):
                    if key.endswith(("_p_up_frac", "_p_down_frac", "_p_timeout_frac")):
                        del copy[key]
            rows.append(copy)
        return rows

    def count_oos_origin_anomalies(self) -> int:
        return self._origin_anomalies

    def fetch_oos_feature_diagnostics(self):
        return list(self._features)

    # The durable seal is the cross-run authority (finding F2). The fake models it as
    # process state SHARED between instances via the class attribute below, because the
    # real defect was that a fresh runner got a fresh filesystem.
    def claim_section_5a_seal(self, payload) -> bool:
        if type(self).durable_seal is not None:
            return False
        type(self).durable_seal = dict(payload)
        return True

    def fetch_section_5a_seal(self):
        seal = type(self).durable_seal
        return None if seal is None else dict(seal)

    def advance_section_5a_seal_state(self, state: str, detail: str = "") -> None:
        if type(self).durable_seal is None:
            raise RuntimeError("no seal to advance")
        type(self).durable_seal["state"] = state
        type(self).durable_seal["state_detail"] = detail


# --------------------------- readiness ---------------------------


def test_readiness_never_requests_probabilities() -> None:
    repo = FakeRepository()
    runner.run_readiness(repo)
    assert repo.calls == [False]


def test_readiness_output_contains_no_score_of_any_kind() -> None:
    """Scan the DATA, not the prose: the explanatory note names what is absent."""

    report = runner.run_readiness(FakeRepository())
    payload = {key: value for key, value in report.items() if key != "note"}
    rendered = json.dumps(payload).lower()
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
    params = {
        "confirmation": runner.CONFIRMATION_TOKEN,
        "artifact_dir": tmp_path,
        "now_utc": AFTER_CLOSE,
        "verify_pin": False,
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
            verify_pin=True,
        )
    assert repo.calls == [], "the pin is verified before the holdout is touched"
    assert not (tmp_path / runner.SNAPSHOT_FILENAME).exists()


def test_the_real_committed_pin_lets_consumption_proceed(tmp_path: Path) -> None:
    """Guard the guard: verify_pin=True must not be permanently broken."""

    result = runner.run_consumption(
        FakeRepository(),
        confirmation=runner.CONFIRMATION_TOKEN,
        artifact_dir=tmp_path,
        now_utc=AFTER_CLOSE,
        verify_pin=True,
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


def test_the_seal_and_the_raw_capture_are_one_atomic_write(tmp_path: Path) -> None:
    """The claim carries the snapshot, so there is no state where one exists alone."""

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
