"""ucpe.a4_card04_companion.v1 (ops/a4_card04_companion): the sealed read-only companion of
ucpe.a4_ledger_audit.v1 for UOR Card 04.

What these tests prove without a database (the scratch-PostgreSQL 17.6 rehearsal proves the rest):
- the sealed SQL passes a structural guard of two layers:
  - the first checks every property on ONE token stream, in which a literal is a value, never SQL:
    printable ASCII only; standard literals only (no backslash, prefixed literal, dollar quote,
    quoted identifier, block comment or two adjacent literals); only the modelled operators,
    keywords, types and functions, and every other identifier a declared name; one SELECT, with no
    write, locking, TABLE or SET clause, comma-join or derived table; no relation but the ledger,
    public.predictions and five catalogs, each through an alias, and exactly the declared reads
    (each relation's uses, every data column reference): from the ledger ten columns, from
    predictions only run_id, from the catalogs only the listed columns; exactly the declared
    literals, function calls and names, none of them a keyword PostgreSQL evaluates as a value;
    the binding, the bound row and its facts, the three counts, the checks and the final SELECT
    exactly as sealed, so the cross-credential count (owner ruling A4-CRID-UNIQUENESS) reads only
    client_request_id, never projects, groups or aggregates a credential_id, and stays separate from
    the credential count; no star but count(*) and the decision's k.*, and no whole-row use of any
    table, alias or CTE; the decision branches in the declared order, judging no count;
  - the second admits no SQL but the sealed SQL's own token stream (comments and whitespace aside),
    whatever the first might miss;
- adversarial mutants that widen a read, read a probability, the body, a whole row (directly, with a
  star, through a CTE or a derived table), the registry, another table or more than the declared
  reads, hide a read in an escape string or a non-ASCII name, stand a literal in for pinned SQL,
  declare a name PostgreSQL evaluates (current_user), use an unmodelled operator, type, keyword or
  identifier, drop or reorder a check, bind on client_request_id alone, judge a count, move the
  count window, swap or add an output, drop the inheritance check, project, group or aggregate
  another credential's id, scope the cross-credential count to one credential or window it, lock or
  write, all fail the first layer alone;
- the expected columns are migration 0013's and 0003's declarations, no later migration changes
  them, and the route still writes each fact where the companion reads it;
- the runner starts only as python -I -B, checks that its folder holds exactly its five files, the
  package against its seal and the SQL against its pin, runs the SQL only in a READ ONLY
  transaction with row security off that it always rolls back, refuses bad inputs before
  contacting anything, never prints a URL, a credential value or an exception message, prints only
  values in the ledger's own formats, and prints nothing of an answer it cannot reproduce; every
  runner mutant breaks one of those behaviours;
- the manifest seals every package file; UOR_HANDOFF.md section 15 carries exactly the companion
  fields, the seal's digest and the keys the runner really prints; the accepted A4 component's seal
  is unchanged and section 14's corrected contract names every key of the A4 audited line.
"""

from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "ops" / "a4_card04_companion"
SQL_FILE = PACKAGE / "a4_card04_companion.sql"
RUNNER_FILE = PACKAGE / "a4_card04_companion.py"
MANIFEST = PACKAGE / "MANIFEST.json"
MIGRATIONS = ROOT / "migrations"
HANDOFF = ROOT / "docs" / "automation" / "UOR_HANDOFF.md"
SEALED_FILES = ("a4_card04_companion.sql", "a4_card04_companion.py", "CARD.md", "build_manifest.py")

# The accepted A4 component this companion accompanies: never changed here.
A4_MANIFEST = ROOT / "ops" / "a4_ledger_audit" / "MANIFEST.json"
A4_ARTIFACT_SHA256 = "2007fa28a52048e13c1cadbc8e7d5c67fd317dcb9d3bb9e57d1a581a728b6577"
A4_SOURCE_COMMIT = "e468f1f118870f904d90505a3cdbb74446d5a495"


def _module(name: str, path: Path, source: str | None = None) -> Any:
    """Load a module from its file's source, or from mutated source standing in for that file. No
    bytecode is ever written: the package folder must hold exactly its five files."""

    spec = importlib.util.spec_from_file_location(name, path)
    assert spec
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    text = path.read_text(encoding="utf-8") if source is None else source
    exec(compile(text, str(path), "exec"), module.__dict__)  # noqa: S102 - test mutants
    return module


runner = _module("a4c_runner_under_test", RUNNER_FILE)
SEALED = SQL_FILE.read_text(encoding="utf-8")

CRED = "uor-radar-2026-10"
CRID = "3e8ca8f0-5016-4e45-9ea1-0aedbe815260"
RUN = "run_d33406cea53648829428b829198577d3"
DEADLINE = "30000"
AHASH = "sha256:" + "ab" * 32
ACTIVATION = "2026-10-05T00:00:00Z"
URL = "postgresql://a4c_user:NOT-A-REAL-PASSWORD@db.invalid:5432/postgres"

# --------------------------------------------------------------------------- the structural guard
LEDGER = "public.automation_radar_ledger"
PREDICTIONS = "public.predictions"
DATA_COLUMNS = {
    LEDGER: {
        "credential_id",
        "client_request_id",
        "evidence_origin",
        "state",
        "outcome_code",
        "http_status",
        "run_id",
        "analysis_hash",
        "deadline_ms",
        "received_at_utc",
    },
    PREDICTIONS: {"run_id"},
}
CATALOGS = {
    "pg_catalog.pg_class",
    "pg_catalog.pg_namespace",
    "pg_catalog.pg_attribute",
    "pg_catalog.pg_constraint",
    "pg_catalog.pg_inherits",
}
RELATIONS = {LEDGER, PREDICTIONS, *CATALOGS}
ALLOWED_QUALIFIED = {*RELATIONS, "pg_catalog.format_type"}
SCHEMAS = {
    "public",
    "pg_catalog",
    "information_schema",
    "pg_toast",
    "auth",
    "storage",
    "extensions",
    "realtime",
    "vault",
    "graphql",
    "graphql_public",
    "cron",
    "net",
    "pgsodium",
    "supabase_functions",
}
CTES = {
    "binding",
    "relations",
    "expected_columns",
    "live_columns",
    "ledger_key",
    "schema_check",
    "target",
    "target_facts",
    "run_predictions",
    "credential_rows",
    "request_rows",
    "checks",
    "decision",
}
FUNCTIONS = {"count", "min", "array_agg", "pg_catalog.format_type"}
PAREN_KEYWORDS = {
    "AS",
    "AND",
    "OR",
    "NOT",
    "ON",
    "WHERE",
    "IN",
    "THEN",
    "WHEN",
    "ELSE",
    "SELECT",
    "FROM",
    "JOIN",
    "EXISTS",
    "VALUES",
    "ANY",
    "CAST",
}
FORBIDDEN_KEYWORDS = {
    "INSERT",
    "UPDATE",
    "DELETE",
    "MERGE",
    "TRUNCATE",
    "COPY",
    "CALL",
    "DO",
    "SET",
    "RESET",
    "LOCK",
    "GRANT",
    "REVOKE",
    "CREATE",
    "ALTER",
    "DROP",
    "COMMENT",
    "VACUUM",
    "ANALYZE",
    "REFRESH",
    "NOTIFY",
    "LISTEN",
    "UNLISTEN",
    "PREPARE",
    "EXECUTE",
    "DEALLOCATE",
    "DISCARD",
    "INTO",
    "FOR",
    "RETURNING",
    "BEGIN",
    "COMMIT",
    "ROLLBACK",
    "SAVEPOINT",
    "CHECKPOINT",
    "CLUSTER",
    "REINDEX",
    "SECURITY",
    "IMPORT",
    "LOAD",
    "RECURSIVE",
    "LATERAL",
    "TABLESAMPLE",
    "TABLE",
    "ONLY",
    "OVER",
}
DENIED_WORDS = {
    "automation_credential",
    "secret_sha256",
    "prediction_outcomes",
    "analysis_runs",
    "snapshot",
    "pg_read_file",
    "pg_sleep",
    "dblink",
    "query_to_xml",
    "lo_import",
    "set_config",
    "current_setting",
    "nextval",
    "setval",
    "row_to_json",
    "to_json",
    "to_jsonb",
}
DENIED_PREFIXES = ("pg_advisory", "section_5a", "pg_stat")
PLACEHOLDERS = [
    "%(credential_id)s",
    "%(client_request_id)s",
    "%(expected_run_id)s",
    "%(expected_deadline_ms)s",
    "%(expected_analysis_hash)s",
    "%(qualification_activation_utc)s",
]
# The binding, the bound row and its facts, the three counts, the checks and the output, each
# exactly as sealed (whitespace aside), matched token by token: every mapping from an input or a
# read to an output is pinned, and a literal can never stand in for any of it.
F_BINDING = (
    "WITH binding AS ( SELECT CAST(%(credential_id)s AS text) AS credential_id, "
    "CAST(%(client_request_id)s AS uuid) AS client_request_id, CAST(%(expected_run_id)s "
    "AS text) AS expected_run_id, CAST(%(expected_deadline_ms)s AS integer) AS "
    "expected_deadline_ms, CAST(%(expected_analysis_hash)s AS text) AS "
    "expected_analysis_hash, CAST(%(qualification_activation_utc)s AS timestamptz) AS "
    "activation_utc )"
)
F_TARGET = (
    "target AS ( SELECT l.evidence_origin, l.state, l.outcome_code, l.http_status, "
    "l.run_id, l.analysis_hash, l.deadline_ms, l.received_at_utc FROM "
    "public.automation_radar_ledger AS l JOIN binding AS b ON l.credential_id = "
    "b.credential_id AND l.client_request_id = b.client_request_id )"
)
F_TARGET_FACTS = (
    "target_facts AS ( SELECT count(*) AS matched_rows, CASE WHEN count(*) = 1 THEN "
    "min(t.evidence_origin) END AS evidence_origin, CASE WHEN count(*) = 1 THEN "
    "min(t.state) END AS state, CASE WHEN count(*) = 1 THEN min(t.outcome_code) END AS "
    "outcome_code, CASE WHEN count(*) = 1 THEN min(t.http_status) END AS http_status, "
    "CASE WHEN count(*) = 1 THEN min(t.run_id) END AS run_id, CASE WHEN count(*) = 1 THEN "
    "min(t.analysis_hash) END AS analysis_hash, CASE WHEN count(*) = 1 THEN "
    "min(t.deadline_ms) END AS deadline_ms, CASE WHEN count(*) = 1 THEN "
    "min(t.received_at_utc) END AS received_at_utc FROM target AS t )"
)
F_RUN_PREDICTIONS = (
    "run_predictions AS ( SELECT count(*) AS predictions_rows_for_run_id FROM "
    "public.predictions AS p JOIN binding AS b ON p.run_id = b.expected_run_id )"
)
F_CREDENTIAL_ROWS = (
    "credential_rows AS ( SELECT count(*) AS credential_ledger_rows_since_activation FROM "
    "public.automation_radar_ledger AS w JOIN binding AS b ON w.credential_id = "
    "b.credential_id AND w.received_at_utc >= b.activation_utc )"
)
F_REQUEST_ROWS = (
    "request_rows AS ( SELECT count(*) AS "
    "ledger_rows_for_client_request_id_across_all_credentials FROM "
    "public.automation_radar_ledger AS g JOIN binding AS b ON g.client_request_id = "
    "b.client_request_id )"
)
F_CHECKS = (
    "checks AS ( SELECT b.credential_id AS bound_credential_id, b.client_request_id::text "
    "AS bound_client_request_id, b.expected_run_id AS bound_run_id, (s.schema_ok IS TRUE) "
    "AS schema_ok, f.matched_rows, f.evidence_origin, f.state, f.outcome_code, "
    "f.http_status, (f.run_id IS NOT DISTINCT FROM b.expected_run_id) AS run_id_matches, "
    "f.deadline_ms, (f.deadline_ms IS NOT DISTINCT FROM b.expected_deadline_ms) AS "
    "deadline_ms_matches, f.analysis_hash, (f.analysis_hash IS NOT DISTINCT FROM "
    "b.expected_analysis_hash) AS analysis_hash_matches, (f.received_at_utc >= "
    "b.activation_utc) AS activation_not_after_request, rp.predictions_rows_for_run_id, "
    "cr.credential_ledger_rows_since_activation, "
    "rq.ledger_rows_for_client_request_id_across_all_credentials FROM binding AS b CROSS "
    "JOIN schema_check AS s CROSS JOIN target_facts AS f CROSS JOIN run_predictions AS rp "
    "CROSS JOIN credential_rows AS cr CROSS JOIN request_rows AS rq )"
)
F_FINAL = (
    "SELECT 'ucpe.a4_card04_companion.v1' AS artifact, CASE WHEN d.reason = 'OK' THEN "
    "'PASS' ELSE 'FAIL' END AS verdict, d.reason, d.bound_credential_id, "
    "d.bound_client_request_id, d.bound_run_id, d.schema_ok, d.deadline_ms, "
    "d.deadline_ms_matches, d.analysis_hash, d.analysis_hash_matches, "
    "d.predictions_rows_for_run_id, d.credential_ledger_rows_since_activation, "
    "d.ledger_rows_for_client_request_id_across_all_credentials FROM decision AS d"
)
REQUIRED_FRAGMENTS = [
    F_BINDING,
    "WHERE n.nspname = 'public'",
    "AND c.relkind = 'r'",
    "AND NOT EXISTS (SELECT 1 FROM pg_catalog.pg_inherits AS i JOIN relations AS h "
    "ON h.oid = i.inhparent)",
    F_TARGET,
    F_TARGET_FACTS,
    F_RUN_PREDICTIONS,
    F_CREDENTIAL_ROWS,
    F_REQUEST_ROWS,
    F_CHECKS,
    "decision AS ( SELECT k.*, CASE",
    "END AS reason FROM checks AS k )",
    F_FINAL,
]
# The decision, branch by branch, in the order it must run.
DECISION_ORDER = [
    "WHEN k.schema_ok IS NOT TRUE THEN 'SCHEMA_DRIFT'",
    "WHEN k.matched_rows = 0 THEN 'NO_ROW'",
    "WHEN k.matched_rows <> 1 THEN 'AMBIGUOUS'",
    "WHEN k.evidence_origin IS DISTINCT FROM 'AUTOMATED_RADAR' THEN 'WRONG_ORIGIN'",
    "WHEN k.state IS DISTINCT FROM 'COMPLETED' THEN 'NOT_COMPLETED'",
    "WHEN k.outcome_code IS DISTINCT FROM 'SUCCEEDED' OR k.http_status IS DISTINCT FROM 200 THEN "
    "'NOT_SUCCEEDED'",
    "WHEN k.run_id_matches IS NOT TRUE THEN 'RUN_MISMATCH'",
    "WHEN k.deadline_ms_matches IS NOT TRUE THEN 'DEADLINE_MISMATCH'",
    "WHEN k.analysis_hash_matches IS NOT TRUE THEN 'ANALYSIS_HASH_MISMATCH'",
    "WHEN k.activation_not_after_request IS NOT TRUE THEN 'ACTIVATION_AFTER_REQUEST'",
    "ELSE 'OK' END AS reason",
]
FROM_LIST_ENDS = {
    "WHERE",
    "GROUP",
    "HAVING",
    "ORDER",
    "LIMIT",
    "OFFSET",
    "UNION",
    "EXCEPT",
    "INTERSECT",
    "WINDOW",
}
# THE GUARD'S MODEL OF SQL is closed: what it does not model, it refuses. Printable ASCII only; no
# backslash, prefixed literal (E'', U&'', B'', X'', N''), dollar quote, quoted identifier or block
# comment; only these operators, punctuation, keywords, types and functions; every other identifier
# is a declared CTE, alias or output name, or an allowed column.
LITERAL = "'L'"  # a masked literal, one token
TOKEN = re.compile(
    r"%\(\w+\)s|'L'|[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*|\d+|::"
    r"|[-+*/<>=~!@#%^&|`?]+|\S"
)
OPERATORS = {"=", "<>", ">", ">=", "*", "::"}
PUNCTUATION = {"(", ")", ",", ".", "[", "]"}
KEYWORDS = {
    "WITH",
    "AS",
    "SELECT",
    "CAST",
    "FROM",
    "JOIN",
    "CROSS",
    "ON",
    "WHERE",
    "AND",
    "OR",
    "NOT",
    "IN",
    "IS",
    "DISTINCT",
    "EXISTS",
    "EXCEPT",
    "VALUES",
    "ARRAY",
    "ANY",
    "ORDER",
    "BY",
    "CASE",
    "WHEN",
    "THEN",
    "ELSE",
    "END",
    "TRUE",
    "FALSE",
}
CAST_TYPES = {"text", "uuid", "integer", "timestamptz"}
# Names PostgreSQL evaluates as values, without parentheses: a SQL that declared one as a column
# could use it bare, and the guard would read a column where PostgreSQL reads the role or the clock.
VALUE_KEYWORDS = {
    "current_catalog",
    "current_date",
    "current_role",
    "current_schema",
    "current_time",
    "current_timestamp",
    "current_user",
    "default",
    "localtime",
    "localtimestamp",
    "null",
    "session_user",
    "system_user",
    "user",
}
# The declared minimum, exactly: how often each relation is read, and every data column reference.
# predictions.run_id is read once, in the count's join; the ledger three times: the bound row, the
# credential's window, and the client_request_id across all credentials (client_request_id only).
RELATION_USES = {
    LEDGER: 3,
    PREDICTIONS: 1,
    "pg_catalog.pg_class": 1,
    "pg_catalog.pg_namespace": 1,
    "pg_catalog.pg_attribute": 2,
    "pg_catalog.pg_constraint": 1,
    "pg_catalog.pg_inherits": 1,
}
DATA_READS = {
    "l.credential_id": 1,
    "l.client_request_id": 1,
    "l.evidence_origin": 1,
    "l.state": 1,
    "l.outcome_code": 1,
    "l.http_status": 1,
    "l.run_id": 1,
    "l.analysis_hash": 1,
    "l.deadline_ms": 1,
    "l.received_at_utc": 1,
    "w.credential_id": 1,
    "w.received_at_utc": 1,
    "p.run_id": 1,
    "g.client_request_id": 1,
}
# Exactly the names the SQL declares (CTE columns and output names), the functions it calls and how
# often, and its literals: nothing can be added, renamed or smuggled in a string.
DECLARED_NAMES = {
    "activation_not_after_request",
    "activation_utc",
    "analysis_hash",
    "analysis_hash_matches",
    "artifact",
    "bound_client_request_id",
    "bound_credential_id",
    "bound_run_id",
    "client_request_id",
    "column_name",
    "column_not_null",
    "column_type",
    "credential_id",
    "credential_ledger_rows_since_activation",
    "deadline_ms",
    "deadline_ms_matches",
    "evidence_origin",
    "expected_analysis_hash",
    "expected_deadline_ms",
    "expected_run_id",
    "http_status",
    "ledger_rows_for_client_request_id_across_all_credentials",
    "matched_rows",
    "outcome_code",
    "predictions_rows_for_run_id",
    "reason",
    "received_at_utc",
    "relname",
    "run_id",
    "run_id_matches",
    "schema_ok",
    "state",
    "verdict",
}
FUNCTION_USES = {"count": 14, "min": 8, "array_agg": 1, "pg_catalog.format_type": 1}
LITERALS = {
    "ACTIVATION_AFTER_REQUEST": 1,
    "AMBIGUOUS": 1,
    "ANALYSIS_HASH_MISMATCH": 1,
    "AUTOMATED_RADAR": 1,
    "COMPLETED": 1,
    "DEADLINE_MISMATCH": 1,
    "FAIL": 1,
    "NOT_COMPLETED": 1,
    "NOT_SUCCEEDED": 1,
    "NO_ROW": 1,
    "OK": 2,
    "PASS": 1,
    "RUN_MISMATCH": 1,
    "SCHEMA_DRIFT": 1,
    "SUCCEEDED": 1,
    "WRONG_ORIGIN": 1,
    "analysis_hash": 1,
    "automation_radar_ledger": 12,
    "client_request_id": 2,
    "credential_id": 2,
    "deadline_ms": 1,
    "evidence_origin": 1,
    "http_status": 1,
    "integer": 2,
    "outcome_code": 1,
    "p": 1,
    "predictions": 2,
    "public": 1,
    "r": 1,
    "received_at_utc": 1,
    "run_id": 2,
    "state": 1,
    "text": 7,
    "timestamp with time zone": 1,
    "ucpe.a4_card04_companion.v1": 1,
    "uuid": 1,
}
CATALOG_COLUMNS = {
    "pg_catalog.pg_class": {"oid", "relname", "relnamespace", "relkind"},
    "pg_catalog.pg_namespace": {"oid", "nspname"},
    "pg_catalog.pg_attribute": {
        "attname",
        "atttypid",
        "atttypmod",
        "attnotnull",
        "attrelid",
        "attnum",
        "attisdropped",
    },
    "pg_catalog.pg_constraint": {"conrelid", "conkey", "contype"},
    "pg_catalog.pg_inherits": {"inhparent"},
}
TYPES = {
    "TEXT": "text",
    "UUID": "uuid",
    "INTEGER": "integer",
    "JSONB": "jsonb",
    "TIMESTAMPTZ": "timestamp with time zone",
    "NUMERIC": "numeric",
    "BOOLEAN": "boolean",
}
COLUMN = re.compile(r"^\s+([a-z_]+)\s+(TEXT|UUID|INTEGER|JSONB|TIMESTAMPTZ|NUMERIC|BOOLEAN)\b(.*)$")


