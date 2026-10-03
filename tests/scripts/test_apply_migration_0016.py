"""The one-shot apply of migration 0016 (Phase 3's least-privilege roles). No database is contacted.

Every database interaction runs against the psycopg-3-shaped fake of migration 0015's test:
- a connection used as a context manager commits on success and rolls back on an exception;
- a statement is recorded with its parameters;
- a check read before and after the migration can return different rows.
The real PostgreSQL rehearsals run in three places:
- .github/workflows/migration-0016-rehearsal.yml (every pull request);
- inside the dispatch job (.github/workflows/apply-migration-0016.yml), before the secret is
  handed to any step;
- .github/workflows/privilege-rehearsal.yml (P1-P8, production's code behind a real PostgREST).
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
from scripts.privilege_rehearsal import rehearse
from tests.scripts.test_apply_migration_0015 import Each, FakeDatabase

ROOT = Path(__file__).resolve().parents[2]
MIGRATION_BYTES = (ROOT / apply_0016.MIGRATION).read_bytes()
MIGRATION_SQL = MIGRATION_BYTES.decode("utf-8")
DATABASE_URL = "postgresql://owner:NEVER-SHOWN-SECRET@db.never-contacted.invalid:5432/postgres"
REHEARSAL_URL = "postgresql:///migration_0016_rehearsal?host=/var/run/postgresql"
PRODUCTION_SERVER = 170006
REHEARSAL_SERVER = 160010
APPLIER = "postgres"
ALL = list(apply_0016.table_privileges_for(PRODUCTION_SERVER))
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
    "other_functions",
    "security",
    "schema_fingerprint",
    "event_triggers",
)


# ------------------------------------------------------------------------ production after 0015


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
    return (name, *(values[field] for field in apply_0016.ROLE_FIELDS[1:]))


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
ROLES_PRE = [AUTHENTICATOR_ROW, APPLIER_ROW]
ROLES_POST = [*ROLES_PRE, *(role_row(role) for role in apply_0016.NEW_ROLES)]
MEMBERSHIPS_PRE = [
    (api, "authenticator", False, False, False, True) for api in apply_0016.API_ROLES
]
WRITER_MEMBERSHIP = ("ucpe_api_writer", "authenticator", True, False, False, True)
CREATOR_MEMBERSHIPS = [(role, APPLIER, False, True, False, False) for role in apply_0016.NEW_ROLES]
MEMBERSHIPS_POST = [*MEMBERSHIPS_PRE, WRITER_MEMBERSHIP, *CREATOR_MEMBERSHIPS]
GRANTS_POST = [
    (role, table, list(apply_0016.EXPECTED_GRANTS.get(role, {}).get(table, ())))
    for role in apply_0016.NEW_ROLES
    for table in apply_0016.TABLES
]
SEQUENCE_GRANTS_POST = [
    (role, sequence, list(apply_0016.EXPECTED_SEQUENCE_GRANTS.get(role, {}).get(sequence, ())))
    for role in apply_0016.NEW_ROLES
    for sequence in apply_0016.SEQUENCES
]
SCHEMA = [
    ("public", "pg_database_owner", True, True, True, False, True, False, True, False, True, False)
]
SCHEMA_GRANTS_POST = [(role, True, False) for role in apply_0016.NEW_ROLES]
POLICIES_POST = [(item, *values) for item, values in sorted(apply_0016.expected_policies().items())]
FUNCTION_PRE = (
    apply_0016.FUNCTION_ARGUMENTS,
    "jsonb",
    "plpgsql",
    False,
    "f",
    "v",
    list(apply_0016.FUNCTION_CONFIG),
    APPLIER,
    True,
    apply_0016.FUNCTION_SOURCE,
    [f"{APPLIER}=EXECUTE", "service_role=EXECUTE"],
)
FUNCTION_POST = (
    apply_0016.FUNCTION_ARGUMENTS,
    "jsonb",
    "plpgsql",
    True,
    "f",
    "v",
    list(apply_0016.FUNCTION_CONFIG),
    "ucpe_bundle_owner",
    False,
    apply_0016.FUNCTION_SOURCE,
    ["service_role=EXECUTE", "ucpe_api_writer=EXECUTE", "ucpe_bundle_owner=EXECUTE"],
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
    return (table, *(values[field] for field in apply_0016.SECURITY_FIELDS[1:]))


ADDED_POLICIES: dict[str, int] = {}
for _item in apply_0016.expected_policies():
    ADDED_POLICIES[_item.split("/", 1)[0]] = ADDED_POLICIES.get(_item.split("/", 1)[0], 0) + 1
SECURITY_PRE = [security_row(table) for table in apply_0016.TABLES]
SECURITY_POST = [
    security_row(table, policies=ADDED_POLICIES.get(table, 0)) for table in apply_0016.TABLES
]
FINGERPRINT = [
    ("predictions/trigger/trg_pred_reject_update", "O 19 reject_core_evidence_mutation"),
    ("watchlist/column/normalized_symbol", "text notnull=true default= acl="),
]
EVENT_TRIGGERS = [("pgrst_ddl_watch", "ddl_command_end", "O", "extensions.pgrst_ddl_watch", "")]


def healthy_results(version: int = PRODUCTION_SERVER, **overrides: Any) -> dict[str, Any]:
    """A first apply on production as it is after 0015: every pre read, then every post read."""

    pre_post = {
        "server": ([(version,)], [(version,)]),
        "roles": (ROLES_PRE, ROLES_POST),
        "memberships": (MEMBERSHIPS_PRE, MEMBERSHIPS_POST),
        "grants": ([], GRANTS_POST),
        "sequence_grants": ([], SEQUENCE_GRANTS_POST),
        "schema": (SCHEMA, SCHEMA),
        "schema_grants": ([], SCHEMA_GRANTS_POST),
        "policies": ([], POLICIES_POST),
        "function": ([FUNCTION_PRE], [FUNCTION_POST]),
        "other_functions": (OTHER_FUNCTIONS, OTHER_FUNCTIONS),
        "security": (SECURITY_PRE, SECURITY_POST),
        "schema_fingerprint": (FINGERPRINT, FINGERPRINT),
        "event_triggers": (EVENT_TRIGGERS, EVENT_TRIGGERS),
    }
    pre_post.update(overrides)
    results: dict[str, Any] = {
        apply_0016.ROLES_SQL: [(3,)],
        apply_0016.SERVER_VERSION_SQL: [(version,)],
    }
    for name, query, _fields in apply_0016.read_only_checks(version):
        before, after = pre_post[name]
        results[query] = Each([before, after])
    return results


def _apply(database: FakeDatabase) -> tuple[dict[str, Any], dict[str, Any]]:
    captured: dict[str, Any] = {}
    outcome = apply_0016.apply_in_one_transaction(
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

    fields = {name: checked for name, _query, checked in apply_0016.read_only_checks(170006)}
    results = healthy_results()
    pre, post = {}, {}
    for name, query, _fields in apply_0016.read_only_checks(170006):
        before, after = results[query]
        pre[name] = _dicts(fields[name], (pre_overrides or {}).get(name, before))
        post[name] = _dicts(fields[name], overrides.get(name, after))
    return pre, post


# ------------------------------------------------------------------------ what the route is


def test_the_script_imports_only_the_standard_library_at_module_level() -> None:
    tree = ast.parse((ROOT / apply_0016.SCRIPT).read_text(encoding="utf-8"))
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
    assert apply_0016.SCRIPT == "scripts/apply_migration_0016.py"
    assert apply_0016.WORKFLOW == ".github/workflows/apply-migration-0016.yml"
    assert (ROOT / apply_0016.WORKFLOW).is_file()
    assert apply_0016.MIGRATION == "migrations/0016_least_privilege_roles.sql"
    assert hashlib.sha256(MIGRATION_BYTES).hexdigest() == apply_0016.MIGRATION_SHA256
    assert apply_0016.CONFIRMATION == "APPLY-MIGRATION-0016-ONCE"
    assert apply_0016.REHEARSAL_URL_VARIABLE == "MIGRATION_0016_REHEARSAL_URL"


def test_its_advisory_lock_is_its_own() -> None:
    keys = {}
    for path in sorted((ROOT / "scripts").glob("apply_*.py")):
        found = re.findall(r"pg_advisory_xact_lock\((\d+)\)", path.read_text(encoding="utf-8"))
        keys.update({key: path.name for key in found})
    assert keys["5000016"] == "apply_migration_0016.py"
    assert list(keys.values()).count("apply_migration_0016.py") == 1


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
    assert inspect.getsource(getattr(apply_0016, name)) == inspect.getsource(
        getattr(apply_0011, name)
    ), name


def test_its_transaction_and_rehearsal_are_0011_s_up_to_the_migration_number() -> None:
    for name in ("apply_in_one_transaction", "_refusal"):
        ours = inspect.getsource(getattr(apply_0016, name))
        theirs = inspect.getsource(getattr(apply_0011, name)).replace("0011", "0016")
        assert ours == theirs, name
    ours = inspect.getsource(apply_0016.rehearse).split('"""')
    theirs = inspect.getsource(apply_0011.rehearse).replace("0011", "0016").split('"""')
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
        assert getattr(apply_0016, constant) == getattr(apply_0011, constant), constant


