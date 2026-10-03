"""The one-shot apply of migration 0018 (Phase 3's D6, service_role narrowed). No database is used.

Every database interaction runs against the psycopg-3-shaped fake of migration 0015's test, and the
catalog as 0017 left it is 0017's own test fixture. The real PostgreSQL rehearsals run in three
places:
- .github/workflows/migration-0018-rehearsal.yml (every pull request);
- inside the dispatch job (.github/workflows/apply-migration-0018.yml), before the secret is
  handed to any step;
- .github/workflows/privilege-rehearsal.yml (D1-D4, behind a real PostgREST).
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
from scripts import apply_migration_0017 as apply_0017
from scripts import apply_migration_0018 as apply_0018
from scripts import core_write_inventory as inventory
from scripts.privilege_rehearsal import rehearse
from tests.scripts import test_apply_migration_0017 as t17
from tests.scripts.test_apply_migration_0015 import Each, FakeDatabase

ROOT = Path(__file__).resolve().parents[2]
MIGRATION_BYTES = (ROOT / apply_0018.MIGRATION).read_bytes()
MIGRATION_SQL = MIGRATION_BYTES.decode("utf-8")
DATABASE_URL = "postgresql://owner:NEVER-SHOWN-SECRET@db.never-contacted.invalid:5432/postgres"
REHEARSAL_URL = "postgresql:///migration_0018_rehearsal?host=/var/run/postgresql"
PRODUCTION_SERVER = t17.PRODUCTION_SERVER
REHEARSAL_SERVER = t17.REHEARSAL_SERVER
APPLIER = t17.APPLIER
OWNER = t17.OWNER
CHECK_NAMES = (*t17.CHECK_NAMES, *(f"inventory_{kind}" for kind in apply_0018.INVENTORY_KINDS))
SELECT_ONLY = ["SELECT"]


# ------------------------------------------------------------------------ production after 0017


GRANTS = t17.grant_rows(apply_0018.EXPECTED_GRANTS)
POLICIES = [(item, *values) for item, values in sorted(apply_0018.expected_policies().items())]
BUNDLE_ACL = list(t17.BUNDLE_ACL)
NARROWED_ACL = [entry for entry in BUNDLE_ACL if entry != "service_role=EXECUTE"]
FUNCTION_PRE = t17.FUNCTION
FUNCTION_POST = (*t17.FUNCTION[:-1], NARROWED_ACL)
FORECAST_PRE = t17.FORECAST_POST
FORECAST_POST = (*t17.FORECAST_POST[:-1], NARROWED_ACL)
POLICY_COUNTS = t17._policy_counts(POLICIES)


def security_rows(version: int, *, applied: bool) -> list[tuple]:
    """Every table as 0017 left it; service_role's core privileges before, or after, 0018."""

    before = apply_0018.service_role_before(version)
    every = list(apply_0018.table_privileges_for(version))
    rows = []
    for table in apply_0018.TABLES:
        if table in apply_0018.CORE_TABLES:
            privileges = SELECT_ONLY if applied else before[table]
        else:
            privileges = every
        rows.append(
            t17.security_row(table, privileges=privileges, policies=POLICY_COUNTS.get(table, 0))
        )
    return rows


def inventory_rows(version: int) -> dict[str, list[tuple]]:
    """D6's inventory before 0018, as production read it (run 37149774863): service_role's write
    privileges on the six tables and both bundle functions; nothing else."""

    tables = sorted(
        (table, privilege)
        for table, privileges in apply_0018.service_role_before(version).items()
        for privilege in privileges
        if privilege != "SELECT"
    )
    functions = [
        (f"{apply_0018.FORECAST_REFERENCE}(jsonb, jsonb, jsonb, jsonb, jsonb)", OWNER),
        (f"{apply_0018.FUNCTION_REFERENCE}(jsonb, jsonb, jsonb)", OWNER),
    ]
    rows = {kind: [] for kind in apply_0018.INVENTORY_KINDS}
    rows.update({"T": tables, "F": functions})
    return rows


