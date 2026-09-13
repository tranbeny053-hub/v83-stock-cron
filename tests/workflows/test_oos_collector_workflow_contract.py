"""The post-T_close collector contract.

Self-contained on purpose: this lane shares no test helper with the section 5A evaluator
lane, so the two can land in either order.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COLLECTOR = ROOT / ".github/workflows/oos-pair-evidence.yml"


def trigger_keys(text: str) -> set[str]:
    keys: set[str] = set()
    inside = False
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if not line.startswith(" "):
            inside = stripped.rstrip(":").strip("\"'") == "on"
            continue
        if not inside:
            continue
        indent = len(line) - len(line.lstrip(" "))
        if indent == 2 and ":" in stripped:
            keys.add(stripped.split(":", 1)[0].strip("\"'"))
    return keys


_FIXTURE = """name: Example

"on":
  schedule:
    - cron: "7 * * * *"
  workflow_dispatch:
    inputs:
      dry_run:
        default: true
"""


def test_trigger_extraction_is_itself_correct() -> None:
    """Guard the guard: a helper returning nothing would make every test below vacuous."""

    assert trigger_keys(_FIXTURE) == {"schedule", "workflow_dispatch"}


def test_the_collector_no_longer_runs_on_a_schedule() -> None:
    """Rows collected after T_close fall outside the lattice and are discarded."""

    assert trigger_keys(COLLECTOR.read_text(encoding="utf-8")) == {"workflow_dispatch"}


def test_the_collector_remains_manually_runnable() -> None:
    """Stopping the cadence must not remove the ability to run it deliberately."""

    text = COLLECTOR.read_text(encoding="utf-8")
    assert "workflow_dispatch" in text
    assert "max_occasions" in text


def test_what_the_collector_writes_is_unchanged() -> None:
    """This lane changes WHEN it runs, never WHAT it computes or persists."""

    text = COLLECTOR.read_text(encoding="utf-8")
    assert "--confirm-write WRITE-OOS-PAIR-EVIDENCE" in text
    assert "UCPE_OOS_PAIR_EVIDENCE_ENABLED" in text
    assert "collect_oos_pair_evidence.py" in text
    assert "--max-occasions 6" in text


def test_restoring_collection_is_a_single_block_revert() -> None:
    """The inert scheduled step is retained so re-enabling is one edit, not a rebuild."""

    text = COLLECTOR.read_text(encoding="utf-8")
    assert "github.event_name == 'schedule'" in text
    assert "one-line revert" in text
