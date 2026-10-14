"""Alert styles and the Decision view's layout (owner rulings X1 and X2, the release-prep lane).

Colour is a signal too. Every card used to lead with a red "BLOCK / Hard gates" banner, and the
stack's blocking checks were red, even when only the evidence gate was active. The style of every
banner, pill and status that restates the gate result is now ONE CSS class, picked by app.js from
the kinds the backend's gate view names (`decision_view.gates.kinds`; `saved_run_view.gates.kinds`
for a reopened run):

- gate-alert-risk     a risk gate with a measured finding (the red there was);
- gate-alert-safety   a system or data gate and no risk gate (a dashed border of its own hue);
- gate-alert-neutral  everything else: the evidence gate alone, a liquidity gate whose stored
                      measurement a reopened run cannot read, no gate, no view. Never red or amber.

The goldens are text, so the class is pinned here: for every scenario of the whole-screen generator
and every surface, by rendering the real app.js and reading the classes off the elements. The
stylesheet's rules for the three classes, and for the Decision view's own lines, are pinned too.
"""

from __future__ import annotations

import copy
import json
import os
import re
import subprocess

import fullscreen_goldens as goldens
import pytest

from crypto_probability_engine.detail import saved_run_view
from crypto_probability_engine.utils.sanitize import sanitize_for_export
from scripts.ux_comprehension import card
from tests.fixtures.market_data import FIXED_NOW

harness = goldens.harness
ROOT = harness.ROOT
NEUTRAL, RISK, SAFETY = "gate-alert-neutral", "gate-alert-risk", "gate-alert-safety"
# The class of every scenario, from the kinds its gate view names: risk wins over safety/data,
# which wins over the evidence gate.
EXPECTED = {
    "evidence_only": NEUTRAL,
    "risk_and_evidence": RISK,
    "wide_spread_and_evidence": RISK,
    "unusable_order_book_and_evidence": SAFETY,
    "missing_order_book_and_evidence_SYNTHETIC": SAFETY,
    "kill_switch_and_evidence_SYNTHETIC": SAFETY,
    "storage_OK": NEUTRAL,
    "storage_STATELESS": NEUTRAL,
    "storage_UNAVAILABLE": NEUTRAL,
    "risk_only_SYNTHETIC": RISK,
    "missing_order_book_only_SYNTHETIC": SAFETY,
    "system_only_SYNTHETIC": SAFETY,
    "first_check_blocks_SYNTHETIC": NEUTRAL,
    "accepted_claim_SYNTHETIC": NEUTRAL,
    "permission_SYNTHETIC": NEUTRAL,
}

# Every element that carries an alert class, on every surface: its alert class(es), its other
# classes (what it is) and the start of its text.
_COLLECT = """
(async () => {
  const collect = (node, out = []) => {
    for (const child of node.children || []) {
      if (!(child instanceof FakeElement)) continue;
      const classes = String(child.className || "").split(/\\s+/).filter(Boolean);
      const alert = classes.filter((name) => name.startsWith("gate-alert-"));
      const role = classes.filter((name) => !name.startsWith("gate-alert-")).join(" ");
      if (alert.length || role.includes("decision-badge") || role.includes("actionability-row ")) {
        out.push({ alert, role, text: child.textContent.slice(0, 48) });
      }
      collect(child, out);
    }
    return out;
  };
  const panel = async (payload, detail) => {
    calibrationDiagnosticsCache = null;
    calibrationDiagnosticsCachedAt = 0;
    renderStructuredDetail(payload, detail);
    for (let tick = 0; tick < 5; tick += 1) await new Promise((done) => setTimeout(done, 0));
    return collect(detailPanel);
  };
  const out = {};
  for (const [name, payload] of Object.entries(cases)) {
    out[name] = {
      single: collect(fakeElement("div", "", [horizonCard(payload)])),
      batch: collect(fakeElement("div", "", [overviewCard(payload)])),
      detail: await panel(payload, details[name]),
    };
  }
  for (const [name, item] of Object.entries(reopened)) {
    out[name] = { ...(out[name] || {}), history: await panel(item.row, item.detail) };
  }
  process.stdout.write(JSON.stringify(out), () => process.exit(0));
})();
"""


