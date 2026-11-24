from __future__ import annotations

import copy
from collections.abc import Mapping
from datetime import UTC, datetime

import pytest

from crypto_probability_engine.config.defaults import DEFAULT_METHODOLOGY_VERSION
from crypto_probability_engine.detail import decision_view
from crypto_probability_engine.quant_ng.pipeline_ng import run_pipeline_ng
from crypto_probability_engine.quant_ng.registry import (
    ADMITTED_CLAIM_STATUSES,
    ADMITTED_RESEARCH_STATUSES,
    ADMITTED_SERVING_STATES,
    AUTHORIZATION_REF_FIELDS,
    CLAIM_RECORD_FIELDS,
    CLAIM_STATUSES,
    CLAIM_TYPES,
    ENTRY_FIELDS_V2,
    GRANTS_PROVISIONAL,
    PERMISSION_FLAGS,
    REGISTRY_FIELDS_V2,
    RESEARCH_STATUSES,
    SCHEMA_ID,
    SCHEMA_ID_V2,
    SERVING_STATES,
    SLOT_POLICY,
    Refusal,
    ServingState,
    serving_state,
    validate_registry,
    validate_registry_v2,
)
from tests.fixtures.market_data import make_snapshot

NOW = datetime(2026, 11, 3, tzinfo=UTC)
CELL = {
    "symbol": "BTC/USDT",
    "venue": "BINANCE_PUBLIC",
    "timeframe": "4H",
    "horizon": 6,
    "target_version": "fixture-target-v1",
    "methodology_version": DEFAULT_METHODOLOGY_VERSION,
}
PERMISSIONS = {flag: False for flag in PERMISSION_FLAGS}


def _v1_entry(cell=CELL):
    return {
        "cell": copy.deepcopy(cell),
        "recipe_id": "recipe-fixture",
        "artifact_id": "artifact-fixture",
        "status": "SHADOW",
        "claims": [],
        "authorization_ref": None,
        "cohort_key": "recipe-fixture",
        "policy_id": None,
    }


def _v1_registry(*entries):
    return {"schema": SCHEMA_ID, "slot_policy": SLOT_POLICY, "cells": list(entries)}


def _v2_entry(cell=CELL, **updates):
    entry = {
        "cell": copy.deepcopy(cell),
        "recipe_id": "recipe-fixture",
        "artifact_id": "artifact-fixture",
        "policy_id": None,
        "cohort_key": "recipe-fixture",
        "serving_state": "HOLD_HIDDEN_REFERENCE",
        "research_status": "SHADOW",
        "claim_status": "NOT_RUN",
        "permissions": dict(PERMISSIONS),
        "claims": [],
        "authorization_refs": [],
    }
    entry.update(updates)
    return entry


def _v2_registry(*entries):
    return {"schema": SCHEMA_ID_V2, "slot_policy": SLOT_POLICY, "cells": list(entries)}


def _claim(**updates):
    record = {
        "claim_type": "C-univ",
        "look_id": "look-001",
        "claim_status": "SUPPORTED_FOR_NAMED_SCOPE",
        "scope_sentence": "A bounded scope sentence.",
        "evidence_digest": "a" * 64,
        "population": "E2_RECONSTRUCTION",
        "look_ledger_ref": "ledger-entry-001",
    }
    record.update(updates)
    return record


def _authorization(cell=CELL, **updates):
    reference = {
        "cell": copy.deepcopy(cell),
        "recipe_id": "recipe-fixture",
        "artifact_digest": "b" * 64,
        "claim_look_ids": ["look-001"],
        "grants": "display",
        "owner_message_sha256": "c" * 64,
        "t3_pr": 1,
        "t4_run_id": 1,
        "state_anchor": "anchor-001",
    }
    reference.update(updates)
    return reference


def _state_fields(state):
    return (state.tier, state.reference, state.status, state.slot_policy, state.reason)


