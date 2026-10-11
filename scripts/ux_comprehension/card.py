"""The owner's UX comprehension check for the DecisionView (governing plan §23 "UX"; §14).

Plan §23: UX is "PASS only when predefined owner-task scenarios distinguish: invalid data;
unvalidated model; accepted forecast; directional permission; saved/unsaved state." This builds
those scenarios and the owner's card (docs/runbooks/UX_COMPREHENSION_CHECK.md) from the product's
own code, so the card cannot drift from what the default screen shows:
- each scenario's gate result is the real gates' (gates/composite.py), its view the real builder's
  (detail/decision_view.py) and its synthesis the real one's (detail/decision_synthesis.py), from
  controlled inputs. The two accepted states are unreachable today (both acceptance registries
  are empty), so they are built with the registries filled for that build only, restored at once,
  and the card marks them SYNTHETIC. The invalid-data state is unreachable today as well: on
  live data the venue selection refuses what the view would call invalid, and the analysis ends
  in an error (the venue selection). The card marks it SYNTHETIC too;
- each scenario's block is the Decision view exactly as the detail panel shows it: the real
  frontend's own function (frontend/app.js renderDecisionViewSection, and everything it calls)
  runs under node and its output is printed in order, nothing added and nothing left out;
- the three places the screen speaks of storage are shown as the screen shows them: the badge at
  the top of the page (updatePersistenceStatus), the Decision view's Storage row once the screen
  holds the analysis's save receipt (the backend's own receipt, api/save_receipt.py, in the
  frontend's own words, saveReceiptText), and Overview's "Storage when requested" row;
- the numbers are illustrative fixtures, never market data, and nothing here reads a database.

The questions ask what a screen MEANS, in words the screen does not use: none can be answered by
finding its words on the card (a test refuses a question whose distinctive words are on an
analysis). The answer key is computed from each analysis's payload and receipt (`answers`), never
typed: a scenario below holds inputs only. Two tempting misreadings are answerable and wrong on
every analysis: taking the gates' disposition for a market call, and taking the badge or the
request-time row for the save receipt (the tests model both readers).

    python scripts/ux_comprehension/card.py --write   # regenerate the card
    python scripts/ux_comprehension/card.py --check   # exit 1 if the committed card differs

tests/frontend/test_ux_comprehension_card.py checks all of the above, that each block is what the
real detail panel renders, and that the committed card is current. The card is never marked run.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if __package__ in {None, ""}:  # run as a script: make the product importable
    sys.path[:0] = [str(ROOT / "src"), str(ROOT)]

from crypto_probability_engine.api import save_receipt  # noqa: E402
from crypto_probability_engine.detail import decision_view  # noqa: E402
from crypto_probability_engine.detail.decision_brief import (  # noqa: E402
    MODEL_READINESS,
    MODEL_READINESS_COPY,
    PROBABILITY_TYPE,
)
from crypto_probability_engine.detail.decision_synthesis import (  # noqa: E402
    build_decision_synthesis,
)
from crypto_probability_engine.execution_realism.realism import (  # noqa: E402
    compute_execution_realism,
)
from crypto_probability_engine.features.liquidity_depth import (  # noqa: E402
    compute_liquidity_depth,
)
from crypto_probability_engine.gates.composite import apply_composite_gates  # noqa: E402

CARD = ROOT / "docs" / "runbooks" / "UX_COMPREHENSION_CHECK.md"
APP_JS = ROOT / "frontend" / "app.js"
METHODOLOGY = "heuristic-v1-wave4b0"
TIMEFRAME = "1H"
CLAIM_KEY = f"{PROBABILITY_TYPE}:{METHODOLOGY}:{TIMEFRAME}"
YES_NO = (("yes", "Yes."), ("no", "No."))
# Each question: what it asks, and its fixed choices (what a reader writes down, what it means).
# They are written as a colleague would ask them, and they ask what a screen MEANS for its reader.
# A question may share ordinary words with a screen; it quotes no headline, label or framing
# sentence, and the tests run three adversaries against the generated card: a reader who answers
# by finding a question's words on the analysis, one who takes the gates' disposition for a call
# on the market, and one who takes the storage badge or the request-time row for the receipt.
# The choices of one question are parallel in form and length.
QUESTIONS = (
    (
        "Is one of the reasons this analysis is blocked something the system actually measured "
        "in the market, such as extreme price moves or trading costs that are too high?",
        YES_NO,
    ),
    (
        "Is one of the reasons that market data the system needed today (prices, the order "
        "book) was missing or could not be used, or that a safety switch was on?",
        YES_NO,
    ),
    (
        "Is one of the reasons that the model has not yet shown it can predict direction?",
        YES_NO,
    ),
    (
        "How much can you rely on the percentages on this screen as a forecast?",
        (
            ("a", "Only as rough background: nobody has signed off on their accuracy."),
            ("b", "As a signed-off forecast, but with no direction approved."),
            ("c", "As a signed-off forecast, and with a direction approved."),
            ("d", "Not at all: the data was too poor to show any."),
        ),
    ),
    (
        "What does this screen tell you to do about a trade?",
        (
            ("a", "It tells me to stay out."),
            ("b", "It tells me to go ahead."),
            ("c", "It tells me neither."),
        ),
    ),
    (
        "If the server were restarted tonight, would this analysis still be in Recent Analysis "
        "tomorrow?",
        (
            ("a", "Yes, it will still be there."),
            ("b", "No, it will be gone."),
            ("c", "Maybe, it could go either way."),
        ),
    ),
)
# The frontend functions the detail panel's Decision view is made of (frontend/app.js), and their
# constants: everything renderDecisionViewSection calls, and the save receipt's text.
_FUNCTIONS = (
    "formatNumber",
    "formatPct",
    "formatFractionPct",
    "formatValue",
    "backendText",
    "persistenceStatusText",
    "decisionDataText",
    "decisionEvidenceText",
    "dispositionLabel",
    "costCaveatRows",
    "decisionViewRows",
    "decisionViewOf",
    "gateView",
    "gateViewOf",
    "hasGateFraming",
    "gateFramingBlocks",
    "gateDetailList",
    "saveReceiptText",
    "renderDecisionViewSection",
    "updatePersistenceStatus",
)
_CONSTANTS = (
    "NOT_ASSESSED_TEXT",
    "VENUE_LABELS",
    "SAVE_RECEIPT_SCHEMA_VERSION",
    "SAVE_RECEIPT_TEXT",
    "STORAGE_ROW_LABEL",
)
# The page's DOM builders, standing in as recorders: each keeps what a user would read, in the
# order the section holds it. The Storage row then takes the receipt's text, as the screen does
# it (watchSaveReceipt): only where the backend's receipt is one this screen can show. The badge
# is written by the page's own function, and Overview's row is the page's own text for the
# status the analysis carries.
_RECORD = """
const noClasses = { add() {}, remove() {} };
const persistenceStatusBadge = { textContent: "", dataset: {}, classList: noClasses };
function textBlock(tagName, text) { return { kind: "text", text: String(text) }; }
function keyValueTable(values) {
  return { kind: "rows", rows: values.map(([label, value]) => [label, formatValue(value)]) };
}
function listBlock(items = []) {
  const shown = [...(items || [])].map(String);
  return { kind: "list", items: shown.length ? shown : ["none"], classList: { add() {} } };
}
function section(title, children) { return { title, blocks: children }; }
const shown = cases.map(([payload, receipt, badge]) => {
  const drawn = renderDecisionViewSection(payload, decisionViewOf(payload));
  const text = saveReceiptText(receipt, payload.run_id);
  for (const block of drawn.blocks) {
    for (const row of block.kind === "rows" ? block.rows : []) {
      if (row[0] === STORAGE_ROW_LABEL && text !== null) row[1] = text;
    }
  }
  updatePersistenceStatus(badge);
  return {
    ...drawn,
    badge: persistenceStatusBadge.textContent,
    requested: persistenceStatusText(payload.debug.persistence_status),
  };
});
process.stdout.write(JSON.stringify(shown));
"""
# Overview's label for storage's status when the analysis was requested (renderStructuredDetail).
REQUESTED_ROW_LABEL = "Storage when requested"


@dataclass(frozen=True)
class Scenario:
    """The inputs of one analysis. No field states an answer: the key is computed from the
    payload and the receipt these inputs lead to (`answers`)."""

    letter: str
    name: str  # never shown before the answer key
    synthetic: bool
    accepted: bool = False
    permission: bool = False
    data_ok: bool = True  # False: no venue served data (SYNTHETIC)
    tail: bool = False  # a measured tail-risk breach
    usable_book: bool = True  # False: a book was served whose spread the measure refuses
    kill: bool = False  # the kill switch (SYNTHETIC: a constant False in the product today)
    requested: str = "OK"  # storage's status when the analysis was requested
    badge: str = "OK"  # storage's status when it was last asked (the badge at the top)
    receipt: str = save_receipt.SAVED  # the save receipt's state for this analysis


# A fixed, non-obvious order: the owner reads A to I without knowing which is which. The three
# storage lines of an analysis never all agree: the receipt is the one that speaks of THIS
# analysis, and each example is a combination the product can show.
SCENARIOS = (
    Scenario("A", "unproven model only", False, requested="UNAVAILABLE", badge="UNAVAILABLE"),
    Scenario(
        "B", "invalid data (a degraded provider)", True, data_ok=False, receipt=save_receipt.FAILED
    ),
    Scenario(
        "C", "directional permission", True, accepted=True, permission=True, badge="UNAVAILABLE"
    ),
    Scenario("D", "unproven model, save not confirmed", False, receipt=save_receipt.FAILED),
    Scenario("E", "accepted forecast", True, accepted=True, requested="UNAVAILABLE"),
    Scenario(
        "F", "a risk gate with the unproven model", False, tail=True, requested="UNAVAILABLE",
        badge="UNAVAILABLE",
    ),
    Scenario(
        "G", "an unusable order book (a data gate)", False, usable_book=False,
        receipt=save_receipt.FAILED,
    ),
    Scenario("H", "the kill switch (a system gate)", True, kill=True, requested="UNAVAILABLE"),
    Scenario(
        "I", "unproven model, storage not configured", False, requested="STATELESS",
        badge="UNKNOWN", receipt=save_receipt.NOT_RETAINED,
    ),
)


def answers(payload: dict[str, Any], receipt: dict[str, Any]) -> tuple[str, ...]:
    """The key of one analysis, computed from the product's own facts: the view's gate authority
    and state, the synthesis's permission, and the save receipt. Nothing here is typed per
    analysis, and nothing is read from a scenario."""

    view = payload["decision_view"]
    gates = view["gates"]
    permission = payload["decision_synthesis"]["action_permission"]

    def yes_no(value: bool) -> str:
        return "yes" if value else "no"

    standing = {
        "NO_ACCEPTED_CLAIM": "a",
        "ACCEPTED_FORECAST_CLAIM": "b",
        "DIRECTIONAL_PERMISSION": "c",
        "INVALID_OR_UNAVAILABLE_DATA": "d",
    }[view["state"]]
    kept = {
        save_receipt.SAVED: "a",
        save_receipt.NOT_RETAINED: "b",
        save_receipt.FAILED: "c",
        save_receipt.PENDING: "c",
    }[receipt["state"]]
    return (
        # The three causes a gate can report, kept apart: a risk gate reports a measured finding
        # about the market or its execution; a system or data gate reports missing or unusable
        # data, or a safety switch; the evidence gate reports an unproven model.
        yes_no(gates["risk_gate_active"] is True),
        yes_no("SYSTEM_OR_DATA" in gates["kinds"]),
        yes_no("EVIDENCE" in gates["kinds"]),
        standing,
        # The product never tells anybody to stay out or to go ahead: its own permission to
        # enter is the one fact that could make this "b", and no fact of the payload says "a".
        "b" if permission["can_enter_now"] is True else "c",
        kept,
    )


@contextmanager
def _registries(*, accepted: bool, permission: bool) -> Iterator[None]:
    """The acceptance registries filled for one SYNTHETIC build only, and restored at once."""

    saved = (decision_view.ACCEPTED_FORECAST_CLAIMS, decision_view.ACCEPTED_DIRECTIONAL_PERMISSIONS)
    try:
        decision_view.ACCEPTED_FORECAST_CLAIMS = frozenset({CLAIM_KEY}) if accepted else frozenset()
        decision_view.ACCEPTED_DIRECTIONAL_PERMISSIONS = (
            frozenset({CLAIM_KEY}) if permission else frozenset()
        )
        yield
    finally:
        decision_view.ACCEPTED_FORECAST_CLAIMS, decision_view.ACCEPTED_DIRECTIONAL_PERMISSIONS = (
            saved
        )


def run_id(scenario: Scenario) -> str:
    return f"run_card_{scenario.letter.lower()}"


def receipt(scenario: Scenario) -> dict[str, str]:
    """The save receipt the backend gives for this analysis (api/save_receipt.py), in the state
    the scenario names: saved, not confirmed, or not retained."""

    checked = datetime(2026, 10, 5, 12, 0, 9, tzinfo=UTC)
    return save_receipt.receipt_payload(run_id(scenario), scenario.receipt, checked)


def build(scenario: Scenario) -> tuple[dict[str, Any], dict[str, Any]]:
    """One scenario's (payload, view): the gate result from the real gates, the view from the real
    builder, and the payload's display fields as the product fills them for these gates."""

    close = datetime(2026, 10, 5, 12, 0, tzinfo=UTC)
    snapshot = SimpleNamespace(
        candles=(SimpleNamespace(close_time_utc=close),),
        as_of_utc=datetime(2026, 10, 5, 12, 0, 5, tzinfo=UTC),
    )
    data_quality = {
        "is_live_data": scenario.data_ok,
        "data_source": "BINANCE_PUBLIC",
        "latest_candle_age_seconds": 5 if scenario.data_ok else None,
        "warnings": [],
    }
    # SYNTHETIC where the data are not OK: no venue served data. Today that analysis ends in an
    # error before any view is built, so these are the inputs the view would have had.
    provider_state = {
        "status": "OK" if scenario.data_ok else "UNAVAILABLE",
        "active_provider": "binance" if scenario.data_ok else None,
        "providers": {"binance": {"status": "OK" if scenario.data_ok else "QUARANTINED"}},
    }
    # Data a synthetic state assumes: an accepted forecast-quality claim implies calibration
    # measured on resolved outcomes, which by itself demonstrates no directional skill; a
    # directional permission also implies demonstrated directional skill.
    accepted = scenario.accepted
    if scenario.permission:
        skill_evidence = {"verdict": "SKILL_DEMONSTRATED", "n": 400}
    elif accepted:
        skill_evidence = {"verdict": "NO_DEMONSTRATED_SKILL", "n": 400}
    else:
        skill_evidence = {"verdict": "INSUFFICIENT_EVIDENCE", "n": 0}
    # The liquidity and execution states are the real features' own, for a book that is served:
    # a tight one, or one whose ask is more than three times its bid (the measure refuses it).
    bid, ask = (120.0, 120.012) if scenario.usable_book else (100.0, 400.0)
    book = SimpleNamespace(
        bids=(SimpleNamespace(price=bid, size=50.0),),
        asks=(SimpleNamespace(price=ask, size=50.0),),
    )
    liquidity = compute_liquidity_depth(book)
    execution = compute_execution_realism(liquidity)
    score = {"disposition": "CONSTRUCTIVE_CAUTIOUS"}
    tail = {"cvar_loss": 0.09 if scenario.tail else 0.0, "cvar_breach_threshold": 0.05}
    # The gates' own result for these states: nothing about it is typed by hand.
    gate = apply_composite_gates(
        epistemic_state={"action": "ALLOW"},
        provider_state=provider_state,
        score_state=score,
        liquidity_state=liquidity,
        tail_risk_state=tail,
        execution_state=execution,
        skill_state=skill_evidence,
        kill_switch=scenario.kill,
    )
    quant_result = {
        "gate_result": gate,
        "score_stack": score,
        "liquidity_state": liquidity,
        "tail_risk_state": tail,
        "probability_state": {
            "horizons": {
                "H_primary": {"p_up_frac": 0.31, "p_down_frac": 0.27, "p_timeout_frac": 0.42}
            }
        },
        "execution_realism": execution,
    }
    decision_brief = {
        "probability_type": PROBABILITY_TYPE,
        "model_readiness": "MEASURED" if accepted else MODEL_READINESS,
        "calibration_status": "CALIBRATED" if accepted else "DEFAULT_PHASE1A",
        "reliability_status": "MEASURED" if accepted else "INSUFFICIENT_SAMPLE",
    }
    with _registries(accepted=accepted, permission=scenario.permission):
        view = decision_view.build_decision_view(
            timeframe=TIMEFRAME,
            methodology_version=METHODOLOGY,
            snapshot=snapshot,
            data_quality=data_quality,
            provider_state=provider_state,
            quant_result=quant_result,
            decision_brief=decision_brief,
            skill_evidence=skill_evidence,
            primary_venue="binance",
        )
    synthesis = build_decision_synthesis(
        timeframe=TIMEFRAME,
        quant_result=quant_result,
        data_quality=data_quality,
        provider_state=provider_state,
        decision_brief=decision_brief,
    )
    payload = {
        "run_id": run_id(scenario),
        "normalized_symbol": "BTC/USDT",
        "frontend_display": {
            # The product's own constant (decision_brief.py), whatever the state: copy is never
            # assumed, only data.
            "model_readiness_label": MODEL_READINESS_COPY,
            # As the product fills it (detail/frontend_display.py): the gate action when a hard
            # gate did not pass, else the score's disposition.
            "disposition": score["disposition"] if gate["hard_gate_passed"] else gate["action"],
        },
        # What storage said when the analysis was requested; whether the analysis was then
        # saved is the receipt's to say.
        "debug": {"persistence_status": scenario.requested},
        "decision_view": view,
        "decision_synthesis": synthesis,
    }
    return payload, view


