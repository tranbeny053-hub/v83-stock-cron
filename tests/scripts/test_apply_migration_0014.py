"""The one-shot apply of migration 0014 (the core-evidence invariants). No database is contacted.

Every database interaction runs against a fake driver that behaves like psycopg 3 where it matters:
a connection used as a context manager commits on success and rolls back on an exception, a
statement is recorded with its parameters, and a check read before and after the migration can
return different rows. The real PostgreSQL rehearsals run in
.github/workflows/migration-0014-rehearsal.yml (every pull request) and inside the dispatch job
(.github/workflows/apply-migration-0014.yml), before the secret is handed to any step.
"""

from __future__ import annotations

import ast
import hashlib
import inspect
import json
import re
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from crypto_probability_engine.runtime_isolation import ProvenanceRefused
from crypto_probability_engine.utils.invariants import PROBABILITY_TOLERANCE
from scripts import apply_migration_0011 as apply_0011
from scripts import apply_migration_0014 as apply_0014

ROOT = Path(__file__).resolve().parents[2]
MIGRATION_BYTES = (ROOT / apply_0014.MIGRATION).read_bytes()
MIGRATION_SQL = MIGRATION_BYTES.decode("utf-8")
DATABASE_URL = "postgresql://owner:NEVER-SHOWN-SECRET@db.never-contacted.invalid:5432/postgres"
REHEARSAL_URL = "postgresql:///migration_0014_rehearsal?host=/var/run/postgresql"
PRODUCTION_SERVER = 170006
REHEARSAL_SERVER = 160010
ALL = list(apply_0014.table_privileges_for(PRODUCTION_SERVER))
CHECK_NAMES = ("targets", "columns", "constraints", "indexes", "triggers", "functions", "other",
               "other_schema", "event_triggers")


# ------------------------------------------------------------------------ a psycopg-3-shaped fake


class FakeDatabase:
    """``results[query]`` is either one list of rows, or ``Each([rows, rows, ...])`` per call."""

    def __init__(self, results: dict[str, Any], fail_on: dict[str, Exception] | None = None):
        self.results = results
        self.fail_on = fail_on or {}
        self.statements: list[tuple[str, Any]] = []
        self.connects: list[tuple[str, dict[str, Any]]] = []
        self.commits = 0
        self.rollbacks = 0
        self.in_transaction = False
        self.calls: dict[str, int] = {}

    def connect(self, url: str, **options: Any) -> FakeConnection:
        self.connects.append((url, options))
        return FakeConnection(self)

    def executed(self) -> list[str]:
        return [statement for statement, _ in self.statements]


class Each(list):
    """Rows for the first call, the second call, and so on; the last repeats."""


class FakeConnection:
    def __init__(self, database: FakeDatabase):
        self.database = database

    def cursor(self) -> FakeCursor:
        return FakeCursor(self.database)

    def commit(self) -> None:
        if self.database.in_transaction:
            self.database.commits += 1
        self.database.in_transaction = False

    def rollback(self) -> None:
        if self.database.in_transaction:
            self.database.rollbacks += 1
        self.database.in_transaction = False

    def __enter__(self) -> FakeConnection:
        return self

    def __exit__(self, exc_type, exc, traceback) -> bool:
        if exc_type is None:
            self.commit()
        else:
            self.rollback()
        return False


class FakeCursor:
    def __init__(self, database: FakeDatabase):
        self.database = database
        self.rows: list[tuple] = []

    def __enter__(self) -> FakeCursor:
        return self

    def __exit__(self, *exc: object) -> bool:
        return False

    def execute(self, query: str, params: Any = None) -> None:
        database = self.database
        database.statements.append((query, params))
        database.in_transaction = True
        if query in database.fail_on:
            raise database.fail_on[query]
        result = database.results.get(query, [])
        if isinstance(result, Each):
            call = database.calls.get(query, 0)
            database.calls[query] = call + 1
            result = result[min(call, len(result) - 1)]
        self.rows = list(result)

    def fetchone(self) -> tuple | None:
        return self.rows[0] if self.rows else None

    def fetchall(self) -> list[tuple]:
        return list(self.rows)


# ------------------------------------------------------------------------ production after 0013


