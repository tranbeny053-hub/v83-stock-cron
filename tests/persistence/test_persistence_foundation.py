from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import httpx

from crypto_probability_engine.api.analysis_service import PersistenceWork, _best_effort_persist
from crypto_probability_engine.config.settings import Settings
from crypto_probability_engine.persistence.repository import (
    InMemoryPersistenceRepository,
    SupabasePersistenceRepository,
    SupabaseRestRepository,
    build_persistence_repository,
)

ROOT = Path(__file__).resolve().parents[2]


class FakeClock:
    def __init__(self) -> None:
        self.now = 1_000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class FakeCursor:
    def __init__(self, rows=None, row=None, *, reject_set_params: bool = False) -> None:
        self.rows = rows or []
        self.row = row
        self.reject_set_params = reject_set_params
        self.statements: list[str] = []
        self.params: list[object] = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False

    def execute(self, statement, params=None) -> None:
        if (
            self.reject_set_params
            and str(statement).strip().upper().startswith("SET LOCAL STATEMENT_TIMEOUT")
            and params is not None
        ):
            raise SyntaxError("SET LOCAL statement_timeout does not accept bind params")
        self.statements.append(str(statement))
        self.params.append(params)

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return self.row


class FakeConnection:
    def __init__(self, cursor: FakeCursor | None = None) -> None:
        self._cursor = cursor or FakeCursor()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False

    def cursor(self) -> FakeCursor:
        return self._cursor


class FakePool:
    def __init__(self) -> None:
        self.attempts = 0
        self.fail = True
        self.closed = False

    def connection(self, timeout=None):
        self.attempts += 1
        if self.fail:
            raise RuntimeError("database unavailable")
        return FakeConnection()

    def close(self) -> None:
        self.closed = True


def test_in_memory_repository_watchlist_and_runs_are_stateless() -> None:
    repo = InMemoryPersistenceRepository()
    assert repo.persistence_status() == "STATELESS"
    assert repo.add_watchlist("BTC/USDT") == "STATELESS"
    assert repo.list_watchlist() == ["BTC/USDT"]
    assert repo.remove_watchlist("BTC/USDT") == "STATELESS"
    assert repo.list_watchlist() == []

    repo.save_run(
        {
            "run_id": "run_test",
            "symbol": "BTC",
            "normalized_symbol": "BTC/USDT",
            "analysis_mode": "METRICS_ONLY",
        }
    )
    assert repo.get_run("run_test")["normalized_symbol"] == "BTC/USDT"
    assert repo.recent_runs(1)[0]["run_id"] == "run_test"


def test_initial_migration_is_idempotent_and_contains_no_secret_values() -> None:
    sql = (ROOT / "migrations" / "0001_init.sql").read_text(encoding="utf-8")
    for table in (
        "watchlist",
        "analysis_runs",
        "analysis_timeframe_results",
        "provider_observations",
        "app_events",
    ):
        assert f"CREATE TABLE IF NOT EXISTS {table}" in sql
    assert "CREATE INDEX IF NOT EXISTS" in sql
    assert "ALTER TABLE" not in sql
    assert "DROP TABLE" not in sql
    for marker in ("SUPABASE_DB_URL", "SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY"):
        assert marker not in sql


def test_prediction_ledger_migration_is_idempotent_and_compact() -> None:
    sql = (ROOT / "migrations" / "0003_prediction_ledger.sql").read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS predictions" in sql
    assert "prediction_id TEXT PRIMARY KEY" in sql
    assert "CREATE INDEX IF NOT EXISTS idx_predictions_horizon_end" in sql
    assert "CREATE INDEX IF NOT EXISTS idx_predictions_symbol_timeframe_predicted" in sql
    assert "CREATE INDEX IF NOT EXISTS idx_predictions_model_timeframe" in sql
    assert "ALTER TABLE" not in sql
    assert "DROP TABLE" not in sql
    for marker in (
        "SUPABASE_DB_URL",
        "SUPABASE_URL",
        "SUPABASE_SERVICE_ROLE_KEY",
        "article_body",
        "full_text",
        "full_article",
    ):
        assert marker not in sql


def test_prediction_outcome_migration_is_idempotent_and_compact() -> None:
    sql = (ROOT / "migrations" / "0004_prediction_outcomes.sql").read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS prediction_outcomes" in sql
    assert "prediction_id TEXT PRIMARY KEY" in sql
    assert "CHECK (realized_label IN ('UP','DOWN','TIMEOUT'))" in sql
    assert "CREATE INDEX IF NOT EXISTS idx_prediction_outcomes_realized_label" in sql
    assert "ALTER TABLE" not in sql
    assert "DROP TABLE" not in sql
    for marker in (
        "SUPABASE_DB_URL",
        "SUPABASE_URL",
        "SUPABASE_SERVICE_ROLE_KEY",
        "article_body",
        "full_text",
        "full_article",
    ):
        assert marker not in sql


