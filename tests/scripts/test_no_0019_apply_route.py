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
    assert 19 not in numbers  # a later root migration may exist; the T4 route orders 0019's move


def test_0020_remains_authored_and_outside_root_migration_globs() -> None:
    assert (ROOT / "migrations/authored/0020_lattice_space_login.sql").is_file()
    assert not list((ROOT / "migrations").glob("0020*"))
    numbers = [int(p.name[:4]) for p in (ROOT / "migrations").glob("[0-9][0-9][0-9][0-9]_*.sql")]
    assert 20 not in numbers


def test_0020_apply_route_is_explicitly_narrow_and_general_route_refuses() -> None:
    allowed = {
        ROOT / "scripts/apply_migration_0019.py",
        ROOT / "scripts/apply_migrations.py",
        ROOT / "scripts/migration_0019_rehearsal",
    }
    mentions = []
    for path in (ROOT / "scripts").rglob("*"):
        if not path.is_file() or path.suffix not in {".py", ".sh", ".sql"}:
            continue
        if "0020_lattice" in path.read_text(encoding="utf-8", errors="replace"):
            mentions.append(path)
    assert all(any(path == item or item in path.parents for item in allowed) for path in mentions)
    general = (ROOT / "scripts/apply_migrations.py").read_text(encoding="utf-8")
    assert '"0020_lattice_space_login.sql"' in general


def test_no_enabled_apply_route_exists() -> None:
    # Since the NG4 pilot build (owner NG4-PILOT INPUTS, 2026-11-06) the one-shot apply route is
    # AUTHORED BUT DISABLED: the authored file waits outside .github/workflows, which GitHub never
    # registers; its script names the .github path the rename creates. Enabling renames the file
    # unchanged and flips its dormancy tests (a T3); dispatching it is the T4.
    scripts = sorted(p.name for p in (ROOT / "scripts").glob("apply_migration_0019*"))
    assert scripts == ["apply_migration_0019.py"]
    source = (ROOT / "scripts/apply_migration_0019.py").read_text(encoding="utf-8")
    # The constant names the path GitHub reports after the enabling rename; dormancy is that no
    # file exists there yet, while the authored file waits outside .github/workflows.
    assert 'WORKFLOW = ".github/workflows/apply-migration-0019.yml"' in source
    assert not (WORKFLOWS / "apply-migration-0019.yml").exists()
    assert not (WORKFLOWS / "ng4-pilot-preflight.yml").exists()
    assert (ROOT / "ops/ng4_pilot/workflows/apply-migration-0019.yml").is_file()
    assert (ROOT / "ops/ng4_pilot/workflows/ng4-pilot-preflight.yml").is_file()
    assert not list(WORKFLOWS.rglob("*0019*apply*")) and not list(WORKFLOWS.rglob("apply*0019*"))
    for path in WORKFLOWS.rglob("*.y*ml"):
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
    # The one path filter that names the authored, disabled route (NG4 pilot, 2026-11-06).
    route_path = "      - scripts/apply_migration_0019.py\n"
    assert text.count(route_path) == 1
    text = text.replace(route_path, "")
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
    assert len(runs) == 3  # commit-ts off, on, and the NG4 pilot route


def test_no_script_outside_the_rehearsal_names_the_authored_file() -> None:
    # The NG4 pilot's authored, disabled apply route (owner NG4-PILOT INPUTS, 2026-11-06) names it
    # by design.
    allowed = {
        ROOT / "scripts/apply_migrations.py",
        ROOT / "scripts/apply_migration_0019.py",
        ROOT / "scripts/migration_0019_capacity.sql",
    }
    for path in (ROOT / "scripts").rglob("*"):
        if not path.is_file() or path.suffix not in {".py", ".sh", ".sql"}:
            continue
        if "migration_0019_rehearsal" in path.parts or path in allowed:
            continue
        assert "0019_lattice" not in path.read_text(encoding="utf-8", errors="replace")
