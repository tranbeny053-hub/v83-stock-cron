"""The migration-0010 workflows, read and EXECUTED the way GitHub runs them.

The apply workflow holds the production database secret, so it carries every guard the other
database routes earned. The rehearsal workflow must never reference a secret at all, and it must
rehearse exactly as the apply workflow does before the secret is handed out.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from crypto_probability_engine.oos.evaluation import provenance
from scripts import apply_migration_0010 as apply_0010
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
PATH = ROOT / apply_0010.WORKFLOW
TEXT = PATH.read_text(encoding="utf-8")
JOB = read_jobs(TEXT)["apply"]
STEPS = JOB.steps
RUN_STEPS = [step for step in STEPS if step.run is not None]

REHEARSAL_PATH = ROOT / apply_0010.REHEARSAL_WORKFLOW
REHEARSAL_TEXT = REHEARSAL_PATH.read_text(encoding="utf-8")
REHEARSAL_JOB = read_jobs(REHEARSAL_TEXT)["test"]

EVALUATION_TEXT = (ROOT / provenance.EVALUATION_WORKFLOW).read_text(encoding="utf-8")
EVALUATION_STEPS = read_jobs(EVALUATION_TEXT)["evaluate"].steps

ENTRYPOINT = ("-I", "-S", "-B", apply_0010.SCRIPT)
RUNNER_TEMP = "/home/runner/work/_temp"
WHEELHOUSE = f"{RUNNER_TEMP}/section-5a-wheels"
REPORT = "migration-0010-apply-report.json"
REHEARSAL_REPORT = "migration-0010-rehearsal-report.json"
REHEARSAL_URL = "postgresql:///migration_0010_rehearsal?host=/var/run/postgresql"
FIXTURES = "scripts/migration_0010_rehearsal"
MIGRATIONS_0001_0009 = " ".join(
    path.relative_to(ROOT).as_posix()
    for path in sorted((ROOT / "migrations").glob("000*.sql"))
)

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


def _step(steps, fragment: str) -> Step:
    matches = [step for step in steps if step.name and fragment in step.name]
    assert len(matches) == 1, (fragment, [step.name for step in steps])
    return matches[0]


INSTALL = _step(STEPS, "hash-locked")
ATTEST = _step(STEPS, "Attest")
REHEARSE = _step(STEPS, "Rehearse")
TESTS = _step(STEPS, "tests under this exact runtime")
APPLY = _step(STEPS, "Apply migration 0010")
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


# --------------------------------------------------------------------------- the apply workflow


def test_it_is_the_workflow_the_script_verifies_and_it_is_dispatch_only() -> None:
    assert PATH.is_file()
    assert trigger_keys(TEXT) == {"workflow_dispatch"}, "no schedule, no push: one owner dispatch"
    expected = TEXT.split("      expected_sha:", 1)[1].split("      confirm:", 1)[0]
    confirm = TEXT.split("      confirm:", 1)[1].split("permissions:", 1)[0]
    for block in (expected, confirm):
        assert "required: true" in block and "type: string" in block
        assert "default:" not in block
    assert apply_0010.CONFIRMATION in confirm


def test_it_can_never_run_beside_another_production_database_dispatch() -> None:
    assert _top_level_block(TEXT, "concurrency") == _top_level_block(EVALUATION_TEXT, "concurrency")
    assert "cancel-in-progress: false" in _top_level_block(TEXT, "concurrency")
    assert _top_level_block(TEXT, "permissions") == ["contents: read"]


def test_no_expression_is_ever_pasted_into_shell_source() -> None:
    assert len(RUN_STEPS) == 5, "the reader must find every run step, or the checks are vacuous"
    for step in RUN_STEPS:
        assert "${{" not in step.run, step.name
        assert "secrets." not in step.run, step.name
        assert step.shell == "bash", step.name
        assert not re.search(r"(?<!\|)\|(?!\|)", step.run), step.name
        occurrences = re.findall(r"\$\{?MIGRATION_0010_[A-Z_]+\}?", step.run)
        quoted = re.findall(r'="\$MIGRATION_0010_[A-Z_]+"', step.run)
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
        "MIGRATION_0010_EXPECTED_SHA": "${{ inputs.expected_sha }}",
        "MIGRATION_0010_CONFIRM": "${{ inputs.confirm }}",
    }
    assert ATTEST.env == {"MIGRATION_0010_EXPECTED_SHA": "${{ inputs.expected_sha }}"}
    assert REHEARSE.env == {"MIGRATION_0010_REHEARSAL_URL": REHEARSAL_URL}
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
        APPLY.index,
        UPLOAD.index,
    ]
    assert order == sorted(order) and len(set(order)) == len(STEPS)


def test_the_actions_runner_and_install_are_exactly_the_evaluation_s() -> None:
    uses = [step.uses for step in STEPS if step.uses]
    assert uses == [step.uses for step in EVALUATION_STEPS if step.uses]
    for reference in uses:
        assert re.fullmatch(r"actions/[a-z-]+@[0-9a-f]{40}", reference), reference
    setup = next(step for step in STEPS if step.uses and "actions/setup-python@" in step.uses)
    assert setup.with_ == {
        "python-version": provenance.PINNED_PYTHON_VERSION,
        "check-latest": "false",
    }
    assert apply_0010.PINNED_PYTHON == (
        provenance.PINNED_PYTHON_IMPLEMENTATION,
        provenance.PINNED_PYTHON_VERSION,
    )
    checkout = next(step for step in STEPS if step.uses and "actions/checkout@" in step.uses)
    assert checkout.with_ == {"persist-credentials": "false"}
    assert JOB.fields["runs-on"] == "ubuntu-24.04"
    assert INSTALL.run == _step(EVALUATION_STEPS, "hash-locked").run


def test_every_python_process_is_isolated_or_is_the_bytecode_free_test_run() -> None:
    for step in (ATTEST, APPLY):
        assert step.run.startswith(f"python -I -S -B {apply_0010.SCRIPT} "), step.name
    assert f"python -I -S -B {apply_0010.SCRIPT} --mode=rehearse" in REHEARSE.run
    for step in RUN_STEPS:
        assert "PYTHONPATH" not in step.run, step.name
        for match in re.finditer(r"\bpython\b(?P<rest>[^\n]*)", step.run):
            assert match.group("rest").startswith((" -I -S -B ", " -s -B -m pytest ")), step.name


def _rehearsal_lines(step: Step) -> list[str]:
    return step.run.strip().splitlines()


def test_the_rehearsal_builds_both_scratch_databases_from_the_real_migrations() -> None:
    lines = _rehearsal_lines(REHEARSE)
    assert lines[0] == "sudo systemctl start postgresql.service"
    assert lines[1] == (
        'sudo -u postgres psql -X -q -v ON_ERROR_STOP=1 -c "CREATE ROLE \\"$(id -un)\\" LOGIN"'
    )
    assert "SUPERUSER" not in REHEARSE.run, "the scratch owner is an ordinary login role"
    assert lines[2] == (
        "sudo -u postgres psql -X -q -v ON_ERROR_STOP=1 -f - < "
        f"{FIXTURES}/00_supabase_like_roles.sql"
    )
    for database, line in zip(("rehearsal", "rebuild"), lines[3:5], strict=True):
        assert line == f'sudo -u postgres createdb -O "$(id -un)" migration_0010_{database}'
    for database, line in zip(("rehearsal", "rebuild"), lines[5:7], strict=True):
        assert line == (
            'sudo -u postgres psql -X -q -v ON_ERROR_STOP=1 -v owner="$(id -un)" '
            f"-d migration_0010_{database} -f - < {FIXTURES}/01_supabase_like_grants.sql"
        )
    assert lines[7] == f'cat {MIGRATIONS_0001_0009} > "$RUNNER_TEMP/migrations_0001_0009.sql"'
    assert len(MIGRATIONS_0001_0009.split()) == 9
    psql = "psql -X -q -v ON_ERROR_STOP=1 -d"
    bundle = '"$RUNNER_TEMP/migrations_0001_0009.sql"'
    assert lines[8] == f"{psql} migration_0010_rehearsal -f - < {bundle}"
    assert lines[9] == (
        f"{psql} migration_0010_rehearsal -f - < {FIXTURES}/10_audited_production_state.sql"
    )
    assert "--mode=rehearse" in lines[10] and f"--report={REHEARSAL_REPORT}" in lines[10]
    assert lines[11] == f"{psql} migration_0010_rebuild -f - < {bundle}"
    assert lines[12] == f"{psql} migration_0010_rebuild -f - < {apply_0010.MIGRATION}"
    assert lines[13] == (
        f"{psql} migration_0010_rebuild -f - < {FIXTURES}/20_assert_rebuild_posture.sql"
    )
    assert len(lines) == 14
    assert "SUPABASE" not in REHEARSE.run
    for relative in (
        *MIGRATIONS_0001_0009.split(),
        apply_0010.MIGRATION,
        *(
            f"{FIXTURES}/{name}"
            for name in (
                "00_supabase_like_roles.sql",
                "01_supabase_like_grants.sql",
                "10_audited_production_state.sql",
                "20_assert_rebuild_posture.sql",
            )
        ),
    ):
        assert (ROOT / relative).is_file(), relative


def test_the_rehearsal_fixtures_hold_no_secret_and_state_what_they_build() -> None:
    fixtures = sorted((ROOT / FIXTURES).glob("*.sql"))
    assert [path.name for path in fixtures] == [
        "00_supabase_like_roles.sql",
        "01_supabase_like_grants.sql",
        "10_audited_production_state.sql",
        "20_assert_rebuild_posture.sql",
    ]
    for path in fixtures:
        text = path.read_text(encoding="utf-8")
        assert "PASSWORD" not in text.upper() and "postgresql://" not in text
        assert "Never run it against a real database" in text or "scratch local PostgreSQL" in text
    production = (ROOT / FIXTURES / "10_audited_production_state.sql").read_text(encoding="utf-8")
    for table in apply_0010.LEGACY_TABLES:
        assert f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY;" in production
    grants = (ROOT / FIXTURES / "01_supabase_like_grants.sql").read_text(encoding="utf-8")
    assert 'FOR ROLE :"owner" IN SCHEMA public' in grants
    assert "GRANT ALL ON TABLES TO anon, authenticated, service_role;" in grants
    assert "GRANT ALL ON SEQUENCES TO anon, authenticated, service_role;" in grants
    roles = (ROOT / FIXTURES / "00_supabase_like_roles.sql").read_text(encoding="utf-8")
    assert "CREATE ROLE service_role NOLOGIN NOINHERIT BYPASSRLS;" in roles
    assertion = (ROOT / FIXTURES / "20_assert_rebuild_posture.sql").read_text(encoding="utf-8")
    for table in apply_0010.LEGACY_TABLES:
        assert f"'{table}'" in assertion
    for _, _, sequence in apply_0010.LEGACY_SEQUENCES:
        assert f"'{sequence.removeprefix('public.')}'" in assertion
    assert assertion.count("RAISE EXCEPTION") == 5


def test_the_in_job_tests_cover_the_script_the_migration_and_this_boundary() -> None:
    command = TESTS.run.split()
    assert command[:7] == ["python", "-s", "-B", "-m", "pytest", "-q", "-p"]
    paths = [part for part in command if part.startswith("tests/")]
    assert paths == [
        "tests/scripts/test_apply_migration_0010.py",
        "tests/migrations/test_legacy_table_security_migration.py",
        "tests/workflows/test_apply_migration_0010_workflow.py",
        "tests/workflows/test_workflow_steps_reader.py",
    ]
    for path in paths:
        assert (ROOT / path).is_file(), path


def test_both_reports_are_uploaded_always() -> None:
    assert f"--report={REPORT}" in APPLY.run
    assert UPLOAD.fields.get("if") == "always()"
    assert UPLOAD.with_["path"].split() == [REPORT, REHEARSAL_REPORT]


def test_no_other_database_route_names_0010() -> None:
    for workflow in (
        provenance.SEAL_MIGRATION_WORKFLOW,
        provenance.EVALUATION_WORKFLOW,
        ".github/workflows/apply-migration-0008.yml",
        ".github/workflows/audit-table-privileges.yml",
    ):
        text = (ROOT / workflow).read_text(encoding="utf-8")
        assert "0010" not in text, workflow


@pytest.mark.parametrize("hostile", HOSTILE)
def test_hostile_inputs_reach_the_script_as_inert_arguments(tmp_path: Path, hostile: str) -> None:
    log = tmp_path / "calls.jsonl"
    bin_dir = tmp_path / "bin"
    install_stub(bin_dir, "python", log)
    contexts = _contexts(hostile)
    for step in (ATTEST, APPLY):
        completed = run_step(
            step, env=_environment(step, contexts), workdir=tmp_path, bin_dir=bin_dir
        )
        assert completed.returncode == 0, completed.stderr
    attest_call, apply_call = (call["argv"] for call in stub_calls(log))
    assert attest_call == [
        *ENTRYPOINT, "--mode=attest", f"--expected-sha={hostile}", f"--wheelhouse={WHEELHOUSE}"
    ]
    args = apply_0010.build_parser().parse_args(apply_call[len(ENTRYPOINT) :])
    assert args.mode == apply_0010.MODE_APPLY, "the mode is fixed in the workflow, never an input"
    assert args.expected_sha == hostile and args.confirm == hostile
    assert args.wheelhouse == WHEELHOUSE and args.report == REPORT
    assert not list(tmp_path.glob("INJECTED*")), "an input executed as a command"


@pytest.mark.parametrize("step", [ATTEST, APPLY, TESTS], ids=lambda step: step.name)
def test_a_failing_command_fails_its_step(tmp_path: Path, step: Step) -> None:
    install_stub(tmp_path / "bin", "python", tmp_path / "calls.jsonl")
    env = _environment(step, _contexts("value"), STUB_EXIT="2")
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
        apply_0010.SCRIPT,
        f"{FIXTURES}/**",
        apply_0010.WORKFLOW,
        apply_0010.REHEARSAL_WORKFLOW,
        "migrations/**",
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


def test_the_rehearsal_workflow_rehearses_exactly_like_the_apply_workflow() -> None:
    rehearse = _step(REHEARSAL_JOB.steps, "Rehearse")
    assert rehearse.env == REHEARSE.env
    ours = _rehearsal_lines(rehearse)
    theirs = _rehearsal_lines(REHEARSE)
    assert len(ours) == len(theirs)
    for index, (mine, apply_s) in enumerate(zip(ours, theirs, strict=True)):
        if index == 10:
            assert mine == (
                f"PYTHONPATH=src python {apply_0010.SCRIPT} --mode=rehearse "
                f"--report={REHEARSAL_REPORT}"
            )
        else:
            assert mine == apply_s, index
    upload = _step(REHEARSAL_JOB.steps, "Upload")
    assert upload.with_["path"] == REHEARSAL_REPORT and upload.fields.get("if") == "always()"