def styled(
    cases: dict[str, dict], reopened: dict[str, dict], details: dict[str, dict] | None = None
) -> dict[str, dict[str, list[dict]]]:
    """Scenario -> surface -> the styled elements of that screen, as the real app.js draws it.
    `details` is the detail each live case's panel is given (the route's own, unless given)."""

    script = "\n".join(
        [
            goldens.frozen_clock(FIXED_NOW),
            harness._DOM_STAND_IN,
            (ROOT / "frontend" / "app.js").read_text(encoding="utf-8"),
            f"const cases = {goldens._js(cases)};",
            f"const details = {goldens._js(details or goldens.live_details(cases))};",
            f"const reopened = {goldens._js(reopened)};",
            _COLLECT,
        ]
    )
    done = subprocess.run(  # noqa: S603 - node on a script built here, read on stdin
        [harness.NODE, "-"],
        input=script,
        capture_output=True,
        encoding="utf-8",
        env={**os.environ, "TZ": "UTC"},
        timeout=120,
        check=True,
    )
    return json.loads(done.stdout)


@pytest.fixture(scope="module")
def cases() -> dict[str, dict]:
    return goldens.build_cases()


@pytest.fixture(scope="module")
def reopened(cases: dict[str, dict]) -> dict[str, dict]:
    return goldens.build_reopened(cases)


@pytest.fixture(scope="module")
def drawn(cases: dict[str, dict], reopened: dict[str, dict]) -> dict[str, dict[str, list[dict]]]:
    return styled(cases, reopened)


def _class_from_kinds(kinds: list[str]) -> str:
    if "RISK" in kinds:
        return RISK
    return SAFETY if "SYSTEM_OR_DATA" in kinds else NEUTRAL


def test_every_scenario_of_the_generator_has_its_class_here(cases: dict, reopened: dict) -> None:
    assert set(EXPECTED) == set(goldens.SCENARIOS) == set(cases)
    for name, payload in cases.items():
        kinds = payload["decision_view"]["gates"]["kinds"]
        assert EXPECTED[name] == _class_from_kinds(kinds), (name, kinds)
        if name in reopened:
            saved = reopened[name]["detail"]["saved_run_view"]["gates"]["kinds"]
            assert _class_from_kinds(saved) == EXPECTED[name], (name, saved)
    # Each of the three classes is the class of a scenario that can occur today.
    today = {EXPECTED[name] for name in EXPECTED if not name.endswith("_SYNTHETIC")}
    assert today == {NEUTRAL, RISK, SAFETY}


@pytest.mark.parametrize("name", list(EXPECTED))
def test_the_alert_class_of_every_surface_is_the_backends_kind(drawn: dict, name: str) -> None:
    """Owner ruling X2, pinned per scenario and surface. Every element that restates the gate
    result carries exactly one alert class, and it is the scenario's: the Single card's banner
    and its BLOCK pill, the gate summary and its framing on every surface, and on the detail
    panel every check of the stack that blocks, with its pill. Nothing else is restyled: a check
    that passes, warns or informs keeps its own style and carries no alert class."""

    expected = EXPECTED[name]
    surfaces = drawn[name]
    assert set(surfaces) == {"single", "batch", "detail"} | (
        {"history"} if name in goldens.HISTORY else set()
    )
    for surface, elements in surfaces.items():
        carrying = [element for element in elements if element["alert"]]
        assert carrying, f"{name}/{surface}: the gate summary is on every screen"
        for element in carrying:
            assert element["alert"] == [expected], (name, surface, element)
        roles = [element["role"] for element in carrying]
        # The summary and its framing are one group: both, once, with the same class.
        assert roles.count("decision-gates") == 1, (name, surface)
        assert roles.count("decision-gate-framing") == 1, (name, surface)
        at = roles.index("decision-gates")
        assert roles[at + 1] == "decision-gate-framing", "directly under it"
    blocked = name != "permission_SYNTHETIC"
    banner = [e for e in surfaces["single"] if e["role"] == "matrix-block-banner"]
    assert len(banner) == (1 if blocked else 0), name
    pills = [e for e in surfaces["single"] if e["role"] == "decision-badge decision-badge-block"]
    assert [pill["alert"] for pill in pills] == ([[expected]] if blocked else [])
    assert all(pill["text"] == "BLOCK" for pill in pills), "the word on the pill is what it was"
    # The detail panel's stack: every check that blocks, and only those.
    rows = [e for e in surfaces["detail"] if e["role"].startswith("actionability-row ")]
    assert len(rows) == 11, f"{name}: the stack's eleven checks"
    for row in rows:
        blocks = row["role"] == "actionability-row actionability-block"
        assert row["alert"] == ([expected] if blocks else []), (name, row)
    badges = [e for e in surfaces["detail"] if e["role"].startswith("decision-badge ")]
    for badge in badges:
        blocks = badge["role"] == "decision-badge decision-badge-block"
        assert badge["alert"] == ([expected] if blocks else []), (name, badge)
        assert (badge["text"] == "BLOCK") is blocks, badge
    assert any(row["alert"] for row in rows) is blocked, name
    # The cards of the batch screen have no banner and no pill: the summary alone.
    assert {e["role"] for e in surfaces["batch"] if e["alert"]} == {
        "decision-gates",
        "decision-gate-framing",
    }


