from __future__ import annotations

import json
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


def _logout_states() -> dict[str, object]:
    source = (ROOT / "frontend" / "app.js").read_text(encoding="utf-8")
    clear_function = _extract_function(source, "clearOperatorData")
    reset_function = _extract_function(source, "resetToLoggedOut")
    script = f"""
function element(classes = []) {{
  const values = new Set(classes);
  return {{
    textContent: "operator data",
    value: "operator secret",
    children: ["operator data"],
    classList: {{
      add: (name) => values.add(name),
      remove: (name) => values.delete(name),
      contains: (name) => values.has(name),
    }},
    replaceChildren(...children) {{ this.children = children; }},
  }};
}}
const elements = {{
  "#logoutButton": element(),
  "#accessCode": element(),
  "#batchResult": element(),
  "#recentList": element(),
  "#watchlistList": element(),
  "#devResult": element(),
  "#recentStatus": element(),
  "#recentSymbolFilter": element(),
  "#recentTimeframeFilter": element(),
  "#recentModeFilter": element(),
}};
const document = {{ querySelector: (selector) => elements[selector] }};
const loginPanel = element(["hidden"]);
const workspace = element();
const sessionStatus = element();
const loginStatus = element();
const singleResult = element();
const lastRefreshed = element();
let recentRuns = [{{ run_id: "run-1" }}];
let recentRunsSource = "persistence";
let lastBatchRequest = {{ symbols: ["BTCUSDT"] }};
let currentWatchlistSymbol = "BTCUSDT";
let calibrationDiagnosticsCache = {{ status: "cached" }};
let calibrationDiagnosticsCachedAt = 123;
let calibrationDiagnosticsRequest = Promise.resolve();
let analysisActive = true;
let refreshReadyAt = 123;
const calls = {{
  hideDetail: 0, placeholders: 0, panels: [], refresh: 0, persistence: [], dev: [],
}};
function hideDetail() {{ calls.hideDetail += 1; }}
function renderTimeframePlaceholders(target) {{
  calls.placeholders += 1;
  target.replaceChildren();
}}
function showPanel(name) {{ calls.panels.push(name); }}
function updateRefreshButton() {{ calls.refresh += 1; }}
function updatePersistenceStatus(status) {{ calls.persistence.push(status); }}
function updateDevModeUx(status) {{ calls.dev.push(status); }}
{clear_function}
{reset_function}

function dataState() {{
  return {{
    containers: [
      singleResult,
      elements["#batchResult"],
      elements["#recentList"],
      elements["#watchlistList"],
      elements["#devResult"],
    ].map((item) => item.children.length),
    recentStatus: elements["#recentStatus"].textContent,
    filterValues: [
      "#recentSymbolFilter", "#recentTimeframeFilter", "#recentModeFilter",
    ].map((selector) => elements[selector].value),
    recentRuns,
    recentRunsSource,
    lastBatchRequest,
    currentWatchlistSymbol,
    calibrationDiagnosticsCache,
    calibrationDiagnosticsCachedAt,
    calibrationDiagnosticsRequest,
  }};
}}

function fillOperatorData() {{
  for (const target of [
    singleResult,
    elements["#batchResult"],
    elements["#recentList"],
    elements["#watchlistList"],
    elements["#devResult"],
  ]) {{
    target.children = ["late operator data"];
  }}
}}

clearOperatorData();
const clearOnly = {{
  ...dataState(),
  workspaceHidden: workspace.classList.contains("hidden"),
  loginShown: !loginPanel.classList.contains("hidden"),
  logoutHidden: elements["#logoutButton"].classList.contains("hidden"),
  sessionStatus: sessionStatus.textContent,
}};

resetToLoggedOut();
const loggedOut = {{
  ...dataState(),
  workspaceHidden: workspace.classList.contains("hidden"),
  loginShown: !loginPanel.classList.contains("hidden"),
  logoutHidden: elements["#logoutButton"].classList.contains("hidden"),
  sessionStatus: sessionStatus.textContent,
  accessCode: elements["#accessCode"].value,
  calls,
}};

fillOperatorData();
clearOperatorData();
const afterLateResponse = dataState();
console.log(JSON.stringify({{ clearOnly, loggedOut, afterLateResponse }}));
"""
    result = subprocess.run(
        ["node", "-e", script],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def test_clear_operator_data_resets_data_without_changing_session_ui() -> None:
    state = _logout_states()["clearOnly"]

    assert state["containers"] == [0, 0, 0, 0, 0]
    assert state["recentStatus"] == "Recent analyses not loaded yet."
    assert state["filterValues"] == ["", "", ""]
    assert state["recentRuns"] == []
    assert state["recentRunsSource"] is None
    assert state["lastBatchRequest"] is None
    assert state["currentWatchlistSymbol"] is None
    assert state["calibrationDiagnosticsCache"] is None
    assert state["calibrationDiagnosticsCachedAt"] == 0
    assert state["calibrationDiagnosticsRequest"] is None
    assert state["workspaceHidden"] is False
    assert state["loginShown"] is False
    assert state["logoutHidden"] is False
    assert state["sessionStatus"] == "operator data"


def test_reset_to_logged_out_clears_operator_ui_and_module_state() -> None:
    state = _logout_states()["loggedOut"]

    assert state["workspaceHidden"] is True
    assert state["loginShown"] is True
    assert state["logoutHidden"] is True
    assert state["sessionStatus"] == "Locked"
    assert state["accessCode"] == ""
    assert state["containers"] == [0, 0, 0, 0, 0]
    assert state["recentStatus"] == "Recent analyses not loaded yet."
    assert state["filterValues"] == ["", "", ""]
    assert state["recentRuns"] == []
    assert state["recentRunsSource"] is None
    assert state["lastBatchRequest"] is None
    assert state["currentWatchlistSymbol"] is None
    assert state["calibrationDiagnosticsCache"] is None
    assert state["calibrationDiagnosticsCachedAt"] == 0
    assert state["calibrationDiagnosticsRequest"] is None
    assert state["calls"]["persistence"] == ["UNKNOWN"]
    assert state["calls"]["dev"] == [{"enabled": False, "configured": False}]


def test_login_clear_removes_operator_data_rendered_after_logout() -> None:
    state = _logout_states()["afterLateResponse"]

    assert state["containers"] == [0, 0, 0, 0, 0]
