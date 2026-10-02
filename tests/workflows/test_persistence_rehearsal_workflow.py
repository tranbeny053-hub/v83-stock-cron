"""PERS-0: the persistence fault rehearsal workflow's contract.

A scratch PostgreSQL on the runner only: pull requests only, a read-only token, no secret. It
builds the database from every migration (production's applied state, 0014 included) and runs
the rehearsal.
SHA pins and job timeouts are enforced for every workflow by test_workflow_action_runtime.py.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TEXT = (ROOT / ".github/workflows/persistence-rehearsal.yml").read_text(encoding="utf-8")


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
    for path in (
        "scripts/persistence_rehearsal/**",
        "src/crypto_probability_engine/persistence/**",
        "src/crypto_probability_engine/api/analysis_service.py",
        "migrations/**",
        ".github/workflows/persistence-rehearsal.yml",
    ):
        assert f"      - {path}\n" in TEXT, path


def test_the_database_is_every_migration_production_has_applied() -> None:
    every = sorted(
        path.relative_to(ROOT).as_posix() for path in (ROOT / "migrations").glob("*.sql")
    )
    assert f'cat {" ".join(every)} > "$RUNNER_TEMP/migrations_0001_0014.sql"' in TEXT
    assert every[-1] == "migrations/0014_core_evidence_invariants.sql", "update the bundle name"


def test_the_rehearsal_targets_the_scratch_socket_and_its_report_is_uploaded_always() -> None:
    assert (
        'PERSISTENCE_REHEARSAL_URL="postgresql:///persistence_rehearsal?host=/var/run/postgresql" '
        "PYTHONPATH=src python scripts/persistence_rehearsal/fault_injection.py "
        "--report=persistence-fault-rehearsal-report.json"
    ) in TEXT
    assert "set -euo pipefail" in TEXT and "ON_ERROR_STOP=1" in TEXT
    upload = TEXT.split("      - name: Upload the rehearsal report\n", 1)[1]
    assert "        if: always()\n" in upload
    assert "          path: persistence-fault-rehearsal-report.json\n" in upload
