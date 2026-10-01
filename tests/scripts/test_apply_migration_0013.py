"""The one-shot apply of migration 0013 (automation registry and ledger). No database is contacted.

Every database interaction runs against a fake driver shaped like psycopg 3 where it matters: a
connection used as a context manager commits on success and rolls back on an exception, and a check
read before and after the migration can return different rows. The real PostgreSQL rehearsal runs
in .github/workflows/apply-migration-0013-rehearsal.yml on every pull request that touches it, and
inside the dispatch job itself before the secret is handed to any step.
"""

from __future__ import annotations

import ast
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from crypto_probability_engine.runtime_isolation import REQUIRED_FLAGS_TEXT, ProvenanceRefused
from scripts import apply_migration_0010 as apply_0010
from scripts import apply_migration_0011 as apply_0011
from scripts import apply_migration_0012 as apply_0012
from scripts import apply_migration_0013 as route

ROOT = Path(__file__).resolve().parents[2]
MIGRATION_BYTES = (ROOT / route.MIGRATION).read_bytes()
MIGRATION_SQL = MIGRATION_BYTES.decode("utf-8")
DATABASE_URL = "postgresql://owner:NEVER-SHOWN-SECRET@db.never-contacted.invalid:5432/postgres"
REHEARSAL_URL = "postgresql:///migration_0013_rehearsal?host=/var/run/postgresql"
SHA = "c" * 40
PRODUCTION_SERVER = 170006  # Supabase PostgreSQL 17.6
REHEARSAL_SERVER = 160010  # Ubuntu 24.04's PostgreSQL 16: no MAINTAIN
ALL = list(route.table_privileges_for(PRODUCTION_SERVER))


# ------------------------------------------------------------------------ a psycopg-3-shaped fake


class Each(list):
    """Rows for the first call, the second call, and so on; the last repeats."""


class FakeDiag:
    def __init__(self, constraint: str | None):
        self.constraint_name = constraint


class FakeIntegrityError(Exception):
    """Shaped like psycopg 3's IntegrityError where the probes read it."""

    def __init__(self, sqlstate: str, constraint: str | None):
        super().__init__(f"synthetic {sqlstate} on {constraint}")
        self.sqlstate = sqlstate
        self.diag = FakeDiag(constraint)


PROBES_BY_NAME = {
    name: (statements, expected) for name, statements, expected in route.CONSTRAINT_PROBES
}


class FakeDatabase:
    """Plays each constraint probe as the reviewed migration would, unless told otherwise."""

    def __init__(
        self,
        results: dict[str, Any],
        fail_on: dict[str, Exception] | None = None,
        probe_outcomes: dict[str, tuple[Any, ...]] | None = None,
    ):
        self.results = results
        self.fail_on = fail_on or {}
        self.probe_outcomes = probe_outcomes or {}
        self.statements: list[str] = []
        self.connects: list[tuple[str, dict[str, Any]]] = []
        self.commits = 0
        self.rollbacks = 0
        self.in_transaction = False
        self.calls: dict[str, int] = {}
        self.fail_commit: Exception | None = None
        self.probe_index = -1
        self.probe_step = 0
        self.in_probe = False

    def connect(self, url: str, **options: Any) -> FakeConnection:
        self.connects.append((url, options))
        self.probe_index = -1
        return FakeConnection(self)

    def play_probe_statement(self) -> None:
        name, statements, expected = route.CONSTRAINT_PROBES[self.probe_index]
        self.probe_step += 1
        outcome = self.probe_outcomes.get(name, expected)
        if self.probe_step == len(statements) and outcome[0] == "refused":
            raise FakeIntegrityError(outcome[1], outcome[2])


class FakeConnection:
    def __init__(self, database: FakeDatabase):
        self.database = database

    def cursor(self) -> FakeCursor:
        return FakeCursor(self.database)

    def commit(self) -> None:
        if self.database.in_transaction and self.database.fail_commit is not None:
            raise self.database.fail_commit
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
        assert params is None, "no check or statement takes a parameter"
        database = self.database
        database.statements.append(query)
        database.in_transaction = True
        if query in database.fail_on:
            raise database.fail_on[query]
        if query == route.PROBE_SAVEPOINT_SQL:
            database.probe_index += 1
            database.probe_step = 0
            database.in_probe = True
            self.rows = []
            return
        if query == route.PROBE_ROLLBACK_SQL:
            database.in_probe = False
            self.rows = []
            return
        if query == route.PROBE_RELEASE_SQL:
            self.rows = []
            return
        if database.in_probe:
            database.play_probe_statement()
            self.rows = []
            return
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


# ------------------------------------------------------------------------ the reviewed result


def security_row(table: str, **changes: Any) -> tuple:
    values = {"table": table, **route.EXPECTED_SECURITY, **changes}
    return tuple(_listed(values[field]) for field in route.SECURITY_FIELDS)


def existing_rows() -> list[tuple]:
    """Production's tables as some earlier migration left them: recorded, never required."""

    return [
        security_row(name, anon=[], authenticated=[], service_role=ALL)
        for name in route.EXISTING_TABLES
    ]


def relation_rows(count: int) -> list[tuple]:
    return [(name, count) for name in route.RELATION_NAMES]


def column_rows(table: str) -> list[tuple]:
    return [
        (name, type_name, not_null, default, False, False, False)
        for name, type_name, not_null, default in route.EXPECTED_COLUMNS[table]
    ]


