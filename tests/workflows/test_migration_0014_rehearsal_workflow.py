"""DBI-1: the migration-0014 pull-request rehearsal workflow's contract.

A scratch PostgreSQL on the runner only: pull requests only, a read-only token, no secret. It builds
two databases from migrations 0001-0013 plus rows 0014's checks would refuse. The first takes the
one-shot route (scripts/apply_migration_0014.py --mode=rehearse: applied once, a second apply
refused), then the production-writer probe and the refusal probe. The second takes the migration
file itself twice and the same probe. SHA pins and job timeouts are enforced for every workflow by
test_workflow_action_runtime.py.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TEXT = (ROOT / ".github/workflows/migration-0014-rehearsal.yml").read_text(encoding="utf-8")
SCRATCH = "postgresql:///migration_0014_rehearsal?host=/var/run/postgresql"
PSQL = "psql -X -q -v ON_ERROR_STOP=1 -d"
FIXTURES = "scripts/migration_0014_rehearsal"


def test_it_runs_on_pull_requests_only_with_a_read_only_token_and_no_secret() -> None:
    assert '"on":\n  pull_request:\n' in TEXT
    for forbidden in ("push:", "schedule", "workflow_dispatch", "secrets.", "SUPABASE",
                      "environment:"):
        assert forbidden not in TEXT, forbidden
    assert "permissions:\n  contents: read\n" in TEXT
    assert "\n  test:\n" in TEXT, "the job is named test, so the merge procedure waits for it"
    for path in ("scripts/apply_migration_0014.py", ".github/workflows/apply-migration-0014.yml",
                 "migrations/**", f"{FIXTURES}/**"):
        assert f"      - {path}\n" in TEXT, path


def test_the_route_then_both_probes_then_the_idempotent_rebuild_run_in_order() -> None:
    steps = [
        f"{PSQL} migration_0014_rehearsal -f - < \"$RUNNER_TEMP/migrations_0001_0013.sql\"",
        f"{PSQL} migration_0014_rehearsal -f - < {FIXTURES}/00_seed_legacy_rows.sql",
        f'MIGRATION_0014_REHEARSAL_URL="{SCRATCH}" PYTHONPATH=src python '
        "scripts/apply_migration_0014.py --mode=rehearse "
        "--report=migration-0014-rehearsal-report.json",
        f'MIGRATION_0014_REHEARSAL_URL="{SCRATCH}" python {FIXTURES}/probe_writer_rows.py',
        f"{PSQL} migration_0014_rehearsal -f - < {FIXTURES}/10_probe.sql",
        f"{PSQL} migration_0014_rebuild -f - < \"$RUNNER_TEMP/migrations_0001_0013.sql\"",
        f"{PSQL} migration_0014_rebuild -f - < {FIXTURES}/00_seed_legacy_rows.sql",
        f"{PSQL} migration_0014_rebuild -f - < migrations/0014_core_evidence_invariants.sql\n"
        f"          {PSQL} migration_0014_rebuild -f - < "
        "migrations/0014_core_evidence_invariants.sql",
        f"{PSQL} migration_0014_rebuild -f - < {FIXTURES}/10_probe.sql",
        'echo "MIGRATION_0014_REHEARSAL=PASS"',
    ]
    positions = [TEXT.find(step) for step in steps]
    assert all(position >= 0 for position in positions), positions
    assert positions == sorted(positions), "the steps run in this order"
    assert "set -euo pipefail" in TEXT and "ON_ERROR_STOP=1" in TEXT


def test_the_bundle_is_every_migration_before_0014() -> None:
    earlier = sorted(
        path.relative_to(ROOT).as_posix()
        for path in (ROOT / "migrations").glob("*.sql")
        if path.name < "0014"
    )
    assert f"cat {' '.join(earlier)} > \"$RUNNER_TEMP/migrations_0001_0013.sql\"" in TEXT
    assert len(earlier) == 13


def test_the_route_s_report_is_uploaded_always() -> None:
    upload = TEXT.split("      - name: Upload the rehearsal report\n", 1)[1]
    assert "        if: always()\n" in upload
    assert "          path: migration-0014-rehearsal-report.json\n" in upload
    assert "          if-no-files-found: warn\n" in upload