def test_a_screen_with_nothing_to_read_is_neutral_and_never_the_risk_style(
    cases: dict, reopened: dict
) -> None:
    """An analysis without a view, a reopened run whose gate result cannot be read, and a
    reopened run whose liquidity gate has no readable measurement get the neutral style. A view
    of an unknown version is not read either. None of them is ever drawn in the risk style."""

    base = cases["risk_and_evidence"]
    no_view = {key: value for key, value in base.items() if key != "decision_view"}
    other_version = copy.deepcopy(base)
    other_version["decision_view"]["gates"]["schema_version"] = "gate_view.v2"

    def stored(scenario: str, change) -> dict:
        detail = sanitize_for_export(copy.deepcopy(cases[scenario]["detail_view"]))
        change(detail)
        return {
            "row": reopened[scenario]["row"],
            "detail": saved_run_view.attach_saved_run_view(detail),
        }

    def liquidity_gate_without_its_state(detail: dict) -> None:
        detail["invalidation_detail"]["hard_blocks"] = [
            "LIQUIDITY_NOT_VIABLE",
            "SKILL_NOT_DEMONSTRATED",
        ]
        detail["liquidity_execution_detail"].pop("liquidity_state")

    damaged = {
        "gate_empty": stored("risk_and_evidence", lambda d: d.update(invalidation_detail={})),
        "liquidity_not_readable": stored("evidence_only", liquidity_gate_without_its_state),
    }
    # (The two live payloads' panels are given no detail: with one, a payload without a view
    # would be drawn as a reopened run, from its saved view. No such screen is served.)
    live = {"no_view": no_view, "other_version": other_version}
    drawn = styled(live, damaged, details={name: {"run_id": "x"} for name in live})
    for name in ("no_view", "other_version"):
        for surface, elements in drawn[name].items():
            alerts = {tuple(element["alert"]) for element in elements if element["alert"]}
            assert alerts <= {(NEUTRAL,)}, (name, surface, alerts)
        banner = [e for e in drawn[name]["single"] if e["role"] == "matrix-block-banner"]
        assert [e["alert"] for e in banner] == [[NEUTRAL]], f"{name}: the banner, neutral"
        blocking = [
            e for e in drawn[name]["detail"] if e["role"] == "actionability-row actionability-block"
        ]
        assert blocking and all(e["alert"] == [NEUTRAL] for e in blocking), name
    # A gate result that cannot be read has no summary to style: the backend's note stands in its
    # place, and it alone carries a class, the neutral one (the release-prep review's minor M-4:
    # it was drawn amber). Drawn with the amber warning class, or the risk one, it fails here.
    note = [e for e in drawn["gate_empty"]["history"] if e["alert"]]
    assert note == [
        {
            "alert": [NEUTRAL],
            "role": "decision-gate-note",
            "text": saved_run_view.GATES_NOT_READABLE[:48],
        }
    ]
    unreadable = damaged["liquidity_not_readable"]["detail"]["saved_run_view"]["gates"]
    assert unreadable["kinds"] == ["EVIDENCE", "NOT_READABLE"]
    alerts = [e["alert"] for e in drawn["liquidity_not_readable"]["history"] if e["alert"]]
    assert alerts == [[NEUTRAL], [NEUTRAL]], "the summary and its framing, neutral"


