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
from tests.fixtures.market_data import FIXED_NOW, make_order_book, make_snapshot

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
        # One entry differs, as it must (minor m4): the evidence gate's. The live analysis holds
        # the verdict and gives the backend's reason for it; the record does not store the
        # verdict, so the reopened run gives the fixed sentence and says so.
        live = payload["decision_view"]["gates"]
        for mine, theirs in zip(saved["gates"]["blocks"], live["blocks"], strict=True):
            if mine["kind"] != "EVIDENCE":
                assert mine == theirs, facts
                continue
            assert {**mine, "detail": None} == {**theirs, "detail": None}, facts
            assert mine["detail"] == gate_kinds.SAVED_EVIDENCE_GATE_DETAIL, facts
            reasons = payload["frontend_display"]["blocking_reasons"]
            (reason,) = [entry for entry in reasons if entry["code"] == "SKILL_NOT_DEMONSTRATED"]
            assert theirs["detail"] == reason["detail"], "the live entry is the backend's reason"
        rest = {key: value for key, value in saved["gates"].items() if key != "blocks"}
        assert rest == {key: value for key, value in live.items() if key != "blocks"}, facts
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
        "caveat": None,
    }
    assert view["cost"]["caveat"] is None, "slippage was estimated: the cost has no caveat"
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


def _damaged(change) -> dict:
    """The evidence-only analysis as it is stored, with one thing about the record damaged."""

    stored = _stored(_analysis())
    change(stored)
    return stored


def _view_of(name: str) -> dict:
    return saved_run_view.build_saved_run_view(_damaged(DAMAGED_RECORDS[name]))


# A gate result that does not say whether the gates passed: no block, no ABORT, and no flag that
# is True or False. The gates write no such result (the re-review's minor 1 and its siblings).
UNDECIDED_GATES = {
    "gate_empty": {},
    "gate_blocks_empty_alone": {"hard_blocks": []},
    "gate_blocks_none_alone": {"hard_blocks": None},
    "gate_action_alone": {"action": "NO_TRADE"},
    "gate_forced_token_alone": {"forced_score_disposition": "ELEVATED_RISK_AVOID"},
    "gate_risk_guard_alone": {"hard_blocks": None, "risk_guard_applied": True},
    "gate_skill_guard_and_action": {"skill_guard_applied": True, "action": "NO_TRADE"},
    "gate_none_values_and_extra_keys": {
        "action": None,
        "forced_score_disposition": None,
        "added_later": {"deep": [None, 1.5]},
    },
    "gate_flag_none": {"hard_gate_passed": None, "hard_blocks": []},
    "gate_flag_a_string": {"hard_gate_passed": "true", "action": "ALLOW"},
    "gate_flag_a_number": {"hard_gate_passed": 1},
}
UNDECIDED_GATE_RESULTS = [pytest.param(gate, id=name) for name, gate in UNDECIDED_GATES.items()]
# Stored records that are old, damaged or odd (the reviewer's cases, and their siblings): each
# is read back without an error and without a line that contradicts the record.
DAMAGED_RECORDS = {
    "passed_true_with_blocks": lambda d: d["invalidation_detail"].update(hard_gate_passed=True),
    "passed_true_and_no_blocks": lambda d: d["invalidation_detail"].update(
        hard_gate_passed=True, hard_blocks=[]
    ),
    "passed_true_no_blocks_no_score": lambda d: (
        d.pop("score_detail"),
        d["invalidation_detail"].update(hard_gate_passed=True, hard_blocks=[]),
    ),
    "blocks_empty_but_not_passed": lambda d: d["invalidation_detail"].update(hard_blocks=[]),
    "action_missing": lambda d: d["invalidation_detail"].pop("action"),
    "action_is_the_forced_token": lambda d: d["invalidation_detail"].update(
        action="ELEVATED_RISK_AVOID"
    ),
    "liquidity_execution_absent": lambda d: d.pop("liquidity_execution_detail"),
    "data_quality_absent": lambda d: d.pop("data_quality_detail"),
    "provider_state_absent": lambda d: d["data_quality_detail"].pop("provider_state"),
    "probability_absent": lambda d: d.pop("probability_detail"),
    "brief_absent": lambda d: d.pop("decision_brief"),
    "gate_absent": lambda d: d.pop("invalidation_detail"),
    # Minor m1 (the exact-final review's three shapes): the record lost its guard flags, and in
    # two of them the stored action is the forced token itself.
    "m1_evidence_block_action_is_the_token_no_flags": lambda d: d.__setitem__(
        "invalidation_detail",
        {
            "hard_gate_passed": False,
            "hard_blocks": ["SKILL_NOT_DEMONSTRATED"],
            "action": "ELEVATED_RISK_AVOID",
        },
    ),
    "m1_passed_no_flags_forced_token_still_stored": lambda d: d.__setitem__(
        "invalidation_detail",
        {
            "hard_gate_passed": True,
            "hard_blocks": [],
            "action": "NO_TRADE",
            "forced_score_disposition": "ELEVATED_RISK_AVOID",
        },
    ),
    "m1_unmeasured_liquidity_block_action_is_the_token_no_flags": lambda d: (
        d.__setitem__(
            "invalidation_detail",
            {
                "hard_gate_passed": False,
                "hard_blocks": ["LIQUIDITY_NOT_VIABLE"],
                "action": "ELEVATED_RISK_AVOID",
            },
        ),
        d["liquidity_execution_detail"].__setitem__(
            "liquidity_state",
            {
                "status": "DEGRADED",
                "spread_frac": None,
                "top_depth_quote": 0.0,
                "warning": "Order book unavailable.",
            },
        ),
    ),
    # A stored gate result that does not say whether the gates passed (the re-review's minor 1):
    # the rest of the record, its score detail among it, is intact.
    **{
        name: (lambda d, gate=gate: d.__setitem__("invalidation_detail", deepcopy(gate)))
        for name, gate in UNDECIDED_GATES.items()
    },
}


