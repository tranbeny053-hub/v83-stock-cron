"""ucpe.a4_ledger_audit.v1 (ops/a4_ledger_audit): the sealed read-only A4 per-request ledger audit.

What these tests prove without a database (the scratch-PostgreSQL rehearsal proves the rest in CI):
- the sealed SQL passes a structural guard: one SELECT, no write, locking or TABLE clause, no
  comma-join, no function outside an allowlist, no unqualified catalog name, and no application
  table but public.automation_radar_ledger, nor any table, view or function another migration
  creates; its decision branches are in the declared order;
- adversarial mutants that widen scope, read a cohort, registry or catalog table, drop or reorder
  an AUTOMATED_RADAR check, bind on client_request_id alone, drop the ambiguity or schema-drift
  branch, select the stored body, or write, all fail that guard;
- the expected schema in the SQL is exactly migration 0013's table, and no later migration
  changes its columns;
- the runner pins the SQL, runs it only in a READ ONLY transaction it always rolls back, refuses
  bad inputs before contacting anything, never prints a URL, a credential value or an exception
  message, and cross-checks the SQL's decision independently; every runner mutant breaks one of
  those behaviours;
- the manifest seals every package file, and UOR_HANDOFF.md section 14 carries exactly the A4
  fields with the seal's digest.
"""

from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import re
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "ops" / "a4_ledger_audit"
SQL_FILE = PACKAGE / "a4_ledger_audit.sql"
RUNNER_FILE = PACKAGE / "a4_ledger_audit.py"
MIGRATION_0013 = ROOT / "migrations" / "0013_automation_radar_ledger.sql"


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


runner = _module("a4_ledger_audit_runner", RUNNER_FILE)
SEALED = SQL_FILE.read_text(encoding="utf-8")

CRED = "uor-radar-2026-10"
CRID = "3e8ca8f0-5016-4e45-9ea1-0aedbe815260"
RUN = "run_d33406cea53648829428b829198577d3"
REL = "UCPE-PROD-E2-20261004-A"
EVH = "sha256:58191ef5c11e12eaadbddc6b5289eecbf0d56fd18999074c6576dd0d8a9ba846"
URL = "postgresql://a4_user:NOT-A-REAL-PASSWORD@db.invalid:5432/postgres"

# --------------------------------------------------------------------------- the structural guard
ALLOWED_QUALIFIED = {
    "public.automation_radar_ledger",
    "pg_catalog.pg_class",
    "pg_catalog.pg_namespace",
    "pg_catalog.pg_attribute",
    "pg_catalog.pg_constraint",
    "pg_catalog.format_type",
}
SCHEMAS = {
    "public", "pg_catalog", "information_schema", "pg_toast", "auth", "storage", "extensions",
    "realtime", "vault", "graphql", "graphql_public", "cron", "net", "pgsodium",
    "supabase_functions",
}
CTES = {
    "binding", "ledger_table", "expected_columns", "live_columns", "primary_key", "schema_check",
    "hits", "row_facts", "checks", "decision",
}
FUNCTIONS = {"count", "min", "array_agg", "pg_catalog.format_type"}
PAREN_KEYWORDS = {
    "AS", "AND", "OR", "NOT", "ON", "WHERE", "IN", "THEN", "WHEN", "ELSE", "SELECT", "FROM",
    "JOIN", "EXISTS", "VALUES", "ANY", "CAST",
}
FORBIDDEN_KEYWORDS = {
    "INSERT", "UPDATE", "DELETE", "MERGE", "TRUNCATE", "COPY", "CALL", "DO", "SET", "RESET",
    "LOCK", "GRANT", "REVOKE", "CREATE", "ALTER", "DROP", "COMMENT", "VACUUM", "ANALYZE",
    "REFRESH", "NOTIFY", "LISTEN", "UNLISTEN", "PREPARE", "EXECUTE", "DEALLOCATE", "DISCARD",
    "INTO", "FOR", "RETURNING", "BEGIN", "COMMIT", "ROLLBACK", "SAVEPOINT", "CHECKPOINT",
    "CLUSTER", "REINDEX", "SECURITY", "IMPORT", "LOAD", "RECURSIVE", "LATERAL", "TABLESAMPLE",
    "TABLE",
}
DENIED_WORDS = {
    "automation_credential", "secret_sha256", "predictions", "prediction_outcomes", "analysis_runs",
    "snapshot", "section_5a", "pg_read_file", "pg_sleep", "dblink", "query_to_xml", "lo_import",
    "set_config", "pg_advisory", "nextval", "setval",
}
PLACEHOLDERS = [
    "%(credential_id)s", "%(client_request_id)s", "%(expected_run_id)s",
    "%(expected_release_id)s", "%(expected_evidence_hash)s",
]
REQUIRED_FRAGMENTS = [
    "FROM public.automation_radar_ledger AS l JOIN binding AS b "
    "ON l.credential_id = b.credential_id AND l.client_request_id = b.client_request_id )",
    "(r.evidence_origin IS NOT DISTINCT FROM 'AUTOMATED_RADAR' AND r.body_evidence_origin IS NOT "
    "DISTINCT FROM 'AUTOMATED_RADAR') AS origin_automated_radar",
    "(s.schema_ok IS TRUE) AS schema_ok",
    "CASE WHEN d.reason = 'OK' THEN 'PASS' ELSE 'FAIL' END AS verdict",
]
# The decision, branch by branch, in the order it must run. In-progress and refused rows have no
# body origin, so the body's origin is judged only after the state and the outcome.
DECISION_ORDER = [
    "WHEN k.schema_ok IS NOT TRUE THEN 'SCHEMA_DRIFT'",
    "WHEN k.matched_rows = 0 THEN 'NO_ROW'",
    "WHEN k.matched_rows <> 1 THEN 'AMBIGUOUS'",
    "WHEN k.evidence_origin IS DISTINCT FROM 'AUTOMATED_RADAR' THEN 'WRONG_ORIGIN'",
    "WHEN k.state IS DISTINCT FROM 'COMPLETED' THEN 'NOT_COMPLETED'",
    "WHEN k.outcome_code IS DISTINCT FROM 'SUCCEEDED' OR k.http_status IS DISTINCT FROM 200 THEN "
    "'NOT_SUCCEEDED'",
    "WHEN k.origin_automated_radar IS NOT TRUE THEN 'WRONG_ORIGIN'",
    "WHEN k.body_identity_consistent IS NOT TRUE THEN 'BODY_IDENTITY_MISMATCH'",
    "WHEN k.run_id_matches IS NOT TRUE THEN 'RUN_MISMATCH'",
    "WHEN k.release_id_matches IS NOT TRUE THEN 'RELEASE_MISMATCH'",
    "WHEN k.evidence_hash_matches IS NOT TRUE THEN 'EVIDENCE_MISMATCH'",
    "ELSE 'OK' END AS reason",
]
TOKEN = re.compile(
    r"%\(\w+\)s|[A-Za-z_][A-Za-z0-9_$]*(?:\.[A-Za-z_][A-Za-z0-9_$]*)*|->>|->|<>|::|\d+|\S"
)


