"""Dormant NG1 registry under KEEP_HOLD; no reference is served."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType as _MappingProxyType

from crypto_probability_engine.config.defaults import (
    DEFAULT_METHODOLOGY_VERSION,
    DISTRIBUTIONAL_METHODOLOGY_VERSION,
)
from crypto_probability_engine.quant_ng.artifact import VENUES
from crypto_probability_engine.quant_ng.evidence import Population as _Population
from crypto_probability_engine.quant_ng.windows import TIMEFRAME_SECONDS

SCHEMA_ID = "quant-ng-registry.v1"
# OD-NG-4 is KEEP_HOLD (2026-10-22, re-affirmed 2026-11-03). Option (A), a fit-free
# reference authoritative, needs a later owner ruling and a reviewed code change.
SLOT_POLICY = "HOLD_HIDDEN_REFERENCE"
ALLOWED_SLOT_POLICIES = frozenset({SLOT_POLICY})
ENTRY_STATUSES = frozenset({"SHADOW"})
PLAN_STATUSES = frozenset(
    {
        "SHADOW",
        "TRANSFER",
        "HISTORICALLY_CONFIRMED",
        "RANGE_ACCEPTED",
        "TRIPLET_ACCEPTED",
        "DEMOTED",
        "RETIRED",
    }
)
CELL_FIELDS = frozenset(
    {
        "symbol",
        "venue",
        "timeframe",
        "horizon",
        "target_version",
        "methodology_version",
    }
)
ENTRY_FIELDS = frozenset(
    {
        "cell",
        "recipe_id",
        "artifact_id",
        "status",
        "claims",
        "authorization_ref",
        "cohort_key",
        "policy_id",
    }
)
REGISTRY_FIELDS = frozenset({"schema", "slot_policy", "cells"})
SCHEMA_ID_V2 = "quant-ng-registry.v2"
# NGA v2 §H (MASTER_PLAN_v2.md:84-85), adopted as the target vocabulary by owner ruling NG6-D1 = A.
RESEARCH_STATUSES = frozenset(
    {"NONE", "SHADOW", "TRANSFER", "HISTORICALLY_CONFIRMED", "BASE_RATE_EQUIVALENT", "REJECTED"}
)
CLAIM_STATUSES = frozenset(
    {"NOT_RUN", "SUPPORTED_FOR_NAMED_SCOPE", "NOT_SUPPORTED", "INCONCLUSIVE", "UNINFORMATIVE"}
)
SERVING_STATES = frozenset(
    {
        "REFERENCE",
        "REFERENCE_LOW_SAMPLE",
        "CANDIDATE_RANGE_ACCEPTED",
        "CANDIDATE_TRIPLET_ACCEPTED",
        "HISTORICAL_LABELLED",
        "UNAVAILABLE",
        "HOLD_HIDDEN_REFERENCE",  # PROVISIONAL: the KEEP_HOLD state.
    }
)
PERMISSION_FLAGS = frozenset(
    {
        "numerical_availability",
        "historical_evidence",
        "prospective_support",
        "display",
        "directional",
    }
)
# PROVISIONAL: the owner determines how grants map to flags and serving states.
GRANTS_PROVISIONAL = PERMISSION_FLAGS | frozenset({"RANGE_ACCEPTANCE", "TRIPLET_ACCEPTANCE"})
CLAIM_TYPES = frozenset({"C-univ", "C-cov", "C-ref"})
ADMITTED_RESEARCH_STATUSES = frozenset({"NONE", "SHADOW"})
ADMITTED_CLAIM_STATUSES = frozenset({"NOT_RUN"})
ADMITTED_SERVING_STATES = frozenset({"HOLD_HIDDEN_REFERENCE"})
REGISTRY_FIELDS_V2 = frozenset({"schema", "slot_policy", "cells"})
ENTRY_FIELDS_V2 = frozenset(
    {
        "cell", "recipe_id", "artifact_id", "policy_id", "cohort_key", "serving_state",
        "research_status", "claim_status", "permissions", "claims", "authorization_refs",
    }
)
CLAIM_RECORD_FIELDS = frozenset(
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
AUTHORIZATION_REF_FIELDS = frozenset(
    {
        "cell", "recipe_id", "artifact_digest", "claim_look_ids", "grants",
        "owner_message_sha256", "t3_pr", "t4_run_id", "state_anchor",
    }
)
_LOOK_ID = re.compile(r"[a-z0-9][a-z0-9._-]{2,63}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_SYMBOL = re.compile(r"[A-Z0-9]{2,20}/[A-Z0-9]{2,10}\Z")
_METHODS = frozenset({DEFAULT_METHODOLOGY_VERSION, DISTRIBUTIONAL_METHODOLOGY_VERSION})
_TIMEFRAMES = frozenset(TIMEFRAME_SECONDS) | {"1D", "1W"}


class Refusal(ValueError):
    """A closed-contract registry or serving-state refusal."""


def _closed(payload: object, fields: frozenset[str], label: str) -> Mapping:
    if not isinstance(payload, Mapping):
        raise Refusal(f"{label} must be a mapping")
    unknown = set(payload) - fields
    if unknown:
        raise Refusal(f"unknown {label} key: {sorted(unknown, key=str)[0]}")
    missing = fields - set(payload)
    if missing:
        raise Refusal(f"missing {label} key: {sorted(missing)[0]}")
    return payload


def _cell_key(cell: Mapping) -> tuple[object, ...]:
    return tuple(
        cell[key]
        for key in (
            "symbol",
            "venue",
            "timeframe",
            "horizon",
            "target_version",
            "methodology_version",
        )
    )


def _validate_cell(payload: object) -> Mapping:
    cell = _closed(payload, CELL_FIELDS, "cell")
    symbol = cell["symbol"]
    if not isinstance(symbol, str) or not _SYMBOL.fullmatch(symbol):
        raise Refusal("symbol must be a normalized symbol")
    if not isinstance(cell["venue"], str) or cell["venue"] not in VENUES:
        raise Refusal("venue is unsupported")
    allowed_timeframe = isinstance(cell["timeframe"], str) and cell["timeframe"] in _TIMEFRAMES
    if not allowed_timeframe:
        raise Refusal("timeframe is unsupported")
    horizon = cell["horizon"]
    if isinstance(horizon, bool) or not isinstance(horizon, int) or horizon < 1:
        raise Refusal("horizon must be an int greater than or equal to one")
    if not isinstance(cell["target_version"], str) or not cell["target_version"].strip():
        raise Refusal("target_version must be a non-empty string")
    if (
        not isinstance(cell["methodology_version"], str)
        or cell["methodology_version"] not in _METHODS
    ):
        raise Refusal("methodology_version is not served under KEEP_HOLD")
    return cell


def _copy(payload: object) -> object:
    """Read a caller's mapping once; every later check and the snapshot use this copy."""
    return dict(payload) if isinstance(payload, Mapping) else payload