def test_the_disposition_of_a_saved_run_is_read_from_its_whole_gate_result() -> None:
    """Review finding 4. A stored gate result whose flag says passed beside a stored block used to
    show the score's forced token alone ("ELEVATED_RISK_AVOID"). The view now reads whether a
    hard gate is active from the whole gate result, and the forced token never stands alone."""

    token, note = "ELEVATED_RISK_AVOID", "ELEVATED_RISK_AVOID (not forced by a risk gate)"
    whole = saved_run_view.build_saved_run_view(_stored(_analysis()))
    assert (whole["disposition"], whole["gate_action"]) == ("NO_TRADE", "NO_TRADE")

    flagged = _view_of("passed_true_with_blocks")
    assert flagged["gates"]["summary"].startswith("Evidence gate: ")
    assert flagged["disposition"] == "NO_TRADE", "the gate is active: its action, not the score's"

    # No block and a flag that says passed: the record holds the score's token and the gate's own
    # note that the evidence gate forced it. It is shown with the note, never alone.
    passed = _damaged(DAMAGED_RECORDS["passed_true_and_no_blocks"])
    assert passed["score_detail"]["disposition"] == token
    assert passed["invalidation_detail"]["skill_guard_applied"] is True
    assert saved_run_view.build_saved_run_view(passed)["disposition"] == note
    # The same record without its two guard flags still holds the token the gates recorded as
    # forced: that alone says a gate forced it, and the note stays (minor m1: the code used to
    # read the flags only, and this test dropped all three at once, which hid it).
    for flag in ("skill_guard_applied", "risk_guard_applied"):
        passed["invalidation_detail"].pop(flag, None)
    assert passed["invalidation_detail"]["forced_score_disposition"] == token
    assert saved_run_view.build_saved_run_view(passed)["disposition"] == note
    # Without that either, nothing in the record says a gate forced it: the score's own reading,
    # which is a risk reading of the score and stands as the live analysis shows it.
    passed["invalidation_detail"].pop("forced_score_disposition")
    assert saved_run_view.build_saved_run_view(passed)["disposition"] == token
    # A stored action that is the forced token itself, under the evidence gate: noted too.
    forced = _view_of("action_is_the_forced_token")
    assert (forced["disposition"], forced["gate_action"]) == (note, note)
    # Under a measured risk gate the token is a risk finding: it stands alone.
    risk = _damaged(
        lambda d: d["invalidation_detail"].update(
            action=token, hard_blocks=["TAIL_RISK_BREACH", "SKILL_NOT_DEMONSTRATED"]
        )
    )
    assert saved_run_view.build_saved_run_view(risk)["disposition"] == token

    # The liquidity gate behind the token is read with the liquidity state the record stores: a
    # measured spread makes it a risk finding (the token stands), an unmeasured book does not.
    def under_the_liquidity_gate(state: dict) -> str:
        record = _damaged(
            lambda d: (
                d["invalidation_detail"].update(action=token, hard_blocks=["LIQUIDITY_NOT_VIABLE"]),
                d["liquidity_execution_detail"].update(liquidity_state=state),
            )
        )
        return saved_run_view.build_saved_run_view(record)["disposition"]

    assert under_the_liquidity_gate({"status": "OK", "spread_frac": 0.09}) == token
    assert under_the_liquidity_gate({"status": "DEGRADED", "spread_frac": None}) == note
    # Without a score, a passed gate has no disposition to show; without an action, a blocked one.
    for name in ("passed_true_no_blocks_no_score", "action_missing"):
        assert _view_of(name)["disposition"] is None, name
    unnamed = _view_of("blocks_empty_but_not_passed")
    assert unnamed["gates"]["summary"] == gate_kinds.UNNAMED_HARD_GATE
    assert unnamed["disposition"] == "NO_TRADE"


