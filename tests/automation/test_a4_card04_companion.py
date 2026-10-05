"""ucpe.a4_card04_companion.v1 (ops/a4_card04_companion): the sealed read-only companion of
ucpe.a4_ledger_audit.v1 for UOR Card 04.

What these tests prove without a database (the scratch-PostgreSQL 17.6 rehearsal proves the rest):
- the sealed SQL passes a structural guard whose model of SQL is closed, so it refuses whatever it
  does not model: printable ASCII only; standard literals only (no backslash, prefixed literal,
  dollar quote, quoted identifier or block comment); only the modelled operators, keywords, types
  and functions, and every other identifier a declared name; one SELECT, with no write, locking,
  TABLE or SET clause, comma-join or derived table; no relation but the ledger, public.predictions
  and five catalogs, each through an alias, and exactly the declared reads (each relation's uses,
  every data column reference); from the ledger ten columns, from predictions only run_id, from the
  catalogs only the listed columns; no star but count(*) and the decision's k.*, and no whole-row
  use of any table, alias or CTE; the decision branches in the declared order, judging no count;
- adversarial mutants that widen a read, read a probability, the body, a whole row (directly, with a
  star, through a CTE or a derived table), the registry, another table or more than the declared
  reads, hide a read in an escape string or a non-ASCII name, use an unmodelled operator, type,
  keyword or identifier, drop or reorder a check, bind on client_request_id alone, judge a count,
  move the count window, add an output, drop the inheritance check, lock or write, all fail it;
- the expected columns are migration 0013's and 0003's declarations, no later migration changes
  them, and the route still writes each fact where the companion reads it;
- the runner checks the package against its seal and the SQL against its pin, runs it only in a READ
  ONLY transaction with row security off that it always rolls back, refuses bad inputs before
  contacting anything, never prints a URL, a credential value or an exception message, and
  cross-checks the SQL's answer; every runner mutant breaks one of those behaviours;
- the manifest seals every package file; UOR_HANDOFF.md section 15 carries exactly the companion
  fields, the seal's digest and the keys the runner really prints; the accepted A4 component's seal
  is unchanged and section 14's corrected contract names every key of the A4 audited line.
"""

