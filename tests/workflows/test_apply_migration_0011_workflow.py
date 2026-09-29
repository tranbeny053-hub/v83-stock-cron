"""The migration-0011 workflow, read and EXECUTED the way GitHub runs it.

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
PATH = ROOT / apply_0011.WORKFLOW
TEXT = PATH.read_text(encoding="utf-8")
JOB = read_jobs(TEXT)["apply"]
STEPS = JOB.steps
RUN_STEPS = [step for step in STEPS if step.run is not None]

EVALUATION_TEXT = (ROOT / provenance.EVALUATION_WORKFLOW).read_text(encoding="utf-8")
EVALUATION_STEPS = read_jobs(EVALUATION_TEXT)["evaluate"].steps

ENTRYPOINT = ("-I", "-S", "-B", apply_0011.SCRIPT)
RUNNER_TEMP = "/home/runner/work/_temp"
WHEELHOUSE = f"{RUNNER_TEMP}/section-5a-wheels"
REPORT = "migration-0011-apply-report.json"
REHEARSAL_REPORT = "migration-0011-rehearsal-report.json"
REHEARSAL_URL = "postgresql:///migration_0011_rehearsal?host=/var/run/postgresql"
FIXTURES = "scripts/migration_0011_rehearsal"
FIXTURE_NAMES = (
    "00_supabase_like_roles.sql",
    "01_supabase_like_grants.sql",
    "10_existing_v0_rows.sql",
    "20_assert_contract.sql",
)
# Migrations 0001-0010, explicit: the state production is in before 0011.
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
    "tests/scripts/test_apply_migration_0011.py",
    "tests/migrations/test_prediction_target_contract_migration.py",
    "tests/workflows/test_apply_migration_0011_workflow.py",
    "tests/workflows/test_workflow_steps_reader.py",
]
# Every other workflow that reaches a database, named explicitly, never globbed.
OTHER_DATABASE_WORKFLOWS = (
    ".github/workflows/section-5a-apply-seal-migration.yml",
    ".github/workflows/section-5a-evaluation.yml",
    ".github/workflows/apply-migration-0008.yml",
    ".github/workflows/apply-migration-0010.yml",
    ".github/workflows/apply-migration-0010-rehearsal.yml",
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
APPLY = _step(STEPS, "Apply migration 0011")
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
    assert f"description: REQUIRED. Exactly {apply_0011.CONFIRMATION}\n" in confirm


def test_its_header_says_it_is_a_dispatch_only_draft_and_what_the_route_checks() -> None:
    header = _comment_header(TEXT)
    assert header.startswith("DRAFT: dispatch-only"), header[:80]
    for phrase in (
        "Merging this workflow is the owner's T3",
        "Dispatching it is a T4",
        "one shot",
        "never rerun",
        "public.predictions exists once",
        "none of the four new columns or three new constraints exists yet",
        "the three CHECK constraints validated",
        "No application row is read.",
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
        occurrences = re.findall(r"\$\{?MIGRATION_0011_[A-Z_]+\}?", step.run)
        quoted = re.findall(r'="\$MIGRATION_0011_[A-Z_]+"', step.run)
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
        "MIGRATION_0011_EXPECTED_SHA": "${{ inputs.expected_sha }}",
        "MIGRATION_0011_CONFIRM": "${{ inputs.confirm }}",
    }
    assert ATTEST.env == {"MIGRATION_0011_EXPECTED_SHA": "${{ inputs.expected_sha }}"}
    assert REHEARSE.env == {apply_0011.REHEARSAL_URL_VARIABLE: REHEARSAL_URL}
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
    assert apply_0011.PINNED_PYTHON == (
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
        assert step.run.startswith(f"python -I -S -B {apply_0011.SCRIPT} "), step.name
    assert f"python -I -S -B {apply_0011.SCRIPT} --mode=rehearse" in REHEARSE.run
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
        'sudo -u postgres createdb -O "$(id -un)" migration_0011_rehearsal',
        'sudo -u postgres createdb -O "$(id -un)" migration_0011_rebuild',
        'sudo -u postgres psql -X -q -v ON_ERROR_STOP=1 -v owner="$(id -un)" '
        f"-d migration_0011_rehearsal -f - < {FIXTURES}/01_supabase_like_grants.sql",
        'sudo -u postgres psql -X -q -v ON_ERROR_STOP=1 -v owner="$(id -un)" '
        f"-d migration_0011_rebuild -f - < {FIXTURES}/01_supabase_like_grants.sql",
        f"cat {' '.join(MIGRATIONS_0001_0010)} > {bundle}",
        f"{psql} migration_0011_rehearsal -f - < {bundle}",
        f"{psql} migration_0011_rehearsal -f - < {FIXTURES}/10_existing_v0_rows.sql",
        f"python -I -S -B {apply_0011.SCRIPT} --mode=rehearse "
        f'--wheelhouse="$RUNNER_TEMP/section-5a-wheels" --report={REHEARSAL_REPORT}',
        f"{psql} migration_0011_rehearsal -f - < {FIXTURES}/20_assert_contract.sql",
        f"{psql} migration_0011_rebuild -f - < {bundle}",
        f"{psql} migration_0011_rebuild -f - < {apply_0011.MIGRATION}",
        f"{psql} migration_0011_rebuild -f - < {FIXTURES}/20_assert_contract.sql",
    ]
    assert len(lines) == 15
    assert "SUPERUSER" not in REHEARSE.run, "the scratch owner is an ordinary login role"
    assert "SUPABASE" not in REHEARSE.run
    for relative in (
        *MIGRATIONS_0001_0010,
        apply_0011.MIGRATION,
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
    for relative in (apply_0011.MIGRATION, *(f"{FIXTURES}/{name}" for name in FIXTURE_NAMES)):
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
        [*as_postgres, "createdb", "-O", "runner", "migration_0011_rehearsal"],
        ["-un"],
        [*as_postgres, "createdb", "-O", "runner", "migration_0011_rebuild"],
        ["-un"],
        [*as_postgres, "psql", *psql, "-v", "owner=runner", "-d", "migration_0011_rehearsal",
         "-f", "-"],
        ["-un"],
        [*as_postgres, "psql", *psql, "-v", "owner=runner", "-d", "migration_0011_rebuild",
         "-f", "-"],
        list(MIGRATIONS_0001_0010),
        [*psql, "-d", "migration_0011_rehearsal", "-f", "-"],
        [*psql, "-d", "migration_0011_rehearsal", "-f", "-"],
        [*ENTRYPOINT, "--mode=rehearse", f"--wheelhouse={tmp_path}/section-5a-wheels",
         f"--report={REHEARSAL_REPORT}"],
        [*psql, "-d", "migration_0011_rehearsal", "-f", "-"],
        [*psql, "-d", "migration_0011_rebuild", "-f", "-"],
        [*psql, "-d", "migration_0011_rebuild", "-f", "-"],
        [*psql, "-d", "migration_0011_rebuild", "-f", "-"],
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


def _not_null_columns_of_0003() -> set[str]:
    text = (ROOT / "migrations/0003_prediction_ledger.sql").read_text(encoding="utf-8")
    body = re.search(r"CREATE TABLE IF NOT EXISTS predictions \((.*?)\n\);", text, re.S)
    assert body is not None
    required = set()
    for line in body.group(1).splitlines():
        match = re.match(r"\s*([a-z_]+)\s+[A-Z]+(.*)$", line)
        if match and ("NOT NULL" in match.group(2) or "PRIMARY KEY" in match.group(2)):
            required.add(match.group(1))
    assert len(required) == 19, required
    return required


def _insert(text: str) -> tuple[list[str], list[list[str]]]:
    """The column list of the one INSERT into predictions, and its rows' comma-split values."""

    match = re.search(r"INSERT INTO public\.predictions \((.*?)\) VALUES(.*?\));", text, re.S)
    assert match is not None
    columns = [part.strip() for part in match.group(1).split(",")]
    rows = [
        [part.strip() for part in row.split(",")]
        for row in re.findall(r"\(\s*(.*?)\s*\)(?:,|$)", match.group(2).strip(), re.S)
    ]
    return columns, rows