def test_a_saved_run_says_its_cost_is_fees_only_when_its_record_supports_it() -> None:
    """The re-review's minor 2, for a reopened run. The caveat is read from the execution state
    the record stores, as the live view read it. A record that does not hold that state, or holds
    one that does not support the sentence, shows the cost it holds and no caveat: it says
    nothing it cannot know."""

    assert _read(_analysis())["cost"]["caveat"] is None, "slippage was estimated"
    payload = _analysis(book=False)
    live = payload["decision_view"]["cost"]
    assert live["caveat"] == decision_view.COST_FEES_ONLY
    stored = _stored(payload)
    saved = saved_run_view.build_saved_run_view(stored)["cost"]
    assert saved["caveat"] == decision_view.COST_FEES_ONLY
    assert saved["round_trip_cost_frac"] == live["round_trip_cost_frac"] == 0.002
    execution = "execution_realism"
    unsupported = {
        "no liquidity and execution detail": lambda d: d.pop("liquidity_execution_detail"),
        "no execution state": lambda d: d["liquidity_execution_detail"].pop(execution),
        "an execution state that is a word": lambda d: d["liquidity_execution_detail"].update(
            execution_realism="DEGRADED"
        ),
        "no status": lambda d: d["liquidity_execution_detail"][execution].pop("status"),
        "no fee": lambda d: d["liquidity_execution_detail"][execution].pop("taker_fee_frac"),
        "slippage counted": lambda d: d["liquidity_execution_detail"][execution].update(
            slippage_frac=0.001
        ),
        "another cost": lambda d: d["liquidity_execution_detail"][execution].update(
            round_trip_cost_frac=0.0041
        ),
    }
    for name, change in unsupported.items():
        lost = deepcopy(stored)
        change(lost)
        assert saved_run_view.build_saved_run_view(lost)["cost"]["caveat"] is None, name


