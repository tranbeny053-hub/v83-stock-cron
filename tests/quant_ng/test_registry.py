from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest

from crypto_probability_engine.config.defaults import DEFAULT_METHODOLOGY_VERSION
from crypto_probability_engine.quant_ng.registry import (
    SLOT_POLICY,
    Refusal,
    ServingState,
    serving_state,
    validate_registry,
)

NOW = datetime(2026, 11, 3, tzinfo=UTC)
CELL = {
    "symbol": "BTC/USDT",
    "venue": "BINANCE_PUBLIC",
    "timeframe": "4H",
    "horizon": 6,
    "target_version": "target-v1",
    "methodology_version": DEFAULT_METHODOLOGY_VERSION,
}
ENTRY = {
    "cell": CELL,
    "recipe_id": "recipe-1",
    "artifact_id": "artifact-1",
    "status": "SHADOW",
    "claims": [],
    "authorization_ref": None,
    "cohort_key": "recipe-1",
    "policy_id": None,
}


def registry(*entries, **extra):
    return {
        "schema": "quant-ng-registry.v1",
        "slot_policy": SLOT_POLICY,
        "cells": list(entries),
        **extra,
    }


def test_closed_registry_and_entry_shapes():
    assert len(validate_registry(registry(ENTRY))) == 1
    with pytest.raises(Refusal, match="unknown registry key"):
        validate_registry(registry(ENTRY, extra=True))
    with pytest.raises(Refusal, match="missing registry key"):
        validate_registry({"schema": "quant-ng-registry.v1", "slot_policy": SLOT_POLICY})
    with pytest.raises(Refusal, match="unknown entry key"):
        validate_registry(registry({**ENTRY, "refit_calendar": "calendar"}))
    with pytest.raises(Refusal, match="missing entry key"):
        validate_registry(registry({key: val for key, val in ENTRY.items() if key != "policy_id"}))
    with pytest.raises(Refusal, match="unknown cell key"):
        validate_registry(registry({**ENTRY, "cell": {**CELL, "extra": True}}))


def test_slot_policy_only_admits_ruled_keep_hold_value():
    with pytest.raises(Refusal, match="slot policy not ruled: REFERENCE_AUTHORITATIVE"):
        validate_registry(
            {
                "schema": "quant-ng-registry.v1",
                "slot_policy": "REFERENCE_AUTHORITATIVE",
                "cells": [],
            }
        )


def test_only_shadow_status_and_empty_claim_authorization_are_admitted():
    with pytest.raises(
        Refusal, match="status requires a claim record and an authorization.*TRANSFER"
    ):
        validate_registry(registry({**ENTRY, "status": "TRANSFER"}))
    with pytest.raises(Refusal, match="claims"):
        validate_registry(registry({**ENTRY, "claims": ["look"]}))
    with pytest.raises(Refusal, match="authorization_ref"):
        validate_registry(registry({**ENTRY, "authorization_ref": "approved"}))
    with pytest.raises(Refusal, match="status is unsupported: NONE"):
        validate_registry(registry({**ENTRY, "status": "NONE"}))
    with pytest.raises(Refusal, match="artifact_id"):
        validate_registry(registry({**ENTRY, "artifact_id": None}))


def test_deferred_policy_identity_and_cohort_are_enforced():
    with pytest.raises(Refusal, match=r"DEFER \(OD-NG-2\)"):
        validate_registry(registry({**ENTRY, "policy_id": "candidate-policy"}))
    with pytest.raises(Refusal, match="cohort_key must equal recipe_id"):
        validate_registry(registry({**ENTRY, "cohort_key": "calendar:2026"}))


@pytest.mark.parametrize(
    "bad_cell",
    [
        {**CELL, "symbol": "btc/usdt"},
        {**CELL, "symbol": 3},
        {**CELL, "venue": "unsupported"},
        {**CELL, "timeframe": "1M"},
        {**CELL, "horizon": True},
        {**CELL, "horizon": 0},
        {**CELL, "target_version": " "},
        {**CELL, "methodology_version": "ng-scale-v1"},
    ],
)
def test_cell_shape_and_admitted_values(bad_cell):
    with pytest.raises(Refusal):
        validate_registry(registry({**ENTRY, "cell": bad_cell}))


def test_duplicate_cells_are_refused():
    with pytest.raises(Refusal, match="duplicate cell"):
        validate_registry(registry(ENTRY, ENTRY))


def test_serving_state_is_always_hidden_and_heuristic():
    present = serving_state(registry(ENTRY), CELL, NOW)
    absent = serving_state(registry(), CELL, NOW)
    assert (present.tier, present.reference, present.status) == ("HEURISTIC", "HIDDEN", "SHADOW")
    assert (absent.tier, absent.reference, absent.status) == ("HEURISTIC", "HIDDEN", "NONE")
    assert present.slot_policy == SLOT_POLICY
    with pytest.raises(Refusal, match="tier must be HEURISTIC"):
        ServingState("REFERENCE", "HIDDEN", "SHADOW", SLOT_POLICY, "reason")
    with pytest.raises(Refusal, match="reference must be HIDDEN"):
        ServingState("HEURISTIC", "SHOWN", "SHADOW", SLOT_POLICY, "reason")


@pytest.mark.parametrize(
    "bad_now",
    [
        datetime(2026, 11, 3),
        datetime(2026, 11, 3, tzinfo=timezone(timedelta(hours=1))),
        datetime(2026, 1, 15, tzinfo=timezone(timedelta(0), "GMT")),
    ],
    ids=["naive", "plus-one-hour", "zero-offset-but-not-utc"],
)
def test_now_must_be_aware_utc(bad_now):
    with pytest.raises(Refusal, match="UTC"):
        serving_state(registry(), CELL, bad_now)