def test_in_memory_prediction_rows_are_immutable_by_prediction_id() -> None:
    repo = InMemoryPersistenceRepository()
    first = _sample_prediction()
    second = {**first, "reference_price": 999_999.0, "p_up_frac": 0.99}

    assert repo.save_prediction(first) == "STATELESS"
    assert repo.save_prediction(second) == "STATELESS"

    stored = repo._predictions[first["prediction_id"]]  # noqa: SLF001 - compact test probe
    assert len(repo._predictions) == 1
    assert stored["reference_price"] == first["reference_price"]
    assert stored["p_up_frac"] == first["p_up_frac"]


def test_in_memory_due_predictions_exclude_non_live_future_and_resolved() -> None:
    repo = InMemoryPersistenceRepository()
    due = _sample_prediction()
    future = {**_sample_prediction(), "prediction_id": "future:4H"}
    future["horizon_end_utc"] = "2026-06-09T00:00:00Z"
    non_live = {**_sample_prediction(), "prediction_id": "fixture:4H", "is_live_data": False}
    resolved = {**_sample_prediction(), "prediction_id": "resolved:4H"}
    repo.save_prediction(future)
    repo.save_prediction(non_live)
    repo.save_prediction(resolved)
    repo.save_prediction(due)
    repo.save_prediction_outcome({**_sample_outcome(), "prediction_id": "resolved:4H"})

    rows = repo.fetch_due_unresolved_predictions(
        datetime(2026, 6, 8, 0, 0, 1, tzinfo=UTC),
        limit=10,
    )

    assert [row["prediction_id"] for row in rows] == [due["prediction_id"]]


def test_in_memory_prediction_outcomes_are_immutable_by_prediction_id() -> None:
    repo = InMemoryPersistenceRepository()
    first = _sample_outcome()
    second = {**first, "realized_label": "DOWN", "terminal_return_frac": -0.10}

    assert repo.save_prediction_outcome(first) == "STATELESS"
    assert repo.save_prediction_outcome(second) == "STATELESS"

    stored = repo._prediction_outcomes[first["prediction_id"]]  # noqa: SLF001
    assert len(repo._prediction_outcomes) == 1
    assert stored["realized_label"] == "UP"
    assert stored["terminal_return_frac"] == first["terminal_return_frac"]


def test_in_memory_calibration_read_filters_live_rows_labels_and_options() -> None:
    repo = InMemoryPersistenceRepository()
    due = _sample_prediction()
    due_outcome = _sample_outcome()
    non_live_prediction = {
        **_sample_prediction(),
        "prediction_id": "non_live_prediction:4H",
        "is_live_data": False,
    }
    non_live_outcome = {**_sample_outcome(), "prediction_id": "non_live_prediction:4H"}
    non_live_outcome_row = {
        **_sample_prediction(),
        "prediction_id": "non_live_outcome:4H",
    }
    non_live_result = {
        **_sample_outcome(),
        "prediction_id": "non_live_outcome:4H",
        "is_live_data": False,
    }
    invalid_label_prediction = {
        **_sample_prediction(),
        "prediction_id": "invalid_label:4H",
    }
    invalid_label_outcome = {
        **_sample_outcome(),
        "prediction_id": "invalid_label:4H",
        "realized_label": "BAD",
    }
    for prediction, outcome in (
        (due, due_outcome),
        (non_live_prediction, non_live_outcome),
        (non_live_outcome_row, non_live_result),
        (invalid_label_prediction, invalid_label_outcome),
    ):
        repo.save_prediction(prediction)
        repo.save_prediction_outcome(outcome)

    rows = repo.fetch_resolved_prediction_outcomes_for_calibration(
        timeframe="4H",
        normalized_symbol="BTC/USDT",
        model_version="phase1a-wave4b0",
        methodology_version="heuristic-v1-wave4b0",
        since="2026-06-08T00:00:00Z",
        until="2026-06-08T00:00:00Z",
        limit=10,
    )

    assert len(rows) == 1
    assert rows[0]["prediction_id"] == due["prediction_id"]
    assert rows[0]["realized_label"] == "UP"
    assert rows[0]["prediction_is_live_data"] is True
    assert rows[0]["outcome_is_live_data"] is True


