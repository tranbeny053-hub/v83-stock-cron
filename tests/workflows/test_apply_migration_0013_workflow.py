"""The migration-0013 workflows, read and EXECUTED the way GitHub runs them.

The dispatch workflow holds the production database secret, so it carries every guard the other
database routes earned, and rehearses the apply on scratch PostgreSQL before the secret is handed
to any step. The pull-request rehearsal workflow proves the same apply, and the application's own
registry and ledger SQL, on a real PostgreSQL before the route can merge; it holds no secret.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from crypto_probability_engine.oos.evaluation import provenance
from scripts import apply_migration_0011 as apply_0011
from scripts import apply_migration_0012 as apply_0012
from scripts import apply_migration_0013 as route
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
PATH = ROOT / route.WORKFLOW
TEXT = PATH.read_text(encoding="utf-8")
JOB = read_jobs(TEXT)["apply"]
STEPS = JOB.steps
RUN_STEPS = [step for step in STEPS if step.run is not None]
REHEARSAL_PATH = ROOT / ".github/workflows/apply-migration-0013-rehearsal.yml"
REHEARSAL_TEXT = REHEARSAL_PATH.read_text(encoding="utf-8")
REHEARSAL_JOB = read_jobs(REHEARSAL_TEXT)["test"]
PRECEDENT_TEXT = (ROOT / apply_0012.WORKFLOW).read_text(encoding="utf-8")
PRECEDENT_STEPS = read_jobs(PRECEDENT_TEXT)["apply"].steps

ENTRYPOINT = ("-I", "-S", "-B", route.SCRIPT)
PROBE = "scripts/migration_0013_rehearsal/probe_app_sql.py"
RUNNER_TEMP = "/home/runner/work/_temp"
WHEELHOUSE = f"{RUNNER_TEMP}/section-5a-wheels"
REPORTS = (
    "migration-0013-apply-report.json",
    "migration-0013-rehearsal-report.json",
    "migration-0013-rebuild-report.json",
)
FIXTURES = "scripts/migration_0013_rehearsal"
FIXTURE_NAMES = (
    "00_supabase_like_roles.sql",
    "01_supabase_like_grants.sql",
    "20_assert_api_roles_refused.sql",
    "probe_app_sql.py",
)
MIGRATIONS_0001_0010 = tuple(
    sorted(
        path.relative_to(ROOT).as_posix()
        for path in (ROOT / "migrations").glob("*.sql")
        if path.name < "0011"
    )
)
IN_JOB_TESTS = [
    "tests/scripts/test_apply_migration_0013.py",
    "tests/migrations/test_automation_radar_ledger_migration.py",
    "tests/workflows/test_apply_migration_0013_workflow.py",
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
)


def _step(steps, fragment: str) -> Step:
    matches = [step for step in steps if step.name and fragment in step.name]
    assert len(matches) == 1, (fragment, [step.name for step in steps])
    return matches[0]


INSTALL = _step(STEPS, "hash-locked")
ATTEST = _step(STEPS, "Attest")
REHEARSE = _step(STEPS, "Rehearse")
TESTS = _step(STEPS, "tests under this exact runtime")
APPLY = _step(STEPS, "Apply migration 0013")
UPLOAD = _step(STEPS, "Upload")
PR_REHEARSE = _step(REHEARSAL_JOB.steps, "Rehearse")


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
    lines = text.splitlines()
    start = next(index for index, line in enumerate(lines) if line.startswith(("#", "--")))
    block = []
    for line in lines[start:]:
        if not line.startswith(("#", "--")):
            break
        block.append(line.lstrip("#-").strip())
    return " ".join(part for part in block if part)


def _lines(step: Step) -> list[str]:
    return step.run.strip().splitlines()


# --------------------------------------------------------------------------- the dispatch workflow


def test_it_is_the_workflow_the_script_verifies_and_it_is_dispatch_only() -> None:
    assert trigger_keys(TEXT) == {"workflow_dispatch"}, "no schedule, push or pull_request"
    code = [line for line in TEXT.splitlines() if not line.lstrip().startswith("#")]
    for trigger in ("pull_request", "push:", "schedule", "cron", "workflow_run", "workflow_call"):
        assert not any(trigger in line for line in code), trigger
    expected = TEXT.split("      expected_sha:", 1)[1].split("      confirm:", 1)[0]
    confirm = TEXT.split("      confirm:", 1)[1].split("permissions:", 1)[0]
    for block in (expected, confirm):
        assert "required: true" in block and "type: string" in block
        assert "default:" not in block
    assert f"description: REQUIRED. Exactly {route.CONFIRMATION}\n" in confirm


def test_its_header_says_it_is_a_dispatch_only_draft_and_what_the_route_checks() -> None:
    header = _comment_header(TEXT)
    assert header.startswith("DRAFT: dispatch-only"), header[:80]
    for phrase in (
        "Merging this workflow is the owner's T3",
        "Dispatching it is a T4",
        "one shot",
        "never rerun",
        "The bulk scripts/apply_migrations.py is never used for 0013",
        "no foreign key in or out, no trigger and no row",
        "No existing application row is read",
        "built from migrations 0001-0012, the state production is expected to be in",
        "from migrations 0001-0010 alone must take the same apply by itself",
        "Only the apply step receives the database secret.",
    ):
        assert phrase in header, phrase


def test_it_can_never_run_beside_another_production_database_dispatch() -> None:
    assert _top_level_block(TEXT, "concurrency") == _top_level_block(PRECEDENT_TEXT, "concurrency")
    assert _top_level_block(TEXT, "concurrency") == [
        "group: section-5a-evaluation",
        "cancel-in-progress: false",
    ]
    assert _top_level_block(TEXT, "permissions") == ["contents: read"]


def test_no_expression_is_ever_pasted_into_shell_source() -> None:
    assert len(RUN_STEPS) == 5, "the reader must find every run step, or the checks are vacuous"
    for step in RUN_STEPS:
        assert "${{" not in step.run, step.name
        assert "secrets." not in step.run, step.name
        assert step.shell == "bash", step.name
        assert not re.search(r"(?<!\|)\|(?!\|)", step.run), step.name
        occurrences = re.findall(r"\$\{?MIGRATION_0013_(?:EXPECTED_SHA|CONFIRM)\}?", step.run)
        quoted = re.findall(r'="\$MIGRATION_0013_(?:EXPECTED_SHA|CONFIRM)"', step.run)
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
        "MIGRATION_0013_EXPECTED_SHA": "${{ inputs.expected_sha }}",
        "MIGRATION_0013_CONFIRM": "${{ inputs.confirm }}",
    }
    assert ATTEST.env == {"MIGRATION_0013_EXPECTED_SHA": "${{ inputs.expected_sha }}"}
    assert REHEARSE.env == {"PYTHONDONTWRITEBYTECODE": "1", "PYTHONNOUSERSITE": "1"}
    assert TESTS.env == {"PYTHONDONTWRITEBYTECODE": "1", "PYTHONNOUSERSITE": "1"}
    assert INSTALL.env == {} and UPLOAD.env == {}


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


def test_the_actions_runner_and_install_are_exactly_0012_s() -> None:
    assert [s.uses for s in STEPS if s.uses] == [s.uses for s in PRECEDENT_STEPS if s.uses]
    setup = next(step for step in STEPS if step.uses and "actions/setup-python@" in step.uses)
    assert setup.with_ == {
        "python-version": provenance.PINNED_PYTHON_VERSION,
        "check-latest": "false",
    }
    checkout = next(step for step in STEPS if step.uses and "actions/checkout@" in step.uses)
    assert checkout.with_ == {"persist-credentials": "false"}
    assert JOB.fields["runs-on"] == "ubuntu-24.04"
    assert JOB.fields["timeout-minutes"] == "20"
    assert INSTALL.run == _step(PRECEDENT_STEPS, "hash-locked").run


def test_every_python_process_is_isolated_or_bytecode_free() -> None:
    for step in (ATTEST, APPLY):
        assert step.run.startswith(f"python -I -S -B {route.SCRIPT} "), step.name
    for step in RUN_STEPS:
        assert "PYTHONPATH" not in step.run, step.name
        for match in re.finditer(r"\bpython\b(?P<rest>[^\n]*)", step.run):
            rest = match.group("rest")
            assert rest.startswith((" -I -S -B ", f" -s -B {PROBE}", " -s -B -m pytest ")), (
                step.name,
                rest,
            )


def test_the_rehearsal_builds_both_scratch_databases_then_applies_refuses_and_probes() -> None:
    lines = _lines(REHEARSE)
    psql = "psql -X -q -v ON_ERROR_STOP=1 -d"
    bundle = '"$RUNNER_TEMP/migrations_0001_0010.sql"'
    url = 'MIGRATION_0013_REHEARSAL_URL="postgresql:///migration_0013_{}?host=/var/run/postgresql"'
    as_postgres = "sudo -u postgres psql -X -q -v ON_ERROR_STOP=1 -d"
    assert lines == [
        "sudo systemctl start postgresql.service",
        'sudo -u postgres psql -X -q -v ON_ERROR_STOP=1 -c "CREATE ROLE \\"$(id -un)\\" LOGIN"',
        "sudo -u postgres psql -X -q -v ON_ERROR_STOP=1 -f - < "
        f"{FIXTURES}/00_supabase_like_roles.sql",
        'sudo -u postgres createdb -O "$(id -un)" migration_0013_rehearsal',
        'sudo -u postgres createdb -O "$(id -un)" migration_0013_rebuild',
        'sudo -u postgres psql -X -q -v ON_ERROR_STOP=1 -v owner="$(id -un)" '
        f"-d migration_0013_rehearsal -f - < {FIXTURES}/01_supabase_like_grants.sql",
        'sudo -u postgres psql -X -q -v ON_ERROR_STOP=1 -v owner="$(id -un)" '
        f"-d migration_0013_rebuild -f - < {FIXTURES}/01_supabase_like_grants.sql",
        f"cat {' '.join(MIGRATIONS_0001_0010)} > {bundle}",
        f"{psql} migration_0013_rehearsal -f - < {bundle}",
        f"{psql} migration_0013_rehearsal -f - < {apply_0011.MIGRATION}",
        f"{psql} migration_0013_rehearsal -f - < {apply_0012.MIGRATION}",
        f"{url.format('rehearsal')} python -I -S -B {route.SCRIPT} --mode=rehearse "
        '--wheelhouse="$RUNNER_TEMP/section-5a-wheels" '
        "--report=migration-0013-rehearsal-report.json",
        f"{as_postgres} migration_0013_rehearsal -f - < {FIXTURES}/20_assert_api_roles_refused.sql",
        f"{url.format('rehearsal')} python -s -B {PROBE}",
        f"{psql} migration_0013_rebuild -f - < {bundle}",
        f"{url.format('rebuild')} python -I -S -B {route.SCRIPT} --mode=rehearse "
        '--wheelhouse="$RUNNER_TEMP/section-5a-wheels" '
        "--report=migration-0013-rebuild-report.json",
        f"{as_postgres} migration_0013_rebuild -f - < {FIXTURES}/20_assert_api_roles_refused.sql",
    ]
    assert len(MIGRATIONS_0001_0010) == 10
    rebuild = [line for line in lines if "migration_0013_rebuild" in line]
    assert not any("0011_" in line or "0012_" in line for line in rebuild), (
        "the rebuild never carries 0011 or 0012, which proves 0013 needs nothing from them"
    )
    assert "SUPERUSER" not in REHEARSE.run and "SUPABASE" not in REHEARSE.run
    for relative in (apply_0011.MIGRATION, apply_0012.MIGRATION, route.MIGRATION):
        assert (ROOT / relative).is_file(), relative


def test_the_rehearse_step_runs_every_command_in_order_and_fails_closed(tmp_path: Path) -> None:
    """Executed as GitHub runs it, with every command it calls replaced by a recording stub."""

    commands = {
        line.split()[1] if line.startswith("MIGRATION_0013_REHEARSAL_URL=") else line.split()[0]
        for line in _lines(REHEARSE)
    }
    commands |= set(re.findall(r"\$\((\w+)", REHEARSE.run))
    assert commands == {"sudo", "cat", "psql", "python", "id"}, "nothing real may run"
    for relative in (
        apply_0011.MIGRATION,
        apply_0012.MIGRATION,
        *(f"{FIXTURES}/{name}" for name in FIXTURE_NAMES),
    ):
        (tmp_path / relative).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / relative).write_text("-- placeholder: the stubs never read it\n")
    log = tmp_path / "calls.jsonl"
    for command in sorted(commands):
        install_stub(tmp_path / "bin", command, log)
    env = _environment(REHEARSE, {}, RUNNER_TEMP=str(tmp_path), STUB_STDOUT="runner")
    completed = run_step(REHEARSE, env=env, workdir=tmp_path, bin_dir=tmp_path / "bin")
    assert completed.returncode == 0, completed.stderr
    calls = [call["argv"] for call in stub_calls(log)]
    python_calls = [argv for argv in calls if argv and argv[0] in ("-I", "-s")]
    assert python_calls == [
        [
            *ENTRYPOINT,
            "--mode=rehearse",
            f"--wheelhouse={tmp_path}/section-5a-wheels",
            "--report=migration-0013-rehearsal-report.json",
        ],
        ["-s", "-B", PROBE],
        [
            *ENTRYPOINT,
            "--mode=rehearse",
            f"--wheelhouse={tmp_path}/section-5a-wheels",
            "--report=migration-0013-rebuild-report.json",
        ],
    ]
    log.unlink()
    failing = {**env, "STUB_EXIT": "3"}
    completed = run_step(REHEARSE, env=failing, workdir=tmp_path, bin_dir=tmp_path / "bin")
    assert completed.returncode == 3, "the first failing command fails the step"
    assert [call["argv"] for call in stub_calls(log)] == [
        ["systemctl", "start", "postgresql.service"]
    ], "and nothing after it runs"


def test_the_in_job_tests_cover_the_script_the_migration_and_this_boundary() -> None:
    assert TESTS.run == ("python -s -B -m pytest -q -p no:cacheprovider " + " ".join(IN_JOB_TESTS))
    for relative in IN_JOB_TESTS:
        assert (ROOT / relative).is_file(), relative


def test_every_report_is_uploaded_always() -> None:
    assert UPLOAD.fields.get("if") == "always()"
    assert UPLOAD.with_["path"].split() == list(REPORTS)
    assert UPLOAD.with_["if-no-files-found"] == "warn"
    assert "--report=migration-0013-apply-report.json" in APPLY.run


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
    args = route.build_parser().parse_args(apply_call[len(ENTRYPOINT) :])
    assert args.mode == route.MODE_APPLY, "the mode is fixed in the workflow, never an input"
    assert args.expected_sha == hostile and args.confirm == hostile
    assert args.wheelhouse == WHEELHOUSE and args.report == REPORTS[0]
    assert not list(tmp_path.glob("INJECTED*")), "an input executed as a command"


@pytest.mark.parametrize("step", [ATTEST, APPLY, TESTS], ids=lambda step: step.name)
def test_a_failing_command_fails_its_step(tmp_path: Path, step: Step) -> None:
    install_stub(tmp_path / "bin", "python", tmp_path / "calls.jsonl")
    env = _environment(step, _contexts("value"), STUB_EXIT="2")
    completed = run_step(step, env=env, workdir=tmp_path, bin_dir=tmp_path / "bin")
    assert completed.returncode == 2, (step.name, completed.stderr)


# --------------------------------------------------------------------------- the fixtures


def test_the_rehearsal_fixtures_hold_no_secret_and_state_where_they_run() -> None:
    fixtures = sorted((ROOT / FIXTURES).glob("*"))
    assert [path.name for path in fixtures] == list(FIXTURE_NAMES)
    for path in fixtures:
        text = path.read_text(encoding="utf-8")
        assert "PASSWORD" not in text.upper(), path.name
        assert not re.search(r"postgresql://[^/]", text), "only local unix-socket URLs"
        assert "SUPABASE_DB_URL" not in text or path.suffix == ".py", path.name
        assert "secrets." not in text, path.name
        assert "Runs ONLY in a scratch local PostgreSQL on a CI runner" in " ".join(text.split())
        assert "Never run it against a real database." in text, path.name


def test_the_role_and_grant_fixtures_are_0012_s_statements() -> None:
    def statements(text: str) -> list[str]:
        return [line for line in text.splitlines() if line.strip() and not line.startswith("--")]

    for name in ("00_supabase_like_roles.sql", "01_supabase_like_grants.sql"):
        precedent = (ROOT / "scripts/migration_0012_rehearsal" / name).read_text(encoding="utf-8")
        mine = (ROOT / FIXTURES / name).read_text(encoding="utf-8")
        assert statements(mine) == statements(precedent), name


def test_the_api_role_assertion_probes_every_role_on_both_tables() -> None:
    text = (ROOT / FIXTURES / "20_assert_api_roles_refused.sql").read_text(encoding="utf-8")
    assert "ARRAY['anon', 'authenticated', 'service_role']" in text
    assert "WHEN insufficient_privilege THEN" in text
    assert "IF probes_run <> 33 THEN" in text
    probes = re.findall(r"^      '(SELECT|INSERT|UPDATE|DELETE|TRUNCATE)", text, re.M)
    assert len(probes) * 3 == 33
    for table in route.TABLES:
        for verb in ("SELECT", "INSERT INTO", "UPDATE", "DELETE FROM", "TRUNCATE"):
            assert re.search(rf"{verb}[^']*public\.{table}", text), (verb, table)


def test_the_probe_refuses_anything_but_a_local_socket_and_the_production_secret() -> None:
    text = (ROOT / PROBE).read_text(encoding="utf-8")
    assert (
        '_LOCAL_SOCKET_URL = re.compile(r"postgresql:///[a-z_][a-z0-9_]*\\?host=/var/run/postgresql")'
        in text
    )
    assert 'if os.environ.get("SUPABASE_DB_URL"):' in text
    for driven in ("PostgresCredentialRegistry", "PostgresAutomationLedger", "authenticate"):
        assert driven in text, driven


# --------------------------------------------------------------------------- the PR rehearsal


def test_the_pr_rehearsal_runs_on_pull_requests_touching_the_route_and_holds_no_secret() -> None:
    assert trigger_keys(REHEARSAL_TEXT) == {"pull_request"}
    paths = REHEARSAL_TEXT.split("    paths:\n", 1)[1].split("\npermissions:", 1)[0]
    assert [line.strip()[2:] for line in paths.splitlines() if line.strip()] == [
        route.SCRIPT,
        f"{FIXTURES}/**",
        route.WORKFLOW,
        ".github/workflows/apply-migration-0013-rehearsal.yml",
        "migrations/**",
        "src/crypto_probability_engine/automation/**",
    ]
    assert "secrets." not in REHEARSAL_TEXT and "SUPABASE_DB_URL" not in REHEARSAL_TEXT
    assert "workflow_dispatch" not in REHEARSAL_TEXT
    assert _top_level_block(REHEARSAL_TEXT, "permissions") == ["contents: read"]
    assert list(read_jobs(REHEARSAL_TEXT)) == ["test"], "named so the merge procedure waits on it"


def test_the_pr_rehearsal_runs_the_same_rehearsal_without_the_locked_runtime() -> None:
    uses = [step.uses for step in REHEARSAL_JOB.steps if step.uses]
    assert uses == [s.uses for s in STEPS if s.uses]
    mine = [
        line.replace(" PYTHONPATH=src python ", " python -I -S -B ")
        .replace(
            " python scripts/migration_0013_rehearsal",
            " python -s -B scripts/migration_0013_rehearsal",
        )
        .replace(
            "--mode=rehearse --report",
            '--mode=rehearse --wheelhouse="$RUNNER_TEMP/section-5a-wheels" --report',
        )
        for line in _lines(PR_REHEARSE)
    ]
    assert mine == _lines(REHEARSE)
    assert PR_REHEARSE.shell == "bash" and "${{" not in PR_REHEARSE.run
