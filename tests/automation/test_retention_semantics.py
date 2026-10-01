"""Retention and idempotency semantics (docs/automation/RETENTION_AND_IDEMPOTENCY.md)."""

import re
from pathlib import Path

from crypto_probability_engine.automation import config as automation_config
from crypto_probability_engine.automation import ledger as automation_ledger

ROOT = Path(__file__).resolve().parents[2]
DOC = ROOT / "docs/automation/RETENTION_AND_IDEMPOTENCY.md"
TABLES = ("automation_radar_ledger", "automation_credential")
# The one file that names a DELETE on these tables: a scratch-only probe that requires each API role
# to be REFUSED it (it never runs against a real database).
DENIAL_PROBE = ROOT / "scripts/migration_0013_rehearsal/20_assert_api_roles_refused.sql"


def _sources():
    for base in ("src", "scripts", ".github", "migrations"):
        for path in (ROOT / base).rglob("*"):
            if path.is_file() and path.suffix in {".py", ".sql", ".yml", ".yaml", ".sh"}:
                yield path


def test_nothing_deletes_or_truncates_a_ledger_or_registry_row():
    offenders = []
    for path in _sources():
        if path == DENIAL_PROBE:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for table in TABLES:
            if re.search(
                rf"\b(DELETE\s+FROM|TRUNCATE)\s+(?:TABLE\s+)?(?:public\.)?{table}\b", text, re.I
            ):
                offenders.append((path.relative_to(ROOT).as_posix(), table))
    assert offenders == []


def test_the_denial_probe_only_expects_refusals():
    text = DENIAL_PROBE.read_text(encoding="utf-8")
    assert "WHEN insufficient_privilege THEN" in text
    assert "RAISE EXCEPTION 'the API role % was not refused: %'" in text


def test_the_stated_retention_is_ninety_days_and_the_doc_says_so():
    assert automation_config.LEDGER_RETENTION_DAYS == 90
    text = DOC.read_text(encoding="utf-8")
    assert "**Retention: at least 90 days**" in text
    assert "the route itself never deletes a row" in text
    assert "There is no recurring job" in text


def test_the_idempotency_key_is_per_credential_in_the_ledger_and_the_migration():
    migration = (ROOT / "migrations/0013_automation_radar_ledger.sql").read_text(encoding="utf-8")
    assert "PRIMARY KEY (credential_id, client_request_id)" in migration
    key = "credential_id = %(credential_id)s AND client_request_id = %(client_request_id)s::uuid"
    assert f"WHERE {key}" in automation_ledger._SELECT_SQL


def test_the_in_memory_ledger_keeps_the_quota_windows_but_is_documented_as_short_lived():
    assert automation_ledger.WINDOW_DAY.total_seconds() == 86_400
    assert automation_ledger.ABANDON_GRACE.total_seconds() == 60
    text = DOC.read_text(encoding="utf-8")
    assert "about 26 hours, not 90 days" in text
