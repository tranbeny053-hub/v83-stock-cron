#!/usr/bin/env python
"""Section 5A evaluation CLI.

    --mode attest              verify dispatch, runtime and pin; touches no repository
    --mode readiness           repeatable; never consumes the one look
    --mode consume             THE ONE LOOK; requires the confirmation token
    --mode recompute           recover from the DURABLE Postgres seal; never re-reads the holdout
    --mode recompute-artifact  offline audit of a local artifact; no database access
    --write-pin                regenerate the reviewed evaluator pin

Every live mode (attest, readiness, consumption and seal recovery) first ATTESTS the run: a manual
dispatch of the evaluation workflow on main, at exactly ``--expected-sha``, under the pinned
interpreter and the hash-locked dependency set (owner rulings E2=A, E3=A). Only then is a
repository built, and it must POSITIVELY declare itself a durable Postgres authority.

V807-F3: this entrypoint used to build ``Settings()``, which does not read the environment, so
even with SUPABASE_DB_URL set it silently constructed an EMPTY in-memory repository. Readiness
would then have reported zero evidence everywhere — a false "the frame failed" rather than a
refusal. Settings now come from the environment, exactly as every other production script does,
and readiness refuses a non-durable repository instead of reporting on one.

V808-R6: the workflow used to pipe this command into ``tee``. Without pipefail a refusal then
exited 0 and the run showed green. The outcome is now written by ``--report``, with no pipe, and
a refusal is both recorded in that report and a non-zero exit.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from crypto_probability_engine.config.settings import Settings
from crypto_probability_engine.oos.evaluation import provenance, runner
from crypto_probability_engine.oos.evaluation.evaluator_pin import EvaluatorPinMismatch, write_pin
from crypto_probability_engine.persistence.repository import build_operator_repository

DEFAULT_ARTIFACT_DIR = Path(".work/section_5a")
MODE_ATTEST = "attest"
MODE_RECOMPUTE = "recompute"
MODE_RECOMPUTE_ARTIFACT = "recompute-artifact"

# Refusals this evaluator raises on purpose. Their messages name no secret, so the report may
# carry them; any other failure is reported by type only, and its detail stays in the job log.
_REFUSALS = (
    provenance.ProvenanceRefused,
    runner.ConsumptionRefused,
    runner.ReadinessRefused,
    runner.OneLookAlreadyConsumed,
    runner.SnapshotTampered,
    EvaluatorPinMismatch,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode",
        choices=[
            MODE_ATTEST,
            runner.MODE_READINESS,
            runner.MODE_CONSUME,
            MODE_RECOMPUTE,
            MODE_RECOMPUTE_ARTIFACT,
        ],
        default=runner.MODE_READINESS,
    )
    parser.add_argument(
        "--confirm",
        default="",
        help=f"required for --mode consume: {runner.CONFIRMATION_TOKEN}",
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
        "--write-pin",
        action="store_true",
        help="regenerate ops/section_5a_evaluator_pin.json and exit",
    )
    return parser


def require_durable_authority(repository) -> None:
    """Positive attestation for every live mode; readiness included."""

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

    return build_operator_repository(Settings.from_env())


def main(argv: list[str] | None = None, *, environ: Mapping[str, str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.write_pin:
        print(json.dumps({"wrote_pin": str(write_pin())}, indent=2))
        return 0

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


def _run(args: argparse.Namespace, environ: Mapping[str, str]) -> dict[str, Any]:
    artifact_dir = Path(args.artifact_dir)

    if args.mode == MODE_RECOMPUTE_ARTIFACT:
        return runner.recompute_from_snapshot(artifact_dir)

    # E2=A, E3=A: every remaining mode is live. Attest BEFORE any repository exists.
    record = provenance.attest(args.expected_sha, environ=environ)
    if args.mode == MODE_ATTEST:
        return {"mode": MODE_ATTEST, "touches_repository": False, "run_provenance": record}

    repository = build_repository()
    require_durable_authority(repository)

    if args.mode == runner.MODE_READINESS:
        return {**runner.run_readiness(repository), "run_provenance": record}

    if args.mode == MODE_RECOMPUTE:
        return {**runner.recompute_from_seal(repository), "recovery_run_provenance": record}

    return runner.run_consumption(
        repository,
        confirmation=args.confirm,
        artifact_dir=artifact_dir,
        provenance=record,
    )


def _refusal_record(mode: str, exc: BaseException) -> dict[str, Any]:
    refused = isinstance(exc, _REFUSALS)
    return {
        "mode": mode,
        "outcome": "REFUSED" if refused else "FAILED",
        "error_type": type(exc).__name__,
        "detail": str(exc)
        if refused
        else "unexpected failure; the detail is withheld from this report, see the job log",
    }


def _write_report(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    sys.exit(main())
