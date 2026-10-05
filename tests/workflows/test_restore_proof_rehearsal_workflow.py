"""The restore proof rehearsal's contract (owner ruling DP-D=2; plan §12.1 and §23 "Backup").

A scratch PostgreSQL 17.6 only: pull requests only, a read-only token, no secret. It builds the
governed server version from its pinned source (the A4C rehearsal's own build script) and runs
scripts/restore_proof/rehearse.py, whose every server is a private, socket-only scratch cluster.
SHA pins and job timeouts are enforced for every workflow by test_workflow_action_runtime.py.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TEXT = (ROOT / ".github/workflows/restore-proof-rehearsal.yml").read_text(encoding="utf-8")
FOLDER = ROOT / "scripts/restore_proof"
SCRATCH = (FOLDER / "scratch.py").read_text(encoding="utf-8")
PROVE = (FOLDER / "prove.py").read_text(encoding="utf-8")
REHEARSAL = (FOLDER / "rehearse.py").read_text(encoding="utf-8")


def test_it_runs_on_pull_requests_only_with_a_read_only_token_and_no_secret() -> None:
    assert '"on":\n  pull_request:\n' in TEXT
    for forbidden in (
        "push:",
        "schedule",
        "workflow_dispatch",
        "secrets.",
        "SUPABASE",
        "environment:",
        "DB_URL",
    ):
        assert forbidden not in TEXT, forbidden
    assert "permissions:\n  contents: read\n" in TEXT
    for path in (
        "scripts/restore_proof/**",
        "docs/runbooks/RESTORE_PROOF_EXPORT.md",
        "scripts/a4_card04_companion_rehearsal/build_postgres.sh",
        "scripts/migration_0013_rehearsal/**",
        "scripts/migration_0015_rehearsal/**",
        "scripts/migration_0016_rehearsal/**",
        "migrations/**",
        ".github/workflows/restore-proof-rehearsal.yml",
    ):
        assert f"      - {path}\n" in TEXT, path
    assert (
        'run: bash scripts/a4_card04_companion_rehearsal/build_postgres.sh "$RUNNER_TEMP/pg17"\n'
    ) in TEXT
    assert (
        'run: python scripts/restore_proof/rehearse.py --pg-bin "$RUNNER_TEMP/pg17/bin" '
        '--work "$RUNNER_TEMP/restore-proof" --report restore-proof-rehearsal-report.json\n'
    ) in TEXT


def test_every_fixture_the_reference_reads_triggers_it() -> None:
    fixtures = set(re.findall(r'"(migration_\d{4}_rehearsal)/', SCRATCH))
    assert fixtures == {
        "migration_0013_rehearsal",
        "migration_0015_rehearsal",
        "migration_0016_rehearsal",
    }
    for fixture in fixtures:
        assert f"      - scripts/{fixture}/**\n" in TEXT, fixture


def test_the_reference_is_every_migration_production_has_applied() -> None:
    registry = json.loads((ROOT / "ops/release/releases.json").read_text(encoding="utf-8"))
    unapplied = [
        migration["id"]
        for migration in registry["migrations_applied"]
        if "applied_run" in migration and migration["applied_run"] is None
    ]
    assert unapplied == [], "an unapplied migration must be excluded from the reference"
    assert 'glob("[0-9][0-9][0-9][0-9]_*.sql")' in SCRATCH
    newest = sorted(path.name for path in (ROOT / "migrations").glob("*.sql"))[-1]
    assert newest == "0018_narrow_service_role.sql", "review the proof for the new migration"


def test_every_server_is_a_private_socket_only_scratch_cluster() -> None:
    assert "-c listen_addresses='' -c unix_socket_directories=" in SCRATCH
    assert '"--auth=trust"' in SCRATCH and "tempfile.mkdtemp(" in SCRATCH
    # The proof takes no database URL: it reaches only the clusters it starts itself.
    assert "--dbname" not in PROVE and "DATABASE_URL" not in PROVE
    # Socket URLs only: "postgresql:///db?host=<socket dir>", never a host name.
    assert re.search(r"postgresql://[^/]", SCRATCH + PROVE + REHEARSAL) is None
    assert 'f"postgresql:///{database}?host={self.socket}' in SCRATCH
    assert "shutil.rmtree(cluster.data" in SCRATCH
