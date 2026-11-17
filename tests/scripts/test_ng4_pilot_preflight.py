from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PREDICATE = ("SELECT NOT EXISTS (SELECT 1 FROM pg_catalog.pg_roles r CROSS JOIN "
             "(VALUES ('pg_read_all_data'),('pg_write_all_data')) g(rolname) "
             "WHERE pg_catalog.pg_has_role(r.oid, g.rolname::name, 'MEMBER') AND r.rolbypassrls "
             "AND NOT r.rolsuper "
             "AND r.rolname<>current_user AND NOT (g.rolname='pg_read_all_data' AND r.rolname IN "
             "('supabase_etl_admin','supabase_read_only_user')))")
SPEC = importlib.util.spec_from_file_location(
    "ng4_preflight", ROOT / "scripts/ng4_pilot_preflight.py"
)
preflight = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(preflight)


class Cursor:
    def __init__(self):
        self.statements = []
        self.result = (True,)
        self.public_bad = False
        self.public_any_schema_bad = False
        self.public_connect_bad = False
        self.bypass_members = "[]"
        self.bypass_fact = None
        self.ddl_triggers = "[]"
        self.ddl_fact = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, sql, params=()):
        self.statements.append((sql, params))
        if sql == preflight.DDL_EVENT_TRIGGERS_SQL:
            self.result = (self.ddl_triggers,)
        elif "json_agg" in sql:
            self.result = (self.bypass_members,)
        elif sql == preflight.PREREQUISITE_SQL["no_bypassrls_data_role_member"]:
            # the fact agrees with the members list unless told not to (delta review note 1)
            members = self.bypass_members
            consistent = members in ("[]", "") or not members.startswith("[")
            self.result = (consistent if self.bypass_fact is None else self.bypass_fact,)
        elif "count(*) FROM pg_event_trigger" in sql:
            parsed = json.loads(self.ddl_triggers)
            count = len(parsed) if isinstance(parsed, list) else 0
            self.result = (count if self.ddl_fact is None else self.ddl_fact,)
        elif self.public_bad and ("has_table_privilege('public'" in sql or
                                "has_function_privilege('public'" in sql):
            self.result = (1,)
        elif self.public_any_schema_bad and "pg_my_temp_schema" in sql:
            self.result = (True,)
        elif self.public_connect_bad and "'CONNECT'" in sql:
            self.result = (False,)
        elif "'CONNECT'" in sql:
            self.result = (True,)
        elif self.public_bad and ("has_schema_privilege('public'" in sql or
                                  "has_database_privilege('public'" in sql and "'CREATE'" in sql):
            self.result = (True,)
        elif "has_schema_privilege('public'" in sql or "has_database_privilege('public'" in sql:
            self.result = (False,)
        else:
            self.result = (0 if "count(" in sql.lower() else True,)

    def fetchone(self):
        return self.result


class Connection:
    def __init__(self):
        self.cursor_obj = Cursor()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def cursor(self):
        return self.cursor_obj


def test_first_statement_read_only_ends_rollback_and_has_no_mutation_keywords():
    conn = Connection()
    preflight.preflight(lambda: conn)
    sql = [q for q, _ in conn.cursor_obj.statements]
    assert sql[0] == "SET TRANSACTION READ ONLY"
    assert sql[1:3] == ["SET LOCAL statement_timeout = '5000'", "SET LOCAL lock_timeout = '2000'"]
    assert sql[-1] == "ROLLBACK"
    assert sql.index(preflight.BYPASSRLS_MEMBERS_SQL) > 0
    assert sql.index(preflight.BYPASSRLS_MEMBERS_SQL) < sql.index("ROLLBACK")
    assert sql.index(preflight.DDL_EVENT_TRIGGERS_SQL) > sql.index(preflight.BYPASSRLS_MEMBERS_SQL)
    assert sql.index(preflight.DDL_EVENT_TRIGGERS_SQL) < sql.index("ROLLBACK")
    assert "SET TRANSACTION READ ONLY" in sql[:sql.index(preflight.BYPASSRLS_MEMBERS_SQL)]
    forbidden = (
        "INSERT",
        "UPDATE",
        "DELETE",
        "CREATE",
        "ALTER",
        "GRANT",
        "REVOKE",
        "DROP",
        "TRUNCATE",
        "COMMIT",
    )
    stripped = [re.sub(r"'(?:[^']|'')*'", "''", statement) for statement in sql]
    assert not any(
        re.search(rf"\b{word}\b", statement, re.IGNORECASE)
        for statement in stripped
        for word in forbidden
    )
    assert not any(re.search(r"\bSET\s+TRANSACTION\s+READ\s+WRITE\b", statement, re.I)
                   for statement in sql)


