"""The section 5A evaluation CLI. No database is contacted and nothing is dispatched.

A guarantee that holds in the library but not at the production entrypoint is exactly the class of
defect V807-F3, V808-F1, V808-R6 and V809-F1 were. So live modes are exercised through ``main()``
with an explicit environment, AND as the workflow runs them: real ``python -I -S -B`` processes.

In-process tests cannot be isolated, since pytest has already imported everything. Only there is
the isolation step replaced, by a declared synthetic report, and every call is recorded so the
ORDER is proven. The real isolation is proven in the subprocess tests below and in
``tests/oos/evaluation/test_runtime_isolation.py``.
"""

from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from crypto_probability_engine import runtime_isolation
from crypto_probability_engine.oos.evaluation import provenance, runner
from scripts import evaluate_section_5a as cli
from tests.oos.evaluation.conftest import (
    SYNTHETIC_SHA,
    synthetic_dispatch,
    synthetic_isolation,
    synthetic_runtime,
)

ROOT = Path(__file__).resolve().parents[2]
LIVE_MODES = ("attest", "readiness", "consume", "recompute")
ISOLATED = ("-I", "-S", "-B")


SYNTHETIC_WHEELHOUSE = "/synthetic/runner-temp/section-5a-wheels"


def _live_argv(mode: str) -> list[str]:
    return [
        f"--mode={mode}",
        f"--confirm={runner.CONFIRMATION_TOKEN}",
        f"--expected-sha={SYNTHETIC_SHA}",
        f"--wheelhouse={SYNTHETIC_WHEELHOUSE}",
    ]


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Declared synthetic isolation for in-process tests; records the order of every guard."""

    order: list[str] = []
    report = synthetic_isolation()
    real_attest = provenance.attest

    def _enter(wheelhouse):
        order.append("isolation")
        return report

    def _modules(isolation):
        assert isolation is report
        order.append("loaded-modules")
        return 0

    def _attest(expected_sha, *, environ, isolation=None, root=None):
        order.append("attest")
        return real_attest(expected_sha, environ=environ, isolation=isolation, root=root)

    monkeypatch.setattr(cli, "enter_isolated_runtime", _enter)
    monkeypatch.setattr(cli, "attest_loaded_modules", _modules)
    monkeypatch.setattr(provenance, "attest", _attest)
    return order


@pytest.fixture
def verified_dispatch(monkeypatch: pytest.MonkeyPatch) -> None:
    """A verified run: synthetic GitHub facts, the pinned runtime. The VERIFIER stays real."""

    monkeypatch.setattr(provenance, "observe_dispatch", lambda environ: synthetic_dispatch())
    monkeypatch.setattr(
        provenance, "observe_runtime", lambda root, isolation=None: synthetic_runtime()
    )


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


def _scrubbed_environment(extra: dict[str, str] | None = None) -> dict[str, str]:
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("GITHUB_", "RUNNER_", "SUPABASE_", "PYTHON")) and key != "ImageOS"
    }
    environment.update(extra or {})
    return environment


# --------------------------------------------------------------------------- the entrypoint itself


def test_the_entrypoint_imports_only_the_standard_library_at_module_level() -> None:
    """V809-F1: a module-level import of the evaluator ran third-party code before any check."""

    tree = ast.parse((ROOT / "scripts/evaluate_section_5a.py").read_text(encoding="utf-8"))
    imported = [
        node.module if isinstance(node, ast.ImportFrom) else alias.name
        for node in tree.body
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in (node.names if isinstance(node, ast.Import) else [None])
    ]
    assert imported, "the parse must find the imports, or this check is vacuous"
    for module in imported:
        assert module == "__future__" or module.split(".")[0] in sys.stdlib_module_names, module


def test_the_cli_mode_names_are_the_runner_s() -> None:
    assert cli.MODE_READINESS == runner.MODE_READINESS
    assert cli.MODE_CONSUME == runner.MODE_CONSUME


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


# --------------------------------------------------------------------------- G1: isolation first


@pytest.mark.parametrize("mode", LIVE_MODES)
def test_an_unisolated_process_is_refused_before_anything_is_attested_or_built(
    mode: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The real isolation step, in this (unisolated) process: refusal precedes everything."""

    monkeypatch.setattr(provenance, "attest", lambda *_, **__: pytest.fail("attested"))
    monkeypatch.setattr(cli, "build_repository", lambda: pytest.fail("repository built"))
    refusal = "must start as `python -I -S -B`"
    with pytest.raises(runtime_isolation.IsolationRefused, match=refusal):
        cli.main(_live_argv(mode), environ={})