def healthy_results(version: int = PRODUCTION_SERVER, **overrides: Any) -> dict[str, Any]:
    """A first apply on production as it is after 0017: every pre read, then every post read."""

    pre_inventory = inventory_rows(version)
    pre_post = {
        "server": ([(version,)], [(version,)]),
        "roles": (t17.ROLES, t17.ROLES),
        "memberships": (t17.MEMBERSHIPS, t17.MEMBERSHIPS),
        "grants": (GRANTS, GRANTS),
        "sequence_grants": (t17.SEQUENCE_GRANTS, t17.SEQUENCE_GRANTS),
        "schema": (t17.SCHEMA, t17.SCHEMA),
        "schema_grants": (t17.SCHEMA_GRANTS, t17.SCHEMA_GRANTS),
        "policies": (POLICIES, POLICIES),
        "function": ([FUNCTION_PRE], [FUNCTION_POST]),
        "forecast": ([FORECAST_PRE], [FORECAST_POST]),
        "other_functions": (t17.OTHER_FUNCTIONS, t17.OTHER_FUNCTIONS),
        "security": (security_rows(version, applied=False), security_rows(version, applied=True)),
        "schema_fingerprint": (t17.FINGERPRINT, t17.FINGERPRINT),
        "event_triggers": (t17.EVENT_TRIGGERS, t17.EVENT_TRIGGERS),
        **{f"inventory_{kind}": (rows, []) for kind, rows in pre_inventory.items()},
    }
    pre_post.update(overrides)
    results: dict[str, Any] = {
        apply_0018.ROLES_SQL: [(3,)],
        apply_0018.SERVER_VERSION_SQL: [(version,)],
    }
    for name, query, _fields in apply_0018.read_only_checks(version):
        before, after = pre_post[name]
        results[query] = Each([before, after])
    return results


def _apply(database: FakeDatabase) -> tuple[dict[str, Any], dict[str, Any]]:
    captured: dict[str, Any] = {}
    outcome = apply_0018.apply_in_one_transaction(
        lambda: database.connect(DATABASE_URL), MIGRATION_SQL, captured
    )
    return outcome, captured


def _state(
    pre_overrides: dict[str, list] | None = None, version: int = PRODUCTION_SERVER, **overrides: Any
):
    """The healthy pre and post reads as the pure checks see them, with ``overrides`` (post)."""

    checks = apply_0018.read_only_checks(version)
    results = healthy_results(version)
    pre, post = {}, {}
    for name, query, fields in checks:
        before, after = results[query]
        pre[name] = t17._dicts(fields, (pre_overrides or {}).get(name, before))
        post[name] = t17._dicts(fields, overrides.get(name, after))
    return pre, post


def _with(row: tuple, **changes: Any) -> list[tuple]:
    return t17._with(row, apply_0018.FUNCTION_FIELDS, **changes)


def _security_with(rows: list[tuple], table: str, **changes: Any) -> list[tuple]:
    fields = apply_0018.SECURITY_FIELDS
    return [
        tuple({**dict(zip(fields, row, strict=True)), **changes}[f] for f in fields)
        if row[0] == table
        else row
        for row in rows
    ]


# ------------------------------------------------------------------------ what the route is


def test_the_script_imports_only_the_standard_library_at_module_level() -> None:
    tree = ast.parse((ROOT / apply_0018.SCRIPT).read_text(encoding="utf-8"))
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
    assert apply_0018.SCRIPT == "scripts/apply_migration_0018.py"
    assert apply_0018.WORKFLOW == ".github/workflows/apply-migration-0018.yml"
    assert (ROOT / apply_0018.WORKFLOW).is_file()
    assert apply_0018.MIGRATION == "migrations/0018_narrow_service_role.sql"
    assert hashlib.sha256(MIGRATION_BYTES).hexdigest() == apply_0018.MIGRATION_SHA256
    assert apply_0018.CONFIRMATION == "APPLY-MIGRATION-0018-ONCE"
    assert apply_0018.REHEARSAL_URL_VARIABLE == "MIGRATION_0018_REHEARSAL_URL"


def test_its_advisory_lock_is_its_own() -> None:
    keys = {}
    for path in sorted((ROOT / "scripts").glob("apply_*.py")):
        found = re.findall(r"pg_advisory_xact_lock\((\d+)\)", path.read_text(encoding="utf-8"))
        keys.update({key: path.name for key in found})
    assert keys["5000018"] == "apply_migration_0018.py"
    assert list(keys.values()).count("apply_migration_0018.py") == 1


# The trust machinery is 0011's, copied verbatim: a reviewed route, not a new one. main differs in
# exactly two lines: what it prints and writes is published (role names withheld).
SHARED = tuple(name for name in t17.SHARED if name != "main")


@pytest.mark.parametrize("name", SHARED)
def test_its_trust_machinery_is_0011_s_verbatim(name: str) -> None:
    assert inspect.getsource(getattr(apply_0018, name)) == inspect.getsource(
        getattr(apply_0011, name)
    ), name


