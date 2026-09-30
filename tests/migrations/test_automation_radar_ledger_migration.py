"""The authored migration is isolated and grants no API-role access; never execute SQL."""

import re
from pathlib import Path

from scripts.apply_migrations import select_migrations

ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "migrations/0013_automation_radar_ledger.sql"
CODE = " ".join(re.sub(r"--[^\n]*", "", MIGRATION.read_text()).split())
STATEMENTS = [statement.strip() for statement in CODE.split(";") if statement.strip()]


def test_exact_migration_statement_inventory():
    assert len(STATEMENTS) == 5
    assert STATEMENTS[0].startswith("CREATE TABLE IF NOT EXISTS public.automation_radar_ledger (")
    assert STATEMENTS[0].endswith(")")
    assert STATEMENTS[1:] == [
        "CREATE INDEX IF NOT EXISTS arl_credential_received "
        "ON public.automation_radar_ledger (credential_id, received_at_utc)",
        "ALTER TABLE public.automation_radar_ledger ENABLE ROW LEVEL SECURITY",
        "REVOKE ALL ON TABLE public.automation_radar_ledger FROM PUBLIC",
        "REVOKE ALL ON TABLE public.automation_radar_ledger FROM anon, authenticated, service_role",
    ]


def test_no_other_table_or_destructive_or_access_granting_statement():
    assert not re.search(
        r"\b(GRANT|POLICY|REFERENCES|FOREIGN\s+KEY|DROP|DELETE|TRUNCATE)\b", CODE, re.I
    )
    tables = re.findall(r"(?:CREATE TABLE IF NOT EXISTS|ALTER TABLE|ON TABLE|ON)\s+([\w.]+)", CODE)
    assert tables == ["public.automation_radar_ledger"] * 5
    assert set(re.findall(r"\bpublic\.\w+", CODE)) == {"public.automation_radar_ledger"}


def test_default_bulk_path_includes_migration_and_only_selects_exactly_it():
    paths = sorted((ROOT / "migrations").glob("*.sql"))
    assert len(paths) > 1
    assert MIGRATION in select_migrations(paths, None)
    assert MIGRATION in select_migrations(paths, [])
    assert select_migrations(paths, [MIGRATION.name]) == [MIGRATION]
