"""Review 3 of lane P, finding 1 (3rd occurrence of the test-adequacy class; owner-authorized
third repair): the legacy decision surfaces are rendered with the real app.js over a payload
matrix (a view that is OK, DEGRADED or UNAVAILABLE, no view at all, and an accepted-claim hold),
and the exact visible framing rows are asserted. Review 2 pinned these only by source substring;
this renders them, so a later edit that reintroduces a market-call framing is caught.

The framing sentence itself is the backend's (detail/gate_kinds.py; review finding D3): these
surfaces word none, and print the backend's gate summary and framing together or not at all.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _extract(source: str, name: str) -> str:
    keyword = f"function {name}(" if f"function {name}(" in source else f"const {name} "
    start = source.index(keyword)
    if keyword.startswith("const"):
        # a const object/string: to its first top-level ';'
        depth = 0
        for index in range(start, len(source)):
            character = source[index]
            depth += {"{": 1, "[": 1, "}": -1, "]": -1}.get(character, 0)
            if character == ";" and depth == 0:
                return source[start : index + 1]
        raise AssertionError(name)
    depth, index = 0, source.index("(", start)
    while True:  # past the parameter list (a default parameter may itself be "{}")
        depth += {"(": 1, ")": -1}.get(source[index], 0)
        index += 1
        if depth == 0:
            break
    opening = source.index("{", index)
    depth = 0
    for index in range(opening, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[start : index + 1]
    raise AssertionError(name)


def _render(payloads: list[dict[str, object]]) -> list[dict[str, object]]:
    source = (ROOT / "frontend" / "app.js").read_text(encoding="utf-8")
    real = "\n".join(
        _extract(source, name)
        for name in (
            "decisionLabelCopy",
            "backendText",
            "orderedActionability",
            "decisionLabelTone",
            "primaryDecisionReason",
            "decisionViewOf",
            "acceptedViewOf",
            "NOT_REPORTED_TEXT",
            "ACCEPTED_DISCLAIMER",
            "gateView",
            "gateViewOf",
            "hasGateFraming",
            "gateFramingBlocks",
            "reopenedGates",
            "briefSummaryRows",
            "dispositionLabel",
            "gateBriefTitle",
            "readinessText",
            "renderFinalDecisionCard",
            "renderDecisionBrief",
            "renderDecisionSynthesis",
        )
    )
    script = f"""