def test_best_effort_persist_defensively_marks_unavailable() -> None:
    class RaisingRepository:
        def __init__(self) -> None:
            self.marked = False

        def persistence_status(self) -> str:
            return "OK"

        def mark_unavailable(self) -> str:
            self.marked = True
            return "UNAVAILABLE"

        def save_run(self, summary: dict) -> str:
            raise RuntimeError("unexpected persistence failure")

        def save_timeframe_result(self, row: dict) -> str:
            return "OK"

        def save_provider_observation(self, row: dict) -> str:
            return "OK"

    repo = RaisingRepository()
    work = PersistenceWork(
        run_summary={"run_id": "run_test"},
        timeframe_result={"run_id": "run_test", "timeframe": "4H"},
        provider_observations=({"run_id": "run_test", "provider": "fixture"},),
    )
    assert _best_effort_persist(work, repo) == "UNAVAILABLE"
    assert repo.marked is True


def test_supabase_circuit_breaker_skips_attempts_until_cooldown() -> None:
    clock = FakeClock()
    pool = FakePool()
    repo = SupabasePersistenceRepository(
        "postgresql://example.invalid/db",
        pool_factory=lambda: pool,
        circuit_cooldown_seconds=60.0,
        clock=clock,
    )

    assert repo.save_run({"run_id": "run_test"}) == "UNAVAILABLE"
    assert pool.attempts == 1
    assert repo.persistence_status() == "UNAVAILABLE"

    assert repo.save_timeframe_result({"run_id": "run_test"}) == "UNAVAILABLE"
    assert pool.attempts == 1

    clock.advance(61.0)
    pool.fail = False
    assert repo.save_provider_observation({"run_id": "run_test"}) == "OK"
    assert pool.attempts == 2
    assert repo.persistence_status() == "OK"
    repo.close()
    assert pool.closed is True


def test_supabase_postgres_prediction_write_is_do_nothing_on_conflict() -> None:
    cursor = FakeCursor()

    class StaticPool:
        def __init__(self) -> None:
            self.attempts = 0

        def connection(self, timeout=None):
            self.attempts += 1
            return FakeConnection(cursor)

    pool = StaticPool()
    repo = SupabasePersistenceRepository(
        "postgresql://example.invalid/db",
        pool_factory=lambda: pool,
    )

    assert repo.save_prediction(_sample_prediction()) == "OK"
    statements = "\n".join(cursor.statements)
    assert "INSERT INTO predictions" in statements
    assert "ON CONFLICT (prediction_id) DO NOTHING" in statements
    assert pool.attempts == 1


def test_supabase_run_db_sets_timeout_without_bind_and_returns_callback_rows() -> None:
    cursor = FakeCursor(rows=[("ok",)], reject_set_params=True)

    class StaticPool:
        def connection(self, timeout=None):
            return FakeConnection(cursor)

    repo = SupabasePersistenceRepository(
        "postgresql://example.invalid/db",
        pool_factory=lambda: StaticPool(),
    )

    status, rows = repo._run_db(  # noqa: SLF001 - wrapper regression test
        lambda db_cursor: (
            db_cursor.execute("SELECT 1"),
            db_cursor.fetchall(),
        )[1]
    )

    assert status == "OK"
    assert rows == [("ok",)]
    assert cursor.statements[0] == "SET LOCAL statement_timeout = 3000"
    assert cursor.params[0] is None


def test_supabase_postgres_due_query_and_outcome_write_are_immutable() -> None:
    cursor = FakeCursor(rows=[_sample_prediction_db_row()], reject_set_params=True)
    outcome_cursor = FakeCursor(reject_set_params=True)
    direct_connections = iter((FakeConnection(cursor), FakeConnection(outcome_cursor)))

    class StaticPool:
        def __init__(self) -> None:
            self.attempts = 0

        def connection(self, timeout=None):
            self.attempts += 1
            raise AssertionError("pool wrapper should not be used for outcome resolver paths")

    repo = SupabasePersistenceRepository(
        "postgresql://example.invalid/db",
        pool_factory=lambda: StaticPool(),
        direct_connection_factory=lambda: next(direct_connections),
    )

    rows = repo.fetch_due_unresolved_predictions("2026-06-08T00:00:01Z", 5)
    assert rows[0]["prediction_id"] == "run_rest:4H"
    assert cursor.statements[0] == "SET LOCAL statement_timeout = 3000"
    assert cursor.params[0] is None
    query = "\n".join(cursor.statements)
    assert "FROM public.predictions p" in query
    assert "LEFT JOIN public.prediction_outcomes o" in query
    assert "ON o.prediction_id = p.prediction_id" in query
    assert "WHERE o.prediction_id IS NULL" in query
    assert "AND p.is_live_data = true" in query
    assert "AND p.horizon_end_utc < %(now_utc)s" in query
    assert "ORDER BY p.horizon_end_utc ASC" in query
    assert "LIMIT %(limit)s" in query
    assert {"now_utc": "2026-06-08T00:00:01Z", "limit": 5} in cursor.params

    assert repo.save_prediction_outcome(_sample_outcome()) == "OK"
    assert outcome_cursor.statements[0] == "SET LOCAL statement_timeout = 3000"
    assert outcome_cursor.params[0] is None
    statements = "\n".join(outcome_cursor.statements)
    assert "INSERT INTO public.prediction_outcomes" in statements
    assert "ON CONFLICT (prediction_id) DO NOTHING" in statements