def security_row(table: str, *, privileges: list[str] = ALL, **changes: Any) -> tuple:
    values = {
        "relations_named_so": 1, "relkind": "r", "owned_by_applying_role": True,
        "row_level_security": True, "row_level_security_forced": False, "policies": 0,
        "public_has_a_privilege": False, "column_grant_to_public_anon_or_authenticated": False,
        "anon": [], "authenticated": [], "service_role": list(privileges),
    }
    values.update(changes)
    return (table, *(values[field] for field in apply_0014.SECURITY_FIELDS[1:]))


TARGETS = [security_row(table) for table in apply_0014.TARGET_TABLES]
OTHER = [security_row(table) for table in sorted(apply_0014.OTHER_TABLES)]
COLUMNS = [
    ("prediction_feature_snapshots.prediction_id", "text", True, False, False, False, False),
    ("prediction_feature_snapshots.snapshot_hash", "text", True, False, False, False, False),
    ("prediction_outcomes.prediction_id", "text", True, False, False, False, False),
    ("prediction_outcomes.outcome_reference_price", "numeric", True, False, False, False, False),
    ("predictions.prediction_id", "text", True, False, False, False, False),
    ("predictions.reference_price", "numeric", True, False, False, False, False),
    ("predictions.p_up_frac", "numeric", True, False, False, False, False),
]
EXISTING_CONSTRAINTS = [
    ("prediction_feature_snapshots.prediction_feature_snapshots_pkey", "p", True, False,
     "PRIMARY KEY (prediction_id)", ["prediction_id"]),
    ("prediction_feature_snapshots.prediction_feature_snapshots_prediction_id_fkey", "f", True,
     False, "FOREIGN KEY (prediction_id) REFERENCES predictions(prediction_id) ON DELETE RESTRICT",
     ["prediction_id"]),
    ("prediction_outcomes.prediction_outcomes_pkey", "p", True, False,
     "PRIMARY KEY (prediction_id)", ["prediction_id"]),
    ("prediction_outcomes.prediction_outcomes_realized_label_check", "c", True, False,
     "CHECK ((realized_label = ANY (ARRAY['UP'::text, 'DOWN'::text, 'TIMEOUT'::text])))",
     ["realized_label"]),
    ("predictions.predictions_pkey", "p", True, False, "PRIMARY KEY (prediction_id)",
     ["prediction_id"]),
    ("predictions.predictions_target_version_chk", "c", True, False,
     "CHECK (((target_version IS NULL) OR (target_version = 'tc-v1'::text)))", ["target_version"]),
]
# The server's own deparse of each new check (PostgreSQL 16 and 17 print these identically).
NEW_CONSTRAINT_ROWS = {
    "predictions.predictions_probability_simplex_chk": (
        "predictions.predictions_probability_simplex_chk", "c", False, False,
        "CHECK (((p_up_frac >= (0)::numeric) AND (p_up_frac <= (1)::numeric) AND "
        "(p_down_frac >= (0)::numeric) AND (p_down_frac <= (1)::numeric) AND "
        "(p_timeout_frac >= (0)::numeric) AND (p_timeout_frac <= (1)::numeric) AND "
        "(abs((((p_up_frac + p_down_frac) + p_timeout_frac) - (1)::numeric)) <= 0.000001)))"
        " NOT VALID",
        ["p_down_frac", "p_timeout_frac", "p_up_frac"],
    ),
    "predictions.predictions_reference_price_chk": (
        "predictions.predictions_reference_price_chk", "c", False, False,
        "CHECK (((reference_price > (0)::numeric) AND (reference_price < 'Infinity'::numeric)))"
        " NOT VALID",
        ["reference_price"],
    ),
    "predictions.predictions_horizon_chronology_chk": (
        "predictions.predictions_horizon_chronology_chk", "c", False, False,
        "CHECK (((horizon_bars > 0) AND (horizon_end_utc > reference_close_utc) AND "
        "(reference_close_utc <= predicted_at_utc))) NOT VALID",
        ["horizon_bars", "horizon_end_utc", "predicted_at_utc", "reference_close_utc"],
    ),
    "prediction_outcomes.prediction_outcomes_reference_price_chk": (
        "prediction_outcomes.prediction_outcomes_reference_price_chk", "c", False, False,
        "CHECK (((outcome_reference_price > (0)::numeric) AND "
        "(outcome_reference_price < 'Infinity'::numeric))) NOT VALID",
        ["outcome_reference_price"],
    ),
}
APPLIED_CONSTRAINTS = sorted([*EXISTING_CONSTRAINTS, *NEW_CONSTRAINT_ROWS.values()])
INDEXES = [
    ("prediction_feature_snapshots.prediction_feature_snapshots_pkey",
     "CREATE UNIQUE INDEX prediction_feature_snapshots_pkey ON public.prediction_feature_snapshots "
     "USING btree (prediction_id)"),
    ("predictions.predictions_pkey",
     "CREATE UNIQUE INDEX predictions_pkey ON public.predictions USING btree (prediction_id)"),
]
NEW_TRIGGER_ROWS = [
    (item, "O", bits, apply_0014.FUNCTION_REFERENCE, 0, False, False)
    for item, bits in sorted(apply_0014.NEW_TRIGGERS.items())
]
FUNCTION_ROW = (
    apply_0014.FUNCTION, "", "trigger", "plpgsql", False, "f",
    list(apply_0014.FUNCTION_CONFIG), True, apply_0014.FUNCTION_SOURCE,
    False, False, False, False,
)
OTHER_SCHEMA = [
    ("prediction_derivatives_snapshots/trigger/trg_pds_reject_update",
     "O 19 reject_prediction_derivatives_snapshot_mutation"),
    ("watchlist/column/normalized_symbol", "text notnull=true default= acl="),
]
EVENT_TRIGGERS = [("pgrst_ddl_watch", "ddl_command_end", "O", "extensions.pgrst_ddl_watch", "")]