def _extract(source: str, name: str) -> str:
    """One top-level function or const of app.js, exactly as written."""

    function = f"function {name}("
    if function in source:
        start = source.index(function)
        depth, index = 0, source.index("(", start)
        while True:  # past the parameter list (a default may itself be "{}")
            depth += {"(": 1, ")": -1}.get(source[index], 0)
            index += 1
            if depth == 0:
                break
        depth = 0
        for position in range(source.index("{", index), len(source)):
            depth += {"{": 1, "}": -1}.get(source[position], 0)
            if depth == 0:
                return source[start : position + 1]
    start = source.index(f"const {name} = ")
    depth = 0
    for position in range(start, len(source)):  # a const: to its first top-level ";"
        depth += {"{": 1, "[": 1, "}": -1, "]": -1}.get(source[position], 0)
        if source[position] == ";" and depth == 0:
            return source[start : position + 1]
    raise ValueError(name)


def render(cases: list[tuple[dict[str, Any], Any, str]]) -> list[dict[str, Any]]:
    """What the real frontend draws for each (payload, receipt, badge status): the Decision view
    section (its title and its blocks in order, each a text, a table of rows or a list), the
    badge at the top of the page, and Overview's request-time storage text."""

    source = APP_JS.read_text(encoding="utf-8")
    code = "\n".join(_extract(source, name) for name in (*_CONSTANTS, *_FUNCTIONS))
    script = f"const cases = {json.dumps(cases)};\n{code}\n{_RECORD}"
    done = subprocess.run(  # noqa: S603 - node on a script built here, read on stdin
        ["node", "-"], input=script, capture_output=True, text=True, timeout=60, check=True
    )
    return json.loads(done.stdout)


