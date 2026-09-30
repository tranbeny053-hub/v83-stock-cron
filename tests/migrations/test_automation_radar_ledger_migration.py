"""Migration 0013 is the two isolated automation tables and nothing else; never execute SQL.

The route's expectations (scripts/apply_migration_0013.py) are cross-checked against the file's own
text here, and against the application's own patterns, so the migration, its apply route and the
code that reads it cannot drift apart.
"""

import hashlib
import re
from pathlib import Path

import pytest

from crypto_probability_engine.automation import config as automation_config
from crypto_probability_engine.automation import credentials
from scripts import apply_migration_0013 as route
from scripts.apply_migrations import select_migrations

ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "migrations/0013_automation_radar_ledger.sql"
TEXT = MIGRATION.read_text()
CODE = " ".join(re.sub(r"--[^\n]*", "", TEXT).split())
STATEMENTS = [statement.strip() for statement in CODE.split(";") if statement.strip()]
LEDGER, REGISTRY = "public.automation_radar_ledger", "public.automation_credential"
SQL_TYPES = {
    "TEXT": "text",
    "UUID": "uuid",
    "INTEGER": "integer",
    "JSONB": "jsonb",
    "TIMESTAMPTZ": "timestamp with time zone",
}
EARLIER_OBJECTS = (
    "prediction_resolution_status",
    "prs_",
    "target_version",
    "reference_venue",
    "core_computed_at_utc",
    "issued_at_utc",
)


def create_table_body(table: str) -> str:
    [statement] = [s for s in STATEMENTS if s.startswith(f"CREATE TABLE IF NOT EXISTS {table} (")]
    return statement[len(f"CREATE TABLE IF NOT EXISTS {table} (") : -1]


def top_level_items(body: str) -> list[str]:
    items, depth, current = [], 0, ""
    for char in body:
        depth += {"(": 1, ")": -1}.get(char, 0)
        if char == "," and depth == 0:
            items.append(current.strip())
            current = ""
        else:
            current += char
    return [*items, current.strip()]


def columns_of(table: str) -> list[tuple[str, str, bool, str | None]]:
    columns = []
    for item in top_level_items(create_table_body(table)):
        if item.startswith("CONSTRAINT "):
            continue
        name, sql_type, *rest = item.split()
        tail = " ".join(rest)
        default = re.search(r"DEFAULT (\S+)", tail)
        deparsed = default and default[1]
        if deparsed and deparsed.startswith("'"):  # the server deparses a literal with its cast
            deparsed = f"{deparsed}::{SQL_TYPES[sql_type]}"
        columns.append((name, SQL_TYPES[sql_type], "NOT NULL" in tail, deparsed))
    return columns


def constraints_of(table: str) -> dict[str, str]:
    found = {}
    for item in top_level_items(create_table_body(table)):
        match = re.fullmatch(r"CONSTRAINT (\w+) (.*)", item)
        if match:
            found[match[1]] = match[2]
    return found


def test_exact_migration_statement_inventory():
    assert len(STATEMENTS) == 9
    assert STATEMENTS[0].startswith(f"CREATE TABLE IF NOT EXISTS {LEDGER} (")
    assert STATEMENTS[5].startswith(f"CREATE TABLE IF NOT EXISTS {REGISTRY} (")
    assert STATEMENTS[1:5] == [
        f"CREATE INDEX IF NOT EXISTS arl_credential_received ON {LEDGER} "
        "(credential_id, received_at_utc)",
        f"ALTER TABLE {LEDGER} ENABLE ROW LEVEL SECURITY",
        f"REVOKE ALL ON TABLE {LEDGER} FROM PUBLIC",
        f"REVOKE ALL ON TABLE {LEDGER} FROM anon, authenticated, service_role",
    ]
    assert STATEMENTS[6:] == [
        f"ALTER TABLE {REGISTRY} ENABLE ROW LEVEL SECURITY",
        f"REVOKE ALL ON TABLE {REGISTRY} FROM PUBLIC",
        f"REVOKE ALL ON TABLE {REGISTRY} FROM anon, authenticated, service_role",
    ]


def test_no_other_table_or_destructive_or_access_granting_statement():
    assert not re.search(
        r"\b(GRANT|POLICY|REFERENCES|FOREIGN\s+KEY|DROP|DELETE|TRUNCATE|INSERT|UPDATE|FUNCTION"
        r"|TRIGGER|FORCE|SECURITY\s+DEFINER|OWNER|EXTENSION|SCHEMA|ROLE)\b",
        CODE,
        re.I,
    )
    assert set(re.findall(r"\bpublic\.\w+", CODE)) == {LEDGER, REGISTRY}
    for name in EARLIER_OBJECTS:
        assert name not in TEXT


