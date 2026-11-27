"""The DecisionView as the browser renders it (plan §14.1-§14.2; owner rulings DP-A and DP-F).

The real app.js functions run under Node on a view the backend built, so what a user reads is
checked, not only the source: the plan's order, the honest DEGRADED, the band-first probabilities
at their evidence level, a gate disposition that is never presented as a market call, and every
legacy surface (each card's banner, the detail's probability rows) deferring to the view.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest

from crypto_probability_engine.api.analysis_service import METHODOLOGY_VERSION
from crypto_probability_engine.detail import decision_view
from crypto_probability_engine.detail.decision_view import STATE_COPY, build_decision_view
from tests.fixtures.market_data import make_snapshot

ROOT = Path(__file__).resolve().parents[2]
NODE = shutil.which("node")
FUNCTIONS = (
    "vietnamTimeParts",
    "formatVietnamTime",
    "formatNumber",
    "formatPct",
    "formatFractionPct",
    "persistenceStatusText",
    "dataBannerText",
    "decisionViewOf",
    "decisionDataBanner",
    "decisionDataText",
    "dataBannerFor",
    "notAssessedByView",
    "legacyProbabilityRows",
    "decisionEvidenceText",
    "decisionViewRows",
    "costCaveatRows",
    "dispositionLabel",
    "renderReferenceDisplay",
)
CONSTANTS = ("NOT_ASSESSED_TEXT", "VENUE_LABELS")


def _extract_function(source: str, name: str) -> str:
    """One whole function: past its parameter list (which may hold a default ``{}``), then its
    balanced body."""

    start = source.index(f"function {name}(")
    depth, index = 0, source.index("(", start)
    while True:
        depth += {"(": 1, ")": -1}.get(source[index], 0)
        index += 1
        if depth == 0:
            break
    index = source.index("{", index)
    depth = 0
    for end in range(index, len(source)):
        depth += {"{": 1, "}": -1}.get(source[end], 0)
        if depth == 0:
            return source[start : end + 1]
    raise AssertionError(f"Could not extract {name}")


def _extract_constant(source: str, name: str) -> str:
    match = re.search(rf"^const {name} = .*;$", source, re.MULTILINE)
    assert match, f"Could not extract {name}"
    return match.group(0)


def _view(
    hard_blocks: tuple[str, ...] = ("SKILL_NOT_DEMONSTRATED",),
    hold: dict | None = None,
    *,
    active: str = "okx",
    age_seconds: int | None = None,
) -> dict:
    gate: dict = {"hard_blocks": list(hard_blocks)}
    # Seven minutes after the last close, so the reference close cannot pass for the as-of time.
    snapshot = make_snapshot(provider="okx", symbol="BTC/USDT", timeframe="1H")
    if hold is not None:
        gate["directional_evidence_hold"] = hold
    return build_decision_view(
        timeframe="1H",
        methodology_version=METHODOLOGY_VERSION,
        snapshot=replace(snapshot, as_of_utc=snapshot.as_of_utc + timedelta(minutes=7)),
        data_quality={
            "is_live_data": True,
            "data_source": "OKX_PUBLIC",
            "latest_candle_age_seconds": age_seconds,
        },
        provider_state={
            "status": "OK",
            "active_provider": active,
            "providers": {"binance": {"status": "QUARANTINED"}, "okx": {"status": "OK"}},
        },
        quant_result={
            "gate_result": gate,
            "probability_state": {
                "horizons": {
                    "H_primary": {"p_up_frac": 0.4, "p_down_frac": 0.35, "p_timeout_frac": 0.25}
                }
            },
            "execution_realism": {
                "round_trip_cost_frac": 0.0036,
                "taker_fee_frac": 0.001,
                "slippage_frac": 0.0016,
            },
        },
        decision_brief={
            "probability_type": "UNCALIBRATED_HEURISTIC_6BAR_OUTCOME",
            "model_readiness": "HEURISTIC_UNCALIBRATED",
            "calibration_status": "DEFAULT_PHASE1A",
            "reliability_status": "INSUFFICIENT_SAMPLE",
        },
        skill_evidence={"verdict": "INSUFFICIENT_EVIDENCE", "n": 0},
        primary_venue="binance",
    )


def _payload(view: dict | None) -> dict:
    payload: dict[str, Any] = {
        "normalized_symbol": "BTC/USDT",
        "frontend_display": {
            "disposition": "NO_TRADE",
            "model_readiness_label": "Model readiness: Heuristic (uncalibrated)",
            "is_live_data": True,
            "data_source": "OKX_PUBLIC",
        },
        "debug": {"persistence_status": "STATELESS"},
    }
    if view is not None:
        payload["decision_view"] = view
    return payload


def _node(body: str, **values: Any) -> Any:
    """The real app.js functions, then ``body`` (which logs one JSON value) under Node."""

    assert NODE is not None, "node is required to run the real app.js"
    source = (ROOT / "frontend" / "app.js").read_text(encoding="utf-8")
    script = "\n".join(
        [
            *(_extract_constant(source, name) for name in CONSTANTS),
            *(_extract_function(source, name) for name in FUNCTIONS),
            *(f"const {name} = {json.dumps(value)};" for name, value in values.items()),
            body,
        ]
    )
    done = subprocess.run(  # noqa: S603 - node on a script built here
        [NODE, "-e", script], capture_output=True, text=True, check=True, timeout=30
    )
    return json.loads(done.stdout)


def _render(view: dict) -> tuple[str, list[list[str]], bool]:
    """The banner and the rows app.js renders for a view, and whether it refuses the same view
    under another schema version: the one before (a v1 view carries no gate authority, so it is
    never rendered as if it did) and one it does not know yet."""

    rendered = _node(
        """