def _strip_comments(sql: str) -> tuple[str, str, list[str], list[str]]:
    """(code without comments, the same with literals masked, the literals, the problems)."""

    kept: list[str] = []
    masked: list[str] = []
    literals: list[str] = []
    problems: list[str] = []
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
            masked.append("'?'")
            i = end + 1
            continue
        kept.append(char)
        masked.append(char)
        i += 1
    return "".join(kept), "".join(masked), literals, problems


def migration_relations() -> set[str]:
    names: set[str] = set()
    pattern = re.compile(
        r"CREATE\s+(?:OR\s+REPLACE\s+)?(?:TABLE|VIEW|MATERIALIZED\s+VIEW|FUNCTION)\s+"
        r"(?:IF\s+NOT\s+EXISTS\s+)?(?:public\.)?([a-z_][a-z0-9_]*)",
        re.IGNORECASE,
    )
    for path in sorted((ROOT / "migrations").glob("*.sql")):
        names.update(match.lower() for match in pattern.findall(path.read_text(encoding="utf-8")))
    return names - {"automation_radar_ledger"}


FROM_LIST_ENDS = {"WHERE", "GROUP", "HAVING", "ORDER", "LIMIT", "OFFSET", "UNION", "EXCEPT",
                  "INTERSECT", "WINDOW"}


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