def test_v1_and_v2_serving_state_and_pipeline_ng_block_match():
    one = _v1_registry(_v1_entry())
    two = _v2_registry(_v2_entry())
    assert _state_fields(serving_state(one, CELL, NOW)) == _state_fields(
        serving_state(two, CELL, NOW)
    )
    snapshot = make_snapshot()
    kwargs = {"cell": CELL, "now": NOW}
    v1_result = run_pipeline_ng(snapshot, {"status": "OK"}, registry=one, **kwargs)
    v2_result = run_pipeline_ng(snapshot, {"status": "OK"}, registry=two, **kwargs)
    assert v1_result["ng"] == v2_result["ng"]
    assert v1_result["ng"]["serving_state"]["status"] == "SHADOW"


def test_v1_validation_rejects_v2_schema_and_v1_empty_registry_is_unchanged():
    with pytest.raises(Refusal, match="^registry schema is unsupported$"):
        validate_registry(_v2_registry())
    from crypto_probability_engine.api.analysis_service import NG_EMPTY_REGISTRY

    assert NG_EMPTY_REGISTRY["schema"] == SCHEMA_ID


def test_admitted_v2_returns_immutable_snapshot_and_preserves_input():
    original = _v2_registry(_v2_entry())
    before = copy.deepcopy(original)
    snapshot = validate_registry_v2(original)
    assert isinstance(snapshot, tuple)
    with pytest.raises(TypeError):
        snapshot[0]["research_status"] = "TRANSFER"
    with pytest.raises(TypeError):
        snapshot[0]["cell"]["symbol"] = "ETH/USDT"
    assert original == before
    assert serving_state(original, CELL, NOW).status == "SHADOW"


def test_dormant_refusal_order_is_after_valid_claim_and_authorization_structure():
    record = _claim()
    reference = _authorization()
    entry = _v2_entry(
        research_status="TRANSFER",
        claims=[record],
        authorization_refs=[reference],
        permissions={**PERMISSIONS, "directional": True},
    )
    with pytest.raises(Refusal, match="^no look exists in this build"):
        validate_registry_v2(_v2_registry(entry))


@pytest.mark.parametrize(
    ("field", "values", "message"),
    [
        (
            "research_status",
            RESEARCH_STATUSES - ADMITTED_RESEARCH_STATUSES,
            "research status not admitted in this build",
        ),
        ("claim_status", CLAIM_STATUSES - ADMITTED_CLAIM_STATUSES, "claim status requires a look"),
        ("serving_state", SERVING_STATES - ADMITTED_SERVING_STATES, "not ruled: OD-NG-4 KEEP_HOLD"),
    ],
)
def test_known_status_values_are_refused_with_contract_message(field, values, message):
    for value in values:
        updates = {field: value}
        if field == "research_status" and value == "NONE":
            updates["artifact_id"] = None
        with pytest.raises(Refusal, match=message):
            validate_registry_v2(_v2_registry(_v2_entry(**updates)))


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("research_status", "MYSTERY", "research status is unsupported"),
        ("claim_status", "MYSTERY", "claim status is unsupported"),
        ("serving_state", "MYSTERY", "serving state is unsupported"),
        ("permissions", {**PERMISSIONS, "transfer": False}, "permission flag is unsupported"),
    ],
)
def test_unknown_vocabulary_values_are_shape_refusals(field, value, message):
    with pytest.raises(Refusal, match=message):
        validate_registry_v2(_v2_registry(_v2_entry(**{field: value})))


@pytest.mark.parametrize("value", [(), "", {}])
def test_claims_must_be_a_list(value):
    with pytest.raises(Refusal, match="^claims must be a list$"):
        validate_registry_v2(_v2_registry(_v2_entry(claims=value)))


@pytest.mark.parametrize("value", [1, 0])
def test_permission_values_must_be_real_booleans(value):
    with pytest.raises(Refusal, match="permission flag must be a bool"):
        validate_registry_v2(_v2_registry(_v2_entry(permissions={**PERMISSIONS, "display": value})))