def synthetic_definition(kind: str, literals: frozenset[str], integers: frozenset[int]) -> str:
    """A deparse carrying exactly the literals and integers the judge reads."""

    if kind == "p":
        return "PRIMARY KEY (credential_id)"
    if kind == "u":
        return "UNIQUE (secret_sha256)"
    parts = [f"(c = '{literal}'::text)" for literal in sorted(literals)]
    parts += [f"(n >= {integer})" for integer in sorted(integers)]
    return f"CHECK (({' AND '.join(parts) or 'c IS NOT NULL'}))"


def constraint_rows(table: str) -> list[tuple]:
    return [
        (name, kind, True, False, synthetic_definition(kind, literals, integers), list(columns))
        for name, (kind, columns, literals, integers) in sorted(
            route.EXPECTED_CONSTRAINTS[table].items()
        )
    ]


def index_rows(table: str) -> list[tuple]:
    structure = route.INDEX_STRUCTURE
    return [
        (
            name,
            unique,
            primary,
            list(columns),
            structure["predicate"],
            structure["access_method"],
            structure["valid"],
            structure["ready"],
            structure["immediate"],
            structure["exclusion"],
            structure["included_columns"],
            structure["expressions"],
            structure["default_order"],
            f"CREATE UNIQUE INDEX {name} ON public.{table} USING btree (...)",
        )
        for name, (unique, primary, columns) in sorted(route.EXPECTED_INDEXES[table].items())
    ]


def schema_rows(changed: str | None = None) -> list[tuple]:
    return [
        (name, *(("f" if name == changed else "e") * 64 for _ in range(5)))
        for name in route.EXISTING_TABLES
    ]


EVENT_TRIGGERS = [("pgrst_ddl_watch", "ddl_command_end", "O", "extensions.pgrst_ddl_watch")]


def healthy_results(server: int = PRODUCTION_SERVER, *, first_apply: bool = True) -> dict:
    results: dict[str, Any] = {
        route.ROLES_SQL: [(3,)],
        route.SERVER_VERSION_SQL: [(server,)],
        route.RELATIONS_SQL: Each([relation_rows(0 if first_apply else 1), relation_rows(1)]),
        route.existing_security_sql(server): Each([existing_rows()]),
        route.EXISTING_SCHEMA_SQL: Each([schema_rows()]),
        route.EVENT_TRIGGERS_SQL: Each([EVENT_TRIGGERS]),
        route.tables_security_sql(server): [security_row(table) for table in route.TABLES],
    }
    for table in route.TABLES:
        results[route.columns_sql(table)] = column_rows(table)
        results[route.constraints_sql(table)] = constraint_rows(table)
        results[route.referencing_sql(table)] = [(0,)]
        results[route.indexes_sql(table)] = index_rows(table)
        results[route.triggers_sql(table)] = []
        results[route.row_count_sql(table)] = [(0,)]
    return results


def apply(results: dict, captured: dict | None = None, **database_options: Any):
    database = FakeDatabase(results, **database_options)
    record = captured if captured is not None else {}
    outcome = route.apply_in_one_transaction(
        lambda: database.connect(REHEARSAL_URL), MIGRATION_SQL, record
    )
    return database, outcome


def refusal(results: dict, **database_options: Any) -> tuple[FakeDatabase, str]:
    database = FakeDatabase(results, **database_options)
    with pytest.raises(ProvenanceRefused) as refused:
        route.apply_in_one_transaction(lambda: database.connect(REHEARSAL_URL), MIGRATION_SQL, {})
    return database, str(refused.value)


def _listed(value: Any) -> Any:
    return list(value) if isinstance(value, tuple) else value


# ------------------------------------------------------------------------ identity and boundary


def test_the_script_imports_only_the_standard_library_at_module_level() -> None:
    tree = ast.parse((ROOT / route.SCRIPT).read_text(encoding="utf-8"))
    modules = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            modules |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom):
            modules.add((node.module or "").split(".")[0])
    assert modules <= {
        "__future__",
        "argparse",
        "hashlib",
        "json",
        "os",
        "platform",
        "re",
        "subprocess",
        "sys",
        "collections",
        "pathlib",
        "types",
        "typing",
    }


def test_it_names_itself_its_workflow_the_reviewed_bytes_and_its_own_token_and_lock() -> None:
    assert route.SCRIPT == "scripts/apply_migration_0013.py"
    assert route.WORKFLOW == ".github/workflows/apply-migration-0013.yml"
    assert route.MIGRATION == "migrations/0013_automation_radar_ledger.sql"
    assert route.migration_bytes() == MIGRATION_BYTES
    assert route.CONFIRMATION == "APPLY-MIGRATION-0013-ONCE"
    assert route.REHEARSAL_URL_VARIABLE == "MIGRATION_0013_REHEARSAL_URL"
    locks = {m.ADVISORY_LOCK_SQL for m in (apply_0010, apply_0011, apply_0012, route)}
    assert len(locks) == 4 and route.ADVISORY_LOCK_SQL.endswith("(5000013)")
    tokens = {m.CONFIRMATION for m in (apply_0011, apply_0012, route)}
    assert len(tokens) == 3


@pytest.mark.parametrize("server", [PRODUCTION_SERVER, REHEARSAL_SERVER])
def test_it_shares_0012_s_trust_boundary_and_security_check(server: int) -> None:
    for name in ("TIMEOUT_STATEMENTS", "PINNED_PYTHON", "EXPECTED_REPOSITORY", "API_ROLES"):
        assert getattr(route, name) == getattr(apply_0012, name), name
    assert route.table_privileges_for(server) == apply_0012.table_privileges_for(server)
    privileges = route.table_privileges_for(server)
    assert route._security_sql(route.TABLES, privileges) == apply_0012._security_sql(
        route.TABLES, privileges
    )
    assert route.RELATIONS_SQL.replace("automation", "") != apply_0012.RELATIONS_SQL
    assert route.SECURITY_FIELDS == apply_0012.SECURITY_FIELDS
    assert dict(route.EXPECTED_SECURITY) == dict(apply_0012.EXPECTED_SECURITY)


