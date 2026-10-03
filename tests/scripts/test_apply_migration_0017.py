"""The one-shot apply of migration 0017 (Phase 3's wider bundle, W-A). No database is contacted.

Every database interaction runs against the psycopg-3-shaped fake of migration 0015's test:
- a connection used as a context manager commits on success and rolls back on an exception;
- a statement is recorded with its parameters;
- a check read before and after the migration can return different rows.
The real PostgreSQL rehearsals run in three places:
- .github/workflows/migration-0017-rehearsal.yml (every pull request);
- inside the dispatch job (.github/workflows/apply-migration-0017.yml), before the secret is
  handed to any step;
- .github/workflows/privilege-rehearsal.yml (W1-W9, the function behind a real PostgREST).
"""

from __future__ import annotations

import ast
import hashlib
import inspect
import json
import re
from pathlib import Path
from typing import Any

import pytest

from crypto_probability_engine.runtime_isolation import ProvenanceRefused
from scripts import apply_migration_0011 as apply_0011
from scripts import apply_migration_0016 as apply_0016
from scripts import apply_migration_0017 as apply_0017
from scripts.privilege_rehearsal import rehearse
from tests.scripts.test_apply_migration_0015 import Each, FakeDatabase

ROOT = Path(__file__).resolve().parents[2]
MIGRATION_BYTES = (ROOT / apply_0017.MIGRATION).read_bytes()
MIGRATION_SQL = MIGRATION_BYTES.decode("utf-8")
DATABASE_URL = "postgresql://owner:NEVER-SHOWN-SECRET@db.never-contacted.invalid:5432/postgres"
REHEARSAL_URL = "postgresql:///migration_0017_rehearsal?host=/var/run/postgresql"
PRODUCTION_SERVER = 170006
REHEARSAL_SERVER = 160010
APPLIER = "postgres"
OWNER = "ucpe_bundle_owner"
ALL = list(apply_0017.table_privileges_for(PRODUCTION_SERVER))
CHECK_NAMES = (
    "server",
    "roles",
    "memberships",
    "grants",
    "sequence_grants",
    "schema",
    "schema_grants",
    "policies",
    "function",
    "forecast",
    "other_functions",
    "security",
    "schema_fingerprint",
    "event_triggers",
)


# ------------------------------------------------------------------------ production after 0016


def role_row(name: str, **changes: Any) -> tuple:
    values = {
        "superuser": False,
        "inherit": False,
        "createrole": False,
        "createdb": False,
        "login": False,
        "replication": False,
        "bypassrls": False,
        "is_applying_role": False,
    }
    values.update(changes)
    return (name, *(values[field] for field in apply_0017.ROLE_FIELDS[1:]))


AUTHENTICATOR_ROW = role_row("authenticator", login=True)
APPLIER_ROW = role_row(
    APPLIER,
    inherit=True,
    createrole=True,
    createdb=True,
    login=True,
    replication=True,
    bypassrls=True,
    is_applying_role=True,
)
ROLES = [AUTHENTICATOR_ROW, APPLIER_ROW, *(role_row(role) for role in apply_0017.NEW_ROLES)]
WRITER_MEMBERSHIP = ("ucpe_api_writer", "authenticator", True, False, False, True)
CREATOR_MEMBERSHIPS = [(role, APPLIER, False, True, False, False) for role in apply_0017.NEW_ROLES]
MEMBERSHIPS = [
    *((api, "authenticator", False, False, False, True) for api in apply_0017.API_ROLES),
    WRITER_MEMBERSHIP,
    *CREATOR_MEMBERSHIPS,
]


def grant_rows(expected: dict[str, dict[str, tuple[str, ...]]]) -> list[tuple]:
    return [
        (role, table, list(expected.get(role, {}).get(table, ())))
        for role in apply_0017.NEW_ROLES
        for table in apply_0017.TABLES
    ]


GRANTS_PRE = grant_rows(apply_0017.EXPECTED_GRANTS_0016)
GRANTS_POST = grant_rows(apply_0017.EXPECTED_GRANTS)
SEQUENCE_GRANTS = [
    (role, sequence, list(apply_0017.EXPECTED_SEQUENCE_GRANTS.get(role, {}).get(sequence, ())))
    for role in apply_0017.NEW_ROLES
    for sequence in apply_0017.SEQUENCES
]
SCHEMA = [
    ("public", "pg_database_owner", True, True, True, False, True, False, True, False, True, False)
]
SCHEMA_GRANTS = [(role, True, False) for role in apply_0017.NEW_ROLES]
POLICIES_PRE = [
    (item, *values)
    for item, values in sorted(
        apply_0017.expected_policies(apply_0017.EXPECTED_GRANTS_0016).items()
    )
]
POLICIES_POST = [(item, *values) for item, values in sorted(apply_0017.expected_policies().items())]
BUNDLE_ACL = ["service_role=EXECUTE", "ucpe_api_writer=EXECUTE", f"{OWNER}=EXECUTE"]
FUNCTION = (
    apply_0017.FUNCTION_ARGUMENTS,
    "jsonb",
    "plpgsql",
    True,
    "f",
    "v",
    list(apply_0017.FUNCTION_CONFIG),
    OWNER,
    False,
    apply_0017.FUNCTION_SOURCE,
    BUNDLE_ACL,
)
FORECAST_POST = (
    apply_0017.FORECAST_ARGUMENTS,
    "jsonb",
    "plpgsql",
    True,
    "f",
    "v",
    list(apply_0017.FUNCTION_CONFIG),
    OWNER,
    False,
    apply_0017.FORECAST_SOURCE,
    ["service_role=EXECUTE", "ucpe_api_writer=EXECUTE", f"{OWNER}=EXECUTE"],
)
OTHER_FUNCTIONS = [
    (
        "reject_core_evidence_mutation()",
        APPLIER,
        False,
        ["search_path=pg_catalog, pg_temp"],
        "0" * 32,
        f"{{{APPLIER}=X/{APPLIER}}}",
    ),
]


