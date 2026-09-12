#!/usr/bin/env python
"""Section 5A evaluation CLI.

    --mode readiness   repeatable; never consumes the one look
    --mode consume     THE ONE LOOK; requires the confirmation token
    --mode recompute   recompute from the immutable snapshot; no database access
    --write-pin        regenerate the reviewed evaluator pin

Readiness never loads a probability, so it cannot compute a score even by mistake.
Consumption arms the seal at the raw capture, before any statistic runs, because the
look is spent the moment the probabilities are read.
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode",
        choices=[runner.MODE_READINESS, runner.MODE_CONSUME, "recompute"],
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


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.write_pin:
        path = write_pin()
        print(json.dumps({"wrote_pin": str(path)}, indent=2))
        return 0

    artifact_dir = Path(args.artifact_dir)

    if args.mode == "recompute":
        print(json.dumps(runner.recompute_from_snapshot(artifact_dir), indent=2))
        return 0

    repository = build_operator_repository(Settings())

    if args.mode == runner.MODE_READINESS:
        print(json.dumps(runner.run_readiness(repository), indent=2))
        return 0

    result = runner.run_consumption(
        repository, confirmation=args.confirm, artifact_dir=artifact_dir
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    sys.exit(main())