const view = decisionViewOf(payload);
const stamped = (version) => ({...payload, decision_view: {...view, schema_version: version}});
console.log(JSON.stringify({
  banner: decisionDataBanner(view.data),
  rows: decisionViewRows(payload, view),
  refusesUnknown: ["decision_view.v1", "decision_view.v3", "", null].every(
    (version) => decisionViewOf(stamped(version)) === null,
  ),
}));
""",
        payload=_payload(view),
    )
    return rendered["banner"], rendered["rows"], rendered["refusesUnknown"]


def test_the_rows_a_user_reads() -> None:
    view = _view()
    banner, ordered, refuses_unknown = _render(view)
    rows = dict(ordered)
    assert [label for label, _ in ordered][:7] == [
        "Asset · venue",
        "Reference close (Vietnam)",
        "Reference close (UTC)",
        "Horizon end (Vietnam)",
        "Horizon end (UTC)",
        "Data",
        "Storage",
    ]
    assert banner == "DEGRADED DATA - OKX_PUBLIC"
    assert rows["Data"].startswith("DEGRADED: Live data, degraded. The configured primary venue")
    assert rows["Asset · venue"] == "BTC/USDT · okx"
    assert rows["In band (inside the decision band)"] == "25.00% (band ±0.36%)"
    assert rows["Up (above the band)"] == "40.00%" and rows["Down (below the band)"] == "35.00%"
    assert rows["Storage"].startswith("No storage configured")
    assert rows["Evidence"] == "INSUFFICIENT_EVIDENCE · 0 resolved outcomes · INSUFFICIENT_SAMPLE"
    assert rows["Gate disposition (not a market call)"] == "NO_TRADE"
    assert rows["Reference close (UTC)"] == view["time"]["reference_close_utc"]
    assert rows["Horizon end (UTC)"] == view["time"]["horizon_end_utc"]
    assert rows["Reference close (Vietnam)"] == _formatted_vietnam(
        view["time"]["reference_close_utc"]
    )
    assert rows["Horizon end (Vietnam)"] == _formatted_vietnam(view["time"]["horizon_end_utc"])
    labels = [label for label, _ in ordered]
    assert labels.index("Reference close (Vietnam)") + 1 == labels.index("Reference close (UTC)")
    assert labels.index("Horizon end (Vietnam)") + 1 == labels.index("Horizon end (UTC)")
    assert rows["Reference close (UTC)"] != view["time"]["as_of_utc"]
    assert refuses_unknown, "a view of an unknown schema version is never rendered"


def test_overview_card_renders_reference_label_with_decision_view_and_no_heat() -> None:
    assert NODE is not None, "node is required to run the real app.js"
    source = (ROOT / "frontend" / "app.js").read_text(encoding="utf-8")
    card = _extract_function(source, "overviewCard")
    script = "\n".join(
        [
            "const inserted = []; const classes = []; const styles = {};",
            "const fakeNode = {classList:{add:(x)=>classes.push(x)},dataset:{},",
            "style:{setProperty:(k,v)=>styles[k]=v},",
            "querySelector:(s)=>s==='h2'?{}:s==='.news-note'?{set textContent(v){}}:",
            "s==='.detail-button'?{addEventListener(){}}:{},",
            "insertBefore:(child)=>inserted.push(child),addEventListener(){}};",
            "const overviewTemplate={content:{firstElementChild:{cloneNode:()=>fakeNode}}};",
            "const document={createElement:()=>({className:'',textContent:'',dataset:{}})};",
            "const backendText=(v)=>typeof v==='string'&&v.length?v:null;",
            "const decisionViewOf=(p)=>p.decision_view;",
            "const decisionDataBanner=()=> 'data'; const dataBannerText=()=> 'data';",
            "const gateViewOf=()=>({}); const gateFramingBlocks=()=>[];",
            "const getScoreHeatBand=()=>({className:'heat-hot',mainColor:'#dc2626',level:'HOT'});",
            "const notAssessedByView=()=>false; const decisionViewRows=()=>[];",
            "const appendDefinitionRows=()=>{}; const formatPct=(v)=>String(v);",
            "const dispositionLabel=()=> 'Disposition'; const firstReason=()=> '';",
            "const openDetail=()=>{}; const modelReadinessCopy='';",
            card,
            "const payload={normalized_symbol:'BTC/USDT',timeframes:{primary:'4H'},run_id:'r1',",
            "frontend_display:{total_score:92,horizon_approx_label:'4H'},",
            "decision_brief:{probability_type:",
            "'DESCRIPTIVE_REFERENCE_6BAR_INSIDE_BAND_FREQUENCY',",
            "uncalibrated_banner:",
            "'Historical-frequency reference · Descriptive estimate — not validated.'},",
            "decision_view:{state:'NO_ACCEPTED_CLAIM',headline:'No claim',",
            "detail:'No claim detail',data:{}},",
            "news_addon_state:{status:'OK'}};",
            "overviewCard(payload);",
            "console.log(JSON.stringify({label:inserted.find((x)=>x.textContent&&x.textContent.startsWith('Historical-frequency'))?.textContent||null,classes,styles}));",
        ]
    )
    completed = subprocess.run(  # noqa: S603 - node receives the local cut-out test script
        [NODE, "-e", script], capture_output=True, text=True, check=False, timeout=30
    )
    assert completed.returncode == 0, completed.stderr
    rendered = json.loads(completed.stdout)
    assert rendered["label"] == (
        "Historical-frequency reference · Descriptive estimate — not validated."
    )
    assert "heat-hot" not in rendered["classes"]
    assert "--heat-main" not in rendered["styles"]
    assert "--heat-border" not in rendered["styles"]


@pytest.mark.parametrize(
    "display, expected_lines",
    [
        (
            {
                "title": "Descriptive reference",
                "count_line": (
                    "In band: 3 of 14 matured six-bar outcomes over the last 28 days ended "
                    "inside today's decision band."
                ),
                "direction_line": "Symmetric by design — no directional signal.",
                "overlap_line": "Outcomes overlap: each shares half its horizon with the next.",
                "honesty_line": (
                    "Not a validated forecast and not a prediction interval. "
                    "Not recorded for scoring."
                ),
                "extended_line": "Extended horizon: not modelled.",
                "retention_line": (
                    "Recent Analysis keeps this reference only in the app's current session "
                    "memory; "
                    "it may disappear after eviction or restart, and it is not recorded for "
                    "forecast evaluation."
                ),
            },
            6,
        ),
        ({"title": "Descriptive reference", "count_line": "Available only for named cells."}, 1),
        (
            {
                "title": "Descriptive reference",
                "count_line": (
                    "Unavailable for this run (HISTORY_FAILED); the percentages shown are "
                    "the heuristic's."
                ),
            },
            1,
        ),
    ],
)
def test_reference_display_uses_backend_lines_as_text(display: dict, expected_lines: int) -> None:
    rendered = _node(
        """