def screens() -> list[dict[str, Any]]:
    """Every scenario's screen: the section the frontend draws, with its view and its receipt."""

    built = [build(scenario) for scenario in SCENARIOS]
    receipts = [receipt(scenario) for scenario in SCENARIOS]
    drawn = render(
        [
            (payload, given, scenario.badge)
            for scenario, (payload, _), given in zip(SCENARIOS, built, receipts, strict=True)
        ]
    )
    return [
        {"scenario": scenario, "payload": payload, "view": view, "receipt": given, **section}
        for scenario, (payload, view), given, section in zip(
            SCENARIOS, built, receipts, drawn, strict=True
        )
    ]


_HEADER = """# Runbook: the UX comprehension check (plan §23 "UX")

**Status: PREPARED, NOT RUN.** For the DecisionView (Lane P; owner rulings DP-A and DP-F): run
it once, before Lane P's release. Generated by `scripts/ux_comprehension/card.py` from the
product's own code; do not edit it by hand.

The governing plan's §23 requires this check. Its criterion is quoted after the answer key.

Some analyses below are **SYNTHETIC**: they show states the product cannot show today. The notes
after the answer key say which, and why.

Each analysis below is one screen, as the product draws it: the storage badge at the top of the
page, the **Decision view** as the detail panel shows it, and one row from the Overview section
further down the same panel.

## How to run it (about thirty minutes)

1. Read analyses A to I below as you would read them on screen. Do not look at the answer
   key first.
2. For each analysis, answer the six questions on paper, each with one of its listed answers.
   They ask what the screen means for you, not which words are on it.
3. Then compare your answers with the key at the end.

**PASS:** every answer matches the key. **Any mismatch:** the UX does not PASS. Send Claude
the analysis letter and the question number only; the screen's wording is then what changes.

The six questions, for every analysis. Questions 1 to 3 go together: an analysis can be blocked
for more than one reason, so more than one of them can be yes. If it is not blocked at all, all
three are no.
"""

