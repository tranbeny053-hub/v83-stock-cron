"""Best-effort persistence repositories for compact app state."""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from collections.abc import Callable, Mapping
from typing import Any, Literal, Protocol

from crypto_probability_engine.config.settings import Settings

PersistenceStatus = Literal["STATELESS", "OK", "UNAVAILABLE"]


class PersistenceRepository(Protocol):
    def persistence_status(self) -> PersistenceStatus:
        """Return current persistence health without exposing connection details."""

    def save_run(self, summary: Mapping[str, Any]) -> PersistenceStatus:
        """Persist compact analysis run summary."""

    def save_timeframe_result(self, row: Mapping[str, Any]) -> PersistenceStatus:
        """Persist compact per-timeframe analysis result."""

    def save_provider_observation(self, row: Mapping[str, Any]) -> PersistenceStatus:
        """Persist compact provider observation."""

    def list_watchlist(self, operator_id: str = "operator") -> list[str]:
        """List normalized watchlist symbols for an operator."""

    def add_watchlist(self, symbol: str, operator_id: str = "operator") -> PersistenceStatus:
        """Add a normalized symbol to an operator watchlist."""

    def remove_watchlist(self, symbol: str, operator_id: str = "operator") -> PersistenceStatus:
        """Remove a normalized symbol from an operator watchlist."""

    def recent_runs(self, limit: int) -> list[dict]:
        """Return compact recent run summaries."""

    def get_run(self, run_id: str) -> dict | None:
        """Return compact run summary by id."""


class InMemoryPersistenceRepository:
    """Stateless process-memory repository used when external persistence is absent."""

    def __init__(self) -> None:
        self._runs: OrderedDict[str, dict] = OrderedDict()
        self._timeframe_results: list[dict] = []
        self._provider_observations: list[dict] = []
        self._watchlists: dict[str, OrderedDict[str, None]] = {}

    def persistence_status(self) -> PersistenceStatus:
        return "STATELESS"

    def repository_type(self) -> str:
        return "IN_MEMORY"

    def circuit_state(self) -> str:
        return "STATELESS"

    def save_run(self, summary: Mapping[str, Any]) -> PersistenceStatus:
        run_id = str(summary.get("run_id", ""))
        if run_id:
            self._runs[run_id] = dict(summary)
            self._runs.move_to_end(run_id)
        return self.persistence_status()

    def save_timeframe_result(self, row: Mapping[str, Any]) -> PersistenceStatus:
        self._timeframe_results.append(dict(row))
        return self.persistence_status()

    def save_provider_observation(self, row: Mapping[str, Any]) -> PersistenceStatus:
        self._provider_observations.append(dict(row))
        return self.persistence_status()

    def list_watchlist(self, operator_id: str = "operator") -> list[str]:
        return list(self._watchlists.get(operator_id, OrderedDict()).keys())

    def add_watchlist(self, symbol: str, operator_id: str = "operator") -> PersistenceStatus:
        self._watchlists.setdefault(operator_id, OrderedDict())[symbol] = None
        return self.persistence_status()

    def remove_watchlist(self, symbol: str, operator_id: str = "operator") -> PersistenceStatus:
        self._watchlists.setdefault(operator_id, OrderedDict()).pop(symbol, None)
        return self.persistence_status()

    def recent_runs(self, limit: int) -> list[dict]:
        values = list(reversed(self._runs.values()))
        return [dict(item) for item in values[:limit]]

    def get_run(self, run_id: str) -> dict | None:
        value = self._runs.get(run_id)
        return dict(value) if value else None


