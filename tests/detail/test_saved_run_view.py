"""The view of a saved run, built when it is read back (detail/saved_run_view.py; owner ruling
AD2=read time; the parity review's second item; review finding D5).

A reopened run shows a block of its own: the gate authority built from the facts it stores, the
values the stored record really holds, and None, which the screen reads as "Not kept in saved
history.", for what it does not hold. These tests read real analyses as they are stored, a run
saved before the gate framing existed, and stored rows that are damaged.
"""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import replace

import pytest

from crypto_probability_engine.adapters.provider_selection import ProviderSelectionResult
from crypto_probability_engine.adapters.types import OrderBookLevel, OrderBookSnapshot
from crypto_probability_engine.api import analysis_service
from crypto_probability_engine.api.schemas import AnalysisRequest
from crypto_probability_engine.config.settings import Settings
from crypto_probability_engine.detail import decision_view, gate_kinds, saved_run_view
from crypto_probability_engine.detail.decision_brief import (
    MODEL_READINESS_COPY,
    PROBABILITY_EXPLANATION,
)
from crypto_probability_engine.persistence.run_store import InMemoryRunStore
from crypto_probability_engine.quant import pipeline
from crypto_probability_engine.utils.sanitize import sanitize_for_export
from tests.api.test_analysis_endpoints import login, make_client
from tests.fixtures.market_data import FIXED_NOW, make_snapshot

NO_SKILL = {"verdict": "INSUFFICIENT_EVIDENCE", "n": 0, "observed_directional_rate": None}
SKILL = {"verdict": "SKILL_DEMONSTRATED", "n": 400, "observed_directional_rate": 0.6}
EVIDENCE_GATE = {"hard_blocks": ["SKILL_NOT_DEMONSTRATED"], "hard_gate_passed": False}


def _analysis(
    *,
    book: bool = True,
    thin: bool = False,
    kill: bool = False,
    lifted: bool = False,
    provider_status: str = "OK",
) -> dict:
    """One real analysis of the service, on the fixture candles (no network, no database)."""

    def select(symbol, timeframe, *, settings):
        del settings
        snapshot = make_snapshot(provider="okx", symbol=symbol.display, timeframe=timeframe)
        if thin:
            # A book that is measured, with a fine spread and too little depth: the liquidity
            # gate alone reports a finding (the execution cost stays under its threshold).
            levels = (
                (OrderBookLevel(price=120.0, size=0.1),),
                (OrderBookLevel(price=120.5, size=0.1),),
            )
            measured = OrderBookSnapshot(bids=levels[0], asks=levels[1], as_of_utc=FIXED_NOW)
            snapshot = replace(snapshot, order_book=measured)
        return ProviderSelectionResult(
            snapshot=snapshot if book else replace(snapshot, order_book=None),
            provider_state={
                "status": provider_status,
                "active_provider": "okx",
                "cross_provider_state": "UNAVAILABLE",
                "providers": {"okx": {"status": "OK"}},
            },
            data_quality={
                "status": "OK",
                "warnings": [],
                "freshness_budget": "DEFAULT_PHASE1A",
                "is_live_data": True,
                "data_source": "OKX_PUBLIC",
                "latest_candle_age_seconds": 0,
                "provider_failures": {},
                "cross_provider_state": "UNAVAILABLE",
            },
        )

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(analysis_service, "select_market_data", select)
        evidence = SKILL if lifted else NO_SKILL
        patch.setattr(analysis_service, "get_cached_skill_evidence", lambda _tf: dict(evidence))
        if lifted:
            patch.setattr(analysis_service, "evidence_for_gate", lambda found: (found, None))
        if kill:
            flags = {**pipeline.global_risk_state(), "kill_switch": True}
            patch.setattr(pipeline, "global_risk_state", lambda: dict(flags))
        return analysis_service.analyze_request(
            AnalysisRequest(symbol="BTC/USDT", timeframe="1H"),
            settings=Settings(data_mode="fixture"),
            run_store=InMemoryRunStore(limit=10),
        )


def _stored(payload: dict) -> dict:
    """What a run stores: its detail view through the export sanitizer, as JSON reads back."""

    return json.loads(json.dumps(sanitize_for_export(deepcopy(payload["detail_view"]))))


def _read(payload: dict) -> dict:
    return saved_run_view.attach_saved_run_view(_stored(payload))["saved_run_view"]