# What the Single Crypto Analysis screen shows around the view, for each timeframe (frontend/app.js
# horizonCard). Each is (the words the card uses for it, a literal of horizonCard that renders it,
# whether that literal sits in horizonCard's own `if (view)` branch or outside both branches).
OUTSIDE_THE_VIEW = (
    ("a BLOCK banner naming the check that blocks", '"matrix-block-banner"', False),
    ("a role label", "displayRole(role.role)", False),
    ("a role sentence", "role.plainEnglish", True),
    ("a Signal heat row", '"Signal heat (not risk)"', True),
    ("the data-source line", "dataBannerFor(payload)", False),
)
# The sections the detail panel shows under the Decision view (renderStructuredDetail), in order.
UNDER_THE_VIEW = (
    "Decision (Probability interpretation and the Actionability stack)",
    "Model Quality",
    "Overview (one of its rows is on this card)",
    "Gates",
    "the data, provider, quant and news sections, and Raw JSON",
)

_LIMITS = """
## What this check covers, and what it does not

- Plan §23: UX is "PASS only when predefined owner-task scenarios distinguish: invalid data;
  unvalidated model; accepted forecast; directional permission; saved/unsaved state."
- Analyses {accepted} are **SYNTHETIC**. No forecast claim or directional permission is
  accepted today (both acceptance registries are empty), so the product cannot show them
  yet. The product's own code built them, with the registries filled for this card only.
  Their data assume what such a claim implies (calibration measured on resolved outcomes;
  for E no demonstrated directional skill, for C demonstrated directional skill); every word
  on them is the product's own.
- Analysis {invalid} is **SYNTHETIC** too, for a different reason. Today, when the market data
  are missing or too short, the product shows an error message and no analysis, so no screen
  shows this state. The product's own code built it for this card only.
- Analysis {system} is **SYNTHETIC** as well. The safety shutdown it shows is switched off in
  today's product, and no setting turns it on, so no screen shows this state. The product's
  own gates built it for this card only, with the switch set.
- Every number is a made-up example, not market data. The gates are the product's own: each
  analysis's gate result, and so its Gate disposition, is what the real gates return for its
  made-up inputs.
- The answer key is computed from each analysis's own data (the response the product builds
  and its save receipt), not typed in. Questions 1 to 3 are the three kinds of gate the view
  can name: a risk gate (a measured finding about the market), a system or data gate (data
  that was missing or unusable, or the safety shutdown) and the evidence gate (a model that
  is not yet proven). Question 4 is the view's state, question 5 the product's own
  permission to enter, and question 6 the save receipt.
{constant}
- What the questions are for. Question 5, and question 1 wherever something other than a
  measured finding blocks, are answered wrongly by a reader who takes BLOCK or the Gate
  disposition for a call on the market. Question 6 is answered wrongly by a reader who takes
  the badge at the top, or the "Storage when requested" row, for the word on this one
  analysis: on every analysis here at least one of those two says something else than the
  Decision view's Storage row, which is the save receipt.
- Each analysis's Decision view is what the detail panel shows, line for line: the product's
  own screen code drew it for this card, and the badge and the Overview row with it. The
  cards of the Single Crypto Analysis and Batch Crypto Analysis screens show the same
  headline, sentence, gate summary, framing and rows; they leave out the list of active
  gates and the notes under the rows. This card shows no layout or colours.
- The screens show more than this, and none of the following is on this card, so a PASS
  here says nothing about it:
  - On the Single Crypto Analysis screen, each timeframe also shows:
{outside}
  - Under the Decision view, the detail panel also shows:
{under}
- The three storage lines. The badge is what storage said when it was last asked, by any
  request. "Storage when requested" is what it said when this analysis was requested. The
  Decision view's Storage row is this analysis's save receipt: after an analysis is shown,
  the screen asks the backend whether that analysis was saved and shows the state the
  backend gives. Until a receipt answers, that row shows storage's status when the analysis
  was requested instead. The states on this card are examples, each one the product can
  give today: saved ({saved}), not confirmed ({unconfirmed}) and not retained
  ({unretained}). One more exists and is not on this card ("Saving… not yet confirmed").
- The save receipt is built, and whether its wording is understood is what question 6
  tests: its UX acceptance is open until this check is run.
"""