def test_main_is_0011_s_but_publishes_what_it_prints_and_writes() -> None:
    ours = inspect.getsource(apply_0018.main)
    theirs = inspect.getsource(apply_0011.main)
    ours = ours.replace(
        "record = _published(_refusal_record(args.mode, exc, captured))",
        "record = _refusal_record(args.mode, exc, captured)",
    ).replace("    outcome = _published(outcome)\n", "")
    assert ours == theirs


def test_its_transaction_and_rehearsal_are_0011_s_up_to_the_migration_number() -> None:
    for name in ("apply_in_one_transaction", "_refusal"):
        ours = inspect.getsource(getattr(apply_0018, name))
        theirs = inspect.getsource(getattr(apply_0011, name)).replace("0011", "0018")
        assert ours == theirs, name
    ours = inspect.getsource(apply_0018.rehearse).split('"""')
    theirs = inspect.getsource(apply_0011.rehearse).replace("0011", "0018").split('"""')
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
        assert getattr(apply_0018, constant) == getattr(apply_0011, constant), constant


@pytest.mark.parametrize("version", [PRODUCTION_SERVER, REHEARSAL_SERVER])
def test_its_checks_are_0017_s_reviewed_ones_plus_d6_s_inventory(version: int) -> None:
    ours = {name: (query, fields) for name, query, fields in apply_0018.read_only_checks(version)}
    theirs = {name: (query, fields) for name, query, fields in apply_0017.read_only_checks(version)}
    for name in theirs:
        assert ours[name] == theirs[name], name
    for kind in apply_0018.INVENTORY_KINDS:
        assert ours[f"inventory_{kind}"] == (
            apply_0018.inventory_sql(kind, version),
            apply_0018.INVENTORY_FIELDS,
        )
    for constant in (
        "NEW_ROLES",
        "TABLES",
        "SEQUENCES",
        "EXPECTED_GRANTS",
        "EXPECTED_SEQUENCE_GRANTS",
        "FUNCTION",
        "FUNCTION_ARGUMENTS",
        "FUNCTION_CONFIG",
        "FUNCTION_SOURCE",
        "FORECAST",
        "FORECAST_ARGUMENTS",
        "FORECAST_SOURCE",
        "NEVER_EXECUTE",
        "NOT_A_FIRST_APPLY",
    ):
        assert getattr(apply_0018, constant) == getattr(apply_0017, constant), constant
    assert apply_0018.expected_policies() == apply_0017.expected_policies()


# ------------------------------------------------------------------------ it matches D6


def test_the_inventory_copies_are_the_inventory_s_own() -> None:
    assert apply_0018.INVENTORY_QUERIES == inventory.QUERIES
    assert apply_0018.CORE_TABLES == inventory.CORE_TABLES
    assert apply_0018.BUNDLE_FUNCTIONS == inventory.BUNDLE_FUNCTIONS
    assert apply_0018.INVENTORY_WRITE_PRIVILEGES == inventory.WRITE_PRIVILEGES
    assert apply_0018.INVENTORY_COLUMN_PRIVILEGES == inventory.COLUMN_PRIVILEGES
    assert apply_0018.INVENTORY_EXPOSED_SCHEMAS == inventory.EXPOSED_SCHEMAS
    assert apply_0018.INVENTORY_KINDS == inventory.SURFACE_KINDS


@pytest.mark.parametrize("version", [PRODUCTION_SERVER, REHEARSAL_SERVER])
@pytest.mark.parametrize("kind", inventory.SURFACE_KINDS)
def test_each_inventory_check_is_the_inventory_s_query_with_its_parameters_as_literals(
    version: int, kind: str
) -> None:
    values = inventory.parameters("service_role", version, inventory.EXPOSED_SCHEMAS)
    expected = inventory.QUERIES[kind]
    for name, value in values.items():
        literal = (
            f"'{value}'"
            if isinstance(value, str)
            else "ARRAY[" + ", ".join(f"'{item}'" for item in value) + "]"
        )
        expected = expected.replace(f"%({name})s", literal)
    assert apply_0018.inventory_sql(kind, version) == expected.replace("%%", "%")


@pytest.mark.parametrize(
    "rows",
    [
        {
            "T": [["predictions", "INSERT"]],
            "F": [["public.save_prediction_bundle(jsonb, jsonb, jsonb)", "o"]],
        },
        {"T": [["watchlist", "INSERT"]]},
        {"C": [["predictions", "UPDATE"]], "F": [["public.other(jsonb)", "o"]]},
        {"O": [["predictions", "x"]], "V": [["public.v", "predictions"]], "K": [["k", "t -> u"]]},
        {"R": [["public.t.r", "predictions"]], "G": [["public.t.g", "o"]]},
    ],
)
def test_its_omission_rule_is_the_inventory_s(rows: dict[str, list[list[str]]]) -> None:
    surfaces = {kind: rows.get(kind, []) for kind in inventory.SURFACE_KINDS}
    expected = [" ".join(row) for row in inventory.omitted({"surfaces": surfaces})]
    ours = apply_0018.inventory_omitted(
        {kind: [{"object": r[0], "detail": r[1]} for r in surfaces[kind]] for kind in surfaces}
    )
    assert ours == expected


