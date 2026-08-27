from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _extract_function(source: str, name: str) -> str:
    function_start = source.index(f"function {name}(")
    async_start = function_start - len("async ")
    start = async_start if source[async_start:function_start] == "async " else function_start
    opening_brace = source.index("{", function_start)
    depth = 0
    for index in range(opening_brace, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[start : index + 1]
    raise AssertionError(f"Could not extract {name}")


def _refresh_states() -> dict[str, object]:
    source = (ROOT / "frontend" / "app.js").read_text(encoding="utf-8")
    functions = "\n".join(
        _extract_function(source, name)
        for name in (
            "showPanel",
            "refreshCurrentView",
            "markRefreshed",
            "startRefreshCooldown",
            "updateRefreshButton",
            "refreshActionLabel",
            "activeTabName",
        )
    )
    script = f"""
let activeTab = "single";
let analysisActive = false;
let refreshReadyAt = 0;
let refreshTimer = null;
const refreshCooldownMs = 15000;
let currentWatchlistSymbol = null;
let lastBatchRequest = null;
let reloadResult = true;
let systemStatusResult = true;
const calls = {{
  hideDetail: 0,
  loadRecentRuns: 0,
  loadSystemStatus: 0,
  runSingleAnalysis: 0,
  runBatchAnalysis: 0,
  loadWatchlist: 0,
  openWatchlistSymbol: 0,
}};
const refreshButton = {{ disabled: false, textContent: "" }};
const lastRefreshed = {{ textContent: "" }};
const workspace = {{ classList: {{ contains: () => false }} }};
const tabNames = ["single", "batch", "watchlist", "recent", "dev"];
const tabs = tabNames.map((tab) => ({{
  dataset: {{ tab }},
  classList: {{
    toggle(cls, on) {{
      if (cls === "active" && on) activeTab = tab;
    }},
  }},
}}));
const document = {{
  querySelectorAll(selector) {{
    if (selector === ".tab") return tabs;
    return [];
  }},
  querySelector(selector) {{
    if (selector === ".tab.active") return {{ dataset: {{ tab: activeTab }} }};
    if (selector === "#watchlistView") return {{ classList: {{ contains: () => true }} }};
    if (tabNames.some((tab) => selector === `#${{tab}}Panel`)) {{
      return {{ classList: {{ toggle: () => {{}} }} }};
    }}
    return {{}};
  }},
}};
class FormData {{}}
const setTimeout = () => 1;
const clearTimeout = () => {{}};
async function loadRecentRuns() {{ calls.loadRecentRuns += 1; return reloadResult; }}
async function loadSystemStatus() {{ calls.loadSystemStatus += 1; return systemStatusResult; }}
async function runSingleAnalysis() {{ calls.runSingleAnalysis += 1; }}
async function runBatchAnalysis() {{ calls.runBatchAnalysis += 1; }}
async function loadWatchlist() {{ calls.loadWatchlist += 1; }}
async function openWatchlistSymbol() {{ calls.openWatchlistSymbol += 1; }}
function hideDetail() {{ calls.hideDetail += 1; }}
function batchRequestFromForm() {{ return {{}}; }}
{functions}
function reset(tab) {{
  activeTab = tab;
  analysisActive = false;
  refreshReadyAt = 0;
  refreshTimer = null;
  reloadResult = true;
  systemStatusResult = true;
  refreshButton.disabled = false;
  refreshButton.textContent = "";
  lastRefreshed.textContent = "previous value";
  Object.keys(calls).forEach((name) => {{ calls[name] = 0; }});
}}
(async () => {{
  reset("recent");
  await refreshCurrentView();
  const recentSuccess = {{ calls: {{ ...calls }}, stamp: lastRefreshed.textContent }};

  reset("recent");
  reloadResult = false;
  await refreshCurrentView();
  const recentFailure = {{
    stamp: lastRefreshed.textContent,
    cooldownArmed: refreshReadyAt > Date.now(),
    disabled: refreshButton.disabled,
  }};

  const labels = {{}};
  for (const tab of ["recent", "single", "batch", "watchlist", "dev"]) {{
    reset(tab);
    updateRefreshButton();
    labels[tab] = refreshButton.textContent;
  }}
  reset("recent");
  analysisActive = true;
  updateRefreshButton();
  labels.recentWhileActive = refreshButton.textContent;

  const cooldownLabels = {{}};
  for (const tab of ["recent", "single", "dev"]) {{
    reset(tab);
    refreshReadyAt = Date.now() + refreshCooldownMs;
    updateRefreshButton();
    cooldownLabels[tab] = refreshButton.textContent;
  }}

  reset("single");
  showPanel("recent");
  const recentPanel = {{ label: refreshButton.textContent, calls: {{ ...calls }} }};

  reset("recent");
  showPanel("single");
  const singlePanel = {{ label: refreshButton.textContent, calls: {{ ...calls }} }};

  reset("single");
  await refreshCurrentView();
  const single = {{ ...calls }};

  reset("dev");
  await refreshCurrentView();
  const dev = {{ calls: {{ ...calls }}, stamp: lastRefreshed.textContent }};

  reset("dev");
  systemStatusResult = false;
  await refreshCurrentView();
  const devFailure = {{
    calls: {{ ...calls }},
    stamp: lastRefreshed.textContent,
    cooldownArmed: refreshReadyAt > Date.now(),
  }};

  reset("single");
  showPanel("dev");
  const devPanel = {{ label: refreshButton.textContent, calls: {{ ...calls }} }};

  reset("somethingelse");
  await refreshCurrentView();
  const unknownSuccess = {{ calls: {{ ...calls }}, stamp: lastRefreshed.textContent }};

  reset("somethingelse");
  systemStatusResult = false;
  await refreshCurrentView();
  const unknownFailure = {{
    calls: {{ ...calls }},
    stamp: lastRefreshed.textContent,
    cooldownArmed: refreshReadyAt > Date.now(),
  }};

  reset("recent");
  analysisActive = true;
  await refreshCurrentView();
  const guarded = {{ ...calls }};

  reset("dev");
  analysisActive = true;
  await refreshCurrentView();
  const devGuarded = {{ ...calls }};

  console.log(JSON.stringify({{
    recentSuccess,
    recentFailure,
    labels,
    cooldownLabels,
    recentPanel,
    singlePanel,
    single,
    dev,
    devFailure,
    devPanel,
    unknownSuccess,
    unknownFailure,
    guarded,
    devGuarded,
  }}));
}})();
"""
    completed = subprocess.run(
        ["node", "-e", script],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)


def test_recent_refresh_semantics() -> None:
    states = _refresh_states()

    success = states["recentSuccess"]
    assert success["calls"]["loadRecentRuns"] == 1
    for forbidden_call in ("loadSystemStatus", "runSingleAnalysis", "runBatchAnalysis"):
        assert success["calls"][forbidden_call] == 0
    assert success["stamp"].startswith("history reloaded at ")

    failure = states["recentFailure"]
    assert failure == {
        "stamp": "previous value",
        "cooldownArmed": True,
        "disabled": True,
    }

    assert states["labels"] == {
        "recent": "Refresh",
        "single": "Re-analyze",
        "batch": "Re-analyze",
        "watchlist": "Re-analyze",
        "dev": "Refresh status",
        "recentWhileActive": "Re-analyzing...",
    }
    assert re.fullmatch(r"Refresh \(\d+s\)", states["cooldownLabels"]["recent"])
    assert re.fullmatch(r"Re-analyze \(\d+s\)", states["cooldownLabels"]["single"])
    assert re.fullmatch(r"Refresh status \(\d+s\)", states["cooldownLabels"]["dev"])

    assert states["recentPanel"]["label"] == "Refresh"
    assert states["recentPanel"]["calls"]["loadRecentRuns"] == 1
    assert states["singlePanel"]["label"] == "Re-analyze"
    assert states["singlePanel"]["calls"]["loadRecentRuns"] == 0
    assert states["devPanel"]["label"] == "Refresh status"

    assert states["single"]["runSingleAnalysis"] == 1
    assert states["single"]["loadRecentRuns"] == 0
    assert states["dev"]["calls"]["loadSystemStatus"] == 1
    assert states["dev"]["calls"]["loadRecentRuns"] == 0
    assert states["dev"]["calls"]["runSingleAnalysis"] == 0
    assert states["dev"]["calls"]["runBatchAnalysis"] == 0
    assert states["dev"]["stamp"].startswith("status refreshed at ")
    assert states["devFailure"]["calls"]["loadSystemStatus"] == 1
    assert states["devFailure"]["stamp"] == "previous value"
    assert states["devFailure"]["cooldownArmed"] is True
    assert states["unknownSuccess"]["calls"]["loadSystemStatus"] == 1
    assert states["unknownSuccess"]["stamp"].startswith("last refreshed at ")
    assert states["unknownFailure"]["calls"]["loadSystemStatus"] == 1
    assert states["unknownFailure"]["stamp"] == "previous value"
    assert states["unknownFailure"]["cooldownArmed"] is True
    assert states["guarded"]["loadRecentRuns"] == 0
    assert states["devGuarded"]["loadSystemStatus"] == 0