M1_SHAPES = [name for name in DAMAGED_RECORDS if name.startswith("m1_")]


@pytest.mark.parametrize("name", M1_SHAPES)
def test_the_forced_token_keeps_its_note_whatever_flags_the_record_lost(name: str) -> None:
    """The exact-final review's minor m1. "Forced" was decided from the two guard flags alone, so
    a record that lost them showed the forced token bare. A gate forced the token when a guard
    flag says so, when the gates recorded it as forced, or when a hard gate is simply active."""

    note = "ELEVATED_RISK_AVOID (not forced by a risk gate)"
    assert len(M1_SHAPES) == 3
    saved = _view_of(name)
    shown = [saved["disposition"], saved["gate_action"]]
    assert note in shown and "ELEVATED_RISK_AVOID" not in shown, shown
    assert saved["gates"]["risk_gate_active"] is False
    # Each of the three ways, alone, says a gate forced it; with none of them the score's own
    # token stands; and a risk gate with a measured finding stands behind a bare token.
    score = {"disposition": "ELEVATED_RISK_AVOID"}
    finding = gate_kinds.elevated_risk_is_a_risk_finding
    for gate in (
        {"skill_guard_applied": True},
        {"risk_guard_applied": True},
        {"forced_score_disposition": "ELEVATED_RISK_AVOID"},
        {"hard_blocks": ["SKILL_NOT_DEMONSTRATED"]},
        {"hard_gate_passed": False},
        {"action": "ABORT"},
    ):
        assert finding(gate, score, None) is False, gate
    unforced = ({}, {"hard_gate_passed": True, "hard_blocks": []}, {"forced_score_disposition": ""})
    for gate in unforced:
        assert finding(gate, score, None) is True, gate
    assert finding({"hard_blocks": ["TAIL_RISK_BREACH"], "risk_guard_applied": True}, score, None)


# Stored liquidity states that are absent or are not what the liquidity measure writes (the
# exact-final review's minor m2: the live analysis measured the order book and found too little
# depth, a risk gate). Each is put where the measured state was.
NOT_READABLE_LIQUIDITY = {
    "state_missing": lambda d: d["liquidity_execution_detail"].pop("liquidity_state"),
    "state_none": lambda d: d["liquidity_execution_detail"].update(liquidity_state=None),
    "state_a_word": lambda d: d["liquidity_execution_detail"].update(liquidity_state="OK"),
    "status_missing": lambda d: d["liquidity_execution_detail"]["liquidity_state"].pop("status"),
    "spread_is_text": lambda d: d["liquidity_execution_detail"]["liquidity_state"].update(
        spread_frac="0.095"
    ),
    "status_unknown": lambda d: d["liquidity_execution_detail"]["liquidity_state"].update(
        status="STALE"
    ),
    "degraded_with_a_spread": lambda d: d["liquidity_execution_detail"]["liquidity_state"].update(
        status="DEGRADED"
    ),
    "degraded_one_price": lambda d: d["liquidity_execution_detail"].update(
        liquidity_state={"status": "DEGRADED", "spread_frac": None, "best_bid": 100.0}
    ),
    "degraded_prices_as_text": lambda d: d["liquidity_execution_detail"].update(
        liquidity_state={
            "status": "DEGRADED",
            "spread_frac": None,
            "best_bid": "100",
            "best_ask": True,
        }
    ),
    "degraded_spread_absent": lambda d: d["liquidity_execution_detail"].update(
        liquidity_state={"status": "DEGRADED"}
    ),
    "whole_detail_missing": lambda d: d.pop("liquidity_execution_detail"),
}


