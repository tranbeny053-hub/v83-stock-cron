from contextlib import nullcontext

import pytest

from crypto_probability_engine.persistence.repository import (
    InMemoryPersistenceRepository,
    SupabasePersistenceRepository,
    SupabaseRestRepository,
    _execute_due_prediction_query,
    _fetch_due_prediction_rows,
)

NOW = "2026-06-08T00:05:00Z"
SOURCES = ("BINANCE_PUBLIC", "OKX_PUBLIC")
TIMEFRAMES = ("15m", "1D", "1H", "1W", "4H")


def _prediction(identifier, source="BINANCE_PUBLIC", timeframe="4H", **overrides):
    return {
        "prediction_id": identifier,
        "data_source": source,
        "timeframe": timeframe,
        "is_live_data": True,
        "horizon_end_utc": "2026-06-08T00:00:00Z",
        **overrides,
    }


def test_memory_exact_filters_and_unfiltered_compatibility():
    repo = InMemoryPersistenceRepository()
    sources = (*SOURCES, "CROSS_PROVIDER", "binance_public", " OKX_PUBLIC", None)
    timeframes = (*TIMEFRAMES, "1M", "2H", "1h", " 4H", None)
    rows = [
        _prediction(f"{i}-{j}", source, timeframe)
        for i, source in enumerate(sources)
        for j, timeframe in enumerate(timeframes)
    ]
    for row in rows:
        repo.save_prediction(row)
    assert [r["prediction_id"] for r in repo.fetch_due_unresolved_predictions(NOW, 1000)] == [
        r["prediction_id"] for r in rows
    ]
    for filters in (
        {"data_sources": SOURCES},
        {"timeframes": TIMEFRAMES},
        {"data_sources": SOURCES, "timeframes": TIMEFRAMES},
    ):
        expected = [
            row["prediction_id"] for row in rows
            if ("data_sources" not in filters or row["data_source"] in SOURCES)
            and ("timeframes" not in filters or row["timeframe"] in TIMEFRAMES)
        ]
        assert [
            row["prediction_id"]
            for row in repo.fetch_due_unresolved_predictions(NOW, 1000, **filters)
        ] == expected


def test_memory_filters_precede_order_and_limit():
    repo = InMemoryPersistenceRepository()
    repo.save_prediction(_prediction("exact"))
    for index in range(60):
        repo.save_prediction(_prediction(
            f"cross-{index}", "CROSS_PROVIDER", horizon_end_utc="2026-06-07T00:00:00Z"
        ))
    unfiltered = repo.fetch_due_unresolved_predictions(NOW, 50)
    assert len(unfiltered) == 50
    assert all(row["data_source"] == "CROSS_PROVIDER" for row in unfiltered)
    filtered = repo.fetch_due_unresolved_predictions(
        NOW, 50, data_sources=SOURCES, timeframes=TIMEFRAMES
    )
    assert [row["prediction_id"] for row in filtered] == ["exact"]


@pytest.fixture
def postgres():
    return SupabasePersistenceRepository("postgresql://resolver.example.invalid/db")


@pytest.fixture
def rest():
    repo = SupabaseRestRepository("https://resolver.example.invalid", "synthetic-test-key")
    yield repo
    repo.close()


@pytest.mark.parametrize("filters", [{"data_sources": ()}, {"timeframes": []}])
def test_empty_filters_never_query(monkeypatch, postgres, rest, filters):
    def unexpected(*args, **kwargs):
        pytest.fail("Empty eligibility filter issued a query")

    monkeypatch.setattr(postgres, "_direct_connection", unexpected)
    monkeypatch.setattr(postgres, "_run_db", unexpected)
    monkeypatch.setattr(rest, "_request", unexpected)
    monkeypatch.setattr(rest._fallback, "fetch_due_unresolved_predictions", unexpected)
    memory = InMemoryPersistenceRepository()
    memory.save_prediction(_prediction("exact"))
    for repo in (memory, postgres, rest):
        assert repo.fetch_due_unresolved_predictions(NOW, 50, **filters) == []


@pytest.fixture(params=["memory", "postgres", "rest"])
def no_query_repository(request, monkeypatch, postgres, rest):
    def unexpected(*args, **kwargs):
        pytest.fail("Invalid eligibility filter reached a query path")

    class NoQueryPredictions(dict):
        values = unexpected

    memory = InMemoryPersistenceRepository()
    monkeypatch.setattr(memory, "_predictions", NoQueryPredictions())
    monkeypatch.setattr(postgres, "_direct_connection", unexpected)
    monkeypatch.setattr(postgres, "_run_db", unexpected)
    monkeypatch.setattr(rest, "_run_rest", unexpected)
    monkeypatch.setattr(rest, "_request", unexpected)
    monkeypatch.setattr(rest, "_fetch_existing_outcome_ids", unexpected)
    monkeypatch.setattr(rest._fallback, "fetch_due_unresolved_predictions", unexpected)
    return {"memory": memory, "postgres": postgres, "rest": rest}[request.param]


