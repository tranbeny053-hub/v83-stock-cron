"""Adversarial RED tests for the frozen section 5A evaluator (task-806).

These tests state the required properties.  They intentionally fail at ``2b31832``;
the repair pass, not this test-authoring pass, owns making them green.  All repository
and driver behaviour is simulated locally.
"""

from __future__ import annotations

import inspect
import json
import os
import shutil
import subprocess
import sys
import threading
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from crypto_probability_engine.oos.evaluation import diagnostics, evaluator_pin, runner
from crypto_probability_engine.oos.evaluation.admission import admit
from crypto_probability_engine.persistence import repository as repository_module
from crypto_probability_engine.persistence.repository import InMemoryPersistenceRepository
from tests.oos.evaluation.conftest import T0, T_CLOSE, T_FREEZE, daily_4h_evidence

AFTER_CLOSE = T_CLOSE + timedelta(hours=1)


class _SealCursor:
    """Tiny psycopg cursor double: records a successful singleton insert."""

    def __init__(self) -> None:
        self.executed = False

    def execute(self, _sql, _params=None) -> None:
        self.executed = True

    def fetchone(self):
        return ("SINGLETON",) if self.executed else None


class _DriverRepository:
    """Driver-shaped repository with the real Postgres seal serializer."""

    def __init__(self, rows, *, feature_rows=()) -> None:
        self.rows = deepcopy(list(rows))
        self.feature_rows = deepcopy(list(feature_rows))
        self.probability_reads = 0
        self.seal = None

    def fetch_section_5a_seal(self):
        return deepcopy(self.seal)

    def count_oos_origin_anomalies(self) -> int:
        return 0

    def fetch_oos_feature_diagnostics(self):
        return deepcopy(self.feature_rows)

    def fetch_oos_paired_evidence(self, *, include_probabilities: bool):
        if include_probabilities:
            self.probability_reads += 1
        return deepcopy(self.rows)

    def claim_section_5a_seal(self, payload) -> bool:
        claimed = repository_module._claim_section_5a_seal_row(_SealCursor(), payload)
        if claimed:
            self.seal = deepcopy(dict(payload))
        return claimed

    def advance_section_5a_seal_state(self, state: str, detail: str = "") -> None:
        if self.seal is None:
            raise RuntimeError("no durable seal")
        self.seal["state"] = state
        self.seal["state_detail"] = detail


def _consume(repository, artifact_dir: Path):
    return runner.run_consumption(
        repository,
        confirmation=runner.CONFIRMATION_TOKEN,
        artifact_dir=artifact_dir,
        now_utc=AFTER_CLOSE,
        verify_pin=False,
    )


def _decimal_probabilities(rows):
    converted = deepcopy(list(rows))
    for row in converted:
        for key, value in list(row.items()):
            if key.endswith(("_p_up_frac", "_p_down_frac", "_p_timeout_frac")):
                row[key] = Decimal(str(value))
    return converted


def _valid_snapshot(*, feature_rows=(), origin_anomalies: int = 0) -> dict:
    rows = daily_4h_evidence()
    pin_digest = str(evaluator_pin.current_pin_artifacts()["closure_digest"])
    snapshot_id = runner.evidence_snapshot_id(
        rows, feature_rows=feature_rows, origin_anomalies=origin_anomalies
    )
    return {
        "captured_at_utc": AFTER_CLOSE.isoformat(),
        "evidence_snapshot_id": snapshot_id,
        "result_inputs_digest": runner.result_inputs_digest(snapshot_id, pin_digest),
        "evaluator_pin_digest": pin_digest,
        "t_freeze": T_FREEZE.isoformat(),
        "t0": T0.isoformat(),
        "t_close": T_CLOSE.isoformat(),
        "timeframes": list(runner.TIMEFRAMES),
        "origin_anomalies": origin_anomalies,
        "feature_rows": deepcopy(list(feature_rows)),
        "rows": rows,
    }