def test_supabase_postgres_due_query_converts_mapping_rows() -> None:
    cursor = FakeCursor(rows=[_sample_prediction()], reject_set_params=True)

    class StaticPool:
        def connection(self, timeout=None):
            return FakeConnection(cursor)

    repo = SupabasePersistenceRepository(
        "postgresql://example.invalid/db",
        direct_connection_factory=lambda: FakeConnection(cursor),
    )

    rows = repo.fetch_due_unresolved_predictions("2026-06-08T00:00:01Z", 5)

    assert len(rows) == 1
    assert rows[0]["prediction_id"] == "run_rest:4H"
    assert rows[0]["normalized_symbol"] == "BTC/USDT"
    assert rows[0]["timeframe"] == "4H"
    assert rows[0]["horizon_end_utc"] == "2026-06-08T00:00:00Z"
    assert rows[0]["is_live_data"] is True


def test_supabase_postgres_due_query_uses_direct_connection_not_pool_wrapper() -> None:
    cursor = FakeCursor(
        rows=[_sample_prediction_db_row(), _sample_prediction_db_row()],
        reject_set_params=True,
    )

    class ExplodingPool:
        def connection(self, timeout=None):
            raise AssertionError("pool wrapper should not be used for due fetch")

    repo = SupabasePersistenceRepository(
        "postgresql://example.invalid/db",
        pool_factory=lambda: ExplodingPool(),
        direct_connection_factory=lambda: FakeConnection(cursor),
    )

    rows = repo.fetch_due_unresolved_predictions("2026-06-08T00:00:01Z", 10)

    assert len(rows) == 2
    assert rows[0]["prediction_id"] == "run_rest:4H"


def test_supabase_postgres_outcome_write_uses_direct_connection_not_pool_wrapper() -> None:
    cursor = FakeCursor(reject_set_params=True)

    class ExplodingPool:
        def connection(self, timeout=None):
            raise AssertionError("pool wrapper should not be used for outcome write")

    repo = SupabasePersistenceRepository(
        "postgresql://example.invalid/db",
        pool_factory=lambda: ExplodingPool(),
        direct_connection_factory=lambda: FakeConnection(cursor),
    )

    assert repo.save_prediction_outcome(_sample_outcome()) == "OK"
    assert cursor.statements[0] == "SET LOCAL statement_timeout = 3000"
    assert cursor.params[0] is None
    statements = "\n".join(cursor.statements)
    assert "INSERT INTO public.prediction_outcomes" in statements
    assert "ON CONFLICT (prediction_id) DO NOTHING" in statements


def test_supabase_postgres_due_query_failure_is_not_fake_empty() -> None:
    repo = SupabasePersistenceRepository(
        "postgresql://example.invalid/db",
        direct_connection_factory=lambda: (_ for _ in ()).throw(
            RuntimeError("database unavailable")
        ),
    )

    try:
        rows = repo.fetch_due_unresolved_predictions("2026-06-08T00:00:01Z", 5)
    except RuntimeError as exc:
        message = str(exc)
    else:  # pragma: no cover - documents the expected non-fallback behavior
        raise AssertionError(f"expected due query failure, got rows={rows!r}")

    assert (
        message
        == "SUPABASE_POSTGRES due query failed: RuntimeError [connect] database unavailable"
    )
    assert "postgresql://example.invalid/db" not in message


def test_supabase_postgres_outcome_write_failure_is_sanitized() -> None:
    repo = SupabasePersistenceRepository(
        "postgresql://example.invalid/db",
        direct_connection_factory=lambda: (_ for _ in ()).throw(
            RuntimeError("postgresql://user:credential@example.invalid/db auth failure")
        ),
    )

    try:
        status = repo.save_prediction_outcome(_sample_outcome())
    except RuntimeError as exc:
        message = str(exc)
    else:  # pragma: no cover - documents the expected non-fallback behavior
        raise AssertionError(f"expected outcome write failure, got status={status!r}")

    assert message.startswith("SUPABASE_POSTGRES outcome write failed: RuntimeError [connect]")
    assert "postgresql://user:credential@example.invalid/db" not in message
    assert "credential" not in message