def test_preflight_prerequisites_match_route_refusing_prechecks():
    route_spec = importlib.util.spec_from_file_location(
        "apply_0019_for_parity", ROOT / "scripts/apply_migration_0019.py"
    )
    route = importlib.util.module_from_spec(route_spec)
    route_spec.loader.exec_module(route)
    assert set(preflight.PREREQUISITES) == set(route.CHECKS)
    for key in preflight.PREREQUISITES:
        assert preflight.PREREQUISITE_SQL[key] == route.CHECKS[key]


def test_bypassrls_predicate_is_exact_and_write_membership_is_never_excepted():
    sql = preflight.PREREQUISITE_SQL["no_bypassrls_data_role_member"]
    assert sql == PREDICATE
    assert preflight.ALLOWED_BYPASSRLS_READERS == (
        "supabase_etl_admin", "supabase_read_only_user"
    )
    assert "NOT (g.rolname='pg_read_all_data'" in sql
    assert "pg_write_all_data' AND r.rolname IN" not in sql
    assert preflight.BYPASSRLS_MEMBERS_SQL.startswith(
        "SELECT coalesce(json_agg(json_build_array(x.rn, x.dn) ORDER BY x.rn, x.dn), "
        "'[]'::json)::text "
        "FROM (SELECT DISTINCT r.rolname AS rn, g.rolname AS dn "
        "FROM pg_catalog.pg_roles r CROSS JOIN"
    )


def test_allowlisted_reader_fact_is_informational_int():
    report = preflight.preflight(lambda: Connection())
    assert "bypassrls_allowlisted_readers" not in report["failing"]
    assert type(report["facts"]["bypassrls_allowlisted_readers"]) is int


def test_public_inclusive_facts_and_signal_backend_are_reported():
    conn = Connection()
    report = preflight.preflight(lambda: conn)
    facts = report["facts"]
    assert {"lattice_space_absent", "applier_signal_backend", "public_relation_privileges",
            "public_executable_definers", "public_schema_create", "public_database_create",
            "public_database_temporary"} <= facts.keys()
    queries = "\n".join(sql for sql, _ in conn.cursor_obj.statements)
    assert "has_table_privilege('public'" in queries
    assert "has_any_column_privilege('public'" in queries
    assert "has_sequence_privilege('public'" in queries
    assert "has_function_privilege('public'" in queries
    assert "has_schema_privilege('public'" in queries
    assert "has_database_privilege(" in queries and "'public',current_database()" in queries
    encoded = json.dumps(report)
    assert "postgresql" not in encoded.lower()
    assert "postgresql://" not in encoded.lower()


def test_bypassrls_members_are_reported_safely_outside_facts():
    conn = Connection()
    report = preflight.preflight(lambda: conn)
    assert report["bypassrls_data_role_members"] == []
    assert all(type(value) in (bool, int) for value in report["facts"].values())
    conn.cursor_obj.bypass_members = json.dumps([["x_reader", "pg_read_all_data"]])
    captured = {}
    report = preflight.preflight(lambda: conn, captured)
    expected = [{"role": "x_reader", "data_role": "pg_read_all_data"}]
    assert report["bypassrls_data_role_members"] == expected
    assert captured["bypassrls_data_role_members"] == expected