def test_service_role_s_privileges_before_are_what_production_held() -> None:
    """The production inventory (run 37149774863, PostgreSQL 17): 31 write rows, six tables."""

    before = apply_0018.service_role_before(PRODUCTION_SERVER)
    writes = {t: [p for p in ps if p != "SELECT"] for t, ps in before.items()}
    assert sum(len(ps) for ps in writes.values()) == 31
    assert writes["analysis_run_details"] == ["INSERT", "UPDATE"]
    assert writes["prediction_derivatives_snapshots"] == ["INSERT"]
    for table in (
        "analysis_runs",
        "prediction_feature_snapshots",
        "prediction_outcomes",
        "predictions",
    ):
        assert writes[table] == [
            "DELETE",
            "INSERT",
            "MAINTAIN",
            "REFERENCES",
            "TRIGGER",
            "TRUNCATE",
            "UPDATE",
        ], table
    assert all("SELECT" in privileges for privileges in before.values())
    assert (
        sum(len(ps) - 1 for ps in apply_0018.service_role_before(REHEARSAL_SERVER).values()) == 27
    )


def _statements(sql: str) -> list[str]:
    return t17._statements(sql)


def test_the_migration_revokes_exactly_d6_s_scope_and_nothing_else() -> None:
    every = _statements(MIGRATION_SQL)
    assert not any(
        s.startswith(("CREATE", "DROP", "ALTER", "INSERT", "UPDATE", "DELETE")) for s in every
    )
    revokes = [s for s in every if s.startswith("REVOKE")]
    assert revokes == [
        "REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER ON TABLE"
        " public.analysis_runs,"
        " public.analysis_run_details, public.predictions, public.prediction_feature_snapshots,"
        " public.prediction_derivatives_snapshots, public.prediction_outcomes FROM service_role",
        "REVOKE EXECUTE ON FUNCTION public.save_prediction_bundle(jsonb, jsonb, jsonb) FROM"
        " service_role",
        "REVOKE EXECUTE ON FUNCTION public.save_forecast_bundle(jsonb, jsonb, jsonb, jsonb, jsonb)"
        " FROM service_role",
        "REVOKE ucpe_bundle_owner FROM CURRENT_USER",
    ]
    grants = [s for s in every if s.startswith("GRANT")]
    assert grants == ["GRANT ucpe_bundle_owner TO CURRENT_USER WITH INHERIT TRUE, SET TRUE"]
    assert "REVOKE MAINTAIN ON TABLE" in MIGRATION_SQL and ">= 170000" in MIGRATION_SQL
    assert "SELECT" not in revokes[0].split(" ON ", 1)[0]
    assert MIGRATION_SQL.count("ERRCODE = 'UP018'") == 2
    assert every[-1] == "NOTIFY pgrst, 'reload schema'"


def test_the_migration_is_the_rehearsed_one() -> None:
    assert rehearse.DRAFT_0018 == ROOT / apply_0018.MIGRATION
    assert apply_0018.CORE_TABLES == inventory.CORE_TABLES


def test_the_tables_are_every_table_of_migrations_0001_to_0017() -> None:
    created = set()
    for path in sorted((ROOT / "migrations").glob("*.sql")):
        if path.name < "0019":
            created |= set(
                re.findall(
                    r"CREATE TABLE IF NOT EXISTS (?:public\.)?([a-z_0-9]+)", path.read_text()
                )
            )
    assert sorted(created) == list(apply_0018.TABLES)
    assert set(apply_0018.CORE_TABLES) <= set(apply_0018.TABLES)


# ------------------------------------------------------------------------ the checks read only


@pytest.mark.parametrize("version", [PRODUCTION_SERVER, REHEARSAL_SERVER])
def test_every_check_is_a_read_only_catalog_query(version: int) -> None:
    queries = [query for _name, query, _fields in apply_0018.read_only_checks(version)]
    queries += [apply_0018.ROLES_SQL, apply_0018.SERVER_VERSION_SQL]
    for query in queries:
        bare = t17._without_literals(query)
        assert query.lstrip().startswith("SELECT"), query[:60]
        assert not t17.FORBIDDEN.search(bare), (t17.FORBIDDEN.search(bare).group(0), query[:80])
        assert "%s" not in query and "%(" not in query, "no parameters"
        for source in re.findall(r"\b(?:FROM|JOIN)\s+([a-z_.]+)", bare):
            # unnest() expands a literal array; it reads no table.
            assert source.startswith("pg_catalog.") or source in ("", "unnest"), (
                source,
                query[:80],
            )
        assert "public." not in bare, query[:80]