def test_the_rehearsal_fixtures_hold_no_secret_and_state_where_they_run() -> None:
    fixtures = sorted((ROOT / FIXTURES).glob("*"))
    assert [path.name for path in fixtures] == list(FIXTURE_NAMES)
    for path in fixtures:
        text = path.read_text(encoding="utf-8")
        assert "PASSWORD" not in text.upper() and "postgresql://" not in text, path.name
        assert "SUPABASE_DB_URL" not in text and "secrets." not in text, path.name
        header = _comment_header(text)
        assert "migration 0011" in header, path.name
        assert "Runs ONLY in a scratch local PostgreSQL on a CI runner" in header, path.name
        assert "Never run it against a real database." in header, path.name


def test_the_role_and_grant_fixtures_are_0010_s_statements() -> None:
    for name in ("00_supabase_like_roles.sql", "01_supabase_like_grants.sql"):
        precedent = (ROOT / "scripts/migration_0010_rehearsal" / name).read_text(encoding="utf-8")
        assert _statements(_fixture(name)) == _statements(precedent), name
    roles = _fixture("00_supabase_like_roles.sql")
    assert "CREATE ROLE service_role NOLOGIN NOINHERIT BYPASSRLS;" in roles
    grants = _fixture("01_supabase_like_grants.sql")
    assert 'FOR ROLE :"owner" IN SCHEMA public' in grants