def test_ddl_event_trigger_reporting_and_sql_safety():
    conn = Connection()
    assert preflight.preflight(lambda: conn)["ddl_event_triggers"] == []
    conn.cursor_obj.ddl_triggers = json.dumps([
        ["pgrst_ddl_watch", "ddl_command_end", "O"],
        ["another_watch", "ddl_command_start", "R"],
    ])
    assert preflight.preflight(lambda: conn)["ddl_event_triggers"] == [
        {"name": "pgrst_ddl_watch", "event": "ddl_command_end", "enabled": "origin"},
        {"name": "another_watch", "event": "ddl_command_start", "enabled": "replica"},
    ]
    for code, state in (("O", "origin"), ("D", "disabled"), ("R", "replica"),
                        ("A", "always"), ("?", "<unexpected>")):
        conn.cursor_obj.ddl_triggers = json.dumps([["pgrst_ddl_watch", "ddl_command_end", code]])
        assert preflight.preflight(lambda: conn)["ddl_event_triggers"] == [{
            "name": "pgrst_ddl_watch", "event": "ddl_command_end", "enabled": state
        }]
    conn.cursor_obj.ddl_triggers = json.dumps([
        ["bad/name_0123456789abcdef", "unknown_event", "O"]
    ])
    assert preflight.preflight(lambda: conn)["ddl_event_triggers"] == [{
        "name": "<non-identifier>", "event": "<unexpected>", "enabled": "origin"
    }]
    conn.cursor_obj.ddl_triggers = json.dumps([
        [f"watch_{i}", "ddl_command_end", "O"] for i in range(21)
    ])
    report = preflight.preflight(lambda: conn)
    assert len(report["ddl_event_triggers"]) == 20
    assert report["ddl_event_triggers_truncated"] is True
    for name in ("bad/name", "Upper_watch", "has space", "a@b", "postgresql://h", "9lead"):
        conn.cursor_obj.ddl_triggers = json.dumps([[name, "ddl_command_end", "O"]])
        assert preflight.preflight(lambda: conn)["ddl_event_triggers"][0]["name"] == (
            "<non-identifier>"), name
    sql = preflight.DDL_EVENT_TRIGGERS_SQL
    assert "pg_catalog.pg_event_trigger" in sql
    # The same planted-function class as the role checks: the aggregate and the array builder are
    # schema-qualified (coalesce is a construct, not a function).
    assert "pg_catalog.json_agg(pg_catalog.json_build_array(" in sql
    assert not re.search(r"(?<!pg_catalog\.)\b(json_agg|json_build_array)\(", sql)
    assert not any(word in sql.lower() for word in
                   ("evtfoid", "evttags", "prosrc", "pg_proc", "pg_get_functiondef"))


def test_ddl_event_trigger_bad_shapes_and_count_fail_closed_in_main(monkeypatch, capsys):
    cases = (("null", 0, "MALFORMED_TRIGGERS"),
             ('[["x","ddl_command_end"]]', 1, "MALFORMED_TRIGGERS"),
             ('[["x","ddl_command_end","O","extra"]]', 1, "MALFORMED_TRIGGERS"),
             ("[]", 1, "INCONSISTENT_TRIGGERS"))
    for raw, fact, _error in cases:
        conn = Connection()
        conn.cursor_obj.ddl_triggers = raw
        conn.cursor_obj.ddl_fact = fact
        driver = type("Driver", (), {"connect": staticmethod(
            lambda *a, conn=conn, **k: conn)})
        monkeypatch.setattr(preflight, "enter_isolated_runtime", lambda _wheelhouse: object())
        monkeypatch.setattr(preflight, "attest_dispatch", lambda *args: {})
        monkeypatch.setattr(preflight, "attest_loaded_modules", lambda _isolation: None)
        monkeypatch.setattr(preflight, "load_driver", lambda driver=driver: driver)
        code = preflight.main(["--mode=run", "--wheelhouse=/tmp/wheels",
                               "--expected-sha=" + "a" * 40], environ={
            "SUPABASE_DB_URL": "postgresql://localhost/test"
        })
        captured = capsys.readouterr().out
        output = json.loads(captured.splitlines()[-1])
        assert code == 1 and output["error"] == "RuntimeError", output
        assert "ddl_event_triggers" not in output


