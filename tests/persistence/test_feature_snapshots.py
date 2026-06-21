from __future__ import annotations

import inspect
import json
from copy import deepcopy
from pathlib import Path

import httpx

from crypto_probability_engine.api.analysis_service import (
    PersistenceWork,
    _best_effort_persist,
    _prediction_row,
)
from crypto_probability_engine.persistence.feature_snapshot import (
    BLOCK_PAYLOAD_FIELDS,
    FEATURE_PAYLOAD_FIELDS,
    FeatureSnapshotWriteStatus,
    _snapshot_hash,
    build_feature_snapshot,
)
from crypto_probability_engine.persistence.repository import (
    InMemoryPersistenceRepository,
    SupabasePersistenceRepository,
    SupabaseRestRepository,
)
from crypto_probability_engine.quant.pipeline import run_quant_pipeline
from crypto_probability_engine.quant_v2.contract import build_quant_v2_shadow
from tests.fixtures.market_data import make_snapshot

ROOT = Path(__file__).resolve().parents[2]


def _evidence() -> tuple[dict, dict]:
    market_snapshot = make_snapshot(provider="binance")
    provider_state = {"status": "OK", "active_provider": "binance"}
    quant_result = run_quant_pipeline(market_snapshot, provider_state)
    prediction = _prediction_row(
        run_id="run_snapshot",
        request_symbol="BTC",
        normalized_symbol="BTC/USDT",
        timeframe="4H",
        snapshot=market_snapshot,
        quant_result=quant_result,
        data_quality={
            "is_live_data": True,
            "data_source": "BINANCE_PUBLIC",
            "cross_provider_state": "UNAVAILABLE",
        },
        provider_state=provider_state,
    )
    assert prediction is not None
    block = build_quant_v2_shadow(
        quant_result=quant_result,
        snapshot=market_snapshot,
        provider_state=provider_state,
        symbol="BTC",
        normalized_symbol="BTC/USDT",
        timeframe="4H",
    )
    return prediction, block


def _snapshot() -> dict:
    prediction, block = _evidence()
    row = build_feature_snapshot(prediction, block)
    assert row is not None
    return row


def _work(prediction: dict, snapshot: dict | None) -> PersistenceWork:
    return PersistenceWork(
        run_summary={"run_id": prediction["run_id"]},
        timeframe_result={"run_id": prediction["run_id"], "timeframe": "4H"},
        provider_observations=(),
        prediction_rows=(prediction,),
        feature_snapshot_rows=(snapshot,) if snapshot is not None else (),
        feature_snapshot_build_failed=snapshot is None,
    )


def test_projection_is_explicit_and_excludes_ui_future_and_sensitive_fields() -> None:
    prediction, block = _evidence()
    block = deepcopy(block)
    block["future_block_field"] = {"ignored": True}
    block["plain_english"] = "UI-only text must not persist."
    for feature in block["features"]:
        feature["future_feature_field"] = ["ignored"]
        feature["explanation_short"] = "UI-only short explanation."
        feature["explanation_detail"] = "UI-only detailed explanation."
    block["request_cookie"] = "not-persisted"
    block["access_token"] = "not-persisted"

    row = build_feature_snapshot(prediction, block)

    assert row is not None
    payload = row["snapshot_payload"]
    assert set(payload) == set(BLOCK_PAYLOAD_FIELDS)
    assert "plain_english" not in payload
    assert "future_block_field" not in payload
    assert "request_cookie" not in payload
    assert "access_token" not in payload
    for feature in payload["features"]:
        assert set(feature) == set(FEATURE_PAYLOAD_FIELDS)
        assert "explanation_short" not in feature
        assert "explanation_detail" not in feature
        assert "future_feature_field" not in feature
        assert "candles" not in feature


