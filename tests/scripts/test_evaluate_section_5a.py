"""The section 5A evaluation CLI. No database is contacted and nothing is dispatched.

Live modes are exercised through ``main()`` with an explicit environment, and once as the workflow
runs it — a real subprocess — because a guarantee that holds in the library but not at the
production entrypoint is exactly the class of defect V807-F3, V808-F1 and V808-R6 were.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from crypto_probability_engine.oos.evaluation import provenance, runner
from scripts import evaluate_section_5a as cli
from tests.oos.evaluation.conftest import (
    SYNTHETIC_SHA,
    synthetic_dispatch,
    synthetic_runtime,
)

ROOT = Path(__file__).resolve().parents[2]
LIVE_MODES = ("attest", "readiness", "consume", "recompute")


def _live_argv(mode: str) -> list[str]:
    return [
        f"--mode={mode}",
        f"--confirm={runner.CONFIRMATION_TOKEN}",
        f"--expected-sha={SYNTHETIC_SHA}",
    ]


@pytest.fixture
def verified_dispatch(monkeypatch: pytest.MonkeyPatch) -> None:
    """A verified run: synthetic GitHub facts, the pinned runtime. The VERIFIER stays real."""

    monkeypatch.setattr(provenance, "observe_dispatch", lambda environ: synthetic_dispatch())
    monkeypatch.setattr(provenance, "observe_runtime", lambda root: synthetic_runtime())


@pytest.fixture
def no_database(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("SUPABASE_DB_URL", "SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def fake_seal():
    from tests.oos.evaluation.test_runner import FakeRepository

    FakeRepository.durable_seal = None
    yield FakeRepository
    FakeRepository.durable_seal = None


# --------------------------------------------------------------------------- parsing


def test_default_mode_is_readiness_not_consume() -> None:
    """The safe mode is the one you get by forgetting to choose."""

    args = cli.build_parser().parse_args([])
    assert args.mode == runner.MODE_READINESS
    assert args.confirm == "" and args.expected_sha == "" and args.report is None


def test_consume_requires_an_explicit_mode_and_token() -> None:
    args = cli.build_parser().parse_args(
        ["--mode", "consume", "--confirm", runner.CONFIRMATION_TOKEN]
    )
    assert args.mode == runner.MODE_CONSUME
    assert args.confirm == runner.CONFIRMATION_TOKEN


def test_the_workflow_argument_forms_bind_hostile_values_to_their_option() -> None:
    """`--opt=value` keeps a value starting with `-` from being read as another option."""

    args = cli.build_parser().parse_args(
        ["--mode=consume", "--confirm=--write-pin", "--expected-sha=--mode=readiness"]
    )
    assert args.confirm == "--write-pin" and args.expected_sha == "--mode=readiness"
    assert args.mode == "consume" and args.write_pin is False


def test_cli_rejects_an_unknown_mode() -> None:
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args(["--mode", "definitely-not-a-mode"])


def test_recovery_and_attestation_modes_are_available() -> None:
    parser = cli.build_parser()
    for mode in ("attest", "recompute", "recompute-artifact"):
        assert parser.parse_args(["--mode", mode]).mode == mode


# --------------------------------------------------------------------------- E2/E3 first


@pytest.mark.parametrize("mode", LIVE_MODES)
def test_every_live_mode_attests_before_any_repository_exists(
    mode: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Outside a verified dispatch nothing is built, so nothing can be read or claimed."""

    def _forbidden():
        raise AssertionError("a repository was built before the run was attested")

    monkeypatch.setattr(cli, "build_repository", _forbidden)
    with pytest.raises(provenance.ProvenanceRefused, match="not running inside GitHub Actions"):
        cli.main(_live_argv(mode), environ={})