const nodes = [];
global.document = { createElement: (tag) => {
  const node = { tag, children: [], append(child) { this.children.push(child); } };
  nodes.push(node);
  return node;
} };
const block = renderReferenceDisplay(display);
console.log(JSON.stringify({
  absent: renderReferenceDisplay(null) === null,
  className: block.className,
  tags: nodes.map((node) => node.tag),
  text: block.children.map((node) => node.textContent),
}));
""",
        display=display,
    )
    assert rendered["absent"] is True
    assert rendered["className"] == "reference-display"
    assert rendered["text"][0] == "Descriptive reference"
    assert len(rendered["text"]) - 1 == expected_lines
    if "retention_line" in display:
        assert display["retention_line"] in rendered["text"]
        assert all("Saved as an analysis run" not in line for line in rendered["text"])
    assert all(tag in {"div", "strong", "p"} for tag in rendered["tags"])


def _formatted_vietnam(value: str) -> str:
    return _node("console.log(JSON.stringify(formatVietnamTime(value)));", value=value)


def test_the_data_row_carries_freshness_and_a_readable_venue() -> None:
    _, ordered, _ = _render(_view(active="cross_provider", age_seconds=42))
    rows = dict(ordered)
    assert rows["Data"].endswith("Latest candle 42s old.")
    assert rows["Asset · venue"] == "BTC/USDT · cross-checked venues"


def test_unavailable_data_shows_no_percentages() -> None:
    banner, ordered, _ = _render(_view(hard_blocks=("PROVIDER_DEGRADED",)))
    rows = dict(ordered)
    assert banner == "DATA UNAVAILABLE - OKX_PUBLIC"
    assert rows["Data"].startswith("UNAVAILABLE: Data unavailable.")
    assert rows["In band (inside the decision band)"].startswith("Not assessed")
    assert rows["Up (above the band)"] == rows["Down (below the band)"] == "Not assessed"
    assert "%" not in "".join(rows[key] for key in rows if key != "Round-trip cost")


def test_the_hold_reads_as_under_review_not_as_a_verdict() -> None:
    _, ordered, _ = _render(_view(hold={"active": True, "hold_reason": "H2"}))
    assert dict(ordered)["Evidence"] == "Directional evidence under review (the hold is active)"


def test_every_card_banner_follows_the_view() -> None:
    """The Single, Watchlist and Batch cards share one banner rule: the view's data state when
    there is a view (never LIVE when it is not OK), and the legacy banner only without one."""

    banners = _node(
        "console.log(JSON.stringify(payloads.map((payload) => dataBannerFor(payload))));",
        payloads=[
            _payload(_view()),
            _payload(_view(hard_blocks=("PROVIDER_DEGRADED",))),
            _payload(None),
        ],
    )
    assert banners == [
        "DEGRADED DATA - OKX_PUBLIC",
        "DATA UNAVAILABLE - OKX_PUBLIC",
        "LIVE DATA - OKX_PUBLIC",
    ]


def test_legacy_probability_rows_defer_to_the_view() -> None:
    rows = [["Up", "40.00%"], ["Down", "35.00%"], ["In band", "25.00%"]]
    rendered = _node(
        "console.log(JSON.stringify(payloads.map((payload) => "
        "legacyProbabilityRows(payload, rows))));",
        payloads=[
            _payload(_view(hard_blocks=("EPISTEMIC_VOID",))),
            _payload(_view()),
            _payload(None),
        ],
        rows=rows,
    )
    not_assessed, assessed, legacy = rendered
    assert not_assessed == [
        [label, "Not assessed (the data cannot support an assessment)"] for label, _ in rows
    ]
    assert assessed == rows and legacy == rows


def test_the_gate_framing_is_the_backends_sentence_for_what_the_view_allows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Review finding D3: app.js worded the gate framing of each state itself. The view words it
    now (detail/gate_kinds.py), for every state, and app.js has no such sentence left."""

    source = (ROOT / "frontend" / "app.js").read_text(encoding="utf-8")
    assert "function gateFramingNote" not in source
    for sentence in ("\"The gates' disposition", "no reason to act or to avoid acting"):
        assert sentence not in source, sentence
    key = f"{_view()['range']['evidence_level']}:{METHODOLOGY_VERSION}:1H"
    blocked = ("SKILL_NOT_DEMONSTRATED",)
    assert _view(blocked)["gates"]["framing"] == (
        "The gates' disposition, not a market call: a gate outcome is not a forecast to act on."
    )
    monkeypatch.setattr(decision_view, "ACCEPTED_FORECAST_CLAIMS", frozenset({key}))
    assert _view(blocked)["gates"]["framing"] == (
        "The gates' disposition: hard gates outrank everything shown."
    )
    monkeypatch.setattr(decision_view, "ACCEPTED_DIRECTIONAL_PERMISSIONS", frozenset({key}))
    permitted = _view(())
    assert permitted["state"] == "DIRECTIONAL_PERMISSION"
    assert permitted["gates"]["framing"].startswith(
        "The gates' disposition, with an accepted directional permission"
    )
    assert "Not financial advice" in permitted["gates"]["framing"]