def _write_snapshot(directory: Path, snapshot: dict) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / runner.SNAPSHOT_FILENAME).write_bytes(runner._pretty_json(snapshot))


def test_g1_1_decimal_probabilities_cannot_be_read_without_a_durable_seal(
    tmp_path: Path,
) -> None:
    repository = _DriverRepository(_decimal_probabilities(daily_4h_evidence()))

    try:
        _consume(repository, tmp_path)
    except Exception:  # the property permits failure only after a durable capture
        pass

    assert repository.probability_reads == 0 or repository.seal is not None, (
        "Decimal probabilities were read, but no durable seal captured them"
    )


def test_g1_2_every_projected_driver_type_is_safe_before_the_look_returns(
    tmp_path: Path,
) -> None:
    cases = {
        "NUMERIC->Decimal": (
            _decimal_probabilities(daily_4h_evidence()),
            [],
        ),
        "TIMESTAMPTZ->datetime": (daily_4h_evidence(), []),
        "TEXT->str": (daily_4h_evidence(), [{"prediction_id": "text", "regime": "CALM"}]),
        "JSONB->dict/list": (
            daily_4h_evidence(),
            [{"prediction_id": "jsonb", "raw": {"nested": [1, "two", None]}}],
        ),
        "NULL->None": (
            daily_4h_evidence(),
            [{"prediction_id": "null", "regime": None}],
        ),
    }
    unsafe = []
    for index, (driver_type, (rows, feature_rows)) in enumerate(cases.items()):
        repository = _DriverRepository(rows, feature_rows=feature_rows)
        try:
            _consume(repository, tmp_path / str(index))
        except Exception as exc:  # completion is optional; sealing is not
            if repository.probability_reads and repository.seal is None:
                unsafe.append(f"{driver_type}: {type(exc).__name__}: {exc}")

    assert unsafe == [], "driver values spent an unsealed look: " + "; ".join(unsafe)


def test_g1_3_decimal_driver_output_hashes_identically_across_processes() -> None:
    program = """
from decimal import Decimal
from crypto_probability_engine.oos.evaluation.runner import evidence_snapshot_id
row = {
    'reference_close_utc': '2026-08-21T04:00:00+00:00',
    'candidate_p_up_frac': Decimal('0.6'),
    'payload': {'items': [None, 'x']},
}
print(evidence_snapshot_id([row]))
"""
    environment = dict(os.environ)
    environment["PYTHONPATH"] = os.pathsep.join(("src", "."))
    runs = [
        subprocess.run(
            [sys.executable, "-c", program],
            check=False,
            capture_output=True,
            text=True,
            env=environment,
        )
        for _ in range(2)
    ]
    errors = [run.stderr.strip().splitlines()[-1] for run in runs if run.returncode]

    assert errors == [], "cross-process canonicalization failed: " + "; ".join(errors)
    assert runs[0].stdout.strip() == runs[1].stdout.strip()


def test_g1_4_numerically_identical_decimal_and_float_have_one_digest() -> None:
    decimal_digest = runner.evidence_snapshot_id([{"scored_value": Decimal("0.6")}])
    float_digest = runner.evidence_snapshot_id([{"scored_value": 0.6}])

    assert decimal_digest == float_digest, (
        "the digest must not depend on whether psycopg returned Decimal or float"
    )


def test_g2_1_recompute_refuses_a_snapshot_missing_evaluator_pin_digest(
    tmp_path: Path,
) -> None:
    snapshot = _valid_snapshot()
    del snapshot["evaluator_pin_digest"]
    _write_snapshot(tmp_path, snapshot)

    with pytest.raises(runner.SnapshotTampered):
        runner.recompute_from_snapshot(tmp_path, verify_pin=False)


def test_g2_2_recompute_refuses_an_altered_result_inputs_digest(tmp_path: Path) -> None:
    snapshot = _valid_snapshot()
    snapshot["result_inputs_digest"] = "0" * 64
    _write_snapshot(tmp_path, snapshot)

    with pytest.raises(runner.SnapshotTampered):
        runner.recompute_from_snapshot(tmp_path, verify_pin=False)