def test_the_class_is_read_from_the_kinds_and_risk_wins_over_safety_over_evidence() -> None:
    """Owner ruling X2: "more than one kind: risk wins over safety/data, which wins over
    evidence". The function itself, cut out of app.js and asked about every combination; a gate
    view of a version this script does not know, or one that is no gate view, is neutral."""

    source = (ROOT / "frontend" / "app.js").read_text(encoding="utf-8")
    code = "\n".join(
        card._extract(source, name) for name in ("GATE_ALERT_CLASSES", "gateView", "gateAlertClass")
    )
    asked = {
        "evidence": ["EVIDENCE"],
        "none": [],
        "not_readable": ["EVIDENCE", "NOT_READABLE"],
        "risk": ["RISK"],
        "risk_and_evidence": ["EVIDENCE", "RISK"],
        "safety": ["SYSTEM_OR_DATA"],
        "safety_and_evidence": ["EVIDENCE", "SYSTEM_OR_DATA"],
        "risk_and_safety": ["RISK", "SYSTEM_OR_DATA"],
        "all_three": ["EVIDENCE", "RISK", "SYSTEM_OR_DATA"],
        "risk_and_not_readable": ["NOT_READABLE", "RISK"],
        "an_unknown_kind": ["SOMETHING_NEW"],
    }
    views = {
        name: {"schema_version": "gate_view.v1", "kinds": kinds} for name, kinds in asked.items()
    }
    views["another_version"] = {"schema_version": "gate_view.v2", "kinds": ["RISK"]}
    views["no_version"] = {"kinds": ["RISK"]}
    views["kinds_not_a_list"] = {"schema_version": "gate_view.v1", "kinds": "RISK"}
    views["nothing"] = None
    script = (
        f"{code}\nconst views = {json.dumps(views)};\n"
        "const out = Object.fromEntries(Object.entries(views).map(([n, v]) => "
        "[n, gateAlertClass(v)]));\nprocess.stdout.write(JSON.stringify(out));"
    )
    done = subprocess.run(  # noqa: S603 - node on a script built here, read on stdin
        [harness.NODE, "-"],
        input=script,
        capture_output=True,
        encoding="utf-8",
        timeout=60,
        check=True,
    )
    assert json.loads(done.stdout) == {
        "evidence": NEUTRAL,
        "none": NEUTRAL,
        "not_readable": NEUTRAL,
        "risk": RISK,
        "risk_and_evidence": RISK,
        "safety": SAFETY,
        "safety_and_evidence": SAFETY,
        "risk_and_safety": RISK,
        "all_three": RISK,
        "risk_and_not_readable": RISK,
        "an_unknown_kind": NEUTRAL,
        "another_version": NEUTRAL,
        "no_version": NEUTRAL,
        "kinds_not_a_list": NEUTRAL,
        "nothing": NEUTRAL,
    }


def test_a_risk_gate_beside_a_system_gate_is_drawn_in_the_risk_style(reopened: dict) -> None:
    """The same precedence on real screens: a measured tail-risk breach beside the kill switch
    (SYNTHETIC), and beside an order book the measure refuses (reachable today)."""

    both = {
        "tail_and_kill_SYNTHETIC": goldens._analysis(tail=True, kill=True),
        "tail_and_unusable_book": goldens._analysis(tail=True, book="unusable"),
    }
    for payload in both.values():
        assert payload["decision_view"]["gates"]["kinds"] == ["EVIDENCE", "RISK", "SYSTEM_OR_DATA"]
    drawn = styled(both, {})
    for name, surfaces in drawn.items():
        for surface, elements in surfaces.items():
            alerts = {tuple(element["alert"]) for element in elements if element["alert"]}
            assert alerts == {(RISK,)}, (name, surface, alerts)


def _rules(css: str) -> dict[str, str]:
    """Selector -> declarations, for the plain rules of the stylesheet (media blocks apart)."""

    rules: dict[str, str] = {}
    for selectors, body in re.findall(
        r"([^{}]+)\{([^{}]*)\}", re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    ):
        for selector in selectors.split(","):
            name = " ".join(selector.split())
            rules[name] = rules.get(name, "") + " ".join(body.split())
    return rules