# ------------------------------------------------------------------------ it matches the migration


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


def test_its_expected_grants_are_the_migration_s_and_the_rehearsal_s() -> None:
    assert _grants(MIGRATION_SQL, "TABLE") == apply_0016.EXPECTED_GRANTS
    assert _grants(MIGRATION_SQL, "SEQUENCE") == apply_0016.EXPECTED_SEQUENCE_GRANTS
    assert {
        role: {t: tuple(sorted(p)) for t, p in tables.items()}
        for role, tables in rehearse.EXPECTED_TABLES.items()
    } == apply_0016.EXPECTED_GRANTS


def test_its_expected_policies_are_the_migration_s() -> None:
    created = set()
    for statement in _statements(MIGRATION_SQL):
        match = re.fullmatch(
            r"CREATE POLICY (\w+) ON public\.(\w+) FOR (\w+) TO (\w+) .+", statement
        )
        if match:
            created.add(f"{match.group(2)}/{match.group(1)}")
    assert created == set(apply_0016.expected_policies()) and len(created) == 40


def test_it_requires_0015_s_body_and_the_migration_changes_only_owner_and_security() -> None:
    fifteen = (ROOT / apply_0016.FUNCTION_MIGRATION).read_text(encoding="utf-8")
    body = re.search(r"AS \$function\$(.*?)\$function\$;", fifteen, re.S).group(1)
    assert body == apply_0016.FUNCTION_SOURCE
    altered = [s for s in _statements(MIGRATION_SQL) if s.startswith("ALTER FUNCTION")]
    reference = f"{apply_0016.FUNCTION_REFERENCE}(jsonb, jsonb, jsonb)"
    assert altered == [
        f"ALTER FUNCTION {reference} SECURITY DEFINER",
        f"ALTER FUNCTION {reference} OWNER TO ucpe_bundle_owner",
    ]
    assert "CREATE OR REPLACE FUNCTION" not in MIGRATION_SQL