def guard_violations(sql: str) -> list[str]:
    violations: list[str] = []
    kept, masked, literals, problems = _strip_comments(sql)
    violations += problems
    tokens = TOKEN.findall(masked)
    upper = [token.upper() for token in tokens]
    if ";" in tokens:
        violations.append("more than one statement")
    if not upper or upper[0] != "WITH":
        violations.append("not a single WITH ... SELECT")
    for token in upper:
        if token in FORBIDDEN_KEYWORDS:
            violations.append(f"forbidden keyword {token}")
    denied = migration_relations() | DENIED_WORDS
    for word in [*tokens, *literals]:
        for part in re.split(r"[^a-z0-9_]+", word.lower()):
            if part in denied or any(part.startswith(d) for d in ("pg_advisory", "section_5a")):
                violations.append(f"denied name {part}")
    ctes = set()
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
                    break
        if name_at >= 0 and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", tokens[name_at]):
            ctes.add(tokens[name_at].lower())
    if ctes != CTES:
        violations.append(f"unexpected CTE set {sorted(ctes ^ CTES)}")
    aliases: set[str] = set()
    for index, token in enumerate(upper):
        if token in {"FROM", "JOIN"} and index + 1 < len(tokens):
            if token == "FROM" and index > 0 and upper[index - 1] == "DISTINCT":
                continue  # IS [NOT] DISTINCT FROM: a comparison, not a relation
            relation = tokens[index + 1]
            if relation != "(" and relation.lower() not in ALLOWED_QUALIFIED | CTES:
                violations.append(f"relation {relation}")
            if relation != "(" and index + 3 < len(tokens) and upper[index + 2] == "AS":
                aliases.add(tokens[index + 3].lower())
            if token == "FROM" and _comma_in_from_list(tokens, upper, index):
                violations.append("a comma-join: every relation needs its own JOIN")
    for index, token in enumerate(tokens):
        if re.match(r"[A-Za-z_]", token):
            if "." in token:
                head = token.split(".", 1)[0].lower()
                if head in SCHEMAS:
                    if token.lower() not in ALLOWED_QUALIFIED:
                        violations.append(f"qualified name {token}")
                elif head not in aliases:
                    violations.append(f"undeclared alias {token}")
            elif token.lower().startswith("pg_"):
                violations.append(f"unqualified catalog name {token}")
        if index + 1 < len(tokens) and tokens[index + 1] == "(" and re.match(r"[A-Za-z_]", token):
            if (token.lower() not in FUNCTIONS and token.upper() not in PAREN_KEYWORDS
                    and token.lower() not in CTES):
                violations.append(f"function {token}")
        if token.lower().endswith("response_body") and (
            index + 1 >= len(tokens) or tokens[index + 1] not in {"->", "->>"}
        ):
            violations.append("the stored body is selected, not one of its identity keys")
    found = [token for token in tokens if token.startswith("%(")]
    if sorted(found) != sorted(PLACEHOLDERS):
        violations.append(f"placeholders {found}")
    normalized = " ".join(kept.split()).replace("( ", "(").replace(" )", ")")
    for fragment in REQUIRED_FRAGMENTS:
        if fragment.replace("( ", "(").replace(" )", ")") not in normalized:
            violations.append(f"missing: {fragment[:60]}")
    decision = normalized.split("decision AS (", 1)[-1]
    positions = [decision.find(branch) for branch in DECISION_ORDER]
    if -1 in positions or positions != sorted(positions):
        violations.append("the decision branches are missing or out of order")
    if normalized.count("'OK'") != 2:
        violations.append("OK must be reachable only through ELSE")
    return violations


def test_the_sealed_sql_passes_the_structural_guard() -> None:
    assert guard_violations(SEALED) == []


def test_the_runner_pins_the_sealed_sql() -> None:
    assert runner.SQL_SHA256 == hashlib.sha256(SQL_FILE.read_bytes()).hexdigest()
    assert runner.SQL_PATH == SQL_FILE.resolve()


MUTANTS = {
    "joins the predictions cohort": (
        "      FROM public.automation_radar_ledger AS l\n",
        "      FROM public.automation_radar_ledger AS l\n"
        "      JOIN public.predictions AS p ON p.run_id = l.run_id\n",
    ),
    "reads the credential registry": (
        "           l.release_id,\n",
        "           l.release_id,\n"
        "           (SELECT min(x.secret_sha256)\n"
        "              FROM public.automation_credential AS x) AS leak,\n",
    ),
    "binds on client_request_id alone": (
        "        ON l.credential_id = b.credential_id\n       AND l.client_request_id",
        "        ON l.client_request_id",
    ),
    "drops the row origin check": (
        "(r.evidence_origin IS NOT DISTINCT FROM 'AUTOMATED_RADAR'\n",
        "(true\n",
    ),
    "drops the body origin check": (
        "            AND r.body_evidence_origin IS NOT DISTINCT FROM 'AUTOMATED_RADAR')",
        "            AND true)",
    ),
    "drops the row-origin branch": (
        "               WHEN k.evidence_origin IS DISTINCT FROM 'AUTOMATED_RADAR' THEN "
        "'WRONG_ORIGIN'\n",
        "",
    ),
    "judges the body origin before the outcome": (
        "               WHEN k.evidence_origin IS DISTINCT FROM 'AUTOMATED_RADAR' THEN "
        "'WRONG_ORIGIN'\n",
        "               WHEN k.origin_automated_radar IS NOT TRUE THEN 'WRONG_ORIGIN'\n",
    ),
    "drops the ambiguity branch": (
        "               WHEN k.matched_rows <> 1 THEN 'AMBIGUOUS'\n", ""
    ),
    "drops the schema-drift branch": (
        "               WHEN k.schema_ok IS NOT TRUE THEN 'SCHEMA_DRIFT'\n", ""
    ),
    "makes the drift check NULL-unsafe": (
        "WHEN k.schema_ok IS NOT TRUE THEN", "WHEN NOT k.schema_ok THEN"
    ),
    "selects the stored body": (
        "           l.evidence_hash,\n",
        "           l.evidence_hash,\n           l.response_body,\n",
    ),
    "locks the row": ("  FROM decision AS d\n", "  FROM decision AS d\n FOR UPDATE\n"),
    "deletes in a CTE": (
        "WITH binding AS (\n",
        "WITH gone AS (DELETE FROM public.automation_radar_ledger RETURNING 1),\nbinding AS (\n",
    ),
    "runs a second statement": ("  FROM decision AS d\n", "  FROM decision AS d;\nSELECT 1\n"),
    "calls a side-effect function": (
        "SELECT count(*) AS matched_rows,",
        "SELECT count(*) AS matched_rows, pg_catalog.pg_sleep(0) AS nap,",
    ),
    "changes a setting": (
        "SELECT count(*) AS matched_rows,",
        "SELECT count(*) AS matched_rows, pg_catalog.set_config('search_path', '', true) AS sp,",
    ),
    "reads information_schema": (
        "      FROM pg_catalog.pg_class AS c\n", "      FROM information_schema.tables AS c\n"
    ),
    "comma-joins a catalog view": (
        "      FROM pg_catalog.pg_class AS c\n",
        "      FROM pg_catalog.pg_class AS c, pg_stat_activity AS z\n",
    ),
    "comma-joins after an ON condition": (
        "      JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace\n",
        "      JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace, other_relation\n",
    ),
    "reads a catalog with TABLE": (
        "SELECT count(*) AS matched_rows,",
        "SELECT (SELECT count(*) FROM (TABLE pg_authid) AS z) AS roles, count(*) AS matched_rows,",
    ),
    "adds an input": (
        "CAST(%(credential_id)s AS text)", "CAST(%(credential_id)s || %(x)s AS text)"
    ),
    "reaches OK another way": (
        "WHEN k.matched_rows = 0 THEN 'NO_ROW'", "WHEN k.matched_rows = 0 THEN 'OK'"
    ),
    "reads another table through a new CTE": (
        "decision AS (\n", "other AS (SELECT 1 FROM public.analysis_runs),\ndecision AS (\n"
    ),
}