from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import re
import shutil
import sys
import tempfile
from collections import Counter
from collections.abc import Callable
from pathlib import Path
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
    """Load a module from its file, or from mutated source standing in for that file."""

    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    if source is None:
        spec.loader.exec_module(module)
    else:
        exec(compile(source, str(path), "exec"), module.__dict__)  # noqa: S102 - test mutants
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
REQUIRED_FRAGMENTS = [
    "FROM public.automation_radar_ledger AS l JOIN binding AS b "
    "ON l.credential_id = b.credential_id AND l.client_request_id = b.client_request_id )",
    "FROM public.predictions AS p JOIN binding AS b ON p.run_id = b.expected_run_id )",
    "FROM public.automation_radar_ledger AS w JOIN binding AS b "
    "ON w.credential_id = b.credential_id AND w.received_at_utc >= b.activation_utc )",
    "WHERE n.nspname = 'public'",
    "AND c.relkind = 'r'",
    "AND NOT EXISTS (SELECT 1 FROM pg_catalog.pg_inherits AS i JOIN relations AS h "
    "ON h.oid = i.inhparent)",
    "(s.schema_ok IS TRUE) AS schema_ok",
    "(f.run_id IS NOT DISTINCT FROM b.expected_run_id) AS run_id_matches",
    "(f.deadline_ms IS NOT DISTINCT FROM b.expected_deadline_ms) AS deadline_ms_matches",
    "(f.analysis_hash IS NOT DISTINCT FROM b.expected_analysis_hash) AS analysis_hash_matches",
    "(f.received_at_utc >= b.activation_utc) AS activation_not_after_request",
    "CASE WHEN d.reason = 'OK' THEN 'PASS' ELSE 'FAIL' END AS verdict",
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
# The declared minimum, exactly: how often each relation is read, and every data column reference.
# predictions.run_id is read once, in the count's join; the ledger twice, for the bound row and the
# credential's window.
RELATION_USES = {
    LEDGER: 2,
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


def _normalized(kept: str) -> str:
    return " ".join(kept.split()).replace("( ", "(").replace(" )", ")")


def final_columns(sql: str) -> tuple[str, ...]:
    """The output names of the final SELECT, in order."""

    normalized = _normalized(_strip_comments(sql)[0])
    final = normalized.rsplit(") SELECT ", 1)[-1].split(" FROM decision AS d", 1)[0]
    return tuple(item.split(" AS ")[-1].split(".")[-1] for item in final.split(", "))


def guard_violations(sql: str) -> list[str]:
    violations: list[str] = []
    kept, masked, literals, problems = _strip_comments(sql)
    violations += problems
    tokens = TOKEN.findall(masked)
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
                    declared.update(lower[back + 1 : index])
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
    found = [token for token in tokens if token.startswith("%(")]
    if sorted(found) != sorted(PLACEHOLDERS):
        violations.append(f"placeholders {found}")
    if sql.count("%") != len(PLACEHOLDERS):  # psycopg reads every %, even in a comment
        violations.append("a stray %")
    normalized = _normalized(kept)
    for fragment in REQUIRED_FRAGMENTS:
        if fragment.replace("( ", "(").replace(" )", ")") not in normalized:
            violations.append(f"missing: {fragment[:60]}")
    decision = normalized.split("decision AS (", 1)[-1].split(") SELECT ", 1)[0]
    positions = [decision.find(branch) for branch in DECISION_ORDER]
    if -1 in positions or positions != sorted(positions):
        violations.append("the decision branches are missing or out of order")
    if set(re.findall(r"THEN '([A-Z_]+)'", decision)) != set(runner.REASONS) - {"OK"}:
        violations.append("the decision judges something else (a count?)")
    if normalized.count("'OK'") != 2:
        violations.append("OK must be reachable only through ELSE")
    if final_columns(sql) != runner.SQL_COLUMNS:
        violations.append("the output columns are not the declared ones")
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
T_WINDOW = (
    "        ON w.credential_id = b.credential_id\n"
    "       AND w.received_at_utc >= b.activation_utc\n"
)
T_TARGET = "    SELECT l.evidence_origin,\n"
MUTANTS = {
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
        "       d.credential_ledger_rows_since_activation\n",
        "       d.credential_ledger_rows_since_activation,\n"
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
    "adds an input": (
        "CAST(%(credential_id)s AS text)",
        "CAST(%(credential_id)s || %(x)s AS text)",
    ),
}


@pytest.mark.parametrize("name", sorted(MUTANTS))
def test_every_adversarial_mutant_fails_the_guard(name: str) -> None:
    old, new = MUTANTS[name]
    assert SEALED.count(old) == 1, name
    assert guard_violations(SEALED.replace(old, new)), name


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
    )
    facts.update(changes)
    return facts


def _row(module: Any = None, **changes: Any) -> tuple[Any, ...]:
    facts = _facts(module, **changes)
    return tuple(facts[name] for name in runner.SQL_COLUMNS)


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
    assert len(payload) == 18 and "response_body" not in text


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
        dict(credential_ledger_rows_since_activation=True),
        dict(reason="SOMETHING_ELSE", verdict="FAIL"),
        dict(reason="RUN_MISMATCH"),  # a FAIL reason with a PASS verdict
        dict(reason="SCHEMA_DRIFT", verdict="FAIL"),  # drift while the schema is fine
        dict(reason="NO_ROW", verdict="FAIL"),  # no row, yet a deadline and a hash
        dict(reason="ANALYSIS_HASH_MISMATCH", verdict="FAIL"),  # yet the hash matches
        dict(bound_run_id="run_" + "2" * 32),
        dict(artifact="ucpe.something_else.v1"),
    ],
)
def test_an_answer_the_runner_cannot_reproduce_is_refused(lie: dict[str, Any]) -> None:
    code, payload, _, _ = _run(FakeConnection(_row(**lie)))
    assert code == 1 and payload["reason"] == "RUNNER_DISAGREES" and payload["verdict"] == "FAIL"


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
        return code == 1 and payload["reason"] == "RUNNER_DISAGREES"

    def disagrees(**lie: Any) -> Callable[[], bool]:
        def probe() -> bool:
            code, payload, _, _ = _invoke(module, FakeConnection(_row(module, **lie)))
            return code == 1 and payload["reason"] == "RUNNER_DISAGREES"

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
        ("result shape", shape),
        ("real failing rows", real_failures),
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
    assert {
        path.name for path in PACKAGE.iterdir() if path.is_file() and not path.name.startswith(".")
    } == {*SEALED_FILES, "MANIFEST.json"}
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
    listed = contract.split("exactly these 18 keys: ", 1)[1].split(";", 1)[0].split(", ")
    printed = sorted(_run()[1])
    assert (
        sorted(listed) == printed == json.loads(MANIFEST.read_text(encoding="utf-8"))["output_keys"]
    )


def test_the_a4_output_contract_names_every_key_of_the_a4_audited_line() -> None:
    """The 2026-10-05 correction of section 14: the A4 runner's audited line also carries
    ``audit``. A runner stop's keys are in the contract's prose, not in this list."""

    contract = _section_fields("## 14. A4 per-request ledger audit")["OUTPUT_CONTRACT"]
    for key in json.loads(A4_MANIFEST.read_text(encoding="utf-8"))["output_keys"]:
        assert re.search(rf"(?<![A-Za-z_]){re.escape(key)}(?![A-Za-z_])", contract), key
    review = _section_fields("## 14. A4 per-request ledger audit")["INDEPENDENT_REVIEW"]
    assert "dbc5c47" in review and "491b460" in review
    assert "3ba2486" not in review and "dd1093a" not in review