def test_the_tables_are_every_table_of_migrations_0001_to_0015() -> None:
    created = set()
    for path in sorted((ROOT / "migrations").glob("*.sql")):
        if path.name < "0016":
            created |= set(
                re.findall(
                    r"CREATE TABLE IF NOT EXISTS (?:public\.)?([a-z_0-9]+)", path.read_text()
                )
            )
    assert sorted(created) == list(apply_0016.TABLES)


def test_the_space_role_keeps_exactly_the_live_f1_uor_grants() -> None:
    space = apply_0016.EXPECTED_GRANTS["ucpe_space_db"]
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
    queries = [query for _name, query, _fields in apply_0016.read_only_checks(version)]
    queries += [apply_0016.ROLES_SQL, apply_0016.SERVER_VERSION_SQL]
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
    for _name, query, _fields in apply_0016.read_only_checks(version):
        assert not re.search(r"ORDER BY \s*\d", query), query[-80:]
        assert not re.search(r",\s*\d+\s+COLLATE", query), query[-80:]


def test_the_checks_cover_every_table_role_and_the_function() -> None:
    names = [name for name, _query, _fields in apply_0016.read_only_checks(PRODUCTION_SERVER)]
    assert tuple(names) == CHECK_NAMES
    for table in apply_0016.TABLES:
        assert f"('{table}')" in apply_0016.security_sql(PRODUCTION_SERVER)
        assert f"('{table}')" in apply_0016.grants_sql(PRODUCTION_SERVER)
        assert f"('{table}')" in apply_0016.SCHEMA_FINGERPRINT_SQL
    for role in apply_0016.NEW_ROLES:
        assert f"'{role}'" in apply_0016.ROLES_STATE_SQL
    assert "'MAINTAIN'" in apply_0016.grants_sql(PRODUCTION_SERVER)
    assert "'MAINTAIN'" not in apply_0016.grants_sql(REHEARSAL_SERVER)
    assert "a.set_option" in apply_0016.memberships_sql(PRODUCTION_SERVER)
    assert "a.set_option" not in apply_0016.memberships_sql(150010)