def test_bypassrls_member_names_and_data_roles_are_sanitized():
    conn = Connection()
    conn.cursor_obj.bypass_members = json.dumps([
        ["bad/name", "pg_read_all_data"], ["x_reader", "unexpected"]
    ])
    report = preflight.preflight(lambda: conn)
    assert report["bypassrls_data_role_members"] == [
        {"role": "<non-identifier>", "data_role": "pg_read_all_data"},
        {"role": "x_reader", "data_role": "<unexpected>"},
    ]


def test_every_non_identifier_role_name_is_replaced():
    for name in ("a@b", "postgresql://h", "has space", "Upper", "", "9lead", "x" * 64):
        conn = Connection()
        conn.cursor_obj.bypass_members = json.dumps([[name, "pg_write_all_data"]])
        report = preflight.preflight(lambda conn=conn: conn)
        assert report["bypassrls_data_role_members"] == [
            {"role": "<non-identifier>", "data_role": "pg_write_all_data"}
        ], name
        assert name not in json.dumps(report) or name == ""


def test_bypassrls_member_list_is_capped_and_sql_matches_prerequisite_predicate():
    conn = Connection()
    pairs = [[f"reader_{i}", "pg_read_all_data"] for i in range(21)]
    conn.cursor_obj.bypass_members = json.dumps(pairs)
    report = preflight.preflight(lambda: conn)
    assert len(report["bypassrls_data_role_members"]) == 20
    assert report["bypassrls_data_role_members_truncated"] is True
    sql = preflight.BYPASSRLS_MEMBERS_SQL
    prerequisite = preflight.PREREQUISITE_SQL["no_bypassrls_data_role_member"]
    prerequisite_from = prerequisite.split(" FROM ", 1)[1]
    assert prerequisite_from.endswith(")")
    subquery = "FROM (SELECT DISTINCT r.rolname AS rn, g.rolname AS dn FROM "
    assert subquery + prerequisite_from[:-1] + ") x" in sql
    for condition in ("pg_read_all_data", "pg_write_all_data", "r.rolbypassrls",
                      "NOT r.rolsuper", "r.rolname<>current_user"):
        assert condition in sql
    prerequisite = preflight.PREREQUISITE_SQL["no_bypassrls_data_role_member"]
    for condition in ("pg_read_all_data", "pg_write_all_data", "r.rolbypassrls",
                      "NOT r.rolsuper", "r.rolname<>current_user"):
        assert condition in prerequisite


def test_public_least_privilege_failures_make_preflight_not_ready():
    conn = Connection()
    conn.cursor_obj.public_bad = True
    report = preflight.preflight(lambda: conn)
    assert report["verdict"] == "NOT_READY"
    assert {"public_relation_privileges", "public_executable_definers",
            "public_schema_create", "public_database_create"} <= set(report["failing"])


def test_public_create_on_any_non_temp_schema_fails_preflight():
    conn = Connection()
    conn.cursor_obj.public_any_schema_bad = True
    report = preflight.preflight(lambda: conn)
    assert "public_any_schema_create" in report["failing"]


def test_public_database_connect_is_required():
    conn = Connection()
    conn.cursor_obj.public_connect_bad = True
    report = preflight.preflight(lambda: conn)
    assert "public_database_connect" in report["failing"]


def test_rehearsal_url_rules():
    assert preflight.refuse_url("postgresql:///x?host=/tmp") is None
    assert preflight.refuse_url("postgresql://localhost/x") is None
    assert preflight.refuse_url("postgresql://host.example/x")
    assert preflight.refuse_url("postgresql://x.supabase.co/db")


