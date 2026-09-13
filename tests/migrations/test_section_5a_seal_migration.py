"""The one-look seal migration. Authored, NOT applied.

No test here executes SQL against a database; these contracts are asserted on the DDL text,
and the Postgres path they govern is REVIEWED BUT UNEXECUTED until the owner applies it.
"""

from __future__ import annotations

from pathlib import Path

SQL = (
    Path(__file__).resolve().parents[2]
    / "migrations/0009_section_5a_evaluation_seal.sql"
).read_text(encoding="utf-8")

# Column alignment is cosmetic; collapse whitespace so these assert structure, not layout.
FLAT = " ".join(SQL.split())


def test_the_table_can_hold_at_most_one_seal() -> None:
    assert "seal_id TEXT PRIMARY KEY CHECK (seal_id = 'SINGLETON')" in FLAT


def test_a_claimed_seal_cannot_carry_evidence() -> None:
    """Claim-before-read cannot be bypassed by handing evidence to the claim."""

    assert "CONSTRAINT section_5a_claimed_has_no_snapshot CHECK" in FLAT
    assert (
        "state <> 'CLAIMED' OR (snapshot_payload IS NULL AND evidence_snapshot_id IS NULL "
        "AND result_inputs_digest IS NULL)"
    ) in FLAT


def test_a_captured_state_requires_the_raw_capture_it_was_exposed_from() -> None:
    assert "CONSTRAINT section_5a_captured_is_complete CHECK" in FLAT
    assert (
        "raw_evidence IS NOT NULL AND snapshot_payload IS NOT NULL "
        "AND evidence_snapshot_id IS NOT NULL AND result_inputs_digest IS NOT NULL"
    ) in FLAT


def test_every_lifecycle_state_is_declared_and_nothing_else() -> None:
    assert (
        "CHECK (state IN ('CLAIMED', 'SEALED_RAW_CAPTURED', 'COMPLETE', "
        "'SEALED_NO_RESULT', 'CAPTURE_FAILED'))"
    ) in FLAT


def test_claim_fields_are_immutable() -> None:
    assert "RAISE EXCEPTION 'section 5A seal claim fields are immutable'" in FLAT
    for column in ("sealed_at_utc", "evaluator_pin_digest", "contract_instants"):
        assert f"NEW.{column} IS DISTINCT FROM OLD.{column}" in FLAT


def test_captured_evidence_is_write_once() -> None:
    assert "RAISE EXCEPTION 'section 5A captured evidence is write-once'" in FLAT
    for column in (
        "raw_evidence",
        "snapshot_payload",
        "evidence_snapshot_id",
        "result_inputs_digest",
    ):
        assert f"OLD.{column} IS NOT NULL" in FLAT


def test_only_legal_transitions_are_accepted() -> None:
    assert "RAISE EXCEPTION 'illegal section 5A seal transition % -> %'" in FLAT
    assert "(OLD.state = 'COMPLETE' AND NEW.state = 'COMPLETE')" in FLAT
    assert "(OLD.state = 'CAPTURE_FAILED' AND NEW.state = 'CAPTURE_FAILED')" in FLAT


def test_the_seal_cannot_be_deleted() -> None:
    assert "BEFORE UPDATE OR DELETE ON section_5a_evaluation_seal" in FLAT
    assert "RAISE EXCEPTION 'section 5A seal cannot be deleted" in FLAT


def test_it_is_idempotent_and_replaces_the_superseded_trigger() -> None:
    assert "CREATE TABLE IF NOT EXISTS" in FLAT
    assert "DROP TRIGGER IF EXISTS section_5a_seal_immutable" in FLAT
    assert "DROP TRIGGER IF EXISTS section_5a_seal_guard" in FLAT


def test_it_records_that_it_is_not_applied_and_how_to_apply_it_safely() -> None:
    assert "AUTHORED, NOT APPLIED" in SQL
    assert "--only 0009_section_5a_evaluation_seal.sql" in SQL