@pytest.mark.parametrize(
    ("hard_blocks", "permission", "state"),
    [
        (("SKILL_NOT_DEMONSTRATED",), False, "ACCEPTED_FORECAST_CLAIM"),
        ((), True, "DIRECTIONAL_PERMISSION"),
    ],
    ids=["an accepted forecast claim", "an accepted directional permission"],
)
def test_accepted_states_read_as_accepted_and_a_permission_stays_non_advisory(
    monkeypatch: pytest.MonkeyPatch, hard_blocks: tuple[str, ...], permission: bool, state: str
) -> None:
    """Owner ruling 2026-10-06, on the view the owner reads first: accepted forecast evidence
    shows its accepted state (the view's own copy, not the uncalibrated-heuristic label), and an
    accepted directional permission is shown without "not a market call" while its label stays
    explicitly non-advisory. Built by the real builder with the (empty) registries filled for
    this test only."""

    key = f"{_view()['range']['evidence_level']}:{METHODOLOGY_VERSION}:1H"
    monkeypatch.setattr(decision_view, "ACCEPTED_FORECAST_CLAIMS", frozenset({key}))
    monkeypatch.setattr(
        decision_view, "ACCEPTED_DIRECTIONAL_PERMISSIONS", frozenset({key} if permission else ())
    )
    view = _view(hard_blocks)
    assert view["state"] == state
    _, ordered, _ = _render(view)
    rows = dict(ordered)
    assert rows["Evidence level"] == STATE_COPY[state][0]
    labels = [label for label, _ in ordered]
    if permission:
        label = "Gate disposition (accepted directional permission; not financial advice)"
        assert rows[label] == "NO_TRADE"
        assert not any("not a market call" in item for item in labels)
    else:
        assert rows["Gate disposition (not a market call)"] == "NO_TRADE"


def test_without_an_accepted_claim_the_evidence_level_is_unchanged() -> None:
    _, ordered, _ = _render(_view())
    assert dict(ordered)["Evidence level"] == "Model readiness: Heuristic (uncalibrated)"
