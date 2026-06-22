"""Manual-only, bounded derivatives shadow-evidence collector.

The collector is dormant unless its process-local enable gate is exactly true.
It delegates analysis identity and persistence to the approved runtime services;
it does not construct persistence rows or issue database statements itself.

The current full four-cell matrix has a finite worst-case ceiling of 58 logical
public requests and 98 HTTP attempts. Failed spot registry reads are not cached,
spot calls use the existing one-retry policy, and the 60-second derivatives
symbol cache may expire between slow cells. Derivatives calls do not retry.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from crypto_probability_engine.api.analysis_service import (
    _peek_prediction_persistence,
    analyze_request,
    persist_analysis_now,
)
from crypto_probability_engine.api.schemas import AnalysisRequest
from crypto_probability_engine.config.settings import Settings
from crypto_probability_engine.persistence.repository import build_operator_repository
from crypto_probability_engine.persistence.run_store import InMemoryRunStore

COLLECTOR_VERSION = "derivatives-evidence-collector.v0"
ENABLE_ENV = "UCPE_DERIV_CADENCE_ENABLED"
WRITE_CONFIRMATION = "WRITE-EVIDENCE"
SCHEDULED_ORIGIN = "SCHEDULED_SHADOW_EVIDENCE"
DERIVATIVES_METHODOLOGY = "deriv-intel-shadow-v0"
RUN_ID_PATTERN = re.compile(r"^cadence-[0-9a-f]{32}$")

MAX_MATRIX_CELLS = 4
MAX_NEW_PREDICTIONS = 4
MAX_NEW_DERIVATIVES_SNAPSHOTS = 4
MATRIX = (
    ("BTC/USDT", "1H"),
    ("BTC/USDT", "4H"),
    ("ETH/USDT", "1H"),
    ("ETH/USDT", "4H"),
)
SPOT_PROVIDER_COUNT = 2
SPOT_CALLS_PER_PROVIDER_CELL = 5  # registry plus four current market resources
SPOT_ATTEMPTS_PER_CALL = 2
DERIVATIVES_PROVIDER_COUNT = 2
DERIVATIVES_CURRENT_CALLS_PER_PROVIDER_SYMBOL = 2
DERIVATIVES_REGISTRY_CALLS = 2
FULL_MATRIX_LOGICAL_REQUEST_CAP = (
    len(MATRIX) * SPOT_PROVIDER_COUNT * SPOT_CALLS_PER_PROVIDER_CELL
    + DERIVATIVES_REGISTRY_CALLS
    + DERIVATIVES_PROVIDER_COUNT
    * len(MATRIX)
    * DERIVATIVES_CURRENT_CALLS_PER_PROVIDER_SYMBOL
)
FULL_MATRIX_HTTP_ATTEMPT_CAP = (
    len(MATRIX)
    * SPOT_PROVIDER_COUNT
    * SPOT_CALLS_PER_PROVIDER_CELL
    * SPOT_ATTEMPTS_PER_CALL
    + DERIVATIVES_REGISTRY_CALLS
    + DERIVATIVES_PROVIDER_COUNT
    * len(MATRIX)
    * DERIVATIVES_CURRENT_CALLS_PER_PROVIDER_SYMBOL
)

MATRIX_SCOPES = {
    "FULL_4_CELL": MATRIX,
    "BTC_ONLY": MATRIX[:2],
    "ETH_ONLY": MATRIX[2:],
}
CELL_RESULT_FIELDS = frozenset(
    {
        "symbol",
        "timeframe",
        "run_id",
        "prediction_id",
        "reference_close_utc",
        "classification",
        "provider_status",
        "prediction_status",
        "derivatives_snapshot_status",
    }
)
CELL_CLASSIFICATIONS = frozenset(
    {
        "INSERTED",
        "ALREADY_EXISTS",
        "SKIPPED_DISABLED",
        "SKIPPED_DRY_RUN",
        "SKIPPED_REFERENCE_UNCERTAIN",
        "PROVIDER_DEGRADED",
        "PROVIDER_UNAVAILABLE",
        "PARTIAL_PERSISTENCE",
        "FAILED_SAFETY_INVARIANT",
        "FAILED",
    }
)
REPORT_FIELDS = frozenset(
    {
        "collector_version",
        "enabled",
        "dry_run",
        "matrix_scope",
        "matrix_cells",
        "started_at_utc",
        "elapsed_seconds",
        "new_predictions",
        "new_derivatives_snapshots",
        "duplicates",
        "skipped",
        "failed",
        "cap_status",
        "final_classification",
        "exit_code",
    }
)


@dataclass(frozen=True)
class CollectorOptions:
    dry_run: bool = True
    confirm_write: str = ""
    matrix_scope: str = "FULL_4_CELL"


@dataclass(frozen=True)
class CollectorDependencies:
    analyze: Callable[..., dict] = analyze_request
    persist: Callable[[dict, object], dict[str, object]] = persist_analysis_now
    inspect_pending: Callable[[dict], tuple[list[dict], list[dict], bool, list[dict], bool]] = (
        _peek_prediction_persistence
    )
    repository_factory: Callable[[Settings], object] = build_operator_repository
    run_store_factory: Callable[[], InMemoryRunStore] = InMemoryRunStore
    now_utc: Callable[[], datetime] = lambda: datetime.now(UTC)
    monotonic: Callable[[], float] = time.monotonic


DEFAULT_DEPENDENCIES = CollectorDependencies()


def parse_bool(value: str) -> bool:
    """Parse only explicit true/false CLI values."""

    normalized = value.lower()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    raise argparse.ArgumentTypeError("expected exactly true or false")


def parse_args(argv: Sequence[str] | None = None) -> CollectorOptions:
    parser = argparse.ArgumentParser(description="Collect bounded derivatives shadow evidence.")
    parser.add_argument("--dry-run", type=parse_bool, default=True)
    parser.add_argument("--confirm-write", default="")
    parser.add_argument(
        "--matrix-scope",
        choices=tuple(MATRIX_SCOPES),
        default="FULL_4_CELL",
    )
    args = parser.parse_args(argv)
    return CollectorOptions(
        dry_run=args.dry_run,
        confirm_write=args.confirm_write,
        matrix_scope=args.matrix_scope,
    )


def run_collector(
    options: CollectorOptions,
    *,
    environ: Mapping[str, str],
    dependencies: CollectorDependencies = DEFAULT_DEPENDENCIES,
) -> dict[str, Any]:
    """Run one bounded matrix and return the strict allowlisted report."""

    started_dt = _require_utc(dependencies.now_utc())
    started_mono = dependencies.monotonic()
    cells = _validated_cells(options.matrix_scope)

    gate = _enable_gate(environ.get(ENABLE_ENV))
    if gate == "DISABLED":
        results = [_blank_cell(*cell, "SKIPPED_DISABLED") for cell in cells]
        return _report(
            options,
            enabled=False,
            results=results,
            started_dt=started_dt,
            elapsed=_elapsed(started_mono, dependencies.monotonic),
            skipped=len(results),
            final_classification="DISABLED",
            exit_code=0,
        )
    if gate == "INVALID":
        return _report(
            options,
            enabled=False,
            results=[],
            started_dt=started_dt,
            elapsed=_elapsed(started_mono, dependencies.monotonic),
            failed=1,
            final_classification="CONFIGURATION_ERROR",
            exit_code=1,
        )

    if not options.dry_run and options.confirm_write != WRITE_CONFIRMATION:
        return _report(
            options,
            enabled=True,
            results=[],
            started_dt=started_dt,
            elapsed=_elapsed(started_mono, dependencies.monotonic),
            failed=1,
            final_classification="CONFIRMATION_REQUIRED",
            exit_code=1,
        )

    database_url: str | None = None
    if not options.dry_run:
        database_url = environ.get("SUPABASE_DB_URL")
        if not database_url:
            return _report(
                options,
                enabled=True,
                results=[],
                started_dt=started_dt,
                elapsed=_elapsed(started_mono, dependencies.monotonic),
                failed=1,
                final_classification="CONFIGURATION_ERROR",
                exit_code=1,
            )

    settings = Settings.model_validate(
        {
            "data_mode": "live",
            "enable_derivatives_intel": True,
            "supabase_db_url": database_url,
            "external_store_configured": bool(database_url),
        }
    )
    run_store = dependencies.run_store_factory()
    repository = (
        None if options.dry_run else dependencies.repository_factory(settings)
    )

    results: list[dict[str, object]] = []
    new_predictions = 0
    new_derivatives_snapshots = 0
    duplicates = 0
    skipped = 0
    failed = 0
    cap_status = "OK"

    for symbol, timeframe in cells:
        result = _process_cell(
            symbol,
            timeframe,
            options=options,
            settings=settings,
            run_store=run_store,
            repository=repository,
            dependencies=dependencies,
        )
        results.append(result)
        classification = str(result["classification"])
        derivative_status = result["derivatives_snapshot_status"]
        if derivative_status == "INSERTED":
            new_predictions += 1
            new_derivatives_snapshots += 1
        elif derivative_status == "IDENTICAL_DUPLICATE":
            duplicates += 1
        if classification.startswith("SKIPPED_"):
            skipped += 1
        if classification in {
            "PROVIDER_UNAVAILABLE",
            "PARTIAL_PERSISTENCE",
            "FAILED_SAFETY_INVARIANT",
            "FAILED",
            "SKIPPED_REFERENCE_UNCERTAIN",
        }:
            failed += 1
        if (
            new_predictions > MAX_NEW_PREDICTIONS
            or new_derivatives_snapshots > MAX_NEW_DERIVATIVES_SNAPSHOTS
        ):
            cap_status = "BREACHED"
            failed += 1
            break

    final_classification, exit_code = _final_result(
        options=options,
        results=results,
        cap_status=cap_status,
    )
    return _report(
        options,
        enabled=True,
        results=results,
        started_dt=started_dt,
        elapsed=_elapsed(started_mono, dependencies.monotonic),
        new_predictions=new_predictions,
        new_derivatives_snapshots=new_derivatives_snapshots,
        duplicates=duplicates,
        skipped=skipped,
        failed=failed,
        cap_status=cap_status,
        final_classification=final_classification,
        exit_code=exit_code,
    )


def _process_cell(
    symbol: str,
    timeframe: str,
    *,
    options: CollectorOptions,
    settings: Settings,
    run_store: InMemoryRunStore,
    repository: object | None,
    dependencies: CollectorDependencies,
) -> dict[str, object]:
    result = _blank_cell(symbol, timeframe, "FAILED")
    try:
        payload = dependencies.analyze(
            AnalysisRequest(symbol=symbol, timeframe=timeframe),
            settings=settings,
            run_store=run_store,
            prediction_origin=SCHEDULED_ORIGIN,
            deterministic_identity=True,
        )
    except Exception:
        return result

    run_id = payload.get("run_id")
    result["run_id"] = run_id if isinstance(run_id, str) else None
    identity = _validated_pending_identity(
        payload,
        symbol=symbol,
        timeframe=timeframe,
        inspect_pending=dependencies.inspect_pending,
    )
    if identity is None:
        result["classification"] = "SKIPPED_REFERENCE_UNCERTAIN"
        return result
    result.update(
        prediction_id=identity["prediction_id"],
        reference_close_utc=identity["reference_close_utc"],
    )

    block = payload.get("derivatives_intelligence")
    provider_status = block.get("block_status") if isinstance(block, Mapping) else None
    result["provider_status"] = provider_status if isinstance(provider_status, str) else None
    if not _safety_invariants_hold(payload, identity):
        result["classification"] = "FAILED_SAFETY_INVARIANT"
        return result

    if options.dry_run:
        result["classification"] = (
            "PROVIDER_UNAVAILABLE"
            if provider_status == "UNAVAILABLE"
            else "SKIPPED_DRY_RUN"
        )
        return result

    if repository is None:
        return result
    confirmation = dependencies.persist(payload, repository)
    if not isinstance(confirmation, Mapping):
        return result
    prediction_status = _optional_text(confirmation.get("prediction"))
    derivatives_status = _optional_text(confirmation.get("derivatives_snapshot"))
    overall = _optional_text(confirmation.get("overall"))
    result["prediction_status"] = prediction_status
    result["derivatives_snapshot_status"] = derivatives_status

    prediction_accepted = prediction_status in {"OK", "STATELESS"}
    derivatives_accepted = derivatives_status in {
        "INSERTED",
        "IDENTICAL_DUPLICATE",
    }
    if provider_status == "UNAVAILABLE":
        result["classification"] = "PROVIDER_UNAVAILABLE"
    elif overall == "OK" and prediction_accepted and derivatives_status == "INSERTED":
        result["classification"] = "INSERTED"
    elif (
        overall == "OK"
        and prediction_accepted
        and derivatives_status == "IDENTICAL_DUPLICATE"
    ):
        result["classification"] = "ALREADY_EXISTS"
    elif prediction_accepted and (overall == "PARTIAL" or not derivatives_accepted):
        result["classification"] = "PARTIAL_PERSISTENCE"
    else:
        result["classification"] = "FAILED"
    return result


def _validated_pending_identity(
    payload: dict,
    *,
    symbol: str,
    timeframe: str,
    inspect_pending: Callable[[dict], tuple[list[dict], list[dict], bool, list[dict], bool]],
) -> dict[str, object] | None:
    run_id = payload.get("run_id")
    if not isinstance(run_id, str) or RUN_ID_PATTERN.fullmatch(run_id) is None:
        return None
    try:
        predictions, _, feature_failed, _, derivatives_failed = inspect_pending(payload)
    except Exception:
        return None
    if feature_failed or derivatives_failed or len(predictions) != 1:
        return None
    row = predictions[0]
    if not isinstance(row, Mapping):
        return None
    prediction_id = row.get("prediction_id")
    reference_close = row.get("reference_close_utc")
    if (
        row.get("run_id") != run_id
        or prediction_id != f"{run_id}:{timeframe}"
        or row.get("timeframe") != timeframe
        or row.get("prediction_origin") != SCHEDULED_ORIGIN
        or row.get("symbol") != symbol
        or not isinstance(reference_close, str)
        or not reference_close
    ):
        return None
    return {
        "prediction_id": prediction_id,
        "prediction_origin": row.get("prediction_origin"),
        "reference_close_utc": reference_close,
    }


def _safety_invariants_hold(payload: dict, identity: Mapping[str, object]) -> bool:
    block = payload.get("derivatives_intelligence")
    if not isinstance(block, Mapping):
        return False
    if identity.get("prediction_origin") != SCHEDULED_ORIGIN:
        return False
    if block.get("methodology_version") != DERIVATIVES_METHODOLOGY:
        return False
    if block.get("influence_mode") != "SHADOW_ONLY":
        return False
    if block.get("decision_influence_frac") != 0.0:
        return False
    if block.get("block_status") not in {"ACTIVE", "DEGRADED", "UNAVAILABLE"}:
        return False
    protected = (
        payload.get("probability_state"),
        payload.get("score_stack"),
        payload.get("gate_result"),
        payload.get("decision_synthesis"),
    )
    for value in protected:
        if _contains_derivatives_influence(value):
            return False
    return True


def _contains_derivatives_influence(value: object) -> bool:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            key_text = str(key).lower()
            if key_text == "decision_influence_frac" and nested != 0.0:
                return True
            if "deriv" in key_text and "influence" in key_text:
                return True
            if _contains_derivatives_influence(nested):
                return True
    elif isinstance(value, (list, tuple)):
        return any(_contains_derivatives_influence(item) for item in value)
    return False


def _validated_cells(matrix_scope: str) -> tuple[tuple[str, str], ...]:
    try:
        cells = tuple(MATRIX_SCOPES[matrix_scope])
    except KeyError as exc:
        raise ValueError("Unsupported matrix scope.") from exc
    if len(cells) > MAX_MATRIX_CELLS or len(set(cells)) != len(cells):
        raise ValueError("Matrix violates the collector circuit breaker.")
    allowed_symbols = {"BTC/USDT", "ETH/USDT"}
    allowed_timeframes = {"1H", "4H"}
    if any(
        symbol not in allowed_symbols or timeframe not in allowed_timeframes
        for symbol, timeframe in cells
    ):
        raise ValueError("Matrix contains an unsupported cell.")
    return cells


def _enable_gate(raw_value: str | None) -> str:
    if raw_value is None or raw_value == "":
        return "DISABLED"
    normalized = raw_value.lower()
    if normalized == "true":
        return "ENABLED"
    if normalized == "false":
        return "DISABLED"
    return "INVALID"


def _final_result(
    *,
    options: CollectorOptions,
    results: list[dict[str, object]],
    cap_status: str,
) -> tuple[str, int]:
    classifications = {str(row["classification"]) for row in results}
    if cap_status != "OK":
        return "FAILED", 1
    if "FAILED_SAFETY_INVARIANT" in classifications:
        return "FAILED_SAFETY_INVARIANT", 1
    if "PARTIAL_PERSISTENCE" in classifications:
        return "PARTIAL_PERSISTENCE", 1
    if classifications & {
        "FAILED",
        "PROVIDER_UNAVAILABLE",
        "SKIPPED_REFERENCE_UNCERTAIN",
    }:
        return "FAILED", 1
    if options.dry_run:
        return "DRY_RUN_COMPLETE", 0
    if any(row.get("provider_status") == "DEGRADED" for row in results):
        return "COMPLETE_WITH_DEGRADED_PROVIDER", 0
    return "COMPLETE", 0


def _blank_cell(symbol: str, timeframe: str, classification: str) -> dict[str, object]:
    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "run_id": None,
        "prediction_id": None,
        "reference_close_utc": None,
        "classification": classification,
        "provider_status": None,
        "prediction_status": None,
        "derivatives_snapshot_status": None,
    }


def _report(
    options: CollectorOptions,
    *,
    enabled: bool,
    results: list[dict[str, object]],
    started_dt: datetime,
    elapsed: float,
    new_predictions: int = 0,
    new_derivatives_snapshots: int = 0,
    duplicates: int = 0,
    skipped: int = 0,
    failed: int = 0,
    cap_status: str = "OK",
    final_classification: str,
    exit_code: int,
) -> dict[str, Any]:
    report = {
        "collector_version": COLLECTOR_VERSION,
        "enabled": enabled,
        "dry_run": options.dry_run,
        "matrix_scope": options.matrix_scope,
        "matrix_cells": results,
        "started_at_utc": _iso_utc(started_dt),
        "elapsed_seconds": elapsed,
        "new_predictions": new_predictions,
        "new_derivatives_snapshots": new_derivatives_snapshots,
        "duplicates": duplicates,
        "skipped": skipped,
        "failed": failed,
        "cap_status": cap_status,
        "final_classification": final_classification,
        "exit_code": exit_code,
    }
    invalid_rows = any(
        set(row) != CELL_RESULT_FIELDS
        or row.get("classification") not in CELL_CLASSIFICATIONS
        for row in results
    )
    if set(report) != REPORT_FIELDS or invalid_rows:
        raise RuntimeError("Collector output contract mismatch.")
    return report


def _elapsed(start: float, monotonic: Callable[[], float]) -> float:
    return round(max(0.0, monotonic() - start), 6)


def _require_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("Collector timestamps must be timezone-aware.")
    return value.astimezone(UTC)


def _iso_utc(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _optional_text(value: object) -> str | None:
    return value if isinstance(value, str) else None


def append_step_summary(path: str | None, report: Mapping[str, object]) -> None:
    if not path:
        return
    lines = [
        "## UCPE Derivatives Evidence Collector",
        "",
        f"- Classification: `{report['final_classification']}`",
        f"- Scope: `{report['matrix_scope']}`",
        f"- Dry run: `{str(report['dry_run']).lower()}`",
        f"- New derivatives snapshots: `{report['new_derivatives_snapshots']}`",
        f"- Duplicates: `{report['duplicates']}`",
        f"- Failed cells: `{report['failed']}`",
        "",
    ]
    with Path(path).open("a", encoding="utf-8") as handle:
        handle.write("\n".join(lines))


def main(argv: Sequence[str] | None = None) -> int:
    options = parse_args(argv)
    report = run_collector(options, environ=os.environ)
    print(json.dumps(report, sort_keys=True, separators=(",", ":"), allow_nan=False))
    append_step_summary(os.environ.get("GITHUB_STEP_SUMMARY"), report)
    return int(report["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
