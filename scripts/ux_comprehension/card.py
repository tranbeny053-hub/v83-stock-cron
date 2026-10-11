"""The owner's UX comprehension check for the DecisionView (governing plan §23 "UX"; §14).

Plan §23: UX is "PASS only when predefined owner-task scenarios distinguish: invalid data;
unvalidated model; accepted forecast; directional permission; saved/unsaved state." This builds
those scenarios and the owner's card (docs/runbooks/UX_COMPREHENSION_CHECK.md) from the product's
own code, so the card cannot drift from what the default screen shows:
- each scenario's gate result is the real gates' (gates/composite.py) and its view the real
  builder's (detail/decision_view.py), from controlled inputs. The two accepted states are
  unreachable today (both acceptance registries are empty), so they are built with the registries
  filled for that build only, restored at once, and the card marks them SYNTHETIC. The
  invalid-data state is unreachable today as well: on live data the venue selection refuses what
  the view would call invalid, and the analysis ends in an error (the venue selection); the
  built-in demo data are always long enough. The card marks it SYNTHETIC too;
- each scenario's block is the Decision view exactly as the detail panel shows it: the real
  frontend's own function (frontend/app.js renderDecisionViewSection, and everything it calls)
  runs under node and its output is printed in order, nothing added and nothing left out;
- each scenario's Storage row is shown as it reads once the screen holds the analysis's save
  receipt: the receipt is the backend's own (api/save_receipt.py) and its text the frontend's own
  (saveReceiptText), put in the row as the screen puts it;
- the numbers are illustrative fixtures, never market data, and nothing here reads a database.
What the cards add around the view, and the detail panel's other sections, are not on the card.
The card says so.

    python scripts/ux_comprehension/card.py --write   # regenerate the card
    python scripts/ux_comprehension/card.py --check   # exit 1 if the committed card differs

tests/frontend/test_ux_comprehension_card.py checks that the scenarios distinguish every §23
dimension, that the answer key follows from each screen, that each block is what the real detail
panel renders, and that the committed card is current.
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
from crypto_probability_engine.gates.composite import apply_composite_gates  # noqa: E402

CARD = ROOT / "docs" / "runbooks" / "UX_COMPREHENSION_CHECK.md"
APP_JS = ROOT / "frontend" / "app.js"
METHODOLOGY = "heuristic-v1-wave4b0"
TIMEFRAME = "1H"
CLAIM_KEY = f"{PROBABILITY_TYPE}:{METHODOLOGY}:{TIMEFRAME}"
QUESTIONS = (
    "Can the market data support an assessment here?",
    "Has a forecast-quality claim been accepted for it?",
    "Does it carry a directional permission?",
    "Does the screen say this analysis is saved in Recent Analysis history?",
    "Does the screen report a risk gate: a finding about market conditions or execution?",
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
    "decisionViewRows",
    "decisionViewOf",
    "gateView",
    "gateViewOf",
    "hasGateFraming",
    "gateFramingBlocks",
    "gateDetailList",
    "saveReceiptText",
    "renderDecisionViewSection",
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
# it (watchSaveReceipt): only where the backend's receipt is one this screen can show.
_RECORD = """
function textBlock(tagName, text) { return { kind: "text", text: String(text) }; }
function keyValueTable(values) {
  return { kind: "rows", rows: values.map(([label, value]) => [label, formatValue(value)]) };
}
function listBlock(items = []) {
  const shown = [...(items || [])].map(String);
  return { kind: "list", items: shown.length ? shown : ["none"], classList: { add() {} } };
}
function section(title, children) { return { title, blocks: children }; }
const shown = cases.map(([payload, receipt]) => {
  const drawn = renderDecisionViewSection(payload, decisionViewOf(payload));
  const text = saveReceiptText(receipt, payload.run_id);
  for (const block of drawn.blocks) {
    for (const row of block.kind === "rows" ? block.rows : []) {
      if (row[0] === STORAGE_ROW_LABEL && text !== null) row[1] = text;
    }
  }
  return drawn;
});
process.stdout.write(JSON.stringify(shown));
"""


@dataclass(frozen=True)
class Scenario:
    letter: str
    name: str  # never shown before the answer key
    synthetic: bool
    data_ok: bool
    accepted: bool
    permission: bool
    saved: bool  # the save receipt's state: SAVED, or FAILED (the save was not confirmed)
    risk: bool = False  # a real risk gate (a tail-risk breach) beside the evidence gate


# A fixed, non-obvious order: the owner reads A to F without knowing which is which.
SCENARIOS = (
    Scenario("A", "unvalidated model, saved", False, True, False, False, True),
    Scenario("B", "invalid data", True, False, False, False, True),
    Scenario("C", "directional permission", True, True, True, True, True),
    Scenario("D", "unvalidated model, save not confirmed", False, True, False, False, False),
    Scenario("E", "accepted forecast", True, True, True, False, True),
    Scenario("F", "risk gate with the evidence gate", False, True, False, False, True, risk=True),
)


def answers(scenario: Scenario) -> tuple[str, str, str, str, str]:
    """The key: what a correct reading of each scenario's screen answers to the five questions."""

    def yes_no(value: bool) -> str:
        return "yes" if value else "no"

    return (
        yes_no(scenario.data_ok),
        yes_no(scenario.accepted),
        yes_no(scenario.permission),
        yes_no(scenario.saved),
        yes_no(scenario.risk),
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
    """The save receipt the backend gives for this analysis (api/save_receipt.py): its whole save
    was acknowledged, or it was not confirmed."""

    state = save_receipt.SAVED if scenario.saved else save_receipt.FAILED
    checked = datetime(2026, 10, 5, 12, 0, 9, tzinfo=UTC)
    return save_receipt.receipt_payload(run_id(scenario), state, checked)


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
    liquidity = {"status": "OK", "spread_frac": 0.0001, "top_depth_quote": 5_000.0}
    execution = {
        "status": "OK",
        "round_trip_cost_frac": 0.0021,
        "taker_fee_frac": 0.001,
        "slippage_frac": 0.00005,
    }
    score = {"disposition": "CONSTRUCTIVE_CAUTIOUS"}
    # The gates' own result for these states: nothing about it is typed by hand.
    gate = apply_composite_gates(
        epistemic_state={"action": "ALLOW"},
        provider_state=provider_state,
        score_state=score,
        liquidity_state=liquidity,
        tail_risk_state={
            "cvar_loss": 0.09 if scenario.risk else 0.0,
            "cvar_breach_threshold": 0.05,
        },
        execution_state=execution,
        skill_state=skill_evidence,
    )
    quant_result = {
        "gate_result": gate,
        "liquidity_state": liquidity,
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
        # Storage answered when each analysis was requested; whether the analysis was then saved
        # is the receipt's to say.
        "debug": {"persistence_status": "OK"},
        "decision_view": view,
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


def render(cases: list[tuple[dict[str, Any], dict[str, Any]]]) -> list[dict[str, Any]]:
    """The Decision view section the real frontend draws for each (payload, receipt): its title and
    its blocks in order, each a text, a table of rows or a list."""

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
    drawn = render([(payload, given) for (payload, _), given in zip(built, receipts, strict=True)])
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

Each analysis below is the **Decision view** as the detail panel shows it: its headline, its
sentence, the gate summary with its framing, the active gates, its rows and its notes.

## How to run it (about ten minutes)

1. Read analyses A to F below as you would read them on screen. Do not look at the answer
   key first.
2. For each analysis, answer the five questions, yes or no, on paper.
3. Then compare your answers with the key at the end.

**PASS:** every answer matches the key. **Any mismatch:** the UX does not PASS. Send Claude
the analysis letter and the question number only; the screen's wording is then what changes.

The five questions, for every analysis:
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
    "Overview",
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
- Every number is a made-up example, not market data. The gates are the product's own: each
  analysis's gate result, and so its Gate disposition, is what the real gates return for its
  made-up inputs.
- Each analysis is the Decision view as the detail panel shows it, line for line: the
  product's own screen code drew it for this card. The cards of the Single Crypto Analysis
  and Batch Crypto Analysis screens show the same headline, sentence, gate summary, framing
  and rows; they leave out the list of active gates and the notes under the rows. This card
  shows no layout or colours.
- Analysis F is a real risk gate together with the evidence gate. That is the only way a risk
  gate can appear today, because the evidence gate is always active.
- The screens show more than the Decision view, and none of the following is on this card, so
  a PASS here says nothing about it:
  - On the Single Crypto Analysis screen, each timeframe also shows:
{outside}
  - Under the Decision view, the detail panel also shows:
{under}
- Question 4 reads the Storage row. On this card that row is the save receipt of the
  analysis: after an analysis is shown, the screen asks the backend whether that analysis
  was saved and shows the state the backend gives. {saved} show a save the backend
  acknowledged; {unsaved} shows a save the backend could not confirm. The receipt states
  are examples for this card, and each is one the product can give today. Until a receipt
  answers, the row shows storage's status when the analysis was requested instead
  ("Storage available"); two more receipt states exist and are not on this card ("Saving…
  not yet confirmed", "Not retained: no storage is configured").
- The save receipt is built, and whether its wording is understood is what question 4
  tests: its UX acceptance is open until this check is run.
"""


def _markdown(block: dict[str, Any], *, headline: bool) -> list[str]:
    if block["kind"] == "rows":
        rows = [f"| {label} | {value} |" for label, value in block["rows"]]
        return ["| Row | Shown |", "| --- | --- |", *rows, ""]
    if block["kind"] == "list":
        return [*(f"- {item}" for item in block["items"]), ""]
    return [f"**{block['text']}**" if headline else block["text"], ""]


def _letters(letters: list[str]) -> str:
    """"Analysis D", or "Analyses A, B and C"."""

    if len(letters) == 1:
        return f"Analysis {letters[0]}"
    return f"Analyses {', '.join(letters[:-1])} and {letters[-1]}"


def card_markdown() -> str:
    lines = _HEADER.split("\n")
    lines += [f"{number}. {question}" for number, question in enumerate(QUESTIONS, start=1)]
    for screen in screens():
        lines += ["", f"## Analysis {screen['scenario'].letter}", ""]
        # The section's own blocks, in its own order: the first is the view's headline. A text
        # that is empty is not on the screen either.
        blocks = [block for block in screen["blocks"] if block.get("text", "x").strip()]
        for position, block in enumerate(blocks):
            lines += _markdown(block, headline=position == 0)
        lines.pop()
    lines += [
        "",
        "## Answer key (read it only after answering)",
        "",
        "| Analysis | 1 | 2 | 3 | 4 | 5 |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    lines += [f"| {s.letter} | {' | '.join(answers(s))} |" for s in SCENARIOS]
    accepted = ", ".join(s.letter for s in SCENARIOS if s.synthetic and s.accepted)
    invalid = ", ".join(s.letter for s in SCENARIOS if s.synthetic and not s.accepted)
    lines += _LIMITS.format(
        accepted=accepted,
        invalid=invalid,
        outside="\n".join(f"    - {name}" for name, _, _ in OUTSIDE_THE_VIEW),
        under="\n".join(f"    - {name}" for name in UNDER_THE_VIEW),
        saved=_letters([s.letter for s in SCENARIOS if s.saved]),
        unsaved=_letters([s.letter for s in SCENARIOS if not s.saved]),
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