def test_the_checks_cover_every_table_role_both_functions_and_every_surface_kind() -> None:
    names = [name for name, _query, _fields in apply_0018.read_only_checks(PRODUCTION_SERVER)]
    assert tuple(names) == CHECK_NAMES
    assert "'MAINTAIN'" in apply_0018.inventory_sql("T", PRODUCTION_SERVER)
    assert "'MAINTAIN'" not in apply_0018.inventory_sql("T", REHEARSAL_SERVER)


# ------------------------------------------------------------------------ the pure verdicts


@pytest.mark.parametrize("version", [PRODUCTION_SERVER, REHEARSAL_SERVER])
def test_a_healthy_first_apply_has_no_pre_or_post_failure(version: int) -> None:
    pre, post = _state(version=version)
    assert apply_0018.pre_check_failures(pre) == []
    assert apply_0018.post_check_failures(pre, post) == []


def test_a_second_apply_is_refused_as_not_a_first_apply() -> None:
    _pre, post = _state()
    failures = apply_0018.pre_check_failures(post)
    assert len(failures) == 1 and apply_0018.NOT_A_FIRST_APPLY in failures[0], failures


@pytest.mark.parametrize(
    ("name", "rows", "expected"),
    [
        ("server", [(150010,)], "is not PostgreSQL 16 or later"),
        ("roles", [t17.AUTHENTICATOR_ROW, t17.APPLIER_ROW], "migration 0016 is not applied"),
        (
            "memberships",
            [row for row in t17.MEMBERSHIPS if row[:2] != (OWNER, APPLIER)],
            f"the applying role holds no ADMIN on {OWNER}, which acting as the functions' owner",
        ),
        (
            "grants",
            t17._grants_with(GRANTS, OWNER, "analysis_runs", []),
            f"{OWNER} holds [] on the table analysis_runs before the apply",
        ),
        ("policies", POLICIES[1:], "is missing before the apply"),
        ("function", [], "exists 0 times, not once"),
        ("function", _with(FUNCTION_PRE, source="BEGIN RETURN NULL; END;"), "source is"),
        ("forecast", [], f"{apply_0018.FORECAST_REFERENCE} exists 0 times, not once"),
        ("forecast", _with(FORECAST_PRE, security_definer=False), "security_definer is False"),
        ("forecast", _with(FORECAST_PRE, source="BEGIN RETURN NULL; END;"), "not 0017's"),
        (
            "forecast",
            _with(FORECAST_PRE, acl=["service_role=EXECUTE", f"{OWNER}=EXECUTE"]),
            "ucpe_api_writer may not execute it",
        ),
        (
            "forecast",
            _with(FORECAST_PRE, acl=[*BUNDLE_ACL, "anon=EXECUTE"]),
            "anon=EXECUTE may execute it",
        ),
        ("schema", [], "the schema public was read as"),
        (
            "security",
            [
                t17.security_row(t, owned_by_applying_role=t != "watchlist")
                for t in apply_0018.TABLES
            ],
            "watchlist: is not owned by the applying role",
        ),
        (
            "security",
            _security_with(
                security_rows(PRODUCTION_SERVER, applied=False),
                "predictions",
                service_role=["INSERT", "SELECT"],
            ),
            "service_role holds ['INSERT', 'SELECT'] on predictions before the apply",
        ),
        (
            "inventory_F",
            [*inventory_rows(PRODUCTION_SERVER)["F"], ("public.other_definer()", APPLIER)],
            "a core write surface outside D6's revoke set exists: F public.other_definer()",
        ),
        (
            "inventory_V",
            [("public.some_view", "predictions")],
            "a core write surface outside D6's revoke set exists: V public.some_view predictions",
        ),
        (
            "inventory_T",
            inventory_rows(PRODUCTION_SERVER)["T"][1:],
            "the inventory's table surfaces",
        ),
        ("inventory_F", inventory_rows(PRODUCTION_SERVER)["F"][1:], "the inventory's function"),
    ],
)
def test_a_database_not_ready_for_0018_refuses(name: str, rows: list[tuple], expected: str) -> None:
    pre, _post = _state(pre_overrides={name: rows})
    failures = apply_0018.pre_check_failures(pre)
    assert failures and any(expected in failure for failure in failures), failures
    assert not any(apply_0018.NOT_A_FIRST_APPLY in failure for failure in failures), failures


