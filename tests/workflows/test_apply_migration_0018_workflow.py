"""The migration-0018 workflow (D6), read and EXECUTED the way GitHub runs it.

It holds the production database secret, so it carries every guard the other database routes
earned: dispatch-only, the section 5A concurrency group, the evaluator's exact runtime, isolated
Python, inputs only through the environment, and the scratch PostgreSQL rehearsal inside the job
before the secret is handed out.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from crypto_probability_engine.oos.evaluation import provenance
from scripts import apply_migration_0018 as apply_0018
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
PATH = ROOT / apply_0018.WORKFLOW
TEXT = PATH.read_text(encoding="utf-8")
JOB = read_jobs(TEXT)["apply"]
STEPS = JOB.steps
RUN_STEPS = [step for step in STEPS if step.run is not None]

EVALUATION_TEXT = (ROOT / provenance.EVALUATION_WORKFLOW).read_text(encoding="utf-8")
EVALUATION_STEPS = read_jobs(EVALUATION_TEXT)["evaluate"].steps

ENTRYPOINT = ("-I", "-S", "-B", apply_0018.SCRIPT)
RUNNER_TEMP = "/home/runner/work/_temp"
WHEELHOUSE = f"{RUNNER_TEMP}/section-5a-wheels"
REPORT = "migration-0018-apply-report.json"
REHEARSAL_REPORT = "migration-0018-rehearsal-report.json"
REHEARSAL_URL = "postgresql:///migration_0018_rehearsal?host=/var/run/postgresql"
ROLES_FIXTURES = "scripts/migration_0013_rehearsal"
FIXTURES = "scripts/migration_0018_rehearsal"
AUTHENTICATOR_FIXTURES = "scripts/migration_0016_rehearsal"
FUNCTION_FIXTURES = "scripts/migration_0015_rehearsal"
# Migrations 0001-0017, explicit: the state production is in before 0018.
MIGRATIONS_0001_0017 = (
    "migrations/0001_init.sql",
    "migrations/0002_news.sql",
    "migrations/0003_prediction_ledger.sql",
    "migrations/0004_prediction_outcomes.sql",
    "migrations/0005_prediction_feature_snapshots.sql",
    "migrations/0006_prediction_derivatives_snapshots.sql",
    "migrations/0007_prediction_origin.sql",
    "migrations/0008_analysis_run_details.sql",
    "migrations/0009_section_5a_evaluation_seal.sql",
    "migrations/0010_legacy_table_security.sql",
    "migrations/0011_prediction_target_provenance.sql",
    "migrations/0012_prediction_resolution_status.sql",
    "migrations/0013_automation_radar_ledger.sql",
    "migrations/0014_core_evidence_invariants.sql",
    "migrations/0015_prediction_bundle_rpc.sql",
    "migrations/0016_least_privilege_roles.sql",
    "migrations/0017_forecast_bundle_rpc.sql",
)
IN_JOB_TESTS = [
    "tests/scripts/test_apply_migration_0018.py",
    "tests/migrations/test_narrow_service_role_migration.py",
    "tests/workflows/test_apply_migration_0018_workflow.py",
    "tests/workflows/test_workflow_steps_reader.py",
]

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
APPLY = _step(STEPS, "Apply migration 0018")
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


def _comment_header(text: str) -> str:
    """The first block of comment lines, joined into one line of prose."""

    lines = text.splitlines()
    start = next(index for index, line in enumerate(lines) if line.startswith(("#", "--")))
    block = []
    for line in lines[start:]:
        if not line.startswith(("#", "--")):
            break
        block.append(line.lstrip("#-").strip())
    return " ".join(part for part in block if part)


# --------------------------------------------------------------------------- the trigger


def test_it_is_the_workflow_the_script_verifies_and_it_is_dispatch_only() -> None:
    assert PATH.is_file()
    assert trigger_keys(TEXT) == {"workflow_dispatch"}, "no schedule, push or pull_request"
    code = [line for line in TEXT.splitlines() if not line.lstrip().startswith("#")]
    for trigger in ("pull_request", "push:", "schedule", "cron", "workflow_run", "workflow_call"):
        assert not any(trigger in line for line in code), trigger
    expected = TEXT.split("      expected_sha:", 1)[1].split("      confirm:", 1)[0]
    confirm = TEXT.split("      confirm:", 1)[1].split("permissions:", 1)[0]
    for block in (expected, confirm):
        assert "required: true" in block and "type: string" in block
        assert "default:" not in block
    assert f"description: REQUIRED. Exactly {apply_0018.CONFIRMATION}\n" in confirm


def test_its_header_says_what_the_route_checks_and_who_may_dispatch_it() -> None:
    header = _comment_header(TEXT)
    assert header.startswith("Dispatch-only."), header[:80]
    for phrase in (
        "Merging this workflow is the owner's T3",
        "Dispatching it is a T4",
        "one shot",
        "never rerun",
        "It is dispatched only after the D6 production inventory is clean (owner ruling D6:"
        " timing B;"
        " run 37149774863, expect=before, PASS) and migrations 0016 and 0017 are applied.",
        "The bulk scripts/apply_migrations.py is never used for 0018",
        "the applying role holds ADMIN on ucpe_bundle_owner (or SUPERUSER) and owns every table",
        "service_role holds exactly its pre-D6 privileges on the six core evidence tables, and D6's"
        " core-write inventory finds every write surface inside the revoke set and none outside it",
        "if service_role already holds only SELECT and EXECUTE on neither function, a second"
        " dispatch changes nothing",
        "service_role holds exactly SELECT on the six tables, and EXECUTE on neither bundle"
        " function",
        "D6's inventory finds no write surface at all",
        "both functions are otherwise unchanged, so their owner and the writer still execute them",
        "the memberships, the four roles' grants and policies and the F1/UOR grants included",
        "No application row is read or written.",
        "every other role name is withheld",
        "Only the apply step receives the database secret, and only after the owner approves the"
        " run in the protected Environment production-db-owner (C4).",
    ):
        assert phrase in header, phrase


def test_it_can_never_run_beside_another_production_database_dispatch() -> None:
    assert _top_level_block(TEXT, "concurrency") == _top_level_block(EVALUATION_TEXT, "concurrency")
    assert _top_level_block(TEXT, "concurrency") == [
        "group: section-5a-evaluation",
        "cancel-in-progress: false",
    ]
    assert _top_level_block(TEXT, "permissions") == ["contents: read"]


# --------------------------------------------------------------------------- the steps


def test_no_expression_is_ever_pasted_into_shell_source() -> None:
    assert len(RUN_STEPS) == 5, "the reader must find every run step, or the checks are vacuous"
    for step in RUN_STEPS:
        assert "${{" not in step.run, step.name
        assert "secrets." not in step.run, step.name
        assert step.shell == "bash", step.name
        assert not re.search(r"(?<!\|)\|(?!\|)", step.run), step.name
        occurrences = re.findall(r"\$\{?MIGRATION_0018_[A-Z_]+\}?", step.run)
        quoted = re.findall(r'="\$MIGRATION_0018_[A-Z_]+"', step.run)
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
        "MIGRATION_0018_EXPECTED_SHA": "${{ inputs.expected_sha }}",
        "MIGRATION_0018_CONFIRM": "${{ inputs.confirm }}",
    }
    assert ATTEST.env == {"MIGRATION_0018_EXPECTED_SHA": "${{ inputs.expected_sha }}"}
    assert REHEARSE.env == {apply_0018.REHEARSAL_URL_VARIABLE: REHEARSAL_URL}
    assert INSTALL.env == {}
    assert TESTS.env == {"PYTHONDONTWRITEBYTECODE": "1", "PYTHONNOUSERSITE": "1"}
    assert UPLOAD.env == {}


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
    assert order == sorted(order) and len(set(order)) == len(STEPS) == 8


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
    assert apply_0018.PINNED_PYTHON == (
        provenance.PINNED_PYTHON_IMPLEMENTATION,
        provenance.PINNED_PYTHON_VERSION,
    )
    checkout = next(step for step in STEPS if step.uses and "actions/checkout@" in step.uses)
    assert checkout.with_ == {"persist-credentials": "false"}
    assert JOB.fields["runs-on"] == "ubuntu-24.04"
    assert JOB.fields["timeout-minutes"] == "20"
    assert INSTALL.run == _step(EVALUATION_STEPS, "hash-locked").run


def test_every_python_process_is_isolated_or_is_the_bytecode_free_test_run() -> None:
    for step in (ATTEST, APPLY):
        assert step.run.startswith(f"python -I -S -B {apply_0018.SCRIPT} "), step.name
    assert f"python -I -S -B {apply_0018.SCRIPT} --mode=rehearse" in REHEARSE.run
    for step in RUN_STEPS:
        assert "PYTHONPATH" not in step.run, step.name
        for match in re.finditer(r"\bpython\b(?P<rest>[^\n]*)", step.run):
            assert match.group("rest").startswith((" -I -S -B ", " -s -B -m pytest ")), step.name


# --------------------------------------------------------------------------- the rehearsal


PSQL = "psql -X -q -v ON_ERROR_STOP=1 -d"
BUNDLE = '"$RUNNER_TEMP/migrations_0001_0017.sql"'
REHEARSAL_LINES = [
    "sudo systemctl start postgresql.service",
    'sudo -u postgres psql -X -q -v ON_ERROR_STOP=1 -c "CREATE ROLE \\"$(id -un)\\" LOGIN"',
    "sudo -u postgres psql -X -q -v ON_ERROR_STOP=1 -f - < "
    f"{ROLES_FIXTURES}/00_supabase_like_roles.sql",
    'sudo -u postgres psql -X -q -v ON_ERROR_STOP=1 -v owner="$(id -un)" -f - < '
    f"{AUTHENTICATOR_FIXTURES}/00_supabase_like_authenticator.sql",
    'sudo -u postgres createdb -O "$(id -un)" migration_0018_rehearsal',
    'sudo -u postgres psql -X -q -v ON_ERROR_STOP=1 -v owner="$(id -un)" '
    f"-d migration_0018_rehearsal -f - < {ROLES_FIXTURES}/01_supabase_like_grants.sql",
    'sudo -u postgres psql -X -q -v ON_ERROR_STOP=1 -v owner="$(id -un)" '
    f"-d migration_0018_rehearsal -f - < {FUNCTION_FIXTURES}/00_supabase_like_function_grants.sql",
    f"cat {' '.join(MIGRATIONS_0001_0017)} > {BUNDLE}",
    f"{PSQL} migration_0018_rehearsal -f - < {BUNDLE}",
    f"python -I -S -B {apply_0018.SCRIPT} --mode=rehearse "
    f'--wheelhouse="$RUNNER_TEMP/section-5a-wheels" --report={REHEARSAL_REPORT}',
    f"{PSQL} migration_0018_rehearsal -f - < {FIXTURES}/10_probe.sql",
]
STDIN_FILES = (
    f"{ROLES_FIXTURES}/00_supabase_like_roles.sql",
    f"{AUTHENTICATOR_FIXTURES}/00_supabase_like_authenticator.sql",
    f"{ROLES_FIXTURES}/01_supabase_like_grants.sql",
    f"{FUNCTION_FIXTURES}/00_supabase_like_function_grants.sql",
    f"{FIXTURES}/10_probe.sql",
)


def test_the_rehearsal_builds_its_scratch_database_from_the_real_migrations() -> None:
    assert REHEARSE.run.strip().splitlines() == REHEARSAL_LINES
    assert "SUPERUSER" not in REHEARSE.run, "the scratch owner is an ordinary login role"
    assert "SUPABASE" not in REHEARSE.run
    # Roles are cluster-wide: a second scratch database would see the roles 0016 created.
    assert REHEARSE.run.count("createdb") == 1
    for relative in (*MIGRATIONS_0001_0017, *STDIN_FILES):
        assert (ROOT / relative).is_file(), relative


def test_the_bundle_is_every_migration_before_0018_in_order() -> None:
    earlier = sorted(
        path.relative_to(ROOT).as_posix()
        for path in (ROOT / "migrations").glob("*.sql")
        if path.name < "0018"
    )
    assert list(MIGRATIONS_0001_0017) == earlier and len(earlier) == 17


def test_the_rehearse_step_runs_every_command_in_order_and_fails_closed(tmp_path: Path) -> None:
    """Executed as GitHub runs it, with every command it calls replaced by a recording stub."""

    commands = {line.split()[0] for line in REHEARSAL_LINES}
    commands |= set(re.findall(r"\$\((\w+)", REHEARSE.run))
    assert commands == {"sudo", "cat", "psql", "python", "id"}, "nothing real may run"
    for relative in STDIN_FILES:
        (tmp_path / relative).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / relative).write_text("-- placeholder: the stubs never read it\n")
    log = tmp_path / "calls.jsonl"
    for command in sorted(commands):
        install_stub(tmp_path / "bin", command, log)
    env = _environment(REHEARSE, {}, RUNNER_TEMP=str(tmp_path), STUB_STDOUT="runner")
    completed = run_step(REHEARSE, env=env, workdir=tmp_path, bin_dir=tmp_path / "bin")
    assert completed.returncode == 0, completed.stderr

    psql = ["-X", "-q", "-v", "ON_ERROR_STOP=1"]
    as_postgres = ["-u", "postgres"]
    rehearsal = [*psql, "-d", "migration_0018_rehearsal", "-f", "-"]
    calls = [call["argv"] for call in stub_calls(log)]
    assert calls == [
        ["systemctl", "start", "postgresql.service"],
        ["-un"],
        [*as_postgres, "psql", *psql, "-c", 'CREATE ROLE "runner" LOGIN'],
        [*as_postgres, "psql", *psql, "-f", "-"],
        ["-un"],
        [*as_postgres, "psql", *psql, "-v", "owner=runner", "-f", "-"],
        ["-un"],
        [*as_postgres, "createdb", "-O", "runner", "migration_0018_rehearsal"],
        ["-un"],
        [
            *as_postgres,
            "psql",
            *psql,
            "-v",
            "owner=runner",
            "-d",
            "migration_0018_rehearsal",
            "-f",
            "-",
        ],
        ["-un"],
        [
            *as_postgres,
            "psql",
            *psql,
            "-v",
            "owner=runner",
            "-d",
            "migration_0018_rehearsal",
            "-f",
            "-",
        ],
        list(MIGRATIONS_0001_0017),
        rehearsal,
        [
            *ENTRYPOINT,
            "--mode=rehearse",
            f"--wheelhouse={tmp_path}/section-5a-wheels",
            f"--report={REHEARSAL_REPORT}",
        ],
        rehearsal,
    ]

    log.unlink()
    failing = {**env, "STUB_EXIT": "3"}
    completed = run_step(REHEARSE, env=failing, workdir=tmp_path, bin_dir=tmp_path / "bin")
    assert completed.returncode == 3, "the first failing command fails the step"
    first = ["systemctl", "start", "postgresql.service"]
    assert [call["argv"] for call in stub_calls(log)] == [first], "and nothing after it runs"


# --------------------------------------------------------------------------- the fixtures


def test_the_probe_holds_no_secret_and_states_where_it_runs() -> None:
    text = (ROOT / FIXTURES / "10_probe.sql").read_text(encoding="utf-8")
    assert "PASSWORD" not in text.upper() and "postgresql://" not in text
    assert "SUPABASE_DB_URL" not in text and "secrets." not in text
    header = _comment_header(text)
    assert "Migration 0018 rehearsal" in header
    assert "Runs ONLY in a scratch local PostgreSQL on a CI runner" in header
    assert "Never run it against a real database." in header


def test_the_probe_asserts_d6_s_result_and_what_must_not_move() -> None:
    text = (ROOT / FIXTURES / "10_probe.sql").read_text(encoding="utf-8")
    for phrase in (
        "core CONSTANT text[] := ARRAY['analysis_runs', 'analysis_run_details', 'predictions',",
        "'prediction_feature_snapshots', 'prediction_derivatives_snapshots',"
        " 'prediction_outcomes']",
        "writes CONSTANT text[] := ARRAY['INSERT', 'UPDATE', 'DELETE', 'TRUNCATE', 'REFERENCES',"
        " 'TRIGGER']",
        "IF NOT pg_catalog.has_table_privilege('service_role', 'public.' || table_name, 'SELECT')",
        "IF pg_catalog.has_table_privilege('service_role', 'public.' || table_name, privilege)",
        "'service_role', 'public.' || table_name, 'INSERT, UPDATE, REFERENCES')",
        "IF pg_catalog.has_function_privilege('service_role', bundle, 'EXECUTE')",
        "OR pg_catalog.has_function_privilege('service_role', wide, 'EXECUTE')",
        "IF NOT pg_catalog.has_function_privilege('ucpe_api_writer', bundle, 'EXECUTE')",
        "OR NOT pg_catalog.has_function_privilege('ucpe_bundle_owner', wide, 'EXECUTE')",
        "IF pg_catalog.pg_has_role(current_user, 'ucpe_bundle_owner', 'USAGE')",
        "OR pg_catalog.has_table_privilege('ucpe_api_writer', 'public.predictions', 'INSERT')",
        "::name[]) <> 44",
        "IF NOT pg_catalog.has_table_privilege('service_role', 'public.watchlist', 'INSERT')",
    ):
        assert phrase in text, phrase


def test_the_in_job_tests_cover_the_script_the_migration_and_this_boundary() -> None:
    command = TESTS.run.split()
    assert command[:7] == ["python", "-s", "-B", "-m", "pytest", "-q", "-p"]
    assert command[7] == "no:cacheprovider"
    paths = [part for part in command if part.startswith("tests/")]
    assert paths == IN_JOB_TESTS and len(command) == 8 + len(IN_JOB_TESTS)
    for path in paths:
        assert (ROOT / path).is_file(), path


def test_both_reports_are_uploaded_always() -> None:
    assert f"--report={REPORT}" in APPLY.run
    assert f"--report={REHEARSAL_REPORT}" in REHEARSE.run
    assert UPLOAD.fields.get("if") == "always()"
    assert UPLOAD.with_["path"].split() == [REPORT, REHEARSAL_REPORT]
    assert UPLOAD.with_["if-no-files-found"] == "warn"


# --------------------------------------------------------------------------- executed


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
        *ENTRYPOINT,
        "--mode=attest",
        f"--expected-sha={hostile}",
        f"--wheelhouse={WHEELHOUSE}",
    ]
    args = apply_0018.build_parser().parse_args(apply_call[len(ENTRYPOINT) :])
    assert args.mode == apply_0018.MODE_APPLY, "the mode is fixed in the workflow, never an input"
    assert args.expected_sha == hostile and args.confirm == hostile
    assert args.wheelhouse == WHEELHOUSE and args.report == REPORT
    assert not list(tmp_path.glob("INJECTED*")), "an input executed as a command"


@pytest.mark.parametrize("step", [ATTEST, APPLY, TESTS], ids=lambda step: step.name)
def test_a_failing_command_fails_its_step(tmp_path: Path, step: Step) -> None:
    install_stub(tmp_path / "bin", "python", tmp_path / "calls.jsonl")
    env = _environment(step, _contexts("value"), STUB_EXIT="2")
    completed = run_step(step, env=env, workdir=tmp_path, bin_dir=tmp_path / "bin")
    assert completed.returncode == 2, (step.name, completed.stderr)
