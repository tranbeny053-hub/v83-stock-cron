from __future__ import annotations

import inspect
import json
from copy import deepcopy
from datetime import timedelta
from pathlib import Path

import httpx
import pytest
from jsonschema import Draft202012Validator, FormatChecker, RefResolver
from jsonschema import ValidationError as JsonSchemaError

import crypto_probability_engine.api.analysis_service as analysis_service
from crypto_probability_engine.api.analysis_service import (
    PersistenceWork,
    _best_effort_persist,
    _prediction_row,
)
from crypto_probability_engine.derivatives_intel.block import (
    build_derivatives_intelligence,
)
from crypto_probability_engine.persistence.derivatives_snapshot import (
    COMPARABILITY_FIELDS,
    METRIC_FIELDS,
    PROVIDER_SUMMARY_FIELDS,
    SNAPSHOT_PAYLOAD_FIELDS,
    DerivativesSnapshotWriteStatus,
    build_derivatives_snapshot,
    snapshot_hash,
)
from crypto_probability_engine.persistence.feature_snapshot import build_feature_snapshot
from crypto_probability_engine.persistence.repository import (
    InMemoryPersistenceRepository,
    SupabasePersistenceRepository,
    SupabaseRestRepository,
)
from crypto_probability_engine.quant.pipeline import run_quant_pipeline
from crypto_probability_engine.quant_v2.contract import build_quant_v2_shadow
from tests.fixtures.market_data import make_snapshot

ROOT = Path(__file__).resolve().parents[2]


