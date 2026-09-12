"""The one-look seal migration. Authored, NOT applied."""

from __future__ import annotations

from pathlib import Path

SQL = (
    Path(__file__).resolve().parents[2]
    / "migrations/0009_section_5a_evaluation_seal.sql"
).read_text(encoding="utf-8")

# Column alignment in the DDL is cosmetic; collapse runs of spaces so these contracts
# assert on structure rather than on formatting.
FLAT = " ".join(SQL.split())


def test_the_table_can_hold_at_most_one_seal() -> None:
    assert "seal_id TEXT PRIMARY KEY CHECK (seal_id = 'SINGLETON')" in FLAT


def test_the_snapshot_lives_in_the_same_row_as_the_claim() -> None:
    assert "snapshot_payload JSONB NOT NULL" in FLAT


def test_the_captured_evidence_is_immutable_once_claimed() -> None:
    assert "section_5a_seal_is_immutable" in SQL
    assert "RAISE EXCEPTION 'section 5A seal evidence is immutable once claimed'" in SQL
    assert "BEFORE UPDATE ON section_5a_evaluation_seal" in SQL


def test_only_the_three_pre_registered_states_are_accepted() -> None:
    assert "CHECK (state IN ('SEALED_RAW_CAPTURED', 'COMPLETE', 'SEALED_NO_RESULT'))" in FLAT


def test_it_is_idempotent_so_a_retry_is_safe() -> None:
    assert "CREATE TABLE IF NOT EXISTS" in SQL
    assert "DROP TRIGGER IF EXISTS" in SQL


def test_it_records_that_it_is_not_applied() -> None:
    assert "AUTHORED, NOT APPLIED" in SQL
