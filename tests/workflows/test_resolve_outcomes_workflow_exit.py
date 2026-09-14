"""The outcome resolver's workflow can never report a failed run as green.

The section 5A evaluation workflow once piped its evaluator into ``tee`` under GitHub's default
``bash -e``, without pipefail, so a refusal exited 0 (V808-R6). The resolver's workflow also pipes
into ``tee``, and was reported as sharing that defect. It does not: its script begins with
``set -euo pipefail``. These tests EXECUTE the step exactly as GitHub runs it, against a stub
resolver, so that property is proven rather than read, and a future edit cannot quietly lose it.
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
TEXT = (ROOT / ".github/workflows/resolve-outcomes.yml").read_text(encoding="utf-8")
JOB = read_jobs(TEXT)["resolve"]
RESOLVER = next(step for step in JOB.steps if step.name == "Run outcome resolver")
CONTEXTS = {"secrets.SUPABASE_DB_URL": "postgresql://stub-never-contacted.invalid/none"}


def _environment(**stub: str) -> dict[str, str]:
    job = resolve_env(JOB.env, CONTEXTS, {"RESOLVER_LIMIT": "50"})
    return {**job, **resolve_env(RESOLVER.env, CONTEXTS), **stub}


def test_the_resolver_step_pipes_its_output_under_pipefail() -> None:
    """The pipe is only safe because pipefail is on before it runs."""

    lines = RESOLVER.run.splitlines()
    pipe = next(index for index, line in enumerate(lines) if " | tee " in line)
    has_pipefail = RESOLVER.shell == "bash" or any(
        line.strip().startswith("set -") and "pipefail" in line for line in lines[:pipe]
    )
    assert has_pipefail


@pytest.mark.parametrize(
    ("exit_code", "stdout", "expected"),
    [
        ("3", "", 3),  # the resolver crashed: the pipeline, and the step, fail with it
        ("1", "due=4 resolved=3 skipped=0 failed=1\n", 1),  # it failed and said so
        ("0", "due=4 resolved=2 skipped=0 failed=2\n", 1),  # it exited 0 but reported failures
        ("0", "due=4 resolved=4 skipped=0 failed=0\n", 0),  # the only green run
    ],
)
def test_the_resolver_step_fails_whenever_the_resolver_fails(
    tmp_path: Path, exit_code: str, stdout: str, expected: int
) -> None:
    log = tmp_path / "calls.jsonl"
    install_stub(tmp_path / "bin", "python", log)
    completed = run_step(
        RESOLVER,
        env=_environment(STUB_EXIT=exit_code, STUB_STDOUT=stdout),
        workdir=tmp_path,
        bin_dir=tmp_path / "bin",
    )
    assert completed.returncode == expected, completed.stdout + completed.stderr
    assert [call["argv"] for call in stub_calls(log)] == [
        ["scripts/resolve_outcomes.py", "--limit", "50"]
    ]


def test_the_same_pipe_without_pipefail_would_have_been_green(tmp_path: Path) -> None:
    """The control: remove pipefail and a crashed resolver reports success. That is the defect."""

    from tests.workflows._workflow_steps import Step

    without = Step(
        RESOLVER.job,
        RESOLVER.index,
        RESOLVER.line,
        {**RESOLVER.fields, "run": RESOLVER.run.replace("set -euo pipefail", "set -eu", 1)},
    )
    install_stub(tmp_path / "bin", "python", tmp_path / "calls.jsonl")
    completed = run_step(
        without, env=_environment(STUB_EXIT="3"), workdir=tmp_path, bin_dir=tmp_path / "bin"
    )
    assert completed.returncode == 0