def healthy_results(version: int = PRODUCTION_SERVER, **overrides: Any) -> dict[str, Any]:
    """A first apply on production as it is after 0013: every pre read, then every post read."""

    pre_post = {
        "targets": (TARGETS, TARGETS),
        "columns": (COLUMNS, COLUMNS),
        "constraints": (EXISTING_CONSTRAINTS, APPLIED_CONSTRAINTS),
        "indexes": (INDEXES, INDEXES),
        "triggers": ([], NEW_TRIGGER_ROWS),
        "functions": ([], [FUNCTION_ROW]),
        "other": (OTHER, OTHER),
        "other_schema": (OTHER_SCHEMA, OTHER_SCHEMA),
        "event_triggers": (EVENT_TRIGGERS, EVENT_TRIGGERS),
    }
    pre_post.update(overrides)
    results: dict[str, Any] = {
        apply_0014.ROLES_SQL: [(3,)],
        apply_0014.SERVER_VERSION_SQL: [(version,)],
    }
    for name, query, _fields in apply_0014.read_only_checks(version):
        before, after = pre_post[name]
        results[query] = Each([before, after])
    return results


def _apply(database: FakeDatabase) -> tuple[dict[str, Any], dict[str, Any]]:
    captured: dict[str, Any] = {}
    outcome = apply_0014.apply_in_one_transaction(
        lambda: database.connect(DATABASE_URL), MIGRATION_SQL, captured
    )
    return outcome, captured


def _dicts(fields: tuple[str, ...], rows: list[tuple]) -> list[dict[str, Any]]:
    return [
        {field: list(value) if isinstance(value, (list, tuple)) else value
         for field, value in zip(fields, row, strict=True)}
        for row in rows
    ]


def _state(**overrides: Any) -> tuple[dict[str, list], dict[str, list]]:
    """The healthy pre and post reads as the pure checks see them, with ``overrides`` (post)."""

    fields = {name: checked for name, _query, checked in apply_0014.read_only_checks(170006)}
    results = healthy_results()
    pre, post = {}, {}
    for name, query, _fields in apply_0014.read_only_checks(170006):
        before, after = results[query]
        pre[name] = _dicts(fields[name], before)
        post[name] = _dicts(fields[name], overrides.get(name, after))
    return pre, post


# ------------------------------------------------------------------------ what the route is


def test_the_script_imports_only_the_standard_library_at_module_level() -> None:
    tree = ast.parse((ROOT / apply_0014.SCRIPT).read_text(encoding="utf-8"))
    imported = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            imported |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert imported <= {"__future__", "argparse", "hashlib", "json", "os", "platform", "re",
                        "subprocess", "sys", "collections", "pathlib", "types", "typing"}