class SupabasePersistenceRepository:
    """Postgres persistence adapter for Supabase direct database URL usage."""

    def __init__(
        self,
        db_url: str,
        *,
        connect_timeout_seconds: int = 3,
        operation_timeout_seconds: float = 3.0,
        circuit_cooldown_seconds: float = 60.0,
        pool_factory: Callable[[], Any] | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._db_url = db_url
        self._connect_timeout_seconds = connect_timeout_seconds
        self._operation_timeout_seconds = operation_timeout_seconds
        self._statement_timeout_ms = max(1000, int(operation_timeout_seconds * 1000))
        self._circuit_cooldown_seconds = circuit_cooldown_seconds
        self._pool_factory = pool_factory
        self._clock = clock
        self._pool: Any | None = None
        self._lock = threading.Lock()
        self._last_status: PersistenceStatus = "OK"
        self._circuit_open_until = 0.0
        self._trial_in_progress = False
        self._fallback = InMemoryPersistenceRepository()

    def persistence_status(self) -> PersistenceStatus:
        with self._lock:
            if self._last_status == "UNAVAILABLE" and self._clock() < self._circuit_open_until:
                return "UNAVAILABLE"
            return self._last_status

    def repository_type(self) -> str:
        return "SUPABASE"

    def circuit_state(self) -> str:
        with self._lock:
            now = self._clock()
            if self._last_status != "UNAVAILABLE":
                return "CLOSED"
            if now < self._circuit_open_until:
                return "OPEN"
            if self._trial_in_progress:
                return "HALF_OPEN"
            return "HALF_OPEN"

    def maybe_can_attempt(self) -> bool:
        with self._lock:
            now = self._clock()
            if self._last_status != "UNAVAILABLE":
                return True
            if now < self._circuit_open_until:
                return False
            if self._trial_in_progress:
                return False
            self._trial_in_progress = True
            return True

    def mark_unavailable(self) -> PersistenceStatus:
        with self._lock:
            self._last_status = "UNAVAILABLE"
            self._circuit_open_until = self._clock() + self._circuit_cooldown_seconds
            self._trial_in_progress = False
        return self._last_status

    def _mark_ok(self) -> PersistenceStatus:
        with self._lock:
            self._last_status = "OK"
            self._circuit_open_until = 0.0
            self._trial_in_progress = False
        return self._last_status

    def _get_pool(self):
        if self._pool is None:
            if self._pool_factory is not None:
                self._pool = self._pool_factory()
            else:
                from psycopg_pool import ConnectionPool

                self._pool = ConnectionPool(
                    conninfo=self._db_url,
                    min_size=0,
                    max_size=2,
                    timeout=self._operation_timeout_seconds,
                    kwargs={
                        "connect_timeout": self._connect_timeout_seconds,
                        "prepare_threshold": None,
                    },
                    open=False,
                )
            open_pool = getattr(self._pool, "open", None)
            if callable(open_pool):
                open_pool(wait=False)
        return self._pool

    def _connection(self):
        return self._get_pool().connection(timeout=self._operation_timeout_seconds)

    def _run_db(self, operation):
        if not self.maybe_can_attempt():
            return "UNAVAILABLE", None
        try:
            with self._connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        "SET LOCAL statement_timeout = %s",
                        (self._statement_timeout_ms,),
                    )
                    result = operation(cursor)
        except Exception:
            return self.mark_unavailable(), None
        return self._mark_ok(), result

    def close(self) -> None:
        pool = self._pool
        if pool is None:
            return
        close_pool = getattr(pool, "close", None)
        if callable(close_pool):
            close_pool()

    def save_run(self, summary: Mapping[str, Any]) -> PersistenceStatus:
        self._fallback.save_run(summary)
        status, _ = self._run_db(
            lambda cursor: cursor.execute(
                """
                INSERT INTO analysis_runs (
                  run_id, operator_id, symbol, normalized_symbol, analysis_mode,
                  asset_class, primary_timeframe, disposition, total_score,
                  data_source, is_live_data, persistence_status, analysis_hash,
                  as_of_utc
                )
                VALUES (
                  %(run_id)s, %(operator_id)s, %(symbol)s, %(normalized_symbol)s,
                  %(analysis_mode)s, %(asset_class)s, %(primary_timeframe)s,
                  %(disposition)s, %(total_score)s, %(data_source)s,
                  %(is_live_data)s, %(persistence_status)s, %(analysis_hash)s,
                  %(as_of_utc)s
                )
                ON CONFLICT (run_id) DO UPDATE SET
                  disposition = EXCLUDED.disposition,
                  total_score = EXCLUDED.total_score,
                  data_source = EXCLUDED.data_source,
                  is_live_data = EXCLUDED.is_live_data,
                  persistence_status = EXCLUDED.persistence_status,
                  analysis_hash = EXCLUDED.analysis_hash
                """,
                dict(summary),
            )
        )
        return status

    def save_timeframe_result(self, row: Mapping[str, Any]) -> PersistenceStatus:
        self._fallback.save_timeframe_result(row)
        status, _ = self._run_db(
            lambda cursor: cursor.execute(
                """
                INSERT INTO analysis_timeframe_results (
                  run_id, timeframe, disposition, total_score, prob_up_pct,
                  prob_down_pct, prob_timeout_pct, gate_action, data_source,
                  is_live_data
                )
                VALUES (
                  %(run_id)s, %(timeframe)s, %(disposition)s, %(total_score)s,
                  %(prob_up_pct)s, %(prob_down_pct)s, %(prob_timeout_pct)s,
                  %(gate_action)s, %(data_source)s, %(is_live_data)s
                )
                """,
                dict(row),
            )
        )
        return status

    def save_provider_observation(self, row: Mapping[str, Any]) -> PersistenceStatus:
        self._fallback.save_provider_observation(row)
        status, _ = self._run_db(
            lambda cursor: cursor.execute(
                """
                INSERT INTO provider_observations (
                  run_id, provider, provider_status, active_provider, data_source,
                  is_live_data, warning_count
                )
                VALUES (
                  %(run_id)s, %(provider)s, %(provider_status)s,
                  %(active_provider)s, %(data_source)s, %(is_live_data)s,
                  %(warning_count)s
                )
                """,
                dict(row),
            )
        )
        return status

    def list_watchlist(self, operator_id: str = "operator") -> list[str]:
        status, rows = self._run_db(lambda cursor: _fetch_watchlist_rows(cursor, operator_id))
        if status == "UNAVAILABLE" or rows is None:
            return self._fallback.list_watchlist(operator_id)
        return [str(row[0]) for row in rows]

    def add_watchlist(self, symbol: str, operator_id: str = "operator") -> PersistenceStatus:
        self._fallback.add_watchlist(symbol, operator_id)
        status, _ = self._run_db(
            lambda cursor: cursor.execute(
                """
                INSERT INTO watchlist (operator_id, normalized_symbol, display_symbol)
                VALUES (%s, %s, %s)
                ON CONFLICT (operator_id, normalized_symbol) DO NOTHING
                """,
                (operator_id, symbol, symbol),
            )
        )
        return status

    def remove_watchlist(self, symbol: str, operator_id: str = "operator") -> PersistenceStatus:
        self._fallback.remove_watchlist(symbol, operator_id)
        status, _ = self._run_db(
            lambda cursor: cursor.execute(
                """
                DELETE FROM watchlist
                WHERE operator_id = %s AND normalized_symbol = %s
                """,
                (operator_id, symbol),
            )
        )
        return status

    def recent_runs(self, limit: int) -> list[dict]:
        status, rows = self._run_db(lambda cursor: _fetch_recent_runs(cursor, limit))
        if status == "UNAVAILABLE" or rows is None:
            return self._fallback.recent_runs(limit)
        return [
            {
                "run_id": row[0],
                "symbol": row[1],
                "normalized_symbol": row[2],
                "analysis_mode": row[3],
                "primary_timeframe": row[4],
                "disposition": row[5],
                "total_score": float(row[6]) if row[6] is not None else None,
                "data_source": row[7],
                "is_live_data": row[8],
                "analysis_hash": row[9],
                "as_of_utc": row[10].isoformat() if row[10] else None,
                "created_at": row[11].isoformat() if row[11] else None,
            }
            for row in rows
        ]

    def get_run(self, run_id: str) -> dict | None:
        status, row = self._run_db(lambda cursor: _fetch_run(cursor, run_id))
        if status == "UNAVAILABLE":
            return self._fallback.get_run(run_id)
        if row is None:
            return None
        return {
            "run_id": row[0],
            "symbol": row[1],
            "normalized_symbol": row[2],
            "analysis_mode": row[3],
            "primary_timeframe": row[4],
            "disposition": row[5],
            "total_score": float(row[6]) if row[6] is not None else None,
            "data_source": row[7],
            "is_live_data": row[8],
            "analysis_hash": row[9],
            "as_of_utc": row[10].isoformat() if row[10] else None,
            "created_at": row[11].isoformat() if row[11] else None,
        }


