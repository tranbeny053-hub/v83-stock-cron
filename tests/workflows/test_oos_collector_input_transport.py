"""Dispatch inputs reach the OOS collector as inert arguments, never as shell source.

The section 5A evaluation workflow pasted a dispatch input into its script with `${{ }}` inside
`run:`, so a quote in the input became a command (V808-F1). The collector's dispatch step used the
same construction for `dry_run` and `max_occasions`. Their input types narrow what can be typed,
but a guarantee that rests on the dispatch form is not a guarantee. These tests EXECUTE the steps
exactly as GitHub runs them, against a stub collector, with hostile values.

The scheduled trigger stays removed and what the collector computes or writes is unchanged; the
existing collector contract tests continue to assert both.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.workflows._workflow_steps import (
    install_stub,
    read_jobs,
    resolve_env,
    run_step,
    stub_calls,
)

ROOT = Path(__file__).resolve().parents[2]
TEXT = (ROOT / ".github/workflows/oos-pair-evidence.yml").read_text(encoding="utf-8")
STEPS = read_jobs(TEXT)["collect"].steps
RUN_STEPS = [step for step in STEPS if step.run is not None]
DISPATCHED = next(
    step for step in STEPS if step.fields.get("if") == "github.event_name == 'workflow_dispatch'"
)
SCHEDULED = next(
    step for step in STEPS if step.fields.get("if") == "github.event_name == 'schedule'"
)

# GitHub evaluates these two expressions; each yields one of two literals, never input text.
DERIVED = {
    "UCPE_OOS_PAIR_EVIDENCE_ENABLED": "false",
    "COLLECTOR_CONFIRM_WRITE": "DRY-RUN",
}
HOSTILE = (
    "true; touch INJECTED_SEMICOLON",
    "$(touch INJECTED_SUBSHELL)",
    "`touch INJECTED_BACKTICK`",
    "6\ntouch INJECTED_NEWLINE",
    "'; touch INJECTED_QUOTE; #'",
    "--confirm-write=WRITE-OOS-PAIR-EVIDENCE",
    "1 2 *",
)


def _contexts(dry_run: str, max_occasions: str) -> dict[str, str]:
    return {
        "inputs.dry_run": dry_run,
        "inputs.max_occasions": max_occasions,
        "secrets.SUPABASE_DB_URL": "postgresql://stub-never-contacted.invalid/none",
    }


def test_no_expression_is_pasted_into_any_shell_source() -> None:
    assert RUN_STEPS, "the reader must find the run steps, or this check is vacuous"
    for step in RUN_STEPS:
        assert "${{" not in step.run, step.name


def test_the_dispatch_step_takes_every_input_from_the_environment() -> None:
    assert DISPATCHED.shell == "bash"
    assert DISPATCHED.env["COLLECTOR_DRY_RUN"] == "${{ inputs.dry_run }}"
    assert DISPATCHED.env["COLLECTOR_MAX_OCCASIONS"] == "${{ inputs.max_occasions }}"
    assert DISPATCHED.run == (
        "PYTHONPATH=src python scripts/collect_oos_pair_evidence.py"
        ' --dry-run="$COLLECTOR_DRY_RUN"'
        ' --max-occasions="$COLLECTOR_MAX_OCCASIONS"'
        ' --confirm-write="$COLLECTOR_CONFIRM_WRITE"'
    )


def test_the_write_confirmation_is_still_derived_only_from_dry_run() -> None:
    """Writing still needs dry_run == false; no input can supply the confirmation text."""

    expression = "${{ inputs.dry_run == false && 'WRITE-OOS-PAIR-EVIDENCE' || 'DRY-RUN' }}"
    assert DISPATCHED.env["COLLECTOR_CONFIRM_WRITE"] == expression
    assert DISPATCHED.env["UCPE_OOS_PAIR_EVIDENCE_ENABLED"] == (
        "${{ inputs.dry_run == false && 'true' || 'false' }}"
    )


def test_the_inert_scheduled_step_is_unchanged() -> None:
    assert SCHEDULED.run == (
        "PYTHONPATH=src python scripts/collect_oos_pair_evidence.py --dry-run false"
        " --max-occasions 6 --confirm-write WRITE-OOS-PAIR-EVIDENCE"
    )


@pytest.mark.parametrize("hostile", HOSTILE)
def test_hostile_inputs_reach_the_collector_as_inert_arguments(
    tmp_path: Path, hostile: str
) -> None:
    log = tmp_path / "calls.jsonl"
    install_stub(tmp_path / "bin", "python", log)
    env = resolve_env(DISPATCHED.env, _contexts(hostile, hostile), DERIVED)
    completed = run_step(DISPATCHED, env=env, workdir=tmp_path, bin_dir=tmp_path / "bin")
    assert completed.returncode == 0, completed.stderr
    assert [call["argv"] for call in stub_calls(log)] == [
        [
            "scripts/collect_oos_pair_evidence.py",
            f"--dry-run={hostile}",
            f"--max-occasions={hostile}",
            "--confirm-write=DRY-RUN",
        ]
    ]
    assert not list(tmp_path.glob("INJECTED*")), "an input executed as a command"


def test_ordinary_inputs_reach_the_collector_parser_unchanged(tmp_path: Path) -> None:
    from scripts.collect_oos_pair_evidence import parse_args

    log = tmp_path / "calls.jsonl"
    install_stub(tmp_path / "bin", "python", log)
    env = resolve_env(DISPATCHED.env, _contexts("true", "6"), DERIVED)
    run_step(DISPATCHED, env=env, workdir=tmp_path, bin_dir=tmp_path / "bin")
    (call,) = stub_calls(log)
    parsed = parse_args(call["argv"][1:])
    assert parsed.dry_run is True
    assert parsed.max_occasions == 6
    assert parsed.confirm_write == "DRY-RUN"


def test_a_failing_collector_fails_the_dispatch_step(tmp_path: Path) -> None:
    install_stub(tmp_path / "bin", "python", tmp_path / "calls.jsonl")
    env = {**resolve_env(DISPATCHED.env, _contexts("true", "6"), DERIVED), "STUB_EXIT": "4"}
    completed = run_step(DISPATCHED, env=env, workdir=tmp_path, bin_dir=tmp_path / "bin")
    assert completed.returncode == 4