@pytest.mark.parametrize("mode", LIVE_MODES)
def test_every_live_mode_is_isolated_then_attested_before_any_repository_exists(
    mode: str, calls: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cli, "build_repository", lambda: pytest.fail("repository built"))
    with pytest.raises(provenance.ProvenanceRefused, match="not running inside GitHub Actions"):
        cli.main(_live_argv(mode), environ={})
    assert calls == ["isolation", "attest"]


def test_the_ambient_github_environment_is_not_trusted_by_tests(
    calls: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Facts are observed from the environment the entrypoint is GIVEN, not from os.environ."""

    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setattr(cli, "build_repository", lambda: pytest.fail("repository built"))
    with pytest.raises(provenance.ProvenanceRefused):
        cli.main(["--mode", "readiness", "--expected-sha", SYNTHETIC_SHA], environ={})


def test_a_wrong_expected_sha_refuses_even_for_an_otherwise_verified_run(
    calls: list[str], verified_dispatch, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cli, "build_repository", lambda: pytest.fail("repository built"))
    with pytest.raises(provenance.ProvenanceRefused, match="not expected_sha"):
        cli.main(["--mode", "readiness", "--expected-sha", "b" * 40], environ={})


def test_attest_touches_no_repository_and_verifies_what_loaded(
    calls: list[str],
    verified_dispatch,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    monkeypatch.setattr(cli, "build_repository", lambda: pytest.fail("repository built"))

    def _driver():
        calls.append("driver-loaded-without-connecting")
        return {"cython_runtime": "f" * 64}

    monkeypatch.setattr(cli, "load_database_driver", _driver)
    assert cli.main(["--mode", "attest", "--expected-sha", SYNTHETIC_SHA], environ={}) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["touches_repository"] is False
    assert printed["driver_helpers"] == {"cython_runtime": "f" * 64}
    record = printed["run_provenance"]
    assert record["dispatch_verified"] is True
    assert record["interpreter_flags"] == runtime_isolation.REQUIRED_FLAGS_TEXT
    # L1b: the secret-free attest step proves the post-driver check before anything connects.
    assert calls == [
        "isolation",
        "attest",
        "loaded-modules",
        "driver-loaded-without-connecting",
        "loaded-modules",
    ]


def test_loading_the_database_driver_connects_to_nothing_and_names_its_helpers() -> None:
    """The real import, in a fresh process: no connection attempt, and only pinned-name helpers."""

    probe = (
        "import json, socket, sys\n"
        f"sys.path[:0] = [{str(ROOT)!r}, {str(ROOT / 'src')!r}]\n"
        "def _refuse(*args, **kwargs):\n"
        "    raise AssertionError('the driver import opened a socket')\n"
        "socket.socket.connect = _refuse\n"
        "from scripts import evaluate_section_5a as cli\n"
        "helpers = cli.load_database_driver()\n"
        "print(json.dumps({'helpers': helpers, 'psycopg': 'psycopg' in sys.modules}))\n"
    )
    completed = subprocess.run(
        [sys.executable, "-B", "-c", probe],
        cwd=ROOT,
        env=_scrubbed_environment(),
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr[-2000:]
    seen = json.loads(completed.stdout.strip().splitlines()[-1])
    assert seen["psycopg"] is True
    assert set(seen["helpers"]) <= set(runtime_isolation.DYNAMIC_HELPER_FINGERPRINTS)


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
    mode: str, calls: list[str], verified_dispatch, no_database
) -> None:
    """V807-F3 and G8, after isolation and attestation: an empty store is refused, never used."""

    with pytest.raises(runner.ConsumptionRefused, match="not a durable Postgres authority"):
        cli.main(_live_argv(mode), environ={})
    assert calls == ["isolation", "attest", "loaded-modules"]


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


def test_a_verified_consumption_reverifies_loaded_code_immediately_before_the_claim(
    calls: list[str],
    verified_dispatch,
    fake_seal,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class Recording(fake_seal):
        def claim_section_5a_seal(self, payload) -> bool:
            calls.append("claim")
            return super().claim_section_5a_seal(payload)

    monkeypatch.setattr(cli, "build_repository", lambda: Recording())
    report = tmp_path / "report.json"
    argv = [*_live_argv("consume"), f"--artifact-dir={tmp_path / 'art'}", f"--report={report}"]
    assert cli.main(argv, environ={}) == 0
    assert calls == [
        "isolation",
        "attest",
        "loaded-modules",  # after the evaluator's imports
        "loaded-modules",  # after the repository is built
        "loaded-modules",  # after the pre-claim reads, IMMEDIATELY before the claim
        "claim",
    ]
    record = fake_seal.durable_seal["run_provenance"]
    assert record["dispatch_verified"] is True and record["expected_sha"] == SYNTHETIC_SHA
    written = json.loads(report.read_text(encoding="utf-8"))
    assert written["consumes_one_look"] is True
    assert written["run_provenance"] == record


def test_readiness_repeats_the_loaded_code_check_after_its_reads(
    calls: list[str],
    verified_dispatch,
    fake_seal,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    """L1b. The reads load the driver; readiness then repeats consume's pre-claim check."""

    def _readiness(repository):
        calls.append("readiness-reads")
        return {"mode": runner.MODE_READINESS}

    monkeypatch.setattr(cli, "build_repository", lambda: fake_seal())
    monkeypatch.setattr(runner, "run_readiness", _readiness)
    assert cli.main(_live_argv("readiness"), environ={}) == 0
    assert calls == [
        "isolation",
        "attest",
        "loaded-modules",  # after the evaluator's imports
        "loaded-modules",  # after the repository is built
        "readiness-reads",
        "loaded-modules",  # after the reads, with the driver loaded: consume's pre-claim guard
    ]
    assert json.loads(capsys.readouterr().out)["run_provenance"]["dispatch_verified"] is True


def test_a_readiness_whose_post_read_check_refuses_is_reported_refused(
    calls: list[str],
    verified_dispatch,
    fake_seal,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    seen = {"count": 0}

    def _refuse_after_the_reads(isolation):
        seen["count"] += 1
        if seen["count"] == 3:
            raise runtime_isolation.IsolationRefused("a module came from an unverified origin")
        return 0

    monkeypatch.setattr(cli, "build_repository", lambda: fake_seal())
    monkeypatch.setattr(runner, "run_readiness", lambda repository: {"mode": "readiness"})
    monkeypatch.setattr(cli, "attest_loaded_modules", _refuse_after_the_reads)
    report = tmp_path / "report.json"
    with pytest.raises(runtime_isolation.IsolationRefused):
        cli.main([*_live_argv("readiness"), f"--report={report}"], environ={})
    assert seen["count"] == 3
    written = json.loads(report.read_text(encoding="utf-8"))
    assert written["outcome"] == "REFUSED" and written["error_type"] == "IsolationRefused"


def test_a_loaded_module_refusal_before_the_claim_spends_nothing(
    calls: list[str],
    verified_dispatch,
    fake_seal,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    seen = {"count": 0}

    def _refuse_before_the_claim(isolation):
        seen["count"] += 1
        if seen["count"] == 3:
            raise runtime_isolation.IsolationRefused("a module came from an unverified origin")
        return 0

    monkeypatch.setattr(cli, "attest_loaded_modules", _refuse_before_the_claim)
    repository = fake_seal()
    monkeypatch.setattr(cli, "build_repository", lambda: repository)
    with pytest.raises(runtime_isolation.IsolationRefused):
        cli.main([*_live_argv("consume"), f"--artifact-dir={tmp_path}"], environ={})
    assert fake_seal.durable_seal is None, "no claim was made"
    assert True not in repository.calls, "no probability was read"


# --------------------------------------------------------------------------- V808-R6 reports


def test_a_refusal_is_written_to_the_report_and_still_fails_the_run(tmp_path: Path) -> None:
    report = tmp_path / "nested" / "report.json"
    with pytest.raises(runtime_isolation.IsolationRefused):
        cli.main([*_live_argv("consume"), f"--report={report}"], environ={})
    written = json.loads(report.read_text(encoding="utf-8"))
    assert written["outcome"] == "REFUSED"
    assert written["error_type"] == "IsolationRefused"
    assert "python -I -S -B" in written["detail"]


@pytest.mark.parametrize("mode", LIVE_MODES)
def test_every_live_mode_requires_the_authenticated_wheelhouse(
    mode: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """J1=B: installed code is attested against lock-verified wheels, so they must be named."""

    monkeypatch.setattr(provenance, "attest", lambda *_, **__: pytest.fail("attested"))
    argv = [arg for arg in _live_argv(mode) if not arg.startswith("--wheelhouse")]
    with pytest.raises(runtime_isolation.IsolationRefused, match="--wheelhouse is required"):
        cli.main(argv, environ={})


def test_the_bundled_pip_helper_names_cpython_s_own_wheel(capsys: pytest.CaptureFixture) -> None:
    assert cli.main(["--bundled-pip"]) == 0
    printed = Path(capsys.readouterr().out.strip())
    assert printed.name.startswith("pip-") and printed.suffix == ".whl"
    assert printed.parent.parts[-2:] == ("ensurepip", "_bundled")


def test_the_floating_installer_is_never_removed_outside_the_isolated_job(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Deleting pip must be impossible on a developer's or CI interpreter."""

    monkeypatch.setattr(
        runtime_isolation, "remove_floating_installer", lambda site: pytest.fail("removed")
    )
    with pytest.raises(runtime_isolation.IsolationRefused, match="python -I -S -B"):
        cli.main(["--remove-floating-installer"], environ={"GITHUB_ACTIONS": "true"})
    monkeypatch.setattr(runtime_isolation, "verify_interpreter_isolation", lambda: "isolated")
    with pytest.raises(runtime_isolation.IsolationRefused, match="only inside the GitHub Actions"):
        cli.main(["--remove-floating-installer"], environ={})


def test_an_unexpected_failure_withholds_its_detail_from_the_report(
    calls: list[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
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


# ------------------------------------------------------------------------ as the workflow runs it


def test_the_isolated_entrypoint_refuses_with_a_nonzero_exit(tmp_path: Path) -> None:
    """A real `python -I -S -B` process, a scrubbed environment, a database URL never to be used."""

    report = tmp_path / "section-5a-report.json"
    completed = subprocess.run(
        [
            sys.executable,
            *ISOLATED,
            "scripts/evaluate_section_5a.py",
            *_live_argv("consume"),
            f"--artifact-dir={tmp_path / 'artifact'}",
            f"--report={report}",
        ],
        cwd=ROOT,
        env=_scrubbed_environment(
            # A syntactically valid URL that must never be contacted: refusal precedes any use.
            {"SUPABASE_DB_URL": "postgresql://must-never-be-contacted.invalid/none"}
        ),
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    assert completed.returncode != 0
    written = json.loads(report.read_text(encoding="utf-8"))
    assert written["outcome"] == "REFUSED"
    # A development or CI interpreter's site-packages is refused by isolation. On the evaluation
    # runner isolation passes, and the missing GitHub dispatch refuses instead.
    assert written["error_type"] in {"IsolationRefused", "ProvenanceRefused"}
    assert "refused before" in written["detail"]
    assert not (tmp_path / "artifact").exists(), "nothing was captured"


def test_an_unisolated_entrypoint_process_is_refused() -> None:
    completed = subprocess.run(
        # -B: this process is deliberately unisolated, and must still leave no bytecode behind.
        [sys.executable, "-B", "scripts/evaluate_section_5a.py", *_live_argv("attest")],
        cwd=ROOT,
        env=_scrubbed_environment(),
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    assert completed.returncode != 0
    assert "IsolationRefused" in completed.stderr and "python -I -S -B" in completed.stderr


def test_nothing_third_party_loads_before_an_isolation_refusal() -> None:
    """Observe the isolated process itself: if isolation refuses, only it had been imported."""

    probe = (
        "import json, runpy, sys, sysconfig\n"
        "from pathlib import Path\n"
        f"sys.argv = ['scripts/evaluate_section_5a.py', *{_live_argv('attest')!r}]\n"
        "outcome = 'returned'\n"
        "try:\n"
        "    runpy.run_path('scripts/evaluate_section_5a.py', run_name='__main__')\n"
        "except BaseException as exc:\n"
        "    outcome = type(exc).__name__\n"
        "lib = Path(sysconfig.get_paths()['stdlib']).resolve()\n"
        "site = Path(sysconfig.get_paths()['purelib']).resolve()\n"
        "def stdlib(path):\n"
        "    path = Path(path).resolve()\n"
        "    return path.is_relative_to(lib) and not path.is_relative_to(site)\n"
        "loaded = sorted(\n"
        "    name for name, module in list(sys.modules.items())\n"
        "    if getattr(module, '__file__', None) and not stdlib(module.__file__)\n"
        ")\n"
        "print(json.dumps({'outcome': outcome, 'loaded': loaded}))\n"
    )
    completed = subprocess.run(
        [sys.executable, *ISOLATED, "-c", probe],
        cwd=ROOT,
        env=_scrubbed_environment(),
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    observed = json.loads(completed.stdout.strip().splitlines()[-1])
    if observed["outcome"] == "IsolationRefused":
        assert observed["loaded"] == [
            "crypto_probability_engine",
            "crypto_probability_engine.runtime_isolation",
        ]
    else:  # the evaluation runner: isolation passed, so the dispatch attestation refused
        assert observed["outcome"] == "ProvenanceRefused"
