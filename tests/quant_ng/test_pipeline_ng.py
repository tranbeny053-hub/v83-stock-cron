"""Parity coverage for the dormant NG1 wrapper.

Frozen fixture generation (run once at the M51 base, never in CI):
```sh
UCPE_GENERATE_NG_PARITY=1 .venv/bin/python -m pytest -q \\
  tests/quant_ng/test_pipeline_ng.py::test_generate_frozen_legacy_parity
```
The explicit environment flag is required; the normal test suite never writes the fixture.
"""

from __future__ import annotations

import copy
import json
import os
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest

from crypto_probability_engine.adapters.types import MarketSnapshot
from crypto_probability_engine.config.defaults import (
    DEFAULT_METHODOLOGY_VERSION,
    DISTRIBUTIONAL_METHODOLOGY_VERSION,
    TIMEFRAME_SECONDS,
)
from crypto_probability_engine.quant.pipeline import run_quant_pipeline
from crypto_probability_engine.quant.probability_distributional import FROZEN_B3_PARAMETERS
from crypto_probability_engine.quant_ng.pipeline_ng import run_pipeline_ng
from crypto_probability_engine.quant_ng.registry import (
    SLOT_POLICY,
    Refusal,
    ServingState,
    serving_state,
    validate_registry,
)
from tests.fixtures.market_data import (
    make_candles,
    make_downtrend_snapshot,
    make_high_volatility_snapshot,
    make_snapshot,
)

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests/quant_ng/fixtures/legacy_parity_v1.json"
PROVIDERS = ({"status": "OK"}, {"status": "DEGRADED"}, {"status": "FAILED"})
METHODS = (DEFAULT_METHODOLOGY_VERSION, DISTRIBUTIONAL_METHODOLOGY_VERSION)
NOW = datetime(2026, 11, 3, tzinfo=UTC)
EXPECTED_NG = {
    "schema": "quant-ng-serving.v1",
    "serving_state": {
        "tier": "HEURISTIC",
        "reference": "HIDDEN",
        "status": "SHADOW",
        "slot_policy": SLOT_POLICY,
        "reason": "OD-NG-4 KEEP_HOLD: the heuristic stays authoritative; the reference is hidden",
    },
    "reference_state": "HIDDEN",
    "evidence_status": "NONE",
    "slot_policy": SLOT_POLICY,
    "policy_id": None,
}
EXPECTED_NG_NONE = {
    **EXPECTED_NG,
    "serving_state": {**EXPECTED_NG["serving_state"], "status": "NONE"},
}


def _snapshots() -> list[tuple[str, MarketSnapshot]]:
    out = [(f"make_snapshot_{tf}", make_snapshot(timeframe=tf)) for tf in TIMEFRAME_SECONDS]
    out.extend(
        (
            ("make_downtrend_snapshot", make_downtrend_snapshot()),
            ("make_high_volatility_snapshot", make_high_volatility_snapshot()),
        )
    )
    short = make_snapshot()
    void = MarketSnapshot(
        provider=short.provider,
        normalized_symbol=short.normalized_symbol,
        timeframe=short.timeframe,
        candles=make_candles(count=10),
        order_book=short.order_book,
        as_of_utc=short.as_of_utc,
        source_status=short.source_status,
    )
    out.append(("epistemic_void", void))
    return out


def _cases():
    for snap_id, snapshot in _snapshots():
        for provider in PROVIDERS:
            methods = METHODS if snapshot.timeframe in FROZEN_B3_PARAMETERS else (METHODS[0],)
            for method in methods:
                yield (
                    f"{snap_id}__{provider['status'].lower()}__{method}",
                    snapshot,
                    provider,
                    method,
                )


def _cell(snapshot: MarketSnapshot, method: str = DEFAULT_METHODOLOGY_VERSION) -> dict:
    return {
        "symbol": snapshot.normalized_symbol,
        "venue": "BINANCE_PUBLIC",
        "timeframe": snapshot.timeframe,
        "horizon": 6,
        "target_version": "fixture-target-v1",
        "methodology_version": method,
    }


def _entry(cell: dict, **updates) -> dict:
    entry = {
        "cell": cell,
        "recipe_id": "recipe-fixture",
        "artifact_id": "artifact-fixture",
        "status": "SHADOW",
        "claims": [],
        "authorization_ref": None,
        "cohort_key": "recipe-fixture",
        "policy_id": None,
    }
    entry.update(updates)
    return entry


