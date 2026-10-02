"""The one-shot apply of migration 0015 (B9's forecast-bundle RPC). No database is contacted.

Every database interaction runs against a fake driver that behaves like psycopg 3 where it matters:
a connection used as a context manager commits on success and rolls back on an exception, a
statement is recorded with its parameters, and a check read before and after the migration can
return different rows. The real PostgreSQL rehearsals run in
.github/workflows/migration-0015-rehearsal.yml (every pull request) and inside the dispatch job
(.github/workflows/apply-migration-0015.yml), before the secret is handed to any step.
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
from scripts import apply_migration_0015 as apply_0015

ROOT = Path(__file__).resolve().parents[2]
MIGRATION_BYTES = (ROOT / apply_0015.MIGRATION).read_bytes()
MIGRATION_SQL = MIGRATION_BYTES.decode("utf-8")
DATABASE_URL = "postgresql://owner:NEVER-SHOWN-SECRET@db.never-contacted.invalid:5432/postgres"
REHEARSAL_URL = "postgresql:///migration_0015_rehearsal?host=/var/run/postgresql"
PRODUCTION_SERVER = 170006
REHEARSAL_SERVER = 160010
ALL = list(apply_0015.table_privileges_for(PRODUCTION_SERVER))
CHECK_NAMES = ("targets", "columns", "constraints", "indexes", "triggers", "functions", "schema",
               "other", "other_schema", "event_triggers")


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


# ------------------------------------------------------------------------ production after 0014


def security_row(table: str, *, privileges: list[str] = ALL, **changes: Any) -> tuple:
    values = {
        "relations_named_so": 1, "relkind": "r", "owned_by_applying_role": True,
        "row_level_security": True, "row_level_security_forced": False, "policies": 0,
        "public_has_a_privilege": False, "column_grant_to_public_anon_or_authenticated": False,
        "anon": [], "authenticated": [], "service_role": list(privileges),
    }
    values.update(changes)
    return (table, *(values[field] for field in apply_0015.SECURITY_FIELDS[1:]))


TARGETS = [security_row(table) for table in apply_0015.TARGET_TABLES]
OTHER = [security_row(table) for table in sorted(apply_0015.OTHER_TABLES)]
COLUMNS = [
    ("prediction_derivatives_snapshots.prediction_id", "text", True, False, False, False, False),
    ("prediction_feature_snapshots.prediction_id", "text", True, False, False, False, False),
    ("predictions.prediction_id", "text", True, False, False, False, False),
    ("predictions.reference_price", "numeric", True, False, False, False, False),
]
CONSTRAINTS = [
    ("prediction_feature_snapshots.prediction_feature_snapshots_pkey", "p", True, False,
     "PRIMARY KEY (prediction_id)", ["prediction_id"]),
    ("predictions.predictions_pkey", "p", True, False, "PRIMARY KEY (prediction_id)",
     ["prediction_id"]),
    ("predictions.predictions_reference_price_chk", "c", False, False,
     "CHECK (((reference_price > (0)::numeric) AND (reference_price < 'Infinity'::numeric)))"
     " NOT VALID", ["reference_price"]),
]
INDEXES = [
    ("predictions.predictions_pkey",
     "CREATE UNIQUE INDEX predictions_pkey ON public.predictions USING btree (prediction_id)"),
]
TRIGGERS = [
    ("predictions.trg_pred_reject_update", "O", 19, "public.reject_core_evidence_mutation", 0,
     False, False),
]
FUNCTION_ROW = (
    apply_0015.FUNCTION, apply_0015.FUNCTION_ARGUMENTS, "jsonb", "plpgsql", False, "f", "v",
    list(apply_0015.FUNCTION_CONFIG), True, apply_0015.FUNCTION_SOURCE, False, False, False, True,
)
SCHEMA = [("public", "postgres", "{postgres=UC/postgres,=U/postgres}", True)]
OTHER_SCHEMA = [
    ("prediction_outcomes/trigger/trg_pout_reject_update", "O 19 reject_core_evidence_mutation"),
    ("watchlist/column/normalized_symbol", "text notnull=true default= acl="),
]
EVENT_TRIGGERS = [("pgrst_ddl_watch", "ddl_command_end", "O", "extensions.pgrst_ddl_watch", "")]


def healthy_results(version: int = PRODUCTION_SERVER, **overrides: Any) -> dict[str, Any]:
    """A first apply on production as it is after 0014: every pre read, then every post read."""

    pre_post = {
        "targets": (TARGETS, TARGETS),
        "columns": (COLUMNS, COLUMNS),
        "constraints": (CONSTRAINTS, CONSTRAINTS),
        "indexes": (INDEXES, INDEXES),
        "triggers": (TRIGGERS, TRIGGERS),
        "functions": ([], [FUNCTION_ROW]),
        "schema": (SCHEMA, SCHEMA),
        "other": (OTHER, OTHER),
        "other_schema": (OTHER_SCHEMA, OTHER_SCHEMA),
        "event_triggers": (EVENT_TRIGGERS, EVENT_TRIGGERS),
    }
    pre_post.update(overrides)
    results: dict[str, Any] = {
        apply_0015.ROLES_SQL: [(3,)],
        apply_0015.SERVER_VERSION_SQL: [(version,)],
    }
    for name, query, _fields in apply_0015.read_only_checks(version):
        before, after = pre_post[name]
        results[query] = Each([before, after])
    return results


def _apply(database: FakeDatabase) -> tuple[dict[str, Any], dict[str, Any]]:
    captured: dict[str, Any] = {}
    outcome = apply_0015.apply_in_one_transaction(
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

    fields = {name: checked for name, _query, checked in apply_0015.read_only_checks(170006)}
    results = healthy_results()
    pre, post = {}, {}
    for name, query, _fields in apply_0015.read_only_checks(170006):
        before, after = results[query]
        pre[name] = _dicts(fields[name], before)
        post[name] = _dicts(fields[name], overrides.get(name, after))
    return pre, post


# ------------------------------------------------------------------------ what the route is


def test_the_script_imports_only_the_standard_library_at_module_level() -> None:
    tree = ast.parse((ROOT / apply_0015.SCRIPT).read_text(encoding="utf-8"))
    imported = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            imported |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert imported <= {"__future__", "argparse", "hashlib", "json", "os", "platform", "re",
                        "subprocess", "sys", "collections", "pathlib", "types", "typing"}


def test_it_names_itself_its_workflow_and_the_reviewed_bytes() -> None:
    assert apply_0015.SCRIPT == "scripts/apply_migration_0015.py"
    assert apply_0015.WORKFLOW == ".github/workflows/apply-migration-0015.yml"
    assert (ROOT / apply_0015.WORKFLOW).is_file()
    assert apply_0015.MIGRATION == "migrations/0015_prediction_bundle_rpc.sql"
    assert hashlib.sha256(MIGRATION_BYTES).hexdigest() == apply_0015.MIGRATION_SHA256
    assert apply_0015.CONFIRMATION == "APPLY-MIGRATION-0015-ONCE"
    assert apply_0015.REHEARSAL_URL_VARIABLE == "MIGRATION_0015_REHEARSAL_URL"


def test_its_advisory_lock_is_its_own() -> None:
    keys = {}
    for path in sorted((ROOT / "scripts").glob("apply_*.py")):
        found = re.findall(r"pg_advisory_xact_lock\((\d+)\)", path.read_text(encoding="utf-8"))
        keys.update({key: path.name for key in found})
    assert keys["5000015"] == "apply_migration_0015.py"
    assert list(keys.values()).count("apply_migration_0015.py") == 1


# The trust machinery is 0011's, copied verbatim: a reviewed route, not a new one.
SHARED = ("table_privileges_for", "_held", "_security_sql", "build_parser", "ensure_source_path",
          "enter_isolated_runtime", "observe", "verify_dispatch", "attest_dispatch",
          "attest_loaded_modules", "load_driver", "migration_bytes", "main", "_run",
          "_count_after", "_unchanged_failures", "_read_checks", "_rows", "_plain", "_row", "_git",
          "_refusal_record", "_commit_state", "_is_refusal", "_write_report")


@pytest.mark.parametrize("name", SHARED)
def test_its_trust_machinery_is_0011_s_verbatim(name: str) -> None:
    assert inspect.getsource(getattr(apply_0015, name)) == inspect.getsource(
        getattr(apply_0011, name)
    ), name


def test_its_transaction_and_rehearsal_are_0011_s_up_to_the_migration_number() -> None:
    for name in ("apply_in_one_transaction", "_refusal"):
        ours = inspect.getsource(getattr(apply_0015, name))
        theirs = inspect.getsource(getattr(apply_0011, name)).replace("0011", "0015")
        assert ours == theirs, name
    ours = inspect.getsource(apply_0015.rehearse).split('"""')
    theirs = inspect.getsource(apply_0011.rehearse).replace("0011", "0015").split('"""')
    assert ours[0] == theirs[0] and ours[2] == theirs[2], "only the docstring differs"
    for constant in ("TIMEOUT_STATEMENTS", "API_ROLES", "TABLE_PRIVILEGES",
                     "MINIMUM_SERVER_VERSION", "MAINTAIN_SINCE_SERVER_VERSION", "SECURITY_FIELDS",
                     "PINNED_PYTHON", "EXPECTED_REPOSITORY", "REQUIRED_REF", "REQUIRED_EVENT"):
        assert getattr(apply_0015, constant) == getattr(apply_0011, constant), constant