def test_it_names_itself_its_workflow_and_the_reviewed_bytes() -> None:
    assert apply_0014.SCRIPT == "scripts/apply_migration_0014.py"
    assert apply_0014.WORKFLOW == ".github/workflows/apply-migration-0014.yml"
    assert (ROOT / apply_0014.WORKFLOW).is_file()
    assert apply_0014.MIGRATION == "migrations/0014_core_evidence_invariants.sql"
    assert hashlib.sha256(MIGRATION_BYTES).hexdigest() == apply_0014.MIGRATION_SHA256
    assert apply_0014.CONFIRMATION == "APPLY-MIGRATION-0014-ONCE"
    assert apply_0014.REHEARSAL_URL_VARIABLE == "MIGRATION_0014_REHEARSAL_URL"


def test_its_advisory_lock_is_its_own() -> None:
    keys = {}
    for path in sorted((ROOT / "scripts").glob("apply_*.py")):
        found = re.findall(r"pg_advisory_xact_lock\((\d+)\)", path.read_text(encoding="utf-8"))
        keys.update({key: path.name for key in found})
    assert keys["5000014"] == "apply_migration_0014.py"
    assert list(keys.values()).count("apply_migration_0014.py") == 1


# The trust machinery is 0011's, copied verbatim: a reviewed route, not a new one.
SHARED = ("table_privileges_for", "_held", "_security_sql", "build_parser", "ensure_source_path",
          "enter_isolated_runtime", "observe", "verify_dispatch", "attest_dispatch",
          "attest_loaded_modules", "load_driver", "migration_bytes", "main", "_run",
          "_count_after", "_unchanged_failures", "_read_checks", "_rows", "_plain", "_row", "_git",
          "_refusal_record", "_commit_state", "_is_refusal", "_write_report")


@pytest.mark.parametrize("name", SHARED)
def test_its_trust_machinery_is_0011_s_verbatim(name: str) -> None:
    assert inspect.getsource(getattr(apply_0014, name)) == inspect.getsource(
        getattr(apply_0011, name)
    ), name


def test_its_transaction_and_rehearsal_are_0011_s_up_to_the_migration_number() -> None:
    for name in ("apply_in_one_transaction", "_refusal"):
        ours = inspect.getsource(getattr(apply_0014, name))
        theirs = inspect.getsource(getattr(apply_0011, name)).replace("0011", "0014")
        assert ours == theirs, name
    ours = inspect.getsource(apply_0014.rehearse).split('"""')
    theirs = inspect.getsource(apply_0011.rehearse).replace("0011", "0014").split('"""')
    assert ours[0] == theirs[0] and ours[2] == theirs[2], "only the docstring differs"
    for constant in ("TIMEOUT_STATEMENTS", "API_ROLES", "TABLE_PRIVILEGES",
                     "MINIMUM_SERVER_VERSION", "MAINTAIN_SINCE_SERVER_VERSION", "SECURITY_FIELDS",
                     "PINNED_PYTHON", "EXPECTED_REPOSITORY", "REQUIRED_REF", "REQUIRED_EVENT"):
        assert getattr(apply_0014, constant) == getattr(apply_0011, constant), constant


# ------------------------------------------------------------------------ it matches the migration


def _check_body(name: str) -> str:
    match = re.search(rf"ADD CONSTRAINT {name}\s+CHECK \((.*?)\)\s+NOT VALID;", MIGRATION_SQL, re.S)
    assert match is not None, name
    return match.group(1)


def test_its_expected_constraints_are_the_migration_s_own() -> None:
    names = set(re.findall(r"ADD CONSTRAINT ([a-z_]+)", MIGRATION_SQL))
    assert {item.split(".")[1] for item in apply_0014.NEW_CONSTRAINTS} == names
    for item, check in apply_0014.NEW_CONSTRAINTS.items():
        table, name = item.split(".")
        assert re.search(rf"ALTER TABLE public\.{table}\s+ADD CONSTRAINT {name}\b", MIGRATION_SQL)
        body = _check_body(name)
        assert apply_0014.constraint_comparisons(body) == check.comparisons, item
        assert apply_0014.constraint_numbers(body) == check.numbers, item
        assert apply_0014.constraint_literals(body) == check.literals, item
        for column in check.columns:
            assert re.search(rf"\b{column}\b", body), (item, column)


def test_the_tolerance_it_expects_is_the_pipeline_s_own() -> None:
    check = apply_0014.NEW_CONSTRAINTS["predictions.predictions_probability_simplex_chk"]
    assert Decimal(str(PROBABILITY_TOLERANCE)) in {Decimal(n) for n in check.numbers}