@pytest.mark.parametrize("name", sorted(MUTANTS))
def test_every_adversarial_mutant_fails_the_guard(name: str) -> None:
    old, new = MUTANTS[name]
    assert SEALED.count(old) == 1, name
    assert guard_violations(SEALED.replace(old, new)), name


# --------------------------------------------------------------------------- schema proof
TYPES = {"TEXT": "text", "UUID": "uuid", "INTEGER": "integer", "JSONB": "jsonb",
         "TIMESTAMPTZ": "timestamp with time zone"}


def migration_columns() -> tuple[list[tuple[str, str, bool]], list[str]]:
    text = MIGRATION_0013.read_text(encoding="utf-8")
    block = text.split("CREATE TABLE IF NOT EXISTS public.automation_radar_ledger (", 1)[1]
    block = block.split("\n);", 1)[0]
    columns = []
    for line in block.splitlines():
        match = re.match(r"\s{4}([a-z_]+)\s+(TEXT|UUID|INTEGER|JSONB|TIMESTAMPTZ)\b(.*)$", line)
        if match:
            columns.append((match[1], TYPES[match[2]], "NOT NULL" in match[3]))
    key = re.search(r"CONSTRAINT automation_radar_ledger_pkey PRIMARY KEY \(([^)]*)\)", block)
    assert key
    return columns, [part.strip() for part in key[1].split(",")]


def test_the_expected_schema_is_migration_0013s_table() -> None:
    columns, key = migration_columns()
    expected = [(m[0], m[1], m[2] == "true") for m in re.findall(
        r"\('([a-z_]+)', '([a-z ]+)', (true|false)\)", SEALED)]
    assert expected == columns and len(columns) == 15
    assert sorted(key) == ["client_request_id", "credential_id"]
    assert "= ARRAY['client_request_id', 'credential_id']" in SEALED


def test_no_later_migration_changes_the_ledger_columns() -> None:
    changes = re.compile(
        r"(ALTER\s+TABLE\s+(?:IF\s+EXISTS\s+)?(?:ONLY\s+)?public\.automation_radar_ledger\s+"
        r"(?:ADD|DROP|ALTER|RENAME))|(DROP\s+TABLE[^;]*automation_radar_ledger)",
        re.IGNORECASE,
    )
    for path in sorted((ROOT / "migrations").glob("*.sql")):
        if path.name[:4] > "0013":
            assert not changes.search(path.read_text(encoding="utf-8")), path.name


def test_the_runner_columns_and_reasons_are_the_sqls() -> None:
    final = SEALED.rsplit("\nSELECT ", 1)[1].split("\n  FROM decision AS d", 1)[0]
    names = [item.strip().split(" AS ")[-1].split(".")[-1] for item in final.split(",\n")]
    assert tuple(names) == runner.SQL_COLUMNS
    decision = SEALED.split("decision AS (", 1)[1].split("\nSELECT 'ucpe", 1)[0]
    assert set(re.findall(r"THEN '([A-Z_]+)'", decision)) == set(runner.REASONS) - {"OK"}
    assert decision.count("ELSE 'OK'") == 1


