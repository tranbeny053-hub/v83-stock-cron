"""The older-table privilege audit workflows, read and EXECUTED the way GitHub runs them.

The audit workflow holds the production database secret, so it carries every guard the other
database routes earned. The rehearsal workflow must never reference a secret at all.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from crypto_probability_engine.oos.evaluation import provenance
from scripts import audit_table_privileges as audit
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
PATH = ROOT / audit.WORKFLOW
TEXT = PATH.read_text(encoding="utf-8")
JOB = read_jobs(TEXT)["audit"]
STEPS = JOB.steps
RUN_STEPS = [step for step in STEPS if step.run is not None]

REHEARSAL_PATH = ROOT / ".github/workflows/audit-table-privileges-rehearsal.yml"
REHEARSAL_TEXT = REHEARSAL_PATH.read_text(encoding="utf-8")
REHEARSAL_JOB = read_jobs(REHEARSAL_TEXT)["test"]

EVALUATION_TEXT = (ROOT / provenance.EVALUATION_WORKFLOW).read_text(encoding="utf-8")
EVALUATION_STEPS = read_jobs(EVALUATION_TEXT)["evaluate"].steps

ENTRYPOINT = ("-I", "-S", "-B", audit.SCRIPT)
RUNNER_TEMP = "/home/runner/work/_temp"
WHEELHOUSE = f"{RUNNER_TEMP}/section-5a-wheels"
REPORT = "older-table-privilege-audit.json"
REHEARSAL_URL = "postgresql:///audit_rehearsal?host=/var/run/postgresql"
FIXTURE_BUNDLE = (
    "scripts/audit_rehearsal/00_supabase_like_roles.sql migrations/0001_init.sql "
    "migrations/0002_news.sql migrations/0003_prediction_ledger.sql "
    "migrations/0004_prediction_outcomes.sql migrations/0007_prediction_origin.sql "
    "scripts/audit_rehearsal/90_variations.sql"
)

HOSTILE = (
    "'; touch INJECTED_SINGLE; #'",
    '"; touch INJECTED_DOUBLE; "',
    "$(touch INJECTED_SUBSHELL)",
    "`touch INJECTED_BACKTICK`",
    "x\ntouch INJECTED_NEWLINE",
    "--mode=audit",
    "a b\tc *",
)


def _step(steps, fragment: str) -> Step:
    matches = [step for step in steps if step.name and fragment in step.name]
    assert len(matches) == 1, (fragment, [step.name for step in steps])
    return matches[0]


INSTALL = _step(STEPS, "hash-locked")
ATTEST = _step(STEPS, "Attest")
REHEARSE = _step(STEPS, "Rehearse")
TESTS = _step(STEPS, "tests under this exact runtime")
AUDIT = _step(STEPS, "Audit the older tables")
UPLOAD = _step(STEPS, "Upload")


def _environment(step: Step, contexts: dict[str, str]) -> dict[str, str]:
    return {**resolve_env(step.env, contexts), "RUNNER_TEMP": RUNNER_TEMP}


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


# --------------------------------------------------------------------------- the audit workflow


def test_the_audit_workflow_is_dispatch_only_with_required_inputs() -> None:
    assert trigger_keys(TEXT) == {"workflow_dispatch"}
    expected = TEXT.split("      expected_sha:", 1)[1].split("      confirm:", 1)[0]
    confirm = TEXT.split("      confirm:", 1)[1].split("permissions:", 1)[0]
    for block in (expected, confirm):
        assert "required: true" in block and "type: string" in block
        assert "default:" not in block
    assert audit.CONFIRMATION in confirm


def test_it_can_never_run_beside_another_production_database_dispatch() -> None:
    assert _top_level_block(TEXT, "concurrency") == _top_level_block(EVALUATION_TEXT, "concurrency")
    assert _top_level_block(TEXT, "permissions") == ["contents: read"]


def test_no_expression_is_ever_pasted_into_shell_source() -> None:
    assert len(RUN_STEPS) == 5
    for step in RUN_STEPS:
        assert "${{" not in step.run, step.name
        assert "secrets." not in step.run, step.name
        assert step.shell == "bash", step.name
        assert not re.search(r"(?<!\|)\|(?!\|)", step.run), step.name
        occurrences = re.findall(r"\$\{?AUDIT_[A-Z_]+\}?", step.run)
        quoted = re.findall(r'="\$AUDIT_[A-Z_]+"', step.run)
        assert len(occurrences) == len(quoted), step.name


def test_only_the_audit_step_receives_the_database_secret() -> None:
    holders = [step.name for step in STEPS if any("secrets." in v for v in step.env.values())]
    assert holders == [AUDIT.name]
    assert not JOB.env
    assert TEXT.count("secrets.") == 1


def test_every_step_takes_exactly_its_inputs_from_the_environment() -> None:
    assert AUDIT.env == {
        "SUPABASE_DB_URL": "${{ secrets.SUPABASE_DB_URL }}",
        "AUDIT_EXPECTED_SHA": "${{ inputs.expected_sha }}",
        "AUDIT_CONFIRM": "${{ inputs.confirm }}",
    }
    assert ATTEST.env == {"AUDIT_EXPECTED_SHA": "${{ inputs.expected_sha }}"}
    assert REHEARSE.env == {"AUDIT_REHEARSAL_URL": REHEARSAL_URL}
    assert INSTALL.env == {}
    assert TESTS.env == {"PYTHONDONTWRITEBYTECODE": "1", "PYTHONNOUSERSITE": "1"}


def test_the_steps_run_in_the_safety_order() -> None:
    order = [
        next(step.index for step in STEPS if step.uses and "actions/checkout@" in step.uses),
        next(step.index for step in STEPS if step.uses and "actions/setup-python@" in step.uses),
        INSTALL.index,
        ATTEST.index,
        REHEARSE.index,
        TESTS.index,
        AUDIT.index,
        UPLOAD.index,
    ]
    assert order == sorted(order) and len(set(order)) == len(STEPS)


def test_the_actions_runner_and_install_are_exactly_the_evaluation_s() -> None:
    uses = [step.uses for step in STEPS if step.uses]
    assert uses == [step.uses for step in EVALUATION_STEPS if step.uses]
    assert INSTALL.run == _step(EVALUATION_STEPS, "hash-locked").run
    assert JOB.fields["runs-on"] == "ubuntu-24.04"


def test_every_python_process_is_isolated_or_is_the_bytecode_free_test_run() -> None:
    for step in (ATTEST, AUDIT):
        assert step.run.startswith(f"python -I -S -B {audit.SCRIPT} "), step.name
    assert f"python -I -S -B {audit.SCRIPT} --mode=rehearse" in REHEARSE.run
    for step in RUN_STEPS:
        for match in re.finditer(r"\bpython\b(?P<rest>[^\n]*)", step.run):
            assert match.group("rest").startswith((" -I -S -B ", " -s -B -m pytest ")), step.name


def test_the_rehearsal_step_builds_the_scratch_database_from_the_real_migrations() -> None:
    lines = REHEARSE.run.strip().splitlines()
    assert lines[0] == "sudo systemctl start postgresql.service"
    assert lines[1] == "sudo -u postgres createdb audit_rehearsal"
    assert "CREATE ROLE" in lines[2] and "$(id -un)" in lines[2] and "LOGIN" in lines[2]
    assert "SUPERUSER" not in REHEARSE.run and "GRANT" not in REHEARSE.run
    assert lines[3] == f'cat {FIXTURE_BUNDLE} > "$RUNNER_TEMP/audit_rehearsal.sql"'
    assert "-v ON_ERROR_STOP=1" in lines[4] and '< "$RUNNER_TEMP/audit_rehearsal.sql"' in lines[4]
    assert "--mode=rehearse" in lines[5] and "SUPABASE" not in REHEARSE.run
    for relative in FIXTURE_BUNDLE.split():
        assert (ROOT / relative).is_file(), relative


def test_the_in_job_tests_cover_the_script_and_this_boundary() -> None:
    paths = [part for part in TESTS.run.split() if part.startswith("tests/")]
    assert paths == [
        "tests/scripts/test_audit_table_privileges.py",
        "tests/workflows/test_audit_table_privileges_workflow.py",
        "tests/workflows/test_workflow_steps_reader.py",
    ]


def test_both_reports_are_uploaded_always() -> None:
    assert f"--report={REPORT}" in AUDIT.run
    assert "--report=audit-rehearsal-report.json" in REHEARSE.run
    assert UPLOAD.fields.get("if") == "always()"
    assert UPLOAD.with_["path"].split() == [REPORT, "audit-rehearsal-report.json"]


@pytest.mark.parametrize("hostile", HOSTILE)
def test_hostile_inputs_reach_the_script_as_inert_arguments(tmp_path: Path, hostile: str) -> None:
    log = tmp_path / "calls.jsonl"
    install_stub(tmp_path / "bin", "python", log)
    contexts = _contexts(hostile)
    for step in (ATTEST, AUDIT):
        completed = run_step(
            step, env=_environment(step, contexts), workdir=tmp_path, bin_dir=tmp_path / "bin"
        )
        assert completed.returncode == 0, completed.stderr
    attest_call, audit_call = (call["argv"] for call in stub_calls(log))
    assert attest_call == [
        *ENTRYPOINT, "--mode=attest", f"--expected-sha={hostile}", f"--wheelhouse={WHEELHOUSE}"
    ]
    args = audit.build_parser().parse_args(audit_call[len(ENTRYPOINT) :])
    assert args.mode == audit.MODE_AUDIT
    assert args.expected_sha == hostile and args.confirm == hostile
    assert args.wheelhouse == WHEELHOUSE and args.report == REPORT
    assert not list(tmp_path.glob("INJECTED*"))


@pytest.mark.parametrize("step", [ATTEST, AUDIT, TESTS], ids=lambda step: step.name)
def test_a_failing_command_fails_its_step(tmp_path: Path, step: Step) -> None:
    install_stub(tmp_path / "bin", "python", tmp_path / "calls.jsonl")
    env = {**_environment(step, _contexts("value")), "STUB_EXIT": "2"}
    completed = run_step(step, env=env, workdir=tmp_path, bin_dir=tmp_path / "bin")
    assert completed.returncode == 2, (step.name, completed.stderr)


# --------------------------------------------------------------------------- the rehearsal workflow


def test_the_rehearsal_workflow_holds_no_secret_and_runs_only_on_pull_requests() -> None:
    assert trigger_keys(REHEARSAL_TEXT) == {"pull_request"}
    assert "secrets." not in REHEARSAL_TEXT and "${{" not in REHEARSAL_TEXT
    assert "SUPABASE" not in REHEARSAL_TEXT
    assert _top_level_block(REHEARSAL_TEXT, "permissions") == ["contents: read"]
    assert "concurrency:" not in REHEARSAL_TEXT


def test_the_rehearsal_workflow_watches_every_file_it_proves() -> None:
    watched = _top_level_block(REHEARSAL_TEXT, '"on"')
    for path in (
        audit.SCRIPT,
        "scripts/audit_rehearsal/**",
        audit.WORKFLOW,
        ".github/workflows/audit-table-privileges-rehearsal.yml",
        *audit.AUDIT_MIGRATIONS,
    ):
        assert f"- {path}" in watched, path


def test_the_rehearsal_job_is_named_test_so_the_merge_procedure_waits_for_it() -> None:
    assert list(read_jobs(REHEARSAL_TEXT)) == ["test"]
    assert REHEARSAL_JOB.fields["runs-on"] == "ubuntu-24.04"
    for step in REHEARSAL_JOB.steps:
        if step.uses:
            assert re.fullmatch(r"actions/[a-z-]+@[0-9a-f]{40}", step.uses), step.uses
        if step.run is not None:
            assert step.shell == "bash" and "${{" not in step.run


def test_the_rehearsal_workflow_rehearses_exactly_like_the_audit_workflow() -> None:
    rehearse = _step(REHEARSAL_JOB.steps, "Rehearse")
    assert rehearse.env == {"AUDIT_REHEARSAL_URL": REHEARSAL_URL}
    ours = rehearse.run.strip().splitlines()
    theirs = REHEARSE.run.strip().splitlines()
    assert ours[:5] == theirs[:5], "the scratch database is built identically"
    assert ours[5] == (
        f"PYTHONPATH=src python {audit.SCRIPT} --mode=rehearse --report=audit-rehearsal-report.json"
    )