def test_supabase_postgres_calibration_read_is_select_only_and_uses_literal_timeout() -> None:
    cursor = FakeCursor(rows=[_sample_calibration_db_row()], reject_set_params=True)

    class ExplodingPool:
        def connection(self, timeout=None):
            raise AssertionError("pool wrapper should not be used for calibration reads")

    repo = SupabasePersistenceRepository(
        "postgresql://example.invalid/db",
        pool_factory=lambda: ExplodingPool(),
        direct_connection_factory=lambda: FakeConnection(cursor),
    )

    rows = repo.fetch_resolved_prediction_outcomes_for_calibration(
        timeframe="4H",
        symbol="BTC",
        normalized_symbol="BTC/USDT",
        model_version="phase1a-wave4b0",
        methodology_version="heuristic-v1-wave4b0",
        since="2026-06-08T00:00:00Z",
        until="2026-06-08T01:00:00Z",
        limit=25,
    )

    assert len(rows) == 1
    assert rows[0]["prediction_id"] == "run_rest:4H"
    assert rows[0]["normalized_symbol"] == "BTC/USDT"
    assert rows[0]["timeframe"] == "4H"
    assert rows[0]["outcome_close_utc"] == "2026-06-08T00:00:00Z"
    assert rows[0]["outcome_is_live_data"] is True
    assert cursor.statements[0] == "SET LOCAL statement_timeout = 3000"
    assert cursor.params[0] is None
    query = "\n".join(cursor.statements[1:])
    query_upper = query.upper()
    assert "SELECT P.PREDICTION_ID" in query_upper
    assert "FROM PUBLIC.PREDICTIONS P" in query_upper
    assert "JOIN PUBLIC.PREDICTION_OUTCOMES O" in query_upper
    assert "ON O.PREDICTION_ID = P.PREDICTION_ID" in query_upper
    assert "P.IS_LIVE_DATA = TRUE" in query_upper
    assert "O.IS_LIVE_DATA = TRUE" in query_upper
    assert "O.REALIZED_LABEL IN ('UP', 'DOWN', 'TIMEOUT')" in query_upper
    assert "ORDER BY O.OUTCOME_CLOSE_UTC ASC" in query_upper
    assert "LIMIT %(LIMIT)S" in query_upper
    assert "INSERT" not in query_upper
    assert "UPDATE" not in query_upper
    assert "DELETE" not in query_upper
    assert cursor.params[1] == {
        "timeframe": "4H",
        "symbol": "BTC",
        "normalized_symbol": "BTC/USDT",
        "model_version": "phase1a-wave4b0",
        "methodology_version": "heuristic-v1-wave4b0",
        "since": "2026-06-08T00:00:00Z",
        "until": "2026-06-08T01:00:00Z",
        "limit": 25,
    }


def test_supabase_postgres_calibration_read_converts_mapping_rows() -> None:
    cursor = FakeCursor(rows=[_sample_calibration_mapping_row()], reject_set_params=True)
    repo = SupabasePersistenceRepository(
        "postgresql://example.invalid/db",
        direct_connection_factory=lambda: FakeConnection(cursor),
    )

    rows = repo.fetch_resolved_prediction_outcomes_for_calibration(limit=1)

    assert len(rows) == 1
    assert rows[0]["prediction_id"] == "run_rest:4H"
    assert rows[0]["realized_label"] == "UP"
    assert rows[0]["prediction_is_live_data"] is True


def test_supabase_postgres_calibration_read_failure_is_not_fake_empty() -> None:
    repo = SupabasePersistenceRepository(
        "postgresql://example.invalid/db",
        direct_connection_factory=lambda: (_ for _ in ()).throw(
            RuntimeError("postgresql://user:credential@example.invalid/db read failure")
        ),
    )

    try:
        rows = repo.fetch_resolved_prediction_outcomes_for_calibration(limit=5)
    except RuntimeError as exc:
        message = str(exc)
    else:  # pragma: no cover - documents the expected non-fallback behavior
        raise AssertionError(f"expected calibration read failure, got rows={rows!r}")

    assert message.startswith("SUPABASE_POSTGRES calibration read failed: RuntimeError [connect]")
    assert "postgresql://user:credential@example.invalid/db" not in message
    assert "credential" not in message