def test_permissions_must_be_a_mapping():
    with pytest.raises(Refusal, match="^permissions must be a mapping$"):
        validate_registry_v2(_v2_registry(_v2_entry(permissions=list(PERMISSIONS.items()))))


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("claim_type", "C-hier", "claim_type is unsupported"),
        ("look_id", "Bad!", "look_id is invalid"),
        ("claim_status", "NOT_RUN", "NOT_RUN is not valid in a claim record"),
        ("scope_sentence", "  ", "scope_sentence must be a non-empty string"),
        ("evidence_digest", "A" * 64, "evidence_digest must be 64 lowercase"),
        ("population", "E1_OPERATIONAL", "E1_OPERATIONAL"),
        ("population", "E4_USER_REQUESTED", "E4_USER_REQUESTED"),
        ("population", "unknown", "population is unsupported"),
        ("look_ledger_ref", "", "look_ledger_ref must be a non-empty string"),
    ],
)
def test_claim_record_structure_errors_are_named(field, value, message):
    with pytest.raises(Refusal, match=message):
        validate_registry_v2(_v2_registry(_v2_entry(claims=[_claim(**{field: value})])))


def test_valid_claim_record_is_checked_before_the_dormant_refusal():
    with pytest.raises(Refusal, match="^no look exists in this build"):
        validate_registry_v2(_v2_registry(_v2_entry(claims=[_claim()])))


def test_authorization_reference_structure_and_cross_checks():
    good_entry = _v2_entry(claims=[_claim()], authorization_refs=[_authorization()])
    with pytest.raises(Refusal, match="^no look exists in this build"):
        validate_registry_v2(_v2_registry(good_entry))
    bad_refs = [
        ({"t3_pr": True}, "t3_pr must be an int"),
        ({"t4_run_id": 0}, "t4_run_id must be an int"),
        ({"claim_look_ids": ("look-001",)}, "claim_look_ids must be a list"),
        ({"claim_look_ids": ["look-001", "look-001"]}, "duplicate claim_look_id"),
        ({"claim_look_ids": ["missing"]}, "authorization claim_look_id is not in claims"),
        ({"grants": "TRANSFER"}, "grant is unsupported"),
        ({"owner_message_sha256": "z" * 64}, "owner_message_sha256 must be 64 lowercase"),
        ({"state_anchor": " "}, "state_anchor must be a non-empty string"),
    ]
    for changes, message in bad_refs:
        entry = _v2_entry(claims=[_claim()], authorization_refs=[_authorization(**changes)])
        with pytest.raises(Refusal, match=message):
            validate_registry_v2(_v2_registry(entry))
    wrong_cell = {**CELL, "symbol": "ETH/USDT"}
    entry = _v2_entry(claims=[_claim()], authorization_refs=[_authorization(cell=wrong_cell)])
    with pytest.raises(Refusal, match="authorization cell must equal entry cell"):
        validate_registry_v2(_v2_registry(entry))
    entry = _v2_entry(
        claims=[_claim()], authorization_refs=[_authorization(recipe_id="other-recipe")]
    )
    with pytest.raises(Refusal, match="authorization recipe_id must equal entry recipe_id"):
        validate_registry_v2(_v2_registry(entry))


def test_duplicate_look_ids_are_rejected_across_registry_entries():
    second_cell = {**CELL, "symbol": "ETH/USDT"}
    entries = [
        _v2_entry(claims=[_claim()]),
        _v2_entry(cell=second_cell, claims=[_claim()]),
    ]
    with pytest.raises(Refusal, match="^duplicate look_id$"):
        validate_registry_v2(_v2_registry(*entries))


@pytest.mark.parametrize(
    ("status", "artifact", "message"),
    [
        ("NONE", "artifact-present", "NONE research status requires artifact_id to be null"),
        ("SHADOW", None, "research status requires a non-empty artifact_id"),
    ],
)
def test_none_and_shadow_artifact_constraints(status, artifact, message):
    with pytest.raises(Refusal, match=message):
        validate_registry_v2(_v2_registry(_v2_entry(research_status=status, artifact_id=artifact)))