def test_a_superuser_applier_needs_no_admin_on_the_owner() -> None:
    superuser = t17.role_row(
        APPLIER, superuser=True, inherit=True, login=True, is_applying_role=True
    )
    roles = [t17.AUTHENTICATOR_ROW, superuser, *(t17.role_row(r) for r in apply_0018.NEW_ROLES)]
    memberships = [row for row in t17.MEMBERSHIPS if row[1] != APPLIER]
    pre, post = _state(
        pre_overrides={"roles": roles, "memberships": memberships},
        roles=roles,
        memberships=memberships,
    )
    assert apply_0018.pre_check_failures(pre) == []
    assert apply_0018.post_check_failures(pre, post) == []


@pytest.mark.parametrize(
    ("name", "rows", "expected"),
    [
        (
            "roles",
            [*t17.ROLES[:-1], t17.role_row("ucpe_space_db", login=True)],
            "the role 'ucpe_space_db' changed during the apply",
        ),
        (
            "memberships",
            [*t17.MEMBERSHIPS, (OWNER, APPLIER, True, False, True, True)],
            "appeared during the apply",
        ),
        (
            "grants",
            t17._grants_with(GRANTS, "ucpe_api_writer", "analysis_runs", ["INSERT"]),
            "ucpe_api_writer holds ['INSERT'] on the table analysis_runs after the apply",
        ),
        ("policies", POLICIES[1:], "is gone after the apply"),
        ("function", [], "is missing after the apply"),
        ("function", [FUNCTION_PRE], "EXECUTE is"),
        ("function", _with(FUNCTION_POST, acl=["service_role=EXECUTE"]), "EXECUTE is"),
        ("function", _with(FUNCTION_POST, owner=APPLIER), "owner changed during the apply"),
        ("forecast", [FORECAST_PRE], "EXECUTE is"),
        ("forecast", _with(FORECAST_POST, acl=[f"{OWNER}=EXECUTE"]), "EXECUTE is"),
        ("forecast", _with(FORECAST_POST, source="BEGIN RETURN NULL; END;"), "source changed"),
        ("forecast", [FORECAST_POST, FORECAST_POST], "appears 2 times after the apply"),
        ("other_functions", [], "is gone after the apply"),
        (
            "security",
            security_rows(PRODUCTION_SERVER, applied=False),
            "service_role holds ['DELETE', 'INSERT', 'MAINTAIN', 'REFERENCES', 'SELECT', 'TRIGGER',"
            " 'TRUNCATE', 'UPDATE'] on analysis_runs after the apply",
        ),
        (
            "security",
            _security_with(
                security_rows(PRODUCTION_SERVER, applied=True), "predictions", service_role=[]
            ),
            "service_role holds [] on predictions after the apply, not ['SELECT']",
        ),
        (
            "security",
            _security_with(
                security_rows(PRODUCTION_SERVER, applied=True), "watchlist", service_role=["SELECT"]
            ),
            "the security of table 'watchlist' changed during the apply",
        ),
        (
            "security",
            _security_with(
                security_rows(PRODUCTION_SERVER, applied=True), "predictions", anon=["SELECT"]
            ),
            "the security of table 'predictions' changed during the apply",
        ),
        ("schema_fingerprint", t17.FINGERPRINT[1:], "is gone after the apply"),
        ("event_triggers", [], "the event trigger 'pgrst_ddl_watch' is gone after the apply"),
        (
            "inventory_T",
            [("predictions", "TRUNCATE")],
            "a core write surface remains after the apply: T predictions TRUNCATE",
        ),
        (
            "inventory_F",
            [(f"{apply_0018.FORECAST_REFERENCE}(jsonb, jsonb, jsonb, jsonb, jsonb)", OWNER)],
            "a core write surface remains after the apply: F public.save_forecast_bundle",
        ),
    ],
)
def test_every_departure_from_the_reviewed_result_refuses(
    name: str, rows: list[tuple], expected: str
) -> None:
    pre, post = _state(**{name: rows})
    failures = apply_0018.post_check_failures(pre, post)
    assert failures and any(expected in failure for failure in failures), failures


# ------------------------------------------------------------------------ one transaction