def _policy_counts(policies: list[tuple]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item, *_values in policies:
        counts[item.split("/", 1)[0]] = counts.get(item.split("/", 1)[0], 0) + 1
    return counts


def security_row(table: str, *, privileges: list[str] = ALL, **changes: Any) -> tuple:
    values = {
        "relations_named_so": 1,
        "relkind": "r",
        "owned_by_applying_role": True,
        "row_level_security": True,
        "row_level_security_forced": False,
        "policies": 0,
        "public_has_a_privilege": False,
        "column_grant_to_public_anon_or_authenticated": False,
        "anon": [],
        "authenticated": [],
        "service_role": list(privileges),
    }
    values.update(changes)
    return (table, *(values[field] for field in apply_0017.SECURITY_FIELDS[1:]))


SECURITY_PRE = [
    security_row(table, policies=_policy_counts(POLICIES_PRE).get(table, 0))
    for table in apply_0017.TABLES
]
SECURITY_POST = [
    security_row(table, policies=_policy_counts(POLICIES_POST).get(table, 0))
    for table in apply_0017.TABLES
]
FINGERPRINT = [
    ("predictions/trigger/trg_pred_reject_update", "O 19 reject_core_evidence_mutation"),
    ("watchlist/column/normalized_symbol", "text notnull=true default= acl="),
]
EVENT_TRIGGERS = [("pgrst_ddl_watch", "ddl_command_end", "O", "extensions.pgrst_ddl_watch", "")]


def healthy_results(version: int = PRODUCTION_SERVER, **overrides: Any) -> dict[str, Any]:
    """A first apply on production as it is after 0016: every pre read, then every post read."""

    pre_post = {
        "server": ([(version,)], [(version,)]),
        "roles": (ROLES, ROLES),
        "memberships": (MEMBERSHIPS, MEMBERSHIPS),
        "grants": (GRANTS_PRE, GRANTS_POST),
        "sequence_grants": (SEQUENCE_GRANTS, SEQUENCE_GRANTS),
        "schema": (SCHEMA, SCHEMA),
        "schema_grants": (SCHEMA_GRANTS, SCHEMA_GRANTS),
        "policies": (POLICIES_PRE, POLICIES_POST),
        "function": ([FUNCTION], [FUNCTION]),
        "forecast": ([], [FORECAST_POST]),
        "other_functions": (OTHER_FUNCTIONS, OTHER_FUNCTIONS),
        "security": (SECURITY_PRE, SECURITY_POST),
        "schema_fingerprint": (FINGERPRINT, FINGERPRINT),
        "event_triggers": (EVENT_TRIGGERS, EVENT_TRIGGERS),
    }
    pre_post.update(overrides)
    results: dict[str, Any] = {
        apply_0017.ROLES_SQL: [(3,)],
        apply_0017.SERVER_VERSION_SQL: [(version,)],
    }
    for name, query, _fields in apply_0017.read_only_checks(version):
        before, after = pre_post[name]
        results[query] = Each([before, after])
    return results


def _apply(database: FakeDatabase) -> tuple[dict[str, Any], dict[str, Any]]:
    captured: dict[str, Any] = {}
    outcome = apply_0017.apply_in_one_transaction(
        lambda: database.connect(DATABASE_URL), MIGRATION_SQL, captured
    )
    return outcome, captured


def _dicts(fields: tuple[str, ...], rows: list[tuple]) -> list[dict[str, Any]]:
    return [
        {
            field: list(value) if isinstance(value, (list, tuple)) else value
            for field, value in zip(fields, row, strict=True)
        }
        for row in rows
    ]


def _state(pre_overrides: dict[str, list] | None = None, **overrides: Any):
    """The healthy pre and post reads as the pure checks see them, with ``overrides`` (post)."""

    fields = {name: checked for name, _query, checked in apply_0017.read_only_checks(170006)}
    results = healthy_results()
    pre, post = {}, {}
    for name, query, _fields in apply_0017.read_only_checks(170006):
        before, after = results[query]
        pre[name] = _dicts(fields[name], (pre_overrides or {}).get(name, before))
        post[name] = _dicts(fields[name], overrides.get(name, after))
    return pre, post


def _with(row: tuple, fields: tuple[str, ...], **changes: Any) -> list[tuple]:
    values = dict(zip(fields, row, strict=True))
    values.update(changes)
    return [tuple(values[field] for field in fields)]


def _function(**changes: Any) -> list[tuple]:
    return _with(FUNCTION, apply_0017.FUNCTION_FIELDS, **changes)


def _forecast(**changes: Any) -> list[tuple]:
    return _with(FORECAST_POST, apply_0017.FUNCTION_FIELDS, **changes)


def _grants_with(rows: list[tuple], role: str, table: str, privileges: list[str]) -> list[tuple]:
    return [(r, t, privileges if (r, t) == (role, table) else p) for r, t, p in rows]


# ------------------------------------------------------------------------ what the route is


def test_the_script_imports_only_the_standard_library_at_module_level() -> None:
    tree = ast.parse((ROOT / apply_0017.SCRIPT).read_text(encoding="utf-8"))
    imported = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            imported |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert imported <= {
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


def test_it_names_itself_its_workflow_and_the_reviewed_bytes() -> None:
    assert apply_0017.SCRIPT == "scripts/apply_migration_0017.py"
    assert apply_0017.WORKFLOW == ".github/workflows/apply-migration-0017.yml"
    assert (ROOT / apply_0017.WORKFLOW).is_file()
    assert apply_0017.MIGRATION == "migrations/0017_forecast_bundle_rpc.sql"
    assert hashlib.sha256(MIGRATION_BYTES).hexdigest() == apply_0017.MIGRATION_SHA256
    assert apply_0017.CONFIRMATION == "APPLY-MIGRATION-0017-ONCE"
    assert apply_0017.REHEARSAL_URL_VARIABLE == "MIGRATION_0017_REHEARSAL_URL"


def test_its_advisory_lock_is_its_own() -> None:
    keys = {}
    for path in sorted((ROOT / "scripts").glob("apply_*.py")):
        found = re.findall(r"pg_advisory_xact_lock\((\d+)\)", path.read_text(encoding="utf-8"))
        keys.update({key: path.name for key in found})
    assert keys["5000017"] == "apply_migration_0017.py"
    assert list(keys.values()).count("apply_migration_0017.py") == 1


# The trust machinery is 0011's, copied verbatim: a reviewed route, not a new one.
SHARED = (
    "table_privileges_for",
    "_held",
    "_security_sql",
    "build_parser",
    "ensure_source_path",
    "enter_isolated_runtime",
    "observe",
    "verify_dispatch",
    "attest_dispatch",
    "attest_loaded_modules",
    "load_driver",
    "migration_bytes",
    "main",
    "_run",
    "_count_after",
    "_unchanged_failures",
    "_read_checks",
    "_rows",
    "_plain",
    "_row",
    "_git",
    "_refusal_record",
    "_commit_state",
    "_is_refusal",
    "_write_report",
)


@pytest.mark.parametrize("name", SHARED)
def test_its_trust_machinery_is_0011_s_verbatim(name: str) -> None:
    assert inspect.getsource(getattr(apply_0017, name)) == inspect.getsource(
        getattr(apply_0011, name)
    ), name


def test_its_transaction_and_rehearsal_are_0011_s_up_to_the_migration_number() -> None:
    for name in ("apply_in_one_transaction", "_refusal"):
        ours = inspect.getsource(getattr(apply_0017, name))
        theirs = inspect.getsource(getattr(apply_0011, name)).replace("0011", "0017")
        assert ours == theirs, name
    ours = inspect.getsource(apply_0017.rehearse).split('"""')
    theirs = inspect.getsource(apply_0011.rehearse).replace("0011", "0017").split('"""')
    assert ours[0] == theirs[0] and ours[2] == theirs[2], "only the docstring differs"
    for constant in (
        "TIMEOUT_STATEMENTS",
        "API_ROLES",
        "TABLE_PRIVILEGES",
        "MINIMUM_SERVER_VERSION",
        "MAINTAIN_SINCE_SERVER_VERSION",
        "SECURITY_FIELDS",
        "PINNED_PYTHON",
        "EXPECTED_REPOSITORY",
        "REQUIRED_REF",
        "REQUIRED_EVENT",
    ):
        assert getattr(apply_0017, constant) == getattr(apply_0011, constant), constant


@pytest.mark.parametrize("version", [PRODUCTION_SERVER, REHEARSAL_SERVER])
def test_its_checks_are_0016_s_reviewed_ones_plus_the_new_function_s(version: int) -> None:
    ours = {name: (query, fields) for name, query, fields in apply_0017.read_only_checks(version)}
    theirs = {name: (query, fields) for name, query, fields in apply_0016.read_only_checks(version)}
    for name in set(theirs) - {"function", "other_functions"}:
        assert ours[name] == theirs[name], name
    assert ours["function"] == theirs["function"], "the bundle RPC is read exactly as 0016 read it"
    assert ours["forecast"] == (
        apply_0016.FUNCTION_SQL.replace("'save_prediction_bundle'", "'save_forecast_bundle'"),
        apply_0016.FUNCTION_FIELDS,
    )
    assert ours["other_functions"][0] == theirs["other_functions"][0].replace(
        "p.proname <> 'save_prediction_bundle'",
        "p.proname <> 'save_prediction_bundle' AND p.proname <> 'save_forecast_bundle'",
    )
    for constant in (
        "NEW_ROLES",
        "TABLES",
        "SEQUENCES",
        "EXPECTED_SEQUENCE_GRANTS",
        "FUNCTION",
        "FUNCTION_ARGUMENTS",
        "FUNCTION_CONFIG",
        "FUNCTION_SOURCE",
        "NOT_A_FIRST_APPLY",
    ):
        assert getattr(apply_0017, constant) == getattr(apply_0016, constant), constant


# ------------------------------------------------------------------------ it matches the migrations


def _statements(sql: str) -> list[str]:
    body = "\n".join(line.split("--", 1)[0] for line in sql.splitlines())
    body = re.sub(r"\$(\w*)\$.*?\$\1\$", "$$ $$", body, flags=re.S)
    return [" ".join(part.split()) for part in re.split(r";\s*(?=\n|$)", body) if part.strip()]


def _grants(sql: str, kind: str) -> dict[str, dict[str, tuple[str, ...]]]:
    grants: dict[str, dict[str, set[str]]] = {}
    for statement in _statements(sql):
        match = re.fullmatch(rf"GRANT ([A-Z, ]+) ON {kind} (.+) TO (\w+)", statement)
        if match:
            for name in match.group(2).split(","):
                held = grants.setdefault(match.group(3), {}).setdefault(
                    name.strip().removeprefix("public."), set()
                )
                held |= {p.strip() for p in match.group(1).split(",")}
    return {
        role: {name: tuple(sorted(p)) for name, p in names.items()}
        for role, names in grants.items()
    }


def test_its_expected_grants_are_0016_s_plus_the_migration_s_and_the_rehearsal_s() -> None:
    assert apply_0017.EXPECTED_GRANTS_0016 == apply_0016.EXPECTED_GRANTS
    assert _grants(MIGRATION_SQL, "TABLE") == {OWNER: apply_0017.ADDED_GRANTS}
    assert _grants(MIGRATION_SQL, "SEQUENCE") == {}
    assert apply_0017.EXPECTED_GRANTS == {
        **apply_0016.EXPECTED_GRANTS,
        OWNER: {**apply_0016.EXPECTED_GRANTS[OWNER], **apply_0017.ADDED_GRANTS},
    }
    assert {t: tuple(sorted(p)) for t, p in rehearse.WIDE_OWNER_TABLES.items()} == (
        apply_0017.EXPECTED_GRANTS[OWNER]
    )


def test_its_expected_policies_are_0016_s_and_the_migration_s() -> None:
    created = set()
    for statement in _statements(MIGRATION_SQL):
        match = re.fullmatch(
            r"CREATE POLICY (\w+) ON public\.(\w+) FOR (\w+) TO (\w+) .+", statement
        )
        if match:
            created.add(f"{match.group(2)}/{match.group(1)}")
    assert created == set(apply_0017.added_policies()) and len(created) == 4
    assert apply_0017.expected_policies(apply_0017.EXPECTED_GRANTS_0016) == (
        apply_0016.expected_policies()
    )
    assert len(apply_0017.expected_policies()) == 44


def test_it_requires_0015_s_body_and_creates_exactly_the_migration_s_function() -> None:
    fifteen = (ROOT / apply_0017.FUNCTION_MIGRATION).read_text(encoding="utf-8")
    assert re.search(r"AS \$function\$(.*?)\$function\$;", fifteen, re.S).group(1) == (
        apply_0017.FUNCTION_SOURCE
    )
    bodies = re.findall(r"AS \$function\$(.*?)\$function\$;", MIGRATION_SQL, re.S)
    assert bodies == [apply_0017.FORECAST_SOURCE]
    every = _statements(MIGRATION_SQL)
    reference = f"{apply_0017.FORECAST_REFERENCE}(jsonb, jsonb, jsonb, jsonb, jsonb)"
    created = [s for s in every if s.startswith("CREATE FUNCTION")]
    assert len(created) == 1
    assert created[0].startswith(f"CREATE FUNCTION {apply_0017.FORECAST_REFERENCE}(")
    for parameter in apply_0017.FORECAST_ARGUMENTS.split(", "):
        assert parameter in created[0], parameter
    assert "SECURITY DEFINER SET search_path = pg_catalog, pg_temp" in created[0]
    assert [s for s in every if s.startswith("ALTER FUNCTION")] == [
        f"ALTER FUNCTION {reference} OWNER TO {OWNER}"
    ]
    assert "CREATE OR REPLACE FUNCTION" not in MIGRATION_SQL
    assert "save_prediction_bundle(jsonb, jsonb, jsonb)" not in " ".join(
        s for s in every if s.startswith(("ALTER", "GRANT", "REVOKE"))
    ), "0017 never touches the bundle RPC"


def test_the_tables_are_every_table_of_migrations_0001_to_0016() -> None:
    created = set()
    for path in sorted((ROOT / "migrations").glob("*.sql")):
        if path.name < "0018":
            created |= set(
                re.findall(
                    r"CREATE TABLE IF NOT EXISTS (?:public\.)?([a-z_0-9]+)", path.read_text()
                )
            )
    assert sorted(created) == list(apply_0017.TABLES)
    assert "CREATE TABLE" not in MIGRATION_SQL


def test_the_space_role_keeps_exactly_the_live_f1_uor_grants() -> None:
    space = apply_0017.EXPECTED_GRANTS["ucpe_space_db"]
    assert space == apply_0016.EXPECTED_GRANTS["ucpe_space_db"]
    assert space["automation_credential"] == ("SELECT",)
    assert space["automation_radar_ledger"] == ("INSERT", "SELECT", "UPDATE")


# ------------------------------------------------------------------------ the checks read only


FORBIDDEN = re.compile(
    r"\b(INSERT|UPDATE|DELETE|ALTER|CREATE|DROP|GRANT|REVOKE|TRUNCATE|COPY|CALL|DO|SET|VALIDATE)\b"
)


def _without_literals(query: str) -> str:
    return re.sub(r"'(?:[^']|'')*'", "''", query)


@pytest.mark.parametrize("version", [PRODUCTION_SERVER, REHEARSAL_SERVER])
def test_every_check_is_a_read_only_catalog_query(version: int) -> None:
    queries = [query for _name, query, _fields in apply_0017.read_only_checks(version)]
    queries += [apply_0017.ROLES_SQL, apply_0017.SERVER_VERSION_SQL]
    for query in queries:
        bare = _without_literals(query)
        assert query.lstrip().startswith("SELECT"), query[:60]
        assert not FORBIDDEN.search(bare), (FORBIDDEN.search(bare).group(0), query[:80])
        assert "%s" not in query and "%(" not in query, "no parameters"
        for source in re.findall(r"\b(?:FROM|JOIN)\s+([a-z_.]+)", bare):
            assert source.startswith("pg_catalog.") or source == "", (source, query[:80])
        assert "public." not in bare, query[:80]


@pytest.mark.parametrize("version", [PRODUCTION_SERVER, REHEARSAL_SERVER])
def test_no_check_orders_by_a_column_position(version: int) -> None:
    for _name, query, _fields in apply_0017.read_only_checks(version):
        assert not re.search(r"ORDER BY \s*\d", query), query[-80:]
        assert not re.search(r",\s*\d+\s+COLLATE", query), query[-80:]


def test_the_checks_cover_every_table_role_and_both_functions() -> None:
    names = [name for name, _query, _fields in apply_0017.read_only_checks(PRODUCTION_SERVER)]
    assert tuple(names) == CHECK_NAMES
    for table in apply_0017.TABLES:
        assert f"('{table}')" in apply_0017.security_sql(PRODUCTION_SERVER)
        assert f"('{table}')" in apply_0017.grants_sql(PRODUCTION_SERVER)
        assert f"('{table}')" in apply_0017.SCHEMA_FINGERPRINT_SQL
    for role in apply_0017.NEW_ROLES:
        assert f"'{role}'" in apply_0017.ROLES_STATE_SQL
    assert "'MAINTAIN'" in apply_0017.grants_sql(PRODUCTION_SERVER)
    assert "'MAINTAIN'" not in apply_0017.grants_sql(REHEARSAL_SERVER)
    assert "a.set_option" in apply_0017.memberships_sql(PRODUCTION_SERVER)


# ------------------------------------------------------------------------ the pure verdicts


def test_a_healthy_first_apply_has_no_pre_or_post_failure() -> None:
    pre, post = _state()
    assert apply_0017.pre_check_failures(pre) == []
    assert apply_0017.post_check_failures(pre, post) == []


@pytest.mark.parametrize(
    ("name", "rows"),
    [
        ("grants", GRANTS_POST),
        ("policies", POLICIES_POST),
        ("forecast", [FORECAST_POST]),
    ],
)
def test_a_second_apply_is_refused_as_not_a_first_apply(name: str, rows: list[tuple]) -> None:
    pre, _post = _state(pre_overrides={name: rows})
    failures = apply_0017.pre_check_failures(pre)
    assert failures and all(apply_0017.NOT_A_FIRST_APPLY in f for f in failures), failures


@pytest.mark.parametrize(
    ("name", "rows", "expected"),
    [
        ("server", [(150010,)], "is not PostgreSQL 16 or later"),
        ("roles", [AUTHENTICATOR_ROW, APPLIER_ROW], "migration 0016 is not applied: the role"),
        ("roles", ROLES[1:], "authenticator role does not exist"),
        (
            "roles",
            [*ROLES[:-1], role_row("ucpe_space_db", login=True)],
            "the role ucpe_space_db holds login",
        ),
        ("roles", [AUTHENTICATOR_ROW, *ROLES[2:]], "the applying role was read 0 times"),
        (
            "memberships",
            [row for row in MEMBERSHIPS if row != WRITER_MEMBERSHIP],
            "authenticator's membership in the writer is not 0016's",
        ),
        (
            "memberships",
            [
                ("ucpe_api_writer", "authenticator", True, False, True, True)
                if row == WRITER_MEMBERSHIP
                else row
                for row in MEMBERSHIPS
            ],
            "authenticator's membership in the writer is not 0016's",
        ),
        (
            "memberships",
            [row for row in MEMBERSHIPS if row[:2] != (OWNER, APPLIER)],
            f"the applying role holds no ADMIN on {OWNER}",
        ),
        (
            "grants",
            _grants_with(GRANTS_PRE, "ucpe_api_writer", "predictions", ["INSERT", "SELECT"]),
            "ucpe_api_writer holds ['INSERT', 'SELECT'] on the table predictions before the apply",
        ),
        (
            "grants",
            _grants_with(GRANTS_PRE, OWNER, "analysis_runs", ["INSERT", "SELECT"]),
            f"{OWNER} holds ['INSERT', 'SELECT'] on the table analysis_runs before the apply",
        ),
        ("grants", GRANTS_PRE[:-1], "the table privileges were read for"),
        (
            "sequence_grants",
            [(r, s, ["USAGE"]) for r, s, _p in SEQUENCE_GRANTS],
            "on the sequence app_events_id_seq before the apply",
        ),
        (
            "schema_grants",
            [(r, True, r == OWNER) for r in apply_0017.NEW_ROLES],
            f"{OWNER} holds (True, True) (USAGE, CREATE) on schema public",
        ),
        ("policies", POLICIES_PRE[1:], "is missing before the apply"),
        (
            "policies",
            [(POLICIES_PRE[0][0], "*", *POLICIES_PRE[0][2:]), *POLICIES_PRE[1:]],
            f"the policy {POLICIES_PRE[0][0]} is",
        ),
        ("function", [], "exists 0 times, not once"),
        ("function", _function(security_definer=False), "security_definer is False"),
        ("function", _function(owner=APPLIER, owned_by_applying_role=True), "owner is 'postgres'"),
        ("function", _function(source="BEGIN RETURN NULL; END;"), "source is"),
        (
            "function",
            _function(acl=["service_role=EXECUTE", f"{OWNER}=EXECUTE"]),
            "ucpe_api_writer may not execute it",
        ),
        (
            "function",
            _function(acl=[*BUNDLE_ACL, "anon=EXECUTE"]),
            "anon=EXECUTE may execute it",
        ),
        (
            "schema",
            [("public", "pg_database_owner", False, True, *SCHEMA[0][4:])],
            "may not CREATE in schema public",
        ),
        (
            "schema",
            [("public", "pg_database_owner", True, False, *SCHEMA[0][4:])],
            "does not hold schema public's owner privileges",
        ),
        (
            "security",
            [security_row(t, owned_by_applying_role=t != "watchlist") for t in apply_0017.TABLES],
            "watchlist: is not owned by the applying role",
        ),
        ("security", SECURITY_PRE[:-1], "the tables read were"),
    ],
)
def test_a_database_not_ready_for_0017_refuses(name: str, rows: list[tuple], expected: str) -> None:
    pre, _post = _state(pre_overrides={name: rows})
    failures = apply_0017.pre_check_failures(pre)
    assert failures and any(expected in failure for failure in failures), failures
    assert not all(apply_0017.NOT_A_FIRST_APPLY in failure for failure in failures), failures


def test_a_superuser_applier_needs_no_admin_on_the_owner() -> None:
    superuser = role_row(APPLIER, superuser=True, inherit=True, login=True, is_applying_role=True)
    roles = [AUTHENTICATOR_ROW, superuser, *(role_row(r) for r in apply_0017.NEW_ROLES)]
    memberships = [row for row in MEMBERSHIPS if row[1] != APPLIER]
    pre, post = _state(
        pre_overrides={"roles": roles, "memberships": memberships},
        roles=roles,
        memberships=memberships,
    )
    assert apply_0017.pre_check_failures(pre) == []
    assert apply_0017.post_check_failures(pre, post) == []


def test_another_grantee_is_accepted_only_where_the_bundle_rpc_has_it_too() -> None:
    extra = "supabase_admin=EXECUTE"
    bundle = _function(acl=sorted([*BUNDLE_ACL, extra]))
    forecast = _forecast(acl=sorted([*FORECAST_POST[-1], extra]))
    pre, post = _state(pre_overrides={"function": bundle}, function=bundle, forecast=forecast)
    assert apply_0017.pre_check_failures(pre) == []
    assert apply_0017.post_check_failures(pre, post) == []
    pre, post = _state(forecast=forecast)
    failures = apply_0017.post_check_failures(pre, post)
    assert failures == [
        f"{apply_0017.FORECAST_REFERENCE}: {extra} may execute it, but not"
        f" {apply_0017.FUNCTION_REFERENCE}"
    ]


@pytest.mark.parametrize(
    ("name", "rows", "expected"),
    [
        (
            "roles",
            [*ROLES[:-1], role_row("ucpe_space_db", login=True)],
            "the role 'ucpe_space_db' changed during the apply",
        ),
        (
            "memberships",
            [*MEMBERSHIPS, (OWNER, APPLIER, True, False, False, True)],
            "appeared during the apply",
        ),
        ("memberships", MEMBERSHIPS[:-1], "is gone after the apply"),
        (
            "grants",
            _grants_with(GRANTS_POST, OWNER, "analysis_runs", ["INSERT", "SELECT", "UPDATE"]),
            f"{OWNER} holds ['INSERT', 'SELECT', 'UPDATE'] on the table analysis_runs after",
        ),
        (
            "grants",
            _grants_with(GRANTS_POST, OWNER, "analysis_run_details", ["SELECT"]),
            "on the table analysis_run_details after the apply, not ['INSERT', 'SELECT']",
        ),
        (
            "grants",
            _grants_with(GRANTS_POST, "ucpe_api_writer", "analysis_runs", ["INSERT"]),
            "ucpe_api_writer holds ['INSERT'] on the table analysis_runs after the apply",
        ),
        (
            "grants",
            _grants_with(GRANTS_POST, "ucpe_space_db", "automation_credential", []),
            "on the table automation_credential after the apply",
        ),
        ("grants", GRANTS_POST[:-1], "the table privileges were read for"),
        (
            "sequence_grants",
            [(r, s, ["USAGE"]) for r, s, _p in SEQUENCE_GRANTS],
            "on the sequence app_events_id_seq after the apply",
        ),
        (
            "schema_grants",
            [(r, True, r == OWNER) for r in apply_0017.NEW_ROLES],
            f"the schema right of '{OWNER}' changed during the apply",
        ),
        (
            "schema",
            [("public", "pg_database_owner", True, True, True, False, True, True, *SCHEMA[0][8:])],
            "the schema 'public' changed during the apply",
        ),
        ("policies", POLICIES_POST[1:], "is gone after the apply"),
        (
            "policies",
            [row for row in POLICIES_POST if row[0] != "analysis_runs/ucpe_bundle_owner_insert"],
            "the policy analysis_runs/ucpe_bundle_owner_insert is missing after the apply",
        ),
        (
            "policies",
            [*POLICIES_POST, ("watchlist/extra", "r", True, ["anon"], "true", "")],
            "the policy 'watchlist/extra' appeared during the apply",
        ),
        (
            "policies",
            [
                (item, "w", *rest)
                if item == "analysis_runs/ucpe_bundle_owner_select"
                else (item, command, *rest)
                for item, command, *rest in POLICIES_POST
            ],
            "the policy analysis_runs/ucpe_bundle_owner_select is",
        ),
        (
            "function",
            _function(acl=[*BUNDLE_ACL, "anon=EXECUTE"]),
            "changed during the apply",
        ),
        ("function", [], "is gone after the apply"),
        ("forecast", [], "is missing after the apply"),
        ("forecast", [FORECAST_POST, FORECAST_POST], "appears 2 times after the apply"),
        ("forecast", _forecast(security_definer=False), "security_definer is False"),
        ("forecast", _forecast(owner=APPLIER), "owner is 'postgres'"),
        ("forecast", _forecast(owned_by_applying_role=True), "owned_by_applying_role is True"),
        ("forecast", _forecast(source="BEGIN RETURN NULL; END;"), "source is"),
        ("forecast", _forecast(config=[]), "config is []"),
        ("forecast", _forecast(volatility="s"), "volatility is 's'"),
        ("forecast", _forecast(returns="json"), "returns is 'json'"),
        ("forecast", _forecast(arguments="p_run jsonb"), "arguments is 'p_run jsonb'"),
        (
            "forecast",
            _forecast(acl=[*FORECAST_POST[-1], "anon=EXECUTE"]),
            "anon=EXECUTE may execute it",
        ),
        (
            "forecast",
            _forecast(acl=[*FORECAST_POST[-1], "PUBLIC=EXECUTE"]),
            "PUBLIC=EXECUTE may execute it",
        ),
        (
            "forecast",
            _forecast(acl=[*FORECAST_POST[-1], "ucpe_resolver=EXECUTE"]),
            "ucpe_resolver=EXECUTE may execute it",
        ),
        (
            "forecast",
            _forecast(acl=["service_role=EXECUTE", f"{OWNER}=EXECUTE"]),
            "ucpe_api_writer may not execute it",
        ),
        ("other_functions", [], "is gone after the apply"),
        (
            "security",
            [
                security_row(t, policies=row[6], anon=["SELECT"])
                for t, row in zip(apply_0017.TABLES, SECURITY_POST, strict=True)
            ],
            "changed during the apply",
        ),
        ("security", SECURITY_PRE, "policies, not"),
        ("schema_fingerprint", FINGERPRINT[1:], "is gone after the apply"),
        ("event_triggers", [], "the event trigger 'pgrst_ddl_watch' is gone after the apply"),
    ],
)
def test_every_departure_from_the_reviewed_result_refuses(
    name: str, rows: list[tuple], expected: str
) -> None:
    pre, post = _state(**{name: rows})
    failures = apply_0017.post_check_failures(pre, post)
    assert failures and any(expected in failure for failure in failures), failures


def test_the_security_policy_counts_grow_only_on_the_run_and_detail_tables() -> None:
    grown = {
        table
        for table, before, after in zip(apply_0017.TABLES, SECURITY_PRE, SECURITY_POST, strict=True)
        if before != after
    }
    assert grown == {"analysis_runs", "analysis_run_details"}
    assert _policy_counts(POLICIES_POST)["analysis_runs"] == (
        _policy_counts(POLICIES_PRE)["analysis_runs"] + 2
    )


# ------------------------------------------------------------------------ one transaction


def test_a_first_apply_runs_every_check_in_one_committed_transaction() -> None:
    database = FakeDatabase(healthy_results())
    outcome, captured = _apply(database)
    checks = [query for _name, query, _fields in apply_0017.read_only_checks(PRODUCTION_SERVER)]
    assert database.executed() == [
        *apply_0017.TIMEOUT_STATEMENTS,
        apply_0017.ADVISORY_LOCK_SQL,
        apply_0017.ROLES_SQL,
        apply_0017.SERVER_VERSION_SQL,
        *checks,
        MIGRATION_SQL,
        *checks,
    ]
    assert database.commits == 1 and database.rollbacks == 0
    assert outcome["outcome"] == "APPLIED" and outcome["committed"] is True
    assert outcome["executed_migration_sha256"] == apply_0017.MIGRATION_SHA256
    assert outcome["pre_forecast"] == []
    assert outcome["post_forecast"][0]["owner"] == OWNER
    assert captured["committed"] is True


def test_a_refused_pre_check_never_runs_the_migration() -> None:
    database = FakeDatabase(healthy_results(forecast=([FORECAST_POST], [FORECAST_POST])))
    with pytest.raises(ProvenanceRefused, match=apply_0017.NOT_A_FIRST_APPLY):
        _apply(database)
    assert MIGRATION_SQL not in database.executed()
    assert database.commits == 0 and database.rollbacks == 1


def test_a_refused_post_check_rolls_the_migration_back() -> None:
    bad = _forecast(acl=[*FORECAST_POST[-1], "anon=EXECUTE"])
    database = FakeDatabase(healthy_results(forecast=([], bad)))
    with pytest.raises(ProvenanceRefused, match="rolled back"):
        _apply(database)
    assert MIGRATION_SQL in database.executed()
    assert database.commits == 0 and database.rollbacks == 1


@pytest.mark.parametrize("version", [140012, None, "17"])
def test_an_unsupported_server_refuses_before_any_check(version: Any) -> None:
    results = healthy_results()
    results[apply_0017.SERVER_VERSION_SQL] = [(version,)]
    database = FakeDatabase(results)
    with pytest.raises(ProvenanceRefused, match="is not PostgreSQL 15 or later"):
        _apply(database)
    assert database.executed()[-1] == apply_0017.SERVER_VERSION_SQL


def test_missing_api_roles_refuse() -> None:
    results = healthy_results()
    results[apply_0017.ROLES_SQL] = [(2,)]
    with pytest.raises(ProvenanceRefused, match="of the 3 Supabase API roles exist"):
        _apply(FakeDatabase(results))


# ------------------------------------------------------------------------ the entrypoint


def test_apply_without_the_exact_token_refuses_before_anything(tmp_path: Path) -> None:
    report = tmp_path / "report.json"
    code = apply_0017.main(["--mode=apply", "--confirm=yes", f"--report={report}"], environ={})
    assert code == 2
    record = json.loads(report.read_text())
    assert record["outcome"] == "REFUSED" and apply_0017.CONFIRMATION in record["detail"]
    assert record["committed"] is False


def test_the_rehearsal_reaches_only_a_local_socket_and_never_beside_the_secret() -> None:
    args = apply_0017.build_parser().parse_args(["--mode=rehearse"])
    with pytest.raises(ProvenanceRefused, match="local unix-socket URL"):
        apply_0017.rehearse(args, {apply_0017.REHEARSAL_URL_VARIABLE: DATABASE_URL}, {})
    environ = {apply_0017.REHEARSAL_URL_VARIABLE: REHEARSAL_URL, "SUPABASE_DB_URL": DATABASE_URL}
    with pytest.raises(ProvenanceRefused, match="never runs where the production database"):
        apply_0017.rehearse(args, environ, {})


def test_a_rehearsal_applies_once_and_proves_a_second_apply_refuses(monkeypatch) -> None:
    applied = healthy_results(REHEARSAL_SERVER)
    # The second apply's pre-reads see the applied state: the function, its grants and policies.
    for _name, query, _fields in apply_0017.read_only_checks(REHEARSAL_SERVER):
        rows = applied[query]
        applied[query] = Each([rows[0], rows[1], rows[1], rows[1]])
    database = FakeDatabase(applied)
    monkeypatch.setattr(apply_0017, "load_driver", lambda: database)
    args = apply_0017.build_parser().parse_args(["--mode=rehearse"])
    captured: dict[str, Any] = {}
    outcome = apply_0017.rehearse(
        args, {apply_0017.REHEARSAL_URL_VARIABLE: REHEARSAL_URL}, captured
    )
    assert outcome["outcome"] == "REHEARSED"
    refusal = outcome["second_apply_refusal"]
    assert refusal.count(apply_0017.NOT_A_FIRST_APPLY) == 3, refusal
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
    monkeypatch.setattr(apply_0017, "load_driver", lambda: driver)
    report = tmp_path / "report.json"
    environ = {apply_0017.REHEARSAL_URL_VARIABLE: REHEARSAL_URL}
    code = apply_0017.main(["--mode=rehearse", f"--report={report}"], environ=environ)
    assert code == 1
    record = json.loads(report.read_text())
    assert record["outcome"] == "FAILED" and record["error_type"] == "Unreachable"
    assert "withheld" in record["detail"]
    output = capsys.readouterr()
    for text in (report.read_text(), output.out, output.err):
        assert "migration_0017_rehearsal?host" not in text and "NEVER-SHOWN" not in text