@pytest.mark.parametrize("name", NOT_READABLE_LIQUIDITY)
def test_a_record_without_a_readable_liquidity_state_asserts_no_cause(name: str) -> None:
    """The exact-final review's minor m2. The live analysis measured its order book (a risk
    gate: liquidity is not viable). A reopened run whose stored liquidity state is absent or
    partial used to say that the order-book data were unavailable ("missing data"), or that the
    served book's spread was out of range: a cause the record does not show. It now names the
    gate and says only that the record holds no readable measurement: no cause, no finding, and
    no "missing data"."""

    payload = _analysis(thin=True)
    live = payload["decision_view"]["gates"]
    assert live["kinds"] == ["EVIDENCE", "RISK"] and "Liquidity is not viable" in live["summary"]
    stored = _stored(payload)
    assert saved_run_view.build_saved_run_view(stored)["gates"]["kinds"] == ["EVIDENCE", "RISK"]
    NOT_READABLE_LIQUIDITY[name](stored)
    saved = saved_run_view.build_saved_run_view(stored)
    gates = saved["gates"]
    assert gates["kinds"] == ["EVIDENCE", "NOT_READABLE"]
    assert gates["risk_gate_active"] is False and gates["framing"] == gate_kinds.NOT_A_MARKET_CALL
    assert gates["summary"] == (
        "The liquidity gate is active: this saved record does not hold a readable liquidity "
        "measurement. The evidence gate is active too: directional skill is not established for "
        "this model and timeframe."
    )
    (entry,) = [block for block in gates["blocks"] if block["block"] == "LIQUIDITY_NOT_VIABLE"]
    assert entry == {
        "block": "LIQUIDITY_NOT_VIABLE",
        "kind": "NOT_READABLE",
        "headline": "Liquidity gate",
        "detail": (
            "This saved record does not hold a readable liquidity measurement, so it cannot say "
            "whether liquidity was measured or what the gate found."
        ),
    }
    written = json.dumps(gates)
    for claim in ("missing data", "unavailable", "outside the range", "Liquidity is not viable"):
        assert claim not in written, claim
    assert "Liquidity could not be measured" not in written
    assert saved["disposition"] == "NO_TRADE"


@pytest.mark.parametrize("name", NOT_READABLE_LIQUIDITY)
def test_the_detail_route_answers_200_for_a_record_without_a_readable_liquidity_state(
    name: str,
) -> None:
    stored = {**_stored(_analysis(thin=True)), "run_id": "durable-run"}
    NOT_READABLE_LIQUIDITY[name](stored)
    client = make_client()
    client.app.state.persistence_repository = _Durable(stored)
    login(client)
    response = client.get("/v1/analyze/detail/durable-run")
    assert response.status_code == 200, name
    saved = response.json()["saved_run_view"]
    assert saved == saved_run_view.build_saved_run_view(stored)
    assert saved["gates"]["kinds"] == ["EVIDENCE", "NOT_READABLE"], name
    written = json.dumps(saved)
    assert "missing data" not in written and "Liquidity is not viable" not in written, name


