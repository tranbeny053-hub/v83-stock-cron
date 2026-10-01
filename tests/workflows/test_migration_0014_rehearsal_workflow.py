"""DBI-1: the migration-0014 rehearsal workflow's contract.

A scratch PostgreSQL on the runner only: pull requests only, a read-only token, no secret. It builds
the database from migrations 0001-0013, seeds rows 0014's checks would refuse, applies 0014 twice,
then runs the production-writer probe and the refusal probe. SHA pins and job timeouts are enforced
for every workflow by test_workflow_action_runtime.py.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TEXT = (ROOT / ".github/workflows/migration-0014-rehearsal.yml").read_text(encoding="utf-8")
SCRATCH = "postgresql:///migration_0014_rehearsal?host=/var/run/postgresql"


def test_it_runs_on_pull_requests_only_with_a_read_only_token_and_no_secret() -> None:
    assert '"on":\n  pull_request:\n' in TEXT
    for forbidden in ("push:", "schedule", "workflow_dispatch", "secrets.", "SUPABASE",
                      "environment:"):
        assert forbidden not in TEXT, forbidden
    assert "permissions:\n  contents: read\n" in TEXT
    assert "\n  test:\n" in TEXT, "the job is named test, so the merge procedure waits for it"


def test_the_rehearsal_order_proves_not_valid_idempotence_and_both_probes() -> None:
    steps = [
        "for migration in migrations/00{01..13}_*.sql; do scratch -f \"$migration\"; done",
        "scratch -f scripts/migration_0014_rehearsal/00_seed_legacy_rows.sql",
        "scratch -f migrations/0014_core_evidence_invariants.sql\n"
        "          scratch -f migrations/0014_core_evidence_invariants.sql",
        f'MIGRATION_0014_REHEARSAL_URL="{SCRATCH}" python '
        "scripts/migration_0014_rehearsal/probe_writer_rows.py",
        "scratch -f scripts/migration_0014_rehearsal/10_probe.sql",
        'echo "MIGRATION_0014_REHEARSAL=PASS"',
    ]
    positions = [TEXT.find(step) for step in steps]
    assert all(position >= 0 for position in positions), positions
    assert positions == sorted(positions), "the steps run in this order"
    assert "set -euo pipefail" in TEXT and "ON_ERROR_STOP=1" in TEXT