def test_the_existing_rows_fixture_inserts_two_complete_v0_rows() -> None:
    text = _fixture("10_existing_v0_rows.sql")
    statements = " ".join(_statements(text))
    assert statements.count(";") == 1 and statements.startswith("INSERT INTO public.predictions (")
    columns, rows = _insert(text)
    assert _not_null_columns_of_0003() <= set(columns)
    assert len(columns) == len(set(columns))
    assert [row[0] for row in rows] == ["'rehearsal-v0-1'", "'rehearsal-v0-2'"]
    for row in rows:
        assert len(row) == len(columns), row
        values = dict(zip(columns, row, strict=True))
        probabilities = (values["p_up_frac"], values["p_down_frac"], values["p_timeout_frac"])
        assert round(sum(float(value) for value in probabilities), 9) == 1.0
    for name, _ in apply_0011.NEW_COLUMNS:
        assert name not in text, "the stamp columns do not exist before the apply"


PROBE_ROW = re.compile(
    r"^\s*\('(?P<name>[a-z0-9-]+)', (?P<target_version>NULL|'[^']*'), "
    r"(?P<reference_venue>NULL|'[^']*'), (?P<core>NULL|[a-z_]+), (?P<issued>NULL|[a-z_]+), "
    r"(?P<rejected_by>NULL|'[a-z_]+')\),?$",
    re.M,
)
_VERSION = "'predictions_target_version_chk'"
_VENUE = "'predictions_reference_venue_chk'"
_STAMP = "'predictions_target_stamp_chk'"
# name: (target_version, reference_venue, core_computed_at_utc, issued_at_utc, rejected_by)
EXPECTED_PROBES = {
    "v0-unstamped": ("NULL", "NULL", "NULL", "NULL", "NULL"),
    "tc-v1-binance": ("'tc-v1'", "'BINANCE_PUBLIC'", "core_at", "issued_at", "NULL"),
    "tc-v1-okx": ("'tc-v1'", "'OKX_PUBLIC'", "core_at", "issued_at", "NULL"),
    "tc-v1-core-equals-issued": ("'tc-v1'", "'BINANCE_PUBLIC'", "issued_at", "issued_at", "NULL"),
    "version-tc-v2": ("'tc-v2'", "'BINANCE_PUBLIC'", "core_at", "issued_at", _VERSION),
    "version-empty": ("''", "'BINANCE_PUBLIC'", "core_at", "issued_at", _VERSION),
    "venue-cross-provider": ("'tc-v1'", "'CROSS_PROVIDER'", "core_at", "issued_at", _VENUE),
    "venue-lowercase-binance": ("'tc-v1'", "'binance'", "core_at", "issued_at", _VENUE),
    "venue-empty": ("'tc-v1'", "''", "core_at", "issued_at", _VENUE),
    "stamp-without-target-version": ("NULL", "'BINANCE_PUBLIC'", "core_at", "issued_at", _STAMP),
    "stamp-without-reference-venue": ("'tc-v1'", "NULL", "core_at", "issued_at", _STAMP),
    "stamp-without-core-computed-at": ("'tc-v1'", "'BINANCE_PUBLIC'", "NULL", "issued_at", _STAMP),
    "stamp-without-issued-at": ("'tc-v1'", "'BINANCE_PUBLIC'", "core_at", "NULL", _STAMP),
    "core-after-issued": ("'tc-v1'", "'BINANCE_PUBLIC'", "after_issued_at", "issued_at", _STAMP),
}


def test_the_contract_assertion_checks_columns_constraints_and_existing_rows() -> None:
    text = _fixture("20_assert_contract.sql")
    statements = "\n".join(_statements(text))
    assert statements.startswith("DO $$\n") and statements.endswith("\nEND\n$$;")
    assert statements.count("$$") == 2, "one DO block and nothing else"
    for name, type_name in apply_0011.NEW_COLUMNS:
        assert f"('{name}', '{type_name}')" in text, name
    for condition in (
        "NOT a.attnotnull",
        "NOT a.atthasdef",
        "a.attidentity = ''",
        "a.attgenerated = ''",
        "pg_catalog.format_type(a.atttypid, a.atttypmod) = expected_column.type_name",
    ):
        assert condition in text, condition
    for name in apply_0011.NEW_CONSTRAINTS:
        assert f"('{name}')" in text, name
    assert "c.contype = 'c'" in text and "AND c.convalidated" in text
    assert (
        "pg_catalog.num_nonnulls(\n      p.target_version, p.reference_venue, "
        "p.core_computed_at_utc, p.issued_at_utc\n    ) > 0"
    ) in text