def test_the_existing_tables_are_every_table_of_migrations_0001_0009_and_0012() -> None:
    names = set()
    for path in sorted((ROOT / "migrations").glob("*.sql")):
        number = int(path.name[:4])
        if number <= 9 or number == 12:
            names |= set(
                re.findall(
                    r"CREATE TABLE IF NOT EXISTS (?:public\.)?(\w+)",
                    path.read_text(encoding="utf-8"),
                    re.I,
                )
            )
    assert tuple(sorted(names)) == route.EXISTING_TABLES
    assert not set(route.TABLES) & names


@pytest.mark.parametrize(
    ("definition", "literals", "integers"),
    [
        ("CHECK (((deadline_ms >= 5000) AND (deadline_ms <= 60000)))", set(), {5000, 60000}),
        ("CHECK ((secret_sha256 ~ '^[0-9a-f]{64}$'::text))", {"^[0-9a-f]{64}$"}, set()),
        (
            "CHECK ((status = ANY (ARRAY['ACTIVE'::text, 'REVOKED'::text])))",
            {"ACTIVE", "REVOKED"},
            set(),
        ),
        ("CHECK (((http_status IS NOT NULL) AND (http_status = 200)))", set(), {200}),
        ("CHECK ((note = 'it''s 5'::text))", {"it's 5"}, set()),
    ],
)
def test_literals_and_integers_are_read_as_sets_from_the_deparse(
    definition: str, literals: set[str], integers: set[int]
) -> None:
    assert route.constraint_literals(definition) == literals
    assert route.constraint_integers(definition) == integers


def test_every_check_is_a_read_only_query_without_parameters() -> None:
    for server in (PRODUCTION_SERVER, REHEARSAL_SERVER):
        for _name, query, _fields in (*route.pre_checks(server), *route.post_checks(server)):
            assert query.startswith("SELECT "), query
            assert "%" not in query
            unquoted = route._QUOTED_LITERAL.sub("''", query)  # privilege names are literals
            assert not re.search(
                r"\b(INSERT|UPDATE|DELETE|TRUNCATE|DROP|ALTER|CREATE|GRANT|REVOKE)\b", unquoted
            )


def test_the_only_application_reads_are_the_new_tables_row_counts_after_the_migration() -> None:
    reads = [
        query
        for _name, query, _fields in route.post_checks(PRODUCTION_SERVER)
        if re.search(r"\bFROM public\.", query)
    ]
    assert reads == [f"SELECT count(*) FROM public.{table}" for table in route.TABLES]
    assert not any(
        re.search(r"\bFROM public\.", query)
        for _n, query, _f in route.pre_checks(PRODUCTION_SERVER)
    )


# ------------------------------------------------------------------------ the transaction


def test_a_first_apply_runs_every_check_in_one_committed_transaction() -> None:
    captured: dict[str, Any] = {}
    database, outcome = apply(healthy_results(), captured)
    assert outcome["outcome"] == "APPLIED" and outcome["committed"] is True
    assert database.commits == 1 and database.rollbacks == 0 and len(database.connects) == 1
    statements = database.statements
    assert statements[:5] == [
        *route.TIMEOUT_STATEMENTS,
        route.ADVISORY_LOCK_SQL,
        route.ROLES_SQL,
        route.SERVER_VERSION_SQL,
    ]
    migration_at = statements.index(MIGRATION_SQL)
    assert statements.count(MIGRATION_SQL) == 1
    pre = [query for _n, query, _f in route.pre_checks(PRODUCTION_SERVER)]
    catalog = [query for _n, query, _f in route.post_catalog_checks(PRODUCTION_SERVER)]
    final = [query for _n, query, _f in route.post_final_checks(PRODUCTION_SERVER)]
    probes = []
    for _name, probe_statements, _expected in route.CONSTRAINT_PROBES:
        probes += [
            route.PROBE_SAVEPOINT_SQL,
            *probe_statements,
            route.PROBE_ROLLBACK_SQL,
            route.PROBE_RELEASE_SQL,
        ]
    assert statements[5:migration_at] == pre
    assert statements[migration_at + 1 :] == catalog + probes + final
    assert captured["committed"] is True
    assert outcome["post_row_count:automation_credential"] == 0
    assert outcome["table_privileges_asked"] == ALL
    assert [row["probe"] for row in outcome["constraint_probes"]] == list(PROBES_BY_NAME)
    assert route.probe_failures(outcome["constraint_probes"]) == []


def test_the_rehearsal_server_is_asked_about_exactly_its_privileges() -> None:
    _database, outcome = apply(healthy_results(REHEARSAL_SERVER))
    assert "MAINTAIN" not in outcome["table_privileges_asked"]
    assert "MAINTAIN" in ALL


@pytest.mark.parametrize("name", route.RELATION_NAMES)
def test_any_relation_already_named_so_in_public_is_not_a_first_apply(name: str) -> None:
    results = healthy_results()
    rows = [(relation, 1 if relation == name else 0) for relation in route.RELATION_NAMES]
    results[route.RELATIONS_SQL] = Each([rows])
    database, message = refusal(results)
    assert route.NOT_A_FIRST_APPLY in message and name in message
    assert MIGRATION_SQL not in database.statements
    assert database.commits == 0 and database.rollbacks == 1