def _strip_comments(sql: str) -> tuple[str, str, list[str], list[str]]:
    """(code without comments, the same with literals masked, the literals, the problems)."""

    kept: list[str] = []
    masked: list[str] = []
    literals: list[str] = []
    problems: list[str] = []
    if any(char != "\n" and not " " <= char <= "~" for char in sql):
        problems.append("a character outside printable ASCII")
    if "\\" in sql:
        problems.append("a backslash")
    i = 0
    while i < len(sql):
        if sql.startswith("--", i):
            end = sql.find("\n", i)
            i = len(sql) if end < 0 else end
            continue
        if sql.startswith("/*", i):
            problems.append("block comment")
            i += 2
            continue
        char = sql[i]
        if char in {'"', "$"}:
            problems.append(f"forbidden quoting {char}")
        if char == "'":
            if i > 0 and (sql[i - 1].isalnum() or sql[i - 1] in "_&"):
                problems.append("a prefixed literal")
            end = i + 1
            while end < len(sql):
                if sql.startswith("''", end):
                    end += 2
                elif sql[end] == "'":
                    break
                else:
                    end += 1
            if end >= len(sql):
                problems.append("unterminated literal")
                break
            literal = sql[i : end + 1]
            literals.append(literal[1:-1].replace("''", "'"))
            kept.append(literal)
            masked.append(LITERAL)
            i = end + 1
            continue
        kept.append(char)
        masked.append(char)
        i += 1
    return "".join(kept), "".join(masked), literals, problems


def table_columns(table: str) -> dict[str, tuple[str, bool]]:
    """Every column any migration gives public.<table>: (type, NOT NULL), from its CREATE TABLE and
    every ADD COLUMN."""

    columns: dict[str, tuple[str, bool]] = {}
    for path in sorted(MIGRATIONS.glob("*.sql")):
        text = path.read_text(encoding="utf-8")
        create = re.search(
            rf"CREATE TABLE IF NOT EXISTS (?:public\.)?{table} \((.*?)\n\);", text, re.S
        )
        if create:
            for line in create[1].splitlines():
                match = COLUMN.match(line)
                if match:
                    columns[match[1]] = (TYPES[match[2]], "NOT NULL" in match[3])
        for statement in re.findall(
            rf"ALTER TABLE (?:IF EXISTS )?(?:ONLY )?(?:public\.)?{table}\b(.*?);", text, re.S | re.I
        ):
            for name in re.findall(r"ADD COLUMN (?:IF NOT EXISTS )?([a-z_]+)", statement, re.I):
                columns.setdefault(name.lower(), ("added", False))
    return columns


def migration_relations() -> set[str]:
    names: set[str] = set()
    pattern = re.compile(
        r"CREATE\s+(?:OR\s+REPLACE\s+)?(?:TABLE|VIEW|MATERIALIZED\s+VIEW|FUNCTION)\s+"
        r"(?:IF\s+NOT\s+EXISTS\s+)?(?:public\.)?([a-z_][a-z0-9_]*)",
        re.IGNORECASE,
    )
    for path in sorted(MIGRATIONS.glob("*.sql")):
        names.update(match.lower() for match in pattern.findall(path.read_text(encoding="utf-8")))
    return names - {"automation_radar_ledger", "predictions"}


def denied_names() -> set[str]:
    """Every other relation or function a migration creates, every column of the two tables the
    companion must not read, and the fixed denied words."""

    unread = (set(table_columns("automation_radar_ledger")) - DATA_COLUMNS[LEDGER]) | (
        set(table_columns("predictions")) - DATA_COLUMNS[PREDICTIONS]
    )
    return migration_relations() | unread | DENIED_WORDS


def _comma_in_from_list(tokens: list[str], upper: list[str], start: int) -> bool:
    """A comma at the FROM list's own depth, from FROM to where that list ends."""

    depth = 0
    for index in range(start + 1, len(tokens)):
        if tokens[index] == "(":
            depth += 1
        elif tokens[index] == ")":
            depth -= 1
            if depth < 0:  # the enclosing parenthesis closes: the FROM list is over
                return False
        elif depth == 0 and upper[index] in FROM_LIST_ENDS:
            return False
        elif depth == 0 and tokens[index] == ",":
            return True
    return False


def _is_distinct_from(upper: list[str], index: int) -> bool:
    """FROM at ``index`` ends IS DISTINCT FROM or IS NOT DISTINCT FROM: a comparison."""

    return upper[index - 1 : index] == ["DISTINCT"] and (
        upper[index - 2 : index - 1] == ["IS"] or upper[index - 3 : index - 1] == ["IS", "NOT"]
    )


def _typed(sql: str) -> tuple[list[tuple[str, str]], list[str]]:
    """The one token stream every check reads, and the problems found reading it. A literal is one
    token, ("L", its value), and never SQL; every other token is ("T", its text). Two adjacent
    literals are refused: PostgreSQL joins them into one when a newline separates them."""

    _, masked, literals, problems = _strip_comments(sql)
    values = iter(literals)
    typed = [
        ("L", next(values, "")) if token == LITERAL else ("T", token)
        for token in TOKEN.findall(masked)
    ]
    if sum(kind == "L" for kind, _ in typed) != len(literals):
        problems.append("the literals and the token stream disagree")
    if any(left[0] == right[0] == "L" for left, right in zip(typed, typed[1:], strict=False)):
        problems.append("two adjacent literals, which PostgreSQL may join into one")
    return typed, problems


def _sequence(text: str) -> list[tuple[str, str]]:
    return _typed(text)[0]


