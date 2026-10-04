"""The A4 ledger audit rehearsal workflow's contract (ucpe.a4_ledger_audit.v1).

A scratch PostgreSQL on the runner only: pull requests only, a read-only token, no secret. It
builds the database from every migration production has applied, adds the probe role that can read
only the ledger, and runs the sealed audit's rehearsal.
SHA pins and job timeouts are enforced for every workflow by test_workflow_action_runtime.py.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TEXT = (ROOT / ".github/workflows/a4-ledger-audit-rehearsal.yml").read_text(encoding="utf-8")


def test_it_runs_on_pull_requests_only_with_a_read_only_token_and_no_secret() -> None:
    assert '"on":\n  pull_request:\n' in TEXT
    for forbidden in ("push:", "schedule", "workflow_dispatch", "secrets.", "SUPABASE",
                      "environment:", "A4_AUDIT_DATABASE_URL"):
        assert forbidden not in TEXT, forbidden
    assert "permissions:\n  contents: read\n" in TEXT
    for path in (
        "ops/a4_ledger_audit/**",
        "scripts/a4_ledger_audit_rehearsal/**",
        "migrations/0013_automation_radar_ledger.sql",
        ".github/workflows/a4-ledger-audit-rehearsal.yml",
    ):
        assert f"      - {path}\n" in TEXT, path


def test_the_database_is_every_migration_production_has_applied() -> None:
    registry = json.loads((ROOT / "ops/release/releases.json").read_text(encoding="utf-8"))
    unapplied = {
        migration["id"]
        for migration in registry["migrations_applied"]
        if "applied_run" in migration and migration["applied_run"] is None
    }
    every = sorted(
        path.relative_to(ROOT).as_posix()
        for path in (ROOT / "migrations").glob("*.sql")
        if path.name[:4] not in unapplied
    )
    assert f'cat {" ".join(every)} > "$RUNNER_TEMP/migrations_0001_0018.sql"' in TEXT
    assert every[-1] == "migrations/0018_narrow_service_role.sql", "update the bundle name"


def test_it_rehearses_only_the_local_scratch_database_with_the_probe_role() -> None:
    assert "sudo -u postgres createdb -O \"$(id -un)\" a4_rehearsal\n" in TEXT
    assert ("-d a4_rehearsal -f - < scripts/a4_ledger_audit_rehearsal/00_probe_role.sql\n"
            in TEXT)
    assert ('A4_REHEARSAL_URL="postgresql:///a4_rehearsal?host=/var/run/postgresql" python '
            "scripts/a4_ledger_audit_rehearsal/rehearse.py "
            "--report=a4-ledger-audit-rehearsal-report.json\n") in TEXT
    probe = (ROOT / "scripts/a4_ledger_audit_rehearsal/00_probe_role.sql").read_text(
        encoding="utf-8")
    grants = [line for line in probe.splitlines() if line.startswith("GRANT")]
    assert grants == [
        "GRANT USAGE ON SCHEMA public TO a4_probe;",
        "GRANT SELECT ON TABLE public.automation_radar_ledger TO a4_probe;",
        'GRANT a4_probe TO :"owner";',
    ]
