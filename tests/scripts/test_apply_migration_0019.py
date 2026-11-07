from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "apply_0019", ROOT / "scripts/apply_migration_0019.py"
)
apply = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(apply)


def test_pinned_digests_match_bytes():
    migration, capacity, migration_0020 = apply.pinned_bytes()
    import hashlib

    assert hashlib.sha256(migration).hexdigest() == apply.MIGRATION_SHA256
    assert hashlib.sha256(capacity).hexdigest() == apply.CAPACITY_SHA256
    assert hashlib.sha256(migration_0020).hexdigest() == apply.MIGRATION_0020_SHA256


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
        self.stage = 0
        self.bad_post = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, sql, *args):
        self.statements.append(sql)
        if "CREATE SCHEMA ucpe_lattice" in sql:
            self.stage = 1
        elif "CREATE ROLE ucpe_lattice_space" in sql:
            self.stage = 2
        if "jsonb_build_object" in sql:
            self.row = ("fingerprint",)
        elif "pg_advisory_xact_lock" in sql:
            self.row = (None,)
        elif sql == apply.POST_MEMBERSHIP_SQL:
            self.rows = [("ucpe_lattice_writer", "ucpe_lattice_space", "applier",
                          False, True, False)]
            if self.bad_post == "membership":
                self.rows = []
        elif sql == apply.POST_MEMBER_OF_SQL:
            self.rows = [("ucpe_lattice_writer", "ucpe_lattice_space")]
            if self.bad_post == "member_of":
                self.rows.append(("ucpe_lattice_space", "ucpe_lattice_writer"))
        elif sql == apply.CURRENT_USER_SQL:
            self.row = ("applier",)
        elif sql == apply.POST_CREATOR_MEMBERSHIPS_SQL:
            # grantor is the bootstrap superuser (oid 10) for PostgreSQL 16's CREATEROLE auto-grant
            self.rows = [(name, True, True, False, False) for name in
                         ("ucpe_lattice_owner", "ucpe_lattice_space", "ucpe_lattice_writer")]
            if self.bad_post == "creator":
                self.rows.pop()
        elif sql == apply.POST_SPACE_ATTRIBUTES_SQL:
            self.row = (
                (False, False, False, False, False, False, False, 3, None)
                if self.bad_post != "attributes"
                else (True, False, False, False, False, False, False, 3, None)
            )
        elif sql == apply.POST_SPACE_SETTINGS_SQL:
            self.rows = [(0, ["statement_timeout=5s", "lock_timeout=2s",
                              "idle_in_transaction_session_timeout=30s"])]
            if self.bad_post == "settings":
                self.rows[0][1].pop()
        elif sql == apply.POST_RELATION_PRIVILEGES_SQL:
            self.row = (1 if self.bad_post == "relation" else 0,)
        elif sql == apply.POST_DEFINER_PRIVILEGES_SQL:
            self.row = (1 if self.bad_post == "definer" else 0,)
        elif sql == apply.POST_CREATE_PRIVILEGES_SQL:
            self.row = (self.bad_post == "create",)
        elif sql == apply.POST_SHDEPEND_SQL:
            self.row = (1 if self.bad_post == "shdepend" else 0,)
        elif "nspname='ucpe_lattice'" in sql and "NOT EXISTS" in sql:
            self.row = (self.stage == 0,)
        elif "rolname IN ('ucpe_lattice_owner'" in sql and "NOT EXISTS" in sql:
            self.row = (self.stage == 0,)
        elif "ucpe_lattice_space" in sql and "NOT EXISTS" in sql and "pg_roles" in sql:
            self.row = (self.stage < 2,)
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
    migration, capacity, migration_0020 = apply.pinned_bytes()
    apply.apply_in_one_transaction(lambda: conn, migration, capacity, migration_0020)
    sql = conn.cur.statements
    lock_index = sql.index("SELECT pg_advisory_xact_lock(5000019)")
    migration_index = sql.index(migration.decode())
    capacity_index = sql.index(capacity.decode())
    migration_0020_index = sql.index(migration_0020.decode())
    assert lock_index < migration_index < capacity_index
    assert capacity_index < migration_0020_index < sql.index(apply.POST_MEMBERSHIP_SQL)
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
    migration, capacity, migration_0020 = apply.pinned_bytes()
    try:
        apply.apply_in_one_transaction(lambda: conn, migration, capacity, migration_0020)
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
    migration, capacity, migration_0020 = apply.pinned_bytes()
    try:
        apply.apply_in_one_transaction(lambda: conn, migration, capacity, migration_0020)
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


