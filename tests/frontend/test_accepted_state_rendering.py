"""Owner ruling 2026-10-06 (review 1 of the ruling, finding 1): under an accepted claim no surface
reads as the uncalibrated heuristic, and under an accepted directional permission none reads as
"not a market call" while each stays explicitly non-advisory.

The whole of app.js runs under Node on a DOM stand-in (not a browser), over real analyses the
backend built with the governed registries patched for the test, and every text a user can read
on the detail panel and the timeframe cards is scanned: not a list of known surfaces. Without an
accepted claim every surface reads as before. Under one, the backend's data (statuses, counts,
verdicts) and the scenario plan's prerequisites are still shown as the backend states them: the
UI defers its evidence-level copy to the view and never rewrites the backend's data.
"""

from __future__ import annotations

import copy
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from crypto_probability_engine.adapters.provider_selection import ProviderSelectionResult
from crypto_probability_engine.api import analysis_service
from crypto_probability_engine.api.schemas import AnalysisRequest
from crypto_probability_engine.config.settings import Settings
from crypto_probability_engine.detail import decision_view
from crypto_probability_engine.detail.decision_brief import (
    DISCLAIMER,
    PROBABILITY_EXPLANATION,
    PROBABILITY_TYPE,
)
from crypto_probability_engine.persistence.run_store import InMemoryRunStore
from tests.fixtures.market_data import make_snapshot

ROOT = Path(__file__).resolve().parents[2]
NODE = shutil.which("node")
METHODOLOGY = analysis_service.METHODOLOGY_VERSION
NO_SKILL = {"verdict": "INSUFFICIENT_EVIDENCE", "n": 0, "observed_directional_rate": None}
SKILL = {"verdict": "SKILL_DEMONSTRATED", "n": 400, "observed_directional_rate": 0.6}
ACCEPTED_DISCLAIMER = "Not financial advice: it never tells you to trade. No profitability claim."

# What would read as the uncalibrated heuristic under an accepted claim (owner ruling 2026-10-06).
HEURISTIC_READING = re.compile(
    r"uncalibrated|heuristic|not measured|not a forecast|not reliability evidence|not validated"
    r"|informational only|\bmuted\b",
    re.IGNORECASE,
)


def _is_heuristic_reading(text: str) -> bool:
    # Not readings: the glossary's term (its definition holds under any claim) and the name of
    # the signal heat score (a heuristic score, not a probability).
    if text == "Heuristic probability" or text.startswith("Heuristic signal heat score:"):
        return False
    return HEURISTIC_READING.search(text) is not None