def test_g2_3_every_security_relevant_snapshot_field_is_integrity_checked(
    tmp_path: Path,
) -> None:
    mutations = {
        "rows": lambda value: value[0].__setitem__("candidate_p_up_frac", 0.99),
        "feature_rows": lambda value: value.append({"prediction_id": "injected"}),
        "origin_anomalies": lambda _value: 17,
        "evidence_snapshot_id": lambda _value: "1" * 64,
        "result_inputs_digest": lambda _value: "2" * 64,
        "evaluator_pin_digest": lambda _value: "3" * 64,
    }
    unchecked = []
    for index, (field, mutate) in enumerate(mutations.items()):
        snapshot = _valid_snapshot()
        replacement = mutate(snapshot[field])
        if replacement is not None:
            snapshot[field] = replacement
        directory = tmp_path / str(index)
        _write_snapshot(directory, snapshot)
        try:
            runner.recompute_from_snapshot(directory, verify_pin=False)
        except runner.SnapshotTampered:
            continue
        unchecked.append(field)

    assert unchecked == [], f"trusted snapshot fields were not integrity-checked: {unchecked}"


class _ConcurrentRepository:
    """Two genuinely concurrent callers sharing one simulated durable authority."""

    def __init__(self, store=None) -> None:
        self.store = store or {
            "lock": threading.Lock(),
            "barrier": threading.Barrier(2),
            "seal": None,
            "probability_reads": 0,
        }
        self.rows = daily_4h_evidence()

    def fresh_handle(self):
        return _ConcurrentRepository(self.store)

    def fetch_section_5a_seal(self):
        with self.store["lock"]:
            return deepcopy(self.store["seal"])

    def count_oos_origin_anomalies(self) -> int:
        return 0

    def fetch_oos_feature_diagnostics(self):
        return []

    def fetch_oos_paired_evidence(self, *, include_probabilities: bool):
        if include_probabilities:
            with self.store["lock"]:
                self.store["probability_reads"] += 1
            self.store["barrier"].wait(timeout=5)
        return deepcopy(self.rows)

    def claim_section_5a_seal(self, payload) -> bool:
        with self.store["lock"]:
            if self.store["seal"] is not None:
                return False
            self.store["seal"] = deepcopy(dict(payload))
            return True

    def advance_section_5a_seal_state(self, state: str, detail: str = "") -> None:
        with self.store["lock"]:
            self.store["seal"]["state"] = state
            self.store["seal"]["state_detail"] = detail


def _concurrent_consumptions(tmp_path: Path):
    repository = _ConcurrentRepository()
    outcomes = [None, None]

    def invoke(index: int) -> None:
        try:
            outcomes[index] = _consume(repository.fresh_handle(), tmp_path / str(index))
        except Exception as exc:  # retain the exact loser type for assertions
            outcomes[index] = exc

    threads = [threading.Thread(target=invoke, args=(index,)) for index in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
    assert all(not thread.is_alive() for thread in threads), "concurrency probe deadlocked"
    return repository, outcomes


def test_g3_1_two_concurrent_consumptions_read_probabilities_at_most_once(
    tmp_path: Path,
) -> None:
    repository, _outcomes = _concurrent_consumptions(tmp_path)

    assert repository.store["probability_reads"] <= 1, (
        "both concurrent consumers read the holdout before either claimed the seal"
    )


def test_g3_4_concurrency_preserves_durability_and_no_read_without_a_seal(
    tmp_path: Path,
) -> None:
    repository, outcomes = _concurrent_consumptions(tmp_path)
    successes = [value for value in outcomes if isinstance(value, dict)]
    refusals = [
        value for value in outcomes if isinstance(value, runner.OneLookAlreadyConsumed)
    ]
    durable = repository.fresh_handle().fetch_section_5a_seal()

    assert len(successes) == 1
    assert len(refusals) == 1
    assert repository.store["probability_reads"] == 1
    assert durable is not None and durable["snapshot_payload"]["rows"]


def _mirrored_pin_root(tmp_path: Path) -> tuple[Path, Path]:
    root = evaluator_pin.project_root()
    for relative in evaluator_pin.pinned_files(root):
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / relative, destination)
    entrypoint = Path("scripts/evaluate_section_5a.py")
    (tmp_path / entrypoint).parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(root / entrypoint, tmp_path / entrypoint)
    pin_path = tmp_path / "pin.json"
    pin_path.write_text(json.dumps(evaluator_pin.current_pin_artifacts(tmp_path)))
    return pin_path, tmp_path / entrypoint


