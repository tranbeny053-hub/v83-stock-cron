"""Guard the guard: the workflow step reader must return what a real YAML parser returns.

Every expected value below was taken from PyYAML 6.0.2 parsing the same fixture (offline, once);
PyYAML is not a dependency, so the values are literal. Unsupported constructs must RAISE.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.workflows._workflow_steps import (
    GITHUB_SHELL_INVOCATIONS,
    WorkflowStepsError,
    install_stub,
    read_jobs,
    resolve_env,
    run_step,
    shell_argv,
    stub_calls,
)

FIXTURE = r"""name: Reader fixture

"on":
  workflow_dispatch:

jobs:
  first:
    runs-on: ubuntu-24.04
    env:
      JOB_LEVEL: "job ${{ github.ref }}"
    steps:
      - uses: actions/checkout@0123456789abcdef0123456789abcdef01234567  # v9
        with:
          persist-credentials: "false"
          path: |
            one
            two/
      - name: Literal clip
        shell: bash
        run: |
          set -euo pipefail
          echo "a: b"

          echo done
      - name: Literal strip
        run: |-
          first
            indented
      - name: Folded clip
        env:
          SINGLE: 'it''s'
          DOUBLE: "say \"hi\" \\ bye"
          EXPR: ${{ inputs.mode }}
        run: >
          python tool.py
          --flag one

          second paragraph
      - name: Folded strip
        run: >-
          python tool.py
          --x "$VALUE"
  second:
    runs-on: ubuntu-24.04
    steps:
      - run: echo plain # trailing comment
"""


def test_the_reader_agrees_with_a_real_yaml_parser() -> None:
    jobs = read_jobs(FIXTURE)
    assert sorted(jobs) == ["first", "second"]
    assert jobs["first"].env == {"JOB_LEVEL": "job ${{ github.ref }}"}
    first = jobs["first"].steps
    assert [step.fields for step in first] == [
        {
            "uses": "actions/checkout@0123456789abcdef0123456789abcdef01234567",
            "with": {"persist-credentials": "false", "path": "one\ntwo/\n"},
        },
        {
            "name": "Literal clip",
            "shell": "bash",
            "run": 'set -euo pipefail\necho "a: b"\n\necho done\n',
        },
        {"name": "Literal strip", "run": "first\n  indented"},
        {
            "name": "Folded clip",
            "env": {
                "SINGLE": "it's",
                "DOUBLE": 'say "hi" \\ bye',
                "EXPR": "${{ inputs.mode }}",
            },
            "run": "python tool.py --flag one\nsecond paragraph\n",
        },
        {"name": "Folded strip", "run": 'python tool.py --x "$VALUE"'},
    ]
    assert [step.fields for step in jobs["second"].steps] == [{"run": "echo plain"}]


@pytest.mark.parametrize(
    ("snippet", "fragment"),
    [
        ("defaults:\n  run:\n    shell: sh\n", "top-level 'defaults'"),
        ("env:\n  INHERITED: ${{ inputs.hostile }}\n", "top-level 'env'"),  # V809-F2
        ("      - run: echo x\n        continue-on-error: true\n", "continue-on-error"),
        ("      - run: echo x\n        working-directory: sub\n", "working-directory"),
        ("      - run: echo a: b\n", "not allowed in a plain scalar"),
        ("      - run: |+\n          x\n", "unsupported block scalar header"),
        ("      - run: echo x\n        env:\n          A: |\n            x\n", "block scalar"),
        ("      - run: echo x\n        frobnicate: yes\n", "unexpected key"),
        ("      - run: echo x\n        uses: a/b@c\n", "exactly one of run/uses"),
        ("      - run: >\n          a\n            b\n", "more-indented folded lines"),
        ("      - run: \"unterminated\n", "unterminated"),
        ("      - run: echo x\n\tshell: bash\n", "tab characters"),
    ],
)
def test_unsupported_constructs_raise_instead_of_being_skipped(snippet: str, fragment: str) -> None:
    head = "jobs:\n  only:\n    runs-on: ubuntu-24.04\n    steps:\n"
    workflow_level = snippet.startswith(("defaults", "env"))
    source = snippet if workflow_level else head + snippet
    if workflow_level:
        source += head + "      - run: echo x\n"
    with pytest.raises(WorkflowStepsError, match=fragment):
        read_jobs(source)


def test_the_shell_invocations_are_githubs_documented_ones() -> None:
    assert GITHUB_SHELL_INVOCATIONS[None] == ("bash", "-e")
    assert GITHUB_SHELL_INVOCATIONS["bash"] == ("bash", "--noprofile", "--norc", "-eo", "pipefail")
    step = read_jobs(FIXTURE)["first"].steps[1]
    assert shell_argv(step, Path("s.sh")) == [
        "bash", "--noprofile", "--norc", "-eo", "pipefail", "s.sh"
    ]
    unsupported = read_jobs(
        "jobs:\n  j:\n    runs-on: x\n    steps:\n      - run: echo\n        shell: pwsh\n"
    )["j"].steps[0]
    with pytest.raises(WorkflowStepsError, match="unsupported shell"):
        shell_argv(unsupported, Path("s.ps1"))


def test_env_resolution_accepts_only_what_the_test_declares() -> None:
    env = {"LITERAL": "x", "MODE": "${{ inputs.mode }}", "COMPLEX": "${{ a == b && 'c' || 'd' }}"}
    with pytest.raises(WorkflowStepsError, match="COMPLEX"):
        resolve_env(env, {"inputs.mode": "consume"})
    with pytest.raises(WorkflowStepsError, match="MODE"):
        resolve_env(env, {}, {"COMPLEX": "d"})
    resolved = resolve_env(env, {"inputs.mode": "consume"}, {"COMPLEX": "d"})
    assert resolved == {"LITERAL": "x", "MODE": "consume", "COMPLEX": "d"}
    with pytest.raises(WorkflowStepsError, match="does not set"):
        resolve_env(env, {"inputs.mode": "consume"}, {"COMPLEX": "d", "TYPO": "x"})


def test_running_a_step_shows_why_pipefail_matters(tmp_path: Path) -> None:
    """V808-R6 in miniature: the same pipe is green without pipefail and red with it."""

    source = (
        "jobs:\n  j:\n    runs-on: x\n    steps:\n"
        "      - run: python tool.py | tee out.txt\n"
        "      - run: python tool.py | tee out.txt\n        shell: bash\n"
    )
    unspecified, explicit = read_jobs(source)["j"].steps
    log = tmp_path / "calls.jsonl"
    install_stub(tmp_path / "bin", "python", log)
    env = {"STUB_EXIT": "3"}
    bin_dir = tmp_path / "bin"
    assert run_step(unspecified, env=env, workdir=tmp_path, bin_dir=bin_dir).returncode == 0
    assert run_step(explicit, env=env, workdir=tmp_path, bin_dir=bin_dir).returncode == 3
    assert [call["argv"] for call in stub_calls(log)] == [["tool.py"], ["tool.py"]]