def test_a_changed_0020_byte_refuses_before_connecting(monkeypatch):
    monkeypatch.setattr(apply, "MIGRATION_0020_SHA256", "0" * 64)
    called = False

    def connect(*args, **kwargs):
        nonlocal called
        called = True

    monkeypatch.setitem(__import__("sys").modules, "psycopg", SimpleNamespace(connect=connect))
    assert apply.main(["--mode=rehearse"], environ={
        "MIGRATION_0019_REHEARSAL_URL": "postgresql://localhost/test"
    }) == 2
    assert called is False


def test_lattice_space_absence_is_a_required_precheck():
    conn = FakeConnection()
    original_execute = conn.cur.execute

    def fail_space_absent(sql, *args):
        original_execute(sql, *args)
        if "rolname='ucpe_lattice_space'" in sql and "NOT EXISTS" in sql:
            conn.cur.row = (False,)

    conn.cur.execute = fail_space_absent
    migration, capacity, migration_0020 = apply.pinned_bytes()
    try:
        apply.apply_in_one_transaction(lambda: conn, migration, capacity, migration_0020)
    except apply.Refused as exc:
        assert "lattice_space_absent" in str(exc)
    else:
        raise AssertionError("existing lattice space role passed the precheck")
    assert migration.decode() not in conn.cur.statements
    assert migration_0020.decode() not in conn.cur.statements


def test_each_postcheck_group_refuses_and_never_commits():
    for bad_post in (
        "membership", "member_of", "creator", "attributes", "settings", "relation", "definer",
        "create", "shdepend",
    ):
        conn = FakeConnection()
        conn.cur.bad_post = bad_post
        migration, capacity, migration_0020 = apply.pinned_bytes()
        try:
            apply.apply_in_one_transaction(
                lambda conn=conn: conn, migration, capacity, migration_0020
            )
        except apply.Refused:
            pass
        else:
            raise AssertionError(f"bad post-check answer accepted: {bad_post}")
        assert not conn.committed, bad_post


def test_report_uses_v2_and_includes_0020_digest_without_connection(capsys):
    assert apply.main(["--mode=rehearse"], environ={}) == 2
    output = capsys.readouterr().err
    assert '"schema": "migration-0019-apply-report.v2"' in output
    assert f'"migration_0020_sha256": "{apply.MIGRATION_0020_SHA256}"' in output
    assert "postgresql" not in output.lower()
    assert "ucpe_lattice_space" not in output


def test_a_change_outside_the_lattice_schema_refuses_and_never_commits():
    conn = FakeConnection()
    fingerprints = iter(("before", "after"))
    original = conn.cur.execute

    def execute(sql, *args):
        original(sql, *args)
        if "jsonb_build_object" in sql:
            conn.cur.row = (next(fingerprints),)

    conn.cur.execute = execute
    migration, capacity, migration_0020 = apply.pinned_bytes()
    try:
        apply.apply_in_one_transaction(lambda: conn, migration, capacity, migration_0020)
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


def test_rehearse_with_a_wheelhouse_loads_the_driver_from_it(monkeypatch):
    # The dispatch workflow rehearses under python -I -S -B: only the wheelhouse can provide the
    # driver (W2 spec review R1-1; sweep survivor W13's sibling).
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
        apply, "enter_isolated_runtime", lambda w: calls.append(("enter", w)) or Isolation()
    )
    monkeypatch.setattr(
        apply, "attest_loaded_modules", lambda isolation: calls.append("attest") or 1
    )
    monkeypatch.setattr(apply, "load_driver", driver)
    env = {"MIGRATION_0019_REHEARSAL_URL": "postgresql:///scratch?host=/tmp"}
    apply.main(["--mode=rehearse", "--wheelhouse=/tmp/wheels"], environ=env)
    assert calls[:3] == [("enter", "/tmp/wheels"), "driver", "attest"]
