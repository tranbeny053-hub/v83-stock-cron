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

from crypto_probability_engine.api.analysis_service import METHODOLOGY_VERSION
from crypto_probability_engine.detail.decision_view import build_decision_view
from tests.fixtures.market_data import make_snapshot

ROOT = Path(__file__).resolve().parents[2]
NODE = shutil.which("node")
FUNCTIONS = (
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
    under an unknown schema version."""

    rendered = _node(
        """
const view = decisionViewOf(payload);
const unknown = {...payload, decision_view: {...view, schema_version: "decision_view.v2"}};
console.log(JSON.stringify({
  banner: decisionDataBanner(view.data),
  rows: decisionViewRows(payload, view),
  refusesUnknown: decisionViewOf(unknown) === null,
}));
""",
        payload=_payload(view),
    )
    return rendered["banner"], rendered["rows"], rendered["refusesUnknown"]


def test_the_rows_a_user_reads() -> None:
    view = _view()
    banner, ordered, refuses_unknown = _render(view)
    rows = dict(ordered)
    assert [label for label, _ in ordered][:5] == [
        "Asset · venue",
        "Reference close (UTC)",
        "Horizon end (UTC)",
        "Data",
        "Saved",
    ]
    assert banner == "DEGRADED DATA - OKX_PUBLIC"
    assert rows["Data"].startswith("DEGRADED: Live data, degraded. The configured primary venue")
    assert rows["Asset · venue"] == "BTC/USDT · okx"
    assert rows["In band (inside the decision band)"] == "25.00% (band ±0.36%)"
    assert rows["Up (above the band)"] == "40.00%" and rows["Down (below the band)"] == "35.00%"
    assert rows["Saved"].startswith("No storage configured")
    assert rows["Evidence"] == "INSUFFICIENT_EVIDENCE · 0 resolved outcomes · INSUFFICIENT_SAMPLE"
    assert rows["Gate disposition (not a market call)"] == "NO_TRADE"
    assert rows["Reference close (UTC)"] == view["time"]["reference_close_utc"]
    assert rows["Horizon end (UTC)"] == view["time"]["horizon_end_utc"]
    assert rows["Reference close (UTC)"] != view["time"]["as_of_utc"]
    assert refuses_unknown, "a view of an unknown schema version is never rendered"


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