def test_a_first_apply_runs_every_check_in_one_committed_transaction() -> None:
    database = FakeDatabase(healthy_results())
    outcome, captured = _apply(database)
    checks = [query for _name, query, _fields in apply_0018.read_only_checks(PRODUCTION_SERVER)]
    assert database.executed() == [
        *apply_0018.TIMEOUT_STATEMENTS,
        apply_0018.ADVISORY_LOCK_SQL,
        apply_0018.ROLES_SQL,
        apply_0018.SERVER_VERSION_SQL,
        *checks,
        MIGRATION_SQL,
        *checks,
    ]
    assert database.commits == 1 and database.rollbacks == 0
    assert outcome["outcome"] == "APPLIED" and outcome["committed"] is True
    assert outcome["executed_migration_sha256"] == apply_0018.MIGRATION_SHA256
    assert len(outcome["pre_inventory_T"]) == 31 and outcome["post_inventory_T"] == []
    assert captured["committed"] is True


def test_a_refused_pre_check_never_runs_the_migration() -> None:
    database = FakeDatabase(
        healthy_results(
            inventory_V=([("public.some_view", "predictions")], []),
        )
    )
    with pytest.raises(ProvenanceRefused, match="outside D6's revoke set"):
        _apply(database)
    assert MIGRATION_SQL not in database.executed()
    assert database.commits == 0 and database.rollbacks == 1


def test_a_refused_post_check_rolls_the_migration_back() -> None:
    database = FakeDatabase(healthy_results(forecast=([FORECAST_PRE], [FORECAST_PRE])))
    with pytest.raises(ProvenanceRefused, match="rolled back"):
        _apply(database)
    assert MIGRATION_SQL in database.executed()
    assert database.commits == 0 and database.rollbacks == 1


# ------------------------------------------------------------------------ what is published


def test_the_applying_role_and_other_unlisted_roles_are_withheld_everywhere() -> None:
    payload = {
        "pre_roles": [
            {"role": "owner_login", "is_applying_role": True},
            {"role": "ucpe_api_writer", "is_applying_role": False},
        ],
        "pre_memberships": [{"role": OWNER, "member": "owner_login"}],
        "pre_other_functions": [
            {"owner": "supabase_admin", "acl": "{supabase_admin=X/supabase_admin}"}
        ],
        "pre_inventory_F": [{"object": "public.f()", "detail": "owner_login"}],
        "pre_schema": [{"owner": "pg_database_owner"}],
        "detail": "the membership ('ucpe_bundle_owner', 'owner_login', True) appeared",
        "acl": ["service_role=EXECUTE", "dashboard_user=EXECUTE"],
    }
    published = apply_0018._published(payload)
    text = json.dumps(published)
    for name in ("owner_login", "supabase_admin", "dashboard_user"):
        assert name not in text, name
    for name in ("ucpe_api_writer", OWNER, "pg_database_owner", "service_role"):
        assert name in text, name
    assert published["pre_roles"][0]["role"] == apply_0018.WITHHELD
    assert published["acl"] == ["service_role=EXECUTE", f"{apply_0018.WITHHELD}=EXECUTE"]


def test_a_withheld_name_inside_a_longer_word_is_left_alone() -> None:
    payload = {
        "pre_roles": [{"role": "postgres", "is_applying_role": True}],
        "note": "postgresql:///x and postgres_extra and not_postgres and postgres",
    }
    assert apply_0018._published(payload)["note"] == (
        f"postgresql:///x and postgres_extra and not_postgres and {apply_0018.WITHHELD}"
    )


def test_main_publishes_its_report_and_its_output(tmp_path: Path, monkeypatch, capsys) -> None:
    applied = healthy_results(REHEARSAL_SERVER)
    for _name, query, _fields in apply_0018.read_only_checks(REHEARSAL_SERVER):
        rows = applied[query]
        applied[query] = Each([rows[0], rows[1], rows[1], rows[1]])
    database = FakeDatabase(applied)
    monkeypatch.setattr(apply_0018, "load_driver", lambda: database)
    report = tmp_path / "report.json"
    code = apply_0018.main(
        ["--mode=rehearse", f"--report={report}"],
        environ={apply_0018.REHEARSAL_URL_VARIABLE: REHEARSAL_URL},
    )
    assert code == 0
    output = capsys.readouterr().out
    for text in (report.read_text(), output):
        assert f"'{APPLIER}'" not in text and f'"{APPLIER}"' not in text
        assert apply_0018.WITHHELD in text
        assert "NEVER-SHOWN" not in text


# ------------------------------------------------------------------------ the entrypoint


def test_apply_without_the_exact_token_refuses_before_anything(tmp_path: Path) -> None:
    report = tmp_path / "report.json"
    code = apply_0018.main(["--mode=apply", "--confirm=yes", f"--report={report}"], environ={})
    assert code == 2
    record = json.loads(report.read_text())
    assert record["outcome"] == "REFUSED" and apply_0018.CONFIRMATION in record["detail"]
    assert record["committed"] is False