def _markdown(block: dict[str, Any], *, headline: bool) -> list[str]:
    if block["kind"] == "rows":
        rows = [f"| {label} | {value} |" for label, value in block["rows"]]
        return ["| Row | Shown |", "| --- | --- |", *rows, ""]
    if block["kind"] == "list":
        return [*(f"- {item}" for item in block["items"]), ""]
    return [f"**{block['text']}**" if headline else block["text"], ""]


def _constant_note(keys: list[tuple[str, ...]]) -> str:
    """The note on every question whose answer is the same on every analysis, said as it is. It
    is computed from the key: a question that tells the analyses apart is not named here."""

    notes = []
    for position, column in enumerate(zip(*keys, strict=True), start=1):
        if len(set(column)) == 1:
            notes.append(
                f"- Question {position} has the same answer on every analysis: {column[0]}. The "
                "product is\n  analysis only: it never tells anyone to buy, to sell or to stay "
                "out. The question is\n  asked each time all the same, because it is the one a "
                "reader gets wrong who takes\n  BLOCK or the Gate disposition for a call on the "
                "market. The other questions are the\n  ones whose answers differ between the "
                "analyses."
            )
    return "\n".join(notes)


def _letters(letters: list[str]) -> str:
    """ "D", or "A, B and C"."""

    if len(letters) == 1:
        return letters[0]
    return f"{', '.join(letters[:-1])} and {letters[-1]}"