# A DOM rich enough to load all of app.js and render its surfaces; no backend answers it.
_DOM_STAND_IN = r"""
class FakeText {
  constructor(text) { this.textContent = String(text); this.parent = null; }
}
class FakeElement {
  constructor(tag) {
    this.tagName = String(tag || "div").toUpperCase();
    this.children = [];
    this.parent = null;
    this.className = "";
    this.dataset = {};
    this.attributes = {};
    this.style = { setProperty() {}, removeProperty() {} };
    this.hidden = false;
    this.disabled = false;
    this.value = "";
    this.content = null;
    const self = this;
    this.classList = {
      add(...names) {
        const set = new Set(self.className.split(/\s+/).filter(Boolean));
        for (const name of names) set.add(name);
        self.className = [...set].join(" ");
      },
      remove(...names) {
        const kept = self.className.split(/\s+/).filter((c) => c && !names.includes(c));
        self.className = kept.join(" ");
      },
      toggle(name, force) {
        const want = force === undefined ? !self.classList.contains(name) : Boolean(force);
        if (want) self.classList.add(name); else self.classList.remove(name);
        return want;
      },
      contains(name) { return self.className.split(/\s+/).includes(name); },
    };
  }
  get textContent() { return this.children.map((child) => child.textContent).join(""); }
  set textContent(value) {
    this.children = [];
    const text = value === null || value === undefined ? "" : String(value);
    if (text) this.append(new FakeText(text));
  }
  set innerHTML(value) { this.textContent = String(value).replace(/<[^>]*>/g, " "); }
  get firstElementChild() { return this.children.find((c) => c instanceof FakeElement) || null; }
  append(...nodes) {
    for (const node of nodes) {
      if (node === null || node === undefined) continue;
      const known = node instanceof FakeElement || node instanceof FakeText;
      const child = known ? node : new FakeText(node);
      if (child.parent) child.parent.children = child.parent.children.filter((c) => c !== child);
      child.parent = this;
      this.children.push(child);
    }
  }
  appendChild(node) { this.append(node); return node; }
  insertBefore(node, ref) {
    this.append(node);
    this.children.pop();
    const index = this.children.indexOf(ref);
    if (index < 0) this.children.push(node); else this.children.splice(index, 0, node);
    return node;
  }
  replaceChildren(...nodes) { this.children = []; this.append(...nodes); }
  replaceWith(node) {
    if (!this.parent) return;
    const parent = this.parent;
    parent.children[parent.children.indexOf(this)] = node;
    node.parent = parent;
  }
  remove() {
    if (this.parent) this.parent.children = this.parent.children.filter((c) => c !== this);
  }
  addEventListener() {}
  removeEventListener() {}
  setAttribute(name, value) { this.attributes[name] = String(value); }
  getAttribute(name) { return name in this.attributes ? this.attributes[name] : null; }
  removeAttribute(name) { delete this.attributes[name]; }
  scrollIntoView() {}
  focus() {}
  click() {}
  closest() { return null; }
  matches(selector) {
    return selector.split(",").map((s) => s.trim()).some((one) => {
      if (one.startsWith(".")) return this.classList.contains(one.slice(1));
      if (one.startsWith("#")) return this.attributes.id === one.slice(1);
      if (one.startsWith("[")) return one.slice(1, -1).split("=")[0] in this.attributes;
      return this.tagName === one.toUpperCase();
    });
  }
  querySelectorAll(selector) {
    const found = [];
    const walk = (node) => {
      for (const child of node.children) {
        if (!(child instanceof FakeElement)) continue;
        if (child.matches(selector)) found.push(child);
        walk(child);
      }
    };
    walk(this);
    return found;
  }
  querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }
  cloneNode(deep) {
    const copy = new FakeElement(this.tagName);
    copy.className = this.className;
    copy.dataset = { ...this.dataset };
    copy.attributes = { ...this.attributes };
    if (deep) {
      for (const child of this.children) {
        const element = child instanceof FakeElement;
        copy.append(element ? child.cloneNode(true) : new FakeText(child.textContent));
      }
    }
    return copy;
  }
}
function fakeElement(tag, className = "", children = []) {
  const node = new FakeElement(tag);
  node.className = className;
  node.append(...children);
  return node;
}
// index.html's overview template, as the browser parses it.
const overviewTemplateElement = new FakeElement("template");
overviewTemplateElement.content = fakeElement("fragment", "", [
  fakeElement("article", "result-card", [
    fakeElement("header", "", [
      fakeElement("h2"),
      fakeElement("button", "detail-button", ["Detail"]),
    ]),
    fakeElement("dl"),
    fakeElement("p", "news-note"),
  ]),
]);
const fakeElements = new Map([["#overviewTemplate", overviewTemplateElement]]);
const document = {
  createElement: (tag) => new FakeElement(tag),
  querySelector(selector) {
    if (!fakeElements.has(selector)) {
      const node = new FakeElement("div");
      node.setAttribute("id", selector.replace(/^#/, ""));
      fakeElements.set(selector, node);
    }
    return fakeElements.get(selector);
  },
  querySelectorAll: () => [],
  addEventListener() {},
  body: new FakeElement("body"),
};
const storage = () => {
  const values = new Map();
  return {
    getItem: (key) => (values.has(key) ? values.get(key) : null),
    setItem: (key, value) => values.set(key, String(value)),
    removeItem: (key) => values.delete(key),
  };
};
const localStorage = storage();
const sessionStorage = storage();
const window = globalThis;
window.addEventListener = () => {};
window.location = { href: "http://localhost/", pathname: "/", search: "", hash: "" };
// No backend behind the stand-in: every request fails, as an unreachable backend's does.
globalThis.fetch = () => Promise.reject(new Error("no backend behind the DOM stand-in"));
// The words a user can read under a node; the raw-JSON debug block, which prints the backend
// payload verbatim by design, excepted.
function visibleTexts(node, out = []) {
  for (const child of node.children) {
    if (child instanceof FakeText) {
      if (child.textContent.trim()) out.push(child.textContent.trim());
    } else if (!child.classList.contains("raw-json")) {
      visibleTexts(child, out);
    }
  }
  return out;
}
// The class names under a node: how its surfaces are styled (a card muted as informational).
function classNames(node, out = new Set()) {
  for (const child of node.children) {
    if (child instanceof FakeElement) {
      for (const name of child.className.split(/\s+/).filter(Boolean)) out.add(name);
      classNames(child, out);
    }
  }
  return out;
}
"""