def test_the_neutral_style_is_neutral_and_the_three_differ_without_colour() -> None:
    """Colour is a signal. The neutral style uses the page's grey and text colours only: no red,
    no amber, no glow. The three are told apart by their border alone: thin and solid (neutral),
    thick and solid (risk), dashed (safety/data), so no reader depends on telling hues apart.
    The safety/data hue is its own: not the danger red, the warning amber, or any status colour."""

    css = (ROOT / "frontend" / "styles.css").read_text(encoding="utf-8")
    rules = _rules(css)
    root = rules[":root"]
    colours = dict(re.findall(r"--([a-z]+): (#[0-9a-f]{6});", root))
    assert colours["safety"] == "#a9b8ff"
    assert (
        len({colours[name] for name in ("safety", "danger", "warning", "cyan", "green", "muted")})
        == 6
    )
    alarm = ("--danger", "--warning", "255, 77, 77", "255, 209, 102", "#ff4d4d", "#ffd166")
    surfaces = (".matrix-block-banner", ".decision-badge-block", ".actionability-block")
    for surface in surfaces:
        neutral, safety = rules[f"{surface}.{NEUTRAL}"], rules[f"{surface}.{SAFETY}"]
        for colour in alarm:
            assert colour not in neutral, (surface, colour)
            assert colour not in safety, (surface, colour)
        assert re.search(r"border: 1px solid var\(--(line|muted)\);", neutral), surface
        assert "dashed var(--safety)" in safety, surface
        assert f"{surface}.{RISK}" not in rules, "the risk style is the style there was"
        assert "var(--danger)" in rules[surface], surface
    # No glow on the neutral or the safety banner and check; the risk ones keep theirs.
    for surface in (".matrix-block-banner", ".actionability-block"):
        assert "box-shadow: none;" in rules[f"{surface}.{NEUTRAL}"]
        assert "box-shadow: none;" in rules[f"{surface}.{SAFETY}"]
        assert "box-shadow: 0 0" in rules[surface]
    assert "border: 2px solid var(--danger);" in rules[".matrix-block-banner"]
    assert "border-width: 2px;" in rules[".actionability-block"]
    # The summary and its framing: one bar down the left edge, in the class's own style.
    for line in (".decision-gates", ".decision-gate-framing"):
        assert rules[f"{line}.{NEUTRAL}"] == "border-left: 3px solid var(--line);"
        assert rules[f"{line}.{RISK}"] == "border-left: 3px solid var(--danger);"
        assert rules[f"{line}.{SAFETY}"] == "border-left: 3px dashed var(--safety);"
    # The note of a reopened run whose gate result cannot be read: the neutral bar, the page's
    # text colour, and no alarm colour (minor M-4). It has no risk or safety style at all.
    note = rules[".decision-gate-note"] + rules[f".decision-gate-note.{NEUTRAL}"]
    for colour in alarm:
        assert colour not in note, colour
    assert "border-left: 3px solid var(--line);" in rules[".decision-gate-note"]
    assert "color: var(--text);" in rules[".decision-gate-note"]
    assert rules[f".decision-gate-note.{NEUTRAL}"] == "border-left: 3px solid var(--line);"
    styled_notes = {name for name in rules if name.startswith(".decision-gate-note.gate-alert-")}
    assert styled_notes == {f".decision-gate-note.{NEUTRAL}"}
    # Readable on the dark page: the neutral and safety pills are light text on a faint fill.
    assert "color: var(--text);" in rules[f".decision-badge-block.{NEUTRAL}"]
    assert "color: var(--safety);" in rules[f".decision-badge-block.{SAFETY}"]
    assert "color-scheme: dark;" in root


def test_the_decision_views_lines_have_a_layout_of_their_own() -> None:
    """Owner ruling X1. In a browser the view's headline, its sentence, the gate summary, the
    framing and the gate list ran together as one block of same-weight text: none of those
    classes had a rule. Each now has one, and app.js gives every such line its class. Layout
    only: no rule adds text (`content:`), hides a line or reorders one."""

    css = (ROOT / "frontend" / "styles.css").read_text(encoding="utf-8")
    js = (ROOT / "frontend" / "app.js").read_text(encoding="utf-8")
    rules = _rules(css)
    headline = rules[".decision-headline"]
    assert "font-weight: 700;" in headline and "font-size: 15px;" in headline
    sentence = rules[".decision-detail"]
    assert "margin: 0 0 12px;" in sentence and "font-size: 13px;" in sentence
    summary, framing = rules[".decision-gates"], rules[".decision-gate-framing"]
    assert "border-left: 3px solid var(--line);" in summary, "the bar they share"
    assert "margin: 0;" in summary and "margin-bottom: 12px;" in framing, "no gap between the two"
    assert "font-weight: 700;" in summary and "color: var(--muted);" in framing
    listed = rules[".decision-gate-list"]
    assert "list-style: disc outside;" in listed and "padding-left: 22px;" in listed
    assert "margin: 0 0 6px;" in rules[".decision-gate-list li"]
    for selector in (
        ".decision-headline",
        ".decision-detail",
        ".decision-gates",
        ".decision-gate-list li",
    ):
        assert "overflow-wrap: anywhere;" in rules[selector], f"{selector}: nothing overflows"
    assert (
        "overflow-wrap: anywhere;" in rules[".detail-kv dd"]
        and "min-width: 0;" in rules[".detail-kv dt"]
    )
    added = re.sub(
        r"/\*.*?\*/", "", css[css.index("/* The Decision view's own lines") :], flags=re.S
    )
    for forbidden in ("content:", "display: none", "visibility:", "::before", "::after"):
        assert forbidden not in added, forbidden
    assert not re.search(r"(?<![-\w])order:", added), "no line is reordered"
    # Every line of the view is given its class by app.js, on the cards and on the panel.
    assert js.count('"decision-headline"') == 3 and js.count('"decision-detail"') >= 3
    assert "`decision-gates ${alert}`" in js and "`decision-gate-framing ${alert}`" in js
    assert 'list.classList.add("decision-gate-list");' in js
    assert 'textBlock("p", view.detail, "decision-detail"),' in js