def test_snapshot_migration_is_additive_immutable_and_server_only() -> None:
    sql = (ROOT / "migrations" / "0005_prediction_feature_snapshots.sql").read_text()
    assert "CREATE TABLE IF NOT EXISTS public.prediction_feature_snapshots" in sql
    assert "REFERENCES public.predictions(prediction_id)" in sql
    assert "ON DELETE RESTRICT" in sql
    assert "CHECK (influence_mode = 'SHADOW_ONLY')" in sql
    assert "idx_pfs_methodology_timeframe_asof" in sql
    assert "idx_pfs_symbol_timeframe_asof" in sql
    assert "ENABLE ROW LEVEL SECURITY" in sql
    assert "FROM anon, authenticated" in sql
    assert "CREATE POLICY" not in sql
    assert "USING GIN" not in sql
    assert "ON CONFLICT" not in sql
    for statement in ("DROP TABLE", "DELETE FROM", "UPDATE public."):
        assert statement not in sql


def test_provider_signature_is_sorted_unique_and_has_unknown_fallback() -> None:
    prediction, block = _evidence()
    mixed = deepcopy(block)
    providers = ["okx", "BINANCE", "okx", None]
    for feature, provider in zip(mixed["features"], providers, strict=True):
        feature["source_provider"] = provider

    mixed_row = build_feature_snapshot(prediction, mixed)
    assert mixed_row is not None
    assert mixed_row["provider_signature"] == "BINANCE+OKX"

    unknown = deepcopy(block)
    for feature in unknown["features"]:
        feature["source_provider"] = None
    unknown_row = build_feature_snapshot(prediction, unknown)
    assert unknown_row is not None
    assert unknown_row["provider_signature"] == "UNKNOWN"


def test_full_envelope_hash_is_deterministic_and_covers_headers_and_payload() -> None:
    first = _snapshot()
    second = _snapshot()
    assert first == second
    assert len(first["snapshot_hash"]) == 64

    immutable_headers = (
        "prediction_id",
        "run_id",
        "symbol",
        "normalized_symbol",
        "timeframe",
        "prediction_as_of_utc",
        "reference_close_utc",
        "quant_v2_schema_version",
        "feature_methodology_version",
        "influence_mode",
        "no_lookahead_assertion",
        "block_status",
        "feature_count",
        "degraded_count",
        "provider_signature",
    )
    for key in immutable_headers:
        changed = deepcopy(first)
        value = changed[key]
        if isinstance(value, bool):
            changed[key] = not value
        elif isinstance(value, int):
            changed[key] = value + 1
        else:
            changed[key] = f"{value}-changed"
        assert _snapshot_hash(changed) != first["snapshot_hash"]

    changed_payload = deepcopy(first)
    changed_payload["snapshot_payload"]["features"][0]["raw_value"] = "changed"
    assert _snapshot_hash(changed_payload) != first["snapshot_hash"]

    with_created_at = {**first, "created_at": "2099-01-01T00:00:00Z"}
    assert _snapshot_hash(with_created_at) == first["snapshot_hash"]


def test_projection_rejects_nonfinite_malformed_and_inconsistent_evidence() -> None:
    prediction, block = _evidence()
    for invalid in (float("nan"), float("inf"), float("-inf")):
        malformed = deepcopy(block)
        malformed["features"][0]["raw_value"] = invalid
        assert build_feature_snapshot(prediction, malformed) is None

    malformed = deepcopy(block)
    malformed["features"][0]["raw_value"] = {"unexpected": "container"}
    assert build_feature_snapshot(prediction, malformed) is None

    inconsistent = deepcopy(block)
    inconsistent["degraded_count"] = 1
    assert build_feature_snapshot(prediction, inconsistent) is None

    non_shadow = deepcopy(block)
    non_shadow["influence_mode"] = "ACTIVE"
    assert build_feature_snapshot(prediction, non_shadow) is None


