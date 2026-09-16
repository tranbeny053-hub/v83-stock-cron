"""The migration-0008 workflow, read and EXECUTED the way GitHub runs it.

It applies migration 0008 once, with the database secret, so it carries every guard the section 5A
routes earned: no expression in shell source (V808-F1), `shell: bash` everywhere (V808-R6), the
exact runtime and the closed trust boundary (E3=A, G1=A, J1=B). Where it must be identical to the
evaluation workflow, this file compares the two to each other rather than to a copy of the text.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from crypto_probability_engine.oos.evaluation import provenance
from scripts import apply_migration_0008 as apply_0008
from tests.workflows._workflow_steps import (
    Step,
    install_stub,
    read_jobs,
    resolve_env,
    run_step,
    stub_calls,
)
from tests.workflows.test_section_5a_evaluation_workflow_contract import trigger_keys

ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / apply_0008.WORKFLOW
TEXT = PATH.read_text(encoding="utf-8")
JOB = read_jobs(TEXT)["apply"]
STEPS = JOB.steps
RUN_STEPS = [step for step in STEPS if step.run is not None]

EVALUATION_TEXT = (ROOT / provenance.EVALUATION_WORKFLOW).read_text(encoding="utf-8")
EVALUATION_STEPS = read_jobs(EVALUATION_TEXT)["evaluate"].steps

ENTRYPOINT = ("-I", "-S", "-B", apply_0008.SCRIPT)
RUNNER_TEMP = "/home/runner/work/_temp"
WHEELHOUSE = f"{RUNNER_TEMP}/section-5a-wheels"
REPORT = "migration-0008-apply-report.json"
BUNDLED_PIP = "/opt/hostedtoolcache/Python/3.13.14/x64/lib/python3.13/ensurepip/_bundled/pip.whl"

HOSTILE = (
    "'; touch INJECTED_SINGLE; #'",
    '"; touch INJECTED_DOUBLE; "',
    "$(touch INJECTED_SUBSHELL)",
    "`touch INJECTED_BACKTICK`",
    "x\ntouch INJECTED_NEWLINE",
    "--mode=apply",
    "a b\tc *",
    "\\",
)


def _step(steps: tuple[Step, ...], fragment: str) -> Step:
    matches = [step for step in steps if step.name and fragment in step.name]
    assert len(matches) == 1, (fragment, [step.name for step in steps])
    return matches[0]


INSTALL = _step(STEPS, "hash-locked")
ATTEST = _step(STEPS, "Attest")
TESTS = _step(STEPS, "tests under this exact runtime")
APPLY = _step(STEPS, "Apply migration 0008")
UPLOAD = _step(STEPS, "Upload")


def _environment(step: Step, contexts: dict[str, str], **extra: str) -> dict[str, str]:
    return {**resolve_env(step.env, contexts), "RUNNER_TEMP": RUNNER_TEMP, **extra}


def _contexts(value: str) -> dict[str, str]:
    return {
        "inputs.expected_sha": value,
        "inputs.confirm": value,
        "secrets.SUPABASE_DB_URL": "postgresql://stub-never-contacted.invalid/none",
    }


def _top_level_block(text: str, key: str) -> list[str]:
    lines = text.splitlines()
    start = lines.index(f"{key}:")
    block = []
    for line in lines[start + 1 :]:
        if line and not line.startswith(" "):
            break
        if line.strip():
            block.append(line.strip())
    return block


# --------------------------------------------------------------------------- static contract


def test_it_is_the_workflow_the_script_verifies_and_it_is_dispatch_only() -> None:
    assert PATH.is_file()
    assert trigger_keys(TEXT) == {"workflow_dispatch"}, "no schedule, no push: one owner dispatch"
    assert apply_0008.WORKFLOW == ".github/workflows/apply-migration-0008.yml"


def test_both_inputs_are_required_strings_and_the_token_is_the_script_s() -> None:
    expected = TEXT.split("      expected_sha:", 1)[1].split("      confirm:", 1)[0]
    confirm = TEXT.split("      confirm:", 1)[1].split("permissions:", 1)[0]
    for block in (expected, confirm):
        assert "required: true" in block and "type: string" in block
        assert "default:" not in block
    assert apply_0008.CONFIRMATION in confirm


def test_it_can_never_run_beside_another_production_database_dispatch() -> None:
    assert _top_level_block(TEXT, "concurrency") == _top_level_block(EVALUATION_TEXT, "concurrency")
    assert "cancel-in-progress: false" in _top_level_block(TEXT, "concurrency")
    assert _top_level_block(TEXT, "permissions") == ["contents: read"]


def test_no_expression_is_ever_pasted_into_shell_source() -> None:
    assert len(RUN_STEPS) == 4, "the reader must find every run step, or the checks are vacuous"
    for step in RUN_STEPS:
        assert "${{" not in step.run, step.name
        assert "secrets." not in step.run, step.name
        assert step.shell == "bash", step.name
        assert not re.search(r"(?<!\|)\|(?!\|)", step.run), step.name
        occurrences = re.findall(r"\$\{?MIGRATION_0008_[A-Z_]+\}?", step.run)
        quoted = re.findall(r'="\$MIGRATION_0008_[A-Z_]+"', step.run)
        assert len(occurrences) == len(quoted), step.name


def test_only_the_apply_step_receives_the_database_secret() -> None:
    holders = [step.name for step in STEPS if any("secrets." in v for v in step.env.values())]
    assert holders == [APPLY.name]
    assert not JOB.env, "no job-level environment: nothing is shared across steps"
    for step in STEPS:
        assert all("secrets." not in value for value in step.with_.values()), step.name
    assert TEXT.count("secrets.") == 1


def test_every_step_takes_exactly_its_inputs_from_the_environment() -> None:
    assert APPLY.env == {
        "SUPABASE_DB_URL": "${{ secrets.SUPABASE_DB_URL }}",
        "MIGRATION_0008_EXPECTED_SHA": "${{ inputs.expected_sha }}",
        "MIGRATION_0008_CONFIRM": "${{ inputs.confirm }}",
    }
    assert ATTEST.env == {"MIGRATION_0008_EXPECTED_SHA": "${{ inputs.expected_sha }}"}
    assert INSTALL.env == {}
    assert TESTS.env == {"PYTHONDONTWRITEBYTECODE": "1", "PYTHONNOUSERSITE": "1"}


def test_the_steps_run_in_the_safety_order() -> None:
    order = [
        next(step.index for step in STEPS if step.uses and "actions/checkout@" in step.uses),
        next(step.index for step in STEPS if step.uses and "actions/setup-python@" in step.uses),
        INSTALL.index,
        ATTEST.index,
        TESTS.index,
        APPLY.index,
        UPLOAD.index,
    ]
    assert order == sorted(order) and len(set(order)) == len(STEPS)


def test_the_actions_and_the_runner_are_exactly_the_evaluation_s() -> None:
    uses = [step.uses for step in STEPS if step.uses]
    assert uses == [step.uses for step in EVALUATION_STEPS if step.uses]
    for reference in uses:
        assert re.fullmatch(r"actions/[a-z-]+@[0-9a-f]{40}", reference), reference
    setup = next(step for step in STEPS if step.uses and "actions/setup-python@" in step.uses)
    assert setup.with_ == {
        "python-version": provenance.PINNED_PYTHON_VERSION,
        "check-latest": "false",
    }
    assert apply_0008.PINNED_PYTHON == (
        provenance.PINNED_PYTHON_IMPLEMENTATION,
        provenance.PINNED_PYTHON_VERSION,
    )
    checkout = next(step for step in STEPS if step.uses and "actions/checkout@" in step.uses)
    assert checkout.with_ == {"persist-credentials": "false"}
    assert JOB.fields["runs-on"] == "ubuntu-24.04"


def test_the_install_is_the_evaluation_s_trusted_install_verbatim() -> None:
    """J1=B. One reviewed install text, not two that could drift apart."""

    assert INSTALL.run == _step(EVALUATION_STEPS, "hash-locked").run
    assert "-m pip" not in TEXT and "requirements.txt" not in TEXT


def test_every_python_process_is_isolated_or_is_the_bytecode_free_test_run() -> None:
    for step in (ATTEST, APPLY):
        assert step.run.startswith(f"python -I -S -B {apply_0008.SCRIPT} "), step.name
    invocations = 0
    for step in RUN_STEPS:
        assert "PYTHONPATH" not in step.run, step.name
        for match in re.finditer(r"\bpython\b(?P<rest>[^\n]*)", step.run):
            invocations += 1
            assert match.group("rest").startswith((" -I -S -B ", " -s -B -m pytest ")), step.name
    assert invocations == 7


def test_the_in_job_tests_cover_the_script_the_migration_and_this_boundary() -> None:
    command = TESTS.run.split()
    assert command[:7] == ["python", "-s", "-B", "-m", "pytest", "-q", "-p"]
    paths = [part for part in command if part.startswith("tests/")]
    assert paths == [
        "tests/scripts/test_apply_migration_0008.py",
        "tests/migrations/test_analysis_run_details_migration.py",
        "tests/workflows/test_apply_migration_0008_workflow.py",
        "tests/workflows/test_workflow_steps_reader.py",
    ]
    for path in paths:
        assert (ROOT / path).is_file(), path


def test_the_uploaded_report_is_the_one_the_apply_writes() -> None:
    assert f"--report={REPORT}" in APPLY.run
    assert UPLOAD.with_["path"] == REPORT
    assert UPLOAD.fields.get("if") == "always()"


def test_the_seal_workflow_is_untouched_and_never_names_0008_s_route() -> None:
    seal = (ROOT / provenance.SEAL_MIGRATION_WORKFLOW).read_text(encoding="utf-8")
    assert "apply_migration_0008" not in seal and "0008_analysis_run_details" not in seal


# --------------------------------------------------------------------------- executed


@pytest.mark.parametrize("hostile", HOSTILE)
def test_hostile_inputs_reach_the_script_as_inert_arguments(tmp_path: Path, hostile: str) -> None:
    log = tmp_path / "calls.jsonl"
    bin_dir = tmp_path / "bin"
    install_stub(bin_dir, "python", log)

    contexts = _contexts(hostile)
    attested = run_step(
        ATTEST, env=_environment(ATTEST, contexts), workdir=tmp_path, bin_dir=bin_dir
    )
    applied = run_step(APPLY, env=_environment(APPLY, contexts), workdir=tmp_path, bin_dir=bin_dir)
    assert attested.returncode == 0, attested.stderr
    assert applied.returncode == 0, applied.stderr

    assert [call["argv"] for call in stub_calls(log)] == [
        [*ENTRYPOINT, "--mode=attest", f"--expected-sha={hostile}", f"--wheelhouse={WHEELHOUSE}"],
        [
            *ENTRYPOINT,
            "--mode=apply",
            f"--expected-sha={hostile}",
            f"--confirm={hostile}",
            f"--wheelhouse={WHEELHOUSE}",
            f"--report={REPORT}",
        ],
    ]
    assert not list(tmp_path.glob("INJECTED*")), "an input executed as a command"


@pytest.mark.parametrize("hostile", HOSTILE)
def test_the_real_parser_binds_each_hostile_value_to_its_own_option(
    tmp_path: Path, hostile: str
) -> None:
    log = tmp_path / "calls.jsonl"
    install_stub(tmp_path / "bin", "python", log)
    run_step(
        APPLY,
        env=_environment(APPLY, _contexts(hostile)),
        workdir=tmp_path,
        bin_dir=tmp_path / "bin",
    )
    (call,) = stub_calls(log)
    assert call["argv"][: len(ENTRYPOINT)] == list(ENTRYPOINT)
    args = apply_0008.build_parser().parse_args(call["argv"][len(ENTRYPOINT) :])
    assert args.mode == apply_0008.MODE_APPLY, "the mode is fixed in the workflow, never an input"
    assert args.confirm == hostile and args.expected_sha == hostile
    assert args.wheelhouse == WHEELHOUSE and args.report == REPORT


@pytest.mark.parametrize("step", RUN_STEPS, ids=lambda step: step.name)
def test_a_failing_command_fails_its_step(tmp_path: Path, step: Step) -> None:
    install_stub(tmp_path / "bin", "python", tmp_path / "calls.jsonl")
    env = _environment(step, _contexts("value"), STUB_EXIT="2", STUB_STDOUT=BUNDLED_PIP)
    completed = run_step(step, env=env, workdir=tmp_path, bin_dir=tmp_path / "bin")
    assert completed.returncode == 2, (step.name, completed.stderr)


@pytest.mark.parametrize("step", RUN_STEPS, ids=lambda step: step.name)
def test_a_succeeding_command_leaves_its_step_green(tmp_path: Path, step: Step) -> None:
    install_stub(tmp_path / "bin", "python", tmp_path / "calls.jsonl")
    env = _environment(step, _contexts("value"), STUB_EXIT="0", STUB_STDOUT=BUNDLED_PIP)
    completed = run_step(step, env=env, workdir=tmp_path, bin_dir=tmp_path / "bin")
    assert completed.returncode == 0, (step.name, completed.stderr)
    assert len(stub_calls(tmp_path / "calls.jsonl")) == (4 if step is INSTALL else 1)