def test_g4_1_editing_the_pin_controlling_cli_entrypoint_breaks_the_pin(
    tmp_path: Path,
) -> None:
    pin_path, entrypoint = _mirrored_pin_root(tmp_path)
    entrypoint.write_text(entrypoint.read_text() + "\n# verify-pin bypass drift\n")

    with pytest.raises(evaluator_pin.EvaluatorPinMismatch):
        evaluator_pin.assert_evaluator_pin(pin_path=pin_path, root=tmp_path)


def test_g4_3_every_production_answer_control_surface_is_declared_in_the_pin() -> None:
    answer_control_surface = {
        "scripts/evaluate_section_5a.py",
        "src/crypto_probability_engine/persistence/repository.py",
    }

    assert answer_control_surface <= set(evaluator_pin.pinned_files()), (
        "production files can select the evaluator path while remaining outside its pin: "
        f"{sorted(answer_control_surface - set(evaluator_pin.pinned_files()))}"
    )


class _SqlCursor:
    def __init__(self) -> None:
        self.statements = []

    def execute(self, sql, _params=None) -> None:
        self.statements.append(sql)

    def fetchall(self):
        return []

    def fetchone(self):
        return None


def test_g5_2_every_digest_feeding_database_read_has_a_deterministic_order() -> None:
    readers = {
        "predictions": lambda cursor: repository_module._fetch_oos_prediction_rows(
            cursor, include_probabilities=True
        ),
        "outcomes": repository_module._fetch_oos_outcome_labels,
        "feature_diagnostics": repository_module._fetch_oos_feature_diagnostic_rows,
    }
    unordered = []
    for name, read in readers.items():
        cursor = _SqlCursor()
        read(cursor)
        if not cursor.statements or "ORDER BY" not in cursor.statements[0].upper():
            unordered.append(name)

    assert unordered == [], f"digest-feeding SQL reads lack ORDER BY: {unordered}"


def test_g5_3_evidence_digest_is_order_independent_even_if_driver_order_changes() -> None:
    rows = daily_4h_evidence()
    features = [
        {"prediction_id": row["candidate_prediction_id"], "regime": "CALM"}
        for row in rows
    ]
    forward = runner.evidence_snapshot_id(rows, feature_rows=features)
    reversed_driver = runner.evidence_snapshot_id(
        list(reversed(rows)), feature_rows=list(reversed(features))
    )

    assert forward == reversed_driver, "row ordering changed the evidence identity"


class _ReadinessRepository:
    def __init__(self, rows, features) -> None:
        self.rows = deepcopy(rows)
        self.features = deepcopy(features)

    def fetch_oos_paired_evidence(self, *, include_probabilities: bool):
        assert include_probabilities is False
        rows = deepcopy(self.rows)
        for row in rows:
            for key in list(row):
                if key.endswith(("_p_up_frac", "_p_down_frac", "_p_timeout_frac")):
                    del row[key]
        return rows

    def fetch_oos_feature_diagnostics(self):
        return deepcopy(self.features)

    def count_oos_origin_anomalies(self) -> int:
        return 0


