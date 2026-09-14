#!/usr/bin/env python
"""Section 5A evaluation CLI.

    --mode attest              verify isolation, dispatch, runtime and pin; touches no repository
    --mode readiness           repeatable; never consumes the one look
    --mode consume             THE ONE LOOK; requires the confirmation token
    --mode recompute           recover from the DURABLE Postgres seal; never re-reads the holdout
    --mode recompute-artifact  offline audit of a local artifact; no database access
    --write-pin                regenerate the reviewed evaluator pin

Every live mode (attest, readiness, consumption, seal recovery) runs in a process started as
``python -I -S -B`` (owner ruling G1=A). Before any module beyond the standard library can load,
:mod:`crypto_probability_engine.runtime_isolation` verifies:
- the interpreter's isolation;
- its import surface: exactly the hash-locked site-packages and a checkout with no untracked code;
- the only import path: stdlib, then verified site-packages, then the reviewed source.

Only then are the evaluator and its dependencies imported. The run is then ATTESTED: a manual
dispatch on main at exactly ``--expected-sha``, under the pinned interpreter and lock (E2=A, E3=A).
The origin of every loaded module is verified, and verified again immediately before the one-look
claim. Only then is a repository built, and it must POSITIVELY declare itself a durable Postgres
authority.

THIS FILE IMPORTS ONLY THE STANDARD LIBRARY AT MODULE LEVEL. Everything else is imported inside
functions, after isolation is verified. V809-F1: importing the repository at module level ran
third-party code before anything was checked.

V807-F3: this entrypoint used to build ``Settings()``, which does not read the environment. With
SUPABASE_DB_URL set it still silently constructed an EMPTY in-memory repository, and readiness
would have reported zero evidence everywhere — a false "the frame failed" rather than a refusal.
Settings now come from the environment, exactly as every other production script does.

V808-R6: the workflow used to pipe this command into ``tee``. Without pipefail a refusal then
exited 0 and the run showed green. The outcome is now written by ``--report``, with no pipe, and a
refusal is both recorded in that report and a non-zero exit.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src"
DEFAULT_ARTIFACT_DIR = Path(".work/section_5a")

MODE_ATTEST = "attest"
MODE_READINESS = "readiness"  # runner.MODE_READINESS; equality is asserted by test
MODE_CONSUME = "consume"  # runner.MODE_CONSUME; equality is asserted by test
MODE_RECOMPUTE = "recompute"
MODE_RECOMPUTE_ARTIFACT = "recompute-artifact"
LIVE_MODES = (MODE_ATTEST, MODE_READINESS, MODE_CONSUME, MODE_RECOMPUTE)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode",
        choices=[*LIVE_MODES, MODE_RECOMPUTE_ARTIFACT],
        default=MODE_READINESS,
    )
    parser.add_argument(
        "--confirm",
        default="",
        help="required for --mode consume: the exact confirmation token",
    )
    parser.add_argument(
        "--expected-sha",
        default="",
        help="required for every live mode: the full commit SHA the owner reviewed and dispatched",
    )
    parser.add_argument("--artifact-dir", default=str(DEFAULT_ARTIFACT_DIR))
    parser.add_argument(
        "--report",
        default=None,
        help="also write this run's outcome, success or refusal, as JSON to this path",
    )
    parser.add_argument(
        "--wheelhouse",
        default="",
        help="required for every live mode: the directory of lock-authenticated wheels installed",
    )
    parser.add_argument(
        "--write-pin",
        action="store_true",
        help="regenerate ops/section_5a_evaluator_pin.json and exit",
    )
    parser.add_argument(
        "--bundled-pip",
        action="store_true",
        help="print the pip wheel CPython bundles (the only trusted installer) and exit",
    )
    parser.add_argument(
        "--remove-floating-installer",
        action="store_true",
        help="in the isolated evaluation job only: delete the runner's unverified pip, unrun",
    )
    return parser


def ensure_source_path() -> None:
    """Make the first-party source importable, AFTER the interpreter's own library."""

    if str(SOURCE) not in sys.path:
        sys.path.append(str(SOURCE))


def enter_isolated_runtime(wheelhouse: str):
    """G1=A, J1=B: verify the isolated process and its authenticated import surface first.

    The source root is appended first, so that the standard-library-only isolation module itself
    can be imported, and nothing else has been added to the import path.
    """

    ensure_source_path()
    from crypto_probability_engine import runtime_isolation

    if not wheelhouse:
        raise runtime_isolation.IsolationRefused(
            "section 5A run refused before the one look could be claimed: --wheelhouse is "
            "required; installed code is authenticated against the lock-verified wheels"
        )
    return runtime_isolation.enter(ROOT, wheelhouse=Path(wheelhouse))


def attest_loaded_modules(isolation) -> int:
    """G1=A: every module loaded so far came from the stdlib, a locked file, or the pin."""

    from crypto_probability_engine import runtime_isolation
    from crypto_probability_engine.oos.evaluation.evaluator_pin import pinned_files

    return runtime_isolation.attest_loaded_modules(
        isolation, pinned=pinned_files(ROOT), root=ROOT
    )


def load_database_driver() -> dict[str, str]:
    """Import the locked database driver WITHOUT connecting; name the dynamic helpers it created.

    Owner ruling L1b. The attest step runs on the real runner before any step holds the secret, so
    the loaded-module check that guards every connection and the claim is proven there first.
    """

    import psycopg  # noqa: F401
    import psycopg_pool  # noqa: F401

    from crypto_probability_engine import runtime_isolation

    return runtime_isolation.loaded_dynamic_helpers()