# ------------------------------------------------------------------------ it matches the migration


def test_its_expected_function_is_the_migration_s_own() -> None:
    body = re.search(r"AS \$function\$(.*?)\$function\$;", MIGRATION_SQL, re.S).group(1)
    assert body == apply_0015.FUNCTION_SOURCE
    path = re.search(r"SET search_path = ([^\n]+)\n", MIGRATION_SQL).group(1)
    assert apply_0015.FUNCTION_CONFIG == (f"search_path={path}",)
    signature = re.search(
        r"CREATE OR REPLACE FUNCTION public\.save_prediction_bundle\((.*?)\)\nRETURNS jsonb",
        MIGRATION_SQL, re.S,
    ).group(1)
    arguments = [" ".join(part.split()[:2]) for part in signature.split(",")]
    assert ", ".join(arguments) == apply_0015.FUNCTION_ARGUMENTS
    assert f"GRANT EXECUTE ON FUNCTION {apply_0015.FUNCTION_REFERENCE}(jsonb, jsonb, jsonb)" in (
        MIGRATION_SQL)
    for table in apply_0015.TARGET_TABLES:
        assert f"INSERT INTO public.{table} (" in MIGRATION_SQL, table


def test_the_other_tables_are_every_other_table_of_migrations_0001_to_0014() -> None:
    created = set()
    for path in sorted((ROOT / "migrations").glob("*.sql")):
        if path.name < "0015":
            created |= set(re.findall(
                r"CREATE TABLE IF NOT EXISTS (?:public\.)?([a-z_0-9]+)", path.read_text()
            ))
    assert sorted(created - set(apply_0015.TARGET_TABLES)) == list(apply_0015.OTHER_TABLES)
    assert set(apply_0015.TARGET_TABLES) <= created


