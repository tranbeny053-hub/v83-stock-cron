"""The view of a saved run, built when the run is read back (owner rulings AD2=read time and R1=A;
the legacy-sections parity review, 2026-10-11).

A saved run stores no decision view. It stores facts: its gate result, the liquidity state its
liquidity gate judged, its probabilities, its costs, its brief's labels. This builds, from those
facts and nothing else, the block a reopened run shows in place of the older gate brief:
- the gate authority (detail/gate_kinds.py), as a live analysis of the same facts reads;
- the values the stored record really holds;
- None for a value it does not hold, which the screen says in so many words ("Not kept in saved
  history."): the reference close, the horizon's end and the directional-skill evidence are not
  stored with a run.

Facts, never sentences: nothing here is read from a sentence the run stored when it was saved, so
an old run and a new one read the same and a wording change needs no stored text rewritten. Nothing
is stored either: the view is attached to the detail as it is returned, and the stored detail is
not changed.

It never raises. Reading a saved run must not fail on what an old or damaged row holds (review
finding D5): a value that is not what the builder writes reads as not kept, and a gate result that
is not what the gates write is not framed at all, because a framing built from it could contradict
the record. The view then says that no gate result can be read.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from crypto_probability_engine.detail.decision_brief import (
    MODEL_READINESS,
    MODEL_READINESS_COPY,
    PROBABILITY_EXPLANATION,
    PROBABILITY_TYPE,
)
from crypto_probability_engine.detail.decision_view import (
    COST_LABEL,
    NOT_ASSESSED,
    RANGE_MEANING,
)
from crypto_probability_engine.detail.gate_kinds import build_gate_view

SCHEMA_VERSION = "saved_run_view.v1"
GATES_NOT_READABLE = (
    "No gate result can be read from this saved analysis, so no gate framing is shown."
)
# The hard blocks under which the live view assesses nothing (decision_view._data_state).
_UNAVAILABLE_DATA_BLOCKS = frozenset({"PROVIDER_DEGRADED", "EPISTEMIC_VOID"})


def build_saved_run_view(detail: Mapping[str, Any]) -> dict[str, Any]:
    """The view of one saved run: a pure function of the detail it stores."""

    gate = _readable_gate(detail.get("invalidation_detail"))
    liquidity_execution = _mapping(detail.get("liquidity_execution_detail"))
    execution = _mapping(liquidity_execution.get("execution_realism"))
    quality = _mapping(detail.get("data_quality_detail"))
    provider_state = _mapping(quality.get("provider_state"))
    data_quality = _mapping(quality.get("data_quality"))
    brief = _mapping(detail.get("decision_brief"))
    horizon = _mapping(
        _mapping(_mapping(detail.get("probability_detail")).get("horizons")).get("H_primary")
    )
    assessed = _assessed(gate, provider_state)
    heuristic = brief.get("probability_type") == PROBABILITY_TYPE
    band = _fraction(execution.get("round_trip_cost_frac"))
    return {
        "schema_version": SCHEMA_VERSION,
        "gates": None
        if gate is None
        else build_gate_view(gate, liquidity=liquidity_execution.get("liquidity_state")),
        "gates_note": GATES_NOT_READABLE if gate is None else None,
        "disposition": _disposition(gate, _mapping(detail.get("score_detail"))),
        # The stored gate result's own action and blocks, as the gates wrote them (raw tokens).
        "gate_action": None if gate is None else _text(gate.get("action")),
        "hard_blocks": None if gate is None else list(gate.get("hard_blocks") or []),
        "venue": _text(provider_state.get("active_provider")),
        "timeframe_label": _text(brief.get("timeframe_label")),
        "horizon_label": _text(brief.get("horizon_label")),
        # The target contract's times are computed from the candles, which a run does not store.
        "time": {"reference_close_utc": None, "horizon_end_utc": None},
        "data": {
            "data_source": _text(data_quality.get("data_source")),
            "is_live_data": _boolean(data_quality.get("is_live_data")),
        },
        "range": {
            "assessed": assessed,
            "decision_band_frac": band,
            "in_band_frac": _fraction(horizon.get("p_timeout_frac")) if assessed else None,
            "up_frac": _fraction(horizon.get("p_up_frac")) if assessed else None,
            "down_frac": _fraction(horizon.get("p_down_frac")) if assessed else None,
            "meaning": RANGE_MEANING if assessed else NOT_ASSESSED,
            # What the percentages are, said from the stored evidence level, not a stored sentence.
            "explanation": PROBABILITY_EXPLANATION if assessed and heuristic else None,
        },
        "cost": {"round_trip_cost_frac": band, "label": COST_LABEL},
        "evidence": {
            "level": MODEL_READINESS_COPY
            if brief.get("model_readiness") == MODEL_READINESS
            else None,
            "probability_type": _text(brief.get("probability_type")),
            "calibration_status": _text(brief.get("calibration_status")),
            "reliability_status": _text(brief.get("reliability_status")),
            # The directional-skill verdict and its count are not stored with a run.
            "skill_verdict": None,
            "resolved_outcomes": None,
            "directional_evidence_hold": None if gate is None else _hold_active(gate),
        },
    }


def attach_saved_run_view(detail: Any) -> Any:
    """A run's detail as it is read back, with the view built now from what it stores. The stored
    detail is not changed. It never raises: a detail that is not a mapping, or one whose reading
    fails, is returned as it is."""

    try:
        if not isinstance(detail, Mapping):
            return detail
        return {**detail, "saved_run_view": build_saved_run_view(detail)}
    except Exception:
        return detail


def _readable_gate(gate: Any) -> Mapping[str, Any] | None:
    """The stored gate result when it is what the gates write: a mapping whose `hard_blocks` is a
    list of block names, or is absent or None, which reads as no blocks. Anything else is None."""

    if not isinstance(gate, Mapping):
        return None
    blocks = gate.get("hard_blocks")
    if blocks is None:
        return gate
    if isinstance(blocks, list) and all(isinstance(block, str) for block in blocks):
        return gate
    return None


def _assessed(gate: Mapping[str, Any] | None, provider_state: Mapping[str, Any]) -> bool:
    """Whether the live view of these facts showed a range (its precedence 1, the data state): it
    shows none when no venue served valid data or the inputs were insufficient."""

    blocks = set(gate.get("hard_blocks") or []) if gate is not None else set()
    if blocks & _UNAVAILABLE_DATA_BLOCKS:
        return False
    return provider_state.get("status") in {"OK", "DEGRADED"}


def _disposition(gate: Mapping[str, Any] | None, score: Mapping[str, Any]) -> str | None:
    """The gates' disposition as the live analysis showed it (detail/frontend_display.py): the gate
    action when a hard gate did not pass, else the score's disposition."""

    if gate is None:
        return None
    if gate.get("hard_gate_passed") is True:
        return _text(score.get("disposition"))
    return _text(gate.get("action"))


def _hold_active(gate: Mapping[str, Any]) -> bool:
    hold = gate.get("directional_evidence_hold")
    return isinstance(hold, Mapping) and bool(hold.get("active"))


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _text(value: Any) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def _boolean(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


def _fraction(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value)