def test_builder_is_pure_and_does_not_change_identity_or_quant_evidence() -> None:
    prediction, block = _evidence()
    prediction_before = deepcopy(prediction)
    block_before = deepcopy(block)
    prediction_bytes = json.dumps(prediction, sort_keys=True, separators=(",", ":"))

    row = build_feature_snapshot(prediction, block)

    assert row is not None
    assert prediction == prediction_before
    assert block == block_before
    assert json.dumps(prediction, sort_keys=True, separators=(",", ":")) == prediction_bytes
    assert row["prediction_id"] == prediction["prediction_id"]
    assert "snapshot_hash" not in prediction
    assert "snapshot_hash" not in block


def test_in_memory_snapshot_storage_is_immutable_and_conflict_aware() -> None:
    repo = InMemoryPersistenceRepository()
    first = _snapshot()
    conflict = {**first, "snapshot_hash": "f" * 64}

    assert repo.save_feature_snapshot(first) == FeatureSnapshotWriteStatus.INSERTED
    assert (
        repo.save_feature_snapshot(deepcopy(first))
        == FeatureSnapshotWriteStatus.IDENTICAL_DUPLICATE
    )
    assert repo.save_feature_snapshot(conflict) == FeatureSnapshotWriteStatus.CONFLICT
    assert repo.get_feature_snapshot(first["prediction_id"]) == first

    first["snapshot_payload"]["features"][0]["raw_value"] = "mutated-after-save"
    fetched = repo.get_feature_snapshot(first["prediction_id"])
    assert fetched is not None
    assert fetched["snapshot_payload"]["features"][0]["raw_value"] != "mutated-after-save"
    fetched["snapshot_payload"]["features"][0]["raw_value"] = "mutated-read-copy"
    assert (
        repo.get_feature_snapshot(first["prediction_id"])["snapshot_payload"]["features"][0][
            "raw_value"
        ]
        != "mutated-read-copy"
    )


class _SnapshotCursor:
    def __init__(self) -> None:
        self.storage: dict[str, dict] = {}
        self.statements: list[str] = []
        self.prepared = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False

    def execute(self, statement, params=None) -> None:
        sql = str(statement)
        self.statements.append(sql)
        if "INSERT INTO public.prediction_feature_snapshots" in sql:
            incoming = dict(params)
            prediction_id = incoming["prediction_id"]
            if prediction_id in self.storage:
                self.prepared = None
            else:
                self.storage[prediction_id] = deepcopy(incoming)
                self.prepared = (incoming["snapshot_hash"],)
        elif "SELECT snapshot_hash" in sql:
            stored = self.storage.get(params["prediction_id"])
            self.prepared = (stored["snapshot_hash"],) if stored else None

    def fetchone(self):
        return self.prepared


class _SnapshotConnection:
    def __init__(self, cursor: _SnapshotCursor) -> None:
        self.cursor_value = cursor

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False

    def cursor(self) -> _SnapshotCursor:
        return self.cursor_value


class _SnapshotPool:
    def __init__(self, cursor: _SnapshotCursor) -> None:
        self.cursor_value = cursor

    def connection(self, timeout=None) -> _SnapshotConnection:
        return _SnapshotConnection(self.cursor_value)


def test_postgres_snapshot_write_detects_duplicate_and_conflict_without_update() -> None:
    cursor = _SnapshotCursor()
    repo = SupabasePersistenceRepository(
        "postgresql://example.invalid/db",
        pool_factory=lambda: _SnapshotPool(cursor),
    )
    first = _snapshot()
    conflict = {**first, "snapshot_hash": "f" * 64}

    assert repo.save_feature_snapshot(first) == FeatureSnapshotWriteStatus.INSERTED
    assert (
        repo.save_feature_snapshot(first)
        == FeatureSnapshotWriteStatus.IDENTICAL_DUPLICATE
    )
    assert repo.save_feature_snapshot(conflict) == FeatureSnapshotWriteStatus.CONFLICT

    statements = "\n".join(cursor.statements)
    assert "ON CONFLICT (prediction_id) DO NOTHING" in statements
    assert "RETURNING snapshot_hash" in statements
    assert statements.count("SELECT snapshot_hash") == 2
    assert "DO UPDATE" not in statements
    stored = cursor.storage[first["prediction_id"]]
    assert stored["snapshot_hash"] == first["snapshot_hash"]