def _prediction_and_quant_v2() -> tuple[dict, dict]:
    market_snapshot = make_snapshot(provider="binance")
    provider_state = {"status": "OK", "active_provider": "binance"}
    quant_result = run_quant_pipeline(market_snapshot, provider_state)
    prediction = _prediction_row(
        run_id="run_derivatives_snapshot",
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
    quant_v2 = build_quant_v2_shadow(
        quant_result=quant_result,
        snapshot=market_snapshot,
        provider_state=provider_state,
        symbol="BTC",
        normalized_symbol="BTC/USDT",
        timeframe="4H",
    )
    return prediction, quant_v2


def _block(status: str = "UNAVAILABLE") -> dict:
    prediction, _ = _prediction_and_quant_v2()
    core = prediction["predicted_at_utc"]
    core_datetime = analysis_service._coerce_utc_datetime(
        analysis_service.datetime.fromisoformat(core.replace("Z", "+00:00"))
    )
    block = build_derivatives_intelligence(
        normalized_symbol=prediction["normalized_symbol"],
        core_prediction_as_of_utc=core_datetime,
        enabled=False,
    )
    block["observation_as_of_utc"] = (
        core_datetime + timedelta(seconds=2)
    ).isoformat().replace("+00:00", "Z")
    block["block_status"] = status
    provider_statuses = {
        "ACTIVE": ("AVAILABLE", "AVAILABLE"),
        "DEGRADED": ("AVAILABLE", "PROVIDER_UNAVAILABLE"),
        "UNAVAILABLE": ("PROVIDER_UNAVAILABLE", "PROVIDER_UNAVAILABLE"),
    }[status]
    block["provider_summary"] = []
    for provider, provider_status in zip(
        ("BINANCE_USDM", "OKX_SWAP"), provider_statuses, strict=True
    ):
        available = provider_status == "AVAILABLE"
        block["provider_summary"].append(
            {
                "provider": provider,
                "status": provider_status,
                "valid_metric_count": 1 if available else 0,
                "total_metric_count": 1 if available else 0,
                "reason": None if available else "Fixture provider evidence unavailable.",
            }
        )
    block["comparability"] = [
        {
            "semantic_class": semantic_class,
            "left_provider": "BINANCE_USDM",
            "right_provider": "OKX_SWAP",
            "comparable": False,
            "reason": "Provider-native evidence is not comparable in this fixture.",
        }
        for semantic_class in ("CURRENT_FUNDING", "CURRENT_OPEN_INTEREST")
    ]
    block["warnings"] = ["Fixture-only unavailable evidence."]
    return block


def _row(status: str = "UNAVAILABLE") -> dict:
    prediction, _ = _prediction_and_quant_v2()
    row = build_derivatives_snapshot(prediction, _block(status))
    assert row is not None
    return row


def _validator() -> Draft202012Validator:
    schema = json.loads((ROOT / "schemas" / "derivatives_snapshot.schema.json").read_text())
    metric_schema = json.loads(
        (ROOT / "schemas" / "derivatives_metric.schema.json").read_text()
    )
    resolver = RefResolver.from_schema(
        schema,
        store={
            "derivatives_metric.schema.json": metric_schema,
            metric_schema["$id"]: metric_schema,
        },
    )
    return Draft202012Validator(schema, resolver=resolver, format_checker=FormatChecker())


@pytest.mark.parametrize("status", ["ACTIVE", "DEGRADED", "UNAVAILABLE"])
def test_eligible_statuses_build_strict_schema_valid_rows(status: str) -> None:
    prediction, _ = _prediction_and_quant_v2()

    row = build_derivatives_snapshot(prediction, _block(status))

    assert row is not None
    assert row["block_status"] == status
    assert row["influence_mode"] == "SHADOW_ONLY"
    assert row["decision_influence_frac"] == 0.0
    _validator().validate(row)


def test_disabled_missing_identity_observation_and_invalid_governance_are_ineligible() -> None:
    prediction, _ = _prediction_and_quant_v2()
    disabled = build_derivatives_intelligence(
        normalized_symbol=prediction["normalized_symbol"],
        core_prediction_as_of_utc=analysis_service.datetime.fromisoformat(
            prediction["predicted_at_utc"].replace("Z", "+00:00")
        ),
        enabled=False,
    )
    assert build_derivatives_snapshot(prediction, disabled) is None

    for key in ("prediction_id", "run_id"):
        malformed_prediction = deepcopy(prediction)
        malformed_prediction[key] = ""
        assert build_derivatives_snapshot(malformed_prediction, _block()) is None

    missing_observation = _block()
    missing_observation["observation_as_of_utc"] = None
    assert build_derivatives_snapshot(prediction, missing_observation) is None

    for key, invalid in (
        ("influence_mode", "ACTIVE"),
        ("decision_influence_frac", 0.1),
    ):
        malformed_block = _block()
        malformed_block[key] = invalid
        assert build_derivatives_snapshot(prediction, malformed_block) is None


def test_identity_and_dual_timestamp_mismatches_fail_closed() -> None:
    prediction, _ = _prediction_and_quant_v2()
    block = _block()

    mismatch = deepcopy(block)
    mismatch["normalized_symbol"] = "ETH/USDT"
    assert build_derivatives_snapshot(prediction, mismatch) is None

    core_mismatch = deepcopy(block)
    core_mismatch["core_prediction_as_of_utc"] = core_mismatch[
        "observation_as_of_utc"
    ]
    assert build_derivatives_snapshot(prediction, core_mismatch) is None

    reversed_times = deepcopy(block)
    reversed_times["observation_as_of_utc"] = "2020-01-01T00:00:00Z"
    assert build_derivatives_snapshot(prediction, reversed_times) is None

    row = build_derivatives_snapshot(prediction, block)
    assert row is not None
    assert row["core_prediction_as_of_utc"] == prediction["predicted_at_utc"]
    assert row["observation_as_of_utc"] != row["core_prediction_as_of_utc"]
    assert (
        row["snapshot_payload"]["core_prediction_as_of_utc"]
        == row["core_prediction_as_of_utc"]
    )
    assert (
        row["snapshot_payload"]["observation_as_of_utc"]
        == row["observation_as_of_utc"]
    )


def test_projection_is_explicit_and_excludes_presentation_and_future_fields() -> None:
    prediction, _ = _prediction_and_quant_v2()
    block = _block()
    block["future_block_field"] = {"excluded": True}
    block["raw_provider_envelope"] = {"excluded": True}
    block["credential_hint"] = "excluded"
    block["plain_english"] = "Presentation-only text."
    for summary in block["provider_summary"]:
        summary["future_provider_field"] = "excluded"
    for comparison in block["comparability"]:
        comparison["future_comparison_field"] = "excluded"

    row = build_derivatives_snapshot(prediction, block)

    assert row is not None
    payload = row["snapshot_payload"]
    assert set(payload) == set(SNAPSHOT_PAYLOAD_FIELDS)
    assert "plain_english" not in payload
    assert "raw_provider_envelope" not in payload
    assert "credential_hint" not in payload
    for summary in payload["provider_summary"]:
        assert set(summary) == set(PROVIDER_SUMMARY_FIELDS)
    for comparison in payload["comparability"]:
        assert set(comparison) == set(COMPARABILITY_FIELDS)


def test_metric_projection_is_allowlisted_when_metric_evidence_is_present() -> None:
    prediction, _ = _prediction_and_quant_v2()
    block = _block("DEGRADED")
    observation = block["observation_as_of_utc"]
    metric = {
        "metric_id": "binance.funding.current_estimate",
        "family": "FUNDING",
        "provider": "BINANCE_USDM",
        "provider_endpoint": "/fapi/v1/premiumIndex",
        "provider_instrument": "BTCUSDT",
        "normalized_symbol": "BTC/USDT",
        "contract_type": "USDT_LINEAR_PERPETUAL",
        "margin_asset": "USDT",
        "settlement_asset": "USDT",
        "timeframe_or_period": None,
        "event_time": observation,
        "interval_start": None,
        "interval_end": None,
        "interval_final": True,
        "fetched_at_utc": observation,
        "prediction_as_of_utc": observation,
        "input_staleness_seconds": 0.0,
        "status": "VALID",
        "reason_if_invalid": None,
        "raw_value": -0.0001,
        "normalized_value": None,
        "bucket": None,
        "direction_hint": None,
        "confidence_hint": None,
        "risk_hint": None,
        "unit": "FRACTION_PER_INTERVAL",
        "source_count": 1,
        "provider_priority": 1,
        "influence_mode": "SHADOW_ONLY",
        "methodology_version": "deriv-intel-shadow-v0",
        "no_lookahead_assertion": True,
        "future_metric_field": "excluded",
    }
    block["metrics"] = [metric]

    row = build_derivatives_snapshot(prediction, block)

    assert row is not None
    assert set(row["snapshot_payload"]["metrics"][0]) == set(METRIC_FIELDS)
    assert "future_metric_field" not in row["snapshot_payload"]["metrics"][0]
    _validator().validate(row)


def test_hash_is_order_independent_full_envelope_and_rejects_nonfinite_values() -> None:
    first = _row()
    reordered = dict(reversed(list(first.items())))
    reordered["snapshot_payload"] = dict(
        reversed(list(first["snapshot_payload"].items()))
    )
    assert snapshot_hash(first) == snapshot_hash(reordered) == first["snapshot_hash"]
    assert len(first["snapshot_hash"]) == 64
    assert first["snapshot_hash"] == first["snapshot_hash"].lower()

    for key in (
        "prediction_id",
        "run_id",
        "normalized_symbol",
        "derivatives_schema_version",
        "derivatives_methodology_version",
        "block_status",
        "core_prediction_as_of_utc",
        "observation_as_of_utc",
    ):
        changed = deepcopy(first)
        changed[key] = f"{changed[key]}-changed"
        assert snapshot_hash(changed) != first["snapshot_hash"]

    changed_payload = deepcopy(first)
    changed_payload["snapshot_payload"]["warnings"] = ["Changed evidence warning."]
    assert snapshot_hash(changed_payload) != first["snapshot_hash"]

    prediction, _ = _prediction_and_quant_v2()
    for invalid in (float("nan"), float("inf"), float("-inf")):
        block = _block("DEGRADED")
        block["decision_influence_frac"] = invalid
        assert build_derivatives_snapshot(prediction, block) is None


def test_snapshot_schema_rejects_missing_extra_presentation_and_invalid_contracts() -> None:
    validator = _validator()
    row = _row()
    validator.validate(row)

    mutations = []
    missing = deepcopy(row)
    missing.pop("run_id")
    mutations.append(missing)
    extra = deepcopy(row)
    extra["unexpected"] = True
    mutations.append(extra)
    presentation = deepcopy(row)
    presentation["snapshot_payload"]["plain_english"] = "Not persistence evidence."
    mutations.append(presentation)
    wrong_status = deepcopy(row)
    wrong_status["block_status"] = "DISABLED"
    mutations.append(wrong_status)
    wrong_mode = deepcopy(row)
    wrong_mode["influence_mode"] = "ACTIVE"
    mutations.append(wrong_mode)
    malformed_time = deepcopy(row)
    malformed_time["observation_as_of_utc"] = "not-a-timestamp"
    mutations.append(malformed_time)

    for mutation in mutations:
        with pytest.raises(JsonSchemaError):
            validator.validate(mutation)


def test_in_memory_repository_is_first_write_wins_and_copy_isolated() -> None:
    repository = InMemoryPersistenceRepository()
    first = _row()
    conflict = {**first, "snapshot_hash": "f" * 64}

    assert (
        repository.save_derivatives_snapshot(first)
        == DerivativesSnapshotWriteStatus.INSERTED
    )
    assert (
        repository.save_derivatives_snapshot(deepcopy(first))
        == DerivativesSnapshotWriteStatus.IDENTICAL_DUPLICATE
    )
    assert (
        repository.save_derivatives_snapshot(conflict)
        == DerivativesSnapshotWriteStatus.CONFLICT
    )
    assert repository.get_derivatives_snapshot(first["prediction_id"]) == first

    first["snapshot_payload"]["warnings"] = ["Changed after save."]
    fetched = repository.get_derivatives_snapshot(first["prediction_id"])
    assert fetched is not None
    assert fetched["snapshot_payload"]["warnings"] != ["Changed after save."]


class _DerivativesCursor:
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
        if "INSERT INTO public.prediction_derivatives_snapshots" in sql:
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


class _DerivativesConnection:
    def __init__(self, cursor: _DerivativesCursor) -> None:
        self.cursor_value = cursor

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False

    def cursor(self) -> _DerivativesCursor:
        return self.cursor_value


class _DerivativesPool:
    def __init__(self, cursor: _DerivativesCursor) -> None:
        self.cursor_value = cursor

    def connection(self, timeout=None) -> _DerivativesConnection:
        return _DerivativesConnection(self.cursor_value)


def test_postgres_repository_classifies_duplicates_without_overwrite() -> None:
    cursor = _DerivativesCursor()
    repository = SupabasePersistenceRepository(
        "postgresql://example.invalid/db",
        pool_factory=lambda: _DerivativesPool(cursor),
    )
    first = _row()
    conflict = {**first, "snapshot_hash": "f" * 64}

    assert (
        repository.save_derivatives_snapshot(first)
        == DerivativesSnapshotWriteStatus.INSERTED
    )
    assert (
        repository.save_derivatives_snapshot(first)
        == DerivativesSnapshotWriteStatus.IDENTICAL_DUPLICATE
    )
    assert (
        repository.save_derivatives_snapshot(conflict)
        == DerivativesSnapshotWriteStatus.CONFLICT
    )
    statements = "\n".join(cursor.statements)
    assert "ON CONFLICT (prediction_id) DO NOTHING" in statements
    assert "RETURNING snapshot_hash" in statements
    assert statements.count("SELECT snapshot_hash") == 2
    assert "DO UPDATE" not in statements
    assert cursor.storage[first["prediction_id"]]["snapshot_hash"] == first[
        "snapshot_hash"
    ]


def test_rest_repository_classifies_duplicates_without_merge_or_overwrite() -> None:
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
            return httpx.Response(201, json=[incoming])
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

    repository = SupabaseRestRepository(
        "https://example.invalid",
        "fixture-key",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    first = _row()
    conflict = {**first, "snapshot_hash": "f" * 64}

    assert (
        repository.save_derivatives_snapshot(first)
        == DerivativesSnapshotWriteStatus.INSERTED
    )
    assert (
        repository.save_derivatives_snapshot(first)
        == DerivativesSnapshotWriteStatus.IDENTICAL_DUPLICATE
    )
    assert (
        repository.save_derivatives_snapshot(conflict)
        == DerivativesSnapshotWriteStatus.CONFLICT
    )
    assert storage[first["prediction_id"]]["snapshot_hash"] == first[
        "snapshot_hash"
    ]
    post_headers = [
        request.headers.get("prefer", "")
        for request in requests
        if request.method == "POST"
    ]
    assert all("resolution=ignore-duplicates" in value for value in post_headers)
    assert all("merge-duplicates" not in value for value in post_headers)


def _work(
    prediction: dict,
    feature_snapshot: dict,
    derivatives_snapshot: dict | None,
    *,
    derivatives_build_failed: bool = False,
) -> PersistenceWork:
    return PersistenceWork(
        run_summary={"run_id": prediction["run_id"]},
        timeframe_result={"run_id": prediction["run_id"], "timeframe": "4H"},
        provider_observations=(),
        prediction_rows=(prediction,),
        feature_snapshot_rows=(feature_snapshot,),
        derivatives_snapshot_rows=(derivatives_snapshot,)
        if derivatives_snapshot is not None
        else (),
        derivatives_snapshot_build_failed=derivatives_build_failed,
    )


def test_persistence_gate_requires_parent_and_contains_snapshot_failure() -> None:
    prediction, quant_v2 = _prediction_and_quant_v2()
    feature_snapshot = build_feature_snapshot(prediction, quant_v2)
    derivatives_snapshot = build_derivatives_snapshot(prediction, _block())
    assert feature_snapshot is not None and derivatives_snapshot is not None

    inserted = InMemoryPersistenceRepository()
    assert (
        _best_effort_persist(
            _work(prediction, feature_snapshot, derivatives_snapshot), inserted
        )
        == "STATELESS"
    )
    assert inserted.get_derivatives_snapshot(prediction["prediction_id"]) is not None

    existing_parent = InMemoryPersistenceRepository()
    existing_parent.save_prediction(prediction)
    assert (
        _best_effort_persist(
            _work(prediction, feature_snapshot, derivatives_snapshot), existing_parent
        )
        == "STATELESS"
    )
    assert existing_parent.get_derivatives_snapshot(prediction["prediction_id"]) is not None

    class ParentUnavailable(InMemoryPersistenceRepository):
        def __init__(self) -> None:
            super().__init__()
            self.derivatives_attempted = False

        def save_prediction(self, row):
            return "UNAVAILABLE"

        def save_derivatives_snapshot(self, row):
            self.derivatives_attempted = True
            return DerivativesSnapshotWriteStatus.INSERTED

    unavailable_parent = ParentUnavailable()
    assert (
        _best_effort_persist(
            _work(prediction, feature_snapshot, derivatives_snapshot),
            unavailable_parent,
        )
        == "UNAVAILABLE"
    )
    assert unavailable_parent.derivatives_attempted is False

    class ParentConflict(ParentUnavailable):
        def save_prediction(self, row):
            return "CONFLICT"

    conflicting_parent = ParentConflict()
    assert (
        _best_effort_persist(
            _work(prediction, feature_snapshot, derivatives_snapshot),
            conflicting_parent,
        )
        == "UNAVAILABLE"
    )
    assert conflicting_parent.derivatives_attempted is False

    class DerivativesUnavailable(InMemoryPersistenceRepository):
        def save_derivatives_snapshot(self, row):
            return DerivativesSnapshotWriteStatus.UNAVAILABLE

    unavailable_snapshot = DerivativesUnavailable()
    assert (
        _best_effort_persist(
            _work(prediction, feature_snapshot, derivatives_snapshot),
            unavailable_snapshot,
        )
        == "UNAVAILABLE"
    )
    assert prediction["prediction_id"] in unavailable_snapshot._predictions  # noqa: SLF001

    class DerivativesRaises(InMemoryPersistenceRepository):
        def save_derivatives_snapshot(self, row):
            raise RuntimeError("fixture derivatives snapshot write failure")

    assert (
        _best_effort_persist(
            _work(prediction, feature_snapshot, derivatives_snapshot),
            DerivativesRaises(),
        )
        == "UNAVAILABLE"
    )

    disabled = InMemoryPersistenceRepository()
    assert _best_effort_persist(_work(prediction, feature_snapshot, None), disabled) == (
        "STATELESS"
    )
    assert disabled.get_derivatives_snapshot(prediction["prediction_id"]) is None


def test_builder_is_pure_and_preserves_prediction_response_quant_and_feature_snapshot() -> None:
    prediction, quant_v2 = _prediction_and_quant_v2()
    block = _block()
    prediction_before = deepcopy(prediction)
    quant_before = deepcopy(quant_v2)
    block_before = deepcopy(block)
    feature_before = build_feature_snapshot(prediction, quant_v2)

    row = build_derivatives_snapshot(prediction, block)

    assert row is not None
    assert prediction == prediction_before
    assert quant_v2 == quant_before
    assert block == block_before
    assert build_feature_snapshot(prediction, quant_v2) == feature_before
    assert row["prediction_id"] == prediction["prediction_id"]


def test_migration_has_fail_closed_consistency_rls_grants_and_mutation_guards() -> None:
    sql = (ROOT / "migrations" / "0006_prediction_derivatives_snapshots.sql").read_text()
    assert "CREATE TABLE IF NOT EXISTS public.prediction_derivatives_snapshots" in sql
    assert "prediction_id TEXT PRIMARY KEY" in sql
    assert "REFERENCES public.predictions(prediction_id)" in sql
    assert "ON DELETE RESTRICT" in sql
    assert "CHECK (influence_mode = 'SHADOW_ONLY')" in sql
    assert "CHECK (decision_influence_frac = 0)" in sql
    assert "'ACTIVE', 'DEGRADED', 'UNAVAILABLE'" in sql
    assert "observation_as_of_utc >= core_prediction_as_of_utc" in sql
    assert "snapshot_hash ~ '^[0-9a-f]{64}$'" in sql
    for key in SNAPSHOT_PAYLOAD_FIELDS:
        assert f"'{key}'" in sql
    for column in (
        "derivatives_schema_version",
        "derivatives_methodology_version",
        "influence_mode",
        "decision_influence_frac",
        "normalized_symbol",
        "block_status",
        "core_prediction_as_of_utc",
        "observation_as_of_utc",
    ):
        assert f"= {column}" in sql
    assert "idx_pds_methodology_symbol_observation" in sql
    assert "ENABLE ROW LEVEL SECURITY" in sql
    assert "CREATE POLICY" not in sql
    assert "FROM PUBLIC, anon, authenticated, service_role" in sql
    assert "GRANT SELECT, INSERT" in sql
    assert "TO service_role" in sql
    assert "BEFORE UPDATE" in sql
    assert "BEFORE DELETE" in sql
    assert "BEFORE TRUNCATE" in sql
    assert "FOR EACH STATEMENT" in sql
    assert "INSERT INTO" not in sql
    assert "backfill" not in sql.lower()


def test_snapshot_module_has_no_runtime_provider_or_decision_dependency() -> None:
    import crypto_probability_engine.persistence.derivatives_snapshot as module

    source = inspect.getsource(module)
    for forbidden in (
        "public_market",
        "httpx",
        "requests",
        "run_quant_pipeline",
        "build_derivatives_intelligence",
        "save_prediction_outcome",
        "resolve_outcomes",
        "calibration",
    ):
        assert forbidden not in source


def test_resolver_calibration_and_shadow_validation_do_not_reference_snapshot_table() -> None:
    paths = [ROOT / "scripts" / "resolve_outcomes.py"]
    paths.extend((ROOT / "src" / "crypto_probability_engine" / "calibration").rglob("*.py"))
    paths.extend(
        (ROOT / "src" / "crypto_probability_engine" / "shadow_validation").rglob("*.py")
    )
    for path in paths:
        assert "prediction_derivatives_snapshots" not in path.read_text()
