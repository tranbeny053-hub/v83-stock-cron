"""Read GitHub workflow jobs and steps exactly as GitHub hands them to a shell, and run them.

Tests that EXECUTE a workflow step need three things GitHub computes: the ``run`` text after YAML
block-scalar folding, the shell invocation GitHub uses for that step, and the environment the step
receives. The shared block-YAML reader cannot read GitHub expressions or block scalars, and a
workflow that is only ever checked as text is how V808-F1 (a dispatch input executed as shell) and
V808-R6 (a failure reported green) went unnoticed.

This is deliberately NOT a general YAML parser. It reads exactly the shapes this repository's
workflows use and raises :class:`WorkflowStepsError` on anything else, so a construct it does not
understand fails the test relying on it instead of being silently skipped.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class WorkflowStepsError(AssertionError):
    """The workflow uses a construct this reader does not support."""


# GitHub's documented invocations (workflow syntax, jobs.<job_id>.steps[*].shell). An unspecified
# shell on Linux is `bash -e {0}`: NO pipefail. Only an explicit `shell: bash` adds it.
GITHUB_SHELL_INVOCATIONS: dict[str | None, tuple[str, ...]] = {
    None: ("bash", "-e"),
    "bash": ("bash", "--noprofile", "--norc", "-eo", "pipefail"),
    "sh": ("sh", "-e"),
}

_STEP_KEYS = frozenset(
    {"name", "id", "if", "uses", "with", "run", "shell", "env", "timeout-minutes"}
)
_JOB_KEYS = frozenset({"name", "runs-on", "timeout-minutes", "env", "steps", "if", "permissions"})
# Keys that change how or whether a failure surfaces, or where a step runs. Unsupported on purpose.
_REFUSED_KEYS = frozenset(
    {"defaults", "continue-on-error", "working-directory", "strategy", "container", "services"}
)
_KEY = re.compile(r"^([A-Za-z_][A-Za-z0-9_-]*|\"[^\"]+\"|'[^']+'):(?: (.*))?$")
_SIMPLE_EXPRESSION = re.compile(r"^\$\{\{\s*([A-Za-z_][A-Za-z0-9_.-]*)\s*\}\}$")


@dataclass(frozen=True)
class Step:
    job: str
    index: int
    line: int
    fields: dict[str, Any]

    @property
    def name(self) -> str | None:
        return self.fields.get("name")

    @property
    def run(self) -> str | None:
        return self.fields.get("run")

    @property
    def shell(self) -> str | None:
        return self.fields.get("shell")

    @property
    def uses(self) -> str | None:
        return self.fields.get("uses")

    @property
    def env(self) -> dict[str, str]:
        return dict(self.fields.get("env", {}))

    @property
    def with_(self) -> dict[str, str]:
        return dict(self.fields.get("with", {}))


@dataclass(frozen=True)
class Job:
    name: str
    fields: dict[str, Any]
    steps: tuple[Step, ...] = field(default=())

    @property
    def env(self) -> dict[str, str]:
        return dict(self.fields.get("env", {}))


@dataclass(frozen=True)
class _Line:
    number: int
    indent: int
    text: str  # without indentation; "" for a blank line
    raw: str


def read_jobs(source: str) -> dict[str, Job]:
    """Every job and its steps. Raises on any unsupported construct."""

    lines = [
        _Line(number, len(raw) - len(raw.lstrip(" ")), raw.strip(), raw)
        for number, raw in enumerate(source.splitlines(), start=1)
    ]
    for line in lines:
        if "\t" in line.raw:
            raise WorkflowStepsError(f"line {line.number}: tab characters are unsupported")

    top = [line for line in lines if line.indent == 0 and _significant(line)]
    for line in top:
        key = _split_key(line)[0]
        if key in _REFUSED_KEYS:
            raise WorkflowStepsError(f"line {line.number}: top-level {key!r} is unsupported")
    jobs_line = next((line for line in top if _split_key(line)[0] == "jobs"), None)
    if jobs_line is None:
        raise WorkflowStepsError("the workflow has no jobs")
    start = lines.index(jobs_line) + 1
    end = next(
        (lines.index(line) for line in top if line.number > jobs_line.number), len(lines)
    )
    body = lines[start:end]

    jobs: dict[str, Job] = {}
    index = 0
    while index < len(body):
        line = body[index]
        if not _significant(line):
            index += 1
            continue
        if line.indent != 2:
            raise WorkflowStepsError(f"line {line.number}: expected a job id at indent 2")
        job_name, inline = _split_key(line)
        if inline is not None:
            raise WorkflowStepsError(f"line {line.number}: job {job_name!r} must be a mapping")
        index += 1
        job_fields, index = _mapping(body, index, 4, job_name, _JOB_KEYS, steps_allowed=True)
        steps = tuple(job_fields.pop("steps", ()))
        if job_name in jobs:
            raise WorkflowStepsError(f"line {line.number}: duplicate job {job_name!r}")
        jobs[job_name] = Job(job_name, job_fields, steps)
    if not jobs:
        raise WorkflowStepsError("the workflow has no jobs")
    return jobs


def read_steps(source: str, job: str) -> tuple[Step, ...]:
    jobs = read_jobs(source)
    if job not in jobs:
        raise WorkflowStepsError(f"no job {job!r}; found {sorted(jobs)}")
    return jobs[job].steps


def shell_argv(step: Step, script: Path) -> list[str]:
    if step.shell not in GITHUB_SHELL_INVOCATIONS:
        raise WorkflowStepsError(f"step {step.index}: unsupported shell {step.shell!r}")
    return [*GITHUB_SHELL_INVOCATIONS[step.shell], str(script)]


def resolve_env(
    mapping: Mapping[str, str],
    contexts: Mapping[str, str],
    overrides: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Evaluate an ``env`` mapping as GitHub would, for the expression forms a test declares.

    A value is a literal, or exactly ONE simple context reference such as ``${{ inputs.mode }}``,
    looked up in ``contexts``. Any other expression must be supplied by variable name in
    ``overrides``: a construct the test did not account for fails rather than being guessed.
    """

    overrides = overrides or {}
    resolved: dict[str, str] = {}
    for name, value in mapping.items():
        if name in overrides:
            resolved[name] = overrides[name]
            continue
        if "${{" not in value:
            resolved[name] = value
            continue
        match = _SIMPLE_EXPRESSION.match(value.strip())
        if match is None or match.group(1) not in contexts:
            raise WorkflowStepsError(f"env {name}: unsupported or unknown expression {value!r}")
        resolved[name] = contexts[match.group(1)]
    unused = set(overrides) - set(mapping)
    if unused:
        raise WorkflowStepsError(f"overrides name variables the env does not set: {sorted(unused)}")
    return resolved


