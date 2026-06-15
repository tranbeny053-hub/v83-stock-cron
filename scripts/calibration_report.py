"""Print read-only calibration diagnostics for resolved UCPE prediction outcomes."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence

from crypto_probability_engine.calibration.service import build_calibration_report
from crypto_probability_engine.config.settings import Settings
from crypto_probability_engine.persistence.repository import build_persistence_repository


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a read-only UCPE calibration report.")
    parser.add_argument("--timeframe")
    parser.add_argument("--symbol")
    parser.add_argument("--model-version")
    parser.add_argument("--methodology-version")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--since")
    parser.add_argument("--until")
    parser.add_argument("--format", choices=("json", "text"), default="json")
    args = parser.parse_args(argv)

    settings = Settings.from_env()
    repository = build_persistence_repository(settings)
    try:
        report = build_calibration_report(
            repository,
            timeframe=args.timeframe,
            symbol=args.symbol,
            model_version=args.model_version,
            methodology_version=args.methodology_version,
            since=args.since,
            until=args.until,
            limit=args.limit,
        )
    except Exception as exc:
        print(json.dumps({"status": "ERROR", "error_type": type(exc).__name__}, sort_keys=True))
        return 1

    if args.format == "text":
        print(_text_report(report))
    else:
        print(json.dumps(report, indent=2, sort_keys=True))
    close = getattr(repository, "close", None)
    if callable(close):
        close()
    return 0


def _text_report(report: dict) -> str:
    return "\n".join(
        (
            f"status: {report['status']}",
            f"repository: {report['repository']}",
            f"sample_gate: {report['sample_gate']}",
            f"sample_count: {report['sample_count']}",
            f"valid_count: {report['valid_count']}",
            f"invalid_row_count: {report['invalid_row_count']}",
            f"brier_score: {report['metrics'].get('brier_score')}",
            f"log_loss: {report['metrics'].get('log_loss')}",
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