def test_a_second_apply_refuses_naming_every_relation() -> None:
    database, message = refusal(healthy_results(first_apply=False))
    assert message.count(route.NOT_A_FIRST_APPLY) == len(route.RELATION_NAMES)
    assert MIGRATION_SQL not in database.statements and database.commits == 0


@pytest.mark.parametrize("roles", [0, 2, 4])
def test_missing_api_roles_refuse_before_anything_is_read(roles: int) -> None:
    results = healthy_results()
    results[route.ROLES_SQL] = [(roles,)]
    database, message = refusal(results)
    assert "Supabase API roles exist" in message
    assert route.RELATIONS_SQL not in database.statements


@pytest.mark.parametrize("version", [140012, "170006", True, None])
def test_an_unsupported_or_unreadable_server_version_refuses(version: Any) -> None:
    results = healthy_results()
    results[route.SERVER_VERSION_SQL] = [(version,)]
    database, message = refusal(results)
    assert "is not PostgreSQL 15 or later" in message
    assert route.RELATIONS_SQL not in database.statements


def test_the_existing_tables_are_recorded_not_required() -> None:
    results = healthy_results()
    odd = [security_row(name, row_level_security=False) for name in route.EXISTING_TABLES]
    results[route.existing_security_sql(PRODUCTION_SERVER)] = Each([odd])
    _database, outcome = apply(results)
    assert outcome["outcome"] == "APPLIED"


LEDGER, REGISTRY = route.LEDGER, route.REGISTRY


def _defect(results: dict, difference: str) -> None:
    server = PRODUCTION_SERVER
    tables = route.tables_security_sql(server)

    def security(**changes: Any) -> None:
        results[tables] = [security_row(REGISTRY, **changes), security_row(LEDGER)]

    def replace_row(query: str, index: int, position: int, value: Any) -> None:
        rows = [list(row) for row in results[query]]
        rows[index][position] = value
        results[query] = [tuple(row) for row in rows]

    if difference == "relation-twice":
        results[route.RELATIONS_SQL] = Each([relation_rows(0), relation_rows(2)])
    elif difference == "rls-off":
        security(row_level_security=False)
    elif difference == "rls-forced":
        security(row_level_security_forced=True)
    elif difference == "a-policy":
        security(policies=1)
    elif difference == "anon-can-select":
        security(anon=["SELECT"])
    elif difference == "service-role-can-insert":
        security(service_role=["INSERT"])
    elif difference == "public-privilege":
        security(public_has_a_privilege=True)
    elif difference == "not-owned":
        security(owned_by_applying_role=False)
    elif difference == "a-view":
        security(relkind="v")
    elif difference == "column-missing":
        results[route.columns_sql(LEDGER)] = column_rows(LEDGER)[:-1]
    elif difference == "column-extra":
        results[route.columns_sql(REGISTRY)] = [
            *column_rows(REGISTRY),
            ("extra", "text", False, None, False, False, False),
        ]
    elif difference == "column-type":
        replace_row(route.columns_sql(LEDGER), 1, 1, "text")
    elif difference == "column-nullable":
        replace_row(route.columns_sql(REGISTRY), 1, 2, False)
    elif difference == "column-default":
        replace_row(route.columns_sql(LEDGER), 3, 3, "'USER_REQUESTED'::text")
    elif difference == "column-identity":
        replace_row(route.columns_sql(REGISTRY), 0, 4, True)
    elif difference == "column-grant":
        replace_row(route.columns_sql(REGISTRY), 1, 6, True)
    elif difference == "constraint-missing":
        results[route.constraints_sql(LEDGER)] = constraint_rows(LEDGER)[1:]
    elif difference == "constraint-not-validated":
        replace_row(route.constraints_sql(REGISTRY), 0, 2, False)
    elif difference == "constraint-deferrable":
        replace_row(route.constraints_sql(REGISTRY), 0, 3, True)
    elif difference == "constraint-literals":
        replace_row(route.constraints_sql(REGISTRY), 0, 4, "CHECK ((c = 'other'::text))")
    elif difference == "constraint-integers":
        index = sorted(route.EXPECTED_CONSTRAINTS[LEDGER]).index("arl_deadline_bounds")
        replace_row(route.constraints_sql(LEDGER), index, 4, "CHECK ((n >= 1))")
    elif difference == "constraint-columns":
        replace_row(route.constraints_sql(LEDGER), 0, 5, ["other"])
    elif difference == "a-foreign-key":
        results[route.constraints_sql(REGISTRY)] = [
            *constraint_rows(REGISTRY),
            (
                "zz_fk",
                "f",
                True,
                False,
                "FOREIGN KEY (credential_id) REFERENCES x",
                ["credential_id"],
            ),
        ]
    elif difference == "referenced":
        results[route.referencing_sql(REGISTRY)] = [(1,)]
    elif difference == "index-not-unique":
        replace_row(route.indexes_sql(REGISTRY), 0, 1, False)
    elif difference == "index-primary":
        replace_row(route.indexes_sql(LEDGER), 0, 2, True)
    elif difference == "index-columns":
        replace_row(route.indexes_sql(LEDGER), 0, 3, ["received_at_utc", "credential_id"])
    elif difference == "index-partial":
        replace_row(route.indexes_sql(LEDGER), 0, 4, "(state = 'IN_PROGRESS'::text)")
    elif difference == "index-brin":
        replace_row(route.indexes_sql(LEDGER), 0, 5, "brin")
    elif difference == "index-invalid":
        replace_row(route.indexes_sql(REGISTRY), 1, 6, False)
    elif difference == "index-not-ready":
        replace_row(route.indexes_sql(REGISTRY), 1, 7, False)
    elif difference == "index-deferred":
        replace_row(route.indexes_sql(REGISTRY), 1, 8, False)
    elif difference == "index-exclusion":
        replace_row(route.indexes_sql(REGISTRY), 1, 9, True)
    elif difference == "index-include":
        replace_row(route.indexes_sql(LEDGER), 0, 10, 1)
    elif difference == "index-expression":
        replace_row(route.indexes_sql(LEDGER), 0, 11, True)
    elif difference == "index-descending":
        replace_row(route.indexes_sql(LEDGER), 0, 12, False)
    elif difference == "schema-changed":
        results[route.EXISTING_SCHEMA_SQL] = Each([schema_rows(), schema_rows("predictions")])
    elif difference == "event-trigger-added":
        added = [*EVENT_TRIGGERS, ("synthetic_watch", "ddl_command_end", "O", "public.f")]
        results[route.EVENT_TRIGGERS_SQL] = Each([EVENT_TRIGGERS, added])
    elif difference == "a-trigger":
        results[route.triggers_sql(LEDGER)] = [("synthetic_trigger", "O")]
    elif difference == "a-row":
        results[route.row_count_sql(REGISTRY)] = [(1,)]
    elif difference == "existing-changed":
        changed = existing_rows()
        changed[0] = security_row(route.EXISTING_TABLES[0], anon=["SELECT"])
        results[route.existing_security_sql(server)] = Each([existing_rows(), changed])
    else:  # pragma: no cover - a typo in the parametrization
        raise AssertionError(difference)


