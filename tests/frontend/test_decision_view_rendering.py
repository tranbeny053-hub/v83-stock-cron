"""The DecisionView as the browser renders it (plan §14.1-§14.2; owner rulings DP-A and DP-F).

The real app.js functions run under Node on a view the backend built, so the rows a user reads are
checked, not only the source: the plan's order, the honest DEGRADED, the band-first probabilities
at their evidence level, and a gate disposition that is never presented as a market call.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from crypto_probability_engine.detail.decision_view import build_decision_view
from tests.fixtures.market_data import make_snapshot

ROOT = Path(__file__).resolve().parents[2]
NODE = shutil.which("node")


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


def _view() -> dict:
    return build_decision_view(
        timeframe="1H",
        snapshot=make_snapshot(provider="okx", symbol="BTC/USDT", timeframe="1H"),
        data_quality={"is_live_data": True, "data_source": "OKX_PUBLIC"},
        provider_state={
            "status": "OK",
            "active_provider": "okx",
            "providers": {"binance": {"status": "QUARANTINED"}, "okx": {"status": "OK"}},
        },
        quant_result={
            "gate_result": {"hard_blocks": ["SKILL_NOT_DEMONSTRATED"]},
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


def test_the_rows_a_user_reads() -> None:
    assert NODE is not None, "node is required to run the real app.js"
    source = (ROOT / "frontend" / "app.js").read_text(encoding="utf-8")
    functions = "\n".join(
        _extract_function(source, name)
        for name in (
            "formatNumber",
            "formatPct",
            "formatFractionPct",
            "persistenceStatusText",
            "decisionViewOf",
            "decisionDataBanner",
            "decisionEvidenceText",
            "decisionViewRows",
        )
    )
    payload = {
        "normalized_symbol": "BTC/USDT",
        "decision_view": _view(),
        "frontend_display": {
            "disposition": "NO_TRADE",
            "model_readiness_label": "Model readiness: Heuristic (uncalibrated)",
        },
        "debug": {"persistence_status": "STATELESS"},
    }
    script = f"""{functions}
const payload = {json.dumps(payload)};
const view = decisionViewOf(payload);
const banner = decisionDataBanner(view.data);
console.log(JSON.stringify({{banner, rows: decisionViewRows(payload, view)}}));
"""
    done = subprocess.run(  # noqa: S603 - node on a script built here
        [NODE, "-e", script], capture_output=True, text=True, check=True, timeout=30
    )
    rendered = json.loads(done.stdout)
    rows = dict(rendered["rows"])
    assert [label for label, _ in rendered["rows"]][:5] == [
        "Asset · venue",
        "Reference close (UTC)",
        "Horizon end (UTC)",
        "Data",
        "Saved",
    ]
    assert rendered["banner"] == "DEGRADED DATA - OKX_PUBLIC"
    assert rows["Data"].startswith("DEGRADED: Live data, degraded. The configured primary venue")
    assert rows["Asset · venue"] == "BTC/USDT · okx"
    assert rows["In band (inside the decision band)"] == "25.00% (band ±0.36%)"
    assert rows["Up (above the band)"] == "40.00%" and rows["Down (below the band)"] == "35.00%"
    assert rows["Saved"].startswith("No storage configured")
    assert rows["Evidence"] == "INSUFFICIENT_EVIDENCE · 0 resolved outcomes · INSUFFICIENT_SAMPLE"
    assert rows["Gate disposition (not a market call)"] == "NO_TRADE"
    assert rows["Reference close (UTC)"].endswith("Z") and rows["Horizon end (UTC)"].endswith("Z")