def test_g6_1_contract_diagnostics_are_complete_per_timeframe_and_cell_in_both_modes() -> None:
    rows = daily_4h_evidence()
    features = [
        {
            "prediction_id": row["candidate_prediction_id"],
            "regime": "CALM",
            "realized_vol": 0.2,
            "trend_mtf": "UP",
            "volume_anomaly": 1.1,
        }
        for row in rows
    ]
    readiness = runner.run_readiness(
        _ReadinessRepository(rows, features), now_utc=AFTER_CLOSE, verify_pin=False
    )
    consumption = runner.compute_from_snapshot(
        _valid_snapshot(feature_rows=features), now_utc=AFTER_CLOSE
    )
    required = {
        "admitted_pairs",
        "usable_windows",
        "dropped_windows",
        "missed_attempts",
        "realized_label_distribution",
        "regime_distribution",
        "realized_vol_summary",
        "trend_mtf_distribution",
        "volume_anomaly_summary",
        "first_reference_close_utc",
        "last_reference_close_utc",
        "realised_span_seconds",
        "t_freeze",
        "t0",
        "activation_gap_seconds",
    }
    missing = []
    incomplete_labels = []
    for mode, report in (("readiness", readiness), ("consumption", consumption)):
        timeframe = report["diagnostics"]["per_timeframe"]["4H"]
        cell = timeframe["per_symbol"]["BTC/USDT"]
        for level, block in (("timeframe", timeframe), ("cell", cell)):
            absent = sorted(required - block.keys())
            if absent:
                missing.append(f"{mode}.{level}: {absent}")
            labels = set(block["realized_label_distribution"])
            if labels != set(diagnostics.OUTCOME_LABELS):
                incomplete_labels.append(f"{mode}.{level}: {sorted(labels)}")

    assert missing == [], "mandatory diagnostics missing: " + "; ".join(missing)
    assert incomplete_labels == [], (
        "realized-label distributions omitted declared labels: "
        + "; ".join(incomplete_labels)
    )


def test_g6_2_unmeasured_quantities_are_never_rendered_as_measured_numbers() -> None:
    empty = admit([], t0=T0, t_close=T_CLOSE)
    block = diagnostics.build(
        empty, t0=T0, t_close=T_CLOSE, t_freeze=T_FREEZE, timeframes=["4H"]
    )
    timeframe = block["per_timeframe"]["4H"]
    fabricated = []
    if block["origin_anomalies"] == 0:
        fabricated.append("origin_anomalies=0 without an anomaly measurement")
    if timeframe["realised_span_seconds"] == 0:
        fabricated.append("realised_span_seconds=0 without any reference closes")

    assert fabricated == [], "fabricated diagnostic defaults: " + "; ".join(fabricated)


def _tier1_rows(run_id: str, *, explicit_only: bool) -> list[dict]:
    rows = []
    reference = datetime(2026, 8, 22, 4, tzinfo=UTC)
    for arm, methodology in (
        ("BASELINE", repository_module.OOS_BASELINE_METHODOLOGY),
        ("CANDIDATE", repository_module.OOS_CANDIDATE_METHODOLOGY),
    ):
        suffix = f":{arm}" if not explicit_only else ":NOT_VISIBLE_TO_SQL"
        row = {
            "prediction_id": f"{run_id}:4H{suffix}",
            "run_id": run_id,
            "normalized_symbol": "BTC/USDT",
            "timeframe": "4H",
            "reference_close_utc": reference,
            "methodology_version": methodology,
        }
        if explicit_only:
            row["arm"] = arm
        rows.append(row)
    return rows