def test_its_expected_triggers_and_function_are_the_migration_s_own() -> None:
    prefixes = dict(re.findall(r"WHEN '([a-z_]+)' THEN '([a-z]+)'", MIGRATION_SQL))
    prefixes[apply_0014.TARGET_TABLES[0]] = re.search(r"ELSE '([a-z]+)'", MIGRATION_SQL).group(1)
    assert prefixes == dict(apply_0014.TRIGGER_PREFIX)
    listed = re.search(r"FOREACH target IN ARRAY ARRAY\[([^\]]*)\]", MIGRATION_SQL).group(1)
    assert sorted(re.findall(r"'([a-z_]+)'", listed)) == list(apply_0014.TARGET_TABLES)
    for event, bits in apply_0014.TRIGGER_EVENTS.items():
        level = "STATEMENT" if event == "truncate" else "ROW"
        assert f"BEFORE {event.upper()} ON public.%I FOR EACH {level}" in MIGRATION_SQL, event
        assert bits & 2 and bool(bits & 1) == (level == "ROW"), event
    body = re.search(r"AS \$\$(.*?)\$\$;", MIGRATION_SQL, re.S).group(1)
    assert body == apply_0014.FUNCTION_SOURCE
    path = re.search(r"SET search_path = ([^\n]+)\n", MIGRATION_SQL).group(1)
    assert apply_0014.FUNCTION_CONFIG == (f"search_path={path}",)
    assert f"CREATE OR REPLACE FUNCTION {apply_0014.FUNCTION_REFERENCE}()" in MIGRATION_SQL


def test_the_other_tables_are_every_other_table_of_migrations_0001_to_0013() -> None:
    created = set()
    for path in sorted((ROOT / "migrations").glob("*.sql")):
        if path.name < "0014":
            created |= set(re.findall(
                r"CREATE TABLE IF NOT EXISTS (?:public\.)?([a-z_0-9]+)", path.read_text()
            ))
    assert sorted(created - set(apply_0014.TARGET_TABLES)) == list(apply_0014.OTHER_TABLES)
    assert set(apply_0014.TARGET_TABLES) <= created


# ------------------------------------------------------------------------ the checks read only


FORBIDDEN = re.compile(
    r"\b(INSERT|UPDATE|DELETE|ALTER|CREATE|DROP|GRANT|REVOKE|TRUNCATE|COPY|CALL|DO|SET|VALIDATE)\b"
)


def _without_literals(query: str) -> str:
    return re.sub(r"'(?:[^']|'')*'", "''", query)


@pytest.mark.parametrize("version", [PRODUCTION_SERVER, REHEARSAL_SERVER])
def test_every_check_is_a_read_only_catalog_query(version: int) -> None:
    queries = [query for _name, query, _fields in apply_0014.read_only_checks(version)]
    queries += [apply_0014.ROLES_SQL, apply_0014.SERVER_VERSION_SQL]
    for query in queries:
        bare = _without_literals(query)
        assert query.lstrip().startswith("SELECT"), query[:60]
        assert not FORBIDDEN.search(bare), (FORBIDDEN.search(bare).group(0), query[:80])
        assert "%s" not in query and "%(" not in query, "no parameters"
        for source in re.findall(r"\b(?:FROM|JOIN)\s+([a-z_.]+)", bare):
            assert source.startswith("pg_catalog.") or source == "", (source, query[:80])
        assert "public." not in bare.replace("'public.' || t.name", ""), query[:80]


def test_the_checks_cover_the_three_tables_the_function_and_every_other_table() -> None:
    names = [name for name, _query, _fields in apply_0014.read_only_checks(PRODUCTION_SERVER)]
    assert tuple(names) == CHECK_NAMES
    targets = apply_0014.targets_security_sql(PRODUCTION_SERVER)
    for table in apply_0014.TARGET_TABLES:
        assert f"('{table}')" in targets
        assert f"('{table}')" in apply_0014.COLUMNS_SQL
    for table in apply_0014.OTHER_TABLES:
        assert f"('{table}')" in apply_0014.other_security_sql(PRODUCTION_SERVER)
        assert f"('{table}')" in apply_0014.OTHER_SCHEMA_SQL
    assert "'MAINTAIN'" in targets
    assert "'MAINTAIN'" not in apply_0014.targets_security_sql(REHEARSAL_SERVER)


# ------------------------------------------------------------------------ the pure verdicts