def _find(
    typed: list[tuple[str, str]], fragment: list[tuple[str, str]], start: int = 0, end: int = -1
) -> int:
    """Where ``fragment``'s tokens occur in ``typed``, adjacent and in order, or -1."""

    stop = len(typed) if end < 0 else end
    for index in range(max(start, 0), stop - len(fragment) + 1):
        if typed[index : index + len(fragment)] == fragment:
            return index
    return -1


def _closing(typed: list[tuple[str, str]], opening: int) -> int:
    """The index of the parenthesis that closes the one at ``opening``, or -1."""

    depth = 0
    for index in range(opening, len(typed)):
        depth += {("T", "("): 1, ("T", ")"): -1}.get(typed[index], 0)
        if depth == 0:
            return index
    return -1


def final_columns(sql: str) -> tuple[str, ...]:
    """The output names of the final SELECT, in order, read from the token stream."""

    typed = _typed(sql)[0]
    depth, start = 0, len(typed)
    for index, token in enumerate(typed):
        depth += {("T", "("): 1, ("T", ")"): -1}.get(token, 0)
        if depth == 0 and token[0] == "T" and token[1].upper() == "SELECT":
            start = index
    items: list[list[tuple[str, str]]] = [[]]
    depth = 0
    for token in typed[start + 1 :]:
        depth += {("T", "("): 1, ("T", ")"): -1}.get(token, 0)
        if depth == 0 and token[0] == "T" and token[1].upper() == "FROM":
            break
        if depth == 0 and token == ("T", ","):
            items.append([])
        else:
            items[-1].append(token)
    last = [item[-1] if item else ("L", "") for item in items]
    return tuple(text.split(".")[-1].lower() if kind == "T" else "" for kind, text in last)


def property_violations(sql: str) -> list[str]:
    """The guard's first layer: every property, checked on the one token stream."""

    violations: list[str] = []
    literals = _strip_comments(sql)[2]
    typed, problems = _typed(sql)
    violations += problems
    tokens = [LITERAL if kind == "L" else token for kind, token in typed]
    upper = [token.upper() for token in tokens]
    lower = [token.lower() for token in tokens]
    for token in tokens:
        modelled = (
            token == LITERAL
            or token.startswith("%(")
            or token.isdigit()
            or re.match(r"[A-Za-z_]", token)
            or token in OPERATORS | PUNCTUATION
        )
        if not modelled:
            violations.append(f"an operator or character the guard does not model: {token}")
    if ";" in tokens:
        violations.append("more than one statement")
    if not upper or upper[0] != "WITH":
        violations.append("not a single WITH ... SELECT")
    for token in upper:
        if token in FORBIDDEN_KEYWORDS:
            violations.append(f"forbidden keyword {token}")
    denied = denied_names()
    for word in [*tokens, *literals]:
        for part in re.split(r"[^a-z0-9_]+", word.lower()):
            if part in denied or part.startswith(DENIED_PREFIXES):
                violations.append(f"denied name {part}")
    ctes: set[str] = set()
    definitions: set[int] = set()
    declared: set[str] = set()  # the names the SQL itself declares: CTE columns and output names
    for index in range(len(tokens) - 2):
        if upper[index + 1] != "AS" or tokens[index + 2] != "(":
            continue
        name_at = index
        if tokens[index] == ")":  # name (column, ...) AS (
            depth = 0
            for back in range(index, -1, -1):
                depth += {")": 1, "(": -1}.get(tokens[back], 0)
                if depth == 0:
                    name_at = back - 1
                    declared.update(
                        name for name in lower[back + 1 : index] if name not in PUNCTUATION
                    )
                    break
        if name_at >= 0 and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", tokens[name_at]):
            ctes.add(lower[name_at])
            definitions.add(name_at)
    if ctes != CTES:
        violations.append(f"unexpected CTE set {sorted(ctes ^ CTES)}")
    aliases: dict[str, str] = {}
    references: set[int] = set()  # the positions that name a relation or declare its alias
    for index, token in enumerate(upper):
        if token not in {"FROM", "JOIN"} or index + 1 >= len(tokens):
            continue
        if token == "FROM" and _is_distinct_from(upper, index):
            continue  # IS [NOT] DISTINCT FROM: a comparison, not a relation
        relation = lower[index + 1]
        if relation == "(":
            violations.append("a derived table: every relation is a named table or CTE")
            continue
        references.add(index + 1)
        if relation not in RELATIONS | CTES:
            violations.append(f"relation {tokens[index + 1]}")
        has_alias = index + 3 < len(tokens) and upper[index + 2] == "AS"
        if has_alias and re.fullmatch(r"[a-z_][a-z0-9_]*", lower[index + 3]):
            alias = lower[index + 3]
            if aliases.setdefault(alias, relation) != relation:
                violations.append(f"alias {alias} names two relations")
            references.add(index + 3)
        elif relation in RELATIONS:
            violations.append(f"relation {tokens[index + 1]} has no alias")
        if token == "FROM" and _comma_in_from_list(tokens, upper, index):
            violations.append("a comma-join: every relation needs its own JOIN")
    # The one star that names no column of a table: decision's k.* over the explicit checks CTE.
    decision_star = {
        index
        for index in range(4, len(tokens) - 2)
        if upper[index - 4 : index] == ["DECISION", "AS", "(", "SELECT"]
        and lower[index] == "k"
        and tokens[index + 1 : index + 3] == [".", "*"]
        and aliases.get("k") == "checks"
    }
    for index, token in enumerate(tokens):
        if token != "*":
            continue
        counted = tokens[index - 2 : index] == ["count", "("] and tokens[index + 1 : index + 2] == [
            ")"
        ]
        if not counted and index - 2 not in decision_star:
            violations.append("a star: every column is named")
    row_sources = set(aliases) | CTES
    data_aliases = {
        alias: relation for alias, relation in aliases.items() if relation in DATA_COLUMNS
    }
    uses = Counter(lower[index] for index in references if lower[index] in RELATIONS)
    if uses != Counter(RELATION_USES):
        violations.append(f"the relations are read other than declared: {dict(uses)}")
    reads = Counter(low for low in lower if "." in low and low.split(".", 1)[0] in data_aliases)
    if reads != Counter(DATA_READS):
        violations.append("the data columns are read other than declared")
    # A type is the token after :: or after the AS of a CAST( ... ), and only a modelled type.
    type_positions = {index + 1 for index, token in enumerate(tokens) if token == "::"}
    for index, token in enumerate(upper):
        if token == "CAST" and tokens[index + 1 : index + 2] == ["("]:
            depth = 0
            for inner in range(index + 1, len(tokens)):
                depth += {"(": 1, ")": -1}.get(tokens[inner], 0)
                if depth == 0:
                    break
                if depth == 1 and upper[inner] == "AS":
                    type_positions.add(inner + 1)
    for index in type_positions:
        if index >= len(tokens) or lower[index] not in CAST_TYPES:
            violations.append("a type the guard does not model")
    for index, token in enumerate(upper):  # an output name: AS <name>, not a type, alias or CTE
        if (
            token == "AS"
            and index + 1 < len(tokens)
            and index + 1 not in type_positions | references
            and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", tokens[index + 1])
            and tokens[index + 2 : index + 3] != ["("]
        ):
            declared.add(lower[index + 1])
    columns_anywhere = declared.union(*DATA_COLUMNS.values()).union(*CATALOG_COLUMNS.values())
    for index, token in enumerate(tokens):
        low = lower[index]
        if re.match(r"[A-Za-z_]", token):
            if "." in token:
                parts = low.split(".")
                if parts[0] in SCHEMAS:
                    if low not in ALLOWED_QUALIFIED:
                        violations.append(f"qualified name {token}")
                elif parts[0] not in aliases:
                    violations.append(f"undeclared alias {token}")
                elif len(parts) != 2:
                    violations.append(f"a nested name {token}")
                elif parts[0] in data_aliases:
                    if parts[1] not in DATA_COLUMNS[data_aliases[parts[0]]]:
                        violations.append(f"unread column {token}")
                elif aliases[parts[0]] in CATALOG_COLUMNS:
                    if parts[1] not in CATALOG_COLUMNS[aliases[parts[0]]]:
                        violations.append(f"an undeclared catalog column {token}")
                elif parts[1] not in columns_anywhere:
                    violations.append(f"a CTE column the SQL never declares {token}")
            else:
                if low.startswith("pg_"):
                    violations.append(f"unqualified catalog name {token}")
                if low in row_sources and index not in references | definitions | decision_star:
                    violations.append(f"whole-row reference {token}")
                if low in {"automation_radar_ledger", "predictions"}:
                    violations.append(f"bare table name {token}")
                known = (
                    upper[index] in KEYWORDS
                    or (low in CAST_TYPES and index in type_positions)
                    or (low in FUNCTIONS and tokens[index + 1 : index + 2] == ["("])
                    or low in row_sources
                    or (low in declared and low not in CAST_TYPES)
                )
                if not known:
                    violations.append(f"an identifier the guard does not model: {token}")
        if index + 1 < len(tokens) and tokens[index + 1] == "(" and re.match(r"[A-Za-z_]", token):
            if low not in FUNCTIONS and token.upper() not in PAREN_KEYWORDS and low not in CTES:
                violations.append(f"function {token}")
        if low.endswith("response_body"):
            violations.append("the stored body")
    if declared != DECLARED_NAMES:
        violations.append(f"the declared names differ: {sorted(declared ^ DECLARED_NAMES)}")
    if declared & VALUE_KEYWORDS:
        violations.append(f"a name PostgreSQL evaluates: {sorted(declared & VALUE_KEYWORDS)}")
    calls = Counter(
        lower[index]
        for index in range(len(tokens) - 1)
        if lower[index] in FUNCTIONS and tokens[index + 1] == "("
    )
    if calls != Counter(FUNCTION_USES):
        violations.append(f"the functions are called other than declared: {dict(calls)}")
    values, expected = Counter(value for kind, value in typed if kind == "L"), Counter(LITERALS)
    if values != expected:
        violations.append(
            f"the literals differ: {sorted((values - expected) + (expected - values))}"
        )
    found = [token for token in tokens if token.startswith("%(")]
    if sorted(found) != sorted(PLACEHOLDERS):
        violations.append(f"placeholders {found}")
    if sql.count("%") != len(PLACEHOLDERS):  # psycopg reads every %, even in a comment
        violations.append("a stray %")
    for fragment in REQUIRED_FRAGMENTS:  # token by token: a literal never stands in for SQL
        if _find(typed, _sequence(fragment)) < 0:
            violations.append(f"missing: {fragment[:60]}")
    opening = _find(typed, _sequence("decision AS ("))
    closing = _closing(typed, opening + 2) if opening >= 0 else -1
    at, ordered = opening, closing >= 0
    for branch in DECISION_ORDER:
        sequence = _sequence(branch)
        found_at = _find(typed, sequence, at, closing) if ordered else -1
        ordered, at = found_at >= 0, found_at + len(sequence)
    if not ordered:
        violations.append("the decision branches are missing or out of order")
    judged = sorted(
        typed[index + 1]
        for index in range(max(opening, 0), closing)
        if typed[index] == ("T", "THEN")
    )
    if judged != sorted(("L", reason) for reason in runner.REASONS if reason != "OK"):
        violations.append("the decision judges something else (a count?)")
    if typed.count(("L", "OK")) != 2:
        violations.append("OK must be reachable only through ELSE")
    if final_columns(sql) != runner.SQL_COLUMNS:
        violations.append("the output columns are not the declared ones")
    return violations


# THE GUARD'S SECOND LAYER: the sealed SQL's exact token stream, comments and whitespace aside. The
# guard admits no other SQL, whatever the first layer's model of SQL might miss.
TOKEN_STREAM_SHA256 = "c75a3264014389039346056c5d7c2b3545916e94b8504da27ba1266aa2e20fc5"


def token_stream_sha256(sql: str) -> str:
    return hashlib.sha256(json.dumps(_typed(sql)[0]).encode("utf-8")).hexdigest()


def guard_violations(sql: str) -> list[str]:
    violations = property_violations(sql)
    if token_stream_sha256(sql) != TOKEN_STREAM_SHA256:
        violations.append("not the sealed SQL's token stream")
    return violations


def test_the_sealed_sql_passes_the_structural_guard() -> None:
    assert guard_violations(SEALED) == []


def test_the_runner_pins_the_sealed_sql() -> None:
    assert runner.SQL_SHA256 == hashlib.sha256(SQL_FILE.read_bytes()).hexdigest()
    assert runner.SQL_PATH == SQL_FILE.resolve()
    assert final_columns(SEALED) == runner.SQL_COLUMNS


