"""Best-effort persistence repositories for compact app state."""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Mapping
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

    def __init__(self, db_url: str, *, connect_timeout_seconds: int = 3) -> None:
        self._db_url = db_url
        self._connect_timeout_seconds = connect_timeout_seconds
        self._last_status: PersistenceStatus = "OK"
        self._fallback = InMemoryPersistenceRepository()

    def persistence_status(self) -> PersistenceStatus:
        return self._last_status

    def _connect(self):
        import psycopg

        return psycopg.connect(
            self._db_url,
            connect_timeout=self._connect_timeout_seconds,
        )

    def _mark_unavailable(self) -> PersistenceStatus:
        self._last_status = "UNAVAILABLE"
        return self._last_status

    def _mark_ok(self) -> PersistenceStatus:
        self._last_status = "OK"
        return self._last_status

    def save_run(self, summary: Mapping[str, Any]) -> PersistenceStatus:
        self._fallback.save_run(summary)
        try:
            with self._connect() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
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
        except Exception:
            return self._mark_unavailable()
        return self._mark_ok()

    def save_timeframe_result(self, row: Mapping[str, Any]) -> PersistenceStatus:
        self._fallback.save_timeframe_result(row)
        try:
            with self._connect() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
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
        except Exception:
            return self._mark_unavailable()
        return self._mark_ok()

    def save_provider_observation(self, row: Mapping[str, Any]) -> PersistenceStatus:
        self._fallback.save_provider_observation(row)
        try:
            with self._connect() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
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
        except Exception:
            return self._mark_unavailable()
        return self._mark_ok()

    def list_watchlist(self, operator_id: str = "operator") -> list[str]:
        try:
            with self._connect() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT display_symbol
                        FROM watchlist
                        WHERE operator_id = %s
                        ORDER BY created_at ASC
                        """,
                        (operator_id,),
                    )
                    rows = cursor.fetchall()
        except Exception:
            self._mark_unavailable()
            return self._fallback.list_watchlist(operator_id)
        self._mark_ok()
        return [str(row[0]) for row in rows]

    def add_watchlist(self, symbol: str, operator_id: str = "operator") -> PersistenceStatus:
        self._fallback.add_watchlist(symbol, operator_id)
        try:
            with self._connect() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO watchlist (operator_id, normalized_symbol, display_symbol)
                        VALUES (%s, %s, %s)
                        ON CONFLICT (operator_id, normalized_symbol) DO NOTHING
                        """,
                        (operator_id, symbol, symbol),
                    )
        except Exception:
            return self._mark_unavailable()
        return self._mark_ok()

    def remove_watchlist(self, symbol: str, operator_id: str = "operator") -> PersistenceStatus:
        self._fallback.remove_watchlist(symbol, operator_id)
        try:
            with self._connect() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        DELETE FROM watchlist
                        WHERE operator_id = %s AND normalized_symbol = %s
                        """,
                        (operator_id, symbol),
                    )
        except Exception:
            return self._mark_unavailable()
        return self._mark_ok()

    def recent_runs(self, limit: int) -> list[dict]:
        try:
            with self._connect() as conn:
                with conn.cursor() as cursor:
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
                    rows = cursor.fetchall()
        except Exception:
            self._mark_unavailable()
            return self._fallback.recent_runs(limit)
        self._mark_ok()
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
        try:
            with self._connect() as conn:
                with conn.cursor() as cursor:
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
                    row = cursor.fetchone()
        except Exception:
            self._mark_unavailable()
            return self._fallback.get_run(run_id)
        self._mark_ok()
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


def build_persistence_repository(settings: Settings) -> PersistenceRepository:
    if settings.supabase_db_url:
        return SupabasePersistenceRepository(settings.supabase_db_url)
    return InMemoryPersistenceRepository()
