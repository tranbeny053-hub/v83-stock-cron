"""The evaluation workflow must never be able to consume the holdout unattended.

The shared block-YAML reader cannot parse folded scalars or GitHub expressions, and
already cannot parse the existing collector workflow, so these contracts are asserted
on the file text — the same approach ``tests/scripts/test_source_integrity_guard.py``
takes. The trigger extraction below is deliberately small and exact rather than a
general YAML parser.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVALUATION = ROOT / ".github/workflows/section-5a-evaluation.yml"
COLLECTOR = ROOT / ".github/workflows/oos-pair-evidence.yml"


def trigger_keys(text: str) -> set[str]:
    """Return the keys nested directly under the workflow's ``on:`` mapping."""

    lines = text.splitlines()
    keys: set[str] = set()
    inside = False
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if not line.startswith(" "):
            inside = stripped.rstrip(":") in {"on", '"on"', "'on'"}
            continue
        if not inside:
            continue
        indent = len(line) - len(line.lstrip(" "))
        if indent == 2 and stripped.endswith(":"):
            keys.add(stripped[:-1].strip("\"'"))
        elif indent == 2 and ":" in stripped:
            keys.add(stripped.split(":", 1)[0].strip("\"'"))
    return keys


def test_trigger_extraction_is_itself_correct() -> None:
    """Guard the guard: a helper that silently returned nothing would pass everything."""

    assert trigger_keys(COLLECTOR.read_text(encoding="utf-8")) == {
        "schedule",
        "workflow_dispatch",
    }


def test_evaluation_workflow_has_no_schedule_trigger() -> None:
    """A cron here could take the one look with nobody watching."""

    keys = trigger_keys(EVALUATION.read_text(encoding="utf-8"))
    assert keys == {"workflow_dispatch"}
    assert "schedule" not in keys


def test_evaluation_workflow_defaults_to_the_safe_mode() -> None:
    text = EVALUATION.read_text(encoding="utf-8")
    mode_block = text.split("mode:", 1)[1].split("confirm:", 1)[0]
    assert "default: readiness" in mode_block


def test_evaluation_workflow_verifies_the_pin_before_it_runs() -> None:
    text = EVALUATION.read_text(encoding="utf-8")
    assert text.index("assert_evaluator_pin") < text.index("evaluate_section_5a.py")


def test_evaluation_workflow_requires_the_confirmation_token_to_be_passed() -> None:
    text = EVALUATION.read_text(encoding="utf-8")
    assert "--confirm" in text
    assert "CONSUME-SECTION-5A-ONE-LOOK" in text


def test_this_lane_leaves_the_collector_schedule_alone() -> None:
    """Stopping the collector is an independent lane needing its own authorization."""

    assert "schedule" in trigger_keys(COLLECTOR.read_text(encoding="utf-8"))