_RENDER = """
(async () => {
  const out = { texts: {}, classes: {} };
  for (const [name, payload] of Object.entries(cases)) {
    renderStructuredDetail(payload, payload.detail_view || {});
    // Let the calibration diagnostics request fail and its fallback render.
    for (let tick = 0; tick < 5; tick += 1) await new Promise((done) => setTimeout(done, 0));
    out.texts[name] = {
      detail: visibleTexts(detailPanel),
      matrix: visibleTexts(fakeElement("div", "", [horizonCard(payload)])),
      overview: visibleTexts(fakeElement("div", "", [overviewCard(payload)])),
    };
    out.classes[name] = [...classNames(detailPanel)];
  }
  // A pipe is written asynchronously: exit only once the whole result is flushed.
  process.stdout.write(JSON.stringify(out), () => process.exit(0));
})();
"""


def _select(symbol, timeframe, *, settings):
    """A live-like market-data selection the analysis cannot tell from a real one (no network)."""

    del settings
    return ProviderSelectionResult(
        snapshot=make_snapshot(provider="okx", symbol=symbol.display, timeframe=timeframe),
        provider_state={
            "status": "OK",
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


def _analysis(timeframe: str, *, claim: bool = False, permission: bool = False) -> dict:
    key = f"{PROBABILITY_TYPE}:{METHODOLOGY}:{timeframe}"
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(analysis_service, "select_market_data", _select)
        evidence = SKILL if permission else NO_SKILL
        patch.setattr(analysis_service, "get_cached_skill_evidence", lambda _tf: dict(evidence))
        accepted = frozenset({key}) if claim or permission else frozenset()
        patch.setattr(decision_view, "ACCEPTED_FORECAST_CLAIMS", accepted)
        permitted = frozenset({key}) if permission else frozenset()
        patch.setattr(decision_view, "ACCEPTED_DIRECTIONAL_PERMISSIONS", permitted)
        if permission:
            # A permission needs clear gates, so the evidence gate's hold is lifted for this one
            # test analysis; the product's hold is untouched.
            patch.setattr(analysis_service, "evidence_for_gate", lambda found: (found, None))
        return analysis_service.analyze_request(
            AnalysisRequest(symbol="BTC/USDT", timeframe=timeframe),
            settings=Settings(data_mode="fixture"),
            run_store=InMemoryRunStore(limit=10),
        )


def _without(payload: dict, key: str) -> dict:
    return {name: value for name, value in payload.items() if name != key}


def _cases() -> dict[str, dict]:
    cases = {
        "today": _analysis("1H"),
        "claim": _analysis("1H", claim=True),
        "permission": _analysis("1H", permission=True),
        "today_1W": _analysis("1W"),
        "claim_1W": _analysis("1W", claim=True),
        "permission_1W": _analysis("1W", permission=True),
    }
    for name in ("today", "claim", "permission"):
        # A payload without a decision synthesis: the gate brief's fallback renders.
        cases[f"{name}_no_synthesis"] = _without(cases[name], "decision_synthesis")
        # A synthesis without its statuses: the missing-status fallbacks render.
        no_status = copy.deepcopy(cases[name])
        for field in ("calibration_status", "reliability_status"):
            no_status["decision_synthesis"]["model_quality_summary"].pop(field)
        cases[f"{name}_no_status"] = no_status
    # A run reopened from history: its payload carries no view.
    cases["history"] = _without(cases["today"], "decision_view")
    return cases


@pytest.fixture(scope="module")
def cases() -> dict[str, dict]:
    return _cases()


@pytest.fixture(scope="module")
def run(cases: dict[str, dict]) -> dict[str, Any]:
    """The detail panel and the timeframe cards of every case, as the real app.js renders them."""

    assert NODE is not None, "node is required to run the real app.js"
    script = "\n".join(
        [
            _DOM_STAND_IN,
            (ROOT / "frontend" / "app.js").read_text(encoding="utf-8"),
            f"const cases = {json.dumps(cases, default=str)};",
            _RENDER,
        ]
    )
    done = subprocess.run(  # noqa: S603 - node on a script built here
        [NODE, "-e", script], capture_output=True, text=True, check=True, timeout=60
    )
    return json.loads(done.stdout)


@pytest.fixture(scope="module")
def rendered(run: dict[str, Any]) -> dict[str, dict[str, list[str]]]:
    return run["texts"]


@pytest.fixture(scope="module")
def styled(run: dict[str, Any]) -> dict[str, list[str]]:
    return run["classes"]


CASES = (
    *("today", "claim", "permission", "today_1W", "claim_1W", "permission_1W"),
    *("today_no_synthesis", "today_no_status", "claim_no_synthesis", "claim_no_status"),
    *("permission_no_synthesis", "permission_no_status", "history"),
)
ACCEPTED = [name for name in CASES if name.startswith(("claim", "permission"))]
PERMISSION = [name for name in CASES if name.startswith("permission")]
WITHOUT_CLAIM = [name for name in CASES if name.startswith(("today", "history"))]


def _value(texts: list[str], *path: str) -> str:
    """The text that follows ``path``'s last label, each label searched after the one before."""

    index = -1
    for label in path:
        index = texts.index(label, index + 1)
    return texts[index + 1]


def _between(texts: list[str], start: str, end: str) -> list[str]:
    first = texts.index(start)
    return texts[first : texts.index(end, first)]


def test_the_analyses_are_the_states_they_claim_to_be(cases: dict[str, dict]) -> None:
    states = {
        "today": "NO_ACCEPTED_CLAIM",
        "claim": "ACCEPTED_FORECAST_CLAIM",
        "permission": "DIRECTIONAL_PERMISSION",
    }
    assert sorted(cases) == sorted(CASES)
    for name, payload in cases.items():
        if name == "history":
            assert "decision_view" not in payload
            continue
        assert payload["decision_view"]["state"] == states[name.split("_")[0]], name
        blocks = payload["gate_result"]["hard_blocks"]
        assert blocks == ([] if name.startswith("permission") else ["SKILL_NOT_DEMONSTRATED"]), name
    # The registries the test patched are empty again: nothing is accepted.
    assert decision_view.ACCEPTED_FORECAST_CLAIMS == frozenset()
    assert decision_view.ACCEPTED_DIRECTIONAL_PERMISSIONS == frozenset()


def test_accepted_evidence_never_reads_as_the_heuristic(rendered: dict) -> None:
    """Every text a user can read, on every surface: none reads as the uncalibrated heuristic."""

    for name in ACCEPTED:
        for surface, texts in rendered[name].items():
            readings = [text for text in texts if _is_heuristic_reading(text)]
            assert readings == [], (name, surface, readings)


def test_the_accepted_state_is_shown_on_every_surface(rendered: dict, cases: dict) -> None:
    for name in ACCEPTED:
        view = cases[name]["decision_view"]
        for surface, texts in rendered[name].items():
            assert view["headline"] in texts, (name, surface)
        detail = rendered[name]["detail"]
        assert _value(detail, "Probability", "Type") == view["headline"], name
        assert _value(detail, "Probability", "Explanation") == view["detail"], name
        assert _value(detail, "State summary") == view["detail"], name
        assert _value(detail, "Disclaimer") == ACCEPTED_DISCLAIMER, name
        assert "Calibration diagnostics unavailable." in detail, name
        if name.endswith("_no_synthesis"):
            assert _value(detail, "Gate brief summary") == view["detail"], name
            continue
        interpretation = _between(detail, "Probability interpretation", "Actionability stack")
        assert view["detail"] in interpretation, name
        quality = _between(detail, "Current status", "Live calibration diagnostics")
        assert quality[1] == view["detail"] and quality[-1] == "No profitability claim.", name
    for name in ("claim_1W", "permission_1W"):
        assert "Advanced probability" in rendered[name]["detail"], name


def test_no_accepted_card_is_muted_as_informational(styled: dict) -> None:
    for name in CASES:
        muted = "probability-informational" in styled[name]
        with_synthesis = not name.endswith("_no_synthesis")
        assert muted == (with_synthesis and name in WITHOUT_CLAIM), name


def test_a_missing_status_is_reported_as_missing_under_an_accepted_claim(rendered: dict) -> None:
    for name in ("claim_no_status", "permission_no_status"):
        detail = rendered[name]["detail"]
        assert "Reliability: Not reported" in detail, name
        assert _value(detail, "Current status", "Calibration status") == "Not reported", name
        assert _value(detail, "Current status", "Reliability status") == "Not reported", name
    detail = rendered["today_no_status"]["detail"]
    assert "Reliability: Not measured yet" in detail
    assert _value(detail, "Current status", "Calibration status") == "Not measured yet"


def test_a_permission_is_shown_without_a_market_call_and_stays_non_advisory(
    rendered: dict,
) -> None:
    for name in PERMISSION:
        for surface, texts in rendered[name].items():
            assert not any("not a market call" in text.lower() for text in texts), (name, surface)
            assert any("not financial advice" in text.lower() for text in texts), (name, surface)
    # An accepted forecast claim carries no directional permission: still never a market call.
    for name in (name for name in ACCEPTED if name not in PERMISSION):
        assert "Gate disposition (not a market call)" in rendered[name]["overview"], name


def test_without_an_accepted_claim_every_surface_reads_as_before(
    rendered: dict, cases: dict
) -> None:
    """Each legacy text the accepted state replaces is still shown, exactly, without one."""

    for name in WITHOUT_CLAIM:
        detail = rendered[name]["detail"]
        brief = cases[name]["decision_brief"]
        assert _value(detail, "Probability", "Type") == PROBABILITY_TYPE, name
        assert _value(detail, "Probability", "Explanation") == PROBABILITY_EXPLANATION, name
        assert _value(detail, "State summary") == brief["state_summary"], name
        assert _value(detail, "Disclaimer") == DISCLAIMER, name
        assert "Calibration diagnostics unavailable. Keep using heuristic status." in detail, name
        if name.endswith("_no_synthesis"):
            assert _value(detail, "Gate brief summary") == brief["state_summary"], name
            assert "Model quality: not measured yet." in detail, name
            assert "Probabilities are heuristic until enough resolved samples exist." in detail
            continue
        synthesis = cases[name]["decision_synthesis"]
        probability = synthesis["probability_interpretation"]
        interpretation = _between(detail, "Probability interpretation", "Actionability stack")
        assert interpretation[1] == "Informational only", name
        assert probability["plain_english"] in interpretation, name
        assert probability["reliability_warning"] in interpretation, name
        quality = _between(detail, "Current status", "Live calibration diagnostics")
        assert quality[1] == synthesis["model_quality_summary"]["warning"], name
        assert probability["reliability_warning"] in quality, name
        assert quality[-1] == (
            "Keep collecting samples; this is not reliability evidence and not profitability "
            "evidence."
        ), name
        assert "Why probability is muted" in detail, name
    assert "Advanced heuristic probability" in rendered["today_1W"]["detail"]


def test_the_backend_data_is_shown_as_the_backend_states_it(rendered: dict) -> None:
    """The UI never rewrites data: the statuses the backend reports (a fixed baseline today) and
    the scenario plan's prerequisites read the same with or without an accepted claim. Making a
    claim reachable must make the backend's own data and copy agree with it."""

    for name in ("claim", "permission"):
        detail = rendered[name]["detail"]
        assert _value(detail, "Current status", "Calibration status") == "DEFAULT_PHASE1A", name
        assert _value(detail, "Current status", "Reliability status") == "INSUFFICIENT_SAMPLE"
        assert "Reliability: INSUFFICIENT_SAMPLE" in detail, name
        safety = _between(detail, "Safety notes", "Advanced context · Future Quant V2")
        assert safety == _between(
            rendered["today"]["detail"], "Safety notes", "Advanced context · Future Quant V2"
        ), name