def test_a_healthy_first_apply_has_no_pre_or_post_failure() -> None:
    pre, post = _state()
    assert apply_0014.pre_check_failures(pre) == []
    assert apply_0014.post_check_failures(pre, post) == []


@pytest.mark.parametrize(
    ("name", "rows", "expected"),
    [
        ("constraints", [*EXISTING_CONSTRAINTS,
                         NEW_CONSTRAINT_ROWS["predictions.predictions_reference_price_chk"]],
         "the constraint predictions.predictions_reference_price_chk already exists"),
        ("triggers", NEW_TRIGGER_ROWS[:1],
         f"the trigger {NEW_TRIGGER_ROWS[0][0]} already exists"),
        ("functions", [FUNCTION_ROW],
         f"the function {apply_0014.FUNCTION_REFERENCE}() already exists"),
    ],
)
def test_a_second_apply_is_refused_as_not_a_first_apply(
    name: str, rows: list[tuple], expected: str
) -> None:
    pre, _post = _state()
    fields = dict((n, f) for n, _q, f in apply_0014.read_only_checks(PRODUCTION_SERVER))
    pre[name] = _dicts(fields[name], rows)
    failures = apply_0014.pre_check_failures(pre)
    assert failures == [f"{apply_0014.NOT_A_FIRST_APPLY}: {expected}"]


@pytest.mark.parametrize(
    ("changes", "expected"),
    [
        ({"owned_by_applying_role": False}, "is not owned by the applying role"),
        ({"relkind": "p"}, "not an ordinary table"),
        ({"relations_named_so": 2}, "relations have this name, not one"),
    ],
)
def test_a_target_the_applying_role_cannot_alter_refuses(
    changes: dict[str, Any], expected: str
) -> None:
    pre, _post = _state()
    pre["targets"][2].update(changes)
    failures = apply_0014.pre_check_failures(pre)
    assert len(failures) == 1 and expected in failures[0] and failures[0].startswith("predictions:")


def _replace(rows: list[tuple], item: str, **changes: Any) -> list[tuple]:
    fields = apply_0014.CONSTRAINT_FIELDS if len(rows[0]) == 6 else apply_0014.TRIGGER_FIELDS
    out = []
    for row in rows:
        if row[0] == item:
            values = dict(zip(fields, row, strict=True))
            values.update(changes)
            row = tuple(values[field] for field in fields)
        out.append(row)
    return out


SIMPLEX = "predictions.predictions_probability_simplex_chk"
PRICE = "predictions.predictions_reference_price_chk"
TRIGGER = NEW_TRIGGER_ROWS[0][0]