def test_supabase_rest_calibration_read_is_explicitly_not_implemented() -> None:
    repo = SupabaseRestRepository(
        "https://project.example.supabase.co",
        "test-service-role-key",
        client=rest_client(lambda request: httpx.Response(200, json=[])),
    )

    try:
        rows = repo.fetch_resolved_prediction_outcomes_for_calibration()
    except NotImplementedError as exc:
        message = str(exc)
    else:  # pragma: no cover
        raise AssertionError(f"expected REST calibration read to be unavailable, got {rows!r}")

    assert message == "Supabase REST calibration read is not implemented."


def rest_client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_runtime_selection_prefers_supabase_rest_over_postgres_url() -> None:
    repo = build_persistence_repository(
        Settings(
            **{
                "supabase_url": "https://project.example.supabase.co",
                "supabase_service_role_key": "test-service-role-key",
                "supabase_db_url": "postgresql://example.invalid/db",
            }
        )
    )

    assert isinstance(repo, SupabaseRestRepository)
    assert repo.repository_type() == "SUPABASE_REST"
    repo.close()


def test_runtime_selection_keeps_direct_postgres_when_rest_is_absent() -> None:
    repo = build_persistence_repository(
        Settings(**{"supabase_db_url": "postgresql://example.invalid/db"})
    )

    assert isinstance(repo, SupabasePersistenceRepository)
    assert repo.repository_type() == "SUPABASE_POSTGRES"


def test_supabase_rest_writes_compact_rows_with_backend_only_headers() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        assert request.url.host == "project.example.supabase.co"
        assert request.headers["apikey"] == "test-service-role-key"
        assert request.headers["authorization"] == "Bearer test-service-role-key"
        return httpx.Response(201, json=[])

    repo = SupabaseRestRepository(
        "https://project.example.supabase.co",
        "test-service-role-key",
        client=rest_client(handler),
    )

    assert repo.save_run(_sample_run_summary()) == "OK"
    assert repo.save_timeframe_result(_sample_timeframe_result()) == "OK"
    assert repo.save_provider_observation(_sample_provider_observation()) == "OK"
    assert [request.url.path for request in seen] == [
        "/rest/v1/analysis_runs",
        "/rest/v1/analysis_timeframe_results",
        "/rest/v1/provider_observations",
    ]
    assert "test-service-role-key" not in repo.repository_type()
    assert repo.persistence_status() == "OK"


def test_supabase_rest_writes_compact_news_metadata_rows() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        body = request.read().decode("utf-8")
        assert "article_body" not in body
        assert "full_text" not in body
        return httpx.Response(201, json=[])

    repo = SupabaseRestRepository(
        "https://project.example.supabase.co",
        "test-service-role-key",
        client=rest_client(handler),
    )

    assert repo.save_news_item(_sample_news_item()) == "OK"
    assert repo.save_news_cluster(_sample_news_cluster()) == "OK"
    assert repo.save_news_evidence_link(_sample_news_link()) == "OK"
    assert [request.url.path for request in seen] == [
        "/rest/v1/news_items",
        "/rest/v1/news_clusters",
        "/rest/v1/news_evidence_links",
    ]


def test_supabase_rest_prediction_write_uses_ignore_duplicates() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        body = request.read().decode("utf-8")
        assert "prediction_id" in body
        assert "article_body" not in body
        assert request.url.params["on_conflict"] == "prediction_id"
        assert request.headers["prefer"] == "resolution=ignore-duplicates,return=minimal"
        return httpx.Response(201, json=[])

    repo = SupabaseRestRepository(
        "https://project.example.supabase.co",
        "test-service-role-key",
        client=rest_client(handler),
    )

    assert repo.save_prediction(_sample_prediction()) == "OK"
    assert [request.url.path for request in seen] == ["/rest/v1/predictions"]


def test_supabase_rest_due_query_filters_existing_outcomes_and_writes_immutably() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.method == "GET" and request.url.path.endswith("/predictions"):
            return httpx.Response(200, json=[_sample_prediction()])
        if request.method == "GET" and request.url.path.endswith("/prediction_outcomes"):
            return httpx.Response(200, json=[])
        body = request.read().decode("utf-8")
        assert "prediction_id" in body
        assert request.url.params["on_conflict"] == "prediction_id"
        assert request.headers["prefer"] == "resolution=ignore-duplicates,return=minimal"
        return httpx.Response(201, json=[])

    repo = SupabaseRestRepository(
        "https://project.example.supabase.co",
        "test-service-role-key",
        client=rest_client(handler),
    )

    rows = repo.fetch_due_unresolved_predictions("2026-06-08T00:00:01Z", 5)
    assert [row["prediction_id"] for row in rows] == ["run_rest:4H"]
    assert repo.save_prediction_outcome(_sample_outcome()) == "OK"
    assert [request.url.path for request in seen] == [
        "/rest/v1/predictions",
        "/rest/v1/prediction_outcomes",
        "/rest/v1/prediction_outcomes",
    ]