const captured = {{ sections: [], texts: [], tables: [], values: [] }};
const elem = () => ({{
  append() {{}}, className: "", textContent: "",
  dataset: {{}}, style: {{}}, classList: {{ add() {{}}, remove() {{}} }},
}});
const document = {{ createElement: () => elem() }};
function section(title, children) {{ captured.sections.push(title); return elem(); }}
function textBlock(tag, text, cls = "") {{ captured.texts.push([cls, text]); return elem(); }}
function keyValueTable(rows) {{
  captured.tables.push(rows.map((row) => row[0]));
  captured.values.push(rows.map((row) => [row[0], String(row[1] ?? "")]));
  return elem();
}}
function decisionBadge() {{ return elem(); }}
function renderPermissionRow() {{ return elem(); }}
function briefListGroup() {{ return elem(); }}
function renderTradePlanSkeleton() {{ return elem(); }}
function renderRiskSummary() {{ return elem(); }}
function renderProbabilityInterpretation() {{ return elem(); }}
function renderActionabilityStack() {{ return elem(); }}
function renderAdvisorExplanations() {{ return elem(); }}
function renderFutureQuantHooks() {{ return elem(); }}
const modelReadinessCopy = "HEURISTIC-COPY";  // recognisable: the fallback readiness
{real}
const payloads = {json.dumps(payloads)};
const synthesis = {{
  decision_synthesis: {{ label: "NO_TRADE", plain_english: "", decision_strength: "" }},
  action_permission: {{}},
  model_quality_summary: {{}},
  actionability_stack: [],
  what_would_change_decision: [],
}};
const brief = {{ action: "NO_TRADE", state_summary: "s", risk_note: "ELEVATED_RISK_AVOID" }};
const rendered = payloads.map((payload) => {{
  const reset = () => {{
    captured.sections.length = 0; captured.texts.length = 0;
    captured.tables.length = 0; captured.values.length = 0;
  }};
  reset();
  renderFinalDecisionCard(synthesis, payload);
  const card = {{ texts: [...captured.texts] }};
  reset();
  renderDecisionBrief(brief, [], payload);
  const briefOut = {{ sections: [...captured.sections], texts: [...captured.texts],
                      tables: [...captured.tables], values: [...captured.values] }};
  reset();
  renderDecisionSynthesis(undefined, brief, payload);  // the "no synthesis" fallback branch
  const fallback = {{ sections: [...captured.sections], texts: [...captured.texts],
                      tables: [...captured.tables], values: [...captured.values] }};
  return {{ card, brief: briefOut, fallback }};
}});
console.log(JSON.stringify(rendered));
"""
    completed = subprocess.run(["node", "-e", script], check=True, capture_output=True, text=True)
    return json.loads(completed.stdout)


_VIEW_OK = {
    "schema_version": "decision_view.v2",
    "state": "NO_ACCEPTED_CLAIM",
    "accepted_claim": False,
    "data": {"state": "OK"},
}
_VIEW_DEGRADED = {
    "schema_version": "decision_view.v2",
    "state": "NO_ACCEPTED_CLAIM",
    "accepted_claim": False,
    "data": {"state": "DEGRADED"},
}
_VIEW_UNAVAILABLE = {
    "schema_version": "decision_view.v2",
    "state": "INVALID_OR_UNAVAILABLE_DATA",
    "accepted_claim": False,
    "data": {"state": "UNAVAILABLE"},
}
_VIEW_HOLD = {
    "schema_version": "decision_view.v2",
    "state": "ACCEPTED_FORECAST_CLAIM",
    "headline": "Accepted forecast-quality claim",
    "accepted_claim": True,
    "data": {"state": "OK"},
}
_VIEW_PERMISSION = {
    "schema_version": "decision_view.v2",
    "state": "DIRECTIONAL_PERMISSION",
    "headline": "Accepted forecast with directional permission",
    "accepted_claim": True,
    "directional_permission": True,
    "data": {"state": "OK"},
}
PERMISSION_FRAME = "(accepted directional permission; not financial advice)"

CASES = {
    "view_ok": {"decision_view": _VIEW_OK},
    "view_degraded": {"decision_view": _VIEW_DEGRADED},
    "view_unavailable": {"decision_view": _VIEW_UNAVAILABLE},
    "no_view": {},  # a run reopened from history: the detail payload carries no view
    # ... and the same run with the gate view the backend built when it read it back (the detail
    # panel hands it to these surfaces on a copy of the history row).
    "reopened": {
        "gate_view": {
            "schema_version": "gate_view.v1",
            "blocked": True,
            "summary": "BACKEND-SUMMARY",
            "framing": "BACKEND-FRAMING",
        }
    },
    "accepted_hold": {"decision_view": _VIEW_HOLD},
    "accepted_permission": {"decision_view": _VIEW_PERMISSION},
}
# Every case but an accepted directional permission keeps "not a market call" (ruling 2026-10-06).
WITHOUT_PERMISSION = [name for name in CASES if name != "accepted_permission"]


def _rendered_cases() -> dict[str, dict[str, object]]:
    keys = list(CASES)
    rendered = _render([CASES[key] for key in keys])
    return dict(zip(keys, rendered, strict=True))


def test_the_final_decision_card_is_always_the_gates_disposition() -> None:
    for name, output in _rendered_cases().items():
        texts = {cls: text for cls, text in output["card"]["texts"]}
        if name in WITHOUT_PERMISSION:
            assert texts["decision-eyebrow"] == "Gate disposition (not a market call)", name
        assert "Backend final decision" not in texts.values(), name


def test_the_decision_brief_is_always_the_gate_brief() -> None:
    for name, output in _rendered_cases().items():
        if name in WITHOUT_PERMISSION:
            assert output["brief"]["sections"][0] == "Gate brief (not a market call)", name
        assert output["brief"]["tables"][0][0] == "Gate disposition", name
        assert "Action" not in output["brief"]["tables"][0], name


def test_the_no_synthesis_fallback_is_the_gate_brief_not_a_call() -> None:
    for name, output in _rendered_cases().items():
        fallback = output["fallback"]
        if name in WITHOUT_PERMISSION:
            assert fallback["sections"][0] == "Gate brief (not a market call)", name
        assert fallback["tables"][0][0] == "Gate disposition", name
        for label in fallback["tables"][0]:
            assert "Existing brief" not in label, name
        notes = dict((cls, text) for cls, text in fallback["texts"])
        assert not any("Decision synthesis unavailable" in text for text in notes.values()), name


def test_no_legacy_surface_words_a_framing_of_its_own() -> None:
    """Review finding D3: the frontend composed three framing sentences. It composes none now:
    no legacy surface prints a sentence about the gates' disposition, whatever the view allows.
    Nor does one print the gate authority: a live analysis shows it in its decision view, and a
    reopened run in its own block. Where a reopened run has that block, its stored summary
    sentence is not shown."""

    cases = _rendered_cases()
    for name, output in cases.items():
        for surface in ("card", "brief", "fallback"):
            texts = [text for _, text in output[surface]["texts"]]
            assert not any("gates' disposition" in str(text) for text in texts), (name, surface)
            assert not any("reason to act" in str(text) for text in texts), (name, surface)
            assert not any(str(text).startswith("BACKEND-") for text in texts), (name, surface)
    reopened, bare = cases["reopened"], cases["no_view"]
    # The stored summary sentence gives way to the read-time framing, and only to it.
    assert "Gate brief summary" not in reopened["fallback"]["tables"][0]
    assert "State summary" not in reopened["brief"]["tables"][0]
    assert "Gate brief summary" in bare["fallback"]["tables"][0]
    assert "State summary" in bare["brief"]["tables"][0]


def test_an_accepted_permission_is_shown_and_stays_non_advisory() -> None:
    """Owner ruling 2026-10-06: an accepted directional permission is shown without "not a
    market call", and every surface stays explicitly non-advisory."""

    output = _rendered_cases()["accepted_permission"]
    card = dict(output["card"]["texts"])
    assert card["decision-eyebrow"] == f"Gate disposition {PERMISSION_FRAME}"
    assert output["brief"]["sections"][0] == f"Gate brief {PERMISSION_FRAME}"
    assert output["fallback"]["sections"][0] == f"Gate brief {PERMISSION_FRAME}"
    shown = [
        *output["card"]["texts"],
        *output["brief"]["texts"],
        *output["fallback"]["texts"],
    ]
    everything = [text for _, text in shown] + [
        *output["brief"]["sections"],
        *output["fallback"]["sections"],
    ]
    assert not any("not a market call" in text for text in everything)
    # Each title and label says it is not financial advice; the sentence that frames the gates
    # under a permission is the backend's (gate_kinds.DIRECTIONAL_PERMISSION_FRAMING).
    for label in (card["decision-eyebrow"], output["brief"]["sections"][0]):
        assert "not financial advice" in label


def test_accepted_evidence_shows_its_accepted_state() -> None:
    """Owner ruling 2026-10-06: under an accepted forecast claim the readiness row shows the
    view's accepted state, never the uncalibrated-heuristic copy; without one it is unchanged."""

    cases = _rendered_cases()
    for name, view in (("accepted_hold", _VIEW_HOLD), ("accepted_permission", _VIEW_PERMISSION)):
        readiness = dict(cases[name]["brief"]["values"][0])["Model readiness"]
        assert readiness == view["headline"], name
    for name in ("view_ok", "view_degraded", "view_unavailable", "no_view", "reopened"):
        assert dict(cases[name]["brief"]["values"][0])["Model readiness"] == "HEURISTIC-COPY", name