def test_the_ambient_github_environment_is_not_trusted_by_tests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Facts are observed from the environment the entrypoint is GIVEN, not from os.environ."""

    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setattr(cli, "build_repository", lambda: pytest.fail("repository built"))
    with pytest.raises(provenance.ProvenanceRefused):
        cli.main(["--mode", "readiness", "--expected-sha", SYNTHETIC_SHA], environ={})


def test_a_wrong_expected_sha_refuses_even_for_an_otherwise_verified_run(
    verified_dispatch, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cli, "build_repository", lambda: pytest.fail("repository built"))
    with pytest.raises(provenance.ProvenanceRefused, match="not expected_sha"):
        cli.main(["--mode", "readiness", "--expected-sha", "b" * 40], environ={})


def test_attest_touches_no_repository_and_reports_the_record(
    verified_dispatch, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    monkeypatch.setattr(cli, "build_repository", lambda: pytest.fail("repository built"))
    assert cli.main(["--mode", "attest", "--expected-sha", SYNTHETIC_SHA], environ={}) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["touches_repository"] is False
    assert printed["run_provenance"]["dispatch_verified"] is True


# --------------------------------------------------------------------------- then the authority


def test_the_cli_requires_a_positive_durable_postgres_declaration() -> None:
    """G8. build_operator_repository silently falls back to in-memory without a database URL;
    a missing secret must refuse rather than seal process-locally."""

    from crypto_probability_engine.persistence import repository as module

    with pytest.raises(runner.ConsumptionRefused, match="not a durable Postgres authority"):
        cli.require_durable_authority(module.InMemoryPersistenceRepository())
    rest = module.SupabaseRestRepository.__new__(module.SupabaseRestRepository)
    with pytest.raises(runner.ConsumptionRefused, match="SUPABASE_DB_URL"):
        cli.require_durable_authority(rest)
    cli.require_durable_authority(
        module.SupabasePersistenceRepository("postgresql://never-connected")
    )


@pytest.mark.parametrize("mode", ("readiness", "consume", "recompute"))
def test_a_verified_run_without_a_database_still_refuses_at_the_authority(
    mode: str, verified_dispatch, no_database
) -> None:
    """V807-F3 and G8, after attestation: an empty store is refused, never reported on."""

    with pytest.raises(runner.ConsumptionRefused, match="not a durable Postgres authority"):
        cli.main(_live_argv(mode), environ={})


def test_the_cli_reads_its_database_configuration_from_the_environment(monkeypatch) -> None:
    """V807-F3. Settings() ignores the environment; with the secret set, the CLI must still build
    the Postgres repository. Constructing it never connects."""

    from crypto_probability_engine.persistence import repository as module

    monkeypatch.setenv("SUPABASE_DB_URL", "postgresql://probe-only-never-connected")
    repository = cli.build_repository()
    assert isinstance(repository, module.SupabasePersistenceRepository)
    cli.require_durable_authority(repository)


def test_an_undeclared_repository_is_refused_by_the_cli() -> None:
    with pytest.raises(runner.ConsumptionRefused, match="None"):
        cli.require_durable_authority(object())


# --------------------------------------------------------------------------- the verified look


def test_a_verified_consumption_records_its_run_in_the_claim_and_the_report(
    verified_dispatch, fake_seal, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(cli, "build_repository", lambda: fake_seal())
    report = tmp_path / "report.json"
    assert (
        cli.main(
            [
                "--mode=consume",
                f"--confirm={runner.CONFIRMATION_TOKEN}",
                f"--expected-sha={SYNTHETIC_SHA}",
                f"--artifact-dir={tmp_path / 'artifact'}",
                f"--report={report}",
            ],
            environ={},
        )
        == 0
    )
    record = fake_seal.durable_seal["run_provenance"]
    assert record["dispatch_verified"] is True and record["expected_sha"] == SYNTHETIC_SHA
    written = json.loads(report.read_text(encoding="utf-8"))
    assert written["consumes_one_look"] is True
    assert written["run_provenance"] == record


# --------------------------------------------------------------------------- V808-R6 reports


def test_a_refusal_is_written_to_the_report_and_still_fails_the_run(tmp_path: Path) -> None:
    report = tmp_path / "nested" / "report.json"
    with pytest.raises(provenance.ProvenanceRefused):
        cli.main(["--mode", "consume", f"--report={report}"], environ={})
    written = json.loads(report.read_text(encoding="utf-8"))
    assert written["outcome"] == "REFUSED"
    assert written["error_type"] == "ProvenanceRefused"
    assert "not running inside GitHub Actions" in written["detail"]


def test_an_unexpected_failure_withholds_its_detail_from_the_report(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A driver error may name a host. The artifact is downloadable, so only the type is kept."""

    def _boom(*_, **__):
        raise RuntimeError("could not connect to postgresql://user@db.example.invalid:5432")

    monkeypatch.setattr(provenance, "attest", _boom)
    report = tmp_path / "report.json"
    with pytest.raises(RuntimeError):
        cli.main(["--mode", "readiness", f"--report={report}"], environ={})
    written = json.loads(report.read_text(encoding="utf-8"))
    assert written["outcome"] == "FAILED" and written["error_type"] == "RuntimeError"
    assert "postgresql" not in json.dumps(written) and "example.invalid" not in json.dumps(written)


def test_the_entrypoint_as_the_workflow_runs_it_refuses_with_a_nonzero_exit(tmp_path: Path) -> None:
    """A real process, a scrubbed environment and a database URL that must never be used."""

    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("GITHUB_", "RUNNER_", "SUPABASE_")) and key not in {"ImageOS"}
    }
    environment.update(
        {
            "PYTHONPATH": "src",
            # A syntactically valid URL that must never be contacted: refusal precedes any use.
            "SUPABASE_DB_URL": "postgresql://must-never-be-contacted.invalid/none",
        }
    )
    report = tmp_path / "section-5a-report.json"
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/evaluate_section_5a.py",
            "--mode=consume",
            f"--confirm={runner.CONFIRMATION_TOKEN}",
            f"--expected-sha={SYNTHETIC_SHA}",
            f"--artifact-dir={tmp_path / 'artifact'}",
            f"--report={report}",
        ],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert completed.returncode != 0
    assert "ProvenanceRefused" in completed.stderr
    assert json.loads(report.read_text(encoding="utf-8"))["outcome"] == "REFUSED"
    assert not (tmp_path / "artifact").exists(), "nothing was captured"