def test_supabase_rest_watchlist_crud_uses_mocked_https() -> None:
    seen: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.path))
        if request.method == "GET":
            return httpx.Response(200, json=[{"display_symbol": "BTC/USDT"}])
        return httpx.Response(201 if request.method == "POST" else 204)

    repo = SupabaseRestRepository(
        "https://project.example.supabase.co",
        "test-service-role-key",
        client=rest_client(handler),
    )

    assert repo.add_watchlist("BTC/USDT") == "OK"
    assert repo.list_watchlist() == ["BTC/USDT"]
    assert repo.remove_watchlist("BTC/USDT") == "OK"
    assert seen == [
        ("POST", "/rest/v1/watchlist"),
        ("GET", "/rest/v1/watchlist"),
        ("DELETE", "/rest/v1/watchlist"),
    ]


def test_supabase_rest_failure_opens_circuit_and_uses_fallback() -> None:
    clock = FakeClock()
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(503, json={"message": "database unavailable"})

    repo = SupabaseRestRepository(
        "https://project.example.supabase.co",
        "test-service-role-key",
        client=rest_client(handler),
        circuit_cooldown_seconds=60.0,
        clock=clock,
    )

    assert repo.save_run(_sample_run_summary()) == "UNAVAILABLE"
    assert repo.persistence_status() == "UNAVAILABLE"
    assert repo.circuit_state() == "OPEN"
    assert attempts == 1

    assert repo.save_timeframe_result(_sample_timeframe_result()) == "UNAVAILABLE"
    assert attempts == 1
    assert repo.get_run("run_rest")["run_id"] == "run_rest"


def _sample_run_summary() -> dict:
    return {
        "run_id": "run_rest",
        "operator_id": "operator",
        "symbol": "BTC",
        "normalized_symbol": "BTC/USDT",
        "analysis_mode": "METRICS_ONLY",
        "asset_class": "CRYPTO_SPOT",
        "primary_timeframe": "4H",
        "disposition": "NO_TRADE",
        "total_score": 50.0,
        "data_source": "FIXTURE_DEMO",
        "is_live_data": False,
        "persistence_status": "OK",
        "analysis_hash": "hash",
        "as_of_utc": "2026-06-07T00:00:00Z",
    }


def _sample_timeframe_result() -> dict:
    return {
        "run_id": "run_rest",
        "timeframe": "4H",
        "disposition": "NO_TRADE",
        "total_score": 50.0,
        "prob_up_pct": 40.0,
        "prob_down_pct": 40.0,
        "prob_timeout_pct": 20.0,
        "gate_action": "NO_TRADE",
        "data_source": "FIXTURE_DEMO",
        "is_live_data": False,
    }


def _sample_provider_observation() -> dict:
    return {
        "run_id": "run_rest",
        "provider": "fixture",
        "provider_status": "OK",
        "active_provider": "fixture",
        "data_source": "FIXTURE_DEMO",
        "is_live_data": False,
        "warning_count": 0,
    }


def _sample_prediction() -> dict:
    return {
        "prediction_id": "run_rest:4H",
        "run_id": "run_rest",
        "operator_id": "operator",
        "symbol": "BTC",
        "normalized_symbol": "BTC/USDT",
        "timeframe": "4H",
        "horizon_bars": 6,
        "predicted_at_utc": "2026-06-07T00:00:00Z",
        "reference_close_utc": "2026-06-07T00:00:00Z",
        "reference_price": 100.0,
        "horizon_end_utc": "2026-06-08T00:00:00Z",
        "p_up_frac": 0.40,
        "p_down_frac": 0.35,
        "p_timeout_frac": 0.25,
        "decision_band_frac": 0.003,
        "model_version": "phase1a-wave4b0",
        "methodology_version": "heuristic-v1-wave4b0",
        "calibration_status": "DEFAULT_PHASE1A",
        "reliability_status": "INSUFFICIENT_SAMPLE",
        "epistemic_sufficiency": "SUFFICIENT",
        "gate_action": "WATCH",
        "data_source": "BINANCE_PUBLIC",
        "is_live_data": True,
        "cross_provider_state": "UNAVAILABLE",
    }