DIFFERENCES = [
    "relation-twice",
    "rls-off",
    "rls-forced",
    "a-policy",
    "anon-can-select",
    "service-role-can-insert",
    "public-privilege",
    "not-owned",
    "a-view",
    "column-missing",
    "column-extra",
    "column-type",
    "column-nullable",
    "column-default",
    "column-identity",
    "column-grant",
    "constraint-missing",
    "constraint-not-validated",
    "constraint-deferrable",
    "constraint-literals",
    "constraint-integers",
    "constraint-columns",
    "a-foreign-key",
    "referenced",
    "index-not-unique",
    "index-primary",
    "index-columns",
    "index-partial",
    "index-brin",
    "index-invalid",
    "index-not-ready",
    "index-deferred",
    "index-exclusion",
    "index-include",
    "index-expression",
    "index-descending",
    "schema-changed",
    "event-trigger-added",
    "a-trigger",
    "a-row",
    "existing-changed",
]


@pytest.mark.parametrize("difference", DIFFERENCES)
def test_any_difference_from_the_reviewed_result_rolls_the_apply_back(difference: str) -> None:
    results = healthy_results()
    _defect(results, difference)
    database, message = refusal(results)
    assert "the applied result is not the reviewed one" in message
    assert database.statements.count(MIGRATION_SQL) == 1
    assert database.commits == 0 and database.rollbacks == 1


PROBE_DEFECTS = {
    "a-weakened-bound-accepts-4999": {"ledger.deadline_4999": ("accepted",)},
    "a-reversed-expiry-accepts-the-past": {"registry.expiry_not_after_creation": ("accepted",)},
    "a-missing-pending-invariant": {"ledger.pending_with_identity": ("accepted",)},
    "another-constraint-refuses": {
        "ledger.cohort_origin": ("refused", route.CHECK_VIOLATION, "arl_state_shape")
    },
    "another-sqlstate": {
        "ledger.duplicate_key": (
            "refused",
            route.CHECK_VIOLATION,
            "automation_radar_ledger_pkey",
        )
    },
    "a-legitimate-row-refused": {
        "ledger.succeeded": ("refused", route.CHECK_VIOLATION, "arl_body_shape")
    },
    "an-owner-row-refused": {
        "registry.revoked": ("refused", route.CHECK_VIOLATION, "ac_revocation_shape")
    },
}


@pytest.mark.parametrize("defect", sorted(PROBE_DEFECTS))
def test_a_constraint_whose_behaviour_differs_rolls_the_apply_back(defect: str) -> None:
    database, message = refusal(healthy_results(), probe_outcomes=PROBE_DEFECTS[defect])
    assert "constraint probe" in message
    assert database.commits == 0 and database.rollbacks == 1


def test_every_probe_is_an_insert_into_a_new_table_inside_a_rolled_back_savepoint() -> None:
    names = [name for name, _statements, _expected in route.CONSTRAINT_PROBES]
    assert len(names) == len(set(names)) == 42
    for name, statements, expected in route.CONSTRAINT_PROBES:
        for statement in statements:
            assert statement.startswith(
                (f"INSERT INTO public.{route.LEDGER} (", f"INSERT INTO public.{route.REGISTRY} (")
            ), name
            assert "%" not in statement and ";" not in statement, name
        assert expected[0] in {"accepted", "refused"}, name
    refused = {
        expected[2] for _n, _s, expected in route.CONSTRAINT_PROBES if expected[0] != "accepted"
    }
    constraints = {name for table in route.TABLES for name in route.EXPECTED_CONSTRAINTS[table]}
    # Every constraint is probed, except the two *_valid CHECKs the *_shape CHECKs imply.
    assert constraints - refused == {"ac_status_valid", "arl_state_valid"}
    accepted = {n for n, _s, e in route.CONSTRAINT_PROBES if e[0] == "accepted"}
    for code in route.RECORDABLE_OUTCOMES - {"SUCCEEDED"}:
        assert f"ledger.refusal.{code}" in accepted