T_LEDGER_FROM = "      FROM public.automation_radar_ledger AS l\n"
T_BIND = "        ON l.credential_id = b.credential_id\n       AND l.client_request_id"
T_RUN_COUNT = "    SELECT count(*) AS predictions_rows_for_run_id\n"
T_RUN_ON = "        ON p.run_id = b.expected_run_id\n"
T_CRID_COUNT = "    SELECT count(*) AS ledger_rows_for_client_request_id_across_all_credentials\n"
T_CRID_ON = "        ON g.client_request_id = b.client_request_id\n"
T_WINDOW = (
    "        ON w.credential_id = b.credential_id\n"
    "       AND w.received_at_utc >= b.activation_utc\n"
)
T_TARGET = "    SELECT l.evidence_origin,\n"
# The fourth review's class: a literal carrying the text of a pinned fragment, so that a guard
# reading literal text as SQL finds the fragment while PostgreSQL runs something else.
L_TARGET = (
    "FROM public.automation_radar_ledger AS l JOIN binding AS b"
    " ON l.credential_id = b.credential_id AND l.client_request_id = b.client_request_id)"
)
L_WINDOW = (
    "FROM public.automation_radar_ledger AS w JOIN binding AS b"
    " ON w.credential_id = b.credential_id AND w.received_at_utc >= b.activation_utc)"
)
L_RUN = "FROM public.predictions AS p JOIN binding AS b ON p.run_id = b.expected_run_id)"
L_REQUEST = (
    "FROM public.automation_radar_ledger AS g JOIN binding AS b"
    " ON g.client_request_id = b.client_request_id)"
)
T_CREDENTIAL_COUNT = "    SELECT count(*) AS credential_ledger_rows_since_activation\n"
T_BOUND_RUN = "           b.expected_run_id AS bound_run_id,\n"
T_MATCHED = "    SELECT count(*) AS matched_rows,\n"
MUTANTS: dict[str, tuple[str, str] | list[tuple[str, str]]] = {
    "reads a probability": (T_RUN_COUNT, T_RUN_COUNT[:-1] + ", min(p.p_up_frac) AS up\n"),
    "reads a prediction's outcome": (
        T_RUN_ON,
        T_RUN_ON
        + "      JOIN public.prediction_outcomes AS o ON o.prediction_id = p.prediction_id\n",
    ),
    "counts predictions by another column": (
        T_RUN_ON,
        "        ON p.prediction_id = b.expected_run_id\n",
    ),
    "reads the stored body": (T_TARGET, "    SELECT l.response_body ->> 'run_id' AS body_run,\n"),
    "reads the request fingerprint": (T_TARGET, "    SELECT l.request_fingerprint,\n"),
    "reads the evidence hash": (T_TARGET, "    SELECT l.evidence_hash,\n"),
    "reads the release id": (T_TARGET, "    SELECT l.release_id,\n"),
    "reads the completion time": (T_TARGET, "    SELECT l.completed_at_utc,\n"),
    "reads a whole ledger row": (
        T_TARGET,
        "    SELECT l::text AS whole,\n           l.evidence_origin,\n",
    ),
    "reads whole prediction rows": (
        T_RUN_COUNT,
        "    SELECT count(p.*) AS predictions_rows_for_run_id\n",
    ),
    "reads an unqualified column": (
        "           l.received_at_utc\n",
        "           l.received_at_utc,\n           response_body\n",
    ),
    "reads the credential registry": (
        T_TARGET,
        "    SELECT (SELECT min(x.secret_sha256) FROM public.automation_credential AS x) AS leak,\n"
        "           l.evidence_origin,\n",
    ),
    "names the section 5A seal": (
        "decision AS (\n",
        "other AS (SELECT 1 FROM public.section_5a_probe AS z),\ndecision AS (\n",
    ),
    "reads another table through a new CTE": (
        "decision AS (\n",
        "other AS (SELECT 1 FROM public.analysis_runs AS z),\ndecision AS (\n",
    ),
    "binds on client_request_id alone": (T_BIND, "        ON l.client_request_id"),
    "joins predictions without an alias": (
        "      FROM public.predictions AS p\n      JOIN binding AS b\n" + T_RUN_ON,
        "      FROM public.predictions\n      JOIN binding AS b\n"
        "        ON run_id = b.expected_run_id\n",
    ),
    "drops the origin branch": (
        "               WHEN k.evidence_origin IS DISTINCT FROM 'AUTOMATED_RADAR' THEN "
        "'WRONG_ORIGIN'\n",
        "",
    ),
    "accepts an in-progress row": (
        "               WHEN k.state IS DISTINCT FROM 'COMPLETED' THEN 'NOT_COMPLETED'\n",
        "",
    ),
    "accepts a success that is not 200": (
        "\n                    OR k.http_status IS DISTINCT FROM 200 THEN",
        " THEN",
    ),
    "drops the run binding": (
        "               WHEN k.run_id_matches IS NOT TRUE THEN 'RUN_MISMATCH'\n",
        "",
    ),
    "drops the deadline comparison": (
        "(f.deadline_ms IS NOT DISTINCT FROM b.expected_deadline_ms) AS deadline_ms_matches",
        "true AS deadline_ms_matches",
    ),
    "drops the analysis-hash comparison": (
        "(f.analysis_hash IS NOT DISTINCT FROM b.expected_analysis_hash) AS analysis_hash_matches",
        "true AS analysis_hash_matches",
    ),
    "drops the activation check": (
        "               WHEN k.activation_not_after_request IS NOT TRUE THEN "
        "'ACTIVATION_AFTER_REQUEST'\n",
        "",
    ),
    "makes the window exclusive": (T_WINDOW, T_WINDOW.replace(">=", ">")),
    "counts every credential's rows": (
        T_WINDOW,
        "        ON w.received_at_utc >= b.activation_utc\n",
    ),
    "judges a count": (
        "               ELSE 'OK'\n",
        "               WHEN k.predictions_rows_for_run_id > 0 THEN 'RUN_HAS_PREDICTIONS'\n"
        "               ELSE 'OK'\n",
    ),
    "adds an output column": (
        "       d.ledger_rows_for_client_request_id_across_all_credentials\n",
        "       d.ledger_rows_for_client_request_id_across_all_credentials,\n"
        "       d.activation_not_after_request\n",
    ),
    "accepts a view for a table": ("       AND c.relkind = 'r'\n", ""),
    "drops the schema-drift branch": (
        "               WHEN k.schema_ok IS NOT TRUE THEN 'SCHEMA_DRIFT'\n",
        "",
    ),
    "makes the drift check NULL-unsafe": (
        "WHEN k.schema_ok IS NOT TRUE THEN",
        "WHEN NOT k.schema_ok THEN",
    ),
    "drops the ambiguity branch": (
        "               WHEN k.matched_rows <> 1 THEN 'AMBIGUOUS'\n",
        "",
    ),
    "reaches OK another way": (
        "WHEN k.matched_rows = 0 THEN 'NO_ROW'",
        "WHEN k.matched_rows = 0 THEN 'OK'",
    ),
    "locks the rows": (T_LEDGER_FROM, T_LEDGER_FROM + "      FOR SHARE\n"),
    "deletes in a CTE": (
        "WITH binding AS (\n",
        "WITH gone AS (DELETE FROM public.automation_radar_ledger RETURNING 1),\nbinding AS (\n",
    ),
    "runs a second statement": ("  FROM decision AS d\n", "  FROM decision AS d;\nSELECT 1\n"),
    "calls a side-effect function": (
        T_RUN_COUNT,
        T_RUN_COUNT[:-1] + ", pg_catalog.pg_sleep(0) AS nap\n",
    ),
    "turns row security back on": (
        T_RUN_COUNT,
        T_RUN_COUNT[:-1] + ", pg_catalog.set_config('row_security', 'on', true) AS rs\n",
    ),
    "reads information_schema": (
        "      FROM pg_catalog.pg_class AS c\n",
        "      FROM information_schema.tables AS c\n",
    ),
    "comma-joins a catalog view": (
        "      FROM pg_catalog.pg_class AS c\n",
        "      FROM pg_catalog.pg_class AS c, pg_stat_activity AS z\n",
    ),
    "comma-joins after an ON condition": (T_RUN_ON, T_RUN_ON[:-1] + ", other_relation AS z\n"),
    "reads a catalog with TABLE": (
        T_RUN_COUNT,
        T_RUN_COUNT[:-1] + ", (SELECT count(*) FROM (TABLE pg_authid) AS z) AS n\n",
    ),
    "adds a stray percent sign to a comment": (
        "-- BINDING. The ledger's primary key",
        "-- BINDING (100%). The ledger's primary key",
    ),
    "selects every ledger column with a star": (
        T_TARGET + "           l.state,\n           l.outcome_code,\n           l.http_status,\n"
        "           l.run_id,\n           l.analysis_hash,\n           l.deadline_ms,\n"
        "           l.received_at_utc\n",
        "    SELECT *\n",
    ),
    "reads a whole row through a CTE alias": (
        "min(t.analysis_hash) END AS analysis_hash",
        "min(t::text) END AS analysis_hash",
    ),
    "a star through a CTE alias": (
        "min(t.analysis_hash) END AS analysis_hash",
        "min(t.analysis_hash) END AS analysis_hash, count(t.*) AS n",
    ),
    "a whole row through a CTE name": (
        T_RUN_COUNT,
        T_RUN_COUNT[:-1] + ", (SELECT min(target::text) FROM target) AS w2\n",
    ),
    "reads a whole ledger row through a derived table": (
        "           b.expected_run_id AS bound_run_id,\n",
        "           (SELECT min(x::text) FROM (SELECT * FROM public.automation_radar_ledger AS z)"
        " AS x) AS bound_run_id,\n",
    ),
    "reads whole prediction rows through a derived table": (
        "           b.expected_run_id AS bound_run_id,\n",
        "           (SELECT min(x::text) FROM (SELECT * FROM public.predictions AS z) AS x)"
        " AS bound_run_id,\n",
    ),
    "reads an unqualified relation after SELECT DISTINCT": (
        T_RUN_COUNT,
        T_RUN_COUNT[:-1] + ", EXISTS (SELECT DISTINCT FROM users) AS u\n",
    ),
    "drops the inheritance check": (
        "            AND NOT EXISTS (SELECT 1\n"
        "                              FROM pg_catalog.pg_inherits AS i\n"
        "                              JOIN relations AS h ON h.oid = i.inhparent)\n",
        "",
    ),
    # The second review's class: SQL the guard's model did not cover. Each must be refused.
    "hides a read inside an escape string": (
        "       d.bound_run_id,\n",
        "       E'\\'' || (SELECT min(z::text) FROM public.automation_radar_ledger AS z)"
        " || E'\\'' AS bound_run_id,\n",
    ),
    "a Unicode-escape literal": (
        "WHEN k.evidence_origin IS DISTINCT FROM 'AUTOMATED_RADAR' THEN 'WRONG_ORIGIN'",
        "WHEN k.evidence_origin IS DISTINCT FROM U&'AUTOMATED_RADAR' THEN 'WRONG_ORIGIN'",
    ),
    "a bit-string literal": (
        "     WHERE a.attnum > 0\n",
        "     WHERE a.attnum > 0 AND B'1' = B'1'\n",
    ),
    "a non-ASCII alias": (
        "      FROM target AS t\n",
        "      FROM target AS t CROSS JOIN target AS \u00e4\n",
    ),
    "a tab": ("WITH binding AS (\n", "WITH binding AS (\n\t"),
    "an operator the guard does not model": (
        "     WHERE a.attnum > 0\n",
        "     WHERE a.attnum > 0 AND a.attname <-> a.attname = 0\n",
    ),
    "a cast to a type the guard does not model": (
        "b.client_request_id::text AS bound_client_request_id",
        "b.client_request_id::regclass AS bound_client_request_id",
    ),
    "a CAST to a type the guard does not model": (
        "CAST(%(credential_id)s AS text)",
        "CAST(%(credential_id)s AS shadow_text)",
    ),
    "a keyword the guard does not model": (
        "     CROSS JOIN credential_rows AS cr\n",
        "     NATURAL JOIN credential_rows AS cr\n",
    ),
    "an identifier the guard does not model": (
        "(s.schema_ok IS TRUE) AS schema_ok",
        "(s.schema_ok IS TRUE AND current_user = current_user) AS schema_ok",
    ),
    "reads an undeclared catalog column": (
        "       AND c.relkind = 'r'\n",
        "       AND c.relkind = 'r'\n       AND c.relhassubclass = false\n",
    ),
    "reads prediction run ids beyond the count": (
        "           b.expected_run_id AS bound_run_id,\n",
        "           (SELECT min(q.run_id) FROM public.predictions AS q) AS bound_run_id,\n",
    ),
    "reads unrelated ledger rows": (
        "           b.expected_run_id AS bound_run_id,\n",
        "           (SELECT min(z.run_id) FROM public.automation_radar_ledger AS z)"
        " AS bound_run_id,\n",
    ),
    "reads the catalog beyond the schema proof": (
        "           b.expected_run_id AS bound_run_id,\n",
        "           (SELECT min(c2.relname) FROM pg_catalog.pg_class AS c2) AS bound_run_id,\n",
    ),
    # A4-CRID-UNIQUENESS: the cross-credential count reads client_request_id and nothing else, names
    # no credential, counts every credential, and is reported, never judged.
    "aggregates other credentials' ids": (
        T_CRID_COUNT,
        T_CRID_COUNT[:-1] + ", array_agg(g.credential_id) AS others\n",
    ),
    "string-aggregates other credentials' ids": (
        T_CRID_COUNT,
        T_CRID_COUNT[:-1] + ", string_agg(g.credential_id, ',') AS others\n",
    ),
    "projects the least of the credentials' ids": (
        T_CRID_COUNT,
        T_CRID_COUNT[:-1] + ", min(g.credential_id) AS other\n",
    ),
    "json-aggregates other credentials' ids": (
        T_CRID_COUNT,
        T_CRID_COUNT[:-1] + ", json_agg(g.credential_id) AS others\n",
    ),
    "groups the count by credential": (T_CRID_ON, T_CRID_ON + "     GROUP BY g.credential_id\n"),
    "counts only the bound credential's rows": (
        T_CRID_ON,
        T_CRID_ON + "       AND g.credential_id = b.credential_id\n",
    ),
    "counts only the other credentials' rows": (
        T_CRID_ON,
        T_CRID_ON + "       AND g.credential_id <> b.credential_id\n",
    ),
    "projects another credential's id": (
        "           b.expected_run_id AS bound_run_id,\n",
        "           (SELECT min(z.credential_id) FROM public.automation_radar_ledger AS z"
        " WHERE z.client_request_id = b.client_request_id) AS bound_run_id,\n",
    ),
    "counts the id from the bound row alone": (
        "      FROM public.automation_radar_ledger AS g\n",
        "      FROM target AS g\n",
    ),
    "judges the cross-credential count": (
        "               ELSE 'OK'\n",
        "               WHEN k.ledger_rows_for_client_request_id_across_all_credentials <> 1"
        " THEN 'CRID_NOT_UNIQUE'\n               ELSE 'OK'\n",
    ),
    "drops the cross-credential count": (
        "       d.credential_ledger_rows_since_activation,\n"
        "       d.ledger_rows_for_client_request_id_across_all_credentials\n",
        "       d.credential_ledger_rows_since_activation\n",
    ),
    "adds an input": (
        "CAST(%(credential_id)s AS text)",
        "CAST(%(credential_id)s || %(x)s AS text)",
    ),
    # The fourth review's class, each first shown to pass the guard before its repair: a literal
    # carries a pinned fragment's text while the SQL around it does something else.
    "aggregates the credential ids behind a window in a literal": [
        (
            T_CREDENTIAL_COUNT,
            "    SELECT array_agg(w.credential_id ORDER BY w.received_at_utc)"
            " AS credential_ledger_rows_since_activation\n",
        ),
        (T_WINDOW, f"        ON '{L_WINDOW}' <> ''\n"),
    ],
    "binds on the id alone behind a literal and projects a credential id as the hash": [
        ("           l.analysis_hash,\n", "           l.credential_id AS analysis_hash,\n"),
        (
            T_BIND + " = b.client_request_id\n",
            "        ON l.client_request_id = b.client_request_id\n"
            f"       AND '{L_TARGET}' <> l.analysis_hash\n",
        ),
    ],
    "binds on client_request_id alone behind a literal": (
        T_BIND,
        f"        ON l.credential_id <> '' AND '{L_TARGET}' <> ''\n       AND l.client_request_id",
    ),
    "makes the window exclusive behind a literal": (
        T_WINDOW,
        T_WINDOW.replace(">=", ">") + f"       AND '{L_WINDOW}' <> ''\n",
    ),
    "counts every credential's rows behind a literal": (
        T_WINDOW,
        "        ON w.credential_id <> ''\n       AND w.received_at_utc >= b.activation_utc\n"
        f"       AND '{L_WINDOW}' <> ''\n",
    ),
    "drops the deadline comparison behind a literal": (
        "(f.deadline_ms IS NOT DISTINCT FROM b.expected_deadline_ms) AS deadline_ms_matches",
        "(TRUE OR '(f.deadline_ms IS NOT DISTINCT FROM b.expected_deadline_ms)"
        " AS deadline_ms_matches' <> '') AS deadline_ms_matches",
    ),
    "drops the analysis-hash comparison behind a literal": (
        "(f.analysis_hash IS NOT DISTINCT FROM b.expected_analysis_hash) AS analysis_hash_matches",
        "(TRUE OR '(f.analysis_hash IS NOT DISTINCT FROM b.expected_analysis_hash)"
        " AS analysis_hash_matches' <> '') AS analysis_hash_matches",
    ),
    "makes the inheritance check always true behind a literal": (
        "                              JOIN relations AS h ON h.oid = i.inhparent)\n",
        "                              JOIN relations AS h ON h.oid = i.inhparent"
        " WHERE 'AND NOT EXISTS (SELECT 1 FROM pg_catalog.pg_inherits AS i"
        " JOIN relations AS h ON h.oid = i.inhparent)' = '')\n",
    ),
    "forces schema_ok behind a literal": (
        "(s.schema_ok IS TRUE) AS schema_ok",
        "(TRUE OR '(s.schema_ok IS TRUE) AS schema_ok' <> '') AS schema_ok",
    ),
    "counts every other run's predictions behind a literal": (
        T_RUN_ON,
        f"        ON p.run_id <> b.expected_run_id\n       AND '{L_RUN}' <> ''\n",
    ),
    "counts every ledger row as the cross-credential count behind a literal": (
        T_CRID_ON,
        f"        ON g.client_request_id <> b.client_request_id OR '{L_REQUEST}' <> ''\n",
    ),
    # A name PostgreSQL evaluates as a value, declared as a column and then used bare: the guard
    # would read a column where PostgreSQL reads the database role or the schema.
    "projects the database role through a declared name": [
        (T_MATCHED, "    SELECT count(*) AS matched_rows, count(*) AS current_user,\n"),
        (T_BOUND_RUN, "           current_user AS bound_run_id,\n"),
    ],
    "projects the session user through a declared name": [
        (T_MATCHED, "    SELECT count(*) AS matched_rows, count(*) AS session_user,\n"),
        (T_BOUND_RUN, "           session_user AS bound_run_id,\n"),
    ],
    "projects the current schema through a declared name": [
        (T_MATCHED, "    SELECT count(*) AS matched_rows, count(*) AS current_schema,\n"),
        (T_BOUND_RUN, "           current_schema AS bound_run_id,\n"),
    ],
    # Every mapping from an input or a read to an output is pinned.
    "swaps two outputs in the final SELECT": (
        "       d.analysis_hash,\n",
        "       d.bound_credential_id AS analysis_hash,\n",
    ),
    "swaps two facts in the checks": (
        "           f.deadline_ms,\n",
        "           f.analysis_hash AS deadline_ms,\n",
    ),
    "swaps two facts of the bound row": (
        "min(t.evidence_origin) END AS evidence_origin",
        "min(t.state) END AS evidence_origin",
    ),
    "swaps two inputs in the binding": [
        (
            "CAST(%(credential_id)s AS text) AS credential_id",
            "CAST(%(expected_run_id)s AS text) AS credential_id",
        ),
        (
            "CAST(%(expected_run_id)s AS text) AS expected_run_id",
            "CAST(%(credential_id)s AS text) AS expected_run_id",
        ),
    ],
    # The two ledger counts stay separate (UOR's addendum): no window on the cross-credential count,
    # no request filter on the credential count, neither reported as the other.
    "windows the cross-credential count by the activation": (
        T_CRID_ON,
        T_CRID_ON + "       AND g.received_at_utc >= b.activation_utc\n",
    ),
    "narrows the credential count to the request": (
        T_WINDOW,
        T_WINDOW + "       AND w.client_request_id = b.client_request_id\n",
    ),
    "reports the credential count as the cross-credential count": (
        "           rq.ledger_rows_for_client_request_id_across_all_credentials\n",
        "           cr.credential_ledger_rows_since_activation"
        " AS ledger_rows_for_client_request_id_across_all_credentials\n",
    ),
    # Exactly the declared literals and function calls, and literals PostgreSQL reads as written.
    "adds a literal": (
        "     WHERE a.attnum > 0\n",
        "     WHERE a.attnum > 0 AND a.attname <> 'x'\n",
    ),
    "calls an allowed function once more": (
        "            AND (SELECT count(*) FROM ledger_key) = 1\n",
        "            AND (SELECT count(*) FROM ledger_key) >= (SELECT min(1) FROM ledger_key)\n",
    ),
    "splits a literal that PostgreSQL would join again": (
        "     WHERE n.nspname = 'public'\n",
        "     WHERE n.nspname = 'pub'\n'lic'\n",
    ),
}


