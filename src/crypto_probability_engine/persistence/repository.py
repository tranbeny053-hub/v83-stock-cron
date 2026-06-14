"""Best-effort persistence repositories for compact app state."""

from __future__ import annotations

import re
import threading
import time
from collections import OrderedDict
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import Any, Literal, Protocol

import httpx

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

    def save_news_item(self, row: Mapping[str, Any]) -> PersistenceStatus:
        """Persist compact news metadata item."""

    def save_news_cluster(self, row: Mapping[str, Any]) -> PersistenceStatus:
        """Persist compact news cluster summary."""

    def save_news_evidence_link(self, row: Mapping[str, Any]) -> PersistenceStatus:
        """Persist compact run-to-news evidence link."""

    def save_prediction(self, row: Mapping[str, Any]) -> PersistenceStatus:
        """Persist immutable prediction ledger row."""

    def fetch_due_unresolved_predictions(self, now_utc: Any, limit: int) -> list[dict]:
        """Fetch due live predictions with no immutable outcome row yet."""

    def save_prediction_outcome(self, row: Mapping[str, Any]) -> PersistenceStatus:
        """Persist immutable prediction outcome row."""

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
        self._news_items: list[dict] = []
        self._news_clusters: list[dict] = []
        self._news_evidence_links: list[dict] = []
        self._predictions: OrderedDict[str, dict] = OrderedDict()
        self._prediction_outcomes: OrderedDict[str, dict] = OrderedDict()
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

    def save_news_item(self, row: Mapping[str, Any]) -> PersistenceStatus:
        self._news_items.append(dict(row))
        return self.persistence_status()

    def save_news_cluster(self, row: Mapping[str, Any]) -> PersistenceStatus:
        self._news_clusters.append(dict(row))
        return self.persistence_status()

    def save_news_evidence_link(self, row: Mapping[str, Any]) -> PersistenceStatus:
        self._news_evidence_links.append(dict(row))
        return self.persistence_status()

    def save_prediction(self, row: Mapping[str, Any]) -> PersistenceStatus:
        prediction_id = str(row.get("prediction_id", ""))
        if prediction_id and prediction_id not in self._predictions:
            self._predictions[prediction_id] = dict(row)
        return self.persistence_status()

    def fetch_due_unresolved_predictions(self, now_utc: Any, limit: int) -> list[dict]:
        due = [
            dict(row)
            for row in self._predictions.values()
            if row.get("is_live_data") is True
            and str(row.get("prediction_id", "")) not in self._prediction_outcomes
            and _timestamp_before(row.get("horizon_end_utc"), now_utc)
        ]
        due.sort(key=lambda row: str(row.get("horizon_end_utc", "")))
        return due[: max(0, int(limit))]

    def save_prediction_outcome(self, row: Mapping[str, Any]) -> PersistenceStatus:
        prediction_id = str(row.get("prediction_id", ""))
        if prediction_id and prediction_id not in self._prediction_outcomes:
            self._prediction_outcomes[prediction_id] = dict(row)
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
        direct_connection_factory: Callable[[], Any] | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._db_url = db_url
        self._connect_timeout_seconds = connect_timeout_seconds
        self._operation_timeout_seconds = operation_timeout_seconds
        self._statement_timeout_ms = max(1000, int(operation_timeout_seconds * 1000))
        self._circuit_cooldown_seconds = circuit_cooldown_seconds
        self._pool_factory = pool_factory
        self._direct_connection_factory = direct_connection_factory
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
        return "SUPABASE_POSTGRES"

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

    def _direct_connection(self):
        if self._direct_connection_factory is not None:
            return self._direct_connection_factory()
        import psycopg

        return psycopg.connect(
            self._db_url,
            connect_timeout=self._connect_timeout_seconds,
            prepare_threshold=None,
        )

    def _run_db(self, operation):
        if not self.maybe_can_attempt():
            return "UNAVAILABLE", None
        try:
            with self._connection() as conn:
                with conn.cursor() as cursor:
                    _set_local_statement_timeout(cursor, self._statement_timeout_ms)
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

    def save_news_item(self, row: Mapping[str, Any]) -> PersistenceStatus:
        self._fallback.save_news_item(row)
        status, _ = self._run_db(
            lambda cursor: cursor.execute(
                """
                INSERT INTO news_items (
                  item_id, run_id, normalized_symbol, provider, source_name, domain,
                  title, snippet, url, url_hash, title_hash, published_at, fetched_at,
                  language, macro_or_micro, event_class, relevance_score, freshness_score,
                  source_authority_score, confidence_score, cluster_id
                )
                VALUES (
                  %(item_id)s, %(run_id)s, %(normalized_symbol)s, %(provider)s,
                  %(source_name)s, %(domain)s, %(title)s, %(snippet)s, %(url)s,
                  %(url_hash)s, %(title_hash)s, %(published_at)s, %(fetched_at)s,
                  %(language)s, %(macro_or_micro)s, %(event_class)s, %(relevance_score)s,
                  %(freshness_score)s, %(source_authority_score)s, %(confidence_score)s,
                  %(cluster_id)s
                )
                ON CONFLICT (item_id) DO UPDATE SET
                  run_id = EXCLUDED.run_id,
                  normalized_symbol = EXCLUDED.normalized_symbol,
                  relevance_score = EXCLUDED.relevance_score,
                  freshness_score = EXCLUDED.freshness_score,
                  source_authority_score = EXCLUDED.source_authority_score,
                  confidence_score = EXCLUDED.confidence_score,
                  cluster_id = EXCLUDED.cluster_id
                """,
                dict(row),
            )
        )
        return status

    def save_news_cluster(self, row: Mapping[str, Any]) -> PersistenceStatus:
        self._fallback.save_news_cluster(row)
        status, _ = self._run_db(
            lambda cursor: cursor.execute(
                """
                INSERT INTO news_clusters (
                  cluster_id, run_id, normalized_symbol, representative_title,
                  macro_or_micro, event_class, source_count, item_count,
                  dropped_count, max_relevance_score
                )
                VALUES (
                  %(cluster_id)s, %(run_id)s, %(normalized_symbol)s,
                  %(representative_title)s, %(macro_or_micro)s, %(event_class)s,
                  %(source_count)s, %(item_count)s, %(dropped_count)s,
                  %(max_relevance_score)s
                )
                ON CONFLICT (cluster_id) DO UPDATE SET
                  run_id = EXCLUDED.run_id,
                  normalized_symbol = EXCLUDED.normalized_symbol,
                  source_count = EXCLUDED.source_count,
                  item_count = EXCLUDED.item_count,
                  dropped_count = EXCLUDED.dropped_count,
                  max_relevance_score = EXCLUDED.max_relevance_score
                """,
                dict(row),
            )
        )
        return status

    def save_news_evidence_link(self, row: Mapping[str, Any]) -> PersistenceStatus:
        self._fallback.save_news_evidence_link(row)
        status, _ = self._run_db(
            lambda cursor: cursor.execute(
                """
                INSERT INTO news_evidence_links (
                  run_id, cluster_id, item_id, evidence_type, relevance_score
                )
                VALUES (
                  %(run_id)s, %(cluster_id)s, %(item_id)s, %(evidence_type)s,
                  %(relevance_score)s
                )
                ON CONFLICT (run_id, cluster_id, item_id) DO UPDATE SET
                  evidence_type = EXCLUDED.evidence_type,
                  relevance_score = EXCLUDED.relevance_score
                """,
                dict(row),
            )
        )
        return status

    def save_prediction(self, row: Mapping[str, Any]) -> PersistenceStatus:
        self._fallback.save_prediction(row)
        status, _ = self._run_db(
            lambda cursor: cursor.execute(
                """
                INSERT INTO predictions (
                  prediction_id, run_id, operator_id, symbol, normalized_symbol,
                  timeframe, horizon_bars, predicted_at_utc, reference_close_utc,
                  reference_price, horizon_end_utc, p_up_frac, p_down_frac,
                  p_timeout_frac, decision_band_frac, model_version, methodology_version,
                  calibration_status, reliability_status, epistemic_sufficiency,
                  gate_action, data_source, is_live_data, cross_provider_state
                )
                VALUES (
                  %(prediction_id)s, %(run_id)s, %(operator_id)s, %(symbol)s,
                  %(normalized_symbol)s, %(timeframe)s, %(horizon_bars)s,
                  %(predicted_at_utc)s, %(reference_close_utc)s, %(reference_price)s,
                  %(horizon_end_utc)s, %(p_up_frac)s, %(p_down_frac)s,
                  %(p_timeout_frac)s, %(decision_band_frac)s, %(model_version)s,
                  %(methodology_version)s, %(calibration_status)s,
                  %(reliability_status)s, %(epistemic_sufficiency)s, %(gate_action)s,
                  %(data_source)s, %(is_live_data)s, %(cross_provider_state)s
                )
                ON CONFLICT (prediction_id) DO NOTHING
                """,
                dict(row),
            )
        )
        return status

    def fetch_due_unresolved_predictions(self, now_utc: Any, limit: int) -> list[dict]:
        if not self.maybe_can_attempt():
            raise RuntimeError(
                "SUPABASE_POSTGRES due query failed: RuntimeError [circuit] CircuitOpen"
            )
        phase = "connect"
        try:
            with self._direct_connection() as conn:
                with conn.cursor() as cursor:
                    phase = "set_timeout"
                    _set_local_statement_timeout(cursor, self._statement_timeout_ms)
                    phase = "query"
                    _execute_due_prediction_query(cursor, now_utc, max(0, int(limit)))
                    phase = "fetch"
                    rows = cursor.fetchall()
                    phase = "convert"
                    converted = [_prediction_row_from_db(row) for row in rows]
        except Exception as exc:
            self.mark_unavailable()
            raise RuntimeError(_postgres_error_message("due query", phase, exc)) from None
        self._mark_ok()
        return converted

    def save_prediction_outcome(self, row: Mapping[str, Any]) -> PersistenceStatus:
        if not self.maybe_can_attempt():
            raise RuntimeError(
                "SUPABASE_POSTGRES outcome write failed: RuntimeError [circuit] CircuitOpen"
            )
        phase = "connect"
        try:
            with self._direct_connection() as conn:
                with conn.cursor() as cursor:
                    phase = "set_timeout"
                    _set_local_statement_timeout(cursor, self._statement_timeout_ms)
                    phase = "write"
                    cursor.execute(
                        """
                        INSERT INTO public.prediction_outcomes (
                          prediction_id, resolved_at_utc, outcome_close_utc,
                          outcome_reference_price, terminal_return_frac, realized_label,
                          decision_band_frac, max_favorable_frac, max_adverse_frac,
                          candles_observed, resolver_version, data_source, is_live_data
                        )
                        VALUES (
                          %(prediction_id)s, %(resolved_at_utc)s, %(outcome_close_utc)s,
                          %(outcome_reference_price)s, %(terminal_return_frac)s,
                          %(realized_label)s, %(decision_band_frac)s, %(max_favorable_frac)s,
                          %(max_adverse_frac)s, %(candles_observed)s, %(resolver_version)s,
                          %(data_source)s, %(is_live_data)s
                        )
                        ON CONFLICT (prediction_id) DO NOTHING
                        """,
                        dict(row),
                    )
        except Exception as exc:
            self.mark_unavailable()
            raise RuntimeError(_postgres_error_message("outcome write", phase, exc)) from None
        self._mark_ok()
        return self.persistence_status()

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