@pytest.mark.parametrize(
    ("name", "rows", "expected"),
    [
        ("constraints", _replace(APPLIED_CONSTRAINTS, SIMPLEX, validated=True),
         f"{SIMPLEX}: is validated, so existing rows were scanned"),
        ("constraints", _replace(APPLIED_CONSTRAINTS, SIMPLEX, deferrable=True),
         f"{SIMPLEX}: is deferrable"),
        ("constraints", _replace(APPLIED_CONSTRAINTS, PRICE, columns=["p_up_frac"]),
         f"{PRICE}: references ['p_up_frac'], not ['reference_price']"),
        ("constraints", _replace(
            APPLIED_CONSTRAINTS, PRICE,
            definition="CHECK ((reference_price > (0)::numeric)) NOT VALID"),
         f"{PRICE}: its literals are [], not ['Infinity']"),
        ("constraints", _replace(
            APPLIED_CONSTRAINTS, SIMPLEX,
            definition=NEW_CONSTRAINT_ROWS[SIMPLEX][4].replace("0.000001", "0.000000001")),
         f"{SIMPLEX}: its numbers are"),
        ("constraints", _replace(
            APPLIED_CONSTRAINTS, PRICE,
            definition=NEW_CONSTRAINT_ROWS[PRICE][4].replace("reference_price > (0)",
                                                             "reference_price < (0)")),
         f"{PRICE}: its comparisons are ['<', '<'], not ['>', '<']"),
        ("constraints", [row for row in APPLIED_CONSTRAINTS if row[0] != PRICE],
         f"{PRICE}: is missing after the apply"),
        ("constraints", [row for row in APPLIED_CONSTRAINTS
                         if row[0] != "predictions.predictions_target_version_chk"],
         "the constraint 'predictions.predictions_target_version_chk' is gone after the apply"),
        ("triggers", NEW_TRIGGER_ROWS[1:], f"{TRIGGER}: is missing after the apply"),
        ("triggers", _replace(NEW_TRIGGER_ROWS, TRIGGER, type=18), f"{TRIGGER}: type is 18"),
        ("triggers", _replace(NEW_TRIGGER_ROWS, TRIGGER, enabled="D"), f"{TRIGGER}: enabled"),
        ("triggers", _replace(NEW_TRIGGER_ROWS, TRIGGER, function="public.other"),
         f"{TRIGGER}: function is 'public.other'"),
        ("triggers", _replace(NEW_TRIGGER_ROWS, TRIGGER, has_when=True), f"{TRIGGER}: has_when"),
        ("functions", [], f"{apply_0014.FUNCTION_REFERENCE}: is missing after the apply"),
        ("functions", [FUNCTION_ROW, FUNCTION_ROW], "appears 2 times after the apply"),
        ("functions", [(*FUNCTION_ROW[:4], True, *FUNCTION_ROW[5:])], "security_definer is True"),
        ("functions", [(*FUNCTION_ROW[:6], [], *FUNCTION_ROW[7:])], "config is []"),
        ("functions", [(*FUNCTION_ROW[:8], "BEGIN NULL; END;", *FUNCTION_ROW[9:])], "source is"),
        ("functions", [(*FUNCTION_ROW[:10], True, *FUNCTION_ROW[11:])], "execute_anon is True"),
        ("functions", [(*FUNCTION_ROW[:12], True)], "execute_service_role is True"),
        ("columns", [(*COLUMNS[0][:2], False, *COLUMNS[0][3:]), *COLUMNS[1:]],
         "the column 'prediction_feature_snapshots.prediction_id' changed during the apply"),
        ("indexes", INDEXES[1:], "is gone after the apply"),
        ("targets", [security_row(t, anon=["SELECT"]) for t in apply_0014.TARGET_TABLES],
         "the security of table 'prediction_feature_snapshots' changed"),
        ("other", [security_row(t, row_level_security=False) for t in
                   sorted(apply_0014.OTHER_TABLES)], "changed during the apply"),
        ("other_schema", [*OTHER_SCHEMA, ("watchlist/trigger/new", "O 19 x")],
         "the schema item 'watchlist/trigger/new' appeared during the apply"),
        ("event_triggers", [], "the event trigger 'pgrst_ddl_watch' is gone after the apply"),
    ],
)
def test_every_departure_from_the_reviewed_result_refuses(
    name: str, rows: list[tuple], expected: str
) -> None:
    pre, post = _state(**{name: rows})
    failures = apply_0014.post_check_failures(pre, post)
    assert failures and any(expected in failure for failure in failures), failures


# ------------------------------------------------------------------------ one transaction


def test_a_first_apply_runs_every_check_in_one_committed_transaction() -> None:
    database = FakeDatabase(healthy_results())
    outcome, captured = _apply(database)
    checks = [query for _name, query, _fields in apply_0014.read_only_checks(PRODUCTION_SERVER)]
    assert database.executed() == [
        *apply_0014.TIMEOUT_STATEMENTS, apply_0014.ADVISORY_LOCK_SQL, apply_0014.ROLES_SQL,
        apply_0014.SERVER_VERSION_SQL, *checks, MIGRATION_SQL, *checks,
    ]
    assert database.commits == 1 and database.rollbacks == 0
    assert outcome["outcome"] == "APPLIED" and outcome["committed"] is True
    assert outcome["executed_migration_sha256"] == apply_0014.MIGRATION_SHA256
    assert outcome["post_functions"][0]["source"] == apply_0014.FUNCTION_SOURCE
    assert captured["committed"] is True


def test_a_refused_pre_check_never_runs_the_migration() -> None:
    database = FakeDatabase(healthy_results(functions=([FUNCTION_ROW], [FUNCTION_ROW])))
    with pytest.raises(ProvenanceRefused, match=apply_0014.NOT_A_FIRST_APPLY):
        _apply(database)
    assert MIGRATION_SQL not in database.executed()
    assert database.commits == 0 and database.rollbacks == 1


