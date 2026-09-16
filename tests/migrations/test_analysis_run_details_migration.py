from __future__ import annotations

import hashlib
import re
from pathlib import Path

from scripts import apply_migration_0008 as apply_0008

ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / "migrations" / "0008_analysis_run_details.sql"
SQL = PATH.read_text()


def _executable(sql: str) -> str:
    """The statements alone, upper-cased on one line: comments cannot satisfy or trip a check."""

    code = "\n".join(line.split("--", 1)[0] for line in sql.splitlines())
    return " ".join(code.upper().split())


EXECUTABLE = _executable(SQL)


def _statements() -> list[str]:
    return [statement.strip() for statement in EXECUTABLE.split(";") if statement.strip()]


def test_analysis_run_details_migration_is_additive_without_foreign_key() -> None:
    assert "CREATE TABLE IF NOT EXISTS PUBLIC.ANALYSIS_RUN_DETAILS" in EXECUTABLE
    assert "CREATE INDEX IF NOT EXISTS" in EXECUTABLE
    assert "DETAIL_PAYLOAD JSONB NOT NULL" in EXECUTABLE
    assert "FOREIGN KEY" not in EXECUTABLE
    assert "REFERENCES" not in EXECUTABLE
    assert "DROP " not in EXECUTABLE
    assert "DELETE " not in EXECUTABLE
    assert "TRUNCATE" not in EXECUTABLE
    assert "ALTER TABLE PUBLIC.PREDICTIONS" not in EXECUTABLE


def test_every_object_is_schema_qualified() -> None:
    assert "ON PUBLIC.ANALYSIS_RUN_DETAILS (CREATED_AT DESC)" in EXECUTABLE
    unqualified = re.findall(r"(?<!PUBLIC\.)\bANALYSIS_RUN_DETAILS\b", EXECUTABLE)
    assert unqualified == [], "every reference names public explicitly"


def test_no_api_role_reaches_the_table_except_service_role_for_the_rest_repository() -> None:
    """The 0005/0006/0009 convention, with exactly the privileges the REST upsert and reads use."""

    assert _statements() == [
        "CREATE TABLE IF NOT EXISTS PUBLIC.ANALYSIS_RUN_DETAILS ( RUN_ID TEXT PRIMARY KEY, "
        "ANALYSIS_HASH TEXT, DETAIL_PAYLOAD JSONB NOT NULL, "
        "CREATED_AT TIMESTAMPTZ NOT NULL DEFAULT NOW() )",
        "CREATE INDEX IF NOT EXISTS IDX_ANALYSIS_RUN_DETAILS_CREATED_AT "
        "ON PUBLIC.ANALYSIS_RUN_DETAILS (CREATED_AT DESC)",
        "ALTER TABLE PUBLIC.ANALYSIS_RUN_DETAILS ENABLE ROW LEVEL SECURITY",
        "REVOKE ALL ON TABLE PUBLIC.ANALYSIS_RUN_DETAILS FROM PUBLIC, ANON, AUTHENTICATED, "
        "SERVICE_ROLE",
        "GRANT SELECT, INSERT, UPDATE ON TABLE PUBLIC.ANALYSIS_RUN_DETAILS TO SERVICE_ROLE",
    ]
    assert "FORCE ROW LEVEL SECURITY" not in EXECUTABLE, "the owner-role Postgres path must work"


def test_the_rest_repository_needs_exactly_what_is_granted() -> None:
    """SupabaseRestRepository upserts on run_id (INSERT + UPDATE) and reads (SELECT) this table."""

    source = (ROOT / "src/crypto_probability_engine/persistence/repository.py").read_text()
    rest = source.split("class SupabaseRestRepository", 1)[1]
    assert '"analysis_run_details",\n                json=dict(row),' in rest
    assert 'params={"on_conflict": "run_id"},' in rest
    assert 'prefer="resolution=merge-duplicates,return=minimal",' in rest
    assert rest.count('"GET",\n                "analysis_run_details",') == 2


def test_the_apply_route_pins_exactly_these_bytes() -> None:
    assert hashlib.sha256(PATH.read_bytes()).hexdigest() == apply_0008.MIGRATION_SHA256
    assert apply_0008.MIGRATION == "migrations/0008_analysis_run_details.sql"


def test_the_apply_route_expects_exactly_the_migration_s_columns() -> None:
    body = SQL.split("CREATE TABLE IF NOT EXISTS public.analysis_run_details (", 1)[1]
    body = body.split(");", 1)[0]
    types = {"TEXT": "text", "TIMESTAMPTZ": "timestamp with time zone", "JSONB": "jsonb"}
    columns = []
    for line in body.splitlines():
        match = re.match(r"^\s*([a-z_]+)\s+(TEXT|TIMESTAMPTZ|JSONB)\b(.*?),?$", line)
        if match:
            name, kind, rest = match.groups()
            required = "NOT NULL" in rest or "PRIMARY KEY" in rest
            default = "now()" if "DEFAULT NOW()" in rest else None
            columns.append((name, types[kind], "NO" if required else "YES", default))
    assert columns == list(apply_0008.EXPECTED_COLUMNS)