def _pairs(mutant: tuple[str, str] | list[tuple[str, str]]) -> list[tuple[str, str]]:
    return mutant if isinstance(mutant, list) else [mutant]


def mutated(name: str) -> str:
    sql = SEALED
    for old, new in _pairs(MUTANTS[name]):
        assert sql.count(old) == 1, name
        sql = sql.replace(old, new)
    assert sql != SEALED, name
    return sql


@pytest.mark.parametrize("name", sorted(MUTANTS))
def test_every_adversarial_mutant_fails_the_guard(name: str) -> None:
    sql = mutated(name)
    # The first layer refuses each mutant on its own; the second refuses every SQL but the sealed.
    assert property_violations(sql), name
    assert guard_violations(sql), name


# --------------------------------------------------------------------------- schema proof
def test_the_expected_columns_are_the_migrations_declarations() -> None:
    expected = {
        (m[0], m[1]): (m[2], m[3] == "true")
        for m in re.findall(r"\('([a-z_]+)', '([a-z_]+)', '([a-z ]+)', (true|false)\)", SEALED)
    }
    ledger, predictions = table_columns("automation_radar_ledger"), table_columns("predictions")
    assert len(ledger) == 15
    assert {"p_up_frac", "p_down_frac", "p_timeout_frac", "prediction_origin"} <= set(predictions)
    wanted = {("automation_radar_ledger", name): ledger[name] for name in DATA_COLUMNS[LEDGER]}
    wanted[("predictions", "run_id")] = predictions["run_id"]
    assert expected == wanted
    assert wanted[("predictions", "run_id")] == ("text", True)
    key = re.search(
        r"CONSTRAINT automation_radar_ledger_pkey PRIMARY KEY \(([^)]*)\)",
        (MIGRATIONS / "0013_automation_radar_ledger.sql").read_text(encoding="utf-8"),
    )
    assert key and sorted(part.strip() for part in key[1].split(",")) == [
        "client_request_id",
        "credential_id",
    ]
    assert "= ARRAY['client_request_id', 'credential_id']" in SEALED


def test_no_later_migration_changes_a_column_the_companion_reads() -> None:
    ledger = re.compile(
        r"(ALTER\s+TABLE\s+(?:IF\s+EXISTS\s+)?(?:ONLY\s+)?public\.automation_radar_ledger\s+"
        r"(?:ADD|DROP|ALTER|RENAME))|(DROP\s+TABLE[^;]*automation_radar_ledger)",
        re.IGNORECASE,
    )
    run_id = re.compile(
        r"(ALTER\s+TABLE[^;]*\bpredictions\b[^;]*(?:ALTER|DROP|RENAME)\s+(?:COLUMN\s+)?run_id)"
        r"|(DROP\s+TABLE[^;]*\bpredictions\b)|(ALTER\s+TABLE[^;]*\bpredictions\b[^;]*RENAME\s+TO)",
        re.IGNORECASE,
    )
    for path in sorted(MIGRATIONS.glob("*.sql")):
        text = path.read_text(encoding="utf-8")
        if path.name[:4] > "0013":
            assert not ledger.search(text), path.name
        if path.name[:4] > "0003":
            assert not run_id.search(text), path.name


def test_the_route_writes_each_fact_where_the_companion_reads_it() -> None:
    """The durable-source proof, kept true: if a writer moves, this companion must be revisited."""

    automation = ROOT / "src" / "crypto_probability_engine" / "automation"
    ledger = (automation / "ledger.py").read_text(encoding="utf-8")
    insert = ledger.split("_INSERT_SQL = ", 1)[1].split('"""', 2)[1]
    complete = ledger.split("_COMPLETE_SQL = ", 1)[1].split('"""', 2)[1]
    # deadline_ms and received_at_utc are written once, at reservation, and never updated.
    assert "deadline_ms" in insert and "received_at_utc" in insert
    assert "deadline_ms" not in complete and "received_at_utc =" not in complete
    # The key columns are written once, at reservation, and never rewritten; no row is deleted. So
    # the count of rows carrying a client_request_id across credentials is durable.
    assert "client_request_id" in insert and "credential_id" in insert
    assert "client_request_id" not in complete.split("WHERE", 1)[0]
    assert "credential_id" not in complete.split("WHERE", 1)[0]
    assert not re.search(r"\b(DELETE\s+FROM|TRUNCATE)\b", ledger, re.I)
    # analysis_hash is written with the outcome, from the same evidence the caller receives.
    assert "analysis_hash = %(analysis_hash)s" in complete
    service = (automation / "service.py").read_text(encoding="utf-8")
    assert "deadline_ms=request.deadline_ms," in service
    assert 'analysis_hash=evidence["analysis_hash"],' in service
    assert "return AutomationResult(200, evidence," in service
    contract = (automation / "contract.py").read_text(encoding="utf-8")
    fingerprint = contract.split("def fingerprint(self)", 1)[1].split("def ", 1)[0]
    assert '"deadline_ms": self.deadline_ms' in fingerprint  # a repeat must carry the same deadline
    analysis = (ROOT / "src/crypto_probability_engine/api/analysis_service.py").read_text(
        encoding="utf-8"
    )
    isolated = analysis.split("def analyze_request_isolated(", 1)[1].split("\ndef ", 1)[0]
    assert "record_prediction=False" in isolated and "prediction_origin=None" in isolated
    assert 'run_id = f"run_{uuid4().hex}"' in analysis  # one generator for both domains


# --------------------------------------------------------------------------- the runner, offline
def _facts(module: Any = None, **changes: Any) -> dict[str, Any]:
    module = module or runner
    facts = dict(
        artifact=module.ARTIFACT,
        verdict="PASS",
        reason="OK",
        bound_credential_id=CRED,
        bound_client_request_id=CRID,
        bound_run_id=RUN,
        schema_ok=True,
        deadline_ms=int(DEADLINE),
        deadline_ms_matches=True,
        analysis_hash=AHASH,
        analysis_hash_matches=True,
        predictions_rows_for_run_id=0,
        credential_ledger_rows_since_activation=3,
        ledger_rows_for_client_request_id_across_all_credentials=1,
    )
    facts.update(changes)
    return facts


def _row(module: Any = None, **changes: Any) -> tuple[Any, ...]:
    facts = _facts(module, **changes)
    return tuple(facts[name] for name in runner.SQL_COLUMNS)