def test_a_stored_liquidity_state_the_measure_writes_is_read_as_it_is() -> None:
    """The other side of minor m2: the three states the measure writes are read as before, and
    only a saved run can meet the unreadable one (a live analysis holds the measure's own)."""

    from crypto_probability_engine.detail import frontend_display
    from crypto_probability_engine.features.liquidity_depth import compute_liquidity_depth

    unreadable = frontend_display.STORED_LIQUIDITY_NOT_READABLE
    usable, refused = make_order_book(), make_order_book(bid=100.0, ask=400.0)
    for book in (None, usable, refused):
        state = json.loads(json.dumps(compute_liquidity_depth(book)))
        assert frontend_display.stored_liquidity_state(state) is state, state
    for state in (None, 5, "OK", [], {}, {"status": "OK"}, {"spread_frac": 0.01}):
        assert frontend_display.stored_liquidity_state(state) is unreadable, state
    # A state with no spread is the measure's only with the measure's own status beside it.
    prices = {"best_bid": 100.0, "best_ask": 400.0}
    for state in (
        {"spread_frac": None},
        {"spread_frac": None, **prices},
        {"status": "STALE", "spread_frac": None},
        {"status": "OK", "spread_frac": None, **prices},
        {"status": None, "spread_frac": None},
    ):
        assert frontend_display.stored_liquidity_state(state) is unreadable, state
    no_book = {"status": "DEGRADED", "spread_frac": None}
    for state in (no_book, {**no_book, **prices}):
        assert frontend_display.stored_liquidity_state(state) is state, state
    gate = {"hard_blocks": ["LIQUIDITY_NOT_VIABLE"], "hard_gate_passed": False}
    # The live builder is given the measure's state, never the stand-in: with no state at all it
    # still reads as before (no measurement: a data gate), so a live analysis is unaffected.
    live = gate_kinds.build_gate_view(gate, liquidity=None)
    assert live["kinds"] == ["SYSTEM_OR_DATA"]
    assert live["summary"] == "A system or data gate is active: Liquidity could not be measured."
    saved = gate_kinds.build_gate_view(gate, liquidity=unreadable)
    assert saved["kinds"] == ["NOT_READABLE"] and saved["risk_gate_active"] is False
    assert saved["summary"] == gate_kinds.LIQUIDITY_NOT_READABLE_SUMMARY
    assert saved["framing"] == gate_kinds.NOT_A_MARKET_CALL


def test_a_record_that_lost_a_part_shows_what_it_still_holds() -> None:
    """The same family. A record without its provider state still holds its percentages: they are
    shown, not called "not assessed". A record without its liquidity and execution state holds no
    cost and no band: those are None by themselves, and the percentages stand."""

    whole = saved_run_view.build_saved_run_view(_stored(_analysis()))
    for name in ("data_quality_absent", "provider_state_absent"):
        saved = _view_of(name)
        assert saved["range"]["assessed"] is True, name
        for value in ("in_band_frac", "up_frac", "down_frac", "meaning", "explanation"):
            assert saved["range"][value] == whole["range"][value] is not None, (name, value)
        assert saved["venue"] is None, name
    lost = _view_of("liquidity_execution_absent")
    assert lost["range"]["decision_band_frac"] is None
    assert lost["cost"]["round_trip_cost_frac"] is None
    assert lost["range"]["up_frac"] == whole["range"]["up_frac"]
    assert lost["gates"] == whole["gates"], "the evidence gate needs no liquidity state"