def test_policy_and_cohort_contracts_are_enforced():
    with pytest.raises(Refusal, match="policy identity is DEFER"):
        validate_registry_v2(_v2_registry(_v2_entry(policy_id="policy")))
    with pytest.raises(Refusal, match="cohort_key must equal recipe_id"):
        validate_registry_v2(_v2_registry(_v2_entry(cohort_key="other")))


def test_duplicate_cells_are_rejected():
    with pytest.raises(Refusal, match="^duplicate cell$"):
        validate_registry_v2(_v2_registry(_v2_entry(), _v2_entry()))


def test_serving_state_guards_and_v2_schema_dispatch():
    with pytest.raises(Refusal, match="status not admitted under KEEP_HOLD"):
        ServingState("HEURISTIC", "HIDDEN", "TRANSFER", SLOT_POLICY, "reason")
    with pytest.raises(Refusal, match="slot policy not admitted under KEEP_HOLD"):
        ServingState("HEURISTIC", "HIDDEN", "SHADOW", "OTHER", "reason")
    with pytest.raises(Refusal, match="^registry schema is unsupported$"):
        serving_state({"schema": "future", "slot_policy": SLOT_POLICY, "cells": []}, CELL, NOW)
    assert serving_state(_v2_registry(), CELL, NOW).status == "NONE"


class _ChangingEntry(Mapping):
    def __init__(self, data):
        self.data = data
        self.status_reads = 0

    def __iter__(self):
        return iter(self.data)

    def __len__(self):
        return len(self.data)

    def __getitem__(self, key):
        if key == "research_status":
            self.status_reads += 1
            return "SHADOW" if self.status_reads == 1 else "TRANSFER"
        return self.data[key]


def test_changing_mapping_status_is_snapshotted_once():
    entry = _ChangingEntry(_v2_entry())
    registry = _v2_registry()
    registry["cells"] = [entry]
    try:
        state = serving_state(registry, CELL, NOW)
        assert state.status == "SHADOW"
    except Refusal:
        pass
    assert entry.status_reads <= 1


def test_decision_view_acceptance_guard_remains_closed():
    assert len(decision_view.ACCEPTANCE_BLOCKERS) == 4
    assert all(
        blocker.startswith(prefix)
        for blocker, prefix in zip(
            decision_view.ACCEPTANCE_BLOCKERS,
            ("BANNER:", "RELIABILITY_LABEL:", "RENDER_TEST:", "BACKEND_COPY:"),
            strict=True,
        )
    )
    assert decision_view.ACCEPTED_FORECAST_CLAIMS == frozenset()
    assert decision_view.ACCEPTED_DIRECTIONAL_PERMISSIONS == frozenset()


def test_v2_validation_is_deterministic_and_pure():
    registry = _v2_registry(_v2_entry())
    original = copy.deepcopy(registry)
    assert validate_registry_v2(registry) == validate_registry_v2(registry)
    assert registry == original