# --------------------------------------------------------------------------- the runner, offline
FAILED_ROW = dict(
    evidence_origin=None, origin_automated_radar=False, state=None, outcome_code=None,
    http_status=None, run_id=None, run_id_matches=False, release_id=None, release_id_matches=False,
    evidence_hash=None, evidence_hash_matches=False, body_identity_consistent=False,
)
# What the SQL returns for rows the route really writes: an in-progress row has no body; a refusal
# stores a radar_evidence_error.v1 body, which carries no origin, run or evidence hash.
IN_PROGRESS = dict(origin_automated_radar=False, state="IN_PROGRESS", outcome_code=None,
                   http_status=None, run_id=None, run_id_matches=False, evidence_hash=None,
                   evidence_hash_matches=False, body_identity_consistent=False)
REFUSED = dict(origin_automated_radar=False, outcome_code="QUOTA_EXCEEDED", http_status=429,
               run_id=None, run_id_matches=False, evidence_hash=None,
               evidence_hash_matches=False, body_identity_consistent=False)


def _row(module: Any = None, **changes: Any) -> tuple[Any, ...]:
    module = module or runner
    facts = dict(
        audit=module.ARTIFACT, verdict="PASS", reason="OK", bound_credential_id=CRED,
        bound_client_request_id=CRID, schema_ok=True, matched_rows=1,
        evidence_origin="AUTOMATED_RADAR",
        origin_automated_radar=True, state="COMPLETED", outcome_code="SUCCEEDED", http_status=200,
        run_id=RUN, run_id_matches=True, release_id=REL, release_id_matches=True, evidence_hash=EVH,
        evidence_hash_matches=True, body_identity_consistent=True,
    )
    facts.update(changes)
    return tuple(facts[name] for name in runner.SQL_COLUMNS)


class FakeConnection:
    def __init__(self, row: tuple[Any, ...] | None = None, *, read_only: str = "on",
                 columns: tuple[str, ...] | None = None, fail_on: str | None = None,
                 rollback_fails: bool = False) -> None:
        self.row = row if row is not None else _row()
        self.read_only = read_only
        self.columns = columns or runner.SQL_COLUMNS
        self.fail_on = fail_on
        self.rollback_fails = rollback_fails
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
        self.connection.calls.append((sql, params))
        if self.connection.fail_on and self.connection.fail_on in sql:
            raise RuntimeError("relation failed at " + URL)
        if sql.startswith("SELECT pg_catalog.current_setting"):
            self.result, self.description = [(self.connection.read_only,)], [("current_setting",)]
        elif sql == SEALED:
            self.result = [self.connection.row]
            self.description = [(name,) for name in self.connection.columns]
        else:
            self.result, self.description = [], None

    def fetchone(self) -> tuple[Any, ...] | None:
        return self.result[0] if self.result else None

    def fetchall(self) -> list[tuple[Any, ...]]:
        return list(self.result)


ARGS = ["--credential-id", CRED, "--client-request-id", CRID, "--run-id", RUN,
        "--release-id", REL, "--evidence-hash", EVH]


def _invoke(module: Any, connection: FakeConnection | None = None, *,
            args: list[str] | None = None, environ: dict[str, str] | None = None,
            connect: Callable[..., Any] | None = None) -> tuple[int, dict[str, Any], list, str]:
    connection = connection or FakeConnection()
    seen: list[Any] = []

    def fake_connect(url: str, **kwargs: Any) -> FakeConnection:
        seen.append((url, kwargs))
        return connection

    out = io.StringIO()
    code = module.main(
        ARGS if args is None else args,
        environ={module.DATABASE_URL_ENV: URL} if environ is None else environ,
        connect=connect or fake_connect, stdout=out,
    )
    text = out.getvalue()
    assert text.endswith("\n") and text.count("\n") == 1
    return code, json.loads(text), seen, text


def _run(connection: FakeConnection | None = None, **kwargs: Any) -> tuple[int, dict, list, str]:
    code, payload, seen, text = _invoke(runner, connection, **kwargs)
    assert URL not in text and "NOT-A-REAL-PASSWORD" not in text
    return code, payload, seen, text