def test_attest_requires_wheelhouse_and_reports_attested(monkeypatch, capsys):
    class Isolation:
        installed_files_sha256 = "b" * 64

    monkeypatch.setattr(preflight, "enter_isolated_runtime", lambda wheelhouse: Isolation())
    monkeypatch.setattr(preflight, "attest_dispatch", lambda *args: {"dispatch_verified": True})
    monkeypatch.setattr(preflight, "attest_loaded_modules", lambda isolation: 1)
    monkeypatch.setattr(preflight, "load_driver", lambda: object())
    env = {"GITHUB_ACTIONS": "true"}
    assert preflight.main(["--mode=attest", "--expected-sha=" + "a" * 40,
                           "--wheelhouse=/tmp/wheels"], environ=env) == 0
    assert '"verdict": "ATTESTED"' in capsys.readouterr().out
    assert preflight.main(["--mode=attest", "--expected-sha=" + "a" * 40], environ=env) == 2
    assert '"error": "REFUSED"' in capsys.readouterr().out


def test_attest_refuses_invalid_dispatch(monkeypatch, capsys):
    def refuse(*args):
        raise ValueError("REFUSED")

    monkeypatch.setattr(preflight, "enter_isolated_runtime", lambda wheelhouse: object())
    monkeypatch.setattr(preflight, "attest_dispatch", refuse)
    assert preflight.main(["--mode=attest", "--expected-sha=" + "a" * 40,
                           "--wheelhouse=/tmp/wheels"], environ={}) == 2
    assert '"error": "REFUSED"' in capsys.readouterr().out


def _dispatch_env(workflow_path: str, sha: str = "a" * 40) -> dict[str, str]:
    repo = "tranbeny053-hub/v83-stock-cron"
    return {
        "GITHUB_ACTIONS": "true",
        "GITHUB_REPOSITORY": repo,
        "GITHUB_EVENT_NAME": "workflow_dispatch",
        "GITHUB_REF": "refs/heads/main", "GITHUB_SHA": sha,
        "GITHUB_WORKFLOW_REF": f"{repo}/{workflow_path}@refs/heads/main",
    }


def test_a_dispatch_of_the_renamed_workflow_passes_and_the_authored_path_refuses(monkeypatch):
    # After the enabling rename GitHub reports .github/workflows/<file>; a dispatch check pinned to
    # the authored ops/ path would refuse every dispatch and spend the one-shot (review R1-1).
    monkeypatch.setattr(preflight.platform, "python_implementation", lambda: "CPython")
    monkeypatch.setattr(preflight.platform, "python_version", lambda: "3.13.14")
    preflight.verify_dispatch(_dispatch_env(".github/workflows/ng4-pilot-preflight.yml"), "a" * 40)
    try:
        preflight.verify_dispatch(
            _dispatch_env("ops/ng4_pilot/workflows/ng4-pilot-preflight.yml"), "a" * 40
        )
    except ValueError:
        pass
    else:
        raise AssertionError("a dispatch from the authored ops/ path was accepted")


def test_rehearse_with_a_wheelhouse_loads_the_driver_from_it(monkeypatch):
    calls = []

    class Isolation:
        installed_files_sha256 = "a" * 64

    class Stop(Exception):
        pass

    def driver():
        calls.append("driver")
        def connect(*_args, **_kwargs):
            raise Stop()

        return type("D", (), {"connect": staticmethod(connect)})

    monkeypatch.setattr(
        preflight, "enter_isolated_runtime", lambda w: calls.append(("enter", w)) or Isolation()
    )
    monkeypatch.setattr(
        preflight, "attest_loaded_modules", lambda isolation: calls.append("attest") or 1
    )
    monkeypatch.setattr(preflight, "load_driver", driver)
    env = {"NG4_PILOT_PREFLIGHT_REHEARSAL_URL": "postgresql:///scratch?host=/tmp"}
    preflight.main(["--mode=rehearse", "--wheelhouse=/tmp/wheels"], environ=env)
    assert calls[:3] == [("enter", "/tmp/wheels"), "driver", "attest"]


def _main_with_fake(monkeypatch, capsys, members, fact=None):
    conn = Connection()
    conn.cursor_obj.bypass_members = members
    conn.cursor_obj.bypass_fact = fact
    monkeypatch.setattr(preflight, "load_driver",
                        lambda: type("D", (), {"connect": staticmethod(lambda *a, **k: conn)}))
    monkeypatch.setattr(preflight, "enter_isolated_runtime", lambda w: object())
    monkeypatch.setattr(preflight, "attest_loaded_modules", lambda isolation: 1)
    env = {"NG4_PILOT_PREFLIGHT_REHEARSAL_URL": "postgresql:///scratch?host=/tmp"}
    code = preflight.main(["--mode=rehearse", "--wheelhouse=/tmp/wheels"], environ=env)
    return code, json.loads(capsys.readouterr().out.strip().splitlines()[-1])