# ------------------------------------------------------------------------ the checks read only


FORBIDDEN = re.compile(
    r"\b(INSERT|UPDATE|DELETE|ALTER|CREATE|DROP|GRANT|REVOKE|TRUNCATE|COPY|CALL|DO|SET|VALIDATE)\b"
)


def _without_literals(query: str) -> str:
    return re.sub(r"'(?:[^']|'')*'", "''", query)


@pytest.mark.parametrize("version", [PRODUCTION_SERVER, REHEARSAL_SERVER])
def test_every_check_is_a_read_only_catalog_query(version: int) -> None:
    queries = [query for _name, query, _fields in apply_0015.read_only_checks(version)]
    queries += [apply_0015.ROLES_SQL, apply_0015.SERVER_VERSION_SQL]
    for query in queries:
        bare = _without_literals(query)
        assert query.lstrip().startswith("SELECT"), query[:60]
        assert not FORBIDDEN.search(bare), (FORBIDDEN.search(bare).group(0), query[:80])
        assert "%s" not in query and "%(" not in query, "no parameters"
        for source in re.findall(r"\b(?:FROM|JOIN)\s+([a-z_.]+)", bare):
            assert source.startswith("pg_catalog.") or source == "", (source, query[:80])
        assert "public." not in bare.replace("'public.' || t.name", ""), query[:80]


