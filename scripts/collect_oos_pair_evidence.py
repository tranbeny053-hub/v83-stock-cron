"""Manual-only, bounded collector for paired OOS shadow evidence.

The command is dry-run by default and cannot construct a write-capable
repository until the enable flag, confirmation token, database configuration,
and candidate freeze proof all pass.
"""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from crypto_probability_engine.adapters.provider_selection import select_market_data
from crypto_probability_engine.api.analysis_service import (
    _pop_prediction_persistence,
    analyze_request,
    persist_analysis_now,
)
from crypto_probability_engine.api.schemas import AnalysisRequest
from crypto_probability_engine.calibration.skill import (
    get_cached_skill_evidence,
    insufficient_skill_evidence,
)
from crypto_probability_engine.config.defaults import (
    DISTRIBUTIONAL_METHODOLOGY_VERSION,
    METHODOLOGY_VERSION,
    TIMEFRAME_SECONDS,
)
from crypto_probability_engine.config.settings import Settings
from crypto_probability_engine.execution_realism.realism import compute_execution_realism
from crypto_probability_engine.features.liquidity_depth import compute_liquidity_depth
from crypto_probability_engine.normalizers.symbols import normalize_symbol
from crypto_probability_engine.oos.freeze_guard import assert_candidate_freeze
from crypto_probability_engine.oos.pair_context import (
    OOS_PREDICTION_ORIGIN,
    OOSArm,
    build_oos_pair_context,
)
from crypto_probability_engine.persistence.repository import build_operator_repository
from crypto_probability_engine.persistence.run_store import InMemoryRunStore

COLLECTOR_VERSION = "oos-pair-evidence-collector.v3"
ENABLE_ENV = "UCPE_OOS_PAIR_EVIDENCE_ENABLED"
WRITE_CONFIRMATION = "WRITE-OOS-PAIR-EVIDENCE"
MAX_OCCASIONS_PER_RUN = 6
MAX_PREDICTIONS_PER_RUN = 12
MATRIX = tuple(
    (symbol, timeframe)
    for symbol in ("BTC/USDT", "ETH/USDT")
    for timeframe in ("15m", "1H", "4H")
)
PERIOD_BY_TIMEFRAME = {
    "15m": timedelta(minutes=45),
    "1H": timedelta(hours=3),
    "4H": timedelta(hours=12),
}


@dataclass(frozen=True)
class CollectorOptions:
    dry_run: bool = True
    confirm_write: str = ""


@dataclass(frozen=True)
class CollectorDependencies:
    select: Callable[..., Any] = select_market_data
    resolve_skill: Callable[[str], Mapping[str, Any]] = get_cached_skill_evidence
    analyze: Callable[..., dict] = analyze_request
    persist: Callable[[dict, object], dict[str, object]] = persist_analysis_now
    repository_factory: Callable[[Settings], object] = build_operator_repository
    run_store_factory: Callable[[], InMemoryRunStore] = InMemoryRunStore
    verify_freeze: Callable[[], object] = assert_candidate_freeze
    now_utc: Callable[[], datetime] = lambda: datetime.now(UTC)


DEFAULT_DEPENDENCIES = CollectorDependencies()


def parse_bool(value: str) -> bool:
    normalized = value.lower()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    raise argparse.ArgumentTypeError("expected exactly true or false")


def parse_args(argv: Sequence[str] | None = None) -> CollectorOptions:
    parser = argparse.ArgumentParser(description="Collect bounded OOS pair evidence.")
    parser.add_argument("--dry-run", type=parse_bool, default=True)
    parser.add_argument("--confirm-write", default="")
    args = parser.parse_args(argv)
    return CollectorOptions(dry_run=args.dry_run, confirm_write=args.confirm_write)


