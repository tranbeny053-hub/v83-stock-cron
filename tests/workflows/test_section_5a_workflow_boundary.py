"""The evaluation workflow, EXECUTED the way GitHub runs it (owner ruling E1).

V808-F1: `--confirm '${{ inputs.confirm }}'` pasted a dispatch input into shell source after the
pin check, so a quote in the input became a command. V808-R6: `| tee` under GitHub's default
`bash -e` turned a refusal into a green run. Both passed every text assertion. These tests read
each step exactly as GitHub hands it to the shell and RUN it, against a stub interpreter, with
hostile inputs.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from crypto_probability_engine.oos.evaluation import provenance, runner
from scripts import evaluate_section_5a as cli
from tests.workflows._workflow_steps import (
    Step,
    install_stub,
    read_jobs,
    resolve_env,
    run_step,
    stub_calls,
)

ROOT = Path(__file__).resolve().parents[2]
TEXT = (ROOT / ".github/workflows/section-5a-evaluation.yml").read_text(encoding="utf-8")
JOB = read_jobs(TEXT)["evaluate"]
STEPS = JOB.steps
RUN_STEPS = [step for step in STEPS if step.run is not None]

ISOLATED_ENTRYPOINT = ("-I", "-S", "-B", "scripts/evaluate_section_5a.py")
RUNNER_TEMP = "/home/runner/work/_temp"
WHEELHOUSE = f"{RUNNER_TEMP}/section-5a-wheels"
BUNDLED_PIP = "/opt/hostedtoolcache/Python/3.13.14/x64/lib/python3.13/ensurepip/_bundled/pip.whl"

HOSTILE = (
    "'; touch INJECTED_SINGLE; #'",
    '"; touch INJECTED_DOUBLE; "',
    "$(touch INJECTED_SUBSHELL)",
    "`touch INJECTED_BACKTICK`",
    "x\ntouch INJECTED_NEWLINE",
    "--write-pin",
    "a b\tc *",
    "\\",
)


def _step(fragment: str) -> Step:
    matches = [step for step in STEPS if step.name and fragment in step.name]
    assert len(matches) == 1, (fragment, [step.name for step in STEPS])
    return matches[0]


INSTALL = _step("hash-locked")
ATTEST = _step("Attest")
TESTS = _step("tests under this exact runtime")
EVALUATE = _step("Run the evaluation")
UPLOAD = _step("Upload")


def _environment(step: Step, contexts: dict[str, str], **extra: str) -> dict[str, str]:
    """What GitHub gives a step: its resolved env, plus RUNNER_TEMP, which every runner sets."""

    return {**resolve_env(step.env, contexts), "RUNNER_TEMP": RUNNER_TEMP, **extra}


def _contexts(value: str) -> dict[str, str]:
    return {
        "inputs.mode": value,
        "inputs.expected_sha": value,
        "inputs.confirm": value,
        "secrets.SUPABASE_DB_URL": "postgresql://stub-never-contacted.invalid/none",
    }


# --------------------------------------------------------------------------- static contract


def test_no_expression_is_ever_pasted_into_shell_source() -> None:
    assert RUN_STEPS, "the reader must find the run steps, or every check below is vacuous"
    for step in RUN_STEPS:
        assert "${{" not in step.run, step.name
        assert "secrets." not in step.run, step.name


def test_every_run_step_declares_bash_with_pipefail() -> None:
    """Only an explicit `shell: bash` runs with pipefail; unspecified is `bash -e` (V808-R6)."""

    for step in RUN_STEPS:
        assert step.shell == "bash", step.name


def test_no_step_pipes_the_evaluator_or_the_installer() -> None:
    for step in RUN_STEPS:
        assert not re.search(r"(?<!\|)\|(?!\|)", step.run), step.name


def test_inputs_are_expanded_only_inside_double_quotes() -> None:
    for step in RUN_STEPS:
        occurrences = re.findall(r"\$\{?SECTION_5A_[A-Z_]+\}?", step.run)
        quoted = re.findall(r'="\$SECTION_5A_[A-Z_]+"', step.run)
        assert len(occurrences) == len(quoted), step.name


def test_only_the_evaluation_step_receives_the_database_secret() -> None:
    holders = [step.name for step in STEPS if any("secrets." in v for v in step.env.values())]
    assert holders == [EVALUATE.name]
    assert EVALUATE.env["SUPABASE_DB_URL"] == "${{ secrets.SUPABASE_DB_URL }}"
    assert not JOB.env, "no job-level environment: nothing is shared across steps"
    for step in STEPS:
        assert all("secrets." not in value for value in step.with_.values()), step.name
    assert TEXT.count("secrets.") == 1


def test_the_evaluator_only_ever_runs_isolated_and_nothing_writes_bytecode() -> None:
    """G1=A. `-I -S -B` for every evaluator process; `-B` for every other Python step."""

    for step in (ATTEST, EVALUATE):
        assert step.run.startswith("python -I -S -B scripts/evaluate_section_5a.py "), step.name
    invocations = 0
    for step in RUN_STEPS:
        assert "PYTHONPATH" not in step.run, step.name
        for match in re.finditer(r"\bpython\b(?P<rest>[^\n]*)", step.run):
            invocations += 1
            rest = match.group("rest")
            # J1=B: every process that installs or evaluates is isolated; only pytest is not,
            # and it may neither write bytecode nor import user site-packages.
            assert rest.startswith((" -I -S -B ", " -s -B -m pytest ")), (step.name, rest)
    assert invocations >= 6, "the check must see every Python invocation, or it proves nothing"


def test_the_evaluation_takes_every_input_from_the_environment() -> None:
    assert EVALUATE.env == {
        "SUPABASE_DB_URL": "${{ secrets.SUPABASE_DB_URL }}",
        "SECTION_5A_MODE": "${{ inputs.mode }}",
        "SECTION_5A_EXPECTED_SHA": "${{ inputs.expected_sha }}",
        "SECTION_5A_CONFIRM": "${{ inputs.confirm }}",
    }
    assert ATTEST.env == {"SECTION_5A_EXPECTED_SHA": "${{ inputs.expected_sha }}"}
    assert INSTALL.env == {}
    assert TESTS.env == {"PYTHONDONTWRITEBYTECODE": "1", "PYTHONNOUSERSITE": "1"}


def test_the_steps_run_in_the_safety_order() -> None:
    """Interpreter, lock, isolated attestation, tests under that runtime, then the secret."""

    order = [
        next(step.index for step in STEPS if step.uses and "actions/checkout@" in step.uses),
        next(step.index for step in STEPS if step.uses and "actions/setup-python@" in step.uses),
        INSTALL.index,
        ATTEST.index,
        TESTS.index,
        EVALUATE.index,
        UPLOAD.index,
    ]
    assert order == sorted(order) and len(set(order)) == len(STEPS)


def test_every_action_is_pinned_to_a_full_commit_sha() -> None:
    uses = [step.uses for step in STEPS if step.uses]
    assert len(uses) == 3
    for reference in uses:
        assert re.fullmatch(r"actions/[a-z-]+@[0-9a-f]{40}", reference), reference


def test_the_interpreter_is_exactly_the_one_the_evaluator_pins() -> None:
    setup = next(step for step in STEPS if step.uses and "actions/setup-python@" in step.uses)
    assert setup.with_ == {
        "python-version": provenance.PINNED_PYTHON_VERSION,
        "check-latest": "false",
    }, "no cache and no version range: the interpreter is exact"


def test_the_install_runs_only_cpython_s_bundled_pip_on_authenticated_wheels() -> None:
    """J1=B. The floating pip is deleted unrun; CPython's bundled pip downloads, then installs
    from the downloaded wheels alone, with every hash required and nothing compiled."""

    commands = [
        " ".join(line.split())
        for line in INSTALL.run.replace("\\\n", " ").splitlines()
        if line.strip()
    ]
    lock = provenance.EVALUATOR_LOCK
    assert commands == [
        "python -I -S -B scripts/evaluate_section_5a.py --remove-floating-installer",
        'bundled_pip="$(python -I -S -B scripts/evaluate_section_5a.py --bundled-pip)"',
        'python -I -S -B "$bundled_pip/pip" download --no-cache-dir --disable-pip-version-check '
        "--require-hashes --no-deps --only-binary=:all: "
        f'--dest "$RUNNER_TEMP/section-5a-wheels" -r {lock}',
        'python -I -S -B "$bundled_pip/pip" install --no-cache-dir --disable-pip-version-check '
        '--no-index --find-links "$RUNNER_TEMP/section-5a-wheels" --no-compile '
        f"--require-hashes --no-deps --only-binary=:all: -r {lock}",
    ]
    assert "requirements.txt" not in TEXT
    assert "-m pip" not in TEXT, "the floating pip must never be executed"


def test_the_checkout_keeps_no_credentials_and_the_image_is_pinned() -> None:
    checkout = next(step for step in STEPS if step.uses and "actions/checkout@" in step.uses)
    assert checkout.with_ == {"persist-credentials": "false"}
    assert JOB.fields["runs-on"] == "ubuntu-24.04"


def test_expected_sha_is_a_required_dispatch_input() -> None:
    block = TEXT.split("      expected_sha:", 1)[1].split("      confirm:", 1)[0]
    assert "required: true" in block and "type: string" in block


def test_the_in_job_tests_cover_the_evaluator_and_this_boundary() -> None:
    command = TESTS.run.split()
    assert command[:7] == ["python", "-s", "-B", "-m", "pytest", "-q", "-p"]
    paths = [part for part in command if part.startswith("tests/")]
    for required in (
        "tests/oos/evaluation",
        "tests/workflows/test_section_5a_workflow_boundary.py",
        "tests/workflows/test_workflow_steps_reader.py",
        "tests/scripts/test_evaluate_section_5a.py",
        "tests/persistence/test_section_5a_seal_sql.py",
        "tests/migrations/test_section_5a_seal_migration.py",
    ):
        assert required in paths, required
    for path in paths:
        assert (ROOT / path).exists(), path


# --------------------------------------------------------------------------- executed


@pytest.mark.parametrize("hostile", HOSTILE)
def test_hostile_inputs_reach_the_evaluator_as_inert_arguments(
    tmp_path: Path, hostile: str
) -> None:
    """Whatever is typed into the dispatch form arrives as ONE argument and runs nothing."""

    log = tmp_path / "calls.jsonl"
    bin_dir = tmp_path / "bin"
    install_stub(bin_dir, "python", log)

    contexts = _contexts(hostile)
    attested = run_step(
        ATTEST, env=_environment(ATTEST, contexts), workdir=tmp_path, bin_dir=bin_dir
    )
    evaluated = run_step(
        EVALUATE, env=_environment(EVALUATE, contexts), workdir=tmp_path, bin_dir=bin_dir
    )
    assert attested.returncode == 0, attested.stderr
    assert evaluated.returncode == 0, evaluated.stderr

    calls = stub_calls(log)
    assert [call["argv"] for call in calls] == [
        [
            *ISOLATED_ENTRYPOINT,
            "--mode=attest",
            f"--expected-sha={hostile}",
            f"--wheelhouse={WHEELHOUSE}",
        ],
        [
            *ISOLATED_ENTRYPOINT,
            f"--mode={hostile}",
            f"--expected-sha={hostile}",
            f"--confirm={hostile}",
            f"--wheelhouse={WHEELHOUSE}",
            "--artifact-dir=.work/section_5a",
            "--report=section-5a-report.json",
        ],
    ]
    assert all(call["PYTHONPATH"] is None for call in calls), "-I ignores it; it must not be set"
    assert not list(tmp_path.glob("INJECTED*")), "an input executed as a command"


@pytest.mark.parametrize("hostile", HOSTILE)
def test_the_real_parser_binds_each_hostile_value_to_its_own_option(
    tmp_path: Path, hostile: str
) -> None:
    log = tmp_path / "calls.jsonl"
    install_stub(tmp_path / "bin", "python", log)
    contexts = {**_contexts(hostile), "inputs.mode": runner.MODE_CONSUME}
    env = _environment(EVALUATE, contexts)
    run_step(EVALUATE, env=env, workdir=tmp_path, bin_dir=tmp_path / "bin")
    (call,) = stub_calls(log)
    assert call["argv"][: len(ISOLATED_ENTRYPOINT)] == list(ISOLATED_ENTRYPOINT)
    args = cli.build_parser().parse_args(call["argv"][len(ISOLATED_ENTRYPOINT) :])
    assert args.mode == runner.MODE_CONSUME
    assert args.confirm == hostile and args.expected_sha == hostile
    assert args.wheelhouse == WHEELHOUSE
    assert args.write_pin is False and args.remove_floating_installer is False


@pytest.mark.parametrize("step", RUN_STEPS, ids=lambda step: step.name)
def test_a_failing_command_fails_its_step(tmp_path: Path, step: Step) -> None:
    """V808-R6: a refusal is a red step, never a green one."""

    install_stub(tmp_path / "bin", "python", tmp_path / "calls.jsonl")
    env = _environment(step, _contexts("value"), STUB_EXIT="5", STUB_STDOUT=BUNDLED_PIP)
    completed = run_step(step, env=env, workdir=tmp_path, bin_dir=tmp_path / "bin")
    assert completed.returncode == 5, (step.name, completed.stderr)


@pytest.mark.parametrize("step", RUN_STEPS, ids=lambda step: step.name)
def test_a_succeeding_command_leaves_its_step_green(tmp_path: Path, step: Step) -> None:
    """The counterpart, so a step that always failed could not pass the test above."""

    install_stub(tmp_path / "bin", "python", tmp_path / "calls.jsonl")
    env = _environment(step, _contexts("value"), STUB_EXIT="0", STUB_STDOUT=BUNDLED_PIP)
    completed = run_step(step, env=env, workdir=tmp_path, bin_dir=tmp_path / "bin")
    assert completed.returncode == 0, (step.name, completed.stderr)
    assert len(stub_calls(tmp_path / "calls.jsonl")) == (4 if step is INSTALL else 1)


def test_the_install_step_executes_in_the_trusted_order(tmp_path: Path) -> None:
    """Executed: removal first, then the bundled pip downloads, then installs from the wheels."""

    log = tmp_path / "calls.jsonl"
    install_stub(tmp_path / "bin", "python", log)
    env = _environment(INSTALL, _contexts("value"), STUB_STDOUT=BUNDLED_PIP)
    completed = run_step(INSTALL, env=env, workdir=tmp_path, bin_dir=tmp_path / "bin")
    assert completed.returncode == 0, completed.stderr
    argv = [call["argv"] for call in stub_calls(log)]
    assert argv[0] == [*ISOLATED_ENTRYPOINT, "--remove-floating-installer"]
    assert argv[1] == [*ISOLATED_ENTRYPOINT, "--bundled-pip"]
    assert argv[2][:5] == ["-I", "-S", "-B", f"{BUNDLED_PIP}/pip", "download"]
    assert argv[2][argv[2].index("--dest") + 1] == WHEELHOUSE
    assert argv[3][:5] == ["-I", "-S", "-B", f"{BUNDLED_PIP}/pip", "install"]
    assert argv[3][argv[3].index("--find-links") + 1] == WHEELHOUSE
    assert {"--no-index", "--no-compile", "--require-hashes", "--no-deps"} <= set(argv[3])
