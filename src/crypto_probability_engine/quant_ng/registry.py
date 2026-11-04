"""Dormant NG1 registry under KEEP_HOLD; no reference is served."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime

from crypto_probability_engine.config.defaults import (
    DEFAULT_METHODOLOGY_VERSION,
    DISTRIBUTIONAL_METHODOLOGY_VERSION,
)
from crypto_probability_engine.quant_ng.artifact import VENUES
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


def serving_state(registry: object, cell: object, now: datetime) -> ServingState:
    """Return the heuristic authority state; the reference remains hidden."""
    entries = validate_registry(registry)
    query_cell = _validate_cell(cell)
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
        raise Refusal("now must be a tz-aware UTC datetime")
    if now.utcoffset().total_seconds() != 0 or now.tzname() != "UTC":
        raise Refusal("now must be a tz-aware UTC datetime")
    key = _cell_key(query_cell)
    status = "NONE"
    for entry in entries:
        if _cell_key(entry["cell"]) == key:
            status = entry["status"]
            break
    return ServingState(
        tier="HEURISTIC",
        reference="HIDDEN",
        status=status,
        slot_policy=SLOT_POLICY,
        reason="OD-NG-4 KEEP_HOLD: the heuristic stays authoritative; the reference is hidden",
    )