def test_the_contract_assertion_probes_exactly_the_reviewed_cases() -> None:
    text = _fixture("20_assert_contract.sql")
    probes = {
        match["name"]: (
            match["target_version"],
            match["reference_venue"],
            match["core"],
            match["issued"],
            match["rejected_by"],
        )
        for match in PROBE_ROW.finditer(text)
    }
    assert probes == EXPECTED_PROBES
    assert len(PROBE_ROW.findall(text)) == len(EXPECTED_PROBES) == 14
    assert f"IF probes_run <> {len(EXPECTED_PROBES)} THEN" in text
    accepted = sorted(name for name, probe in probes.items() if probe[-1] == "NULL")
    assert accepted == ["tc-v1-binance", "tc-v1-core-equals-issued", "tc-v1-okx", "v0-unstamped"]
    rejected_by = {probe[-1].strip("'") for probe in probes.values()} - {"NULL"}
    assert rejected_by == set(apply_0011.NEW_CONSTRAINTS)
    # The instants the probes use, in order: core < issued < after_issued.
    for declaration in (
        "core_at timestamptz := '2026-09-29 12:00:01+00';",
        "issued_at timestamptz := '2026-09-29 12:00:02+00';",
        "after_issued_at timestamptz := '2026-09-29 12:00:03+00';",
    ):
        assert declaration in text, declaration
    # Each probe is a full valid row, varied only in its four stamp values.
    columns, rows = _insert(text)
    assert _not_null_columns_of_0003() <= set(columns)
    assert columns[-4:] == [name for name, _ in apply_0011.NEW_COLUMNS]
    assert len(rows) == 1 and len(rows[0]) == len(columns)
    assert rows[0][0] == "'rehearsal-probe-' || probe.probe_name"
    assert rows[0][-4:] == [f"probe.{name}" for name, _ in apply_0011.NEW_COLUMNS]
    # Accepted: a sentinel only its own handler swallows. Rejected: exactly the named constraint.
    sentinel = "'migration 0011 rehearsal probe accepted'"
    assert text.count(sentinel) == 2
    assert "WHEN check_violation THEN" in text and "WHEN raise_exception THEN" in text
    assert "GET STACKED DIAGNOSTICS violated = CONSTRAINT_NAME;" in text
    assert "violated IS DISTINCT FROM probe.rejected_by" in text
    assert text.count("RAISE;") == 1 and "WHEN OTHERS" not in text
    assert "WHERE p.prediction_id LIKE 'rehearsal-probe-%'" in text


def test_the_in_job_tests_cover_the_script_the_migration_and_this_boundary() -> None:
    command = TESTS.run.split()
    assert command[:7] == ["python", "-s", "-B", "-m", "pytest", "-q", "-p"]
    assert command[7] == "no:cacheprovider"
    paths = [part for part in command if part.startswith("tests/")]
    assert paths == IN_JOB_TESTS and len(command) == 8 + len(IN_JOB_TESTS)
    for path in paths:
        assert (ROOT / path).is_file(), path
    assert "tests/migrations/test_prediction_target_contract_values.py" not in TESTS.run


def test_both_reports_are_uploaded_always() -> None:
    assert f"--report={REPORT}" in APPLY.run
    assert f"--report={REHEARSAL_REPORT}" in REHEARSE.run
    assert UPLOAD.fields.get("if") == "always()"
    assert UPLOAD.with_["path"].split() == [REPORT, REHEARSAL_REPORT]
    assert UPLOAD.with_["if-no-files-found"] == "warn"


def test_no_other_database_workflow_names_0011() -> None:
    for workflow in OTHER_DATABASE_WORKFLOWS:
        text = (ROOT / workflow).read_text(encoding="utf-8")
        assert "0011" not in text, workflow
    assert provenance.SEAL_MIGRATION_WORKFLOW in OTHER_DATABASE_WORKFLOWS
    assert provenance.EVALUATION_WORKFLOW in OTHER_DATABASE_WORKFLOWS


def test_there_is_no_migration_0011_rehearsal_workflow() -> None:
    for name in ("apply-migration-0011-rehearsal.yml", "migration-0011-rehearsal.yml"):
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
    args = apply_0011.build_parser().parse_args(apply_call[len(ENTRYPOINT) :])
    assert args.mode == apply_0011.MODE_APPLY, "the mode is fixed in the workflow, never an input"
    assert args.expected_sha == hostile and args.confirm == hostile
    assert args.wheelhouse == WHEELHOUSE and args.report == REPORT
    assert not list(tmp_path.glob("INJECTED*")), "an input executed as a command"


@pytest.mark.parametrize("step", [ATTEST, APPLY, TESTS], ids=lambda step: step.name)
def test_a_failing_command_fails_its_step(tmp_path: Path, step: Step) -> None:
    install_stub(tmp_path / "bin", "python", tmp_path / "calls.jsonl")
    env = _environment(step, _contexts("value"), STUB_EXIT="2")
    completed = run_step(step, env=env, workdir=tmp_path, bin_dir=tmp_path / "bin")
    assert completed.returncode == 2, (step.name, completed.stderr)