def run_collector(
    options: CollectorOptions,
    *,
    environ: Mapping[str, str],
    dependencies: CollectorDependencies = DEFAULT_DEPENDENCIES,
) -> dict[str, Any]:
    enabled = environ.get(ENABLE_ENV) == "true"
    if not enabled:
        classification = (
            "DISABLED" if environ.get(ENABLE_ENV) in {None, "", "false"} else "CONFIGURATION_ERROR"
        )
        return _report(options, enabled=False, classification=classification)
    if options.dry_run:
        return _report(
            options,
            enabled=True,
            skipped=len(MATRIX),
            classification="DRY_RUN",
        )
    if options.confirm_write != WRITE_CONFIRMATION:
        return _report(options, enabled=True, failed=1, classification="CONFIRMATION_REQUIRED")
    database_url = environ.get("SUPABASE_DB_URL")
    if not database_url:
        return _report(options, enabled=True, failed=1, classification="CONFIGURATION_ERROR")

    try:
        dependencies.verify_freeze()
    except Exception:
        return _report(options, enabled=True, failed=1, classification="FREEZE_MISMATCH")

    settings = Settings.model_validate(
        {
            "data_mode": "live",
            "supabase_db_url": database_url,
            "external_store_configured": True,
        }
    )
    try:
        repository = dependencies.repository_factory(settings)
        now_utc = _require_utc(dependencies.now_utc())
        run_store = dependencies.run_store_factory()
    except Exception:
        return _report(options, enabled=True, failed=1, classification="READ_UNAVAILABLE")

    inserted = skipped = orphans = failed = selections = 0
    cells: list[dict[str, object]] = []
    for symbol_text, timeframe in MATRIX:
        if inserted >= MAX_OCCASIONS_PER_RUN:
            skipped += 1
            cells.append(_cell(symbol_text, timeframe, "SKIPPED_CAP"))
            continue
        normalized = normalize_symbol(symbol_text).display
        try:
            latest = repository.fetch_latest_oos_occasion(normalized, timeframe)
        except Exception:
            failed += 1
            cells.append(_cell(symbol_text, timeframe, "READ_UNAVAILABLE"))
            continue
        if not _is_due(latest, now_utc, PERIOD_BY_TIMEFRAME[timeframe]):
            skipped += 1
            cells.append(_cell(symbol_text, timeframe, "NOT_DUE"))
            continue
        try:
            selection = dependencies.select(
                normalize_symbol(symbol_text), timeframe, settings=settings
            )
            selections += 1
        except Exception:
            failed += 1
            cells.append(_cell(symbol_text, timeframe, "SELECTION_FAILED"))
            continue
        snapshot = selection.snapshot
        reference_close = snapshot.candles[-1].close_time_utc if snapshot.candles else None
        if (
            selection.data_quality.get("is_live_data") is not True
            or not _is_current_live_reference(
                reference_close,
                snapshot.as_of_utc,
                now_utc,
                timeframe,
            )
        ):
            failed += 1
            cells.append(_cell(symbol_text, timeframe, "BACKFILL_REFUSED"))
            continue
        try:
            existing_count = _occasion_count(
                repository, normalized, timeframe, reference_close
            )
        except Exception:
            failed += 1
            cells.append(_cell(symbol_text, timeframe, "READ_UNAVAILABLE"))
            continue
        if existing_count:
            skipped += 1
            if existing_count == 1:
                orphans += 1
            cells.append(
                _cell(
                    symbol_text,
                    timeframe,
                    "ORPHAN_SKIPPED" if existing_count == 1 else "OCCASION_EXISTS",
                    reference_close,
                )
            )
            continue
        try:
            skill_evidence = dependencies.resolve_skill(timeframe)
        except Exception:
            skill_evidence = insufficient_skill_evidence()
        band = compute_execution_realism(
            compute_liquidity_depth(snapshot.order_book)
        )["round_trip_cost_frac"]
        pair = None
        payloads = None
        try:
            pair = build_oos_pair_context(
                market_snapshot=snapshot,
                provider_state=selection.provider_state,
                data_quality=selection.data_quality,
                resolved_skill_evidence=skill_evidence,
                information_cutoff=snapshot.as_of_utc,
                decision_band_frac=band,
            )
            payloads = [
                dependencies.analyze(
                    AnalysisRequest(symbol=symbol_text, timeframe=timeframe),
                    settings=settings,
                    run_store=run_store,
                    prediction_origin=OOS_PREDICTION_ORIGIN,
                    methodology_version=methodology,
                    pair_context=pair,
                    arm=arm,
                )
                for arm, methodology in (
                    (OOSArm.BASELINE, METHODOLOGY_VERSION),
                    (OOSArm.CANDIDATE, DISTRIBUTIONAL_METHODOLOGY_VERSION),
                )
            ]
            if ((inserted + 1) * 2) > MAX_PREDICTIONS_PER_RUN:
                raise RuntimeError("prediction cap would be exceeded")
            result = dependencies.persist(payloads[0], repository)
            if result.get("overall") != "OK":
                raise RuntimeError("paired persistence was not confirmed")
        except Exception:
            failed += 1
            cells.append(_cell(symbol_text, timeframe, "FAILED", reference_close))
        else:
            inserted += 1
            cells.append(_cell(symbol_text, timeframe, "INSERTED", reference_close, pair.run_id))
        finally:
            if pair is not None:
                _pop_prediction_persistence({"run_id": pair.run_id})

    classification = "OK" if failed == 0 else "PARTIAL_FAILURE"
    return _report(
        options,
        enabled=True,
        inserted=inserted,
        skipped=skipped,
        orphans=orphans,
        failed=failed,
        selections=selections,
        cells=cells,
        classification=classification,
    )