def test_rest_snapshot_write_detects_duplicate_and_conflict_without_merge() -> None:
    storage: dict[str, dict] = {}
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "POST":
            incoming = json.loads(request.content)
            prediction_id = incoming["prediction_id"]
            if prediction_id in storage:
                return httpx.Response(200, json=[])
            storage[prediction_id] = deepcopy(incoming)
            return httpx.Response(
                201,
                json=[
                    {
                        "prediction_id": prediction_id,
                        "snapshot_hash": incoming["snapshot_hash"],
                    }
                ],
            )
        prediction_id = request.url.params["prediction_id"].removeprefix("eq.")
        stored = storage.get(prediction_id)
        return httpx.Response(
            200,
            json=(
                [
                    {
                        "prediction_id": prediction_id,
                        "snapshot_hash": stored["snapshot_hash"],
                    }
                ]
                if stored
                else []
            ),
        )

    repo = SupabaseRestRepository(
        "https://example.invalid",
        "test-key",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    first = _snapshot()
    conflict = {**first, "snapshot_hash": "f" * 64}

    assert repo.save_feature_snapshot(first) == FeatureSnapshotWriteStatus.INSERTED
    assert (
        repo.save_feature_snapshot(first)
        == FeatureSnapshotWriteStatus.IDENTICAL_DUPLICATE
    )
    assert repo.save_feature_snapshot(conflict) == FeatureSnapshotWriteStatus.CONFLICT
    assert storage[first["prediction_id"]]["snapshot_hash"] == first["snapshot_hash"]
    post_headers = [
        request.headers.get("prefer", "")
        for request in requests
        if request.method == "POST"
    ]
    assert all("resolution=ignore-duplicates" in value for value in post_headers)
    assert all("merge-duplicates" not in value for value in post_headers)


def test_persistence_handoff_requires_parent_and_reports_snapshot_failure() -> None:
    prediction, _ = _evidence()
    snapshot = _snapshot()

    inserted = InMemoryPersistenceRepository()
    assert _best_effort_persist(_work(prediction, snapshot), inserted) == "STATELESS"
    assert inserted.get_feature_snapshot(prediction["prediction_id"]) == snapshot

    existing_parent = InMemoryPersistenceRepository()
    existing_parent.save_prediction(prediction)
    assert _best_effort_persist(_work(prediction, snapshot), existing_parent) == "STATELESS"
    assert existing_parent.get_feature_snapshot(prediction["prediction_id"]) == snapshot

    class SnapshotUnavailable(InMemoryPersistenceRepository):
        def save_feature_snapshot(self, row):
            return FeatureSnapshotWriteStatus.UNAVAILABLE

    unavailable = SnapshotUnavailable()
    assert _best_effort_persist(_work(prediction, snapshot), unavailable) == "UNAVAILABLE"
    assert prediction["prediction_id"] in unavailable._predictions  # noqa: SLF001

    class ParentUnavailable(InMemoryPersistenceRepository):
        def __init__(self) -> None:
            super().__init__()
            self.snapshot_attempted = False

        def save_prediction(self, row):
            return "UNAVAILABLE"

        def save_feature_snapshot(self, row):
            self.snapshot_attempted = True
            return FeatureSnapshotWriteStatus.INSERTED

    parent_unavailable = ParentUnavailable()
    assert (
        _best_effort_persist(_work(prediction, snapshot), parent_unavailable)
        == "UNAVAILABLE"
    )
    assert parent_unavailable.snapshot_attempted is False


def test_snapshot_module_has_no_refetch_backfill_or_decision_dependency() -> None:
    import crypto_probability_engine.persistence.feature_snapshot as module

    source = inspect.getsource(module)
    for forbidden in (
        "public_market",
        "httpx",
        "requests",
        "run_quant_pipeline",
        "save_prediction_outcome",
        "resolve_outcomes",
        "calibration",
    ):
        assert forbidden not in source
