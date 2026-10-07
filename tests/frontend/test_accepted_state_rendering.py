"""Owner ruling 2026-10-06 (review 1 of the ruling, finding 1): under an accepted claim no surface
reads as the uncalibrated heuristic, and under an accepted directional permission none reads as
"not a market call" while each stays explicitly non-advisory.

The whole of app.js runs under Node on a DOM stand-in (not a browser), over real analyses the
backend built with the governed registries patched for the test. Every text a user can read is
scanned, not a list of known surfaces:
- the detail panel, with the calibration diagnostics both failing and answering (review 2);
- the timeframe card and the overview card.
Three checks hold under an accepted claim:
- No text reads as the heuristic (a denylist).
- The legacy evidence-level copy is gone, whatever its wording.
- Beside today's render of the same analysis, the only new texts are the accepted state's copy,
  and every evidence-related text that stays is the backend's own data or copy, or a listed UI
  text.
Without an accepted claim every surface reads as before. The backend's data (statuses, counts,
verdicts), the gates, the scenario plan's prerequisites and the diagnostics endpoint's items are
shown as the backend states them: the UI defers its evidence-level copy to the view and never
rewrites the backend's data.
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
from crypto_probability_engine.api import analysis_service, calibration_endpoint
from crypto_probability_engine.api.schemas import AnalysisRequest, CalibrationResponse
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
ACCEPTED_DIAGNOSTICS = "Diagnostic only — not profitability evidence, not trade EV."
# The UI's own texts under an accepted claim (frontend/app.js), beside the view's.
ACCEPTED_UI_TEXTS = {
    ACCEPTED_DISCLAIMER,
    ACCEPTED_DIAGNOSTICS,
    "Not reported",
    "Reliability: Not reported",
    "Advanced probability",
    "Calibration diagnostics unavailable.",
    "The gates' disposition: hard gates outrank everything shown.",
}

# What would read as the uncalibrated heuristic under an accepted claim (owner ruling 2026-10-06).
HEURISTIC_READING = re.compile(
    r"uncalibrated|heuristic|not measured|not a forecast|not reliability evidence|not validated"
    r"|informational only|\bmuted\b|not accuracy|early diagnostic",
    re.IGNORECASE,
)
# The legacy copy that defers to the view under an accepted claim, whatever its wording.
DEFERRED = (
    ("decision_brief", "probability_type"),
    ("decision_brief", "state_summary"),
    ("decision_brief", "disclaimer"),
    ("frontend_display", "probability_explanation"),
    ("frontend_display", "model_readiness_label"),
    ("decision_synthesis", "probability_interpretation", "plain_english"),
    ("decision_synthesis", "probability_interpretation", "reliability_warning"),
    ("decision_synthesis", "model_quality_summary", "warning"),
    ("decision_synthesis", "advisor_explanations", "why_probability_is_muted"),
)
# Evidence-related wording: a text with it that stays under an accepted claim must be accounted for.
EVIDENCE_WORDING = re.compile(
    r"heuristic|calibrat|reliab|accura|measur|diagnos|validat|forecast|informational|muted"
    r"|sample|skill|guarantee|estimate|uncertain|confiden|proven|demonstrat|early",
    re.IGNORECASE,
)
# The UI's own texts with such wording that rightly stay under any claim: row and section labels,
# the model-quality glossary (true under any claim), and the claim-only titles that keep "not a
# market call" (an accepted forecast claim carries no directional permission).
STATE_INDEPENDENT_UI_TEXTS = {
    *("Calibration", "Calibration status", "Reliability", "Reliability status"),
    *("Reliability available", "Evidence", "Evidence level", "Why reliability is insufficient"),
    *("Live calibration diagnostics", "Read-only diagnostic", "news evidence"),
    "Invalidation Conditions",
    "Per-timeframe calibration diagnostics",
    "Resolved-sample metrics are not surfaced in this view yet.",
    *("Heuristic probability", "Insufficient sample", "Measured calibration"),
    "An early estimate produced before measured calibration is established.",
    "A comparison between forecast probabilities and resolved outcomes after the sample gate "
    "is met.",
    "Average squared probability error; interpret only with a comparable resolved sample.",
    "A probability error measure that weighs confidently wrong forecasts more heavily.",
    "How often the highest-probability label matched the resolved outcome; it is not a complete "
    "quality measure.",
    "Probability quality also depends on calibration, sample size, outcome mix, and evaluation "
    "context.",
    "Forecast diagnostics do not include execution costs, sizing, or realized returns.",
    *("Gate brief (not a market call)", "Gate disposition (not a market call)"),
}


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
// No backend behind the stand-in: every request fails, as an unreachable backend's does, except
// the calibration diagnostics when the test gives their answer.
let calibrationAnswer = null;
globalThis.fetch = (path) =>
  String(path).startsWith("/v1/calibration") && calibrationAnswer
    ? Promise.resolve({ ok: true, json: async () => structuredClone(calibrationAnswer) })
    : Promise.reject(new Error("no backend behind the DOM stand-in"));
// The words a user can read under a node, except under the classes skipped: the raw-JSON debug
// block prints the backend payload verbatim by design.
function visibleTexts(node, skipped = ["raw-json"], out = []) {
  for (const child of node.children) {
    if (child instanceof FakeText) {
      if (child.textContent.trim()) out.push(child.textContent.trim());
    } else if (!skipped.some((name) => child.classList.contains(name))) {
      visibleTexts(child, skipped, out);
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
  const out = { texts: {}, classes: {}, cards: {} };
  // The per-timeframe diagnostics cards are the endpoint's items, read separately.
  const skipped = ["raw-json", "calibration-timeframe-card"];
  for (const [name, payload] of Object.entries(cases)) {
    const texts = {};
    for (const [surface, answer] of [["detail", null], ["detail_diagnostics", diagnostics]]) {
      calibrationAnswer = answer;
      calibrationDiagnosticsCache = null;
      calibrationDiagnosticsCachedAt = 0;
      renderStructuredDetail(payload, payload.detail_view || {});
      // Let the diagnostics request settle (fail, or answer) and its result render.
      for (let tick = 0; tick < 5; tick += 1) await new Promise((done) => setTimeout(done, 0));
      texts[surface] = visibleTexts(detailPanel, skipped);
    }
    out.cards[name] = detailPanel
      .querySelectorAll(".calibration-timeframe-card")
      .map((card) => visibleTexts(card));
    texts.matrix = visibleTexts(fakeElement("div", "", [horizonCard(payload)]));
    texts.overview = visibleTexts(fakeElement("div", "", [overviewCard(payload)]));
    out.texts[name] = texts;
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


def _diagnostics() -> dict:
    """The calibration endpoint's answer, made by its own mapper with no database. The analyses'
    timeframes are MEASURED, as a backend that agrees with an acceptance would report them; the
    others are still sampling."""

    items = []
    for timeframe in calibration_endpoint.SUPPORTED_TIMEFRAMES:
        measured = timeframe in ("1H", "1W")
        count = 400 if measured else 40
        report = {
            "sample_count": count,
            "valid_count": count,
            "sample_gate": "MEASURED" if measured else "INSUFFICIENT_SAMPLE",
            "metrics": (
                {"brier_score": 0.61, "log_loss": 1.02, "top_label_hit_rate": 0.44}
                if measured
                else {}
            ),
            "outcome_distribution": {"UP": count // 2, "DOWN": count // 4, "TIMEOUT": count // 4},
            "versions_present": {"model_versions": ["v1"], "methodology_versions": [METHODOLOGY]},
        }
        items.append(
            calibration_endpoint._map_timeframe_item(timeframe, report, include_buckets=False)
        )
    response = CalibrationResponse(
        status="OK",
        repository="FIXTURE",
        generated_at="2026-10-07T00:00:00Z",
        timeframes=items,
    )
    return response.model_dump(mode="json")


def _strings(value: Any) -> set[str]:
    if isinstance(value, str):
        return {value.strip()}
    items = value.values() if isinstance(value, dict) else value if isinstance(value, list) else ()
    return set().union(*(_strings(item) for item in items))


def _deferred(payload: dict) -> set[str]:
    values = set()
    for path in DEFERRED:
        value: Any = payload
        for key in path:
            value = value.get(key) if isinstance(value, dict) else None
        if isinstance(value, str) and value.strip():
            values.add(value.strip())
    return values


def _backend_says(text: str, payload: dict) -> bool:
    """Whether a text is the backend's own data or copy, as the UI renders it."""

    if text in _strings(payload) - _deferred(payload) or text.startswith(("{", "Evidence: ")):
        return True
    view = payload.get("decision_view") or {}
    evidence = view.get("evidence") or {}
    reasons = (payload.get("frontend_display") or {}).get("blocking_reasons") or []
    return text in {
        f"{evidence.get('skill_verdict')} · {evidence.get('resolved_outcomes')} resolved outcomes"
        f" · {evidence.get('reliability_status')}",
        *(f"{reason.get('headline')}: {reason.get('detail')}" for reason in reasons),
        *(f"Reliability: {status}" for status in _strings(payload)),
    }


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
            f"const diagnostics = {json.dumps(_diagnostics())};",
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