def _fetch_watchlist_rows(cursor, operator_id: str):
    cursor.execute(
        """
        SELECT display_symbol
        FROM watchlist
        WHERE operator_id = %s
        ORDER BY created_at ASC
        """,
        (operator_id,),
    )
    return cursor.fetchall()


def _fetch_recent_runs(cursor, limit: int):
    cursor.execute(
        """
        SELECT run_id, symbol, normalized_symbol, analysis_mode,
               primary_timeframe, disposition, total_score, data_source,
               is_live_data, analysis_hash, as_of_utc, created_at
        FROM analysis_runs
        ORDER BY created_at DESC
        LIMIT %s
        """,
        (limit,),
    )
    return cursor.fetchall()


def _fetch_run(cursor, run_id: str):
    cursor.execute(
        """
        SELECT run_id, symbol, normalized_symbol, analysis_mode,
               primary_timeframe, disposition, total_score, data_source,
               is_live_data, analysis_hash, as_of_utc, created_at
        FROM analysis_runs
        WHERE run_id = %s
        """,
        (run_id,),
    )
    return cursor.fetchone()


def build_persistence_repository(settings: Settings) -> PersistenceRepository:
    if settings.supabase_db_url:
        return SupabasePersistenceRepository(settings.supabase_db_url)
    return InMemoryPersistenceRepository()
