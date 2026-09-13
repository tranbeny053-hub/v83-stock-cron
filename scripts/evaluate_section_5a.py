#!/usr/bin/env python
"""Section 5A evaluation CLI.

    --mode readiness           repeatable; never consumes the one look
    --mode consume             THE ONE LOOK; requires the confirmation token
    --mode recompute           recover from the DURABLE Postgres seal; never re-reads the holdout
    --mode recompute-artifact  offline audit of a local artifact; no database access
    --write-pin                regenerate the reviewed evaluator pin

Every live mode — readiness, consumption and seal recovery — requires the repository to
POSITIVELY declare itself a durable Postgres authority.

V807-F3: this entrypoint used to build ``Settings()``, which does not read the environment, so
even with SUPABASE_DB_URL set it silently constructed an EMPTY in-memory repository. Readiness
would then have reported zero evidence everywhere — a false "the frame failed" rather than a
refusal. Settings now come from the environment, exactly as every other production script does,
and readiness refuses a non-durable repository instead of reporting on one.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from crypto_probability_engine.config.settings import Settings
from crypto_probability_engine.oos.evaluation import runner
from crypto_probability_engine.oos.evaluation.evaluator_pin import write_pin
from crypto_probability_engine.persistence.repository import build_operator_repository

DEFAULT_ARTIFACT_DIR = Path(".work/section_5a")
MODE_RECOMPUTE = "recompute"
MODE_RECOMPUTE_ARTIFACT = "recompute-artifact"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode",
        choices=[
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
    parser.add_argument("--artifact-dir", default=str(DEFAULT_ARTIFACT_DIR))
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


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.write_pin:
        print(json.dumps({"wrote_pin": str(write_pin())}, indent=2))
        return 0

    artifact_dir = Path(args.artifact_dir)

    if args.mode == MODE_RECOMPUTE_ARTIFACT:
        print(json.dumps(runner.recompute_from_snapshot(artifact_dir), indent=2))
        return 0

    repository = build_repository()
    require_durable_authority(repository)

    if args.mode == runner.MODE_READINESS:
        print(json.dumps(runner.run_readiness(repository), indent=2))
        return 0

    if args.mode == MODE_RECOMPUTE:
        print(json.dumps(runner.recompute_from_seal(repository), indent=2))
        return 0

    result = runner.run_consumption(
        repository, confirmation=args.confirm, artifact_dir=artifact_dir
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    sys.exit(main())
