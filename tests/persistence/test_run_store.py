from __future__ import annotations

from crypto_probability_engine.persistence.run_store import InMemoryRunStore


def payload(run_id: str) -> dict:
    return {
        "run_id": run_id,
        "symbol": "BTC/USDT",
        "analysis_mode": "METRICS_ONLY",
        "as_of_utc": "2026-08-27T00:00:00Z",
        "analysis_hash": f"hash-{run_id}",
        "detail_view": {"run_id": run_id},
    }


def test_put_default_preserves_user_requested_behavior_without_mutating_payload() -> None:
    store = InMemoryRunStore()
    original = payload("default")
    expected = original.copy()

    store.put("default", original)

    assert store.get("default") is original
    assert original == expected
    assert store.list_runs()[0]["prediction_origin"] == "USER_REQUESTED"


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
    store.put("second", payload("second"))
    store.put("first", first, prediction_origin="SCHEDULED_SHADOW_EVIDENCE")
    store.put("third", payload("third"))

    assert list(store.runs) == ["first", "third"]
    assert store.get("second") is None
    assert [row["run_id"] for row in store.list_runs()] == ["third", "first"]
    assert store.list_runs()[1]["prediction_origin"] == "SCHEDULED_SHADOW_EVIDENCE"