@pytest.fixture(scope="module")
def diagnostics_cards(run: dict[str, Any]) -> dict[str, list[list[str]]]:
    return run["cards"]


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
        probability = _between(detail, "Probability", "Risk / Gates")
        # The Model readiness row states the accepted state; no Type row repeats it.
        assert "Type" not in probability, name
        assert _value(probability, "Model readiness") == view["headline"], name
        assert _value(probability, "Explanation") == view["detail"], name
        assert _value(detail, "State summary") == view["detail"], name
        assert _value(detail, "Disclaimer") == ACCEPTED_DISCLAIMER, name
        assert "Calibration diagnostics unavailable." in detail, name
        assert ACCEPTED_DIAGNOSTICS in rendered[name]["detail_diagnostics"], name
        if name.endswith("_no_synthesis"):
            assert _value(detail, "Gate brief summary") == view["detail"], name
            continue
        interpretation = _between(detail, "Probability interpretation", "Actionability stack")
        assert view["detail"] in interpretation, name
        quality = _between(detail, "Current status", "Live calibration diagnostics")
        assert quality[1] == view["detail"] and quality[-1] == "No profitability claim.", name
    for name in ("claim_1W", "permission_1W"):
        assert "Advanced probability" in rendered[name]["detail"], name


def test_the_legacy_evidence_copy_never_survives_an_accepted_claim(
    rendered: dict, cases: dict
) -> None:
    """Review 2: a denylist cannot know every wording. Whatever its words, the legacy copy that
    defers is gone. Beside today's render of the same analysis (the same gates; only the claim
    differs), the only new texts are the accepted state's copy. Every evidence-related text that
    stays is the backend's own data or copy, or a listed UI text that holds under any claim."""

    for name in ACCEPTED:
        deferred = _deferred(cases[name])
        for surface, texts in rendered[name].items():
            assert deferred.isdisjoint(texts), (name, surface, deferred & set(texts))
    for claim in (name for name in ACCEPTED if name not in PERMISSION):
        today = claim.replace("claim", "today")
        payload = cases[claim]
        view = payload["decision_view"]
        accepted = {
            view["headline"],
            view["detail"],
            *view["evidence"]["limitations"],
            *ACCEPTED_UI_TEXTS,
        }
        run_ids = {payload["run_id"], cases[today]["run_id"]}
        for surface, texts in rendered[claim].items():
            shown, before = set(texts) - run_ids, set(rendered[today][surface]) - run_ids
            assert shown - before <= accepted, (claim, surface, shown - before - accepted)
            stayed = {text for text in shown & before if EVIDENCE_WORDING.search(text)}
            unaccounted = {
                text
                for text in stayed - STATE_INDEPENDENT_UI_TEXTS
                if not _backend_says(text, payload)
            }
            assert unaccounted == set(), (claim, surface, unaccounted)


def test_the_diagnostics_cards_are_the_endpoints_items(diagnostics_cards: dict) -> None:
    """The per-timeframe cards render the calibration endpoint's items as they are, the same
    under any claim: a sample gate's note, the metrics and the endpoint's own warning. That
    warning is the endpoint's copy; an acceptance must make it agree (decision_view.py)."""

    for name in CASES:
        assert diagnostics_cards[name] == diagnostics_cards["today"], name
    by_timeframe = {card[0]: card for card in diagnostics_cards["claim"]}
    assert list(by_timeframe) == list(calibration_endpoint.SUPPORTED_TIMEFRAMES)
    for timeframe in ("1H", "1W"):
        assert "Measured calibration diagnostic — not a guarantee." in by_timeframe[timeframe]
    assert by_timeframe["1H"][-1] == calibration_endpoint._ITEM_WARNING


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
        assert (
            "Early diagnostic only — not accuracy, not profitability evidence, not trade EV."
            in rendered[name]["detail_diagnostics"]
        ), name
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
