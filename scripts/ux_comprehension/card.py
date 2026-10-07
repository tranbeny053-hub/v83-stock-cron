"""The owner's UX comprehension check for the DecisionView (governing plan §23 "UX"; §14).

Plan §23: UX is "PASS only when predefined owner-task scenarios distinguish: invalid data;
unvalidated model; accepted forecast; directional permission; saved/unsaved state." This builds
those scenarios and the owner's card (docs/runbooks/UX_COMPREHENSION_CHECK.md) from the product's
own code, so the card cannot drift from what the screen shows:
- each scenario's view is built by the real backend builder (detail/decision_view.py) from
  controlled inputs. The two accepted states are unreachable today (both acceptance registries
  are empty), so they are built with the registries filled for that build only, restored at once,
  and the card marks them SYNTHETIC;
- each scenario's visible rows are rendered by the real frontend (frontend/app.js:
  decisionViewRows and the helpers it calls) under node;
- the numbers are illustrative fixtures, never market data, and nothing here reads a database.

    python scripts/ux_comprehension/card.py --write   # regenerate the card
    python scripts/ux_comprehension/card.py --check   # exit 1 if the committed card differs

tests/frontend/test_ux_comprehension_card.py checks that the scenarios distinguish every §23
dimension, that the answer key follows from each view, and that the committed card is current.
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

from crypto_probability_engine.detail import decision_view  # noqa: E402
from crypto_probability_engine.detail.decision_brief import (  # noqa: E402
    MODEL_READINESS,
    MODEL_READINESS_COPY,
    PROBABILITY_TYPE,
)

CARD = ROOT / "docs" / "runbooks" / "UX_COMPREHENSION_CHECK.md"
APP_JS = ROOT / "frontend" / "app.js"
METHODOLOGY = "heuristic-v1-wave4b0"
TIMEFRAME = "1H"
CLAIM_KEY = f"{PROBABILITY_TYPE}:{METHODOLOGY}:{TIMEFRAME}"
QUESTIONS = (
    "Can the market data support an assessment here?",
    "Has a forecast-quality claim been accepted for it?",
    "Does it carry a directional permission?",
    "Does the screen say this analysis will NOT be kept in Recent Analysis history?",
)
# The frontend functions the view's rows are made of (frontend/app.js), and their constants.
_FUNCTIONS = (
    "formatNumber",
    "formatPct",
    "formatFractionPct",
    "persistenceStatusText",
    "decisionDataText",
    "decisionEvidenceText",
    "dispositionLabel",
    "decisionViewRows",
)
_CONSTANTS = ("NOT_ASSESSED_TEXT", "VENUE_LABELS")


@dataclass(frozen=True)
class Scenario:
    letter: str
    name: str  # never shown before the answer key
    synthetic: bool
    data_ok: bool
    accepted: bool
    permission: bool
    retained: bool
    disposition: str  # the gates' disposition the product would show for these gates


# A fixed, non-obvious order: the owner reads A to E without knowing which is which.
SCENARIOS = (
    Scenario("A", "unvalidated model, kept", False, True, False, False, True, "NO_TRADE"),
    Scenario("B", "invalid data", False, False, False, False, True, "ABORT"),
    Scenario(
        "C",
        "directional permission",
        True,
        True,
        True,
        True,
        True,
        "CONSTRUCTIVE_CAUTIOUS",
    ),
    Scenario("D", "unvalidated model, not kept", False, True, False, False, False, "NO_TRADE"),
    Scenario("E", "accepted forecast", True, True, True, False, True, "NO_TRADE"),
)


def answers(scenario: Scenario) -> tuple[str, str, str, str]:
    """The key: what a correct reading of each scenario's screen answers to the four questions."""

    def yes_no(value: bool) -> str:
        return "yes" if value else "no"

    return (
        yes_no(scenario.data_ok),
        yes_no(scenario.accepted),
        yes_no(scenario.permission),
        yes_no(not scenario.retained),
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


def build(scenario: Scenario) -> tuple[dict[str, Any], dict[str, Any]]:
    """One scenario's (payload, view): the view from the real builder, the payload's display
    fields as the product fills them for these gates."""

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
    provider_state = {
        "status": "OK" if scenario.data_ok else "UNAVAILABLE",
        "active_provider": "binance" if scenario.data_ok else None,
        "providers": {"binance": {"status": "OK" if scenario.data_ok else "QUARANTINED"}},
    }
    if not scenario.data_ok:
        hard_blocks = ["PROVIDER_DEGRADED"]
    elif scenario.permission:
        hard_blocks = []
    else:
        hard_blocks = ["SKILL_NOT_DEMONSTRATED"]
    quant_result = {
        "gate_result": {"hard_blocks": hard_blocks},
        "probability_state": {
            "horizons": {
                "H_primary": {"p_up_frac": 0.31, "p_down_frac": 0.27, "p_timeout_frac": 0.42}
            }
        },
        "execution_realism": {
            "round_trip_cost_frac": 0.0021,
            "taker_fee_frac": 0.001,
            "slippage_frac": 0.00005,
        },
    }
    accepted = scenario.accepted
    decision_brief = {
        "probability_type": PROBABILITY_TYPE,
        "model_readiness": "MEASURED" if accepted else MODEL_READINESS,
        "calibration_status": "CALIBRATED" if accepted else "DEFAULT_PHASE1A",
        "reliability_status": "MEASURED" if accepted else "INSUFFICIENT_SAMPLE",
    }
    # Data a synthetic state assumes: an accepted forecast-quality claim implies calibration
    # measured on resolved outcomes, which by itself demonstrates no directional skill; a
    # directional permission also implies demonstrated directional skill.
    if scenario.permission:
        skill_evidence = {"verdict": "SKILL_DEMONSTRATED", "n": 400}
    elif accepted:
        skill_evidence = {"verdict": "NO_DEMONSTRATED_SKILL", "n": 400}
    else:
        skill_evidence = {"verdict": "INSUFFICIENT_EVIDENCE", "n": 0}
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
        "normalized_symbol": "BTC/USDT",
        "frontend_display": {
            # The product's own constant (decision_brief.py), whatever the state: copy is never
            # assumed, only data.
            "model_readiness_label": MODEL_READINESS_COPY,
            "disposition": scenario.disposition,
        },
        "debug": {"persistence_status": "OK" if scenario.retained else "UNAVAILABLE"},
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
    return source[start : source.index("\n", start)]  # these two constants are one line each


def render(cases: list[tuple[dict[str, Any], dict[str, Any]]]) -> list[list[list[str]]]:
    """The rows the real frontend shows for each (payload, view)."""

    source = APP_JS.read_text(encoding="utf-8")
    code = "\n".join(_extract(source, name) for name in (*_CONSTANTS, *_FUNCTIONS))
    script = (
        f"{code}\nconst cases = {json.dumps(cases)};\n"
        "console.log(JSON.stringify(cases.map(([payload, view]) => "
        "decisionViewRows(payload, view).map(([label, value]) => [label, String(value)]))));"
    )
    done = subprocess.run(  # noqa: S603
        ["node", "-e", script], capture_output=True, text=True, timeout=60, check=True
    )
    return json.loads(done.stdout)


_HEADER = """# Runbook: the UX comprehension check (plan §23 "UX")

**Status: PREPARED, NOT RUN.** For the DecisionView (Lane P, local only under DP-A): run it
once, before Lane P's release. Generated by `scripts/ux_comprehension/card.py` from the
product's own code; do not edit it by hand.

Plan §23: UX is "PASS only when predefined owner-task scenarios distinguish: invalid data;
unvalidated model; accepted forecast; directional permission; saved/unsaved state."

## How to run it (about ten minutes)

1. Read analyses A to E below as you would read them on screen. Do not look at the answer
   key first.
2. For each analysis, answer the four questions, yes or no, on paper.
3. Then compare your answers with the key at the end.

**PASS:** every answer matches the key. **Any mismatch:** the UX does not PASS. Send Claude
the analysis letter and the question number only; the screen's wording is then what changes.

The four questions, for every analysis:
"""

_LIMITS = """
## What this check covers, and what it does not

- Analyses {synthetic} are **SYNTHETIC**. No forecast claim or directional permission is
  accepted today (both acceptance registries are empty), so the product cannot show them
  yet. The product's own code built them, with the registries filled for this card only.
  Their data assume what such a claim implies (calibration measured on resolved outcomes;
  for E no demonstrated directional skill, for C demonstrated directional skill); every word
  on them is the product's own.
- Every number is an illustrative fixture, not market data.
- The card shows the screen's words, not its layout or colours.
- Question 4 reads the Storage row, which says when an analysis will not be kept. The
  product shows no per-analysis save receipt (plan §14.2 item 4, left as recorded in Lane
  P's review 1).
"""


def card_markdown() -> str:
    built = [build(scenario) for scenario in SCENARIOS]
    rendered = render(built)
    lines = _HEADER.split("\n")
    lines += [f"{number}. {question}" for number, question in enumerate(QUESTIONS, start=1)]
    for scenario, (_, view), rows in zip(SCENARIOS, built, rendered, strict=True):
        lines += ["", f"## Analysis {scenario.letter}", "", f"**{view['headline']}**", ""]
        lines += [view["detail"], "", "| Row | Shown |", "| --- | --- |"]
        lines += [f"| {label} | {value} |" for label, value in rows]
    lines += [
        "",
        "## Answer key (read it only after answering)",
        "",
        "| Analysis | 1 | 2 | 3 | 4 |",
        "| --- | --- | --- | --- | --- |",
    ]
    lines += [f"| {s.letter} | {' | '.join(answers(s))} |" for s in SCENARIOS]
    synthetic = ", ".join(s.letter for s in SCENARIOS if s.synthetic)
    lines += _LIMITS.format(synthetic=synthetic).split("\n")
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
