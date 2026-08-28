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


def _restore_states() -> dict[str, object]:
    source = (ROOT / "frontend" / "app.js").read_text(encoding="utf-8")
    restore_session = _extract_function(source, "restoreSession")
    script = f"""
let probeResult = true;
let sessionGeneration = 7;
let sequence = [];
const calls = {{ loadSystemStatus: 0, clearOperatorData: 0 }};
function fakeElement(initialClasses, initialText) {{
  const classes = new Set(initialClasses);
  return {{
    classList: {{
      add(value) {{ classes.add(value); }},
      remove(value) {{
        if (value === "hidden" && this === workspace.classList) {{
          sequence.push("workspace shown");
        }}
        classes.delete(value);
      }},
      contains(value) {{ return classes.has(value); }},
    }},
    get textContent() {{ return initialText; }},
    set textContent(value) {{ initialText = value; }},
  }};
}}
const loginPanel = fakeElement([], "");
const workspace = fakeElement(["hidden"], "");
const logoutButton = fakeElement(["hidden"], "");
const sessionStatus = fakeElement([], "Locked");
const loginStatus = fakeElement([], "");
const document = {{
  querySelector(selector) {{
    if (selector === "#logoutButton") return logoutButton;
    return {{}};
  }},
}};
async function loadSystemStatus() {{
  calls.loadSystemStatus += 1;
  return probeResult;
}}
function clearOperatorData() {{
  calls.clearOperatorData += 1;
  sequence.push("operator data cleared");
}}
function updateRefreshButton() {{}}
{restore_session}
function snapshot(result, initialGeneration) {{
  return {{
    result,
    workspaceHidden: workspace.classList.contains("hidden"),
    loginHidden: loginPanel.classList.contains("hidden"),
    logoutHidden: logoutButton.classList.contains("hidden"),
    sessionStatus: sessionStatus.textContent,
    loginStatus: loginStatus.textContent,
    clearOperatorData: calls.clearOperatorData,
    loadSystemStatus: calls.loadSystemStatus,
    generationDelta: sessionGeneration - initialGeneration,
    sequence: [...sequence],
  }};
}}
(async () => {{
  const successGeneration = sessionGeneration;
  const success = snapshot(await restoreSession(), successGeneration);

  probeResult = false;
  sessionGeneration = 19;
  sequence = [];
  calls.loadSystemStatus = 0;
  calls.clearOperatorData = 0;
  loginPanel.classList.remove("hidden");
  workspace.classList.add("hidden");
  logoutButton.classList.add("hidden");
  sessionStatus.textContent = "Initial session status";
  loginStatus.textContent = "";
  const failureGeneration = sessionGeneration;
  const failure = snapshot(await restoreSession(), failureGeneration);

  console.log(JSON.stringify({{ success, failure }}));
}})();
"""
    completed = subprocess.run(
        ["node", "-e", script],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)


def test_restore_session_success() -> None:
    success = _restore_states()["success"]

    assert success == {
        "result": True,
        "workspaceHidden": False,
        "loginHidden": True,
        "logoutHidden": False,
        "sessionStatus": "Ready",
        "loginStatus": "",
        "clearOperatorData": 1,
        "loadSystemStatus": 1,
        "generationDelta": 1,
        "sequence": ["operator data cleared", "workspace shown"],
    }


def test_restore_session_failure_is_silent_and_does_not_mutate_ui() -> None:
    failure = _restore_states()["failure"]

    assert failure == {
        "result": False,
        "workspaceHidden": True,
        "loginHidden": False,
        "logoutHidden": True,
        "sessionStatus": "Initial session status",
        "loginStatus": "",
        "clearOperatorData": 0,
        "loadSystemStatus": 1,
        "generationDelta": 0,
        "sequence": [],
    }


def test_restore_session_boot_and_source_contract() -> None:
    source = (ROOT / "frontend" / "app.js").read_text(encoding="utf-8")
    restore_session = _extract_function(source, "restoreSession")
    boot = source[source.rindex("renderTimeframePlaceholders(singleResult);") :]

    assert re.search(r"updateRefreshButton\(\);\s*void restoreSession\(\);", boot)
    assert "api(" not in restore_session