def test_a_saved_run_reads_the_gate_authority_its_live_analysis_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for facts in ({}, {"book": False}, {"kill": True}, {"book": False, "lifted": True}):
        payload = _analysis(**facts)
        saved = _read(payload)
        # The whole gate view: kinds, blocks with their detail sentences, summary and framing.
        assert saved["gates"] == payload["decision_view"]["gates"], facts
        assert saved["gates_note"] is None
        # The same-session copy (not sanitized) reads the same as the stored copy.
        held = saved_run_view.attach_saved_run_view(payload["detail_view"])
        assert held["saved_run_view"] == saved, facts
        assert "saved_run_view" not in payload["detail_view"], "nothing is added to what is held"


def test_a_saved_run_shows_what_its_record_holds_and_none_for_what_it_does_not(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _analysis()
    view = payload["decision_view"]
    saved = _read(payload)
    assert saved["schema_version"] == "saved_run_view.v1"
    assert set(saved) == {
        "schema_version",
        "gates",
        "gates_note",
        "disposition",
        "gate_action",
        "hard_blocks",
        "venue",
        "timeframe_label",
        "horizon_label",
        "time",
        "data",
        "range",
        "cost",
        "evidence",
    }
    # Held by the record, and equal to what the live view showed for the same analysis.
    assert saved["disposition"] == payload["frontend_display"]["disposition"] == "NO_TRADE"
    assert saved["venue"] == view["data"]["venue"] == "okx"
    assert saved["gate_action"] == payload["gate_result"]["action"] == "NO_TRADE"
    assert saved["hard_blocks"] == payload["gate_result"]["hard_blocks"]
    assert saved["timeframe_label"] == payload["timeframes"]["timeframe_label"] == "1H setup"
    assert saved["horizon_label"] == payload["timeframes"]["horizon_label"] == "~6H horizon"
    assert saved["data"] == {"data_source": "OKX_PUBLIC", "is_live_data": True}
    for name in ("assessed", "decision_band_frac", "in_band_frac", "up_frac", "down_frac"):
        assert saved["range"][name] == view["range"][name], name
    assert saved["range"]["meaning"] == view["range"]["meaning"] == decision_view.RANGE_MEANING
    assert saved["range"]["explanation"] == view["range"]["explanation"] == PROBABILITY_EXPLANATION
    assert saved["cost"] == {
        "round_trip_cost_frac": view["cost"]["round_trip_cost_frac"],
        "label": decision_view.COST_LABEL,
    }
    evidence = saved["evidence"]
    assert (
        evidence["level"]
        == MODEL_READINESS_COPY
        == (payload["frontend_display"]["model_readiness_label"])
    )
    assert evidence["probability_type"] == view["range"]["evidence_level"]
    assert evidence["calibration_status"] == view["evidence"]["calibration_status"]
    assert evidence["reliability_status"] == view["evidence"]["reliability_status"]
    assert evidence["directional_evidence_hold"] is False
    # Not held by the record: named, and None. The live view had them.
    assert saved["time"] == {"reference_close_utc": None, "horizon_end_utc": None}
    assert view["time"]["reference_close_utc"] and view["time"]["horizon_end_utc"]
    assert evidence["skill_verdict"] is None and evidence["resolved_outcomes"] is None
    assert view["evidence"]["skill_verdict"] == "INSUFFICIENT_EVIDENCE"
    stored = _stored(payload)
    assert "skill_evidence" not in stored and "decision_view" not in stored
    assert "saved_run_view" not in stored, "the view is never stored"


def test_the_disposition_is_the_one_the_live_analysis_showed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The older gate brief showed the brief's own action: NO_TRADE under the kill switch, where
    the view said ABORT. The saved view shows what the live analysis showed."""

    kill = _analysis(kill=True)
    assert kill["decision_brief"]["action"] == "NO_TRADE"
    assert _read(kill)["disposition"] == kill["frontend_display"]["disposition"] == "ABORT"
    assert _read(kill)["gate_action"] == "ABORT"
    assert _read(kill)["hard_blocks"] == ["KILL_SWITCH", "SKILL_NOT_DEMONSTRATED"]
    # A gate that passed (SYNTHETIC: the evidence gate lifted): the score's disposition.
    clear = _analysis(lifted=True)
    assert clear["gate_result"]["hard_gate_passed"] is True
    saved = _read(clear)
    assert saved["disposition"] == clear["frontend_display"]["disposition"]
    assert saved["disposition"] == clear["score_stack"]["disposition"]
    assert saved["gates"]["blocked"] is False and saved["hard_blocks"] == []
    assert saved["gate_action"] == clear["gate_result"]["action"]
    assert saved["gates"]["summary"] == gate_kinds.NO_HARD_GATE


def test_a_saved_run_shows_no_percentage_the_live_view_withheld(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Precedence 1 of the view (data that cannot support an assessment) holds for a saved run:
    the same facts, read from the record, withhold the same range."""

    payload = _analysis(provider_status="UNAVAILABLE")
    assert payload["decision_view"]["state"] == "INVALID_OR_UNAVAILABLE_DATA"
    saved = _read(payload)
    assert saved["range"]["assessed"] is False
    for name in ("in_band_frac", "up_frac", "down_frac", "explanation"):
        assert saved["range"][name] is None, name
    assert saved["range"]["meaning"] == decision_view.NOT_ASSESSED
    for block in ("EPISTEMIC_VOID", "PROVIDER_DEGRADED"):
        stored = _stored(_analysis())
        stored["invalidation_detail"] = {"hard_blocks": [block], "hard_gate_passed": False}
        assert saved_run_view.build_saved_run_view(stored)["range"]["assessed"] is False, block
    # The provider's own stored status withholds it too, whatever the stored gate result says
    # or fails to say (the live view reads both: decision_view._data_state).
    for status in ("UNAVAILABLE", "QUARANTINED", None, 5):
        for gate in ({"hard_blocks": [], "hard_gate_passed": True}, "not a gate result"):
            stored = _stored(_analysis())
            stored["data_quality_detail"]["provider_state"]["status"] = status
            stored["invalidation_detail"] = gate
            withheld = saved_run_view.build_saved_run_view(stored)["range"]
            assert withheld["assessed"] is False and withheld["up_frac"] is None, (status, gate)
    for status in ("OK", "DEGRADED"):
        stored = _stored(_analysis())
        stored["data_quality_detail"]["provider_state"]["status"] = status
        assert saved_run_view.build_saved_run_view(stored)["range"]["assessed"] is True, status


def test_every_sentence_of_the_analysis_reads_the_liquidity_state_the_gate_judged() -> None:
    """Owner ruling G2, through the real service. The same block, LIQUIDITY_NOT_VIABLE, beside
    the evidence gate: measured (too little depth) it is a risk gate in the view, the stack, the
    blocking reasons, the plan's reason and the forced token's note; on a missing order book it is
    a data gate in each of them, and none calls it a finding. A saved run reads the same."""

    thin, missing = _analysis(thin=True), _analysis(book=False)
    blocks = ["LIQUIDITY_NOT_VIABLE", "SKILL_NOT_DEMONSTRATED"]
    for payload in (thin, missing):
        assert payload["gate_result"]["hard_blocks"] == blocks
        assert payload["gate_result"]["risk_guard_applied"] is True
        assert payload["score_stack"]["disposition"] == "ELEVATED_RISK_AVOID"
    assert (
        thin["liquidity_state"]["status"] == "OK" and missing["liquidity_state"]["status"] != "OK"
    )

    def sentences(payload: dict) -> dict[str, object]:
        synthesis = payload["decision_synthesis"]
        return {
            "risk": payload["decision_view"]["gates"]["risk_gate_active"],
            "summary": payload["decision_view"]["gates"]["summary"],
            "check": synthesis["actionability_stack"][3]["plain_english"],
            "reason": payload["frontend_display"]["blocking_reasons"][0]["headline"],
            "plan": synthesis["trade_plan_skeleton"]["disabled_reason"],
            "brief": payload["decision_brief"]["state_summary"].rsplit(" is ", 1)[1],
            "key": payload["decision_brief"]["key_reasons"][1],
            "saved": _read(payload)["gates"]["summary"],
        }

    measured = "A risk gate is active: Liquidity is not viable. The evidence gate is active too: "
    unmeasured = (
        "A system or data gate is active: Liquidity could not be measured. The evidence gate is "
        "active too: "
    )
    evidence = "directional skill is not established for this model and timeframe."
    assert sentences(thin) == {
        "risk": True,
        "summary": measured + evidence,
        "check": measured + evidence,
        "reason": "Liquidity is not viable",
        "plan": "The elevated-risk disposition disables scenario planning.",
        "brief": "ELEVATED_RISK_AVOID.",
        "key": "Backend disposition: ELEVATED_RISK_AVOID.",
        "saved": measured + evidence,
    }
    assert sentences(missing) == {
        "risk": False,
        "summary": unmeasured + evidence,
        "check": unmeasured + evidence,
        "reason": "Liquidity could not be measured",
        "plan": unmeasured + evidence,
        "brief": "ELEVATED_RISK_AVOID (not forced by a risk gate).",
        "key": "Backend disposition: ELEVATED_RISK_AVOID (not forced by a risk gate).",
        "saved": unmeasured + evidence,
    }


def test_the_sentences_are_built_from_stored_facts_never_from_stored_sentences(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A run saved before the gate framing existed stores a summary with the forced token alone.
    Its view is the same as a new run's: nothing is read from a sentence the run stored."""

    payload = _analysis()
    new = _stored(payload)
    old = deepcopy(new)
    brief = old["decision_brief"]
    for name in ("state_summary", "risk_note", "disclaimer"):
        brief[name] = f"AN OLD STORED SENTENCE ({name}) ELEVATED_RISK_AVOID"
    for name in ("watchlist_triggers", "invalidation_conditions", "hard_blockers"):
        brief[name] = ["AN OLD STORED LINE"]
    assert saved_run_view.build_saved_run_view(old) == saved_run_view.build_saved_run_view(new)
    assert "OLD STORED" not in json.dumps(saved_run_view.build_saved_run_view(old))
    # The evidence level is the stored token's sentence, and a type this build does not know
    # gets no sentence written for it.
    other = deepcopy(new)
    other["decision_brief"].update(probability_type="A_NEW_TYPE", model_readiness="MEASURED")
    saved = saved_run_view.build_saved_run_view(other)
    assert saved["evidence"]["level"] is None and saved["range"]["explanation"] is None
    assert saved["evidence"]["probability_type"] == "A_NEW_TYPE"


def test_the_hold_a_run_stored_is_read_back(monkeypatch: pytest.MonkeyPatch) -> None:
    stored = _stored(_analysis())
    stored["invalidation_detail"]["directional_evidence_hold"] = {"active": True}
    assert saved_run_view.build_saved_run_view(stored)["evidence"]["directional_evidence_hold"]


# What a stored `invalidation_detail` can hold that is not a gate result as the gates write it.
# Framed anyway, a number or a boolean for `hard_blocks` would raise (the detail route would answer
# 500), and a string would read as one block a character: a framing that contradicts the record.
# An absent or None `hard_blocks` is not among them: it reads as no blocks.
MALFORMED_GATE_RESULTS = [
    pytest.param(None, id="none"),
    pytest.param(5, id="a-number"),
    pytest.param(True, id="a-boolean"),
    pytest.param("NO_TRADE", id="a-string"),
    pytest.param(["TAIL_RISK_BREACH"], id="a-list"),
    pytest.param({"hard_blocks": 5, "hard_gate_passed": False}, id="hard-blocks-a-number"),
    pytest.param({"hard_blocks": True}, id="hard-blocks-a-boolean"),
    pytest.param({"hard_blocks": "TAIL_RISK_BREACH"}, id="hard-blocks-a-string"),
    pytest.param({"hard_blocks": {"TAIL_RISK_BREACH": True}}, id="hard-blocks-a-mapping"),
    pytest.param({"hard_blocks": 0, "hard_gate_passed": False}, id="hard-blocks-zero"),
    pytest.param({"hard_blocks": False}, id="hard-blocks-false"),
    pytest.param({"hard_blocks": ""}, id="hard-blocks-an-empty-string"),
    pytest.param({"hard_blocks": {}}, id="hard-blocks-an-empty-mapping"),
    pytest.param({"hard_blocks": [None]}, id="a-none-entry"),
    pytest.param({"hard_blocks": ["TAIL_RISK_BREACH", 7]}, id="a-number-entry"),
    pytest.param({"hard_blocks": [["TAIL_RISK_BREACH"]]}, id="a-list-entry"),
    pytest.param({"hard_blocks": [{"block": "TAIL_RISK_BREACH"}]}, id="a-mapping-entry"),
    pytest.param(
        {"hard_blocks": 5, "action": "NO_TRADE", "added_later": {"deep": [None, 1.5]}},
        id="an-action-and-extra-keys",
    ),
]
# A gate result with no `hard_blocks`, or with None there: no blocks.
NO_BLOCKS_GATE_RESULTS = [
    pytest.param({}, id="an-empty-gate-result"),
    pytest.param({"hard_blocks": None}, id="hard-blocks-none"),
    pytest.param({"hard_gate_passed": True, "action": "ALLOW"}, id="absent-and-passed"),
    pytest.param({"hard_gate_passed": False}, id="absent-and-not-passed"),
    pytest.param({"hard_blocks": None, "hard_gate_passed": False}, id="none-and-not-passed"),
    pytest.param({"action": "ABORT"}, id="absent-and-aborted"),
    pytest.param({"hard_blocks": None, "risk_guard_applied": True}, id="none-and-a-risk-guard"),
    pytest.param(
        {"action": None, "forced_score_disposition": None, "added_later": {"deep": [None, 1.5]}},
        id="absent-with-none-values-and-extra-keys",
    ),
]


@pytest.mark.parametrize("gate", MALFORMED_GATE_RESULTS)
def test_a_malformed_stored_gate_result_is_never_framed_and_the_view_says_so(
    monkeypatch: pytest.MonkeyPatch, gate: object
) -> None:
    """Review finding D5: no 500, and no framing that could contradict the record. The view says
    that no gate result can be read, shows no disposition, and still shows what else is held."""

    stored = _stored(_analysis())
    stored["invalidation_detail"] = gate
    before = deepcopy(stored)
    read = saved_run_view.attach_saved_run_view(stored)
    assert stored == before and "saved_run_view" not in stored, "the stored detail is not changed"
    saved = read["saved_run_view"]
    assert saved["gates"] is None and saved["disposition"] is None
    assert saved["gate_action"] is None and saved["hard_blocks"] is None
    assert saved["gates_note"] == (
        "No gate result can be read from this saved analysis, so no gate framing is shown."
    )
    assert saved["evidence"]["directional_evidence_hold"] is None
    assert saved["range"]["up_frac"] is not None and saved["venue"] == "okx"
    assert {key: value for key, value in read.items() if key != "saved_run_view"} == before


@pytest.mark.parametrize("gate", NO_BLOCKS_GATE_RESULTS)
def test_an_absent_or_none_hard_blocks_is_framed_as_no_blocks(
    monkeypatch: pytest.MonkeyPatch, gate: dict
) -> None:
    stored = _stored(_analysis())
    stored["invalidation_detail"] = gate
    saved = saved_run_view.attach_saved_run_view(stored)["saved_run_view"]
    view = saved["gates"]
    liquidity = stored["liquidity_execution_detail"]["liquidity_state"]
    assert view == gate_kinds.build_gate_view(gate, liquidity=liquidity)
    assert view["blocks"] == [] and view["kinds"] == [] and view["risk_gate_active"] is False
    # No block is named, so no risk gate is: the gates' flag alone words no finding.
    assert view["framing"] == gate_kinds.NOT_A_MARKET_CALL
    blocked = gate.get("hard_gate_passed") is False or gate.get("action") == "ABORT"
    assert view["blocked"] is blocked
    assert view["summary"] == (gate_kinds.UNNAMED_HARD_GATE if blocked else gate_kinds.NO_HARD_GATE)
    assert saved["gates_note"] is None


def test_a_tuple_of_blocks_is_not_a_stored_list_of_blocks() -> None:
    for blocks in (("TAIL_RISK_BREACH",), ()):
        stored = {"invalidation_detail": {"hard_blocks": blocks}}
        assert saved_run_view.build_saved_run_view(stored)["gates"] is None, blocks


@pytest.mark.parametrize(
    "liquidity", [None, 5, "x", [], {"liquidity_state": 5}, {"liquidity_state": ["OK"]}]
)
def test_a_malformed_stored_liquidity_state_never_fails_and_never_words_a_finding(
    liquidity: object,
) -> None:
    gate = {"hard_blocks": ["LIQUIDITY_NOT_VIABLE", "SKILL_NOT_DEMONSTRATED"]}
    stored = {"invalidation_detail": gate, "liquidity_execution_detail": liquidity}
    view = saved_run_view.attach_saved_run_view(stored)["saved_run_view"]["gates"]
    assert view["summary"].startswith(
        "A system or data gate is active: Liquidity could not be measured."
    )
    assert view["risk_gate_active"] is False


@pytest.mark.parametrize(
    "damaged",
    [
        "probability_detail",
        "liquidity_execution_detail",
        "data_quality_detail",
        "decision_brief",
        "score_detail",
        "invalidation_detail",
    ],
)
@pytest.mark.parametrize("value", [None, 5, "x", [], [{}], {"horizons": 5}, {"H_primary": []}])
def test_every_stored_part_can_be_missing_or_damaged(
    monkeypatch: pytest.MonkeyPatch, damaged: str, value: object
) -> None:
    """Each part of the stored detail the view reads, replaced by what is not a mapping, or by a
    mapping of the wrong shape, and removed: the view is built, and what it cannot read is None."""

    whole = _stored(_analysis())
    intact = saved_run_view.build_saved_run_view(whole)
    for stored in ({**whole, damaged: value}, {k: v for k, v in whole.items() if k != damaged}):
        saved = saved_run_view.attach_saved_run_view(stored)["saved_run_view"]
        assert set(saved) == set(intact)
        json.dumps(saved, allow_nan=False)
    assert saved_run_view.build_saved_run_view({})["gates_note"] == (
        saved_run_view.GATES_NOT_READABLE
    )


def test_a_value_of_the_wrong_type_reads_as_not_kept() -> None:
    stored = {
        "invalidation_detail": {**EVIDENCE_GATE, "action": 7},
        "probability_detail": {
            "horizons": {"H_primary": {"p_up_frac": "0.4", "p_down_frac": True}}
        },
        "liquidity_execution_detail": {"execution_realism": {"round_trip_cost_frac": None}},
        "data_quality_detail": {
            "provider_state": {"status": "OK", "active_provider": 3},
            "data_quality": {"data_source": "", "is_live_data": "yes"},
        },
        "decision_brief": {"timeframe_label": "1H setup", "calibration_status": 0},
    }
    saved = saved_run_view.build_saved_run_view(stored)
    assert saved["disposition"] is None and saved["venue"] is None
    assert saved["gate_action"] is None and saved["hard_blocks"] == ["SKILL_NOT_DEMONSTRATED"]
    assert saved["timeframe_label"] == "1H setup" and saved["horizon_label"] is None
    assert saved["data"] == {"data_source": None, "is_live_data": None}
    assert saved["range"]["up_frac"] is None and saved["range"]["down_frac"] is None
    assert saved["range"]["in_band_frac"] is None and saved["cost"]["round_trip_cost_frac"] is None
    assert saved["evidence"]["calibration_status"] is None
    assert saved["gates"]["summary"].startswith("Evidence gate: ")


@pytest.mark.parametrize("detail", [None, 5, 1.5, True, "text", b"bytes", [], [{}], object()])
def test_a_detail_that_is_not_a_mapping_is_returned_as_it_is(detail: object) -> None:
    assert saved_run_view.attach_saved_run_view(detail) is detail


def test_reading_never_raises_even_when_building_the_view_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Unreadable(dict):
        def get(self, *_args: object) -> object:
            raise RuntimeError("unreadable")

    unreadable = Unreadable(invalidation_detail=dict(EVIDENCE_GATE))
    assert saved_run_view.attach_saved_run_view(unreadable) is unreadable
    nested = {"invalidation_detail": Unreadable(hard_blocks=[])}
    assert saved_run_view.attach_saved_run_view(nested) is nested

    def failing(*_args: object, **_facts: object) -> dict:
        raise RuntimeError("framing failed")

    monkeypatch.setattr(saved_run_view, "build_gate_view", failing)
    stored = {"invalidation_detail": dict(EVIDENCE_GATE)}
    assert saved_run_view.attach_saved_run_view(stored) is stored


def test_no_field_of_the_view_is_named_as_the_sanitizer_masks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    saved = _read(_analysis(book=False))
    assert sanitize_for_export({"saved_run_view": deepcopy(saved)})["saved_run_view"] == saved


class _Durable:
    """A durable store holding one run, as a stored JSON row reads back."""

    def __init__(self, stored: dict) -> None:
        self.stored = stored

    def get_run_detail(self, run_id: str, *, prediction_origin: str) -> dict | None:
        del prediction_origin
        return json.loads(json.dumps(self.stored)) if run_id == "durable-run" else None


@pytest.mark.parametrize("gate", [*MALFORMED_GATE_RESULTS, *NO_BLOCKS_GATE_RESULTS])
def test_the_detail_route_answers_200_for_whatever_gate_result_a_stored_run_holds(
    gate: object,
) -> None:
    stored = {"run_id": "durable-run", "invalidation_detail": gate, "sections": {"score": "x"}}
    client = make_client()
    client.app.state.persistence_repository = _Durable(stored)
    login(client)
    response = client.get("/v1/analyze/detail/durable-run")
    assert response.status_code == 200
    answer = response.json()
    assert {key: value for key, value in answer.items() if key != "saved_run_view"} == stored
    assert answer["saved_run_view"] == saved_run_view.build_saved_run_view(stored)
    assert (answer["saved_run_view"]["gates"] is None) is (
        answer["saved_run_view"]["gates_note"] is not None
    )