@pytest.mark.parametrize("name,value", [
    ("data_sources", "BINANCE_PUBLIC"), ("timeframes", "4H"),
])
@pytest.mark.parametrize("other_filter", [None, ()])
def test_bare_string_filters_never_query(no_query_repository, name, value, other_filter):
    filters = {"data_sources": other_filter, "timeframes": other_filter, name: value}
    with pytest.raises(TypeError, match=f"{name} must be a collection of strings"):
        no_query_repository.fetch_due_unresolved_predictions(NOW, 50, **filters)


@pytest.mark.parametrize("name", ["data_sources", "timeframes"])
@pytest.mark.parametrize("value", [
    'BINANCE_PUBLIC","OKX_PUBLIC', "BINANCE_PUBLIC,OKX_PUBLIC", " OKX_PUBLIC",
    "OKX PUBLIC", "", 1, None, r"a\b", "(x)",
])
@pytest.mark.parametrize("other_filter", [None, ()])
def test_invalid_filter_values_never_query(no_query_repository, name, value, other_filter):
    filters = {"data_sources": other_filter, "timeframes": other_filter, name: (value,)}
    with pytest.raises(ValueError, match=f"{name} values must match"):
        no_query_repository.fetch_due_unresolved_predictions(NOW, 50, **filters)


class RecordingCursor:
    def __init__(self):
        self.calls = []

    def execute(self, sql, params=None):
        self.calls.append((sql, params))

    def fetchall(self):
        return []


def _assert_filtered_query(sql, params):
    source_clause = "AND p.data_source = ANY(%(data_sources)s)"
    timeframe_clause = "AND p.timeframe = ANY(%(timeframes)s)"
    assert (
        sql.index("AND p.horizon_end_utc") < sql.index(source_clause)
        < sql.index(timeframe_clause) < sql.index("ORDER BY") < sql.index("LIMIT")
    )
    assert params == {
        "now_utc": NOW, "limit": 50,
        "data_sources": list(SOURCES), "timeframes": list(TIMEFRAMES),
    }


def test_postgres_query_filters_and_unchanged_default_sql():
    cursor = RecordingCursor()
    _execute_due_prediction_query(cursor, NOW, 50, data_sources=SOURCES, timeframes=TIMEFRAMES)
    sql, params = cursor.calls[-1]
    _assert_filtered_query(sql, params)
    _execute_due_prediction_query(cursor, NOW, 50)
    default_sql, default_params = cursor.calls[-1]
    assert "ANY(" not in default_sql
    assert default_params == {"now_utc": NOW, "limit": 50}
    assert default_sql == sql.replace(
        "\n          AND p.data_source = ANY(%(data_sources)s)", ""
    ).replace("\n          AND p.timeframe = ANY(%(timeframes)s)", "")
    assert _fetch_due_prediction_rows(
        cursor, NOW, 50, data_sources=SOURCES, timeframes=TIMEFRAMES
    ) == []
    _assert_filtered_query(*cursor.calls[-1])


def test_postgres_public_method_forwards_filters(monkeypatch, postgres):
    cursor = RecordingCursor()

    class Connection:
        def cursor(self):
            return nullcontext(cursor)

    monkeypatch.setattr(postgres, "_direct_connection", lambda: nullcontext(Connection()))
    assert postgres.fetch_due_unresolved_predictions(
        NOW, 50, data_sources=SOURCES, timeframes=TIMEFRAMES
    ) == []
    assert len(cursor.calls) == 2  # Statement timeout, then the due query.
    _assert_filtered_query(*cursor.calls[-1])


def test_rest_filter_params_and_unchanged_defaults(monkeypatch, rest):
    calls = []

    def request(method, table, *, params):
        calls.append((method, table, params))
        return []

    monkeypatch.setattr(rest, "_request", request)
    assert rest.fetch_due_unresolved_predictions(
        NOW, 50, data_sources=SOURCES, timeframes=TIMEFRAMES
    ) == []
    assert len(calls) == 1
    method, table, params = calls[-1]
    assert (method, table) == ("GET", "predictions")
    assert params["data_source"] == 'in.("BINANCE_PUBLIC","OKX_PUBLIC")'
    assert params["timeframe"] == 'in.("15m","1D","1H","1W","4H")'
    assert rest.fetch_due_unresolved_predictions(NOW, 50) == []
    assert calls[-1][2] == {
        key: value for key, value in params.items() if key not in {"data_source", "timeframe"}
    }


def test_rest_unavailable_forwards_filters_to_fallback(monkeypatch, rest):
    calls = []
    expected = [_prediction("fallback")]

    def request(*args, **kwargs):
        raise RuntimeError("synthetic unavailable")

    def fallback(now_utc, limit, *, data_sources=None, timeframes=None):
        calls.append((now_utc, limit, data_sources, timeframes))
        return expected

    monkeypatch.setattr(rest, "_request", request)
    monkeypatch.setattr(rest._fallback, "fetch_due_unresolved_predictions", fallback)
    assert rest.fetch_due_unresolved_predictions(
        NOW, 50, data_sources=SOURCES, timeframes=TIMEFRAMES
    ) == expected
    assert calls == [(NOW, 50, SOURCES, TIMEFRAMES)]
    assert calls[0][2] is SOURCES
    assert calls[0][3] is TIMEFRAMES