def test_the_rehearsal_reaches_only_a_local_socket_and_never_beside_the_secret() -> None:
    args = apply_0018.build_parser().parse_args(["--mode=rehearse"])
    with pytest.raises(ProvenanceRefused, match="local unix-socket URL"):
        apply_0018.rehearse(args, {apply_0018.REHEARSAL_URL_VARIABLE: DATABASE_URL}, {})
    environ = {apply_0018.REHEARSAL_URL_VARIABLE: REHEARSAL_URL, "SUPABASE_DB_URL": DATABASE_URL}
    with pytest.raises(ProvenanceRefused, match="never runs where the production database"):
        apply_0018.rehearse(args, environ, {})


def test_a_rehearsal_applies_once_and_proves_a_second_apply_refuses(monkeypatch) -> None:
    applied = healthy_results(REHEARSAL_SERVER)
    # The second apply's pre-reads see the applied state: SELECT only, EXECUTE on neither function.
    for _name, query, _fields in apply_0018.read_only_checks(REHEARSAL_SERVER):
        rows = applied[query]
        applied[query] = Each([rows[0], rows[1], rows[1], rows[1]])
    database = FakeDatabase(applied)
    monkeypatch.setattr(apply_0018, "load_driver", lambda: database)
    args = apply_0018.build_parser().parse_args(["--mode=rehearse"])
    captured: dict[str, Any] = {}
    outcome = apply_0018.rehearse(
        args, {apply_0018.REHEARSAL_URL_VARIABLE: REHEARSAL_URL}, captured
    )
    assert outcome["outcome"] == "REHEARSED"
    assert outcome["second_apply_refusal"].count(apply_0018.NOT_A_FIRST_APPLY) == 1
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
    monkeypatch.setattr(apply_0018, "load_driver", lambda: driver)
    report = tmp_path / "report.json"
    environ = {apply_0018.REHEARSAL_URL_VARIABLE: REHEARSAL_URL}
    code = apply_0018.main(["--mode=rehearse", f"--report={report}"], environ=environ)
    assert code == 1
    record = json.loads(report.read_text())
    assert record["outcome"] == "FAILED" and record["error_type"] == "Unreachable"
    assert "withheld" in record["detail"]
    output = capsys.readouterr()
    for text in (report.read_text(), output.out, output.err):
        assert "migration_0018_rehearsal?host" not in text and "NEVER-SHOWN" not in text


def test_a_half_applied_state_is_refused_but_never_taken_for_a_second_apply() -> None:
    """SELECT only on the tables while a function still executes for service_role: not 0018's
    result, so it is no second apply; the state itself is refused."""

    _pre, post = _state()
    half = dict(post)
    half["forecast"] = t17._dicts(apply_0018.FUNCTION_FIELDS, [FORECAST_PRE])
    assert apply_0018.already_applied(half) is False
    failures = apply_0018.pre_check_failures(half)
    assert failures and not any(apply_0018.NOT_A_FIRST_APPLY in f for f in failures), failures
    half = dict(post)
    half["inventory_T"] = [{"object": "predictions", "detail": "INSERT"}]
    assert apply_0018.already_applied(half) is False


def test_the_applying_role_is_withheld_even_where_only_its_own_row_names_it() -> None:
    payload = {
        "pre_roles": [{"role": "solo_owner", "is_applying_role": True}],
        "detail": "the applying role solo_owner refused",
        "acl": "{anon=r/grantor_only_role}",
    }
    text = json.dumps(apply_0018._published(payload))
    assert "solo_owner" not in text and "grantor_only_role" not in text
    assert "anon=r/" in text


def test_only_acl_text_is_read_for_role_names() -> None:
    payload = {
        "pre_roles": [{"role": "ucpe_api_writer", "is_applying_role": False}],
        "pre_function": [
            {"config": ["search_path=pg_catalog, pg_temp"], "acl": ["x_admin=EXECUTE"]}
        ],
        "pre_schema_fingerprint": [
            {"item": "t/column/c", "detail": "text notnull=true acl={y_admin=r/z}"}
        ],
    }
    published = apply_0018._published(payload)
    assert published["pre_function"][0]["config"] == ["search_path=pg_catalog, pg_temp"]
    assert published["pre_function"][0]["acl"] == [f"{apply_0018.WITHHELD}=EXECUTE"]
    detail = published["pre_schema_fingerprint"][0]["detail"]
    assert detail == f"text notnull=true acl={{{apply_0018.WITHHELD}=r/{apply_0018.WITHHELD}}}"