# ------------------------------------------------------------------------ the pure verdicts


def test_a_healthy_first_apply_has_no_pre_or_post_failure() -> None:
    pre, post = _state()
    assert apply_0016.pre_check_failures(pre) == []
    assert apply_0016.post_check_failures(pre, post) == []


@pytest.mark.parametrize(
    ("name", "rows"),
    [
        ("roles", ROLES_POST),
        ("policies", POLICIES_POST),
        ("function", [FUNCTION_POST]),
    ],
)
def test_a_second_apply_is_refused_as_not_a_first_apply(name: str, rows: list[tuple]) -> None:
    pre, _post = _state(pre_overrides={name: rows})
    failures = apply_0016.pre_check_failures(pre)
    assert failures and all(apply_0016.NOT_A_FIRST_APPLY in f for f in failures), failures


def _function_pre(**changes: Any) -> list[tuple]:
    values = dict(zip(apply_0016.FUNCTION_FIELDS, FUNCTION_PRE, strict=True))
    values.update(changes)
    return [tuple(values[field] for field in apply_0016.FUNCTION_FIELDS)]


@pytest.mark.parametrize(
    ("name", "rows", "expected"),
    [
        ("server", [(150010,)], "is not PostgreSQL 16 or later"),
        ("roles", [APPLIER_ROW], "authenticator role does not exist"),
        (
            "roles",
            [AUTHENTICATOR_ROW, role_row(APPLIER, is_applying_role=True)],
            "holds neither CREATEROLE nor SUPERUSER",
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
        ("function", [], "exists 0 times, not once"),
        ("function", _function_pre(source="BEGIN RETURN NULL; END;"), "source is"),
        ("function", _function_pre(owned_by_applying_role=False), "owned_by_applying_role is"),
        ("function", _function_pre(acl=[f"{APPLIER}=EXECUTE"]), "service_role may not execute"),
        (
            "function",
            _function_pre(acl=[f"{APPLIER}=EXECUTE", "anon=EXECUTE", "service_role=EXECUTE"]),
            "anon=EXECUTE may execute",
        ),
        (
            "security",
            [security_row(t, owned_by_applying_role=t != "watchlist") for t in apply_0016.TABLES],
            "watchlist: is not owned by the applying role",
        ),
        (
            "security",
            [
                security_row(t, relkind="p" if t == "predictions" else "r")
                for t in apply_0016.TABLES
            ],
            "predictions: is 'p', not an ordinary table",
        ),
        ("security", SECURITY_PRE[:-1], "the tables read were"),
    ],
)
def test_a_database_not_ready_for_0016_refuses(name: str, rows: list[tuple], expected: str) -> None:
    pre, _post = _state(pre_overrides={name: rows})
    failures = apply_0016.pre_check_failures(pre)
    assert failures and any(expected in failure for failure in failures), failures


def test_another_grantee_of_the_function_is_recorded_not_refused_and_kept() -> None:
    acl = [f"{APPLIER}=EXECUTE", "service_role=EXECUTE", "supabase_admin=EXECUTE"]
    after = [
        "service_role=EXECUTE",
        "supabase_admin=EXECUTE",
        "ucpe_api_writer=EXECUTE",
        "ucpe_bundle_owner=EXECUTE",
    ]
    post_function = [(*FUNCTION_POST[:-1], after)]
    pre, post = _state(pre_overrides={"function": _function_pre(acl=acl)}, function=post_function)
    assert apply_0016.pre_check_failures(pre) == []
    assert apply_0016.post_check_failures(pre, post) == []
    lost = [(*FUNCTION_POST[:-1], [e for e in after if not e.startswith("supabase_admin")])]
    pre, post = _state(pre_overrides={"function": _function_pre(acl=acl)}, function=lost)
    assert any("acl is" in f for f in apply_0016.post_check_failures(pre, post))


def _post_function(**changes: Any) -> list[tuple]:
    values = dict(zip(apply_0016.FUNCTION_FIELDS, FUNCTION_POST, strict=True))
    values.update(changes)
    return [tuple(values[field] for field in apply_0016.FUNCTION_FIELDS)]


def _grants_with(role: str, table: str, privileges: list[str]) -> list[tuple]:
    return [(r, t, privileges if (r, t) == (role, table) else p) for r, t, p in GRANTS_POST]


@pytest.mark.parametrize(
    ("name", "rows", "expected"),
    [
        (
            "roles",
            [*ROLES_PRE, *(role_row(r, login=r == "ucpe_space_db") for r in apply_0016.NEW_ROLES)],
            "ucpe_space_db holds login",
        ),
        (
            "roles",
            [
                *ROLES_PRE,
                *(role_row(r, bypassrls=r == "ucpe_api_writer") for r in apply_0016.NEW_ROLES),
            ],
            "holds bypassrls",
        ),
        (
            "roles",
            ROLES_PRE + [role_row(r) for r in apply_0016.NEW_ROLES[:3]],
            "the role ucpe_space_db is missing",
        ),
        (
            "roles",
            [
                role_row("authenticator", login=True, inherit=True),
                APPLIER_ROW,
                *(role_row(r) for r in apply_0016.NEW_ROLES),
            ],
            "the role 'authenticator' changed",
        ),
        (
            "memberships",
            [*MEMBERSHIPS_PRE, *CREATOR_MEMBERSHIPS],
            "authenticator cannot switch to the writer",
        ),
        (
            "memberships",
            [*MEMBERSHIPS_POST, ("ucpe_space_db", "authenticator", True, False, False, True)],
            "appeared during the apply",
        ),
        (
            "memberships",
            [
                *MEMBERSHIPS_PRE,
                ("ucpe_api_writer", "authenticator", True, False, True, True),
                *CREATOR_MEMBERSHIPS,
            ],
            "authenticator cannot switch to the writer",
        ),
        (
            "memberships",
            [
                *MEMBERSHIPS_PRE,
                WRITER_MEMBERSHIP,
                *CREATOR_MEMBERSHIPS[:3],
                ("ucpe_space_db", APPLIER, False, True, False, True),
            ],
            "appeared during the apply",
        ),
        ("memberships", MEMBERSHIPS_POST[1:], "is gone after the apply"),
        (
            "grants",
            _grants_with("ucpe_api_writer", "predictions", ["INSERT", "SELECT"]),
            "ucpe_api_writer holds ['INSERT', 'SELECT'] on the table predictions",
        ),
        (
            "grants",
            _grants_with("ucpe_space_db", "automation_radar_ledger", ["SELECT"]),
            "on the table automation_radar_ledger",
        ),
        ("grants", GRANTS_POST[:-1], "the table privileges were read for"),
        (
            "sequence_grants",
            [(r, s, ["USAGE"]) for r, s, _p in SEQUENCE_GRANTS_POST],
            "on the sequence app_events_id_seq",
        ),
        (
            "schema_grants",
            [(r, True, r == "ucpe_bundle_owner") for r in apply_0016.NEW_ROLES],
            "ucpe_bundle_owner holds (True, True) (USAGE, CREATE) on schema public",
        ),
        (
            "schema",
            [
                (
                    "public",
                    "pg_database_owner",
                    True,
                    True,
                    True,
                    False,
                    True,
                    True,
                    True,
                    False,
                    True,
                    False,
                )
            ],
            "the schema 'public' changed during the apply",
        ),
        ("policies", POLICIES_POST[1:], "is missing after the apply"),
        (
            "policies",
            [*POLICIES_POST, ("watchlist/extra", "r", True, ["anon"], "true", "")],
            "the policy 'watchlist/extra' appeared during the apply",
        ),
        (
            "policies",
            [(POLICIES_POST[0][0], "*", *POLICIES_POST[0][2:]), *POLICIES_POST[1:]],
            f"the policy {POLICIES_POST[0][0]} is",
        ),
        ("function", [], "is missing after the apply"),
        ("function", _post_function(security_definer=False), "security_definer is False"),
        ("function", _post_function(owner=APPLIER), f"owner is '{APPLIER}'"),
        ("function", _post_function(source="BEGIN RETURN NULL; END;"), "source is"),
        ("function", _post_function(config=[]), "config is []"),
        ("function", _post_function(acl=[*FUNCTION_POST[-1], "anon=EXECUTE"]), "acl is"),
        ("other_functions", [], "is gone after the apply"),
        (
            "security",
            [
                security_row(t, policies=ADDED_POLICIES.get(t, 0), anon=["SELECT"])
                for t in apply_0016.TABLES
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
    failures = apply_0016.post_check_failures(pre, post)
    assert failures and any(expected in failure for failure in failures), failures


def test_a_superuser_applier_has_no_creator_grants_and_may_record_another_grantor() -> None:
    superuser = role_row(APPLIER, superuser=True, inherit=True, login=True, is_applying_role=True)
    roles_pre = [AUTHENTICATOR_ROW, superuser]
    roles_post = [*roles_pre, *(role_row(r) for r in apply_0016.NEW_ROLES)]
    writer = ("ucpe_api_writer", "authenticator", False, False, False, True)
    pre, post = _state(
        pre_overrides={"roles": roles_pre}, roles=roles_post, memberships=[*MEMBERSHIPS_PRE, writer]
    )
    assert apply_0016.post_check_failures(pre, post) == []
    pre, post = _state(
        pre_overrides={"roles": roles_pre},
        roles=roles_post,
        memberships=[*MEMBERSHIPS_PRE, writer, *CREATOR_MEMBERSHIPS],
    )
    assert any(
        "SUPERUSER applier was granted" in f for f in apply_0016.post_check_failures(pre, post)
    )


# ------------------------------------------------------------------------ one transaction


def test_a_first_apply_runs_every_check_in_one_committed_transaction() -> None:
    database = FakeDatabase(healthy_results())
    outcome, captured = _apply(database)
    checks = [query for _name, query, _fields in apply_0016.read_only_checks(PRODUCTION_SERVER)]
    assert database.executed() == [
        *apply_0016.TIMEOUT_STATEMENTS,
        apply_0016.ADVISORY_LOCK_SQL,
        apply_0016.ROLES_SQL,
        apply_0016.SERVER_VERSION_SQL,
        *checks,
        MIGRATION_SQL,
        *checks,
    ]
    assert database.commits == 1 and database.rollbacks == 0
    assert outcome["outcome"] == "APPLIED" and outcome["committed"] is True
    assert outcome["executed_migration_sha256"] == apply_0016.MIGRATION_SHA256
    assert outcome["post_function"][0]["owner"] == "ucpe_bundle_owner"
    assert captured["committed"] is True


def test_a_refused_pre_check_never_runs_the_migration() -> None:
    database = FakeDatabase(healthy_results(roles=(ROLES_POST, ROLES_POST)))
    with pytest.raises(ProvenanceRefused, match=apply_0016.NOT_A_FIRST_APPLY):
        _apply(database)
    assert MIGRATION_SQL not in database.executed()
    assert database.commits == 0 and database.rollbacks == 1


def test_a_refused_post_check_rolls_the_migration_back() -> None:
    bad = [(*FUNCTION_POST[:-1], [*FUNCTION_POST[-1], "anon=EXECUTE"])]
    database = FakeDatabase(healthy_results(function=([FUNCTION_PRE], bad)))
    with pytest.raises(ProvenanceRefused, match="rolled back"):
        _apply(database)
    assert MIGRATION_SQL in database.executed()
    assert database.commits == 0 and database.rollbacks == 1


@pytest.mark.parametrize("version", [140012, None, "17"])
def test_an_unsupported_server_refuses_before_any_check(version: Any) -> None:
    results = healthy_results()
    results[apply_0016.SERVER_VERSION_SQL] = [(version,)]
    database = FakeDatabase(results)
    with pytest.raises(ProvenanceRefused, match="is not PostgreSQL 15 or later"):
        _apply(database)
    assert database.executed()[-1] == apply_0016.SERVER_VERSION_SQL


def test_missing_api_roles_refuse() -> None:
    results = healthy_results()
    results[apply_0016.ROLES_SQL] = [(2,)]
    with pytest.raises(ProvenanceRefused, match="of the 3 Supabase API roles exist"):
        _apply(FakeDatabase(results))


# ------------------------------------------------------------------------ the entrypoint


def test_apply_without_the_exact_token_refuses_before_anything(tmp_path: Path) -> None:
    report = tmp_path / "report.json"
    code = apply_0016.main(["--mode=apply", "--confirm=yes", f"--report={report}"], environ={})
    assert code == 2
    record = json.loads(report.read_text())
    assert record["outcome"] == "REFUSED" and apply_0016.CONFIRMATION in record["detail"]
    assert record["committed"] is False


def test_the_rehearsal_reaches_only_a_local_socket_and_never_beside_the_secret() -> None:
    args = apply_0016.build_parser().parse_args(["--mode=rehearse"])
    with pytest.raises(ProvenanceRefused, match="local unix-socket URL"):
        apply_0016.rehearse(args, {apply_0016.REHEARSAL_URL_VARIABLE: DATABASE_URL}, {})
    environ = {apply_0016.REHEARSAL_URL_VARIABLE: REHEARSAL_URL, "SUPABASE_DB_URL": DATABASE_URL}
    with pytest.raises(ProvenanceRefused, match="never runs where the production database"):
        apply_0016.rehearse(args, environ, {})


def test_a_rehearsal_applies_once_and_proves_a_second_apply_refuses(monkeypatch) -> None:
    applied = healthy_results(REHEARSAL_SERVER)
    # The second apply's pre-reads see the applied state: the roles exist.
    for _name, query, _fields in apply_0016.read_only_checks(REHEARSAL_SERVER):
        rows = applied[query]
        applied[query] = Each([rows[0], rows[1], rows[1], rows[1]])
    database = FakeDatabase(applied)
    monkeypatch.setattr(apply_0016, "load_driver", lambda: database)
    args = apply_0016.build_parser().parse_args(["--mode=rehearse"])
    captured: dict[str, Any] = {}
    outcome = apply_0016.rehearse(
        args, {apply_0016.REHEARSAL_URL_VARIABLE: REHEARSAL_URL}, captured
    )
    assert outcome["outcome"] == "REHEARSED"
    assert apply_0016.NOT_A_FIRST_APPLY in outcome["second_apply_refusal"]
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
    monkeypatch.setattr(apply_0016, "load_driver", lambda: driver)
    report = tmp_path / "report.json"
    environ = {apply_0016.REHEARSAL_URL_VARIABLE: REHEARSAL_URL}
    code = apply_0016.main(["--mode=rehearse", f"--report={report}"], environ=environ)
    assert code == 1
    record = json.loads(report.read_text())
    assert record["outcome"] == "FAILED" and record["error_type"] == "Unreachable"
    assert "withheld" in record["detail"]
    output = capsys.readouterr()
    for text in (report.read_text(), output.out, output.err):
        assert "migration_0016_rehearsal?host" not in text and "NEVER-SHOWN" not in text