def test_the_judges_name_every_difference_not_only_the_first() -> None:
    results = healthy_results()
    for difference in ("rls-off", "column-type", "a-trigger", "a-row", "existing-changed"):
        _defect(results, difference)
    _database, message = refusal(results)
    assert "row_level_security is False" in message
    assert "client_request_id: type is 'text'" in message
    assert "synthetic_trigger" in message
    assert "rows are in automation_credential" in message
    assert "analysis_run_details" in message


def test_a_malformed_check_row_refuses() -> None:
    results = healthy_results()
    results[route.columns_sql(LEDGER)] = [("credential_id", "text")]
    database, message = refusal(results)
    assert "not a row of" in message and database.commits == 0


@pytest.mark.parametrize("position", [0, 4, 6, -1])
def test_a_driver_error_at_any_statement_rolls_back(position: int) -> None:
    results = healthy_results()
    probe = FakeDatabase(results)
    route.apply_in_one_transaction(lambda: probe.connect(REHEARSAL_URL), MIGRATION_SQL, {})
    failing = probe.statements[position]
    database = FakeDatabase(healthy_results(), fail_on={failing: RuntimeError("driver failure")})
    with pytest.raises(RuntimeError):
        route.apply_in_one_transaction(lambda: database.connect(REHEARSAL_URL), MIGRATION_SQL, {})
    assert database.commits == 0 and database.rollbacks == 1


# ------------------------------------------------------------------------ the dispatch


def _dispatch(**changes: str) -> dict[str, str]:
    values = {
        "github_actions": "true",
        "event_name": "workflow_dispatch",
        "repository": route.EXPECTED_REPOSITORY,
        "workflow_ref": f"{route.EXPECTED_REPOSITORY}/{route.WORKFLOW}@refs/heads/main",
        "ref": "refs/heads/main",
        "sha": SHA,
        "run_id": "123456789",
        "run_attempt": "1",
    }
    values.update(changes)
    return values


def _runtime(**changes: Any) -> dict[str, Any]:
    values: dict[str, Any] = {
        "git_head": SHA,
        "tracked_tree_clean": True,
        "python_implementation": "CPython",
        "python_version": "3.13.14",
        "interpreter_flags": REQUIRED_FLAGS_TEXT,
        "installed_files_sha256": "e" * 64,
    }
    values.update(changes)
    return values


def test_a_verified_dispatch_records_this_workflow() -> None:
    record = route.verify_dispatch(_dispatch(), _runtime(), expected_sha=SHA)
    assert record["dispatch_verified"] is True
    assert record["schema_version"] == route.DISPATCH_SCHEMA
    assert record["workflow"] == route.WORKFLOW
    assert record["expected_sha"] == record["sha"] == record["git_head"] == SHA


REPOSITORY = route.EXPECTED_REPOSITORY
DISPATCH_REFUSALS = {
    "not-actions": (_dispatch(github_actions=""), _runtime(), SHA),
    "pull-request": (_dispatch(event_name="pull_request"), _runtime(), SHA),
    "push-event": (_dispatch(event_name="push"), _runtime(), SHA),
    "other-branch": (_dispatch(ref="refs/heads/feature"), _runtime(), SHA),
    "the-0012-workflow": (
        _dispatch(workflow_ref=f"{REPOSITORY}/{apply_0012.WORKFLOW}@refs/heads/main"),
        _runtime(),
        SHA,
    ),
    "the-rehearsal-workflow": (
        _dispatch(
            workflow_ref=f"{REPOSITORY}/.github/workflows/apply-migration-0013-rehearsal.yml"
            "@refs/heads/main"
        ),
        _runtime(),
        SHA,
    ),
    "workflow-from-a-branch": (
        _dispatch(workflow_ref=f"{REPOSITORY}/{route.WORKFLOW}@refs/heads/feature"),
        _runtime(),
        SHA,
    ),
    "self-consistent-fork": (
        _dispatch(
            repository="attacker/fork",
            workflow_ref=f"attacker/fork/{route.WORKFLOW}@refs/heads/main",
        ),
        _runtime(),
        SHA,
    ),
    "short-sha": (_dispatch(sha=SHA[:7]), _runtime(git_head=SHA[:7]), SHA[:7]),
    "dispatched-other-commit": (_dispatch(sha="f" * 40), _runtime(), SHA),
    "checked-out-other-commit": (_dispatch(), _runtime(git_head="f" * 40), SHA),
    "dirty-tree": (_dispatch(), _runtime(tracked_tree_clean=False), SHA),
    "other-python": (_dispatch(), _runtime(python_version="3.13.13"), SHA),
    "not-isolated": (_dispatch(), _runtime(interpreter_flags=""), SHA),
    "unverified-install": (_dispatch(), _runtime(installed_files_sha256=""), SHA),
    "bad-run-id": (_dispatch(run_id="x"), _runtime(), SHA),
}


@pytest.mark.parametrize("case", sorted(DISPATCH_REFUSALS))
def test_every_dispatch_deviation_refuses(case: str) -> None:
    dispatch, runtime, expected = DISPATCH_REFUSALS[case]
    with pytest.raises(ProvenanceRefused, match="dispatch does not verify"):
        route.verify_dispatch(dispatch, runtime, expected_sha=expected)


def test_different_migration_bytes_refuse_before_any_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(route, "MIGRATION_SHA256", "0" * 64)
    with pytest.raises(ProvenanceRefused, match="not the reviewed"):
        route.migration_bytes()