@pytest.mark.parametrize("version", [PRODUCTION_SERVER, REHEARSAL_SERVER])
def test_no_check_orders_by_a_column_position(version: int) -> None:
    for _name, query, _fields in apply_0015.read_only_checks(version):
        assert not re.search(r"ORDER BY \s*\d", query), query[-80:]
        assert not re.search(r",\s*\d+\s+COLLATE", query), query[-80:]


def test_the_checks_cover_the_three_tables_the_function_the_schema_and_every_other_table() -> None:
    names = [name for name, _query, _fields in apply_0015.read_only_checks(PRODUCTION_SERVER)]
    assert tuple(names) == CHECK_NAMES
    targets = apply_0015.targets_security_sql(PRODUCTION_SERVER)
    for table in apply_0015.TARGET_TABLES:
        assert f"('{table}')" in targets
        assert f"('{table}')" in apply_0015.COLUMNS_SQL
    for table in apply_0015.OTHER_TABLES:
        assert f"('{table}')" in apply_0015.other_security_sql(PRODUCTION_SERVER)
        assert f"('{table}')" in apply_0015.OTHER_SCHEMA_SQL
    assert "'MAINTAIN'" in targets
    assert "'MAINTAIN'" not in apply_0015.targets_security_sql(REHEARSAL_SERVER)


# ------------------------------------------------------------------------ the pure verdicts


def test_a_healthy_first_apply_has_no_pre_or_post_failure() -> None:
    pre, post = _state()
    assert apply_0015.pre_check_failures(pre) == []
    assert apply_0015.post_check_failures(pre, post) == []


def test_a_second_apply_is_refused_as_not_a_first_apply() -> None:
    pre, _post = _state()
    fields = dict((n, f) for n, _q, f in apply_0015.read_only_checks(PRODUCTION_SERVER))
    pre["functions"] = _dicts(fields["functions"], [FUNCTION_ROW])
    assert apply_0015.pre_check_failures(pre) == [
        f"{apply_0015.NOT_A_FIRST_APPLY}: the function {apply_0015.FUNCTION_REFERENCE}"
        f"({apply_0015.FUNCTION_ARGUMENTS}) already exists"
    ]


@pytest.mark.parametrize(
    ("changes", "expected"),
    [
        ({"service_role": ["SELECT"]}, "service_role lacks INSERT"),
        ({"service_role": []}, "service_role lacks INSERT, SELECT"),
        ({"relkind": "p"}, "not an ordinary table"),
        ({"relations_named_so": 2}, "relations have this name, not one"),
    ],
)
def test_a_target_the_function_could_not_write_refuses(
    changes: dict[str, Any], expected: str
) -> None:
    pre, _post = _state()
    pre["targets"][2].update(changes)
    failures = apply_0015.pre_check_failures(pre)
    assert len(failures) == 1 and expected in failures[0] and failures[0].startswith("predictions:")


def test_ownership_of_the_targets_is_recorded_not_required() -> None:
    pre, _post = _state()
    for row in pre["targets"]:
        row["owned_by_applying_role"] = False
    assert apply_0015.pre_check_failures(pre) == []


def test_a_schema_the_applying_role_cannot_create_in_refuses() -> None:
    pre, _post = _state()
    pre["schema"][0]["applying_role_may_create"] = False
    assert apply_0015.pre_check_failures(pre) == [
        "the applying role may not CREATE in schema public"
    ]


def _function(**changes: Any) -> list[tuple]:
    values = dict(zip(apply_0015.FUNCTION_FIELDS, FUNCTION_ROW, strict=True))
    values.update(changes)
    return [tuple(values[field] for field in apply_0015.FUNCTION_FIELDS)]


