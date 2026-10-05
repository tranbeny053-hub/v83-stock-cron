"""The A4 Card-04 companion rehearsal's contract (ucpe.a4_card04_companion.v1).

A scratch PostgreSQL 17.6 only: pull requests only, a read-only token, no secret. It builds the
governed server version from its pinned source, starts a socket-only cluster from every migration
production has applied, adds three readers of exactly the companion's eleven columns, and runs the
sealed companion's rehearsal. A local run uses the same two scripts.
SHA pins and job timeouts are enforced for every workflow by test_workflow_action_runtime.py.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TEXT = (ROOT / ".github/workflows/a4-card04-companion-rehearsal.yml").read_text(encoding="utf-8")
FOLDER = ROOT / "scripts/a4_card04_companion_rehearsal"
BUILD = (FOLDER / "build_postgres.sh").read_text(encoding="utf-8")
SCRATCH = (FOLDER / "run_scratch.sh").read_text(encoding="utf-8")
PROBES = (FOLDER / "00_probe_roles.sql").read_text(encoding="utf-8")
REHEARSAL = (FOLDER / "rehearse.py").read_text(encoding="utf-8")
COLUMNS = (
    "GRANT SELECT (credential_id, client_request_id, evidence_origin, state, outcome_code, "
    "http_status, run_id, analysis_hash, deadline_ms, received_at_utc) ON TABLE "
    "public.automation_radar_ledger TO {role};"
)


def test_it_runs_on_pull_requests_only_with_a_read_only_token_and_no_secret() -> None:
    assert '"on":\n  pull_request:\n' in TEXT
    for forbidden in (
        "push:",
        "schedule",
        "workflow_dispatch",
        "secrets.",
        "SUPABASE",
        "environment:",
        "A4_COMPANION_DATABASE_URL",
    ):
        assert forbidden not in TEXT, forbidden
    assert "permissions:\n  contents: read\n" in TEXT
    for path in (
        "ops/a4_card04_companion/**",
        "scripts/a4_card04_companion_rehearsal/**",
        "scripts/migration_0013_rehearsal/**",
        "scripts/migration_0015_rehearsal/**",
        "scripts/migration_0016_rehearsal/**",
        "docs/automation/examples/**",
        "migrations/**",
        ".github/workflows/a4-card04-companion-rehearsal.yml",
    ):
        assert f"      - {path}\n" in TEXT, path
    assert (
        'run: bash scripts/a4_card04_companion_rehearsal/build_postgres.sh "$RUNNER_TEMP/pg17"\n'
    ) in TEXT
    assert (
        "run: bash scripts/a4_card04_companion_rehearsal/run_scratch.sh "
        '"$RUNNER_TEMP/pg17/bin" "$RUNNER_TEMP/a4c" '
        "a4-card04-companion-rehearsal-report.json\n"
    ) in TEXT


def test_it_builds_the_governed_server_version_from_its_pinned_source() -> None:
    governed = re.search(
        r"production runs (\d+\.\d+)",
        (ROOT / "scripts/apply_migration_0012.py").read_text(encoding="utf-8"),
    )
    assert governed and governed[1] == "17.6"
    assert "\nVERSION=17.6\n" in BUILD
    assert re.search(r"\nSHA256=[0-9a-f]{64}\n", BUILD), "pin the verified tarball's sha256"
    assert (
        'URL="https://ftp.postgresql.org/pub/source/v$VERSION/postgresql-$VERSION.tar.bz2"' in BUILD
    )
    assert BUILD.count("curl ") == 1 and "--proto '=https'" in BUILD
    # The digest is checked before anything is extracted or built.
    assert BUILD.index("hashlib.sha256") < BUILD.index("tar -xjf") < BUILD.index("./configure")
    assert '--prefix="$PREFIX"' in BUILD and "sudo" not in BUILD


def test_the_database_is_every_migration_production_has_applied() -> None:
    registry = json.loads((ROOT / "ops/release/releases.json").read_text(encoding="utf-8"))
    unapplied = [
        migration["id"]
        for migration in registry["migrations_applied"]
        if "applied_run" in migration and migration["applied_run"] is None
    ]
    assert unapplied == [], "an unapplied migration must be excluded from run_scratch.sh"
    assert 'for migration in "$ROOT"/migrations/[0-9][0-9][0-9][0-9]_*.sql; do\n' in SCRATCH
    assert '  as_owner -d "$DB" -f "$migration"\n' in SCRATCH
    newest = sorted(path.name for path in (ROOT / "migrations").glob("*.sql"))[-1]
    assert newest == "0018_narrow_service_role.sql", "review the rehearsal for the new migration"


def test_it_rehearses_only_a_local_socket_scratch_database() -> None:
    assert "-c listen_addresses=''" in SCRATCH and "--auth=trust" in SCRATCH
    assert 'SOCKET="$(mktemp -d /tmp/a4c.XXXXXX)"' in SCRATCH
    assert "\nDB=a4_companion_rehearsal\n" in SCRATCH
    assert 'A4C_REHEARSAL_URL="postgresql:///$DB?host=$SOCKET"' in SCRATCH
    assert "refuse_non_scratch(url)" in REHEARSAL and 'DATABASE = "a4_companion_rehearsal"' in (
        REHEARSAL
    )
    assert "trap cleanup EXIT" in SCRATCH


def test_it_runs_the_cards_exact_command_and_keeps_the_package_folder_as_sealed() -> None:
    # The card's command line, python -I -B, in a child process, and every other start refused.
    assert 'start(PACKAGE / "a4_card04_companion.py", "-I", "-B")' in REHEARSAL
    assert 'for flags in (("-B",), ("-I",), ())' in REHEARSAL
    assert "before == after == sorted(runner.PACKAGE_FILES)" in REHEARSAL
    assert "not ran_under_isolation" in REHEARSAL and 'command_line["ok"]' in REHEARSAL
    # The rehearsal itself never writes bytecode into the package folder.
    assert "spec.loader.exec_module" not in REHEARSAL


def test_the_readers_see_exactly_the_companions_eleven_columns() -> None:
    normalized = " ".join(PROBES.split())
    manifest = json.loads(
        (ROOT / "ops/a4_card04_companion/MANIFEST.json").read_text(encoding="utf-8")
    )
    assert (
        sorted(re.findall(r"[a-z_]+", COLUMNS.split("(", 1)[1].split(")", 1)[0]))
        == (manifest["reads"]["public.automation_radar_ledger"])
    )
    for role in ("a4c_probe", "a4c_policy_reader", "a4c_hidden_reader"):
        assert COLUMNS.format(role=role) in normalized, role
        assert f"GRANT SELECT (run_id) ON TABLE public.predictions TO {role};" in normalized
        assert normalized.count(f" TO {role};") == 3, role  # USAGE and the two column grants
    assert "CREATE ROLE a4c_probe NOLOGIN NOINHERIT BYPASSRLS;" in normalized
    assert "CREATE ROLE a4c_policy_reader NOLOGIN NOINHERIT;" in normalized
    assert "CREATE ROLE a4c_hidden_reader NOLOGIN NOINHERIT;" in normalized
    assert normalized.count("CREATE POLICY") == 2
    assert normalized.count("TO a4c_policy_reader USING (true);") == 2


def test_every_file_the_rehearsal_reads_triggers_it() -> None:
    assert "docs/automation/examples/" in REHEARSAL
    assert "      - docs/automation/examples/**\n" in TEXT
    fixtures = set(re.findall(r"scripts/(migration_\d{4}_rehearsal)/", SCRATCH))
    assert fixtures == {
        "migration_0013_rehearsal",
        "migration_0015_rehearsal",
        "migration_0016_rehearsal",
    }
    for fixture in sorted(fixtures):
        assert f"      - scripts/{fixture}/**\n" in TEXT, fixture