def _sample_prediction_db_row() -> tuple:
    row = _sample_prediction()
    return (
        row["prediction_id"],
        row["run_id"],
        row["operator_id"],
        row["symbol"],
        row["normalized_symbol"],
        row["timeframe"],
        row["horizon_bars"],
        row["predicted_at_utc"],
        row["reference_close_utc"],
        row["reference_price"],
        row["horizon_end_utc"],
        row["p_up_frac"],
        row["p_down_frac"],
        row["p_timeout_frac"],
        row["decision_band_frac"],
        row["model_version"],
        row["methodology_version"],
        row["calibration_status"],
        row["reliability_status"],
        row["epistemic_sufficiency"],
        row["gate_action"],
        row["data_source"],
        row["is_live_data"],
        row["cross_provider_state"],
    )


def _sample_outcome() -> dict:
    return {
        "prediction_id": "run_rest:4H",
        "resolved_at_utc": "2026-06-08T00:05:00Z",
        "outcome_close_utc": "2026-06-08T00:00:00Z",
        "outcome_reference_price": 101.0,
        "terminal_return_frac": 0.01,
        "realized_label": "UP",
        "decision_band_frac": 0.003,
        "max_favorable_frac": 0.015,
        "max_adverse_frac": -0.002,
        "candles_observed": 6,
        "resolver_version": "resolver-v1-wave4b2",
        "data_source": "BINANCE_PUBLIC",
        "is_live_data": True,
    }


def _sample_calibration_db_row() -> tuple:
    prediction = _sample_prediction()
    outcome = _sample_outcome()
    return (
        prediction["prediction_id"],
        prediction["run_id"],
        prediction["operator_id"],
        prediction["symbol"],
        prediction["normalized_symbol"],
        prediction["timeframe"],
        prediction["horizon_bars"],
        prediction["predicted_at_utc"],
        prediction["reference_close_utc"],
        prediction["reference_price"],
        prediction["horizon_end_utc"],
        prediction["p_up_frac"],
        prediction["p_down_frac"],
        prediction["p_timeout_frac"],
        prediction["decision_band_frac"],
        prediction["model_version"],
        prediction["methodology_version"],
        prediction["calibration_status"],
        prediction["reliability_status"],
        prediction["epistemic_sufficiency"],
        prediction["gate_action"],
        prediction["data_source"],
        prediction["is_live_data"],
        prediction["cross_provider_state"],
        outcome["resolved_at_utc"],
        outcome["outcome_close_utc"],
        outcome["outcome_reference_price"],
        outcome["terminal_return_frac"],
        outcome["realized_label"],
        outcome["max_favorable_frac"],
        outcome["max_adverse_frac"],
        outcome["candles_observed"],
        outcome["resolver_version"],
        outcome["data_source"],
        outcome["is_live_data"],
    )


def _sample_calibration_mapping_row() -> dict:
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
        "prediction_data_source",
        "prediction_is_live_data",
        "cross_provider_state",
        "resolved_at_utc",
        "outcome_close_utc",
        "outcome_reference_price",
        "terminal_return_frac",
        "realized_label",
        "max_favorable_frac",
        "max_adverse_frac",
        "candles_observed",
        "resolver_version",
        "outcome_data_source",
        "outcome_is_live_data",
    )
    return dict(zip(keys, _sample_calibration_db_row(), strict=True))


def _sample_news_item() -> dict:
    return {
        "item_id": "urlhash",
        "run_id": "run_rest",
        "normalized_symbol": "BTC/USDT",
        "provider": "gdelt",
        "source_name": "Example",
        "domain": "example.com",
        "title": "Bitcoin ETF metadata item",
        "snippet": "Metadata summary only.",
        "url": "https://example.com/news",
        "url_hash": "urlhash",
        "title_hash": "titlehash",
        "published_at": "2026-06-08T10:00:00Z",
        "fetched_at": "2026-06-08T12:00:00Z",
        "language": "en",
        "macro_or_micro": "MICRO",
        "event_class": "ASSET_SPECIFIC",
        "relevance_score": 0.8,
        "freshness_score": 1.0,
        "source_authority_score": 0.7,
        "confidence_score": 0.8,
        "cluster_id": "cluster_1",
    }


def _sample_news_cluster() -> dict:
    return {
        "cluster_id": "cluster_1",
        "run_id": "run_rest",
        "normalized_symbol": "BTC/USDT",
        "representative_title": "Bitcoin ETF metadata item",
        "macro_or_micro": "MICRO",
        "event_class": "ASSET_SPECIFIC",
        "source_count": 1,
        "item_count": 1,
        "dropped_count": 0,
        "max_relevance_score": 0.8,
    }


def _sample_news_link() -> dict:
    return {
        "run_id": "run_rest",
        "cluster_id": "cluster_1",
        "item_id": "urlhash",
        "evidence_type": "ADVISORY_NEWS_METADATA",
        "relevance_score": 0.8,
    }