def test_a_refused_post_check_rolls_the_migration_back() -> None:
    weakened = _replace(APPLIED_CONSTRAINTS, SIMPLEX, validated=True)
    database = FakeDatabase(healthy_results(constraints=(EXISTING_CONSTRAINTS, weakened)))
    with pytest.raises(ProvenanceRefused, match="rolled back"):
        _apply(database)
    assert MIGRATION_SQL in database.executed()
    assert database.commits == 0 and database.rollbacks == 1


@pytest.mark.parametrize("version", [140012, None, "17"])
def test_an_unsupported_server_refuses_before_any_check(version: Any) -> None:
    results = healthy_results()
    results[apply_0014.SERVER_VERSION_SQL] = [(version,)]
    database = FakeDatabase(results)
    with pytest.raises(ProvenanceRefused, match="is not PostgreSQL 15 or later"):
        _apply(database)
    assert database.executed()[-1] == apply_0014.SERVER_VERSION_SQL


def test_missing_api_roles_refuse() -> None:
    results = healthy_results()
    results[apply_0014.ROLES_SQL] = [(2,)]
    with pytest.raises(ProvenanceRefused, match="of the 3 Supabase API roles exist"):
        _apply(FakeDatabase(results))


# ------------------------------------------------------------------------ the entrypoint


def test_apply_without_the_exact_token_refuses_before_anything(tmp_path: Path) -> None:
    report = tmp_path / "report.json"
    code = apply_0014.main(["--mode=apply", "--confirm=yes", f"--report={report}"], environ={})
    assert code == 2
    record = json.loads(report.read_text())
    assert record["outcome"] == "REFUSED" and apply_0014.CONFIRMATION in record["detail"]
    assert record["committed"] is False


def test_the_rehearsal_reaches_only_a_local_socket_and_never_beside_the_secret() -> None:
    args = apply_0014.build_parser().parse_args(["--mode=rehearse"])
    with pytest.raises(ProvenanceRefused, match="local unix-socket URL"):
        apply_0014.rehearse(args, {apply_0014.REHEARSAL_URL_VARIABLE: DATABASE_URL}, {})
    environ = {apply_0014.REHEARSAL_URL_VARIABLE: REHEARSAL_URL, "SUPABASE_DB_URL": DATABASE_URL}
    with pytest.raises(ProvenanceRefused, match="never runs where the production database"):
        apply_0014.rehearse(args, environ, {})


def test_a_rehearsal_applies_once_and_proves_a_second_apply_refuses(monkeypatch) -> None:
    applied = healthy_results(REHEARSAL_SERVER)
    # The second apply's pre-reads see the applied state: the function and triggers exist.
    for _name, query, _fields in apply_0014.read_only_checks(REHEARSAL_SERVER):
        rows = applied[query]
        applied[query] = Each([rows[0], rows[1], rows[1], rows[1]])
    database = FakeDatabase(applied)
    monkeypatch.setattr(apply_0014, "load_driver", lambda: database)
    args = apply_0014.build_parser().parse_args(["--mode=rehearse"])
    captured: dict[str, Any] = {}
    outcome = apply_0014.rehearse(args, {apply_0014.REHEARSAL_URL_VARIABLE: REHEARSAL_URL},
                                  captured)
    assert outcome["outcome"] == "REHEARSED"
    assert apply_0014.NOT_A_FIRST_APPLY in outcome["second_apply_refusal"]
    assert database.commits == 1 and database.rollbacks == 1
    assert [url for url, _options in database.connects] == [REHEARSAL_URL, REHEARSAL_URL]


def test_a_failure_names_no_secret(tmp_path: Path, monkeypatch, capsys) -> None:
    class Unreachable(Exception):
        pass

    def connect(url: str, **options: Any) -> None:
        raise Unreachable(f"could not connect to {url}")

    class Driver:
        pass

    driver = Driver()
    driver.connect = connect  # type: ignore[attr-defined]
    monkeypatch.setattr(apply_0014, "load_driver", lambda: driver)
    report = tmp_path / "report.json"
    environ = {apply_0014.REHEARSAL_URL_VARIABLE: REHEARSAL_URL}
    code = apply_0014.main(["--mode=rehearse", f"--report={report}"], environ=environ)
    assert code == 1
    record = json.loads(report.read_text())
    assert record["outcome"] == "FAILED" and record["error_type"] == "Unreachable"
    assert "withheld" in record["detail"]
    output = capsys.readouterr()
    for text in (report.read_text(), output.out, output.err):
        assert "migration_0014_rehearsal?host" not in text and "NEVER-SHOWN" not in text