def _non_empty_string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise Refusal(f"{field} must be a non-empty string")
    return value


def _digest(value: object, field: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise Refusal(f"{field} must be 64 lowercase hexadecimal characters")
    return value


def _validate_claim_record(payload: object) -> Mapping:
    """Validate one v2 claim's closed structure; admission is handled by its caller."""
    record = _closed(_copy(payload), CLAIM_RECORD_FIELDS, "claim record")
    claim_type = record["claim_type"]
    if not isinstance(claim_type, str) or claim_type not in CLAIM_TYPES:
        raise Refusal(f"claim_type is unsupported: {claim_type}")
    look_id = record["look_id"]
    if not isinstance(look_id, str) or not _LOOK_ID.fullmatch(look_id):
        raise Refusal("look_id is invalid")
    claim_status = record["claim_status"]
    if not isinstance(claim_status, str) or claim_status not in CLAIM_STATUSES:
        raise Refusal(f"claim status is unsupported: {claim_status}")
    if claim_status == "NOT_RUN":
        raise Refusal("NOT_RUN is not valid in a claim record")
    scope_sentence = _non_empty_string(record["scope_sentence"], "scope_sentence")
    evidence_digest = _digest(record["evidence_digest"], "evidence_digest")
    population = record["population"]
    population_value = population.value if isinstance(population, _Population) else population
    if not isinstance(population_value, str):
        raise Refusal(f"population is unsupported: {population}")
    try:
        population_value = _Population(population_value).value
    except ValueError:
        raise Refusal(f"population is unsupported: {population_value}") from None
    if population_value in {_Population.E1_OPERATIONAL.value, _Population.E4_USER_REQUESTED.value}:
        raise Refusal(f"population is refused by name: {population_value}")
    if population_value not in {
        _Population.E2_RECONSTRUCTION.value,
        _Population.E3_SPACE_ISSUED.value,
    }:
        raise Refusal(f"population is unsupported: {population_value}")
    ledger_ref = _non_empty_string(record["look_ledger_ref"], "look_ledger_ref")
    return _MappingProxyType(
        {
            "claim_type": claim_type,
            "look_id": look_id,
            "claim_status": claim_status,
            "scope_sentence": scope_sentence,
            "evidence_digest": evidence_digest,
            "population": population_value,
            "look_ledger_ref": ledger_ref,
        }
    )


def _validate_authorization_ref(payload: object) -> Mapping:
    """Validate one v2 authorization's closed structure; it never grants access."""
    authorization = _closed(_copy(payload), AUTHORIZATION_REF_FIELDS, "authorization reference")
    cell = _validate_cell(_copy(authorization["cell"]))
    recipe_id = _non_empty_string(authorization["recipe_id"], "recipe_id")
    artifact_digest = _digest(authorization["artifact_digest"], "artifact_digest")
    look_ids = authorization["claim_look_ids"]
    if not isinstance(look_ids, list):
        raise Refusal("claim_look_ids must be a list")
    if not look_ids:
        raise Refusal("claim_look_ids must be non-empty")
    checked_look_ids = []
    for look_id in look_ids:
        if not isinstance(look_id, str) or not _LOOK_ID.fullmatch(look_id):
            raise Refusal("claim_look_id is invalid")
        if look_id in checked_look_ids:
            raise Refusal("duplicate claim_look_id")
        checked_look_ids.append(look_id)
    grant = authorization["grants"]
    if not isinstance(grant, str) or grant not in GRANTS_PROVISIONAL:
        raise Refusal(f"grant is unsupported: {grant}")
    owner_sha = _digest(authorization["owner_message_sha256"], "owner_message_sha256")
    t3_pr = authorization["t3_pr"]
    if type(t3_pr) is not int or t3_pr < 1:
        raise Refusal("t3_pr must be an int greater than or equal to one")
    t4_run_id = authorization["t4_run_id"]
    if type(t4_run_id) is not int or t4_run_id < 1:
        raise Refusal("t4_run_id must be an int greater than or equal to one")
    state_anchor = _non_empty_string(authorization["state_anchor"], "state_anchor")
    return _MappingProxyType(
        {
            "cell": _MappingProxyType(dict(cell)),
            "recipe_id": recipe_id,
            "artifact_digest": artifact_digest,
            "claim_look_ids": tuple(checked_look_ids),
            "grants": grant,
            "owner_message_sha256": owner_sha,
            "t3_pr": t3_pr,
            "t4_run_id": t4_run_id,
            "state_anchor": state_anchor,
        }
    )


def validate_registry_v2(registry: object) -> tuple[_MappingProxyType, ...]:
    """Validate v2 and return an immutable snapshot of its admitted records."""
    payload = _closed(_copy(registry), REGISTRY_FIELDS_V2, "registry")
    if payload["schema"] != SCHEMA_ID_V2:
        raise Refusal("registry schema is unsupported")
    slot_policy = payload["slot_policy"]
    if not isinstance(slot_policy, str) or slot_policy not in ALLOWED_SLOT_POLICIES:
        raise Refusal(f"slot policy not ruled: {slot_policy}")
    raw_entries = payload["cells"]
    if not isinstance(raw_entries, list):
        raise Refusal("cells must be a list")

    checked_entries = []
    seen_cells = set()
    for raw_entry in raw_entries:
        entry = _closed(_copy(raw_entry), ENTRY_FIELDS_V2, "entry")
        cell = _validate_cell(_copy(entry["cell"]))
        cell_key = _cell_key(cell)
        if cell_key in seen_cells:
            raise Refusal("duplicate cell")
        seen_cells.add(cell_key)
        recipe_id = _non_empty_string(entry["recipe_id"], "recipe_id")
        research_status = entry["research_status"]
        if not isinstance(research_status, str) or research_status not in RESEARCH_STATUSES:
            raise Refusal(f"research status is unsupported: {research_status}")
        artifact_id = entry["artifact_id"]
        if research_status == "NONE":
            if artifact_id is not None:
                raise Refusal("NONE research status requires artifact_id to be null (PROVISIONAL)")
        elif not isinstance(artifact_id, str) or not artifact_id.strip():
            raise Refusal("research status requires a non-empty artifact_id")
        if entry["policy_id"] is not None:
            raise Refusal("policy identity is DEFER (OD-NG-2)")
        if entry["cohort_key"] != recipe_id:
            raise Refusal("cohort_key must equal recipe_id under OD-NG-2 DEFER")

        serving = entry["serving_state"]
        if not isinstance(serving, str) or serving not in SERVING_STATES:
            raise Refusal(f"serving state is unsupported: {serving}")
        claim_status = entry["claim_status"]
        if not isinstance(claim_status, str) or claim_status not in CLAIM_STATUSES:
            raise Refusal(f"claim status is unsupported: {claim_status}")
        permissions = _copy(entry["permissions"])
        if not isinstance(permissions, Mapping):
            raise Refusal("permissions must be a mapping")
        if set(permissions) != PERMISSION_FLAGS:
            extra = set(permissions) - PERMISSION_FLAGS
            if extra:
                raise Refusal(f"permission flag is unsupported: {sorted(extra, key=str)[0]}")
            missing_flag = sorted(PERMISSION_FLAGS - set(permissions))[0]
            raise Refusal(f"missing permission flag: {missing_flag}")
        checked_permissions = {}
        for flag in PERMISSION_FLAGS:
            value = permissions[flag]
            if type(value) is not bool:
                raise Refusal(f"permission flag must be a bool: {flag}")
            checked_permissions[flag] = value

        claims = entry["claims"]
        if not isinstance(claims, list):
            raise Refusal("claims must be a list")
        checked_claims = tuple(_validate_claim_record(record) for record in claims)
        authorization_refs = entry["authorization_refs"]
        if not isinstance(authorization_refs, list):
            raise Refusal("authorization_refs must be a list")
        checked_authorizations = tuple(
            _validate_authorization_ref(reference) for reference in authorization_refs
        )
        checked_entries.append(
            {
                "cell": _MappingProxyType(dict(cell)),
                "recipe_id": recipe_id,
                "artifact_id": artifact_id,
                "policy_id": None,
                "cohort_key": recipe_id,
                "serving_state": serving,
                "research_status": research_status,
                "claim_status": claim_status,
                "permissions": _MappingProxyType(checked_permissions),
                "claims": checked_claims,
                "authorization_refs": checked_authorizations,
            }
        )

    # Cross-check only after every record and authorization has passed structural validation.
    seen_look_ids = set()
    for entry in checked_entries:
        claim_ids = set()
        for claim in entry["claims"]:
            look_id = claim["look_id"]
            if look_id in seen_look_ids:
                raise Refusal("duplicate look_id")
            seen_look_ids.add(look_id)
            claim_ids.add(look_id)
        for authorization in entry["authorization_refs"]:
            for look_id in authorization["claim_look_ids"]:
                if look_id not in claim_ids:
                    raise Refusal(f"authorization claim_look_id is not in claims: {look_id}")
            if _cell_key(authorization["cell"]) != _cell_key(entry["cell"]):
                raise Refusal("authorization cell must equal entry cell")
            if authorization["recipe_id"] != entry["recipe_id"]:
                raise Refusal("authorization recipe_id must equal entry recipe_id")

    # Dormant refusals intentionally follow all structural and cross-record checks.
    for entry in checked_entries:
        # An authorization needs claims, so it is refused first: each refusal stays reachable.
        if entry["authorization_refs"]:
            raise Refusal("no authorization exists in this build")
        if entry["claims"]:
            raise Refusal(
                "no look exists in this build (the look ledger and claim outcomes are unruled)"
            )
        for flag, enabled in entry["permissions"].items():
            if enabled:
                raise Refusal(f"permission not ruled in this build: {flag}")
        if entry["serving_state"] not in ADMITTED_SERVING_STATES:
            raise Refusal("not ruled: OD-NG-4 KEEP_HOLD")
        if entry["research_status"] not in ADMITTED_RESEARCH_STATUSES:
            raise Refusal(
                "research status not admitted in this build (its transition is unruled): "
                f"{entry['research_status']}"
            )
        if entry["claim_status"] not in ADMITTED_CLAIM_STATUSES:
            raise Refusal(f"claim status requires a look: {entry['claim_status']}")
        if entry["research_status"] == "SHADOW" and not entry["artifact_id"]:
            raise Refusal("SHADOW research status requires a non-empty artifact_id")
    return tuple(_MappingProxyType(entry) for entry in checked_entries)


def validate_registry(registry: object) -> tuple[Mapping, ...]:
    """Validate a caller-owned registry mapping and return its entries."""
    payload = _closed(registry, REGISTRY_FIELDS, "registry")
    if payload["schema"] != SCHEMA_ID:
        raise Refusal("registry schema is unsupported")
    policy = payload["slot_policy"]
    if not isinstance(policy, str) or policy not in ALLOWED_SLOT_POLICIES:
        raise Refusal(f"slot policy not ruled: {policy}")
    entries = payload["cells"]
    if not isinstance(entries, list):
        raise Refusal("cells must be a list")
    seen = set()
    for entry_raw in entries:
        entry = _closed(entry_raw, ENTRY_FIELDS, "entry")
        cell = _validate_cell(entry["cell"])
        key = _cell_key(cell)
        if key in seen:
            raise Refusal("duplicate cell")
        seen.add(key)
        recipe = entry["recipe_id"]
        if not isinstance(recipe, str) or not recipe.strip():
            raise Refusal("recipe_id must be a non-empty string")
        status = entry["status"]
        if not isinstance(status, str) or status not in PLAN_STATUSES:
            raise Refusal(f"status is unsupported: {status}")
        if status not in ENTRY_STATUSES:
            raise Refusal(
                f"status requires a claim record and an authorization (B-NG6, not built): {status}"
            )
        artifact = entry["artifact_id"]
        if not isinstance(artifact, str) or not artifact.strip():
            raise Refusal("SHADOW status requires a non-empty artifact_id")
        if entry["claims"] != []:
            raise Refusal("claims must be empty; no look exists in this build")
        if entry["authorization_ref"] is not None:
            raise Refusal("authorization_ref must be null; no authorization exists in this build")
        policy_id = entry["policy_id"]
        if policy_id is not None:
            raise Refusal(f"policy identity is DEFER (OD-NG-2): {policy_id}")
        if entry["cohort_key"] != recipe:
            raise Refusal("cohort_key must equal recipe_id under OD-NG-2 DEFER")
    return tuple(entries)


@dataclass(frozen=True)
class ServingState:
    tier: str
    reference: str
    status: str
    slot_policy: str
    reason: str

    def __post_init__(self) -> None:
        if self.tier != "HEURISTIC":
            raise Refusal("tier must be HEURISTIC under KEEP_HOLD")
        if self.reference != "HIDDEN":
            raise Refusal("reference must be HIDDEN under KEEP_HOLD")
        if self.status not in {"NONE", "SHADOW"}:
            raise Refusal("status not admitted under KEEP_HOLD")
        if self.slot_policy != SLOT_POLICY:
            raise Refusal("slot policy not admitted under KEEP_HOLD")


def serving_state(registry: object, cell: object, now: datetime) -> ServingState:
    """Return the heuristic authority state; the reference remains hidden."""
    if isinstance(registry, Mapping) and "schema" in registry:
        schema = registry["schema"]
        if schema == SCHEMA_ID_V2:
            entries = validate_registry_v2(registry)
            is_v2 = True
        elif schema == SCHEMA_ID:
            entries = validate_registry(registry)
            is_v2 = False
        else:
            raise Refusal("registry schema is unsupported")
    else:
        entries = validate_registry(registry)
        is_v2 = False
    query_cell = _validate_cell(cell)
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
        raise Refusal("now must be a tz-aware UTC datetime")
    if now.utcoffset().total_seconds() != 0 or now.tzname() != "UTC":
        raise Refusal("now must be a tz-aware UTC datetime")
    key = _cell_key(query_cell)
    status = "NONE"
    for entry in entries:
        if _cell_key(entry["cell"]) == key:
            status = entry["research_status"] if is_v2 else entry["status"]
            break
    return ServingState(
        tier="HEURISTIC",
        reference="HIDDEN",
        status=status,
        slot_policy=SLOT_POLICY,
        reason="OD-NG-4 KEEP_HOLD: the heuristic stays authoritative; the reference is hidden",
    )
