from __future__ import annotations

import importlib.util
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

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, sql, params=()):
        self.statements.append((sql, params))
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
        re.search(rf"\b{word}\b", statement, re.IGNORECASE)
        for statement in sql
        for word in forbidden
    )


def test_rehearsal_url_rules():
    assert preflight.refuse_url("postgresql:///x?host=/tmp") is None
    assert preflight.refuse_url("postgresql://localhost/x") is None
    assert preflight.refuse_url("postgresql://host.example/x")
    assert preflight.refuse_url("postgresql://x.supabase.co/db")
