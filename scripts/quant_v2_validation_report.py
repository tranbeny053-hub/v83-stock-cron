"""Print deterministic read-only Quant V2 shadow validation diagnostics."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from jsonschema import Draft202012Validator

from crypto_probability_engine.config.settings import Settings
from crypto_probability_engine.persistence.repository import build_operator_repository
from crypto_probability_engine.shadow_validation.schemas import MAX_VALIDATION_ROWS
from crypto_probability_engine.shadow_validation.service import (
    build_shadow_validation_report,
)

ROOT = Path(__file__).resolve().parents[1]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build framework-only Quant V2 shadow validation diagnostics."
    )
    parser.add_argument(
        "--feature-methodology-version",
        default="quant-v2-shadow-v0",
    )
    parser.add_argument("--timeframe")
    parser.add_argument("--since")
    parser.add_argument("--until")
    parser.add_argument("--limit", type=int, default=MAX_VALIDATION_ROWS)
    parser.add_argument("--format", choices=("json", "text"), default="json")
    parser.add_argument("--generated-at-utc")
    args = parser.parse_args(argv)
    if args.limit <= 0:
        parser.error("--limit must be positive")

    generated_at = args.generated_at_utc or datetime.now(tz=UTC).isoformat().replace(
        "+00:00", "Z"
    )
    repository = build_operator_repository(Settings.from_env())
    try:
        report = build_shadow_validation_report(
            repository,
            feature_methodology_version=args.feature_methodology_version,
            timeframe=args.timeframe,
            since=_parse_optional_utc(args.since),
            until=_parse_optional_utc(args.until),
            limit=min(args.limit, MAX_VALIDATION_ROWS),
            generated_at_utc=generated_at,
        )
        schema = json.loads(
            (ROOT / "schemas" / "quant_v2_validation_report.schema.json").read_text()
        )
        Draft202012Validator(schema).validate(report)
        print(_text_report(report) if args.format == "text" else _json_report(report))
    except Exception as exc:
        print(json.dumps({"status": "ERROR", "error_class": type(exc).__name__}))
        return 1
    finally:
        close = getattr(repository, "close", None)
        if callable(close):
            close()
    return 0


def _json_report(report: dict) -> str:
    return json.dumps(report, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _text_report(report: dict) -> str:
    coverage = report["coverage_summary"]["eligible_era"]
    return "\n".join(
        (
            f"status: {report['overall_status']}",
            f"repository: {report['repository']}",
            f"framework_mode: {report['framework_mode']}",
            f"eligible_snapshot_outcome_joins: {coverage['snapshot_outcome_joins']}",
            f"cohorts: {len(report['cohort_summary'])}",
            f"feature_reports: {len(report['feature_reports'])}",
            "holdout_status: SEALED_NOT_EVALUATED",
            "promotion_eligible: false",
        )
    )


def _parse_optional_utc(value: str | None) -> datetime | None:
    if value is None:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Time bounds must include a timezone.")
    return parsed.astimezone(UTC)


if __name__ == "__main__":
    raise SystemExit(main())
