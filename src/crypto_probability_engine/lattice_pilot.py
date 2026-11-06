"""Dormant NG4 pilot runner. Importing this module performs no I/O."""
from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from crypto_probability_engine.quant_ng import lattice, reference, reference_v1d, windows
from crypto_probability_engine.telemetry.events import EVENTS_SINK

WRITER_DB_URL_ENV: str | None = None  # W1 HELD, W2 not ruled
GRACE_SECONDS = 20
STEP_TIMEOUT_SECONDS = 120
STOP_TIMEOUT_SECONDS = 10


def _event(sink: Any, event: str, **fields: object) -> None:
    sink.record(event, fields)


def _load_specs():
    root = Path(__file__).resolve().parents[2]
    v1 = json.loads((root / "ops/quant_ng/REFERENCE_SPEC_v1.json").read_text())
    v1d = json.loads((root / "ops/quant_ng/REFERENCE_SPEC_v1d.json").read_text())
    return reference.load_reference_spec(v1), reference_v1d.load_reference_spec_v1d(v1d)


class PilotHandle:
    def __init__(self, task: asyncio.Task, sink: Any):
        self.task, self.sink = task, sink

    async def stop(self) -> None:
        try:
            self.task.cancel()
            await asyncio.wait_for(self.task, STOP_TIMEOUT_SECONDS)
        except BaseException:
            pass


async def _run(settings: Any, start: datetime, end: datetime, config: Any,
               connect: Any, sink: Any, clock: Any, process_started_at: datetime) -> None:
    from crypto_probability_engine.adapters import http_client, public_market
    from crypto_probability_engine.adapters.candle_history import BINANCE_KLINES_PATH
    from crypto_probability_engine.adapters.mappers import (
        BINANCE_BASE_URL,
        map_interval,
        parse_binance_candles,
        provider_symbol,
    )
    from crypto_probability_engine.normalizers.symbols import normalize_symbol
    from crypto_probability_engine.persistence.lattice_store import LatticeStore

    state: dict = {}
    adapter = public_market.BinancePublicAdapter(settings=settings)
    candle_history_adapter = adapter
    def fetch_snapshot(cell):
        return adapter.fetch_market_snapshot(normalize_symbol(cell.symbol), cell.timeframe)
    def fetch_window(cell, snapshot, step_now):
        if cell.timeframe != "1D":
            return windows.acquire_window(
                snapshot,
                symbol=normalize_symbol(cell.symbol),
                bars_required=lattice.PILOT_BARS_REQUIRED[cell.timeframe],
                history_adapter=candle_history_adapter,
            )
        client = adapter.http_client
        symbol = normalize_symbol(cell.symbol)
        try:  # a failed fetch or a payload that does not parse is a missed instant, never a crash
            payload = client.get_json(base_url=BINANCE_BASE_URL, path=BINANCE_KLINES_PATH,
                params={"symbol": provider_symbol(symbol, "binance"),
                        "interval": map_interval("1D", "binance"), "limit": 376},
                provider="binance")
            candles = list(parse_binance_candles(payload, timeframe="1D"))[-371:]
        except Exception as exc:
            raise windows.WindowUnavailable(
                windows.UnavailableReason.HISTORY_FAILED, type(exc).__name__
            ) from None
        reference_v1d.require_well_formed_1d(candles)
        window = windows.Window(
            "binance", snapshot.normalized_symbol, "1D", tuple(candles),
            windows.WindowSource.HISTORY, 1,
        )
        due = lattice.latest_due_instant("1D", step_now)
        if len(candles) != 371 or window.last_close_utc != due:
            raise windows.WindowUnavailable(
                windows.UnavailableReason.HISTORY_INVALID,
                "the 1D window is not 371 candles closing at the instant",
            )
        return window
    store = LatticeStore(connect)
    checkpoint = start + lattice.PILOT_CHECKPOINT
    checkpoint_sent = False
    status_fields = {
        "INSERTED": "inserted", "INSERTED_WARN": "inserted_warn",
        "DUPLICATE": "duplicate", "LOGGED": "logged",
        "CAPACITY_STOP": "capacity_stop", "CAPACITY_UNSET": "capacity_unset",
    }
    counts = {name: 0 for name in (*status_fields.values(), "errors")}
    while True:
        now = clock()
        if now >= end:
            step_now = end - timedelta(microseconds=1)
        else:
            due = [i for cell in lattice.PILOT_CELLS
                   for i in lattice.lattice_instants(cell.timeframe, start, end) if i >= now]
            target = min(due) + timedelta(seconds=GRACE_SECONDS) if due else end
            await asyncio.sleep(max(0, (target-now).total_seconds()))
            step_now = clock()
        token = http_client.PROVIDER_COALESCING.set(False)
        try:
            worker = asyncio.create_task(asyncio.to_thread(
                lattice.lattice_step, step_now, config=config, fetch_snapshot=fetch_snapshot,
                fetch_window=lambda cell, snapshot, now=step_now: fetch_window(cell, snapshot, now),
                store=store, app_clock=clock, state=state, pilot_window=(start, end),
                fresh_after=process_started_at - timedelta(seconds=GRACE_SECONDS)))
            try:
                result = await asyncio.wait_for(asyncio.shield(worker), STEP_TIMEOUT_SECONDS)
            except TimeoutError:
                _event(sink, "lattice_pilot_error", exception_class="StepTimeout")
                counts["errors"] += 1
                result = await worker
        except Exception as exc:
            _event(sink, "lattice_pilot_error", exception_class=type(exc).__name__)
            counts["errors"] += 1
            result = {}
        finally:
            http_client.PROVIDER_COALESCING.reset(token)
        for entry in result.get("results", []):
            status = entry.get("status")
            field = status_fields.get(status)
            if field:
                counts[field] += 1
        if not checkpoint_sent and clock() >= checkpoint:
            _event(sink, "lattice_pilot_checkpoint", scope="since_process_start", **counts)
            checkpoint_sent = True
        if result.get("stopped") or clock() >= end:
            return


def start(settings: Any, *, clock=lambda: datetime.now(UTC), environ=None,
          sink=EVENTS_SINK) -> PilotHandle | None:
    if not lattice.LATTICE_ENABLED:
        return None
    try:
        start_utc = lattice.PILOT_START_UTC
        now = clock()
        if start_utc is None:
            _event(sink, "lattice_pilot_state", state="NOT_CONFIGURED")
            return None
        end = lattice.pilot_end(start_utc)
        if now >= end:
            _event(sink, "lattice_pilot_state", state="WINDOW_CLOSED")
            return None
        values = __import__("os").environ if environ is None else environ
        name = WRITER_DB_URL_ENV
        url = values.get(name) if name else None
        if not url:
            _event(sink, "lattice_pilot_state", state="NOT_CONFIGURED")
            return None
        spec, spec_1d = _load_specs()
        config = lattice.pilot_config(spec, spec_1d)
        def connect():
            import psycopg
            return psycopg.connect(url, connect_timeout=10, tcp_user_timeout=10000,
                prepare_threshold=None, options="-c statement_timeout=5000")
        process_started_at = now
        task = asyncio.get_running_loop().create_task(
            _run(settings, start_utc, end, config, connect, sink, clock, process_started_at)
        )
        _event(sink, "lattice_pilot_state", state="RUNNING")
        return PilotHandle(task, sink)
    except Exception as exc:
        _event(sink, "lattice_pilot_state", state="ERROR", exception_class=type(exc).__name__)
        return None
