from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_analysis_run_details_migration_is_additive_without_foreign_key() -> None:
    sql = (ROOT / "migrations" / "0008_analysis_run_details.sql").read_text()
    normalized = " ".join(sql.upper().split())

    assert "CREATE TABLE IF NOT EXISTS ANALYSIS_RUN_DETAILS" in normalized
    assert "CREATE INDEX IF NOT EXISTS" in normalized
    assert "DETAIL_PAYLOAD JSONB NOT NULL" in normalized
    assert "FOREIGN KEY" not in normalized
    assert "REFERENCES" not in normalized
    assert "DROP " not in normalized
    assert "DELETE " not in normalized