def _registry(*entries: dict, slot_policy: str = SLOT_POLICY) -> dict:
    return {"schema": "quant-ng-registry.v1", "slot_policy": slot_policy, "cells": list(entries)}


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()


def _frozen_rows() -> list[dict]:
    rows = []
    for case_id, snapshot, provider, method in _cases():
        result = run_quant_pipeline(snapshot, dict(provider), methodology_version=method)
        rows.append(
            {
                "id": case_id,
                "analysis_hash": result["analysis_hash"],
                "probability_state": {
                    horizon: {
                        key: data[key] for key in ("p_up_frac", "p_down_frac", "p_timeout_frac")
                    }
                    for horizon, data in result["probability_state"].get("horizons", {}).items()
                },
                "gate_result": {
                    key: result["gate_result"].get(key)
                    for key in ("action", "disposition", "final_action", "final_disposition")
                    if key in result["gate_result"]
                },
            }
        )
    return rows


def test_generate_frozen_legacy_parity() -> None:
    """Generate only with UCPE_GENERATE_NG_PARITY=1; normal CI must not write files."""
    if os.environ.get("UCPE_GENERATE_NG_PARITY") != "1":
        return
    FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    FIXTURE.write_text(
        json.dumps(_frozen_rows(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def test_legacy_frozen_parity_and_ng_whole_result_identity() -> None:
    frozen = {row["id"]: row for row in json.loads(FIXTURE.read_text(encoding="utf-8"))}
    assert len(frozen) == 45
    saw_nonempty_legacy_gate = False
    for case_id, snapshot, provider, method in _cases():
        legacy = run_quant_pipeline(snapshot, dict(provider), methodology_version=method)
        row = frozen[case_id]
        assert row["analysis_hash"] == legacy["analysis_hash"], case_id
        expected_probability = {
            horizon: {key: data[key] for key in ("p_up_frac", "p_down_frac", "p_timeout_frac")}
            for horizon, data in legacy["probability_state"].get("horizons", {}).items()
        }
        assert row["probability_state"] == expected_probability, case_id
        expected_gate = {
            key: legacy["gate_result"].get(key)
            for key in ("action", "disposition", "final_action", "final_disposition")
            if key in legacy["gate_result"]
        }
        assert row["gate_result"] == expected_gate, case_id
        saw_nonempty_legacy_gate = saw_nonempty_legacy_gate or bool(legacy["gate_result"])
        no_registry_cell = snapshot.timeframe == "1M"
        if no_registry_cell:
            continue
        ng = run_pipeline_ng(
            snapshot,
            dict(provider),
            registry=_registry(_entry(_cell(snapshot, method))),
            cell=_cell(snapshot, method),
            now=NOW,
            methodology_version=method,
        )
        assert ng["result"] == legacy, case_id
        assert _canonical(ng["result"]) == _canonical(legacy), case_id
        assert ng == {"result": legacy, "ng": EXPECTED_NG}, case_id
        for horizon in legacy["probability_state"].get("horizons", {}).values():
            assert horizon["p_up_frac"] + horizon["p_down_frac"] + horizon["p_timeout_frac"] == 1.0
        assert _timestamp_values(ng["result"]) == _timestamp_values(legacy)
    assert saw_nonempty_legacy_gate


def _timestamp_values(value):
    if isinstance(value, dict):
        return {k: _timestamp_values(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_timestamp_values(v) for v in value]
    if isinstance(value, str) and ("T" in value and value.endswith(("Z", "+00:00"))):
        return value
    return None


def test_run_pipeline_refuses_1m():
    snap = make_snapshot(timeframe="1M")
    with pytest.raises(Refusal, match="timeframe"):
        run_pipeline_ng(snap, {"status": "OK"}, registry=_registry(), cell=_cell(snap), now=NOW)


def test_non_mapping_cell_is_refused():
    snap = make_snapshot()
    with pytest.raises(Refusal):
        run_pipeline_ng(snap, {"status": "OK"}, registry=_registry(), cell=[], now=NOW)


def test_unsupported_argument_precedes_legacy_cell_validation():
    snap = make_snapshot()
    with pytest.raises(ValueError, match="^Unsupported methodology version: unknown$"):
        run_pipeline_ng(
            snap, {"status": "OK"}, registry=_registry(), cell=_cell(snap), now=NOW,
            methodology_version="unknown",
        )


def test_serving_state_hidden_for_shadow_and_unregistered() -> None:
    snap = make_snapshot()
    cell = _cell(snap)
    assert serving_state(_registry(_entry(cell)), cell, NOW).status == "SHADOW"
    assert serving_state(_registry(), cell, NOW).status == "NONE"


@pytest.mark.parametrize(
    "status",
    [
        "TRANSFER",
        "HISTORICALLY_CONFIRMED",
        "RANGE_ACCEPTED",
        "TRIPLET_ACCEPTED",
        "DEMOTED",
        "RETIRED",
    ],
)
def test_claim_statuses_refused(status):
    with pytest.raises(Refusal, match=status):
        validate_registry(_registry(_entry(_cell(make_snapshot()), status=status)))


@pytest.mark.parametrize(
    "updates,match",
    [
        ({"claims": ["look"]}, "claims"),
        ({"authorization_ref": "auth"}, "authorization_ref"),
        ({"policy_id": "policy"}, "DEFER"),
        ({"cohort_key": "calendar"}, "cohort_key"),
        ({"refit_calendar": "2026"}, "unknown entry key"),
        ({"status": "NONE"}, "status is unsupported"),
        ({"artifact_id": None}, "artifact_id"),
    ],
)
def test_registry_deferred_or_unbuilt_fields_refused(updates, match):
    with pytest.raises(Refusal, match=match):
        validate_registry(_registry(_entry(_cell(make_snapshot()), **updates)))


def test_slot_policy_and_tier_are_closed():
    with pytest.raises(Refusal, match="slot policy not ruled"):
        validate_registry(_registry(slot_policy="REFERENCE_AUTHORITATIVE"))
    with pytest.raises(Refusal, match="tier must be HEURISTIC"):
        ServingState("REFERENCE", "HIDDEN", "NONE", SLOT_POLICY, "reason")


@pytest.mark.parametrize("method", ["reference-daytype-v1", "ng-scale-v1"])
def test_unserved_methodology_uses_legacy_value_error(method):
    snap = make_snapshot()
    cell = _cell(snap, method)
    with pytest.raises(ValueError, match=f"Unsupported methodology version: {method}"):
        run_pipeline_ng(
            snap,
            {"status": "OK"},
            registry=_registry(),
            cell=cell,
            now=NOW,
            methodology_version=method,
        )


@pytest.mark.parametrize(
    "bad_now", [datetime(2026, 11, 3), datetime(2026, 11, 3, tzinfo=timezone(timedelta(hours=1)))]
)
def test_now_must_be_utc(bad_now):
    with pytest.raises(Refusal, match="UTC"):
        serving_state(_registry(), _cell(make_snapshot()), bad_now)


def test_snapshot_mismatches_are_refused():
    snap = make_snapshot()
    cell = _cell(snap)
    for field, value in (
        ("symbol", "ETH/USDT"),
        ("timeframe", "1H"),
        ("methodology_version", DISTRIBUTIONAL_METHODOLOGY_VERSION),
    ):
        bad = dict(cell, **{field: value})
        with pytest.raises(Refusal, match=field):
            run_pipeline_ng(
                snap, {"status": "OK"}, registry=_registry(), cell=bad, now=NOW
            )


def test_gate_hook_is_not_an_injection_point():
    snap = make_snapshot()
    with pytest.raises(TypeError):
        run_pipeline_ng(
            snap, {"status": "OK"}, registry=_registry(), cell=_cell(snap), now=NOW,
            apply_gates=lambda **_: {},
        )



@pytest.mark.parametrize(
    "field,value",
    [
        ("symbol", "btc/usdt"),
        ("venue", "OTHER"),
        ("timeframe", "1M"),
        ("horizon", True),
        ("target_version", ""),
        ("methodology_version", "ng-scale-v1"),
    ],
)
def test_malformed_cell_field_refused(field, value):
    snap = make_snapshot()
    with pytest.raises(Refusal):
        validate_registry(_registry(_entry(dict(_cell(snap), **{field: value}))))


def test_inputs_are_not_mutated_and_repeated_calls_are_deterministic():
    snap, provider = make_snapshot(), {"status": "OK"}
    cell = _cell(snap)
    registry = _registry(_entry(cell))
    before = copy.deepcopy((snap, provider, cell, registry))
    args = dict(registry=registry, cell=cell, now=NOW)
    first = run_pipeline_ng(snap, provider, **args)
    second = run_pipeline_ng(snap, provider, **args)
    assert first == second
    assert (snap, provider, cell, registry) == before
    legacy_before = copy.deepcopy((snap, provider))
    run_quant_pipeline(snap, provider)
    assert (snap, provider) == legacy_before