# A stop line: the runner's own values only, never any of the SQL's answer.
STOP_KEYS = {
    "artifact",
    "verdict",
    "reason",
    "sql_sha256",
    "bound_credential_id",
    "bound_client_request_id",
    "bound_run_id",
    "bound_qualification_activation_utc",
}
OTHER_CREDENTIAL = "uor-radar-other"  # a value the SQL must never get printed


def _link(path: Path) -> None:
    """Replace a package file by a link to a file with the same bytes, outside the folder."""

    target = path.parent.parent / f"{path.name}.target"
    target.write_bytes(path.read_bytes())
    path.unlink()
    path.symlink_to(target)


class FakeConnection:
    """A session that honours the preamble like PostgreSQL: read-only and row security only change
    when the runner sets them, unless the server is told to ignore it."""

    def __init__(
        self,
        row: tuple[Any, ...] | None = None,
        *,
        rows: int = 1,
        columns: tuple[str, ...] | None = None,
        fail_on: str | None = None,
        rollback_fails: bool = False,
        ignore: tuple[str, ...] = (),
    ) -> None:
        self.row = row if row is not None else _row()
        self.rows = rows
        self.columns = columns or runner.SQL_COLUMNS
        self.fail_on = fail_on
        self.rollback_fails = rollback_fails
        self.ignore = ignore
        self.settings = {"transaction_read_only": "off", "row_security": "on"}
        self.calls: list[tuple[str, Any]] = []
        self.ended: list[str] = []

    def cursor(self) -> FakeCursor:
        return FakeCursor(self)

    def rollback(self) -> None:
        self.ended.append("rollback")
        if self.rollback_fails:
            raise RuntimeError("connection lost " + URL)

    def close(self) -> None:
        self.ended.append("close")


class FakeCursor:
    def __init__(self, connection: FakeConnection) -> None:
        self.connection = connection
        self.description: list[tuple[str]] | None = None
        self.result: list[tuple[Any, ...]] = []

    def __enter__(self) -> FakeCursor:
        return self

    def __exit__(self, *_: Any) -> bool:
        return False

    def execute(self, sql: str, params: Any = None) -> None:
        connection = self.connection
        connection.calls.append((sql, params))
        if connection.fail_on and connection.fail_on in sql:
            raise RuntimeError("relation failed at " + URL)
        if sql == "SET TRANSACTION READ ONLY" and "read_only" not in connection.ignore:
            connection.settings["transaction_read_only"] = "on"
        if sql == "SET LOCAL row_security = off" and "row_security" not in connection.ignore:
            connection.settings["row_security"] = "off"
        if sql.startswith("SELECT pg_catalog.current_setting"):
            settings = connection.settings
            self.result = [(settings["transaction_read_only"], settings["row_security"])]
            self.description = [("current_setting",), ("current_setting",)]
        elif sql == SEALED:
            self.result = [connection.row] * connection.rows
            self.description = [(name,) for name in connection.columns]
        else:
            self.result, self.description = [], None

    def fetchone(self) -> tuple[Any, ...] | None:
        return self.result[0] if self.result else None

    def fetchall(self) -> list[tuple[Any, ...]]:
        return list(self.result)


ARGS = [
    "--credential-id",
    CRED,
    "--client-request-id",
    CRID,
    "--run-id",
    RUN,
    "--deadline-ms",
    DEADLINE,
    "--analysis-hash",
    AHASH,
    "--qualification-activation-utc",
    ACTIVATION,
]


def _invoke(
    module: Any,
    connection: FakeConnection | None = None,
    *,
    args: list[str] | None = None,
    environ: dict[str, str] | None = None,
    connect: Callable[..., Any] | None = None,
) -> tuple[int, dict[str, Any], list, str]:
    connection = connection or FakeConnection(_row(module))
    seen: list[Any] = []

    def fake_connect(url: str, **kwargs: Any) -> FakeConnection:
        seen.append((url, kwargs))
        return connection

    out = io.StringIO()
    code = module.main(
        ARGS if args is None else args,
        environ={module.DATABASE_URL_ENV: URL} if environ is None else environ,
        connect=connect or fake_connect,
        stdout=out,
    )
    text = out.getvalue()
    assert text.endswith("\n") and text.count("\n") == 1
    return code, json.loads(text), seen, text


def _run(connection: FakeConnection | None = None, **kwargs: Any) -> tuple[int, dict, list, str]:
    code, payload, seen, text = _invoke(runner, connection, **kwargs)
    assert URL not in text and "NOT-A-REAL-PASSWORD" not in text
    return code, payload, seen, text


def _args(**changes: str) -> list[str]:
    pairs = dict(zip(ARGS[::2], ARGS[1::2], strict=True))
    pairs.update({f"--{flag.replace('_', '-')}": value for flag, value in changes.items()})
    return [item for pair in pairs.items() for item in pair]


def test_a_qualifying_row_passes_inside_one_read_only_unfiltered_transaction() -> None:
    connection = FakeConnection()
    code, payload, seen, text = _run(connection)
    assert code == 0 and payload["verdict"] == "PASS" and payload["reason"] == "OK"
    assert payload["transaction_read_only"] is True and payload["row_security_off"] is True
    assert payload["sql_sha256"] == runner.SQL_SHA256
    assert payload["artifact_sha256"] == hashlib.sha256(MANIFEST.read_bytes()).hexdigest()
    assert payload["bound_qualification_activation_utc"] == ACTIVATION
    assert text == json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n"
    assert [sql for sql, _ in connection.calls] == [
        "SET TRANSACTION READ ONLY",
        "SET LOCAL statement_timeout = '5000ms'",
        "SET LOCAL lock_timeout = '1000ms'",
        "SET LOCAL row_security = off",
        "SELECT pg_catalog.current_setting('transaction_read_only'),"
        " pg_catalog.current_setting('row_security')",
        SEALED,
    ]
    assert connection.calls[-1][1] == {
        "credential_id": CRED,
        "client_request_id": CRID,
        "expected_run_id": RUN,
        "expected_deadline_ms": DEADLINE,
        "expected_analysis_hash": AHASH,
        "qualification_activation_utc": ACTIVATION,
    }
    assert connection.ended == ["rollback", "close"]
    ((url, kwargs),) = seen
    assert url == URL and kwargs["autocommit"] is False and kwargs["prepare_threshold"] is None
    assert kwargs["connect_timeout"] == 10
    assert sorted(payload) == json.loads(MANIFEST.read_text(encoding="utf-8"))["output_keys"]
    assert len(payload) == 19 and "response_body" not in text


def test_the_output_is_byte_for_byte_deterministic() -> None:
    first, second = _run()[3], _run()[3]
    assert first == second


@pytest.mark.parametrize(
    ("reason", "changes"),
    [
        ("SCHEMA_DRIFT", dict(schema_ok=False)),
        (
            "NO_ROW",
            dict(
                deadline_ms=None,
                deadline_ms_matches=False,
                analysis_hash=None,
                analysis_hash_matches=False,
            ),
        ),
        (
            "AMBIGUOUS",
            dict(
                deadline_ms=None,
                deadline_ms_matches=False,
                analysis_hash=None,
                analysis_hash_matches=False,
                ledger_rows_for_client_request_id_across_all_credentials=2,
            ),
        ),
        ("WRONG_ORIGIN", {}),
        ("NOT_COMPLETED", dict(analysis_hash=None, analysis_hash_matches=False)),
        ("NOT_SUCCEEDED", dict(analysis_hash=None, analysis_hash_matches=False)),
        ("RUN_MISMATCH", {}),
        ("DEADLINE_MISMATCH", dict(deadline_ms=45000, deadline_ms_matches=False)),
        (
            "ANALYSIS_HASH_MISMATCH",
            dict(analysis_hash="sha256:" + "0" * 64, analysis_hash_matches=False),
        ),
        ("ACTIVATION_AFTER_REQUEST", {}),
    ],
)
def test_every_failing_row_fails_with_its_reason(reason: str, changes: dict[str, Any]) -> None:
    code, payload, _, _ = _run(FakeConnection(_row(verdict="FAIL", reason=reason, **changes)))
    assert code == 1 and payload["verdict"] == "FAIL" and payload["reason"] == reason


@pytest.mark.parametrize(
    "lie",
    [
        dict(deadline_ms=45000),  # PASS, but the deadline differs
        dict(analysis_hash="sha256:" + "1" * 64),  # PASS, but the hash differs
        dict(deadline_ms_matches=False),  # a match the runner cannot reproduce
        dict(predictions_rows_for_run_id=-1),
        dict(ledger_rows_for_client_request_id_across_all_credentials=-1),
        dict(ledger_rows_for_client_request_id_across_all_credentials=True),
        dict(ledger_rows_for_client_request_id_across_all_credentials=0),  # a bound row, yet none
        dict(  # an ambiguous pair is two rows carrying the id, yet one
            reason="AMBIGUOUS",
            verdict="FAIL",
            deadline_ms=None,
            deadline_ms_matches=False,
            analysis_hash=None,
            analysis_hash_matches=False,
        ),
        dict(credential_ledger_rows_since_activation=True),
        dict(reason="SOMETHING_ELSE", verdict="FAIL"),
        dict(reason="RUN_MISMATCH"),  # a FAIL reason with a PASS verdict
        dict(reason="SCHEMA_DRIFT", verdict="FAIL"),  # drift while the schema is fine
        dict(reason="NO_ROW", verdict="FAIL"),  # no row, yet a deadline and a hash
        dict(reason="ANALYSIS_HASH_MISMATCH", verdict="FAIL"),  # yet the hash matches
        dict(bound_run_id="run_" + "2" * 32),
        dict(artifact="ucpe.something_else.v1"),
        # Values outside the ledger's own formats, though the reason agrees with them.
        dict(
            reason="ANALYSIS_HASH_MISMATCH",
            verdict="FAIL",
            analysis_hash=OTHER_CREDENTIAL,
            analysis_hash_matches=False,
        ),
        dict(reason="DEADLINE_MISMATCH", verdict="FAIL", deadline_ms=1, deadline_ms_matches=False),
        dict(credential_ledger_rows_since_activation=[OTHER_CREDENTIAL]),
    ],
)
def test_an_answer_the_runner_cannot_reproduce_is_refused(lie: dict[str, Any]) -> None:
    code, payload, _, text = _run(FakeConnection(_row(**lie)))
    assert code == 1 and payload["reason"] == "RUNNER_DISAGREES" and payload["verdict"] == "FAIL"
    # None of the SQL's answer is printed: only the stop line, with the runner's own values.
    assert set(payload) == STOP_KEYS and OTHER_CREDENTIAL not in text
    assert payload["bound_run_id"] == RUN and payload["sql_sha256"] == runner.SQL_SHA256


@pytest.mark.parametrize(
    ("ignored", "reason"),
    [("read_only", "NOT_READ_ONLY"), ("row_security", "ROW_SECURITY_NOT_OFF")],
)
def test_a_session_that_is_not_proven_runs_nothing(ignored: str, reason: str) -> None:
    connection = FakeConnection(ignore=(ignored,))
    code, payload, _, _ = _run(connection)
    assert code == 4 and payload["reason"] == reason
    assert SEALED not in [sql for sql, _ in connection.calls]
    assert connection.ended == ["rollback", "close"]


def test_a_database_error_is_named_by_class_only_and_still_rolls_back() -> None:
    connection = FakeConnection(fail_on="WITH binding", rollback_fails=True)
    code, payload, _, text = _run(connection)
    assert code == 4 and payload["reason"] == "DATABASE_ERROR"
    assert payload["error_class"] == "RuntimeError" and "relation failed" not in text
    assert connection.ended == ["rollback", "close"]


def _refusing_connect(url: str, **_: Any) -> Any:
    raise ConnectionError("could not connect to " + url)


def test_a_failed_connection_is_named_by_class_only() -> None:
    code, payload, _, _ = _run(connect=_refusing_connect)
    assert code == 4 and payload["error_class"] == "ConnectionError"


@pytest.mark.parametrize(
    "connection",
    [
        FakeConnection(columns=(*runner.SQL_COLUMNS[:-1], "extra")),
        FakeConnection(rows=0),
        FakeConnection(rows=2),
    ],
    ids=["columns", "no row", "two rows"],
)
def test_an_unexpected_result_shape_is_refused(connection: FakeConnection) -> None:
    code, payload, _, _ = _run(connection)
    assert code == 4 and payload["reason"] == "UNEXPECTED_RESULT_SHAPE"


def test_a_missing_database_url_contacts_nothing() -> None:
    code, payload, seen, _ = _run(environ={})
    assert code == 4 and payload["reason"] == "DATABASE_URL_MISSING" and seen == []


