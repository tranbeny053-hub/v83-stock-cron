"""B9: the migration-0015 pull-request rehearsal workflow's contract.

A scratch PostgreSQL on the runner only: pull requests only, a read-only token, no secret. It builds
two databases from migrations 0001-0014 with Supabase-like roles and default privileges, functions
included. The first takes the one-shot route (scripts/apply_migration_0015.py --mode=rehearse:
applied once, a second apply refused), then the probe calls the bundle function as each of
PostgREST's roles. The second takes the migration file itself twice and the same probe. SHA pins and
job timeouts are enforced for every workflow by test_workflow_action_runtime.py.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TEXT = (ROOT / ".github/workflows/migration-0015-rehearsal.yml").read_text(encoding="utf-8")
SCRATCH = "postgresql:///migration_0015_rehearsal?host=/var/run/postgresql"
PSQL = "psql -X -q -v ON_ERROR_STOP=1 -d"
FIXTURES = "scripts/migration_0015_rehearsal"
MIGRATION = "migrations/0015_prediction_bundle_rpc.sql"


def test_it_runs_on_pull_requests_only_with_a_read_only_token_and_no_secret() -> None:
    assert '"on":\n  pull_request:\n' in TEXT
    for forbidden in ("push:", "schedule", "workflow_dispatch", "secrets.", "SUPABASE",
                      "environment:"):
        assert forbidden not in TEXT, forbidden
    assert "permissions:\n  contents: read\n" in TEXT
    assert "\n  test:\n" in TEXT, "the job is named test, so the merge procedure waits for it"
    for path in ("scripts/apply_migration_0015.py", ".github/workflows/apply-migration-0015.yml",
                 "migrations/**", f"{FIXTURES}/**",
                 "src/crypto_probability_engine/persistence/**"):
        assert f"      - {path}\n" in TEXT, path


def test_the_function_defaults_are_production_s_before_any_migration() -> None:
    for database in ("migration_0015_rehearsal", "migration_0015_rebuild"):
        grants = (f'-v owner="$(id -un)" -d {database} -f - < '
                  f"{FIXTURES}/00_supabase_like_function_grants.sql")
        bundle = f"{PSQL} {database} -f - < \"$RUNNER_TEMP/migrations_0001_0014.sql\""
        assert 0 <= TEXT.find(grants) < TEXT.find(bundle), database


def test_the_route_then_the_probe_then_the_idempotent_rebuild_run_in_order() -> None:
    steps = [
        f"{PSQL} migration_0015_rehearsal -f - < \"$RUNNER_TEMP/migrations_0001_0014.sql\"",
        f'MIGRATION_0015_REHEARSAL_URL="{SCRATCH}" PYTHONPATH=src python '
        "scripts/apply_migration_0015.py --mode=rehearse "
        "--report=migration-0015-rehearsal-report.json",
        f"{PSQL} migration_0015_rehearsal -f - < {FIXTURES}/10_probe.sql",
        f"{PSQL} migration_0015_rebuild -f - < \"$RUNNER_TEMP/migrations_0001_0014.sql\"",
        f"{PSQL} migration_0015_rebuild -f - < {MIGRATION}\n"
        f"          {PSQL} migration_0015_rebuild -f - < {MIGRATION}",
        f"{PSQL} migration_0015_rebuild -f - < {FIXTURES}/10_probe.sql",
        'echo "MIGRATION_0015_REHEARSAL=PASS"',
    ]
    positions = [TEXT.find(step) for step in steps]
    assert all(position >= 0 for position in positions), positions
    assert positions == sorted(positions), "the steps run in this order"
    assert "set -euo pipefail" in TEXT and "ON_ERROR_STOP=1" in TEXT


def test_the_bundle_is_every_migration_before_0015() -> None:
    earlier = sorted(
        path.relative_to(ROOT).as_posix()
        for path in (ROOT / "migrations").glob("*.sql")
        if path.name < "0015"
    )
    assert f"cat {' '.join(earlier)} > \"$RUNNER_TEMP/migrations_0001_0014.sql\"" in TEXT
    assert len(earlier) == 14


def test_the_route_s_report_is_uploaded_always() -> None:
    upload = TEXT.split("      - name: Upload the rehearsal report\n", 1)[1]
    assert "        if: always()\n" in upload
    assert "          path: migration-0015-rehearsal-report.json\n" in upload
    assert "          if-no-files-found: warn\n" in upload
