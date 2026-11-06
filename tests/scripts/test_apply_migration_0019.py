from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "apply_0019", ROOT / "scripts/apply_migration_0019.py"
)
apply = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(apply)


def test_pinned_digests_match_bytes():
    migration, capacity = apply.pinned_bytes()
    import hashlib

    assert hashlib.sha256(migration).hexdigest() == apply.MIGRATION_SHA256
    assert hashlib.sha256(capacity).hexdigest() == apply.CAPACITY_SHA256


def test_digest_change_refuses_before_connecting(monkeypatch):
    monkeypatch.setattr(apply, "MIGRATION_SHA256", "0" * 64)
    called = False
    try:
        apply.pinned_bytes()
    except apply.Refused:
        pass
    else:
        raise AssertionError("digest mutation accepted")
    assert called is False


def test_rehearsal_url_rules():
    assert apply.refuse_url("postgresql:///x?host=/tmp") is None
    assert apply.refuse_url("postgresql://localhost/x") is None
    assert apply.refuse_url("postgresql://user:secret@localhost/x")
    assert apply.refuse_url("postgresql://db.supabase.co/x")


class FakeCursor:
    def __init__(self):
        self.statements = []
        self.row = (True,)
        self.applied = False  # after the migration runs, the schema and the roles exist

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, sql, *args):
        self.statements.append(sql)
        if "CREATE SCHEMA ucpe_lattice" in sql:
            self.applied = True
        if self.applied and ("nspname='ucpe_lattice'" in sql and "NOT EXISTS" in sql
                             or "rolname IN ('ucpe_lattice_owner'" in sql and "NOT EXISTS" in sql):
            self.row = (False,)
        elif "jsonb_build_object" in sql:
            self.row = ("fingerprint",)
        elif "pg_advisory_xact_lock" in sql:
            self.row = (None,)
        elif "admin_option AND NOT" in sql:
            self.rows = [(True,), (True,)]
        elif "count(*)" in sql:
            self.row = (0,)
        else:
            self.row = (True,)

    def fetchone(self):
        return self.row

    def fetchall(self):
        return getattr(self, "rows", [])


class FakeConnection:
    def __init__(self):
        self.cur = FakeCursor()
        self.committed = False

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def cursor(self):
        return self.cur

    def commit(self):
        self.committed = True


def test_apply_runs_checks_then_exact_bytes_then_postchecks_then_commit():
    conn = FakeConnection()
    migration, capacity = apply.pinned_bytes()
    apply.apply_in_one_transaction(lambda: conn, migration, capacity)
    sql = conn.cur.statements
    lock_index = sql.index("SELECT pg_advisory_xact_lock(5000019)")
    migration_index = sql.index(migration.decode())
    capacity_index = sql.index(capacity.decode())
    assert lock_index < migration_index < capacity_index
    assert sql.index("SET LOCAL statement_timeout = '120s'") < lock_index
    assert (
        len(
            [statement for statement in sql[capacity_index + 1 :] if statement.startswith("SELECT")]
        )
        >= 8
    )
    assert conn.committed


def test_failed_precheck_never_sends_migration():
    conn = FakeConnection()
    original_execute = conn.cur.execute

    def fail_schema(sql, *args):
        original_execute(sql, *args)
        if "nspname='ucpe_lattice'" in sql:
            conn.cur.row = (False,)

    conn.cur.execute = fail_schema
    migration, capacity = apply.pinned_bytes()
    try:
        apply.apply_in_one_transaction(lambda: conn, migration, capacity)
    except apply.Refused:
        pass
    else:
        raise AssertionError("pre-check failure was accepted")
    assert migration.decode() not in conn.cur.statements


def test_createrole_self_grant_refuses_before_migration():
    conn = FakeConnection()
    original_execute = conn.cur.execute

    def nonempty_setting(sql, *args):
        original_execute(sql, *args)
        if "createrole_self_grant" in sql:
            conn.cur.row = (False,)

    conn.cur.execute = nonempty_setting
    migration, capacity = apply.pinned_bytes()
    try:
        apply.apply_in_one_transaction(lambda: conn, migration, capacity)
    except apply.Refused as exc:
        assert "createrole_self_grant_empty" in str(exc)
    else:
        raise AssertionError("non-empty self-grant setting was accepted")
    assert migration.decode() not in conn.cur.statements