def _occasion_count(repository, symbol: str, timeframe: str, reference_close: datetime) -> int:
    counter = getattr(repository, "count_oos_occasion_rows", None)
    if callable(counter):
        return int(counter(symbol, timeframe, reference_close))
    return int(repository.oos_occasion_exists(symbol, timeframe, reference_close))


def _is_due(latest: Any, now_utc: datetime, period: timedelta) -> bool:
    if latest is None:
        return True
    try:
        return now_utc - _require_utc(latest) >= period
    except (TypeError, ValueError):
        return False


def _is_current_live_reference(
    reference_close: Any,
    snapshot_as_of: Any,
    now_utc: datetime,
    timeframe: str,
) -> bool:
    try:
        reference = _require_utc(reference_close)
        as_of = _require_utc(snapshot_as_of)
    except (TypeError, ValueError):
        return False
    seconds = TIMEFRAME_SECONDS[timeframe]
    current_boundary = datetime.fromtimestamp(
        int(now_utc.timestamp()) // seconds * seconds,
        tz=UTC,
    )
    return (
        reference == current_boundary
        and reference <= as_of <= now_utc + timedelta(minutes=5)
    )


def _require_utc(value: Any) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timezone-aware datetime required")
    return value.astimezone(UTC)


def _cell(
    symbol: str,
    timeframe: str,
    classification: str,
    reference_close: datetime | None = None,
    run_id: str | None = None,
) -> dict[str, object]:
    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "classification": classification,
        "reference_close_utc": (
            reference_close.isoformat().replace("+00:00", "Z") if reference_close else None
        ),
        "run_id": run_id,
    }


def _report(
    options: CollectorOptions,
    *,
    enabled: bool,
    inserted: int = 0,
    skipped: int = 0,
    orphans: int = 0,
    failed: int = 0,
    selections: int = 0,
    cells: list[dict[str, object]] | None = None,
    classification: str,
) -> dict[str, Any]:
    return {
        "collector_version": COLLECTOR_VERSION,
        "enabled": enabled,
        "dry_run": options.dry_run,
        "occasions_inserted": inserted,
        "predictions_inserted": inserted * 2,
        "skipped": skipped,
        "orphans": orphans,
        "failed": failed,
        "market_selections": selections,
        "cells": cells or [],
        "final_classification": classification,
        "exit_code": 0 if failed == 0 and classification != "CONFIGURATION_ERROR" else 1,
    }


def main(argv: Sequence[str] | None = None) -> int:
    report = run_collector(parse_args(argv), environ=os.environ)
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return int(report["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
