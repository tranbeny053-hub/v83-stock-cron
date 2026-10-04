"""Offline synchronization of the operational inventory with repository paths and triggers."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.workflows._block_yaml import read_block_yaml

ROOT = Path(__file__).resolve().parents[2]
INVENTORY = ROOT / "docs/TOOLING_INVENTORY.md"
CLASSES = {
    "ACTIVE_GATE", "ACTIVE_RELEASE", "ACTIVE_JOB", "ACTIVE_OWNER_TOOL",
    "ACTIVE_PIN", "REHEARSAL", "HISTORICAL_CONSUMED", "HISTORICAL_REFERENCE",
}
TOUCHES = {
    "local", "CI only", "scratch PG", "production DB", "HF Space",
    "Supabase API", "external read-only",
}


def inventory_rows() -> dict[str, list[str]]:
    rows = {}
    for number, line in enumerate(INVENTORY.read_text(encoding="utf-8").splitlines(), 1):
        if not re.match(r"^\s*\|\s*`[^`]+`\s*\|", line):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        assert len(cells) == 5, f"Inventory line {number}: expected five cells"
        path = cells[0][1:-1]
        assert path not in rows, f"Duplicate inventory path: {path}"
        rows[path] = cells[1:]
    return rows


def scoped_paths() -> set[str]:
    paths = {
        p.relative_to(ROOT).as_posix() + ("/" if p.is_dir() else "")
        for p in (ROOT / "scripts").iterdir()
        if p.name != "__pycache__"
    }
    for pattern in (".github/workflows/*.yml", "ops/**/*", "docs/runbooks/*.md"):
        paths.update(p.relative_to(ROOT).as_posix() for p in ROOT.glob(pattern) if p.is_file())
    return paths


def workflow_triggers(path: Path) -> list[str]:
    # Isolate only the top-level on block: jobs contain shell/literal YAML outside
    # the intentionally small reader's supported subset. Preserve child order.
    lines = path.read_text(encoding="utf-8").splitlines()
    starts = [i for i, line in enumerate(lines) if re.match(r"^(?:on|'on'|\"on\"):", line)]
    assert len(starts) == 1, f"{path.name}: expected exactly one on block"
    start = starts[0]
    end = start + 1
    while end < len(lines):
        line = lines[end]
        if line.strip() and not line.startswith((" ", "\t", "#")):
            break
        end += 1
    try:
        block = read_block_yaml("\n".join(lines[start:end]))["on"]
    except AssertionError as exc:
        raise AssertionError(f"{path.name}: cannot parse on block: {exc}") from exc
    assert isinstance(block, dict) and block, f"{path.name}: expected on mapping"
    return list(block)


def test_inventory_exact_scope() -> None:
    listed, expected = set(inventory_rows()), scoped_paths()
    assert listed == expected, (
        f"Missing inventory entries: {sorted(expected - listed)}; "
        f"Extra inventory entries: {sorted(listed - expected)}"
    )


def test_inventory_classes_and_evidence() -> None:
    state = (ROOT / "STATE.md").read_text(encoding="utf-8")
    for path, (classification, trigger, touches, evidence) in inventory_rows().items():
        assert classification in CLASSES, f"{path}: invalid or UNVERIFIED class {classification}"
        assert touches in TOUCHES, f"{path}: invalid Touches {touches}"
        assert trigger and evidence, f"{path}: missing trigger or evidence"
        if classification == "HISTORICAL_CONSUMED":
            quote = re.search(r"STATE\.md: '([^']+)'", evidence)
            assert quote, f"{path}: consumed action needs a STATE.md quote"
            assert quote[1] in state, f"{path}: consumed evidence is absent from STATE.md"


@pytest.mark.parametrize(
    "path", sorted((ROOT / ".github/workflows").glob("*.yml")), ids=lambda p: p.name,
)
def test_workflow_inventory(path: Path) -> None:
    relative = path.relative_to(ROOT).as_posix()
    rows = inventory_rows()
    assert relative in rows, f"Missing inventory entry: {relative}"
    classification, trigger, _, _ = rows[relative]
    actual = workflow_triggers(path)
    assert trigger == ", ".join(actual), f"{relative}: Trigger must be {actual}"
    if classification == "HISTORICAL_CONSUMED":
        assert actual == ["workflow_dispatch"], (
            f"{relative}: consumed workflow is not dispatch-only"
        )
    if classification == "ACTIVE_GATE":
        assert {"push", "pull_request"} & set(actual), f"{relative}: gate lacks push/pull_request"