@pytest.mark.parametrize(
    ("name", "rows", "expected"),
    [
        ("functions", [], f"{apply_0015.FUNCTION_REFERENCE}: is missing after the apply"),
        ("functions", [FUNCTION_ROW, FUNCTION_ROW], "appears 2 times after the apply"),
        ("functions", _function(security_definer=True), "security_definer is True"),
        ("functions", _function(volatility="s"), "volatility is 's'"),
        ("functions", _function(config=[]), "config is []"),
        ("functions", _function(source="BEGIN RETURN NULL; END;"), "source is"),
        ("functions", _function(arguments="p_prediction jsonb"), "arguments is"),
        ("functions", _function(returns="json"), "returns is 'json'"),
        ("functions", _function(owned_by_applying_role=False), "owned_by_applying_role is False"),
        ("functions", _function(execute_public=True), "execute_public is True"),
        ("functions", _function(execute_anon=True), "execute_anon is True"),
        ("functions", _function(execute_authenticated=True), "execute_authenticated is True"),
        ("functions", _function(execute_service_role=False), "execute_service_role is False"),
        ("columns", [(*COLUMNS[0][:2], False, *COLUMNS[0][3:]), *COLUMNS[1:]],
         "the column 'prediction_derivatives_snapshots.prediction_id' changed during the apply"),
        ("constraints", CONSTRAINTS[:2], "is gone after the apply"),
        ("indexes", [], "is gone after the apply"),
        ("triggers", [*TRIGGERS, ("predictions.trg_new", "O", 5, "public.x", 0, False, False)],
         "the trigger 'predictions.trg_new' appeared during the apply"),
        ("schema", [("public", "postgres", "{postgres=UC/postgres,=UC/postgres}", True)],
         "the schema 'public' changed during the apply"),
        ("targets", [security_row(t, anon=["SELECT"]) for t in apply_0015.TARGET_TABLES],
         "the security of table 'prediction_derivatives_snapshots' changed"),
        ("other", [security_row(t, row_level_security=False) for t in
                   sorted(apply_0015.OTHER_TABLES)], "changed during the apply"),
        ("other_schema", [*OTHER_SCHEMA, ("watchlist/trigger/new", "O 19 x")],
         "the schema item 'watchlist/trigger/new' appeared during the apply"),
        ("event_triggers", [], "the event trigger 'pgrst_ddl_watch' is gone after the apply"),
    ],
)
def test_every_departure_from_the_reviewed_result_refuses(
    name: str, rows: list[tuple], expected: str
) -> None:
    pre, post = _state(**{name: rows})
    failures = apply_0015.post_check_failures(pre, post)
    assert failures and any(expected in failure for failure in failures), failures


# ------------------------------------------------------------------------ one transaction


def test_a_first_apply_runs_every_check_in_one_committed_transaction() -> None:
    database = FakeDatabase(healthy_results())
    outcome, captured = _apply(database)
    checks = [query for _name, query, _fields in apply_0015.read_only_checks(PRODUCTION_SERVER)]
    assert database.executed() == [
        *apply_0015.TIMEOUT_STATEMENTS, apply_0015.ADVISORY_LOCK_SQL, apply_0015.ROLES_SQL,
        apply_0015.SERVER_VERSION_SQL, *checks, MIGRATION_SQL, *checks,
    ]
    assert database.commits == 1 and database.rollbacks == 0
    assert outcome["outcome"] == "APPLIED" and outcome["committed"] is True
    assert outcome["executed_migration_sha256"] == apply_0015.MIGRATION_SHA256
    assert outcome["post_functions"][0]["source"] == apply_0015.FUNCTION_SOURCE
    assert captured["committed"] is True


def test_a_refused_pre_check_never_runs_the_migration() -> None:
    database = FakeDatabase(healthy_results(functions=([FUNCTION_ROW], [FUNCTION_ROW])))
    with pytest.raises(ProvenanceRefused, match=apply_0015.NOT_A_FIRST_APPLY):
        _apply(database)
    assert MIGRATION_SQL not in database.executed()
    assert database.commits == 0 and database.rollbacks == 1