def test_a_qualifying_row_passes_inside_one_read_only_transaction() -> None:
    connection = FakeConnection()
    code, payload, seen, text = _run(connection)
    assert code == 0 and payload["verdict"] == "PASS" and payload["reason"] == "OK"
    assert payload["transaction_read_only"] is True and payload["sql_sha256"] == runner.SQL_SHA256
    assert text == json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n"
    assert [sql for sql, _ in connection.calls] == [
        "SET TRANSACTION READ ONLY",
        "SET LOCAL statement_timeout = '5000ms'",
        "SET LOCAL lock_timeout = '1000ms'",
        "SELECT pg_catalog.current_setting('transaction_read_only')",
        SEALED,
    ]
    assert connection.calls[-1][1] == {
        "credential_id": CRED, "client_request_id": CRID, "expected_run_id": RUN,
        "expected_release_id": REL, "expected_evidence_hash": EVH,
    }
    assert connection.ended == ["rollback", "close"]
    (url, kwargs), = seen
    assert url == URL and kwargs["autocommit"] is False and kwargs["prepare_threshold"] is None
    assert set(payload) == {*runner.SQL_COLUMNS, "artifact", "sql_sha256", "transaction_read_only"}
    assert "response_body" not in text


@pytest.mark.parametrize(
    ("reason", "changes"),
    [
        ("SCHEMA_DRIFT", dict(schema_ok=False)),
        ("NO_ROW", dict(matched_rows=0, **FAILED_ROW)),
        ("AMBIGUOUS", dict(matched_rows=2, **FAILED_ROW)),
        ("WRONG_ORIGIN", dict(evidence_origin="USER_REQUESTED", origin_automated_radar=False)),
        ("NOT_COMPLETED", IN_PROGRESS),
        ("NOT_SUCCEEDED", REFUSED),
        ("WRONG_ORIGIN", dict(origin_automated_radar=False)),  # a success whose body says otherwise
        ("BODY_IDENTITY_MISMATCH", dict(body_identity_consistent=False)),
        ("RUN_MISMATCH", dict(run_id="run_" + "0" * 32, run_id_matches=False)),
        ("RELEASE_MISMATCH", dict(release_id="UCPE-PROD-OTHER", release_id_matches=False)),
        ("EVIDENCE_MISMATCH", dict(evidence_hash="sha256:" + "0" * 64,
                                   evidence_hash_matches=False)),
    ],
)
def test_every_failing_row_fails_with_its_reason(reason: str, changes: dict[str, Any]) -> None:
    code, payload, _, _ = _run(FakeConnection(_row(verdict="FAIL", reason=reason, **changes)))
    assert code == 1 and payload["verdict"] == "FAIL" and payload["reason"] == reason


def test_a_pass_the_runner_cannot_reproduce_is_refused() -> None:
    lying = _row(run_id="run_" + "1" * 32)  # the SQL says PASS, but the run differs
    code, payload, _, _ = _run(FakeConnection(lying))
    assert code == 1 and payload["reason"] == "RUNNER_DISAGREES" and payload["verdict"] == "FAIL"


def test_a_session_that_is_not_read_only_runs_nothing() -> None:
    connection = FakeConnection(read_only="off")
    code, payload, _, _ = _run(connection)
    assert code == 4 and payload["reason"] == "NOT_READ_ONLY"
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


def test_an_unexpected_result_shape_is_refused() -> None:
    code, payload, _, _ = _run(FakeConnection(columns=(*runner.SQL_COLUMNS[:-1], "extra")))
    assert code == 4 and payload["reason"] == "UNEXPECTED_RESULT_SHAPE"


def test_a_missing_database_url_contacts_nothing() -> None:
    code, payload, seen, _ = _run(environ={})
    assert code == 4 and payload["reason"] == "DATABASE_URL_MISSING" and seen == []


