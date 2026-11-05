"""Dormant, unwired REF-only lattice pilot preparation."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from crypto_probability_engine.adapters.types import MarketSnapshot
from crypto_probability_engine.config.defaults import DEFAULT_PHASE1A
from crypto_probability_engine.normalizers.symbols import normalize_symbol
from crypto_probability_engine.quant_ng import evidence, reference, reference_v1d, windows
from crypto_probability_engine.targets.contract_v1 import VENUE_LABELS, stamp_v1, validate_v1

# OFF: turning this on is activation: a reviewed code change, then T3/T4; no environment
# variable, setting, header or request reads or sets it.
LATTICE_ENABLED = False
DECLARED_CELLS: tuple = ()
PROTOCOL_VERSION = "E3_LATTICE_V1"
LATTICE_ANCHOR_UTC = datetime(2026, 9, 21, tzinfo=UTC)
TIMEFRAMES = ("15m", "1H", "4H", "1D")
CADENCE_BARS = DEFAULT_PHASE1A.h_primary_bars // 2
assert DEFAULT_PHASE1A.h_primary_bars % 2 == 0
_BAR_SECONDS = {**windows.TIMEFRAME_SECONDS, "1D": 86_400}
_MISSED = {
    "STALE_SNAPSHOT",
    "FETCH_FAILED",
    "WINDOW_UNAVAILABLE",
    "REFERENCE_UNAVAILABLE",
    "NOT_ISSUED",
    "CAPACITY_STOP",
}


def _utc(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime) or value.utcoffset() != timedelta(0):
        raise ValueError(f"{name} must be an aware UTC datetime")
    return value.astimezone(UTC)


def lattice_instants(
    timeframe: str, start_utc: datetime, end_utc: datetime
) -> tuple[datetime, ...]:
    if timeframe not in TIMEFRAMES:
        raise ValueError("Unsupported timeframe")
    start, end = _utc(start_utc, "start_utc"), _utc(end_utc, "end_utc")
    step = timedelta(seconds=_BAR_SECONDS[timeframe] * CADENCE_BARS)
    elapsed = (start - LATTICE_ANCHOR_UTC).total_seconds()
    first = LATTICE_ANCHOR_UTC + ((int(elapsed // step.total_seconds())) * step)
    if first < start:
        first += step
    result = []
    while first <= end:
        result.append(first)
        first += step
    return tuple(result)


def latest_due_instant(timeframe: str, now_utc: datetime) -> datetime | None:
    now = _utc(now_utc, "now_utc")
    instants = lattice_instants(timeframe, LATTICE_ANCHOR_UTC, now)
    return instants[-1] if instants else None


@dataclass(frozen=True)
class LatticeCell:
    symbol: str
    venue: str
    timeframe: str


def validate_cell(cell: LatticeCell) -> None:
    if not isinstance(cell, LatticeCell):
        raise ValueError("cell must be a LatticeCell")
    normalized = normalize_symbol(cell.symbol)
    if any(token in normalized.base.upper() for token in ("BTC", "ETH")):
        raise ValueError("BTC and ETH bases and proxies are excluded")
    if normalized.quote != "USDT":
        raise ValueError("Quote must be USDT")
    if cell.venue not in VENUE_LABELS:
        raise ValueError("Venue is not mapped")
    if cell.timeframe not in TIMEFRAMES or cell.timeframe == "1M":
        raise ValueError("Unsupported timeframe")


@dataclass(frozen=True)
class PilotConfig:
    cells: tuple[LatticeCell, ...]
    priors: Mapping[str, reference.ReferencePriors | float | None]
    reference_prior_id: str
    recipe_id: str
    reference_spec: Any = None
    reference_spec_v1d: Any = None


def reconstruct_gaps(
    grid: Iterable[datetime], row_instants: Iterable[datetime], missed_instants: Iterable[datetime]
) -> tuple[datetime, ...]:
    rows, missed = set(row_instants), set(missed_instants)
    return tuple(instant for instant in grid if instant not in rows and instant not in missed)


def lattice_row_id(cell: LatticeCell, instant: datetime) -> str:
    _utc(instant, "instant")
    canonical = [PROTOCOL_VERSION, cell.symbol, cell.venue, cell.timeframe, instant.isoformat()]
    digest = hashlib.sha256(json.dumps(canonical, separators=(",", ":")).encode()).hexdigest()[:32]
    return f"e3l-{digest}:{cell.timeframe}:REF"


def build_lattice_row(
    cell: LatticeCell,
    instant: datetime,
    snapshot: MarketSnapshot,
    window: Any,
    triplet: Any,
    *,
    config: PilotConfig,
    core_computed_at: datetime,
    issued_at: datetime,
) -> dict[str, Any]:
    validate_cell(cell)
    issued = _utc(issued_at, "issued_at")
    close = window.last_close_utc
    seconds = _BAR_SECONDS[cell.timeframe]
    row = {
        "lattice_row_id": lattice_row_id(cell, instant),
        "lattice_run_id": lattice_row_id(cell, instant).split(":")[0],
        "lattice_instant_utc": _utc(instant, "instant").isoformat(),
        "protocol_version": PROTOCOL_VERSION,
        "evaluation_population": evidence.Population.E1_OPERATIONAL.value,
        "timing_class": evidence.Timing.NOT_APPLICABLE.value,
        "evidence_use": "TEST_ONLY",
        "arm": "REF",
        "artifact_id": None,
        "recipe_id": config.recipe_id,
        "methodology_version": "reference-daytype-v1d"
        if cell.timeframe == "1D"
        else "reference-daytype-v1",
        "reference_prior_id": config.reference_prior_id,
        "normalized_symbol": snapshot.normalized_symbol,
        "timeframe": cell.timeframe,
        "data_source": snapshot.provider,
        "provider_signature": snapshot.provider,
        "reference_close_utc": close.isoformat(),
        "horizon_end_utc": (
            close + timedelta(seconds=seconds * DEFAULT_PHASE1A.h_primary_bars)
        ).isoformat(),
        "predicted_at_utc": snapshot.as_of_utc.isoformat(),
        "reference_price": window.candles[-1].close,
        "band_frac": 0.0,
        "decision_band_frac": 0.0,
        "horizon_bars": DEFAULT_PHASE1A.h_primary_bars,
        "p_up_frac": triplet.p_up_frac,
        "p_down_frac": triplet.p_down_frac,
        "p_timeout_frac": triplet.p_timeout_frac,
        "is_live_data": True,
    }
    row = stamp_v1(
        row,
        snapshot_provider=snapshot.provider,
        core_computed_at=core_computed_at,
        issued_at=issued,
    )
    if (
        validate_v1(row) != ()
        or row.get("evaluation_population") != evidence.Population.E1_OPERATIONAL.value
        or row.get("timing_class") != evidence.Timing.NOT_APPLICABLE.value
    ):
        raise AssertionError("lattice row failed tc-v1 or evidence contract")
    return row


class LatticeDisabled(RuntimeError):
    pass


def lattice_step(
    now_utc: datetime,
    *,
    config: PilotConfig,
    fetch_snapshot: Any,
    fetch_window: Any,
    store: Any,
    app_clock: Any,
    state: dict[str, Any],
) -> dict[str, Any]:
    if not LATTICE_ENABLED:
        raise LatticeDisabled("Lattice is disabled")
    if not config.cells:
        raise ValueError("Pilot config has no cells")
    results: list[dict[str, Any]] = []
    stop = False
    for cell in config.cells:
        validate_cell(cell)
        instant = latest_due_instant(cell.timeframe, now_utc)
        if instant is None:
            continue
        previous = state.get(cell)
        if previous is not None:
            skipped = lattice_instants(
                cell.timeframe,
                previous + timedelta(microseconds=1),
                instant - timedelta(microseconds=1),
            )[:1000]
            for gap in skipped:
                status = store.record_missed(
                    {"cell": cell, "lattice_instant_utc": gap.isoformat(), "reason": "NOT_ISSUED"}
                )
                if status in {"CAPACITY_STOP", "CAPACITY_UNSET"}:
                    results.append({"instant": gap, "status": status, "reason": "NOT_ISSUED"})
                    stop = True
                    break
            if stop:
                break
        reason = None
        try:
            snapshot = fetch_snapshot(cell)
        except Exception:
            snapshot, reason = None, "FETCH_FAILED"
        if snapshot is not None and snapshot.as_of_utc < instant:
            reason = "STALE_SNAPSHOT"
        if snapshot is not None and reason is None:
            try:
                window = fetch_window(cell, snapshot)
            except Exception:
                window, reason = None, "WINDOW_UNAVAILABLE"
            if window is not None and reason is None:
                try:
                    prior = config.priors.get(cell.timeframe)
                    if cell.timeframe == "1D":
                        if prior is None:
                            raise reference.ReferenceNotFrozenError(
                                "Frozen reference prior required"
                            )
                        triplet = reference_v1d.compute_reference_v1d(
                            window.candles,
                            timeframe=cell.timeframe,
                            band_frac=0.0,
                            spec=config.reference_spec_v1d,
                            prior=prior,
                        )
                    else:
                        if prior is None:
                            raise reference.ReferenceNotFrozenError(
                                "Frozen reference priors required"
                            )
                        triplet = reference.compute_reference(
                            window.candles,
                            timeframe=cell.timeframe,
                            band_frac=0.0,
                            spec=config.reference_spec,
                            priors=prior,
                        )
                except reference.ReferenceNotFrozenError:
                    triplet, reason = None, "REFERENCE_UNAVAILABLE"
                except Exception:
                    triplet, reason = None, "WINDOW_UNAVAILABLE"
                if triplet is not None:
                    row = build_lattice_row(
                        cell,
                        instant,
                        snapshot,
                        window,
                        triplet,
                        config=config,
                        core_computed_at=app_clock(),
                        issued_at=app_clock(),
                    )
                    status = store.record_row(row)
                    results.append({"instant": instant, "status": status})
                    if status in {"CAPACITY_STOP", "CAPACITY_UNSET"}:
                        stop = True
        if reason:
            status = store.record_missed(
                {"cell": cell, "lattice_instant_utc": instant.isoformat(), "reason": reason}
            )
            results.append({"instant": instant, "status": status, "reason": reason})
            if status in {"CAPACITY_STOP", "CAPACITY_UNSET"} or reason == "CAPACITY_STOP":
                stop = True
        state[cell] = instant
        if stop:
            break
    store.capture_commit_receipts(1000)
    return {"results": results, "stopped": stop}