def install_stub(bin_dir: Path, command: str, log: Path) -> Path:
    """An executable named ``command`` that records its argv and exits with ``$STUB_EXIT``.

    It prints ``$STUB_STDOUT`` first, so a step that inspects its command's output can be driven.
    """

    bin_dir.mkdir(parents=True, exist_ok=True)
    stub = bin_dir / command
    stub.write_text(
        f"#!{sys.executable}\n"
        "import json, os, sys\n"
        f"with open({str(log)!r}, 'a', encoding='utf-8') as handle:\n"
        "    handle.write(json.dumps({'argv': sys.argv[1:], "
        "'PYTHONPATH': os.environ.get('PYTHONPATH')}) + '\\n')\n"
        "sys.stdout.write(os.environ.get('STUB_STDOUT', ''))\n"
        "sys.exit(int(os.environ.get('STUB_EXIT', '0')))\n",
        encoding="utf-8",
    )
    stub.chmod(0o755)
    return stub


def stub_calls(log: Path) -> list[dict[str, Any]]:
    if not log.exists():
        return []
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines() if line]


def run_step(
    step: Step,
    *,
    env: Mapping[str, str],
    workdir: Path,
    bin_dir: Path,
    timeout: float = 60,
) -> subprocess.CompletedProcess[str]:
    """Execute a step as the runner does: its run text written to a file, run by its shell.

    ``bin_dir`` comes first on PATH, so stubs replace the commands the step calls.
    """

    if step.run is None:
        raise WorkflowStepsError(f"step {step.index} has no run text")
    script = workdir / f".step-{step.job}-{step.index}.sh"
    script.write_text(step.run, encoding="utf-8")
    process_env = {
        "PATH": f"{bin_dir}:/usr/bin:/bin",
        "HOME": str(workdir),
        "LANG": "C",
        **env,
    }
    return subprocess.run(
        shell_argv(step, script),
        cwd=workdir,
        env=process_env,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


# --------------------------------------------------------------------------- internals


def _significant(line: _Line) -> bool:
    return bool(line.text) and not line.text.startswith("#")


def _split_key(line: _Line) -> tuple[str, str | None]:
    match = _KEY.match(line.text)
    if match is None:
        raise WorkflowStepsError(f"line {line.number}: expected `key:` or `key: value`")
    key = match.group(1).strip("\"'")
    value = match.group(2)
    return key, (value if value is not None and value.strip() else None)


def _mapping(
    lines: list[_Line],
    index: int,
    indent: int,
    owner: str,
    allowed: frozenset[str],
    *,
    steps_allowed: bool = False,
    first: tuple[_Line, int] | None = None,
) -> tuple[dict[str, Any], int]:
    """Read the mapping at ``indent``. ``first`` is a key already on a sequence dash line."""

    fields: dict[str, Any] = {}
    pending = [first] if first else []
    while pending or index < len(lines):
        if pending:
            line, key_indent = pending.pop()
        else:
            line = lines[index]
            if not _significant(line):
                index += 1
                continue
            if line.indent < indent:
                break
            if line.indent > indent:
                raise WorkflowStepsError(f"line {line.number}: unexpected indentation")
            key_indent = indent
            index += 1
        key, inline = _split_key(line)
        if key in _REFUSED_KEYS:
            raise WorkflowStepsError(f"line {line.number}: {key!r} is unsupported ({owner})")
        if key not in allowed:
            raise WorkflowStepsError(f"line {line.number}: unexpected key {key!r} ({owner})")
        if key in fields:
            raise WorkflowStepsError(f"line {line.number}: duplicate key {key!r} ({owner})")
        if key == "steps":
            if not steps_allowed or inline is not None:
                raise WorkflowStepsError(f"line {line.number}: steps must be a sequence")
            fields[key], index = _steps(lines, index, key_indent + 2, owner)
        elif inline is not None and inline[0] in "|>":
            if key != "run":
                raise WorkflowStepsError(f"line {line.number}: block scalar only for run")
            fields[key], index = _block_scalar(lines, index, key_indent, inline, line.number)
        elif inline is not None:
            fields[key] = _scalar(inline, line.number)
        else:
            fields[key], index = _flat_mapping(
                lines, index, key_indent + 2, line.number, allow_block=key == "with"
            )
    return fields, index


def _steps(lines: list[_Line], index: int, indent: int, job: str) -> tuple[list[Step], int]:
    steps: list[Step] = []
    while index < len(lines):
        line = lines[index]
        if not _significant(line):
            index += 1
            continue
        if line.indent < indent:
            break
        if line.indent != indent or not line.text.startswith("- "):
            raise WorkflowStepsError(f"line {line.number}: expected a step item `- key: value`")
        dash_body = line.text[2:]
        item = _Line(line.number, indent + 2, dash_body, line.raw)
        index += 1
        owner = f"{job} step {len(steps)}"
        fields, index = _mapping(
            lines, index, indent + 2, owner, _STEP_KEYS, first=(item, indent + 2)
        )
        if ("run" in fields) == ("uses" in fields):
            raise WorkflowStepsError(f"line {line.number}: a step needs exactly one of run/uses")
        steps.append(Step(job, len(steps), line.number, fields))
    return steps, index


def _flat_mapping(
    lines: list[_Line], index: int, indent: int, owner_line: int, *, allow_block: bool = False
) -> tuple[dict[str, str], int]:
    values: dict[str, str] = {}
    while index < len(lines):
        line = lines[index]
        if not _significant(line):
            index += 1
            continue
        if line.indent < indent:
            break
        if line.indent != indent:
            raise WorkflowStepsError(f"line {line.number}: unexpected indentation")
        key, inline = _split_key(line)
        if inline is None:
            raise WorkflowStepsError(f"line {line.number}: nested values must be scalars")
        if key in values:
            raise WorkflowStepsError(f"line {line.number}: duplicate key {key!r}")
        index += 1
        if inline[0] in "|>":
            if not allow_block:
                raise WorkflowStepsError(f"line {line.number}: block scalar unsupported here")
            values[key], index = _block_scalar(lines, index, indent, inline, line.number)
        else:
            values[key] = _scalar(inline, line.number)
    if not values:
        raise WorkflowStepsError(f"line {owner_line}: empty mapping")
    return values, index


def _scalar(text: str, number: int) -> str:
    """A plain, single- or double-quoted scalar, with YAML's trailing-comment rule applied."""

    value = text.strip()
    if value[0] in "\"'":
        quote = value[0]
        position, result = 1, []
        while True:
            if position >= len(value):
                raise WorkflowStepsError(f"line {number}: unterminated quoted scalar")
            character = value[position]
            if quote == '"' and character == "\\":
                following = value[position + 1 : position + 2]
                if following not in {'"', "\\"}:
                    raise WorkflowStepsError(f"line {number}: unsupported escape \\{following}")
                result.append(following)
                position += 2
                continue
            if character == quote:
                if quote == "'" and value[position + 1 : position + 2] == "'":
                    result.append("'")
                    position += 2
                    continue
                break
            result.append(character)
            position += 1
        remainder = value[position + 1 :]
        if remainder.strip() and not re.match(r"^\s+#", remainder):
            raise WorkflowStepsError(f"line {number}: text after a quoted scalar")
        return "".join(result)
    if value[0] in "{[&*!%@`|>#":
        raise WorkflowStepsError(f"line {number}: unsupported scalar {value!r}")
    # YAML: in a plain scalar, `#` preceded by whitespace starts a comment.
    value = re.split(r"\s#", value, maxsplit=1)[0].rstrip()
    if ": " in value or value.endswith(":"):
        raise WorkflowStepsError(f"line {number}: `: ` is not allowed in a plain scalar")
    return value


def _block_scalar(
    lines: list[_Line], index: int, key_indent: int, header: str, number: int
) -> tuple[str, int]:
    header = header.strip()
    if header not in {"|", "|-", ">", ">-"}:
        raise WorkflowStepsError(f"line {number}: unsupported block scalar header {header!r}")
    content: list[_Line] = []
    content_indent: int | None = None
    while index < len(lines):
        line = lines[index]
        if line.text:
            if line.indent <= key_indent:
                break
            if content_indent is None:
                content_indent = line.indent
            elif line.indent < content_indent:
                raise WorkflowStepsError(f"line {line.number}: block scalar is under-indented")
        content.append(line)
        index += 1
    while content and not content[-1].text:
        content.pop()  # trailing blank lines are chomped away by `-` and by clip alike
    if content_indent is None:
        raise WorkflowStepsError(f"line {number}: empty block scalar")
    if not content[0].text:
        raise WorkflowStepsError(f"line {number}: leading blank lines in a block scalar")

    texts = [line.raw[content_indent:] if line.text else "" for line in content]
    if header.startswith("|"):
        body = "\n".join(texts)
    else:
        if any(text.startswith(" ") for text in texts):
            raise WorkflowStepsError(f"line {number}: more-indented folded lines are unsupported")
        paragraphs: list[str] = []
        buffer: list[str] = []
        blank_run = 0
        for text in texts:
            if text:
                if buffer and blank_run:
                    paragraphs.append(" ".join(buffer) + "\n" * blank_run)
                    buffer = []
                buffer.append(text)
                blank_run = 0
            else:
                blank_run += 1
        if buffer:
            paragraphs.append(" ".join(buffer))
        body = "".join(paragraphs)
    return (body if header.endswith("-") else body + "\n"), index