def shown_lines(screen: dict[str, Any]) -> list[str]:
    """Every line of the screen an analysis shows on the card, in order: the badge, the Decision
    view's blocks, and Overview's request-time row. What a reader can read, and nothing else."""

    lines = [screen["badge"], screen["title"]]
    for block in screen["blocks"]:
        if block["kind"] == "rows":
            lines += [text for row in block["rows"] for text in row]
        elif block["kind"] == "list":
            lines += block["items"]
        elif block["text"].strip():
            lines.append(block["text"])
    return [*lines, REQUESTED_ROW_LABEL, screen["requested"]]


def card_markdown() -> str:
    lines = _HEADER.split("\n")
    for number, (question, choices) in enumerate(QUESTIONS, start=1):
        lines += [f"{number}. {question}"]
        lines += [f"   - **{answer}** — {meaning}" for answer, meaning in choices]
    drawn = screens()
    for screen in drawn:
        lines += ["", f"## Analysis {screen['scenario'].letter}", ""]
        lines += [f"At the top of the page: {screen['badge']}", "", "### Decision view", ""]
        # The section's own blocks, in its own order: the first is the view's headline. A text
        # that is empty is not on the screen either.
        blocks = [block for block in screen["blocks"] if block.get("text", "x").strip()]
        for position, block in enumerate(blocks):
            lines += _markdown(block, headline=position == 0)
        lines += ["Further down the same panel, in Overview:", ""]
        lines += ["| Row | Shown |", "| --- | --- |"]
        lines += [f"| {REQUESTED_ROW_LABEL} | {screen['requested']} |"]
    numbers = " | ".join(str(number) for number in range(1, len(QUESTIONS) + 1))
    lines += [
        "",
        "## Answer key (read it only after answering)",
        "",
        f"| Analysis | {numbers} |",
        f"| --- | {' | '.join('---' for _ in QUESTIONS)} |",
    ]
    for screen in drawn:
        key = answers(screen["payload"], screen["receipt"])
        lines += [f"| {screen['scenario'].letter} | {' | '.join(key)} |"]

    def by_state(state: str) -> str:
        return _letters([s.letter for s in SCENARIOS if s.receipt == state])

    accepted = ", ".join(s.letter for s in SCENARIOS if s.synthetic and s.accepted)
    invalid = ", ".join(s.letter for s in SCENARIOS if s.synthetic and not s.data_ok)
    system = ", ".join(s.letter for s in SCENARIOS if s.synthetic and s.kill)
    keys = [answers(screen["payload"], screen["receipt"]) for screen in drawn]
    lines += _LIMITS.format(
        accepted=accepted,
        invalid=invalid,
        system=system,
        constant=_constant_note(keys),
        outside="\n".join(f"    - {name}" for name, _, _ in OUTSIDE_THE_VIEW),
        under="\n".join(f"    - {name}" for name in UNDER_THE_VIEW),
        saved=by_state(save_receipt.SAVED),
        unconfirmed=by_state(save_receipt.FAILED),
        unretained=by_state(save_receipt.NOT_RETAINED),
    ).split("\n")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true", help="regenerate the card")
    mode.add_argument("--check", action="store_true", help="exit 1 if the card differs")
    args = parser.parse_args(argv)
    text = card_markdown()
    if args.write:
        CARD.write_text(text, encoding="utf-8")
        print(f"wrote {CARD.relative_to(ROOT)}")
        return 0
    current = CARD.read_text(encoding="utf-8") if CARD.exists() else ""
    if current != text:
        print(f"{CARD.relative_to(ROOT)} is stale: run card.py --write", file=sys.stderr)
        return 1
    print(f"{CARD.relative_to(ROOT)} is current")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