def test_attest_requires_wheelhouse_and_reports_attested(monkeypatch, capsys):
    class Isolation:
        installed_files_sha256 = "a" * 64

    monkeypatch.setattr(apply, "enter_isolated_runtime", lambda wheelhouse: Isolation())
    monkeypatch.setattr(apply, "attest_dispatch", lambda *args: {"dispatch_verified": True})
    monkeypatch.setattr(apply, "attest_loaded_modules", lambda isolation: 1)
    monkeypatch.setattr(apply, "load_driver", lambda: object())
    env = {"GITHUB_ACTIONS": "true"}
    assert apply.main(["--mode=attest", "--expected-sha=" + "a" * 40,
                       "--wheelhouse=/tmp/wheels"], environ=env) == 0
    assert '"outcome": "ATTESTED"' in capsys.readouterr().out
    assert apply.main(["--mode=attest", "--expected-sha=" + "a" * 40], environ=env) == 2
    assert '"outcome": "REFUSED"' in capsys.readouterr().err


def test_attest_refuses_invalid_dispatch(monkeypatch, capsys):
    def refuse(*args):
        raise apply.Refused("dispatch")

    monkeypatch.setattr(apply, "enter_isolated_runtime", lambda wheelhouse: object())
    monkeypatch.setattr(apply, "attest_dispatch", refuse)
    assert apply.main(["--mode=attest", "--expected-sha=" + "a" * 40,
                       "--wheelhouse=/tmp/wheels"], environ={}) == 2
    assert '"outcome": "REFUSED"' in capsys.readouterr().err


def test_attestation_admits_the_evaluator_pin_files_as_0018_does() -> None:
    # The scripts import crypto_probability_engine.runtime_isolation, a pinned file: an attestation
    # over this script alone would refuse every real dispatch before it reached the database.
    root = Path(__file__).resolve().parents[2]
    for name in ("scripts/apply_migration_0019.py", "scripts/ng4_pilot_preflight.py"):
        source = (root / name).read_text(encoding="utf-8")
        assert "pinned=(*pinned_files(" in source, name
        assert "pinned=(SCRIPT,)" not in source, name


def test_a_changed_capacity_byte_refuses_before_connecting(monkeypatch):
    monkeypatch.setattr(apply, "CAPACITY_SHA256", "0" * 64)
    try:
        apply.pinned_bytes()
    except apply.Refused as exc:
        assert "capacity" in str(exc)
    else:
        raise AssertionError("a capacity digest mismatch was accepted")


def test_a_change_outside_the_lattice_schema_refuses_and_never_commits():
    conn = FakeConnection()
    fingerprints = iter(("before", "after"))
    original = conn.cur.execute

    def execute(sql, *args):
        original(sql, *args)
        if "jsonb_build_object" in sql:
            conn.cur.row = (next(fingerprints),)

    conn.cur.execute = execute
    migration, capacity = apply.pinned_bytes()
    try:
        apply.apply_in_one_transaction(lambda: conn, migration, capacity)
    except apply.Refused as exc:
        assert "catalog mismatch" in str(exc)
    else:
        raise AssertionError("a catalog change outside ucpe_lattice was accepted")
    assert conn.committed is False


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
    monkeypatch.setattr(apply.platform, "python_implementation", lambda: "CPython")
    monkeypatch.setattr(apply.platform, "python_version", lambda: "3.13.14")
    apply.verify_dispatch(_dispatch_env(".github/workflows/apply-migration-0019.yml"), "a" * 40)
    try:
        apply.verify_dispatch(
            _dispatch_env("ops/ng4_pilot/workflows/apply-migration-0019.yml"), "a" * 40
        )
    except apply.Refused:
        pass
    else:
        raise AssertionError("a dispatch from the authored ops/ path was accepted")