def test_public_surface_is_explicitly_allowlisted():
    import crypto_probability_engine.quant_ng.registry as registry

    expected = {
        "ALLOWED_SLOT_POLICIES",
        "annotations",
        "ADMITTED_CLAIM_STATUSES",
        "ADMITTED_RESEARCH_STATUSES",
        "ADMITTED_SERVING_STATES",
        "AUTHORIZATION_REF_FIELDS",
        "CELL_FIELDS",
        "CLAIM_RECORD_FIELDS",
        "CLAIM_STATUSES",
        "CLAIM_TYPES",
        "DEFAULT_METHODOLOGY_VERSION",
        "DISTRIBUTIONAL_METHODOLOGY_VERSION",
        "ENTRY_FIELDS",
        "ENTRY_FIELDS_V2",
        "ENTRY_STATUSES",
        "GRANTS_PROVISIONAL",
        "PERMISSION_FLAGS",
        "PLAN_STATUSES",
        "REGISTRY_FIELDS",
        "REGISTRY_FIELDS_V2",
        "RESEARCH_STATUSES",
        "SCHEMA_ID",
        "SCHEMA_ID_V2",
        "SERVING_STATES",
        "SLOT_POLICY",
        "TIMEFRAME_SECONDS",
        "VENUES",
        "Refusal",
        "ServingState",
        "dataclass",
        "datetime",
        "re",
        "Mapping",
        "serving_state",
        "validate_registry",
        "validate_registry_v2",
    }
    assert {name for name in dir(registry) if not name.startswith("_")} == expected
    assert ADMITTED_RESEARCH_STATUSES == frozenset({"NONE", "SHADOW"})
    assert CLAIM_TYPES == frozenset({"C-univ", "C-cov", "C-ref"})
    assert GRANTS_PROVISIONAL == PERMISSION_FLAGS | {"RANGE_ACCEPTANCE", "TRIPLET_ACCEPTANCE"}
    assert REGISTRY_FIELDS_V2 == frozenset({"schema", "slot_policy", "cells"})
    assert ENTRY_FIELDS_V2 == frozenset(
        {
            "cell",
            "recipe_id",
            "artifact_id",
            "policy_id",
            "cohort_key",
            "serving_state",
            "research_status",
            "claim_status",
            "permissions",
            "claims",
            "authorization_refs",
        }
    )
    assert CLAIM_RECORD_FIELDS == frozenset(
        {
            "claim_type",
            "look_id",
            "claim_status",
            "scope_sentence",
            "evidence_digest",
            "population",
            "look_ledger_ref",
        }
    )
    assert AUTHORIZATION_REF_FIELDS == frozenset(
        {
            "cell",
            "recipe_id",
            "artifact_digest",
            "claim_look_ids",
            "grants",
            "owner_message_sha256",
            "t3_pr",
            "t4_run_id",
            "state_anchor",
        }
    )


def test_vocabularies_are_exactly_the_plan_text():
    # MASTER_PLAN_v2.md:84-85 (NG6-D1 = A); MASTER_PLAN.md:97-103 (F.3) plus the KEEP_HOLD state.
    assert RESEARCH_STATUSES == frozenset(
        {
            "NONE",
            "SHADOW",
            "TRANSFER",
            "HISTORICALLY_CONFIRMED",
            "BASE_RATE_EQUIVALENT",
            "REJECTED",
        }
    )
    assert CLAIM_STATUSES == frozenset(
        {
            "NOT_RUN",
            "SUPPORTED_FOR_NAMED_SCOPE",
            "NOT_SUPPORTED",
            "INCONCLUSIVE",
            "UNINFORMATIVE",
        }
    )
    assert SERVING_STATES == frozenset(
        {
            "REFERENCE",
            "REFERENCE_LOW_SAMPLE",
            "CANDIDATE_RANGE_ACCEPTED",
            "CANDIDATE_TRIPLET_ACCEPTED",
            "HISTORICAL_LABELLED",
            "UNAVAILABLE",
            "HOLD_HIDDEN_REFERENCE",
        }
    )
    assert PERMISSION_FLAGS == frozenset(
        {
            "numerical_availability",
            "historical_evidence",
            "prospective_support",
            "display",
            "directional",
        }
    )
    assert CLAIM_TYPES == frozenset({"C-univ", "C-cov", "C-ref"})


def test_a_cell_mapping_is_read_once_and_the_snapshot_holds_the_checked_value():
    class Flipping(Mapping):
        """Answers "BTC/USDT" for symbol on the first read and an invalid value afterwards."""

        def __init__(self, data):
            self.data, self.reads = dict(data), 0

        def __getitem__(self, key):
            if key == "symbol":
                self.reads += 1
                return self.data[key] if self.reads == 1 else "btc/usdt"
            return self.data[key]

        def __iter__(self):
            return iter(self.data)

        def __len__(self):
            return len(self.data)

    entry = _v2_entry()
    entry["cell"] = Flipping(entry["cell"])
    snapshot = validate_registry_v2(_v2_registry(entry))
    assert snapshot[0]["cell"]["symbol"] == "BTC/USDT"
    assert entry["cell"].reads == 1