def test_malformed_or_inconsistent_members_fail_closed_as_errors_not_refusals(monkeypatch, capsys):
    # review R1-2/R1-6: an error class (exit 1), never REFUSED, and no names key in the output
    for members, fact, error in (
        ("not json", False, "JSONDecodeError"),
        (json.dumps("x_reader"), False, "RuntimeError"),
        (json.dumps([["x_reader"]]), False, "RuntimeError"),
        (json.dumps([["x_reader", "pg_read_all_data", "extra"]]), False, "RuntimeError"),
        (json.dumps([["x_reader", "pg_read_all_data"]]), True, "RuntimeError"),
        ("[]", False, "RuntimeError"),
    ):
        code, report = _main_with_fake(monkeypatch, capsys, members, fact)
        assert code == 1 and report["error"] == error, (members, fact, report)
        assert "bypassrls_data_role_members" not in report
        assert "x_reader" not in json.dumps(report)


def test_a_consistent_member_list_passes_through_main(monkeypatch, capsys):
    pair = [["x_reader", "pg_read_all_data"]]
    code, report = _main_with_fake(monkeypatch, capsys, json.dumps(pair))
    assert code == 0 and report["verdict"] == "NOT_READY"
    assert "no_bypassrls_data_role_member" in report["failing"]
    expected = [{"role": "x_reader", "data_role": "pg_read_all_data"}]
    assert report["bypassrls_data_role_members"] == expected


def test_token_like_role_names_are_replaced():
    for name in ("a" * 16, "role_0123456789abcdef", "x_" + "deadbeef" * 5):
        conn = Connection()
        conn.cursor_obj.bypass_members = json.dumps([[name, "pg_read_all_data"]])
        report = preflight.preflight(lambda conn=conn: conn)
        assert report["bypassrls_data_role_members"][0]["role"] == "<non-identifier>", name


def test_role_checks_are_schema_qualified_and_the_set_role_paths_are_counted():
    # review R1-1: an unqualified pg_has_role(oid, text, text) could be shadowed by a planted
    # public function of that exact signature (the CVE-2018-1058 class); review R1-2: SET ROLE
    # carries BYPASSRLS, so the roles that can SET ROLE to a named reader are counted.
    route_spec = importlib.util.spec_from_file_location(
        "apply_0019_for_qualification", ROOT / "scripts/apply_migration_0019.py"
    )
    route = importlib.util.module_from_spec(route_spec)
    route_spec.loader.exec_module(route)
    unqualified = re.compile(r"(?<!pg_catalog\.)\b(pg_has_role|pg_roles)\b")
    texts = [preflight.PREREQUISITE_SQL["no_bypassrls_data_role_member"],
             route.CHECKS["no_bypassrls_data_role_member"], preflight.BYPASSRLS_MEMBERS_SQL]
    for text in texts:
        assert not unqualified.search(text), text
    conn = Connection()
    report = preflight.preflight(lambda: conn)
    queries = "\n".join(sql for sql, _ in conn.cursor_obj.statements)
    assert "pg_catalog.pg_has_role(u.oid, n.oid, 'SET')" in queries
    assert "pg_catalog.pg_has_role(u.oid, n.oid, 'MEMBER WITH ADMIN OPTION')" in queries
    # A planted public.count(oid) would beat pg_catalog's count("any"): only count(*) may be bare.
    bare_count = re.compile(r"(?<!pg_catalog\.)\bcount\((?!\*)")
    for sql, _ in conn.cursor_obj.statements:
        assert not bare_count.search(sql), sql
    for fact in ("bypassrls_allowlisted_readers", "named_reader_set_role_paths"):
        assert type(report["facts"][fact]) is int
        assert fact not in report["failing"]

