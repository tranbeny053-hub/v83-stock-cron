from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
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

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, sql, params=()):
        self.statements.append((sql, params))
        if self.public_bad and ("has_table_privilege('public'" in sql or
                                "has_function_privilege('public'" in sql):
            self.result = (1,)
        elif self.public_bad and ("has_schema_privilege('public'" in sql or
                                  "has_database_privilege('public'" in sql and "'CREATE'" in sql):
            self.result = (True,)
        elif "has_schema_privilege('public'" in sql or "has_database_privilege('public'" in sql:
            self.result = (False,)
        else:
            self.result = (0 if "count(*)" in sql.lower() else True,)

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
    assert not any(
        re.match(rf"\s*{word}\b", statement, re.IGNORECASE)
        for statement in sql
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


def test_public_least_privilege_failures_make_preflight_not_ready():
    conn = Connection()
    conn.cursor_obj.public_bad = True
    report = preflight.preflight(lambda: conn)
    assert report["verdict"] == "NOT_READY"
    assert {"public_relation_privileges", "public_executable_definers",
            "public_schema_create", "public_database_create"} <= set(report["failing"])


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