def require_durable_authority(repository) -> None:
    """Positive attestation for every live mode; readiness included."""

    from crypto_probability_engine.oos.evaluation import runner

    declare = getattr(repository, "section_5a_seal_authority", None)
    authority = declare() if callable(declare) else None
    if authority != runner.SEAL_AUTHORITY_POSTGRES:
        raise runner.ConsumptionRefused(
            f"the configured repository is {authority!r}, not a durable Postgres authority; "
            "check that SUPABASE_DB_URL is set. Refusing rather than reading or sealing "
            "process-locally."
        )


def build_repository():
    """The ONE way this entrypoint obtains its repository: from the environment (V807-F3)."""

    from crypto_probability_engine.config.settings import Settings
    from crypto_probability_engine.persistence.repository import build_operator_repository

    return build_operator_repository(Settings.from_env())


def main(argv: list[str] | None = None, *, environ: Mapping[str, str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.write_pin:
        ensure_source_path()
        from crypto_probability_engine.oos.evaluation.evaluator_pin import write_pin

        print(json.dumps({"wrote_pin": str(write_pin())}, indent=2))
        return 0

    if args.bundled_pip or args.remove_floating_installer:
        return _installer_action(args, os.environ if environ is None else environ)

    try:
        outcome = _run(args, os.environ if environ is None else environ)
    except Exception as exc:
        if args.report:
            _write_report(Path(args.report), _refusal_record(args.mode, exc))
        raise
    print(json.dumps(outcome, indent=2))
    if args.report:
        _write_report(Path(args.report), outcome)
    return 0


def _installer_action(args: argparse.Namespace, environ: Mapping[str, str]) -> int:
    """J1=B install-step helpers. Standard library only; nothing third-party is imported."""

    ensure_source_path()
    from crypto_probability_engine import runtime_isolation

    if args.bundled_pip:
        print(runtime_isolation.bundled_pip_wheel())
        return 0
    # Deleting pip is safe only in the isolated evaluation job, never on a developer's interpreter.
    runtime_isolation.verify_interpreter_isolation()
    if environ.get("GITHUB_ACTIONS") != "true":
        raise runtime_isolation.IsolationRefused(
            "--remove-floating-installer runs only inside the GitHub Actions evaluation job"
        )
    site = runtime_isolation.single_site_directory()
    print(json.dumps({"removed": runtime_isolation.remove_floating_installer(site)}))
    return 0


def _run(args: argparse.Namespace, environ: Mapping[str, str]) -> dict[str, Any]:
    artifact_dir = Path(args.artifact_dir)

    if args.mode == MODE_RECOMPUTE_ARTIFACT:
        ensure_source_path()
        from crypto_probability_engine.oos.evaluation import runner

        return runner.recompute_from_snapshot(artifact_dir)

    # Every remaining mode is live. Isolation FIRST: nothing third-party may load before it.
    isolation = enter_isolated_runtime(args.wheelhouse)

    from crypto_probability_engine.oos.evaluation import provenance, runner

    # E2=A, E3=A: attest the dispatch and runtime, then verify what actually loaded.
    record = provenance.attest(args.expected_sha, environ=environ, isolation=isolation)
    attest_loaded_modules(isolation)
    if args.mode == MODE_ATTEST:
        driver_helpers = load_database_driver()
        attest_loaded_modules(isolation)
        return {
            "mode": MODE_ATTEST,
            "touches_repository": False,
            "driver_helpers": driver_helpers,
            "run_provenance": record,
        }

    repository = build_repository()
    require_durable_authority(repository)
    attest_loaded_modules(isolation)

    if args.mode == MODE_READINESS:
        outcome = runner.run_readiness(repository)
        # Owner ruling L1b: the reads load the database driver, so readiness repeats the loaded-code
        # check consume makes before its claim. A readiness run rehearses that guard faithfully.
        attest_loaded_modules(isolation)
        return {**outcome, "run_provenance": record}

    if args.mode == MODE_RECOMPUTE:
        return {**runner.recompute_from_seal(repository), "recovery_run_provenance": record}

    return runner.run_consumption(
        repository,
        confirmation=args.confirm,
        artifact_dir=artifact_dir,
        provenance=record,
        runtime_guard=lambda: attest_loaded_modules(isolation),
    )


def _refusal_record(mode: str, exc: BaseException) -> dict[str, Any]:
    """Deliberate refusals name no secret; any other failure is reported by type only."""

    refused = _is_refusal(exc)
    return {
        "mode": mode,
        "outcome": "REFUSED" if refused else "FAILED",
        "error_type": type(exc).__name__,
        "detail": str(exc)
        if refused
        else "unexpected failure; the detail is withheld from this report, see the job log",
    }


def _is_refusal(exc: BaseException) -> bool:
    """Classify without importing anything new: an error path must not load unverified code."""

    ensure_source_path()
    from crypto_probability_engine.runtime_isolation import ProvenanceRefused  # stdlib-only

    if isinstance(exc, ProvenanceRefused):
        return True
    deliberate = []
    for module_name, names in (
        (
            "crypto_probability_engine.oos.evaluation.runner",
            (
                "ConsumptionRefused",
                "ReadinessRefused",
                "OneLookAlreadyConsumed",
                "SnapshotTampered",
            ),
        ),
        ("crypto_probability_engine.oos.evaluation.evaluator_pin", ("EvaluatorPinMismatch",)),
    ):
        module = sys.modules.get(module_name)
        if module is not None:
            deliberate.extend(getattr(module, name) for name in names)
    return isinstance(exc, tuple(deliberate))


def _write_report(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    sys.exit(main())