def test_a_changed_sql_is_refused_before_anything_is_contacted(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    tampered = tmp_path / "a4_card04_companion.sql"
    tampered.write_text(SEALED.replace("'AMBIGUOUS'", "'OK'"), encoding="utf-8")
    monkeypatch.setattr(runner, "SQL_PATH", tampered)
    code, payload, seen, _ = _run()
    assert code == 3 and payload["reason"] == "SEAL_MISMATCH" and seen == []


def _copied_package(tmp_path: Path) -> Path:
    copy = tmp_path / "ops" / "a4_card04_companion"
    shutil.copytree(PACKAGE, copy, ignore=shutil.ignore_patterns("__pycache__", ".*"))
    return copy


@pytest.mark.parametrize(
    "tamper",
    [
        lambda copy: (copy / "CARD.md").write_text("edited\n", encoding="utf-8"),
        lambda copy: (copy / "build_manifest.py").write_text("# edited\n", encoding="utf-8"),
        lambda copy: (copy / "MANIFEST.json").unlink(),
        lambda copy: (copy / "MANIFEST.json").write_text("{", encoding="utf-8"),
        lambda copy: (copy / "MANIFEST.json").write_text(
            (copy / "MANIFEST.json")
            .read_text(encoding="utf-8")
            .replace('"ops/a4_card04_companion/CARD.md"', '"ops/a4_card04_companion/OTHER.md"'),
            encoding="utf-8",
        ),
    ],
    ids=["card", "builder", "no manifest", "garbled manifest", "renamed entry"],
)
def test_a_package_that_does_not_match_its_seal_contacts_nothing(
    tmp_path: Path, tamper: Callable[[Path], Any]
) -> None:
    copy = _copied_package(tmp_path)
    tamper(copy)
    module = _module("a4c_runner_copy", copy / "a4_card04_companion.py")
    code, payload, seen, _ = _invoke(module, FakeConnection(_row(module)))
    assert code == 3 and payload["reason"] == "SEAL_MISMATCH" and seen == []


@pytest.mark.parametrize(
    "plant",
    [
        lambda copy: (copy / "psycopg.py").write_text("raise SystemExit(99)\n", encoding="utf-8"),
        lambda copy: (copy / "__pycache__").mkdir(),
        lambda copy: (copy / ".DS_Store").write_bytes(b""),
        lambda copy: _link(copy / "CARD.md"),
    ],
    ids=["a module", "a bytecode folder", "a hidden file", "a link with the same bytes"],
)
def test_a_package_folder_holding_anything_else_contacts_nothing(
    tmp_path: Path, plant: Callable[[Path], Any]
) -> None:
    copy = _copied_package(tmp_path)
    plant(copy)
    module = _module("a4c_runner_planted", copy / "a4_card04_companion.py")
    code, payload, seen, _ = _invoke(module, FakeConnection(_row(module)))
    assert code == 3 and payload["reason"] == "SEAL_MISMATCH" and seen == []


def test_an_intact_copy_of_the_package_still_runs(tmp_path: Path) -> None:
    module = _module("a4c_runner_intact_copy", _copied_package(tmp_path) / "a4_card04_companion.py")
    code, payload, _, _ = _invoke(module, FakeConnection(_row(module)))
    assert (
        code == 0
        and payload["artifact_sha256"] == hashlib.sha256(MANIFEST.read_bytes()).hexdigest()
    )


@pytest.mark.parametrize(
    ("flag", "value"),
    [
        ("credential_id", "ucpea.uor-radar-2026-10.THE-SECRET-VALUE"),
        ("credential_id", "UOR"),
        ("client_request_id", CRID.upper()),
        ("client_request_id", CRID.replace("-", "")),
        ("client_request_id", "00000000-0000-0000-0000-000000000000"),
        ("run_id", RUN.upper()),
        ("deadline_ms", "4999"),
        ("deadline_ms", "60001"),
        ("deadline_ms", "030000"),
        ("deadline_ms", "30000.0"),
        ("deadline_ms", "+30000"),
        ("analysis_hash", "ab" * 32),
        ("analysis_hash", AHASH.upper()),
        ("qualification_activation_utc", "2026-10-05T00:00:00"),
        ("qualification_activation_utc", "2026-10-05T00:00:00+00:00"),
        ("qualification_activation_utc", "2026-10-05t00:00:00z"),
        ("qualification_activation_utc", "2026-10-05 00:00:00Z"),
        ("qualification_activation_utc", "2026-02-30T00:00:00Z"),
        ("qualification_activation_utc", "2026-10-05T24:00:00Z"),
        ("qualification_activation_utc", "2026-10-05T23:59:60Z"),
        ("qualification_activation_utc", "2026-10-05T00:00:00.1234567Z"),
        ("qualification_activation_utc", "2026-10-05"),
    ],
)
def test_malformed_inputs_are_refused_unechoed_before_contact(flag: str, value: str) -> None:
    code, payload, seen, text = _run(args=_args(**{flag: value}))
    assert code == 2 and payload["reason"] == f"INPUT_REFUSED:{flag}"
    assert seen == [] and value not in text


@pytest.mark.parametrize(
    "activation", ["2026-10-05T00:00:00.5Z", "2026-10-05T23:59:59.999999Z", "2024-02-29T12:00:00Z"]
)
def test_canonical_activation_instants_are_accepted(activation: str) -> None:
    code, payload, _, _ = _run(args=_args(qualification_activation_utc=activation))
    assert code == 0 and payload["bound_qualification_activation_utc"] == activation


@pytest.mark.parametrize(
    "args",
    [
        ["--token", "ucpea.x-y-z.SECRET"],
        ["-h"],
        [*ARGS, "--help"],
        [*ARGS, "--run-id", RUN],
        [*ARGS[:-2], "--qualification-activation", ACTIVATION],
        [*ARGS, "ucpea.x-y-z.SECRET"],
    ],
    ids=["unknown", "-h", "--help", "repeated", "abbreviated", "positional"],
)
def test_unknown_repeated_or_abbreviated_arguments_are_refused_unechoed(args: list[str]) -> None:
    code, payload, seen, text = _run(args=args)
    assert code == 2 and payload["reason"] == "INPUT_REFUSED:arguments"
    assert seen == [] and "SECRET" not in text


@pytest.mark.parametrize(
    ("isolated", "no_bytecode"), [(0, 1), (1, 0), (0, 0)], ids=["no -I", "no -B", "neither"]
)
def test_the_command_line_refuses_any_start_but_python_dash_i_dash_b(
    isolated: int, no_bytecode: int
) -> None:
    connection, out = FakeConnection(), io.StringIO()
    code = runner.entry(
        ARGS,
        flags=SimpleNamespace(isolated=isolated, dont_write_bytecode=no_bytecode),
        environ={runner.DATABASE_URL_ENV: URL},
        connect=lambda url, **_: connection,
        stdout=out,
    )
    assert code == 2 and connection.calls == []
    assert json.loads(out.getvalue()) == {
        "artifact": runner.ARTIFACT,
        "verdict": "FAIL",
        "reason": "NOT_ISOLATED",
    }


def test_python_dash_i_dash_b_runs_the_audit() -> None:
    connection, out = FakeConnection(), io.StringIO()
    code = runner.entry(
        ARGS,
        flags=SimpleNamespace(isolated=1, dont_write_bytecode=1),
        environ={runner.DATABASE_URL_ENV: URL},
        connect=lambda url, **_: connection,
        stdout=out,
    )
    assert code == 0 and json.loads(out.getvalue())["verdict"] == "PASS"


def test_the_real_command_line_starts_only_as_python_dash_i_dash_b() -> None:
    """The file itself, as the card runs it, in a child process given no database URL: -I -B passes
    the start and the package check and stops at the missing URL, contacting nothing; any other
    start is refused. The package folder is unchanged after all three."""

    environment = {"PATH": os.environ.get("PATH", "")}
    stops = {}
    for flags in (["-I", "-B"], ["-B"], ["-I"]):
        done = subprocess.run(  # noqa: S603 - this interpreter, this file, fixed arguments
            [sys.executable, *flags, str(RUNNER_FILE), *ARGS],
            env=environment,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        stops[" ".join(flags)] = (done.returncode, json.loads(done.stdout)["reason"])
    assert stops == {
        "-I -B": (4, "DATABASE_URL_MISSING"),
        "-B": (2, "NOT_ISOLATED"),
        "-I": (2, "NOT_ISOLATED"),
    }
    assert sorted(path.name for path in PACKAGE.iterdir()) == sorted(runner.PACKAGE_FILES)


def test_the_runner_is_standalone_and_names_no_table() -> None:
    source = RUNNER_FILE.read_text(encoding="utf-8")
    assert "crypto_probability_engine" not in source
    for word in (
        migration_relations()
        | {"automation_radar_ledger", "predictions"}
        | (denied_names() - DENIED_WORDS)
    ):
        assert not re.search(rf"\b{re.escape(word)}\b", source), word
    assert "print(" not in source


# --------------------------------------------------------------------------- runner mutants
def _behaviour_failures(module: Any) -> list[str]:
    """Every behaviour the runner promises, checked against ``module``; the names that break."""

    failures: list[str] = []

    def check(name: str, probe: Callable[[], bool]) -> None:
        try:
            ok = probe()
        except BaseException:  # noqa: BLE001 - a crashing mutant breaks the behaviour
            ok = False
        if not ok:
            failures.append(name)

    def happy() -> bool:
        connection = FakeConnection(_row(module))
        code, payload, seen, text = _invoke(module, connection)
        return (
            code == 0
            and connection.ended == ["rollback", "close"]
            and [sql for sql, _ in connection.calls][:5]
            == [*module.READ_ONLY_PREAMBLE, module.SESSION_PROOF]
            and seen[0][1]["autocommit"] is False
            and seen[0][1]["connect_timeout"] == 10
            and payload["row_security_off"] is True
            and payload["transaction_read_only"] is True
            and text == json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n"
        )

    def proven(ignored: str) -> Callable[[], bool]:
        def probe() -> bool:
            connection = FakeConnection(_row(module), ignore=(ignored,))
            code, _, _, _ = _invoke(module, connection)
            return code == 4 and SEALED not in [sql for sql, _ in connection.calls]

        return probe

    def database_error() -> bool:
        connection = FakeConnection(_row(module), fail_on="WITH binding")
        code, _, _, text = _invoke(module, connection)
        return code == 4 and URL not in text and connection.ended == ["rollback", "close"]

    def no_url_on_connect_failure() -> bool:
        code, _, _, text = _invoke(module, connect=_refusing_connect)
        return code == 4 and URL not in text

    def sql_seal() -> bool:
        original = module.SQL_PATH
        with tempfile.TemporaryDirectory() as folder:
            tampered = Path(folder) / "a4_card04_companion.sql"
            tampered.write_text(SEALED.replace("'AMBIGUOUS'", "'OK'"), encoding="utf-8")
            module.SQL_PATH = tampered
            try:
                code, _, seen, _ = _invoke(module)
            finally:
                module.SQL_PATH = original
        return code == 3 and seen == []

    def package_seal() -> bool:
        original = module.PACKAGE, module.MANIFEST_PATH
        with tempfile.TemporaryDirectory() as folder:
            copy = Path(folder) / "a4_card04_companion"
            shutil.copytree(PACKAGE, copy, ignore=shutil.ignore_patterns("__pycache__", ".*"))
            (copy / "CARD.md").write_text("edited\n", encoding="utf-8")
            module.PACKAGE, module.MANIFEST_PATH = copy, copy / "MANIFEST.json"
            try:
                code, _, seen, _ = _invoke(module)
            finally:
                module.PACKAGE, module.MANIFEST_PATH = original
        return code == 3 and seen == []

    def refused(args: list[str], secret: str = "SECRET") -> Callable[[], bool]:
        def probe() -> bool:
            code, _, seen, text = _invoke(module, args=args)
            return code == 2 and seen == [] and secret not in text

        return probe

    def cross_check() -> bool:
        lying = FakeConnection(_row(module, deadline_ms=45000))
        code, payload, _, _ = _invoke(module, lying)
        return code == 1 and payload["reason"] == "RUNNER_DISAGREES" and set(payload) == STOP_KEYS

    def disagrees(**lie: Any) -> Callable[[], bool]:
        def probe() -> bool:
            code, payload, _, text = _invoke(module, FakeConnection(_row(module, **lie)))
            return (
                code == 1
                and payload["reason"] == "RUNNER_DISAGREES"
                and set(payload) == STOP_KEYS
                and OTHER_CREDENTIAL not in text
            )

        return probe

    def folder(plant: Callable[[Path], Any]) -> Callable[[], bool]:
        def probe() -> bool:
            original = module.PACKAGE, module.MANIFEST_PATH
            with tempfile.TemporaryDirectory() as root:
                copy = Path(root) / "ops" / "a4_card04_companion"
                shutil.copytree(PACKAGE, copy, ignore=shutil.ignore_patterns("__pycache__", ".*"))
                plant(copy)
                module.PACKAGE, module.MANIFEST_PATH = copy, copy / "MANIFEST.json"
                try:
                    code, _, seen, _ = _invoke(module)
                finally:
                    module.PACKAGE, module.MANIFEST_PATH = original
            return code == 3 and seen == []

        return probe

    def started(isolated: int, no_bytecode: int, expected: int) -> Callable[[], bool]:
        def probe() -> bool:
            connection, out = FakeConnection(_row(module)), io.StringIO()
            code = module.entry(
                ARGS,
                flags=SimpleNamespace(isolated=isolated, dont_write_bytecode=no_bytecode),
                environ={module.DATABASE_URL_ENV: URL},
                connect=lambda url, **_: connection,
                stdout=out,
            )
            return code == expected and (expected == 0 or connection.calls == [])

        return probe

    def shape() -> bool:
        connection = FakeConnection(_row(module), columns=(*runner.SQL_COLUMNS[:-1], "extra"))
        code, payload, _, _ = _invoke(module, connection)
        return code == 4 and payload["reason"] == "UNEXPECTED_RESULT_SHAPE"

    def real_failures() -> bool:
        cases = [
            ("NOT_COMPLETED", dict(analysis_hash=None, analysis_hash_matches=False)),
            ("DEADLINE_MISMATCH", dict(deadline_ms=45000, deadline_ms_matches=False)),
        ]
        return all(
            _invoke(module, FakeConnection(_row(module, verdict="FAIL", reason=reason, **changes)))[
                1
            ]["reason"]
            == reason
            for reason, changes in cases
        )

    for name, probe in [
        ("happy path", happy),
        ("read-only proven", proven("read_only")),
        ("row security proven", proven("row_security")),
        ("database error", database_error),
        ("no URL on connect failure", no_url_on_connect_failure),
        ("SQL seal", sql_seal),
        ("package seal", package_seal),
        ("credential value refused", refused(_args(credential_id="ucpea.u-v-w.THE-SECRET"))),
        ("canonical UUID only", refused(_args(client_request_id=CRID.upper()))),
        ("deadline range", refused(_args(deadline_ms="60001"))),
        ("activation instant", refused(_args(qualification_activation_utc="2026-10-05T00:00:00"))),
        ("unknown arguments", refused(["--token", "ucpea.x-y-z.SECRET"])),
        ("help refused", refused(["-h"])),
        ("repeat refused", refused([*ARGS, "--run-id", RUN])),
        ("abbreviation refused", refused([*ARGS[:-2], "--qualification-activation", ACTIVATION])),
        ("cross-check", cross_check),
        ("bound run checked", disagrees(bound_run_id="run_" + "2" * 32)),
        ("count types checked", disagrees(predictions_rows_for_run_id=True)),
        (
            "request count type checked",
            disagrees(ledger_rows_for_client_request_id_across_all_credentials=True),
        ),
        (
            "a bound row is counted",
            disagrees(ledger_rows_for_client_request_id_across_all_credentials=0),
        ),
        (
            "an ambiguous pair is counted twice",
            disagrees(
                reason="AMBIGUOUS",
                verdict="FAIL",
                deadline_ms=None,
                deadline_ms_matches=False,
                analysis_hash=None,
                analysis_hash_matches=False,
            ),
        ),
        ("result shape", shape),
        ("real failing rows", real_failures),
        (
            "an extra module refused",
            folder(lambda copy: (copy / "json.py").write_text("x = 1\n", encoding="utf-8")),
        ),
        ("a bytecode folder refused", folder(lambda copy: (copy / "__pycache__").mkdir())),
        ("a link refused", folder(lambda copy: _link(copy / "CARD.md"))),
        (
            "a deadline outside the ledger's range never printed",
            disagrees(
                reason="DEADLINE_MISMATCH", verdict="FAIL", deadline_ms=1, deadline_ms_matches=False
            ),
        ),
        (
            "an analysis hash outside the ledger's format never printed",
            disagrees(
                reason="ANALYSIS_HASH_MISMATCH",
                verdict="FAIL",
                analysis_hash=OTHER_CREDENTIAL,
                analysis_hash_matches=False,
            ),
        ),
        ("a start without -I refused", started(0, 1, 2)),
        ("a start without -B refused", started(1, 0, 2)),
        ("a start with -I -B runs", started(1, 1, 0)),
    ]:
        check(name, probe)
    return failures


RUNNER_MUTANTS = {
    "R01 no read-only preamble": ("                begin_read_only(cursor)\n", ""),
    "R02 read-only not proven": ('    if proof is None or proof[0] != "on":', "    if False:"),
    "R03 row security not set": ('    "SET LOCAL row_security = off",\n', ""),
    "R04 row security not proven": ('    if proof[1] != "off":', "    if False:"),
    "R05 no rollback": (
        "    for step in (connection.rollback, connection.close):",
        "    for step in (connection.close,):",
    ),
    "R06 exception message printed": (
        'raise Refusal("DATABASE_ERROR", EXIT_DATABASE, type(exc).__name__) from None',
        'raise Refusal("DATABASE_ERROR", EXIT_DATABASE, f"{type(exc).__name__}: {exc}") from None',
    ),
    "R07 any UUID spelling": (
        "    return str(parsed) == value and parsed.variant == uuid.RFC_4122 and",
        "    return True or",
    ),
    "R08 no cross-check": ("    return all(agreements)", "    return True"),
    "R09 SQL pin not enforced": (
        "    if hashlib.sha256(data).hexdigest() != SQL_SHA256:",
        "    if False:",
    ),
    "R10 package not verified": ("    if not intact:", "    if False:"),
    "R11 unsorted output": (
        "    return json.dumps(payload, sort_keys=True, separators=",
        "    return json.dumps(payload, separators=",
    ),
    "R12 argparse echoes": ("    parser = _Parser(", "    parser = argparse.ArgumentParser("),
    "R13 autocommit session": ("            autocommit=False,\n", "            autocommit=True,\n"),
    "R14 credential unchecked": (
        "    if not CREDENTIAL_ID.fullmatch(credential_id):",
        "    if False:",
    ),
    "R15 result shape unchecked": (
        "    if names != SQL_COLUMNS or len(rows) != 1:",
        "    if False:",
    ),
    "R16 help exits 0": ("add_help=False", "add_help=True"),
    "R17 deadline range unchecked": (
        "DEADLINE_MS_MIN <= int(deadline_ms) <= DEADLINE_MS_MAX",
        "True",
    ),
    "R18 activation unchecked": ("    if not _canonical_utc(activation_utc):", "    if False:"),
    "R19 repeats accepted": (
        "        if getattr(namespace, self.dest) is not None:",
        "        if False:",
    ),
    "R20 abbreviations accepted": ("allow_abbrev=False", "allow_abbrev=True"),
    "R21 bound run unchecked": ('        facts["bound_run_id"] == binding.run_id,\n', ""),
    "R22 count types unchecked": (
        "    return type(value) is int and value >= 0",
        "    return True",
    ),
    "R23 no connect timeout": ("            connect_timeout=CONNECT_TIMEOUT_SECONDS,\n", ""),
    "R24 request count's type unchecked": (
        "    request_rows_valid = _count(request_rows)",
        "    request_rows_valid = True",
    ),
    "R25 a bound row may count no request row": (
        'position <= REASONS.index("AMBIGUOUS") or (request_rows_valid and request_rows >= 1)',
        "True",
    ),
    "R26 an ambiguous pair may count one request row": (
        'reason != "AMBIGUOUS" or (request_rows_valid and request_rows >= 2)',
        "True",
    ),
    "R27 other files accepted": ("    if not exact:", "    if False:"),
    "R28 links followed": ("entry.is_file(follow_symlinks=False)", "entry.is_file()"),
    "R29 any deadline printed": ("        _ledger_deadline(deadline),\n", ""),
    "R30 any analysis hash printed": ("        _ledger_hash(analysis_hash),\n", ""),
    "R31 a disagreement prints the answer": (
        'return {**base, "verdict": "FAIL", "reason": "RUNNER_DISAGREES"}, EXIT_FAIL',
        'return {**base, **facts, "verdict": "FAIL", "reason": "RUNNER_DISAGREES"}, EXIT_FAIL',
    ),
    "R32 a start without -I runs": (
        "    if not (flags.isolated and flags.dont_write_bytecode):",
        "    if not flags.dont_write_bytecode:",
    ),
    "R33 a start without -B runs": (
        "    if not (flags.isolated and flags.dont_write_bytecode):",
        "    if not flags.isolated:",
    ),
}
RUNNER_SOURCE = RUNNER_FILE.read_text(encoding="utf-8")


def test_the_behaviour_battery_passes_the_real_runner() -> None:
    assert _behaviour_failures(_module("a4c_runner_real", RUNNER_FILE, RUNNER_SOURCE)) == []


@pytest.mark.parametrize("name", sorted(RUNNER_MUTANTS))
def test_every_runner_mutant_breaks_a_behaviour(name: str) -> None:
    old, new = RUNNER_MUTANTS[name]
    assert RUNNER_SOURCE.count(old) >= 1, name
    mutant = _module(f"a4c_runner_{name[:3]}", RUNNER_FILE, RUNNER_SOURCE.replace(old, new))
    assert _behaviour_failures(mutant), name


# --------------------------------------------------------------------------- seal and handoff
FIELDS = (
    "COMPANION_STATUS",
    "ARTIFACT_NAME",
    "ARTIFACT_SHA256",
    "SOURCE_COMMIT",
    "UPSTREAM_RELEASE_IDENTITY",
    "INPUT_BINDING",
    "OUTPUT_CONTRACT",
    "DEADLINE_MS_PROOF",
    "ANALYSIS_HASH_PROOF",
    "PREDICTIONS_RUN_ID_COUNT_PROOF",
    "CREDENTIAL_ROWS_SINCE_ACTIVATION_PROOF",
    "READ_ONLY_PROOF",
    "ISOLATION_PROOF",
    "TESTS",
    "INDEPENDENT_REVIEW",
    "PRODUCTION_QUERY_EXECUTED",
    "PRODUCTION_MUTATED",
    "PROTECTED_5A_ACCESSED",
    "PACKAGE_PATH",
)


def test_the_manifest_seals_every_package_file() -> None:
    built = _module("a4c_manifest", PACKAGE / "build_manifest.py").manifest()
    assert (
        MANIFEST.read_text(encoding="utf-8") == json.dumps(built, indent=1, sort_keys=True) + "\n"
    )
    assert set(built["files"]) == {f"ops/a4_card04_companion/{name}" for name in SEALED_FILES}
    # The folder holds exactly its five files, each a regular file: no test writes bytecode here.
    assert sorted(path.name for path in PACKAGE.iterdir()) == sorted(
        [*SEALED_FILES, "MANIFEST.json"]
    )
    assert all(path.is_file() and not path.is_symlink() for path in PACKAGE.iterdir())
    assert built["package_files"] == sorted(runner.PACKAGE_FILES) == sorted(os.listdir(PACKAGE))
    assert built["invocation"] == "python -I -B ops/a4_card04_companion/a4_card04_companion.py"
    assert sorted(built["counts"]) == sorted(
        [
            "predictions_rows_for_run_id",
            "credential_ledger_rows_since_activation",
            "ledger_rows_for_client_request_id_across_all_credentials",
        ]
    )
    for path, digest in built["schema_sources"].items():
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == digest
    assert built["reads"]["public.automation_radar_ledger"] == sorted(DATA_COLUMNS[LEDGER])
    assert built["reads"]["public.predictions"] == ["run_id"]
    assert {f"pg_catalog.{name}" for name in built["reads"]["pg_catalog"]} == CATALOGS
    assert built["reasons"] == list(runner.REASONS)


def test_the_accepted_a4_component_is_unchanged() -> None:
    assert hashlib.sha256(A4_MANIFEST.read_bytes()).hexdigest() == A4_ARTIFACT_SHA256
    companion_of = json.loads(MANIFEST.read_text(encoding="utf-8"))["companion_of"]
    assert companion_of == {
        "artifact": "ucpe.a4_ledger_audit.v1",
        "artifact_sha256": A4_ARTIFACT_SHA256,
        "source_commit": A4_SOURCE_COMMIT,
    }


def _section_fields(heading: str) -> dict[str, str]:
    section = HANDOFF.read_text(encoding="utf-8").split(heading, 1)[1]
    block = section.split("```text\n", 1)[1].split("```", 1)[0]
    return dict(line.split("=", 1) for line in block.strip().splitlines())


def test_the_handoff_carries_exactly_the_companion_fields_and_the_seal() -> None:
    text = HANDOFF.read_text(encoding="utf-8")
    section = text.split("## 15. Card 04 companion", 1)[1]
    block = section.split("```text\n", 1)[1].split("```", 1)[0]
    lines = block.strip().splitlines()
    assert [line.split("=", 1)[0] for line in lines] == list(FIELDS)
    values = _section_fields("## 15. Card 04 companion")
    assert all(values.values())
    assert values["COMPANION_STATUS"].startswith("PREPARED_AND_VERIFIED")
    assert values["ARTIFACT_NAME"] == runner.ARTIFACT
    assert values["ARTIFACT_SHA256"] == hashlib.sha256(MANIFEST.read_bytes()).hexdigest()
    assert values["PRODUCTION_QUERY_EXECUTED"] == "NO"
    assert values["PRODUCTION_MUTATED"] == "NO"
    assert values["PROTECTED_5A_ACCESSED"] == "NO"
    assert values["PACKAGE_PATH"] == "ops/a4_card04_companion/"
    for name in ("MANIFEST.json", *SEALED_FILES):
        assert f"| `ops/a4_card04_companion/{name}` |" in section, name


def test_the_companion_output_contract_names_exactly_the_keys_the_runner_prints() -> None:
    contract = _section_fields("## 15. Card 04 companion")["OUTPUT_CONTRACT"]
    listed = contract.split("exactly these 19 keys: ", 1)[1].split(";", 1)[0].split(", ")
    printed = sorted(_run()[1])
    assert (
        sorted(listed) == printed == json.loads(MANIFEST.read_text(encoding="utf-8"))["output_keys"]
    )
    # The stop lines it names: a disagreement prints the stop keys only, and a start without -I -B
    # is refused.
    stop = contract.split("a runner stop", 1)[1]
    for key in sorted(STOP_KEYS - {"verdict", "reason"}):
        assert key in stop, key
    assert "RUNNER_DISAGREES" in stop and "NOT_ISOLATED" in stop
    assert runner.INVOCATION in HANDOFF.read_text(encoding="utf-8").split("## 15. ", 1)[1]


def test_the_a4_output_contract_names_every_key_of_the_a4_audited_line() -> None:
    """The 2026-10-05 correction of section 14: the A4 runner's audited line also carries
    ``audit``. Only the audited line's keys are checked here: section 14 does not name the A4
    runner's error_class (recorded in STATE; section 14 is the accepted component's handoff)."""

    contract = _section_fields("## 14. A4 per-request ledger audit")["OUTPUT_CONTRACT"]
    for key in json.loads(A4_MANIFEST.read_text(encoding="utf-8"))["output_keys"]:
        assert re.search(rf"(?<![A-Za-z_]){re.escape(key)}(?![A-Za-z_])", contract), key
    review = _section_fields("## 14. A4 per-request ledger audit")["INDEPENDENT_REVIEW"]
    assert "dbc5c47" in review and "491b460" in review
    assert "3ba2486" not in review and "dd1093a" not in review
