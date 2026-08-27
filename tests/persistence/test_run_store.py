from __future__ import annotations

from collections import OrderedDict

import pytest

from crypto_probability_engine.persistence.prediction_origin import (
    ALLOWED_PREDICTION_ORIGINS,
    validate_prediction_origin,
)
from crypto_probability_engine.persistence.run_store import (
    UNCLASSIFIED_RUN_ORIGIN,
    InMemoryRunStore,
)


def payload(run_id: str) -> dict:
    return {
        "run_id": run_id,
        "symbol": "BTC/USDT",
        "analysis_mode": "METRICS_ONLY",
        "as_of_utc": "2026-08-27T00:00:00Z",
        "analysis_hash": f"hash-{run_id}",
        "detail_view": {"run_id": run_id},
    }


def test_put_requires_explicit_origin_without_mutating_payload() -> None:
    store = InMemoryRunStore()
    original = payload("default")
    expected = original.copy()

    with pytest.raises(TypeError):
        store.put("default", original)  # type: ignore[call-arg]

    store.put("default", original, prediction_origin="USER_REQUESTED")

    assert store.get("default") is original
    assert original == expected
    assert store.list_runs()[0]["prediction_origin"] == "USER_REQUESTED"


def test_constructor_runs_without_recorded_origin_are_unclassified() -> None:
    store = InMemoryRunStore(runs=OrderedDict([("legacy", payload("legacy"))]))

    assert store.list_runs()[0]["prediction_origin"] == UNCLASSIFIED_RUN_ORIGIN


def test_list_runs_projects_context_without_mutating_payload() -> None:
    store = InMemoryRunStore()
    original = {
        **payload("context"),
        "timeframes": {"primary": "4H"},
        "data_quality": {"data_source": "exchange_feed", "is_live_data": True},
    }
    expected = original.copy()
    store.put("context", original, prediction_origin="USER_REQUESTED")

    assert store.list_runs()[0] == {
        "run_id": "context",
        "symbol": "BTC/USDT",
        "analysis_mode": "METRICS_ONLY",
        "as_of_utc": "2026-08-27T00:00:00Z",
        "analysis_hash": "hash-context",
        "prediction_origin": "USER_REQUESTED",
        "primary_timeframe": "4H",
        "data_source": "exchange_feed",
        "is_live_data": True,
    }
    assert original == expected


def test_list_runs_missing_context_is_none_and_existing_fallback_is_unchanged() -> None:
    store = InMemoryRunStore(runs=OrderedDict([("legacy", payload("legacy"))]))

    assert store.list_runs()[0] == {
        "run_id": "legacy",
        "symbol": "BTC/USDT",
        "analysis_mode": "METRICS_ONLY",
        "as_of_utc": "2026-08-27T00:00:00Z",
        "analysis_hash": "hash-legacy",
        "prediction_origin": UNCLASSIFIED_RUN_ORIGIN,
        "primary_timeframe": None,
        "data_source": None,
        "is_live_data": None,
    }


def test_unclassified_origin_is_not_persistable() -> None:
    assert UNCLASSIFIED_RUN_ORIGIN not in ALLOWED_PREDICTION_ORIGINS
    with pytest.raises(ValueError, match="Unsupported prediction origin"):
        validate_prediction_origin(UNCLASSIFIED_RUN_ORIGIN)


def test_list_runs_reports_each_recorded_origin() -> None:
    store = InMemoryRunStore()
    store.put("user", payload("user"), prediction_origin="USER_REQUESTED")
    store.put("smoke", payload("smoke"), prediction_origin="CONTROLLED_SMOKE")
    store.put(
        "scheduled",
        payload("scheduled"),
        prediction_origin="SCHEDULED_SHADOW_EVIDENCE",
    )

    assert [(row["run_id"], row["prediction_origin"]) for row in store.list_runs()] == [
        ("scheduled", "SCHEDULED_SHADOW_EVIDENCE"),
        ("smoke", "CONTROLLED_SMOKE"),
        ("user", "USER_REQUESTED"),
    ]


def test_retention_and_refresh_order_are_unchanged() -> None:
    store = InMemoryRunStore(limit=2)
    first = payload("first")
    store.put("first", first, prediction_origin="CONTROLLED_SMOKE")
    store.put("second", payload("second"), prediction_origin="USER_REQUESTED")
    store.put("first", first, prediction_origin="SCHEDULED_SHADOW_EVIDENCE")
    store.put("third", payload("third"), prediction_origin="USER_REQUESTED")

    assert list(store.runs) == ["first", "third"]
    assert store.get("second") is None
    assert "second" not in store._prediction_origins  # noqa: SLF001
    assert [row["run_id"] for row in store.list_runs()] == ["third", "first"]
    assert store.list_runs()[1]["prediction_origin"] == "SCHEDULED_SHADOW_EVIDENCE"