def test_the_columns_are_the_route_s_expected_columns():
    for table, name in ((LEDGER, route.LEDGER), (REGISTRY, route.REGISTRY)):
        assert columns_of(table) == list(route.EXPECTED_COLUMNS[name])


def test_the_constraints_are_the_route_s_expected_constraints():
    for table, name in ((LEDGER, route.LEDGER), (REGISTRY, route.REGISTRY)):
        found = constraints_of(table)
        expected = route.EXPECTED_CONSTRAINTS[name]
        assert set(found) == set(expected)
        for constraint, (kind, _columns, literals, integers) in expected.items():
            definition = found[constraint]
            prefix = {"p": "PRIMARY KEY", "u": "UNIQUE", "c": "CHECK"}[kind]
            assert definition.startswith(prefix), constraint
            assert route.constraint_literals(definition) == literals, constraint
            assert route.constraint_integers(definition) == integers, constraint


def test_nullable_comparisons_are_guarded_so_no_check_passes_on_null():
    success = constraints_of(LEDGER)["arl_success_shape"]
    for column in ("http_status", "run_id", "analysis_hash", "evidence_hash"):
        assert f"{column} IS NOT NULL AND {column} " in success
    assert (
        "http_status IS NOT NULL AND http_status BETWEEN 400 AND 599"
        in (constraints_of(LEDGER)["arl_refusal_shape"])
    )
    assert (
        "revoked_at_utc IS NOT NULL AND revoked_at_utc >= created_at_utc"
        in (constraints_of(REGISTRY)["ac_revocation_shape"])
    )


def test_the_indexes_are_the_route_s_expected_indexes():
    assert route.EXPECTED_INDEXES[route.LEDGER] == {
        "arl_credential_received": (False, ("credential_id", "received_at_utc")),
        "automation_radar_ledger_pkey": (True, ("credential_id", "client_request_id")),
    }
    ledger_constraints = constraints_of(LEDGER)
    assert ledger_constraints["automation_radar_ledger_pkey"] == (
        "PRIMARY KEY (credential_id, client_request_id)"
    )
    registry_constraints = constraints_of(REGISTRY)
    assert registry_constraints["automation_credential_pkey"] == "PRIMARY KEY (credential_id)"
    assert registry_constraints["ac_secret_sha256_unique"] == "UNIQUE (secret_sha256)"
    relations = {
        *route.EXPECTED_INDEXES[route.LEDGER],
        *route.EXPECTED_INDEXES[route.REGISTRY],
        route.LEDGER,
        route.REGISTRY,
    }
    assert sorted(relations) == list(route.RELATION_NAMES)


def test_the_registry_mirrors_the_application_s_own_patterns():
    constraints = constraints_of(REGISTRY)
    assert route.constraint_literals(constraints["ac_credential_id_format"]) == {
        credentials.CREDENTIAL_ID_PATTERN.pattern
    }
    assert route.constraint_literals(constraints["ac_secret_sha256_format"]) == {
        credentials.SECRET_DIGEST_PATTERN.pattern
    }
    assert route.constraint_literals(constraints["ac_status_valid"]) == set(
        credentials.CREDENTIAL_STATUSES
    )
    ledger = constraints_of(LEDGER)
    assert route.constraint_literals(ledger["arl_credential_id_format"]) == {
        credentials.CREDENTIAL_ID_PATTERN.pattern
    }
    assert route.constraint_integers(ledger["arl_deadline_bounds"]) == {
        automation_config.DEADLINE_MS_MIN,
        automation_config.DEADLINE_MS_MAX,
    }


def test_the_route_pins_these_exact_bytes_and_the_header_names_the_route():
    assert hashlib.sha256(MIGRATION.read_bytes()).hexdigest() == route.MIGRATION_SHA256
    assert route.MIGRATION == "migrations/0013_automation_radar_ledger.sql"
    assert "AUTHORED, NOT APPLIED" in TEXT
    assert ".github/workflows/apply-migration-0013.yml" in TEXT
    assert "scripts/apply_migration_0013.py" in TEXT
    assert "must never be used for it" in TEXT


def test_default_bulk_path_includes_migration_so_only_the_route_may_apply_it():
    paths = sorted((ROOT / "migrations").glob("*.sql"))
    assert len(paths) > 1
    assert MIGRATION in select_migrations(paths, None)
    assert MIGRATION in select_migrations(paths, [])
    assert select_migrations(paths, [MIGRATION.name]) == [MIGRATION]


@pytest.mark.parametrize("workflow", sorted((ROOT / ".github/workflows").glob("*.yml")))
def test_no_workflow_runs_the_bulk_migration_script(workflow: Path):
    code = [line for line in workflow.read_text().splitlines() if not line.lstrip().startswith("#")]
    assert not any("apply_migrations.py" in line for line in code)