def _sql_visible_tier1_run_ids(rows) -> set[str]:
    grouped = {}
    for row in rows:
        key = (
            row["run_id"],
            row["normalized_symbol"],
            row["timeframe"],
            row["reference_close_utc"],
        )
        grouped.setdefault(key, []).append(row)
    admitted = set()
    for key, group in grouped.items():
        baseline = [
            row
            for row in group
            if str(row["prediction_id"]).endswith(":BASELINE")
            and row["methodology_version"] == repository_module.OOS_BASELINE_METHODOLOGY
        ]
        candidate = [
            row
            for row in group
            if str(row["prediction_id"]).endswith(":CANDIDATE")
            and row["methodology_version"] == repository_module.OOS_CANDIDATE_METHODOLOGY
        ]
        if len(group) == 2 and len(baseline) == len(candidate) == 1:
            admitted.add(str(key[0]))
    return admitted


def test_g7_1_in_memory_and_postgres_tier1_qualifiers_admit_identical_populations() -> None:
    regular_run = "oosb-" + "a" * 32
    explicit_run = "oosb-" + "b" * 32
    rows = _tier1_rows(regular_run, explicit_only=False) + _tier1_rows(
        explicit_run, explicit_only=True
    )
    in_memory = {
        str(pair["run_id"]) for pair in repository_module._oos_qualifying_pairs(rows)
    }
    postgres = _sql_visible_tier1_run_ids(rows)

    assert in_memory == postgres, (
        f"Tier-1 population diverged: in_memory={sorted(in_memory)}, postgres={sorted(postgres)}"
    )


def test_g7_2_explicit_arm_logic_cannot_coexist_with_suffix_only_sql() -> None:
    arm_source = inspect.getsource(repository_module._oos_arm)
    cursor = _SqlCursor()
    repository_module._fetch_oos_t0_row(cursor)
    sql = cursor.statements[0].lower()
    accepts_explicit_arm = 'row.get("arm")' in arm_source
    sql_can_see_arm = " arm" in sql or "arm," in sql

    assert not accepts_explicit_arm or sql_can_see_arm, (
        "_oos_arm accepts row['arm'], but the Postgres qualifier can only see prediction_id"
    )


# Sibling sweep findings.  These are deliberately numbered beyond G7.


def test_g8_process_local_repository_is_not_accepted_as_a_durable_seal_authority(
    tmp_path: Path,
) -> None:
    with pytest.raises((runner.ConsumptionRefused, RuntimeError), match="durable|Postgres"):
        _consume(InMemoryPersistenceRepository(), tmp_path)


def test_g9_postgres_seal_serializer_accepts_every_value_the_digest_accepts() -> None:
    snapshot = _valid_snapshot()
    runner._canonical_json(snapshot)  # establishes that the digest path accepts it
    payload = {
        "sealed_at_utc": AFTER_CLOSE.isoformat(),
        "evidence_snapshot_id": snapshot["evidence_snapshot_id"],
        "result_inputs_digest": snapshot["result_inputs_digest"],
        "evaluator_pin_digest": snapshot["evaluator_pin_digest"],
        "contract_instants": {"t0": T0.isoformat()},
        "snapshot_payload": snapshot,
    }

    assert repository_module._claim_section_5a_seal_row(_SealCursor(), payload) is True


def test_g10_missing_captured_diagnostics_are_not_defaulted_during_recompute(
    tmp_path: Path,
) -> None:
    accepted_absences = []
    for field in ("feature_rows", "origin_anomalies"):
        snapshot = _valid_snapshot()
        del snapshot[field]
        directory = tmp_path / field
        _write_snapshot(directory, snapshot)
        try:
            runner.recompute_from_snapshot(directory, verify_pin=False)
        except runner.SnapshotTampered:
            continue
        accepted_absences.append(field)

    assert accepted_absences == [], (
        "missing captured diagnostics were treated as empty/zero: "
        f"{accepted_absences}"
    )


def test_g11_empty_population_has_no_measured_realised_span() -> None:
    empty = admit([], t0=T0, t_close=T_CLOSE)
    block = diagnostics.build(
        empty, t0=T0, t_close=T_CLOSE, t_freeze=T_FREEZE, timeframes=["4H"]
    )

    assert block["per_timeframe"]["4H"]["realised_span_seconds"] is None