class SupabaseRestRepository:
    """Supabase PostgREST persistence adapter for HTTPS-only runtimes."""

    def __init__(
        self,
        supabase_url: str,
        service_role_key: str,
        *,
        timeout_seconds: float = 3.0,
        circuit_cooldown_seconds: float = 60.0,
        client: httpx.Client | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._base_url = f"{supabase_url.rstrip('/')}/rest/v1"
        self._service_role_key = service_role_key
        self._timeout_seconds = timeout_seconds
        self._circuit_cooldown_seconds = circuit_cooldown_seconds
        self._client = client or httpx.Client(timeout=timeout_seconds)
        self._owns_client = client is None
        self._clock = clock
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
        return "SUPABASE_REST"

    def circuit_state(self) -> str:
        with self._lock:
            now = self._clock()
            if self._last_status != "UNAVAILABLE":
                return "CLOSED"
            if now < self._circuit_open_until:
                return "OPEN"
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

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def save_run(self, summary: Mapping[str, Any]) -> PersistenceStatus:
        self._fallback.save_run(summary)
        status, _ = self._run_rest(
            lambda: self._request(
                "POST",
                "analysis_runs",
                json=dict(summary),
                params={"on_conflict": "run_id"},
                prefer="resolution=merge-duplicates,return=minimal",
            )
        )
        return status

    def save_timeframe_result(self, row: Mapping[str, Any]) -> PersistenceStatus:
        self._fallback.save_timeframe_result(row)
        status, _ = self._run_rest(
            lambda: self._request(
                "POST",
                "analysis_timeframe_results",
                json=dict(row),
                prefer="return=minimal",
            )
        )
        return status

    def save_provider_observation(self, row: Mapping[str, Any]) -> PersistenceStatus:
        self._fallback.save_provider_observation(row)
        status, _ = self._run_rest(
            lambda: self._request(
                "POST",
                "provider_observations",
                json=dict(row),
                prefer="return=minimal",
            )
        )
        return status

    def save_news_item(self, row: Mapping[str, Any]) -> PersistenceStatus:
        self._fallback.save_news_item(row)
        status, _ = self._run_rest(
            lambda: self._request(
                "POST",
                "news_items",
                json=dict(row),
                params={"on_conflict": "item_id"},
                prefer="resolution=merge-duplicates,return=minimal",
            )
        )
        return status

    def save_news_cluster(self, row: Mapping[str, Any]) -> PersistenceStatus:
        self._fallback.save_news_cluster(row)
        status, _ = self._run_rest(
            lambda: self._request(
                "POST",
                "news_clusters",
                json=dict(row),
                params={"on_conflict": "cluster_id"},
                prefer="resolution=merge-duplicates,return=minimal",
            )
        )
        return status

    def save_news_evidence_link(self, row: Mapping[str, Any]) -> PersistenceStatus:
        self._fallback.save_news_evidence_link(row)
        status, _ = self._run_rest(
            lambda: self._request(
                "POST",
                "news_evidence_links",
                json=dict(row),
                params={"on_conflict": "run_id,cluster_id,item_id"},
                prefer="resolution=merge-duplicates,return=minimal",
            )
        )
        return status

    def save_prediction(self, row: Mapping[str, Any]) -> PersistenceStatus:
        self._fallback.save_prediction(row)
        status, _ = self._run_rest(
            lambda: self._request(
                "POST",
                "predictions",
                json=dict(row),
                params={"on_conflict": "prediction_id"},
                prefer="resolution=ignore-duplicates,return=minimal",
            )
        )
        return status

    def fetch_due_unresolved_predictions(self, now_utc: Any, limit: int) -> list[dict]:
        status, rows = self._run_rest(
            lambda: self._request(
                "GET",
                "predictions",
                params={
                    "select": (
                        "prediction_id,run_id,operator_id,symbol,normalized_symbol,timeframe,"
                        "horizon_bars,predicted_at_utc,reference_close_utc,reference_price,"
                        "horizon_end_utc,p_up_frac,p_down_frac,p_timeout_frac,"
                        "decision_band_frac,model_version,methodology_version,"
                        "calibration_status,reliability_status,epistemic_sufficiency,"
                        "gate_action,data_source,is_live_data,cross_provider_state"
                    ),
                    "horizon_end_utc": f"lt.{_iso_for_query(now_utc)}",
                    "is_live_data": "eq.true",
                    "order": "horizon_end_utc.asc",
                    "limit": str(limit),
                },
            )
        )
        if status == "UNAVAILABLE" or not isinstance(rows, list):
            return self._fallback.fetch_due_unresolved_predictions(now_utc, limit)
        prediction_ids = [str(row.get("prediction_id", "")) for row in rows]
        existing = self._fetch_existing_outcome_ids(prediction_ids)
        return [dict(row) for row in rows if str(row.get("prediction_id", "")) not in existing]

    def save_prediction_outcome(self, row: Mapping[str, Any]) -> PersistenceStatus:
        self._fallback.save_prediction_outcome(row)
        status, _ = self._run_rest(
            lambda: self._request(
                "POST",
                "prediction_outcomes",
                json=dict(row),
                params={"on_conflict": "prediction_id"},
                prefer="resolution=ignore-duplicates,return=minimal",
            )
        )
        return status

    def list_watchlist(self, operator_id: str = "operator") -> list[str]:
        status, rows = self._run_rest(
            lambda: self._request(
                "GET",
                "watchlist",
                params={
                    "select": "display_symbol",
                    "operator_id": f"eq.{operator_id}",
                    "order": "created_at.asc",
                },
            )
        )
        if status == "UNAVAILABLE" or not isinstance(rows, list):
            return self._fallback.list_watchlist(operator_id)
        return [str(row["display_symbol"]) for row in rows if "display_symbol" in row]

    def add_watchlist(self, symbol: str, operator_id: str = "operator") -> PersistenceStatus:
        self._fallback.add_watchlist(symbol, operator_id)
        status, _ = self._run_rest(
            lambda: self._request(
                "POST",
                "watchlist",
                json={
                    "operator_id": operator_id,
                    "normalized_symbol": symbol,
                    "display_symbol": symbol,
                },
                params={"on_conflict": "operator_id,normalized_symbol"},
                prefer="resolution=merge-duplicates,return=minimal",
            )
        )
        return status

    def remove_watchlist(self, symbol: str, operator_id: str = "operator") -> PersistenceStatus:
        self._fallback.remove_watchlist(symbol, operator_id)
        status, _ = self._run_rest(
            lambda: self._request(
                "DELETE",
                "watchlist",
                params={
                    "operator_id": f"eq.{operator_id}",
                    "normalized_symbol": f"eq.{symbol}",
                },
                prefer="return=minimal",
            )
        )
        return status

    def recent_runs(self, limit: int) -> list[dict]:
        status, rows = self._run_rest(
            lambda: self._request(
                "GET",
                "analysis_runs",
                params={
                    "select": (
                        "run_id,symbol,normalized_symbol,analysis_mode,primary_timeframe,"
                        "disposition,total_score,data_source,is_live_data,analysis_hash,"
                        "as_of_utc,created_at"
                    ),
                    "order": "created_at.desc",
                    "limit": str(limit),
                },
            )
        )
        if status == "UNAVAILABLE" or not isinstance(rows, list):
            return self._fallback.recent_runs(limit)
        return [dict(row) for row in rows]

    def get_run(self, run_id: str) -> dict | None:
        status, rows = self._run_rest(
            lambda: self._request(
                "GET",
                "analysis_runs",
                params={
                    "select": (
                        "run_id,symbol,normalized_symbol,analysis_mode,primary_timeframe,"
                        "disposition,total_score,data_source,is_live_data,analysis_hash,"
                        "as_of_utc,created_at"
                    ),
                    "run_id": f"eq.{run_id}",
                    "limit": "1",
                },
            )
        )
        if status == "UNAVAILABLE":
            return self._fallback.get_run(run_id)
        if not isinstance(rows, list) or not rows:
            return None
        return dict(rows[0])

    def _run_rest(self, operation):
        if not self.maybe_can_attempt():
            return "UNAVAILABLE", None
        try:
            result = operation()
        except Exception:
            return self.mark_unavailable(), None
        return self._mark_ok(), result

    def _request(
        self,
        method: str,
        table: str,
        *,
        json: Mapping[str, Any] | None = None,
        params: Mapping[str, str] | None = None,
        prefer: str | None = None,
    ):
        headers = self._headers(prefer=prefer)
        response = self._client.request(
            method,
            f"{self._base_url}/{table}",
            headers=headers,
            params=dict(params or {}),
            json=dict(json) if json is not None else None,
            timeout=self._timeout_seconds,
        )
        if response.status_code not in {200, 201, 204}:
            raise RuntimeError("Supabase REST persistence request failed.")
        if response.status_code == 204 or not response.content:
            return None
        return response.json()

    def _fetch_existing_outcome_ids(self, prediction_ids: list[str]) -> set[str]:
        prediction_ids = [prediction_id for prediction_id in prediction_ids if prediction_id]
        if not prediction_ids:
            return set()
        status, rows = self._run_rest(
            lambda: self._request(
                "GET",
                "prediction_outcomes",
                params={
                    "select": "prediction_id",
                    "prediction_id": f"in.({_postgrest_csv(prediction_ids)})",
                },
            )
        )
        if status == "UNAVAILABLE" or not isinstance(rows, list):
            return set()
        return {str(row.get("prediction_id")) for row in rows if row.get("prediction_id")}

    def _headers(self, *, prefer: str | None = None) -> dict[str, str]:
        headers = {
            "apikey": self._service_role_key,
            "Authorization": f"Bearer {self._service_role_key}",
            "Content-Type": "application/json",
        }
        if prefer:
            headers["Prefer"] = prefer
        return headers


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


def _set_local_statement_timeout(cursor, timeout_ms: int) -> None:
    cursor.execute(f"SET LOCAL statement_timeout = {int(timeout_ms)}")


def _execute_due_prediction_query(cursor, now_utc: Any, limit: int) -> None:
    cursor.execute(
        """
        SELECT p.prediction_id, p.run_id, p.operator_id, p.symbol, p.normalized_symbol,
               p.timeframe, p.horizon_bars, p.predicted_at_utc, p.reference_close_utc,
               p.reference_price, p.horizon_end_utc, p.p_up_frac, p.p_down_frac,
               p.p_timeout_frac, p.decision_band_frac, p.model_version,
               p.methodology_version, p.calibration_status, p.reliability_status,
               p.epistemic_sufficiency, p.gate_action, p.data_source, p.is_live_data,
               p.cross_provider_state
        FROM public.predictions p
        LEFT JOIN public.prediction_outcomes o
          ON o.prediction_id = p.prediction_id
        WHERE o.prediction_id IS NULL
          AND p.is_live_data = true
          AND p.horizon_end_utc < %(now_utc)s
        ORDER BY p.horizon_end_utc ASC
        LIMIT %(limit)s
        """,
        {"now_utc": now_utc, "limit": limit},
    )


def _fetch_due_prediction_rows(cursor, now_utc: Any, limit: int):
    _execute_due_prediction_query(cursor, now_utc, limit)
    return cursor.fetchall()


def _prediction_row_from_db(row) -> dict:
    keys = (
        "prediction_id",
        "run_id",
        "operator_id",
        "symbol",
        "normalized_symbol",
        "timeframe",
        "horizon_bars",
        "predicted_at_utc",
        "reference_close_utc",
        "reference_price",
        "horizon_end_utc",
        "p_up_frac",
        "p_down_frac",
        "p_timeout_frac",
        "decision_band_frac",
        "model_version",
        "methodology_version",
        "calibration_status",
        "reliability_status",
        "epistemic_sufficiency",
        "gate_action",
        "data_source",
        "is_live_data",
        "cross_provider_state",
    )
    if isinstance(row, Mapping):
        return {
            key: value.isoformat() if hasattr(value, "isoformat") else value
            for key, value in row.items()
        }
    return {
        key: value.isoformat() if hasattr(value, "isoformat") else value
        for key, value in zip(keys, row, strict=True)
    }


def _postgres_error_message(operation: str, phase: str, exc: Exception) -> str:
    message = _sanitize_postgres_error(str(exc))
    return f"SUPABASE_POSTGRES {operation} failed: {type(exc).__name__} [{phase}] {message}"


def _sanitize_postgres_error(message: str) -> str:
    compact = " ".join(str(message).split())
    compact = re.sub(r"(?i)\b(?:postgresql|postgres)://\S+", "<redacted-postgres-url>", compact)
    compact = re.sub(
        r"(?i)\b(password|apikey|authorization|bearer)\b\s*[:=]\s*\S+",
        r"\1=<redacted>",
        compact,
    )
    return (compact or "no detail")[:200]


def _iso_for_query(value: Any) -> str:
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def _timestamp_before(left: Any, right: Any) -> bool:
    try:
        return _to_utc_datetime(left) < _to_utc_datetime(right)
    except (TypeError, ValueError):
        return False


def _to_utc_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    else:
        raise TypeError("Unsupported timestamp value.")
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _postgrest_csv(values: list[str]) -> str:
    return ",".join(f'"{value}"' for value in values)


def build_persistence_repository(settings: Settings) -> PersistenceRepository:
    if settings.supabase_url and settings.supabase_service_role_key:
        return SupabaseRestRepository(
            settings.supabase_url,
            settings.supabase_service_role_key,
        )
    if settings.supabase_db_url:
        return SupabasePersistenceRepository(settings.supabase_db_url)
    return InMemoryPersistenceRepository()
