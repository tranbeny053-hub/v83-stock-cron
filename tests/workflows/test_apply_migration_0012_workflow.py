"""The migration-0012 workflow, read and EXECUTED the way GitHub runs it.

It holds the production database secret, so it carries every guard the other database routes
earned. It is dispatch-only (owner ruling): there is no pull-request rehearsal workflow, so the
scratch PostgreSQL rehearsal runs inside the dispatch job itself, before the secret is handed out.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from crypto_probability_engine.oos.evaluation import provenance
from scripts import apply_migration_0011 as apply_0011
from scripts import apply_migration_0012 as apply_0012
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
PATH = ROOT / apply_0012.WORKFLOW
TEXT = PATH.read_text(encoding="utf-8")
JOB = read_jobs(TEXT)["apply"]
STEPS = JOB.steps
RUN_STEPS = [step for step in STEPS if step.run is not None]

EVALUATION_TEXT = (ROOT / provenance.EVALUATION_WORKFLOW).read_text(encoding="utf-8")
EVALUATION_STEPS = read_jobs(EVALUATION_TEXT)["evaluate"].steps

ENTRYPOINT = ("-I", "-S", "-B", apply_0012.SCRIPT)
RUNNER_TEMP = "/home/runner/work/_temp"
WHEELHOUSE = f"{RUNNER_TEMP}/section-5a-wheels"
REPORT = "migration-0012-apply-report.json"
REHEARSAL_REPORT = "migration-0012-rehearsal-report.json"
REHEARSAL_URL = "postgresql:///migration_0012_rehearsal?host=/var/run/postgresql"
FIXTURES = "scripts/migration_0012_rehearsal"
FIXTURE_NAMES = (
    "00_supabase_like_roles.sql",
    "01_supabase_like_grants.sql",
    "20_assert_status_table.sql",
)
# Migrations 0001-0010, explicit. With 0011 on top they are the state production is expected to be
# in when 0012 is applied.
MIGRATIONS_0001_0010 = (
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
)
IN_JOB_TESTS = [
    "tests/scripts/test_apply_migration_0012.py",
    "tests/migrations/test_prediction_resolution_status_migration.py",
    "tests/workflows/test_apply_migration_0012_workflow.py",
    "tests/workflows/test_workflow_steps_reader.py",
]
# Every other workflow that reaches a database, named explicitly, never globbed.
OTHER_DATABASE_WORKFLOWS = (
    ".github/workflows/section-5a-apply-seal-migration.yml",
    ".github/workflows/section-5a-evaluation.yml",
    ".github/workflows/apply-migration-0008.yml",
    ".github/workflows/apply-migration-0010.yml",
    ".github/workflows/apply-migration-0010-rehearsal.yml",
    ".github/workflows/apply-migration-0011.yml",
    ".github/workflows/audit-table-privileges.yml",
    ".github/workflows/audit-table-privileges-rehearsal.yml",
    ".github/workflows/resolve-outcomes.yml",
    ".github/workflows/oos-pair-evidence.yml",
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
APPLY = _step(STEPS, "Apply migration 0012")
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
    assert f"description: REQUIRED. Exactly {apply_0012.CONFIRMATION}\n" in confirm


def test_its_header_says_it_is_a_dispatch_only_draft_and_what_the_route_checks() -> None:
    header = _comment_header(TEXT)
    assert header.startswith("DRAFT: dispatch-only"), header[:80]
    for phrase in (
        "Merging this workflow is the owner's T3",
        "Dispatching it is a T4",
        "one shot",
        "never rerun",
        "no relation of any kind named prediction_resolution_status",
        "exactly its thirteen columns, nine validated constraints and two indexes",
        "no foreign key in or out, no trigger and no row",
        "migration 0011's columns on predictions, unchanged",
        "No existing application row is read",
        "built from migrations 0001-0011, the state production is expected to be in",
        "rebuilt from migrations 0001-0010 and 0012 alone, without 0011",
        "Only the apply step receives the database secret.",
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
        occurrences = re.findall(r"\$\{?MIGRATION_0012_[A-Z_]+\}?", step.run)
        quoted = re.findall(r'="\$MIGRATION_0012_[A-Z_]+"', step.run)
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
        "MIGRATION_0012_EXPECTED_SHA": "${{ inputs.expected_sha }}",
        "MIGRATION_0012_CONFIRM": "${{ inputs.confirm }}",
    }
    assert ATTEST.env == {"MIGRATION_0012_EXPECTED_SHA": "${{ inputs.expected_sha }}"}
    assert REHEARSE.env == {apply_0012.REHEARSAL_URL_VARIABLE: REHEARSAL_URL}
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
    assert apply_0012.PINNED_PYTHON == (
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
        assert step.run.startswith(f"python -I -S -B {apply_0012.SCRIPT} "), step.name
    assert f"python -I -S -B {apply_0012.SCRIPT} --mode=rehearse" in REHEARSE.run
    for step in RUN_STEPS:
        assert "PYTHONPATH" not in step.run, step.name
        for match in re.finditer(r"\bpython\b(?P<rest>[^\n]*)", step.run):
            assert match.group("rest").startswith((" -I -S -B ", " -s -B -m pytest ")), step.name


# --------------------------------------------------------------------------- the rehearsal


def _rehearsal_lines(step: Step) -> list[str]:
    return step.run.strip().splitlines()


def test_the_rehearsal_builds_both_scratch_databases_from_the_real_migrations() -> None:
    lines = _rehearsal_lines(REHEARSE)
    psql = "psql -X -q -v ON_ERROR_STOP=1 -d"
    bundle = '"$RUNNER_TEMP/migrations_0001_0010.sql"'
    assert lines == [
        "sudo systemctl start postgresql.service",
        'sudo -u postgres psql -X -q -v ON_ERROR_STOP=1 -c "CREATE ROLE \\"$(id -un)\\" LOGIN"',
        "sudo -u postgres psql -X -q -v ON_ERROR_STOP=1 -f - < "
        f"{FIXTURES}/00_supabase_like_roles.sql",
        'sudo -u postgres createdb -O "$(id -un)" migration_0012_rehearsal',
        'sudo -u postgres createdb -O "$(id -un)" migration_0012_rebuild',
        'sudo -u postgres psql -X -q -v ON_ERROR_STOP=1 -v owner="$(id -un)" '
        f"-d migration_0012_rehearsal -f - < {FIXTURES}/01_supabase_like_grants.sql",
        'sudo -u postgres psql -X -q -v ON_ERROR_STOP=1 -v owner="$(id -un)" '
        f"-d migration_0012_rebuild -f - < {FIXTURES}/01_supabase_like_grants.sql",
        f"cat {' '.join(MIGRATIONS_0001_0010)} > {bundle}",
        f"{psql} migration_0012_rehearsal -f - < {bundle}",
        f"{psql} migration_0012_rehearsal -f - < {apply_0011.MIGRATION}",
        f"python -I -S -B {apply_0012.SCRIPT} --mode=rehearse "
        f'--wheelhouse="$RUNNER_TEMP/section-5a-wheels" --report={REHEARSAL_REPORT}',
        f"{psql} migration_0012_rehearsal -f - < {FIXTURES}/20_assert_status_table.sql",
        f"{psql} migration_0012_rebuild -f - < {bundle}",
        f"{psql} migration_0012_rebuild -f - < {apply_0012.MIGRATION}",
        f"{psql} migration_0012_rebuild -f - < {FIXTURES}/20_assert_status_table.sql",
    ]
    assert len(lines) == 15
    assert apply_0011.MIGRATION == "migrations/0011_prediction_target_provenance.sql"
    rebuild = [line for line in lines if "migration_0012_rebuild" in line]
    assert len(rebuild) == 5 and not any(apply_0011.MIGRATION in line for line in rebuild), (
        "the rebuild never carries 0011, which proves 0012 needs nothing from it"
    )
    assert "SUPERUSER" not in REHEARSE.run, "the scratch owner is an ordinary login role"
    assert "SUPABASE" not in REHEARSE.run
    for relative in (
        *MIGRATIONS_0001_0010,
        apply_0011.MIGRATION,
        apply_0012.MIGRATION,
        *(f"{FIXTURES}/{name}" for name in FIXTURE_NAMES),
    ):
        assert (ROOT / relative).is_file(), relative


def test_the_rebuild_bundle_is_every_migration_before_0011_in_order() -> None:
    earlier = sorted(
        path.relative_to(ROOT).as_posix()
        for path in (ROOT / "migrations").glob("*.sql")
        if path.name < "0011"
    )
    assert list(MIGRATIONS_0001_0010) == earlier and len(earlier) == 10


def test_the_rehearse_step_runs_every_command_in_order_and_fails_closed(tmp_path: Path) -> None:
    """Executed as GitHub runs it, with every command it calls replaced by a recording stub."""

    commands = {line.split()[0] for line in _rehearsal_lines(REHEARSE)}
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

    psql = ["-X", "-q", "-v", "ON_ERROR_STOP=1"]
    as_postgres = ["-u", "postgres"]
    calls = [call["argv"] for call in stub_calls(log)]
    assert calls == [
        ["systemctl", "start", "postgresql.service"],
        ["-un"],
        [*as_postgres, "psql", *psql, "-c", 'CREATE ROLE "runner" LOGIN'],
        [*as_postgres, "psql", *psql, "-f", "-"],
        ["-un"],
        [*as_postgres, "createdb", "-O", "runner", "migration_0012_rehearsal"],
        ["-un"],
        [*as_postgres, "createdb", "-O", "runner", "migration_0012_rebuild"],
        ["-un"],
        [*as_postgres, "psql", *psql, "-v", "owner=runner", "-d", "migration_0012_rehearsal",
         "-f", "-"],
        ["-un"],
        [*as_postgres, "psql", *psql, "-v", "owner=runner", "-d", "migration_0012_rebuild",
         "-f", "-"],
        list(MIGRATIONS_0001_0010),
        [*psql, "-d", "migration_0012_rehearsal", "-f", "-"],
        [*psql, "-d", "migration_0012_rehearsal", "-f", "-"],
        [*ENTRYPOINT, "--mode=rehearse", f"--wheelhouse={tmp_path}/section-5a-wheels",
         f"--report={REHEARSAL_REPORT}"],
        [*psql, "-d", "migration_0012_rehearsal", "-f", "-"],
        [*psql, "-d", "migration_0012_rebuild", "-f", "-"],
        [*psql, "-d", "migration_0012_rebuild", "-f", "-"],
        [*psql, "-d", "migration_0012_rebuild", "-f", "-"],
    ]

    log.unlink()
    failing = {**env, "STUB_EXIT": "3"}
    completed = run_step(REHEARSE, env=failing, workdir=tmp_path, bin_dir=tmp_path / "bin")
    assert completed.returncode == 3, "the first failing command fails the step"
    first = ["systemctl", "start", "postgresql.service"]
    assert [call["argv"] for call in stub_calls(log)] == [first], "and nothing after it runs"


# --------------------------------------------------------------------------- the fixtures


def _fixture(name: str) -> str:
    return (ROOT / FIXTURES / name).read_text(encoding="utf-8")


def _statements(text: str) -> list[str]:
    return [line for line in text.splitlines() if line.strip() and not line.startswith("--")]


def test_the_rehearsal_fixtures_hold_no_secret_and_state_where_they_run() -> None:
    fixtures = sorted((ROOT / FIXTURES).glob("*"))
    assert [path.name for path in fixtures] == list(FIXTURE_NAMES)
    for path in fixtures:
        text = path.read_text(encoding="utf-8")
        assert "PASSWORD" not in text.upper() and "postgresql://" not in text, path.name
        assert "SUPABASE_DB_URL" not in text and "secrets." not in text, path.name
        header = _comment_header(text)
        assert "migration 0012" in header, path.name
        assert "Runs ONLY in a scratch local PostgreSQL on a CI runner" in header, path.name
        assert "Never run it against a real database." in header, path.name


def test_the_role_and_grant_fixtures_are_0011_s_statements() -> None:
    for name in ("00_supabase_like_roles.sql", "01_supabase_like_grants.sql"):
        precedent = (ROOT / "scripts/migration_0011_rehearsal" / name).read_text(encoding="utf-8")
        assert _statements(_fixture(name)) == _statements(precedent), name
    roles = _fixture("00_supabase_like_roles.sql")
    assert "CREATE ROLE service_role NOLOGIN NOINHERIT BYPASSRLS;" in roles
    grants = _fixture("01_supabase_like_grants.sql")
    assert 'FOR ROLE :"owner" IN SCHEMA public' in grants
    assert "GRANT ALL ON TABLES TO anon, authenticated, service_role;" in grants
    assert "the migration revokes them" in _comment_header(grants)


ASSERTION = "20_assert_status_table.sql"
EXPECTED_COLUMN_ROW = re.compile(
    r"^\s*\((?P<position>\d+), '(?P<name>[a-z_]+)', '(?P<type>[a-z ]+)', "
    r"(?P<not_null>true|false), (?P<default>NULL|'[^']*')\),?$",
    re.M,
)
EXPECTED_CONSTRAINT_ROW = re.compile(r"^\s*\('(?P<name>[a-z_]+)', '(?P<kind>[pc])'\),?$", re.M)


def test_the_assertion_checks_columns_constraints_indexes_security_and_rows() -> None:
    text = _fixture(ASSERTION)
    statements = "\n".join(_statements(text))
    assert statements.startswith("DO $$\n") and statements.endswith("\nEND\n$$;")
    assert statements.count("$$") == 2, "one DO block and nothing else"
    # (a) the thirteen columns, in order.
    columns = [
        (
            int(match["position"]),
            match["name"],
            match["type"],
            match["not_null"] == "true",
            None if match["default"] == "NULL" else match["default"].strip("'"),
        )
        for match in EXPECTED_COLUMN_ROW.finditer(text)
    ]
    assert [column[0] for column in columns] == list(range(1, 14))
    assert tuple(column[1:] for column in columns) == apply_0012.EXPECTED_COLUMNS
    for condition in (
        "IF counted <> 13 THEN",
        "a.attnum = expected_column.column_position",
        "pg_catalog.format_type(a.atttypid, a.atttypmod) = expected_column.type_name",
        "a.attnotnull = expected_column.not_null",
        "IS NOT DISTINCT FROM expected_column.default_expression",
        "a.attidentity = ''",
        "a.attgenerated = ''",
        "a.attacl IS NULL",
    ):
        assert condition in text, condition
    # (b) the nine constraints, validated, and the two indexes.
    constraints = {match["name"]: match["kind"] for match in EXPECTED_CONSTRAINT_ROW.finditer(text)}
    assert constraints == {
        name: kind for name, (kind, _, _) in apply_0012.EXPECTED_CONSTRAINTS.items()
    }
    for condition in (
        "c.contype::text = expected_constraint.constraint_type",
        "AND c.convalidated",
        "AND c.contype <> 'n';",
        "IF counted <> 9 THEN",
        "('prediction_resolution_status_pkey', true, ARRAY['prediction_id'], NULL),",
        "'prediction_resolution_status_retry_idx', false,",
        "ARRAY['next_eligible_utc', 'prediction_id'], '(resolution_status = ''RETRYABLE''::text)'",
        "FROM pg_catalog.unnest(x.indkey) WITH ORDINALITY AS k(attnum, n)",
        "x.indisunique = expected_index.is_unique",
        "IS NOT DISTINCT FROM expected_index.predicate",
        "IF counted <> 2 THEN",
    ):
        assert condition in text, condition
    # (c) row-level security on, not forced, no policy.
    for condition in (
        "AND c.relrowsecurity",
        "AND NOT c.relforcerowsecurity",
        "pg_catalog.pg_policy",
    ):
        assert condition in text, condition
    # (d) no privilege for PUBLIC or an API role: every privilege, MAINTAIN from 17.
    assert (
        "ARRAY[\n"
        "    'SELECT', 'INSERT', 'UPDATE', 'DELETE', 'TRUNCATE', 'REFERENCES', 'TRIGGER'\n"
        "  ]"
    ) in text
    assert "current_setting('server_version_num')::integer >= 170000 THEN" in text
    assert "asked_privileges := asked_privileges || 'MAINTAIN'::text;" in text
    assert "ARRAY['public', 'anon', 'authenticated', 'service_role']" in text
    assert "pg_catalog.has_table_privilege(" in text
    # (e) no row, before the probes and after them.
    assert text.count("SELECT count(*) INTO counted FROM public.prediction_resolution_status;") == 2


PROBE_ROW = re.compile(
    r"^\s*\('(?P<name>[a-z0-9-]+)', '(?P<expected>accepted|[0-9]{5})', "
    r"(?P<rejected_by>NULL|'[a-z0-9_]+'), (?P<copies>[0-9]+),\n"
    r"\s*(?P<values>.+?)\),?$",
    re.M,
)
PROBE_COLUMNS = (
    "prediction_id",
    "resolution_status",
    "attempt_count",
    "first_attempt_utc",
    "last_attempt_utc",
    "first_reason",
    "last_reason",
    "next_eligible_utc",
    "quarantined_at_utc",
    "resolved_at_utc",
    "policy_version",
    "resolver_version",
)
# A valid RETRYABLE row, as the probe table spells it; every probe varies it.
BASE = {
    "prediction_id": "probe_id",
    "resolution_status": "'RETRYABLE'",
    "attempt_count": "1",
    "first_attempt_utc": "at_1",
    "last_attempt_utc": "at_2",
    "first_reason": "a_skip",
    "last_reason": "an_error",
    "next_eligible_utc": "at_3",
    "quarantined_at_utc": "NULL",
    "resolved_at_utc": "NULL",
    "policy_version": "'rq-v1'",
    "resolver_version": "resolver",
}
QUARANTINED = {
    "resolution_status": "'QUARANTINED'",
    "attempt_count": "5",
    "next_eligible_utc": "NULL",
    "quarantined_at_utc": "at_3",
}
RESOLVED = {
    "resolution_status": "'RESOLVED'",
    "attempt_count": "2",
    "next_eligible_utc": "NULL",
    "resolved_at_utc": "at_3",
}


def probe(expected: str, rejected_by: str, copies: str = "1", **changes: str) -> tuple:
    values = {**BASE, **changes}
    return (expected, rejected_by, copies, tuple(values[column] for column in PROBE_COLUMNS))


ACCEPTED = ("accepted", "NULL")
SHAPE = ("23514", "'prs_state_shape'")
REASON = ("23514", "'prs_reason_format'")
POLICY = ("23514", "'prs_policy_version_format'")
# name: (expected, rejected_by, copies, the twelve column values)
EXPECTED_PROBES = {
    "retryable": probe(*ACCEPTED),
    "quarantined": probe(*ACCEPTED, **QUARANTINED),
    "resolved": probe(*ACCEPTED, **RESOLVED),
    "first-equals-last-attempt": probe(*ACCEPTED, first_attempt_utc="at_2"),
    "reason-64-characters": probe(*ACCEPTED, first_reason="reason_64", last_reason="reason_64"),
    "policy-rq-v1": probe(*ACCEPTED),
    "policy-rq-v12": probe(*ACCEPTED, policy_version="'rq-v12'"),
    "retryable-without-next-eligible": probe(*SHAPE, next_eligible_utc="NULL"),
    "retryable-with-quarantined-at": probe(*SHAPE, quarantined_at_utc="at_3"),
    "retryable-with-resolved-at": probe(*SHAPE, resolved_at_utc="at_3"),
    "quarantined-without-quarantined-at": probe(
        *SHAPE, **{**QUARANTINED, "quarantined_at_utc": "NULL"}
    ),
    "quarantined-with-next-eligible": probe(*SHAPE, **{**QUARANTINED, "next_eligible_utc": "at_3"}),
    "quarantined-with-resolved-at": probe(*SHAPE, **{**QUARANTINED, "resolved_at_utc": "at_3"}),
    "resolved-without-resolved-at": probe(*SHAPE, **{**RESOLVED, "resolved_at_utc": "NULL"}),
    "resolved-with-next-eligible": probe(*SHAPE, **{**RESOLVED, "next_eligible_utc": "at_3"}),
    "resolved-with-quarantined-at": probe(*SHAPE, **{**RESOLVED, "quarantined_at_utc": "at_3"}),
    "status-pending": probe(*SHAPE, resolution_status="'PENDING'"),
    "attempt-count-zero": probe("23514", "'prs_attempt_count_positive'", attempt_count="0"),
    "last-attempt-before-first": probe(
        "23514", "'prs_attempt_chronology'", first_attempt_utc="at_2", last_attempt_utc="at_1"
    ),
    "reason-failed-prefix": probe(*REASON, first_reason="'failed_x'"),
    "reason-bare-skip-prefix": probe(*REASON, last_reason="'skip_'"),
    "reason-uppercase": probe(*REASON, first_reason="'SKIP_X'"),
    "reason-hyphen": probe(*REASON, last_reason="'error_x-y'"),
    "reason-65-characters": probe(*REASON, first_reason="reason_65"),
    "policy-rq-v0": probe(*POLICY, policy_version="'rq-v0'"),
    "policy-rq-1": probe(*POLICY, policy_version="'rq-1'"),
    "policy-rq-v01": probe(*POLICY, policy_version="'rq-v01'"),
    "resolver-version-blank": probe(
        "23514", "'prs_resolver_version_nonblank'", resolver_version="'  '"
    ),
    "prediction-id-blank": probe("23514", "'prs_prediction_id_nonblank'", prediction_id="' '"),
    "first-reason-null": probe("23502", "'first_reason'", first_reason="NULL"),
    "prediction-id-twice": probe("23505", "'prediction_resolution_status_pkey'", copies="2"),
}


def test_the_assertion_probes_exactly_the_reviewed_cases() -> None:
    text = _fixture(ASSERTION)
    probes = {
        match["name"]: (
            match["expected"],
            match["rejected_by"],
            match["copies"],
            tuple(match["values"].split(", ")),
        )
        for match in PROBE_ROW.finditer(text)
    }
    assert probes == EXPECTED_PROBES
    assert len(PROBE_ROW.findall(text)) == len(EXPECTED_PROBES) == 31
    assert f"IF probes_run <> {len(EXPECTED_PROBES)} THEN" in text
    accepted = sorted(name for name, row in probes.items() if row[0] == "accepted")
    assert accepted == [
        "first-equals-last-attempt",
        "policy-rq-v1",
        "policy-rq-v12",
        "quarantined",
        "reason-64-characters",
        "resolved",
        "retryable",
    ]
    assert [name for name, row in probes.items() if row[2] != "1"] == ["prediction-id-twice"]
    # Every rejected probe names what must reject it: a constraint, or the NOT NULL column.
    named = {row[1].strip("'") for row in probes.values() if row[0] != "accepted"}
    not_null = {name for name, _, required, _ in apply_0012.EXPECTED_COLUMNS if required}
    for name, (expected, rejected_by, _, _) in probes.items():
        by = rejected_by.strip("'")
        if expected in ("23514", "23505"):
            assert by in apply_0012.EXPECTED_CONSTRAINTS, name
        elif expected == "23502":
            assert by in not_null, name
        else:
            assert (expected, rejected_by) == ACCEPTED, name
    # PostgreSQL tests CHECK constraints in name order, and a status outside the three fails
    # prs_state_shape too, which sorts first: prs_status_valid can never be the one named.
    assert "prs_state_shape" < "prs_status_valid"
    assert named == (set(apply_0012.EXPECTED_CONSTRAINTS) - {"prs_status_valid"}) | {
        "first_reason"
    }
    for declaration in (
        "at_1 timestamptz := '2026-09-29 12:00:01+00';",
        "at_2 timestamptz := '2026-09-29 12:00:02+00';",
        "at_3 timestamptz := '2026-09-29 12:00:03+00';",
        "probe_id text := 'rehearsal-probe';",
        "resolver text := 'resolver-v2a';",
        "a_skip text := 'skip_not_due';",
        "an_error text := 'error_candle_invalid';",
        "reason_64 text := 'error_' || pg_catalog.repeat('x', 58);",
        "reason_65 text := 'error_' || pg_catalog.repeat('x', 59);",
    ):
        assert declaration in text, declaration


def test_each_probe_inserts_a_full_row_and_passes_only_on_its_exact_outcome() -> None:
    text = _fixture(ASSERTION)
    inserted = re.search(
        r"INSERT INTO public\.prediction_resolution_status \((?P<columns>.*?)\)\s+SELECT"
        r"(?P<values>.*?)FROM pg_catalog\.generate_series\(1, probe\.copies\);",
        text,
        re.S,
    )
    assert inserted is not None
    columns = [part.strip() for part in inserted["columns"].split(",")]
    assert tuple(columns) == PROBE_COLUMNS
    assert tuple(columns) == apply_0012.EXPECTED_COLUMN_NAMES[:-1], "all but updated_at_utc"
    values = [part.strip() for part in inserted["values"].split(",")]
    assert values == [f"probe.{column}" for column in PROBE_COLUMNS]
    # Every probe ends in an exception, so nothing it inserted persists.
    sentinel = "'migration 0012 rehearsal probe accepted'"
    assert text.count(sentinel) == 2
    assert (
        "FROM pg_catalog.generate_series(1, probe.copies);\n"
        f"      RAISE EXCEPTION {sentinel};"
    ) in text
    assert text.count("WHEN OTHERS THEN") == 1
    for item in (
        "failed_state = RETURNED_SQLSTATE",
        "failed_message = MESSAGE_TEXT",
        "failed_constraint = CONSTRAINT_NAME",
        "failed_column = COLUMN_NAME;",
    ):
        assert item in text, item
    assert (
        "failed_name := CASE WHEN failed_state = '23502' THEN failed_column "
        "ELSE failed_constraint END;"
    ) in text
    assert f"IF failed_state <> 'P0001' OR failed_message <> {sentinel} THEN" in text
    assert "ELSIF failed_state <> probe.expected THEN" in text
    assert "ELSIF failed_name IS DISTINCT FROM probe.rejected_by THEN" in text
    assert "RAISE;" not in text, "a failure is re-raised as a message naming the probe"
    assert "ELSIF CASE" not in text, "a CASE in a PL/pgSQL condition ends at its first THEN"


def test_the_in_job_tests_cover_the_script_the_migration_and_this_boundary() -> None:
    command = TESTS.run.split()
    assert command[:7] == ["python", "-s", "-B", "-m", "pytest", "-q", "-p"]
    assert command[7] == "no:cacheprovider"
    paths = [part for part in command if part.startswith("tests/")]
    assert paths == IN_JOB_TESTS and len(command) == 8 + len(IN_JOB_TESTS)
    for path in paths:
        assert (ROOT / path).is_file(), path
    assert "tests/migrations/test_prediction_resolution_status_values.py" not in TESTS.run


def test_both_reports_are_uploaded_always() -> None:
    assert f"--report={REPORT}" in APPLY.run
    assert f"--report={REHEARSAL_REPORT}" in REHEARSE.run
    assert UPLOAD.fields.get("if") == "always()"
    assert UPLOAD.with_["path"].split() == [REPORT, REHEARSAL_REPORT]
    assert UPLOAD.with_["if-no-files-found"] == "warn"


def test_no_other_database_workflow_names_0012() -> None:
    for workflow in OTHER_DATABASE_WORKFLOWS:
        text = (ROOT / workflow).read_text(encoding="utf-8")
        assert "0012" not in text, workflow
    assert provenance.SEAL_MIGRATION_WORKFLOW in OTHER_DATABASE_WORKFLOWS
    assert provenance.EVALUATION_WORKFLOW in OTHER_DATABASE_WORKFLOWS
    assert apply_0011.WORKFLOW in OTHER_DATABASE_WORKFLOWS


def test_there_is_no_migration_0012_rehearsal_workflow() -> None:
    for name in ("apply-migration-0012-rehearsal.yml", "migration-0012-rehearsal.yml"):
        assert not (ROOT / ".github/workflows" / name).exists(), name
        assert name not in TEXT


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
        *ENTRYPOINT, "--mode=attest", f"--expected-sha={hostile}", f"--wheelhouse={WHEELHOUSE}"
    ]
    args = apply_0012.build_parser().parse_args(apply_call[len(ENTRYPOINT) :])
    assert args.mode == apply_0012.MODE_APPLY, "the mode is fixed in the workflow, never an input"
    assert args.expected_sha == hostile and args.confirm == hostile
    assert args.wheelhouse == WHEELHOUSE and args.report == REPORT
    assert not list(tmp_path.glob("INJECTED*")), "an input executed as a command"


@pytest.mark.parametrize("step", [ATTEST, APPLY, TESTS], ids=lambda step: step.name)
def test_a_failing_command_fails_its_step(tmp_path: Path, step: Step) -> None:
    install_stub(tmp_path / "bin", "python", tmp_path / "calls.jsonl")
    env = _environment(step, _contexts("value"), STUB_EXIT="2")
    completed = run_step(step, env=env, workdir=tmp_path, bin_dir=tmp_path / "bin")
    assert completed.returncode == 2, (step.name, completed.stderr)