# ------------------------------------------------------------------------ the entrypoint


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Isolation, attestation and the driver, replaced by recorders. Nothing real is entered."""

    events: list[str] = []

    def _enter(wheelhouse: str):
        events.append(f"enter:{wheelhouse}")
        return "isolation-report"

    def _attest(expected_sha, environ, isolation):
        events.append(f"attest:{expected_sha}")
        return {"dispatch_verified": True, "workflow": route.WORKFLOW}

    monkeypatch.setattr(route, "enter_isolated_runtime", _enter)
    monkeypatch.setattr(route, "attest_dispatch", _attest)
    monkeypatch.setattr(route, "attest_loaded_modules", lambda isolation: events.append("modules"))
    return events


def _argv(mode: str, tmp_path: Path, **overrides: str) -> list[str]:
    options = {
        "mode": mode,
        "expected-sha": SHA,
        "confirm": route.CONFIRMATION,
        "wheelhouse": "/synthetic/runner-temp/section-5a-wheels",
        "report": str(tmp_path / "report.json"),
        **overrides,
    }
    return [f"--{name}={value}" for name, value in options.items() if value is not None]


def _install_driver(monkeypatch: pytest.MonkeyPatch, database: FakeDatabase, events: list[str]):
    def _load():
        events.append("driver")
        return database

    monkeypatch.setattr(route, "load_driver", _load)


def _report(tmp_path: Path) -> dict[str, Any]:
    return json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))


def test_apply_refuses_without_the_exact_token_before_anything_is_entered(
    calls: list[str], tmp_path: Path
) -> None:
    for token in ("", "apply", route.CONFIRMATION.lower(), apply_0012.CONFIRMATION):
        assert route.main(_argv("apply", tmp_path, confirm=token), environ={}) == 2
    assert calls == []
    report = _report(tmp_path)
    assert report["outcome"] == "REFUSED" and report["committed"] is False
    assert report["detail"].startswith("migration 0013 refused; nothing is applied: ")


def test_attest_mode_touches_no_database(
    calls: list[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = FakeDatabase(healthy_results())
    _install_driver(monkeypatch, database, calls)
    monkeypatch.setattr(
        "crypto_probability_engine.runtime_isolation.loaded_dynamic_helpers", lambda: []
    )
    code = route.main(
        _argv("attest", tmp_path, confirm=""), environ={"SUPABASE_DB_URL": DATABASE_URL}
    )
    assert code == 0
    assert calls == [
        "enter:/synthetic/runner-temp/section-5a-wheels",
        f"attest:{SHA}",
        "modules",
        "driver",
        "modules",
    ]
    assert database.connects == [] and database.statements == []
    report = _report(tmp_path)
    assert report["touches_database"] is False
    assert report["migration_sha256"] == route.MIGRATION_SHA256


def test_apply_without_a_database_url_refuses_before_the_driver_loads(
    calls: list[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = FakeDatabase(healthy_results())
    _install_driver(monkeypatch, database, calls)
    assert route.main(_argv("apply", tmp_path), environ={}) == 2
    assert "driver" not in calls and database.connects == []


def test_a_full_apply_reports_raw_results_without_the_url(
    calls: list[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = FakeDatabase(healthy_results())
    _install_driver(monkeypatch, database, calls)
    assert route.main(_argv("apply", tmp_path), environ={"SUPABASE_DB_URL": DATABASE_URL}) == 0
    assert database.connects == [(DATABASE_URL, {"connect_timeout": 8, "prepare_threshold": None})]
    assert database.commits == 1
    report = _report(tmp_path)
    assert report["outcome"] == "APPLIED" and report["mode"] == "apply"
    assert [row["table"] for row in report["post_tables"]] == list(route.TABLES)
    output = capsys.readouterr()
    written = (tmp_path / "report.json").read_text(encoding="utf-8") + output.out + output.err
    assert DATABASE_URL not in written and "NEVER-SHOWN-SECRET" not in written


def test_a_refused_apply_reports_what_it_saw_and_commits_nothing(
    calls: list[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = FakeDatabase(healthy_results(first_apply=False))
    _install_driver(monkeypatch, database, calls)
    assert route.main(_argv("apply", tmp_path), environ={"SUPABASE_DB_URL": DATABASE_URL}) == 2
    report = _report(tmp_path)
    assert report["outcome"] == "REFUSED" and report["committed"] is False
    assert route.NOT_A_FIRST_APPLY in report["detail"]
    assert report["captured"]["pre_relations"][0]["relations_in_public"] == 1


def test_an_unexpected_failure_withholds_its_message_because_it_can_name_the_host(
    calls: list[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = FakeDatabase(
        healthy_results(), fail_on={route.ROLES_SQL: RuntimeError(f"cannot reach {DATABASE_URL}")}
    )
    _install_driver(monkeypatch, database, calls)
    assert route.main(_argv("apply", tmp_path), environ={"SUPABASE_DB_URL": DATABASE_URL}) == 1
    report = _report(tmp_path)
    assert report["outcome"] == "FAILED" and report["error_type"] == "RuntimeError"
    assert DATABASE_URL not in json.dumps(report)


def test_a_commit_that_fails_in_flight_is_reported_as_unknown(
    calls: list[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = FakeDatabase(healthy_results())
    database.fail_commit = RuntimeError("connection lost")
    _install_driver(monkeypatch, database, calls)
    assert route.main(_argv("apply", tmp_path), environ={"SUPABASE_DB_URL": DATABASE_URL}) == 1
    assert _report(tmp_path)["committed"] == route.COMMIT_UNKNOWN


# ------------------------------------------------------------------------ the rehearsal


def _rehearsal_results() -> dict:
    results = healthy_results(REHEARSAL_SERVER)
    # First apply: nothing named so yet, then the new relations. Second apply: already there.
    results[route.RELATIONS_SQL] = Each([relation_rows(0), relation_rows(1), relation_rows(1)])
    return results


def test_a_rehearsal_applies_once_and_proves_a_second_apply_refuses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = FakeDatabase(_rehearsal_results())
    _install_driver(monkeypatch, database, [])
    code = route.main(
        _argv("rehearse", tmp_path, wheelhouse=""),
        environ={route.REHEARSAL_URL_VARIABLE: REHEARSAL_URL},
    )
    assert code == 0
    report = _report(tmp_path)
    assert report["outcome"] == "REHEARSED"
    assert route.NOT_A_FIRST_APPLY in report["second_apply_refusal"]
    assert database.commits == 1 and database.rollbacks == 1
    assert (
        database.connects
        == [
            (REHEARSAL_URL, {"connect_timeout": 8, "prepare_threshold": None}),
        ]
        * 2
    )


def test_a_rehearsal_whose_second_apply_succeeds_refuses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    results = _rehearsal_results()
    results[route.RELATIONS_SQL] = Each(
        [relation_rows(0), relation_rows(1), relation_rows(0), relation_rows(1)]
    )
    _install_driver(monkeypatch, FakeDatabase(results), [])
    code = route.main(
        _argv("rehearse", tmp_path, wheelhouse=""),
        environ={route.REHEARSAL_URL_VARIABLE: REHEARSAL_URL},
    )
    assert code == 2
    assert "one-shot property does not hold" in _report(tmp_path)["detail"]


@pytest.mark.parametrize(
    "url",
    [
        "",
        DATABASE_URL,
        "postgresql://localhost/migration_0013_rehearsal",
        "postgresql:///migration_0013_rehearsal?host=/tmp",
        REHEARSAL_URL + "&sslmode=disable",
    ],
)
def test_the_rehearsal_only_ever_reaches_a_local_socket(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, url: str
) -> None:
    database = FakeDatabase(_rehearsal_results())
    _install_driver(monkeypatch, database, [])
    code = route.main(
        _argv("rehearse", tmp_path, wheelhouse=""), environ={route.REHEARSAL_URL_VARIABLE: url}
    )
    assert code == 2 and database.connects == []


def test_the_rehearsal_never_runs_beside_the_production_secret(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = FakeDatabase(_rehearsal_results())
    _install_driver(monkeypatch, database, [])
    code = route.main(
        _argv("rehearse", tmp_path, wheelhouse=""),
        environ={route.REHEARSAL_URL_VARIABLE: REHEARSAL_URL, "SUPABASE_DB_URL": DATABASE_URL},
    )
    assert code == 2 and database.connects == []
    assert "production database secret" in _report(tmp_path)["detail"]


def test_the_rehearsal_is_isolated_when_given_the_wheelhouse(
    calls: list[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = FakeDatabase(_rehearsal_results())
    _install_driver(monkeypatch, database, calls)
    code = route.main(
        _argv("rehearse", tmp_path, confirm=""),
        environ={route.REHEARSAL_URL_VARIABLE: REHEARSAL_URL},
    )
    assert code == 0
    assert calls == ["enter:/synthetic/runner-temp/section-5a-wheels", "driver", "modules"]


def test_the_loaded_module_check_covers_the_pin_and_this_script(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from crypto_probability_engine import runtime_isolation
    from crypto_probability_engine.oos.evaluation.evaluator_pin import pinned_files

    seen: dict[str, Any] = {}

    def _attest(report, *, pinned, root):
        seen.update(pinned=tuple(pinned), root=root)
        return 1

    monkeypatch.setattr(runtime_isolation, "attest_loaded_modules", _attest)
    route.attest_loaded_modules("isolation")
    assert seen["pinned"] == (*pinned_files(ROOT), route.SCRIPT)
    assert Path(seen["root"]).resolve() == ROOT


# ------------------------------------------------------------------------ the process


def _scrubbed_environment(extra: dict[str, str]) -> dict[str, str]:
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("GITHUB_", "RUNNER_", "SUPABASE_", "PYTHON", "MIGRATION_"))
        and key != "ImageOS"
    }
    environment.update(extra)
    return environment


def test_an_unisolated_process_refuses_before_any_database_access(tmp_path: Path) -> None:
    report = tmp_path / "report.json"
    completed = subprocess.run(
        [sys.executable, "-B", route.SCRIPT, *_argv("apply", tmp_path, report=str(report))],
        cwd=ROOT,
        env=_scrubbed_environment({"SUPABASE_DB_URL": DATABASE_URL}),
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    assert completed.returncode == 2, completed.stderr
    assert "python -I -S -B" in completed.stderr
    recorded = report.read_text(encoding="utf-8")
    assert json.loads(recorded)["outcome"] == "REFUSED"
    for text in (recorded, completed.stdout, completed.stderr):
        assert "NEVER-SHOWN-SECRET" not in text and "never-contacted" not in text


def test_no_connection_of_the_route_uses_server_side_prepared_statements() -> None:
    """The probes repeat their savepoint statements 42 times: never prepared behind a pooler."""

    assert dict(route.CONNECT_OPTIONS) == {"connect_timeout": 8, "prepare_threshold": None}
    repeated = {route.PROBE_SAVEPOINT_SQL, route.PROBE_ROLLBACK_SQL, route.PROBE_RELEASE_SQL}
    database, _outcome = apply(healthy_results())
    for statement in repeated:
        assert database.statements.count(statement) == len(route.CONSTRAINT_PROBES) > 5
    source = (ROOT / route.SCRIPT).read_text(encoding="utf-8")
    assert source.count("driver.connect(") == 2
    assert source.count("**CONNECT_OPTIONS)") == 2
