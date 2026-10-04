"""Phase 3: the migration-0018 (D6) pull-request rehearsal workflow's contract.

A scratch PostgreSQL on the runner only: pull requests only, a read-only token, no secret.
- It builds one database from migrations 0001-0017, with Supabase-like roles and default privileges
  (functions included), PostgREST's authenticator, and an owner holding CREATEROLE without
  SUPERUSER, which creates 0016's roles.
- The database takes the one-shot route (scripts/apply_migration_0018.py --mode=rehearse: applied
  once, a second apply refused), then the independent probe.
- There is no second database: roles are cluster-wide, so it would see the roles 0016 created.
SHA pins and job timeouts are enforced for every workflow by test_workflow_action_runtime.py.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TEXT = (ROOT / ".github/workflows/migration-0018-rehearsal.yml").read_text(encoding="utf-8")
SCRATCH = "postgresql:///migration_0018_rehearsal?host=/var/run/postgresql"
PSQL = "psql -X -q -v ON_ERROR_STOP=1 -d"
FIXTURES = "scripts/migration_0018_rehearsal"
AUTHENTICATOR_FIXTURES = "scripts/migration_0016_rehearsal"


def test_it_runs_on_pull_requests_only_with_a_read_only_token_and_no_secret() -> None:
    assert '"on":\n  pull_request:\n' in TEXT
    for forbidden in (
        "push:",
        "schedule",
        "workflow_dispatch",
        "secrets.",
        "SUPABASE",
        "environment:",
    ):
        assert forbidden not in TEXT, forbidden
    assert "permissions:\n  contents: read\n" in TEXT
    assert "\n  test:\n" in TEXT, "the job is named test, so the merge procedure waits for it"
    for path in (
        "scripts/apply_migration_0018.py",
        ".github/workflows/apply-migration-0018.yml",
        "migrations/**",
        f"{FIXTURES}/**",
        f"{AUTHENTICATOR_FIXTURES}/**",
        "src/crypto_probability_engine/persistence/**",
        "scripts/migration_0017_rehearsal/**",
        "scripts/core_write_inventory.py",
    ):
        assert f"      - {path}\n" in TEXT, path


def test_the_roles_and_defaults_are_production_s_before_any_migration() -> None:
    authenticator = (
        f'-v owner="$(id -un)" -f - < {AUTHENTICATOR_FIXTURES}/00_supabase_like_authenticator.sql'
    )
    functions = (
        '-v owner="$(id -un)" -d migration_0018_rehearsal -f - < '
        "scripts/migration_0015_rehearsal/00_supabase_like_function_grants.sql"
    )
    bundle = f'{PSQL} migration_0018_rehearsal -f - < "$RUNNER_TEMP/migrations_0001_0017.sql"'
    assert 0 <= TEXT.find(authenticator) < TEXT.find(functions) < TEXT.find(bundle)
    assert TEXT.count("createdb") == 1, "one scratch database: roles are cluster-wide"
    assert "SUPERUSER" not in TEXT.split('"on":', 1)[1]


def test_the_route_then_the_probe_run_in_order() -> None:
    steps = [
        f'{PSQL} migration_0018_rehearsal -f - < "$RUNNER_TEMP/migrations_0001_0017.sql"',
        f"{PSQL} migration_0018_rehearsal -f - < {FIXTURES}/00_g1_resolver_login.sql",
        f'MIGRATION_0018_REHEARSAL_URL="{SCRATCH}" PYTHONPATH=src python '
        "scripts/apply_migration_0018.py --mode=rehearse "
        "--report=migration-0018-rehearsal-report.json",
        f"{PSQL} migration_0018_rehearsal -f - < {FIXTURES}/10_probe.sql",
        'echo "MIGRATION_0018_REHEARSAL=PASS"',
    ]
    positions = [TEXT.find(step) for step in steps]
    assert all(position >= 0 for position in positions), positions
    assert positions == sorted(positions), "the steps run in this order"
    assert "set -euo pipefail" in TEXT and "ON_ERROR_STOP=1" in TEXT


def test_the_bundle_is_every_migration_before_0018() -> None:
    earlier = sorted(
        path.relative_to(ROOT).as_posix()
        for path in (ROOT / "migrations").glob("*.sql")
        if path.name < "0018"
    )
    assert f'cat {" ".join(earlier)} > "$RUNNER_TEMP/migrations_0001_0017.sql"' in TEXT
    assert len(earlier) == 17


def test_the_route_s_report_is_uploaded_always() -> None:
    upload = TEXT.split("      - name: Upload the rehearsal report\n", 1)[1]
    assert "        if: always()\n" in upload
    assert "          path: migration-0018-rehearsal-report.json\n" in upload
    assert "          if-no-files-found: warn\n" in upload
