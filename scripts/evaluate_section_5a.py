#!/usr/bin/env python
"""Section 5A evaluation CLI.

    --mode readiness           repeatable; never consumes the one look
    --mode consume             THE ONE LOOK; requires the confirmation token
    --mode recompute           recover from the DURABLE Postgres seal; never re-reads the holdout
    --mode recompute-artifact  offline audit of a local artifact; no database access
    --write-pin                regenerate the reviewed evaluator pin

Consumption and seal recovery require the repository to POSITIVELY declare itself a durable
Postgres authority. ``build_operator_repository`` silently falls back to an in-memory
repository when no database is configured; a missing secret must refuse, not quietly produce a
process-local seal that dies with the job (finding G8).
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
    """Positive attestation: only a declared durable Postgres authority may seal or recover."""

    authority = repository.section_5a_seal_authority()
    if authority != runner.SEAL_AUTHORITY_POSTGRES:
        raise runner.ConsumptionRefused(
            f"the configured repository is {authority!r}, not a durable Postgres authority; "
            "check that SUPABASE_DB_URL is set. Refusing rather than sealing process-locally."
        )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.write_pin:
        print(json.dumps({"wrote_pin": str(write_pin())}, indent=2))
        return 0

    artifact_dir = Path(args.artifact_dir)

    if args.mode == MODE_RECOMPUTE_ARTIFACT:
        print(json.dumps(runner.recompute_from_snapshot(artifact_dir), indent=2))
        return 0

    repository = build_operator_repository(Settings())

    if args.mode == runner.MODE_READINESS:
        print(json.dumps(runner.run_readiness(repository), indent=2))
        return 0

    require_durable_authority(repository)

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