def test_a_refused_post_check_rolls_the_migration_back() -> None:
    database = FakeDatabase(healthy_results(functions=([], _function(execute_anon=True))))
    with pytest.raises(ProvenanceRefused, match="rolled back"):
        _apply(database)
    assert MIGRATION_SQL in database.executed()
    assert database.commits == 0 and database.rollbacks == 1


@pytest.mark.parametrize("version", [140012, None, "17"])
def test_an_unsupported_server_refuses_before_any_check(version: Any) -> None:
    results = healthy_results()
    results[apply_0015.SERVER_VERSION_SQL] = [(version,)]
    database = FakeDatabase(results)
    with pytest.raises(ProvenanceRefused, match="is not PostgreSQL 15 or later"):
        _apply(database)
    assert database.executed()[-1] == apply_0015.SERVER_VERSION_SQL


def test_missing_api_roles_refuse() -> None:
    results = healthy_results()
    results[apply_0015.ROLES_SQL] = [(2,)]
    with pytest.raises(ProvenanceRefused, match="of the 3 Supabase API roles exist"):
        _apply(FakeDatabase(results))


# ------------------------------------------------------------------------ the entrypoint


def test_apply_without_the_exact_token_refuses_before_anything(tmp_path: Path) -> None:
    report = tmp_path / "report.json"
    code = apply_0015.main(["--mode=apply", "--confirm=yes", f"--report={report}"], environ={})
    assert code == 2
    record = json.loads(report.read_text())
    assert record["outcome"] == "REFUSED" and apply_0015.CONFIRMATION in record["detail"]
    assert record["committed"] is False


def test_the_rehearsal_reaches_only_a_local_socket_and_never_beside_the_secret() -> None:
    args = apply_0015.build_parser().parse_args(["--mode=rehearse"])
    with pytest.raises(ProvenanceRefused, match="local unix-socket URL"):
        apply_0015.rehearse(args, {apply_0015.REHEARSAL_URL_VARIABLE: DATABASE_URL}, {})
    environ = {apply_0015.REHEARSAL_URL_VARIABLE: REHEARSAL_URL, "SUPABASE_DB_URL": DATABASE_URL}
    with pytest.raises(ProvenanceRefused, match="never runs where the production database"):
        apply_0015.rehearse(args, environ, {})


def test_a_rehearsal_applies_once_and_proves_a_second_apply_refuses(monkeypatch) -> None:
    applied = healthy_results(REHEARSAL_SERVER)
    # The second apply's pre-reads see the applied state: the function exists.
    for _name, query, _fields in apply_0015.read_only_checks(REHEARSAL_SERVER):
        rows = applied[query]
        applied[query] = Each([rows[0], rows[1], rows[1], rows[1]])
    database = FakeDatabase(applied)
    monkeypatch.setattr(apply_0015, "load_driver", lambda: database)
    args = apply_0015.build_parser().parse_args(["--mode=rehearse"])
    captured: dict[str, Any] = {}
    outcome = apply_0015.rehearse(args, {apply_0015.REHEARSAL_URL_VARIABLE: REHEARSAL_URL},
                                  captured)
    assert outcome["outcome"] == "REHEARSED"
    assert apply_0015.NOT_A_FIRST_APPLY in outcome["second_apply_refusal"]
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
    monkeypatch.setattr(apply_0015, "load_driver", lambda: driver)
    report = tmp_path / "report.json"
    environ = {apply_0015.REHEARSAL_URL_VARIABLE: REHEARSAL_URL}
    code = apply_0015.main(["--mode=rehearse", f"--report={report}"], environ=environ)
    assert code == 1
    record = json.loads(report.read_text())
    assert record["outcome"] == "FAILED" and record["error_type"] == "Unreachable"
    assert "withheld" in record["detail"]
    output = capsys.readouterr()
    for text in (report.read_text(), output.out, output.err):
        assert "migration_0015_rehearsal?host" not in text and "NEVER-SHOWN" not in text
