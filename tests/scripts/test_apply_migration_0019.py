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

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, sql, *args):
        self.statements.append(sql)
        if "jsonb_build_object" in sql:
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