@pytest.mark.parametrize("name", DAMAGED_RECORDS)
def test_the_detail_route_answers_200_for_every_damaged_record(name: str) -> None:
    stored = {**_damaged(DAMAGED_RECORDS[name]), "run_id": "durable-run"}
    client = make_client()
    client.app.state.persistence_repository = _Durable(stored)
    login(client)
    response = client.get("/v1/analyze/detail/durable-run")
    assert response.status_code == 200, name
    saved = response.json()["saved_run_view"]
    assert saved == saved_run_view.build_saved_run_view(stored)
    for token in (saved["disposition"], saved["gate_action"]):
        assert token != "ELEVATED_RISK_AVOID", f"{name}: the forced token alone"
    if name in UNDECIDED_GATES:
        assert saved["gates"] is None and saved["disposition"] is None, name
        assert saved["gates_note"] == saved_run_view.GATES_NOT_READABLE, name
        assert "No hard gate is active." not in response.text, name


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
    for status in ("UNAVAILABLE", "QUARANTINED", ""):
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
# A gate result with no `hard_blocks`, or with None or an empty list there, that still says
# whether the gates passed (its flag, or an ABORT action): no blocks.
NO_BLOCKS_GATE_RESULTS = [
    pytest.param({"hard_gate_passed": True, "action": "ALLOW"}, id="absent-and-passed"),
    pytest.param({"hard_blocks": [], "hard_gate_passed": True}, id="empty-and-passed"),
    pytest.param({"hard_gate_passed": False}, id="absent-and-not-passed"),
    pytest.param({"hard_blocks": None, "hard_gate_passed": False}, id="none-and-not-passed"),
    pytest.param({"action": "ABORT"}, id="absent-and-aborted"),
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


@pytest.mark.parametrize("gate", UNDECIDED_GATE_RESULTS)
def test_a_gate_result_that_does_not_say_whether_the_gates_passed_is_not_read_as_passed(
    gate: dict,
) -> None:
    """The re-review's minor 1 (a regression of the correction before). A stored gate result that
    is empty, or carries no flag and no block, showed "No hard gate is active." and the score's
    forced token alone. It is not a gate result that passed: it is not framed at all, the view
    says no gate result can be read, and no disposition, action or block is made of it. The
    score detail is intact here, and its forced token is on no field of the view."""

    stored = _stored(_analysis())
    assert stored["score_detail"]["disposition"] == "ELEVATED_RISK_AVOID"
    stored["invalidation_detail"] = gate
    saved = saved_run_view.attach_saved_run_view(stored)["saved_run_view"]
    assert saved["gates"] is None
    assert saved["gates_note"] == saved_run_view.GATES_NOT_READABLE
    assert saved["disposition"] is None, "what the record does not hold is not made up"
    assert saved["gate_action"] is None and saved["hard_blocks"] is None
    assert saved["evidence"]["directional_evidence_hold"] is None
    written = json.dumps(saved)
    assert gate_kinds.NO_HARD_GATE not in written and "ELEVATED_RISK_AVOID" not in written
    assert "NO_TRADE" not in written, "no second disposition beside the one that is not kept"
    # Everything else the record holds is still shown.
    assert saved["range"]["up_frac"] is not None and saved["venue"] == "okx"
    # The same result with its flag reads as the gates wrote it.
    flagged = {**gate, "hard_gate_passed": True, "hard_blocks": []}
    passed = saved_run_view.build_saved_run_view({**stored, "invalidation_detail": flagged})
    assert passed["gates"]["summary"] == gate_kinds.NO_HARD_GATE
    flagged = {**gate, "hard_gate_passed": False}
    blocked = saved_run_view.build_saved_run_view({**stored, "invalidation_detail": flagged})
    assert blocked["gates"]["blocked"] is True


def test_the_disposition_itself_is_the_scores_only_for_a_result_that_says_it_passed() -> None:
    """The reviewer's own smallest fix, kept beside the rule above: whatever reaches it, the
    disposition is the score's token only when the stored flag is True, the gate action while a
    gate is active, and nothing for a result that says neither."""

    score = {"disposition": "CONSTRUCTIVE"}
    disposition = saved_run_view._disposition
    for gate in UNDECIDED_GATES.values():
        assert disposition(gate, score, None) is None, gate
    assert disposition({"hard_gate_passed": True}, score, None) == "CONSTRUCTIVE"
    assert disposition({"hard_gate_passed": False, "action": "NO_TRADE"}, score, None) == "NO_TRADE"
    assert disposition({"hard_gate_passed": True, "action": "ABORT"}, score, None) == "ABORT"
    assert disposition(None, score, None) is None


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
    # Minor m2: no cause is read from a state the record does not hold. The gate is named, and
    # the record says only that it holds no readable measurement.
    assert view["summary"] == (
        "The liquidity gate is active: this saved record does not hold a readable liquidity "
        "measurement. The evidence gate is active too: directional skill is not established for "
        "this model and timeframe."
    )
    assert view["kinds"] == ["EVIDENCE", "NOT_READABLE"]
    assert view["risk_gate_active"] is False
    assert view["framing"] == gate_kinds.NOT_A_MARKET_CALL


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


@pytest.mark.parametrize(
    "gate", [*MALFORMED_GATE_RESULTS, *NO_BLOCKS_GATE_RESULTS, *UNDECIDED_GATE_RESULTS]
)
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
