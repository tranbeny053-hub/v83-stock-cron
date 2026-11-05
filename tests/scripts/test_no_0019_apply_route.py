"""Migration 0019 is AUTHORED, NOT APPLIED.

No path can apply it without a later, separately authorized route.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github/workflows"
REHEARSAL_WORKFLOW = WORKFLOWS / "migration-0019-rehearsal.yml"


def test_the_file_sits_outside_every_migration_glob() -> None:
    assert (ROOT / "migrations/authored/0019_lattice_evidence.sql").is_file()
    assert not list((ROOT / "migrations").glob("0019*"))
    assert not any(
        "ucpe_lattice" in p.read_text(encoding="utf-8") for p in (ROOT / "migrations").glob("*.sql")
    )


def test_the_number_is_reserved_until_the_t4_move() -> None:
    numbers = [int(p.name[:4]) for p in (ROOT / "migrations").glob("[0-9][0-9][0-9][0-9]_*.sql")]
    assert max(numbers) < 19


def test_no_apply_script_or_workflow_exists() -> None:
    assert not list((ROOT / "scripts").glob("apply_migration_0019*"))
    for path in WORKFLOWS.glob("*.y*ml"):
        text = path.read_text(encoding="utf-8")
        if path == REHEARSAL_WORKFLOW:
            continue
        assert "0019" not in path.name and "0019_lattice" not in text and "ucpe_lattice" not in text


def test_the_rehearsal_workflow_is_scratch_only() -> None:
    raw = REHEARSAL_WORKFLOW.read_text(encoding="utf-8")
    text = "\n".join(line for line in raw.splitlines() if not line.lstrip().startswith("#"))
    text += "\n"
    triggers = text.split('"on":', 1)[1].split("permissions:", 1)[0]
    assert re.findall(r"^  (\w+):", triggers, re.MULTILINE) == ["pull_request"]
    assert "permissions:\n  contents: read\n" in text
    for forbidden in (
        "secrets.",
        "environment:",
        "SUPABASE",
        "DB_URL",
        "apply_migration",
        "workflow_dispatch",
    ):
        assert forbidden not in text
    runs = re.findall(r"run_scratch\.sh /usr/lib/postgresql/16/bin", text)
    assert len(runs) == 2


def test_no_script_outside_the_rehearsal_names_the_authored_file() -> None:
    allowed = {ROOT / "scripts/apply_migrations.py"}
    for path in (ROOT / "scripts").rglob("*"):
        if not path.is_file() or path.suffix not in {".py", ".sh", ".sql"}:
            continue
        if "migration_0019_rehearsal" in path.parts or path in allowed:
            continue
        assert "0019_lattice" not in path.read_text(encoding="utf-8", errors="replace")
