from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _extract_function(source: str, name: str) -> str:
    function_start = source.index(f"function {name}(")
    async_start = function_start - len("async ")
    start = async_start if source[async_start:function_start] == "async " else function_start
    opening_parenthesis = source.index("(", function_start)
    parenthesis_depth = 0
    opening_brace = -1
    for index in range(opening_parenthesis, len(source)):
        if source[index] == "(":
            parenthesis_depth += 1
        elif source[index] == ")":
            parenthesis_depth -= 1
            if parenthesis_depth == 0:
                opening_brace = source.index("{", index)
                break
    if opening_brace < 0:
        raise AssertionError(f"Could not find body for {name}")
    depth = 0
    for index in range(opening_brace, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[start : index + 1]
    raise AssertionError(f"Could not extract {name}")


def _dev_states() -> dict[str, object]:
    source = (ROOT / "frontend" / "app.js").read_text(encoding="utf-8")
    functions = "\n".join(
        _extract_function(source, name)
        for name in (
            "loginFailureMessage",
            "handleDevFormSubmit",
            "devToolFailureMessage",
            "exportDebugRun",
            "loadDebugRuns",
        )
    )
    script = """
const devResult = {
  textContent: "",
  children: [],
  append(...items) { this.children.push(...items); },
};
const devModeStatus = { textContent: "Dev Mode is available. Re-auth to load debug tools." };
const apiCalls = [];
const responses = new Map();
const document = {
  querySelector(selector) {
    if (selector === "#devResult") return devResult;
    if (selector === "#devModeStatus") return devModeStatus;
    throw new Error(`Unexpected selector: ${selector}`);
  },
  createElement(tag) {
    return {
      tag,
      type: "",
      textContent: "",
      listener: null,
      addEventListener(event, listener) {
        if (event !== "click") throw new Error(`Unexpected event: ${event}`);
        this.listener = listener;
      },
    };
  },
};
class FormData { get(name) { if (name !== "code") throw new Error(name); return "entered-code"; } }
async function api(path, options = {}) {
  apiCalls.push({ path, options });
  const response = responses.get(path);
  if (response instanceof Error) throw response;
  return response;
}
function failure(status, message, retryAfter) {
  const error = new Error(message || "failure");
  error.status = status;
  error.payload = message === undefined
    ? null
    : {
        detail: {
          error: { message, ...(retryAfter ? { retry_after_seconds: retryAfter } : {}) },
        },
      };
  return error;
}
function reset() {
  devResult.textContent = "";
  devResult.children = [];
  devModeStatus.textContent = "Dev Mode is available. Re-auth to load debug tools.";
  apiCalls.length = 0;
  responses.clear();
}
function submitEvent() { return { currentTarget: {}, preventDefault() {} }; }
__FUNCTIONS__
(async () => {
  const authFailures = {};
  for (const [name, error] of [
    ["unauthorized", failure(401, "Invalid Dev Mode code.")],
    ["limited", failure(429, "Too many attempts.", 60)],
    ["disabled", failure(403, "Dev Mode is disabled.")],
  ]) {
    reset();
    responses.set("/v1/auth/dev", error);
    await handleDevFormSubmit(submitEvent());
    authFailures[name] = {
      result: devResult.textContent,
      status: devModeStatus.textContent,
      calls: apiCalls.length,
    };
  }

  reset();
  responses.set("/v1/auth/dev", { ok: true });
  await handleDevFormSubmit(submitEvent());
  const authSuccess = { result: devResult.textContent, calls: [...apiCalls] };

  reset();
  responses.set("/v1/debug/runs", failure(401, "Dev session expired."));
  await loadDebugRuns();
  const loadFailure = { result: devResult.textContent, calls: [...apiCalls] };

  reset();
  const runs = { runs: [{ run_id: "run-1" }, { run_id: "run-2" }] };
  responses.set("/v1/debug/runs", runs);
  await loadDebugRuns();
  const buttons = devResult.children.filter((item) => item.tag === "button");
  const loadSuccess = {
    result: devResult.textContent,
    buttonLabels: buttons.map((button) => button.textContent),
    calls: [...apiCalls],
  };

  responses.set("/v1/debug/export/run-1", failure(429, "Too many attempts.", 60));
  await buttons[0].listener();
  const exportFailure = { result: devResult.textContent, calls: [...apiCalls] };

  console.log(JSON.stringify({
    authFailures,
    authSuccess,
    loadFailure,
    loadSuccess,
    exportFailure,
  }));
})();
""".replace("__FUNCTIONS__", functions)
    completed = subprocess.run(
        ["node", "-e", script],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)


def test_dev_auth_failures_render_backend_truth_without_changing_availability() -> None:
    states = _dev_states()["authFailures"]
    stale = "Dev Mode is available. Re-auth to load debug tools."

    assert states["unauthorized"]["result"] == "Invalid Dev Mode code."
    assert stale not in states["unauthorized"]["result"]
    assert states["limited"]["result"] == "Too many attempts. Try again in 60 seconds."
    assert states["disabled"]["result"] == "Dev Mode is disabled."
    assert all(state["status"] == stale for state in states.values())


def test_debug_failures_name_action_and_preserve_normal_session() -> None:
    states = _dev_states()
    load_message = states["loadFailure"]["result"]
    export_message = states["exportFailure"]["result"]

    assert "Loading the run list failed" in load_message
    assert "Dev Mode re-auth is needed" in load_message
    assert "normal session remains active" in load_message
    assert "signed out" not in load_message.lower()
    assert "Exporting run run-1 failed" in export_message
    assert "Try again in 60 seconds" in export_message
    assert export_message != load_message


def test_debug_failure_does_not_retry() -> None:
    calls = _dev_states()["loadFailure"]["calls"]

    assert len(calls) == 1
    assert calls[0]["path"] == "/v1/debug/runs"


def test_dev_success_paths_are_unchanged() -> None:
    states = _dev_states()

    assert states["authSuccess"]["result"] == "Dev Mode ready."
    assert states["loadSuccess"]["result"] == json.dumps(
        {"runs": [{"run_id": "run-1"}, {"run_id": "run-2"}]},
        indent=2,
        separators=(",", ": "),
    )
    assert states["loadSuccess"]["buttonLabels"] == ["Export run-1", "Export run-2"]