def test_a_changed_sql_is_refused_before_anything_is_contacted(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    tampered = tmp_path / "a4_ledger_audit.sql"
    tampered.write_text(SEALED.replace("'AMBIGUOUS'", "'OK'"), encoding="utf-8")
    monkeypatch.setattr(runner, "SQL_PATH", tampered)
    code, payload, seen, _ = _run()
    assert code == 3 and payload["reason"] == "SEAL_MISMATCH" and seen == []


@pytest.mark.parametrize(
    ("flag", "value"),
    [
        ("--credential-id", "ucpea.uor-radar-2026-10.THE-SECRET-VALUE"),
        ("--credential-id", "UOR"),
        ("--client-request-id", "3E8CA8F0-5016-4E45-9EA1-0AEDBE815260"),
        ("--client-request-id", "3e8ca8f050164e459ea10aedbe815260"),
        ("--run-id", "run_D33406CEA53648829428B829198577D3"),
        ("--release-id", "PROD-E2"),
        ("--evidence-hash", "58191ef5c11e12eaadbddc6b5289eecbf0d56fd18999074c6576dd0d8a9ba846"),
    ],
)
def test_malformed_inputs_are_refused_unechoed_before_contact(flag: str, value: str) -> None:
    args = dict(zip(ARGS[::2], ARGS[1::2], strict=True))
    args[flag] = value
    code, payload, seen, text = _run(args=[item for pair in args.items() for item in pair])
    assert code == 2 and payload["reason"] == f"INPUT_REFUSED:{flag[2:].replace('-', '_')}"
    assert seen == [] and value not in text


@pytest.mark.parametrize("args", [["--token", "ucpea.x-y-z.SECRET"], ["-h"], [*ARGS, "--help"]])
def test_unknown_arguments_and_help_are_refused_unechoed(args: list[str]) -> None:
    code, payload, seen, text = _run(args=args)
    assert code == 2 and payload["reason"] == "INPUT_REFUSED:arguments"
    assert seen == [] and "SECRET" not in text


def test_the_runner_is_standalone_and_names_no_other_table() -> None:
    source = RUNNER_FILE.read_text(encoding="utf-8")
    assert "crypto_probability_engine" not in source
    for word in migration_relations() | {"automation_credential", "secret_sha256"}:
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
        return (code == 0 and connection.ended == ["rollback", "close"]
                and [sql for sql, _ in connection.calls][:4] == list(module.READ_ONLY_PREAMBLE)
                + ["SELECT pg_catalog.current_setting('transaction_read_only')"]
                and seen[0][1]["autocommit"] is False
                and text == json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")

    def not_read_only() -> bool:
        connection = FakeConnection(_row(module), read_only="off")
        code, payload, _, _ = _invoke(module, connection)
        return code == 4 and SEALED not in [sql for sql, _ in connection.calls]

    def database_error() -> bool:
        connection = FakeConnection(_row(module), fail_on="WITH binding")
        code, payload, _, text = _invoke(module, connection)
        return code == 4 and URL not in text and connection.ended == ["rollback", "close"]

    def no_url_on_connect_failure() -> bool:
        code, _, _, text = _invoke(module, connect=_refusing_connect)
        return code == 4 and URL not in text

    def seal() -> bool:
        original = module.SQL_PATH
        with tempfile.TemporaryDirectory() as folder:
            tampered = Path(folder) / "a4_ledger_audit.sql"
            tampered.write_text(SEALED.replace("'AMBIGUOUS'", "'OK'"), encoding="utf-8")
            module.SQL_PATH = tampered
            try:
                code, _, seen, _ = _invoke(module)
            finally:
                module.SQL_PATH = original
        return code == 3 and seen == []

    def credential_value() -> bool:
        args = list(ARGS)
        args[1] = "ucpea.uor-radar-2026-10.THE-SECRET-VALUE"
        code, _, seen, text = _invoke(module, args=args)
        return code == 2 and seen == [] and "THE-SECRET-VALUE" not in text

    def canonical_uuid_only() -> bool:
        args = list(ARGS)
        args[3] = CRID.upper()
        code, _, seen, _ = _invoke(module, args=args)
        return code == 2 and seen == []

    def arguments() -> bool:
        results = [_invoke(module, args=["--token", "ucpea.x-y-z.SECRET"]), _invoke(module,
                   args=["-h"])]
        return all(code == 2 and seen == [] and "SECRET" not in text
                   for code, _, seen, text in results)

    def cross_check() -> bool:
        lying = FakeConnection(_row(module, run_id="run_" + "1" * 32))
        code, payload, _, _ = _invoke(module, lying)
        return code == 1 and payload["reason"] == "RUNNER_DISAGREES"

    def shape() -> bool:
        connection = FakeConnection(_row(module), columns=(*runner.SQL_COLUMNS[:-1], "extra"))
        code, payload, _, _ = _invoke(module, connection)
        return code == 4 and payload["reason"] == "UNEXPECTED_RESULT_SHAPE"

    def real_failures() -> bool:
        cases = [("NOT_COMPLETED", IN_PROGRESS), ("NOT_SUCCEEDED", REFUSED)]
        return all(_invoke(module, FakeConnection(_row(module, verdict="FAIL", reason=reason,
                                                       **changes)))[1]["reason"] == reason
                   for reason, changes in cases)

    for name, probe in [
        ("happy path", happy), ("read-only proven", not_read_only),
        ("database error", database_error),
        ("no URL on connect failure", no_url_on_connect_failure),
        ("seal", seal), ("credential value refused", credential_value),
        ("canonical UUID only", canonical_uuid_only), ("arguments refused", arguments),
        ("cross-check", cross_check), ("result shape", shape), ("real failing rows", real_failures),
    ]:
        check(name, probe)
    return failures


RUNNER_MUTANTS = {
    "R01 no read-only preamble": ("                begin_read_only(cursor)\n", ""),
    "R02 read-only not proven": (
        '    if read_only is None or read_only[0] != "on":', "    if False:"
    ),
    "R03 no rollback": ("    for step in (connection.rollback, connection.close):",
                        "    for step in (connection.close,):"),
    "R04 exception message printed": (
        'raise Refusal("DATABASE_ERROR", EXIT_DATABASE, type(exc).__name__) from None',
        'raise Refusal("DATABASE_ERROR", EXIT_DATABASE, f"{type(exc).__name__}: {exc}") from None',
    ),
    "R05 any UUID spelling": ("        return str(uuid.UUID(value)) == value",
                              "        return bool(uuid.UUID(value))"),
    "R06 no cross-check": ("    reason = expected_reason(facts, binding)\n    return (",
                           "    reason = expected_reason(facts, binding)\n    return True or ("),
    "R07 seal not enforced": ("    if hashlib.sha256(data).hexdigest() != SQL_SHA256:",
                              "    if False:"),
    "R08 unsorted output": ('    return json.dumps(payload, sort_keys=True, separators=',
                            '    return json.dumps(payload, separators='),
    "R09 argparse echoes": (
        "    parser = _Parser(prog=", "    parser = argparse.ArgumentParser(prog="
    ),
    "R10 autocommit session": ("            autocommit=False,\n", "            autocommit=True,\n"),
    "R11 credential unchecked": ("    if not CREDENTIAL_ID.fullmatch(credential_id):",
                                 "    if False:"),
    "R12 result shape unchecked": ("    if names != SQL_COLUMNS or len(rows) != 1:",
                                   "    if False:"),
    "R13 body origin judged first": (
        '    if facts["evidence_origin"] != "AUTOMATED_RADAR":',
        '    if facts["evidence_origin"] != "AUTOMATED_RADAR"'
        ' or facts["origin_automated_radar"] is not True:',
    ),
    "R14 help exits 0": ("add_help=False", "add_help=True"),
}
RUNNER_SOURCE = RUNNER_FILE.read_text(encoding="utf-8")


def test_the_behaviour_battery_passes_the_real_runner() -> None:
    assert _behaviour_failures(_module("a4_runner_real", RUNNER_FILE, RUNNER_SOURCE)) == []


@pytest.mark.parametrize("name", sorted(RUNNER_MUTANTS))
def test_every_runner_mutant_breaks_a_behaviour(name: str) -> None:
    old, new = RUNNER_MUTANTS[name]
    assert RUNNER_SOURCE.count(old) >= 1, name
    mutant = _module(f"a4_runner_{name[:3]}", RUNNER_FILE, RUNNER_SOURCE.replace(old, new))
    assert _behaviour_failures(mutant), name


# --------------------------------------------------------------------------- seal and handoff
MANIFEST = PACKAGE / "MANIFEST.json"
HANDOFF = ROOT / "docs" / "automation" / "UOR_HANDOFF.md"
SEALED_FILES = ("a4_ledger_audit.sql", "a4_ledger_audit.py", "CARD.md", "build_manifest.py")
FIELDS = (
    "A4_ARTIFACT_STATUS", "ARTIFACT_NAME", "ARTIFACT_SHA256", "UPSTREAM_RELEASE_IDENTITY",
    "INPUT_BINDING", "OUTPUT_CONTRACT", "READ_ONLY_PROOF", "ISOLATION_PROOF", "TESTS",
    "INDEPENDENT_REVIEW", "PRODUCTION_QUERY_EXECUTED", "PACKAGE_PATH",
)


def test_the_manifest_seals_every_package_file() -> None:
    built = _module("a4_manifest", PACKAGE / "build_manifest.py").manifest()
    expected = json.dumps(built, indent=1, sort_keys=True) + "\n"
    assert MANIFEST.read_text(encoding="utf-8") == expected
    assert set(built["files"]) == {f"ops/a4_ledger_audit/{name}" for name in SEALED_FILES}
    assert {path.name for path in PACKAGE.iterdir()
            if path.is_file() and not path.name.startswith(".")} == {*SEALED_FILES, "MANIFEST.json"}
    migration = hashlib.sha256(MIGRATION_0013.read_bytes()).hexdigest()
    assert built["ledger_schema"]["sha256"] == migration


def test_the_handoff_carries_exactly_the_a4_fields_and_the_seal() -> None:
    text = HANDOFF.read_text(encoding="utf-8")
    assert "It is the only UCPE release serving" not in text
    section = text.split("## 14. A4 per-request ledger audit", 1)[1]
    block = section.split("```text\n", 1)[1].split("```", 1)[0]
    lines = block.strip().splitlines()
    assert [line.split("=", 1)[0] for line in lines] == list(FIELDS)
    values = dict(line.split("=", 1) for line in lines)
    assert all(values.values()) and "@@" not in section
    assert values["ARTIFACT_NAME"] == runner.ARTIFACT
    assert values["ARTIFACT_SHA256"] == hashlib.sha256(MANIFEST.read_bytes()).hexdigest()
    assert values["PRODUCTION_QUERY_EXECUTED"] == "NO"
    assert values["PACKAGE_PATH"] == "ops/a4_ledger_audit/"
    for name in ("MANIFEST.json", *SEALED_FILES):
        assert f"| `ops/a4_ledger_audit/{name}` |" in section, name
