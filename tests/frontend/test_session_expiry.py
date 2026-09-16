from __future__ import annotations

import json
import re
import subprocess
from collections import Counter
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


def _session_api_states() -> dict[str, object]:
    source = (ROOT / "frontend" / "app.js").read_text(encoding="utf-8")
    functions = "\n".join(
        _extract_function(source, name) for name in ("sessionApi", "handleSessionExpired")
    )
    script = f"""
let sessionGeneration = 0;
let resetCalls = 0;
let hidden = false;
let apiImpl = async () => ({{}});
const loginStatus = {{ textContent: "" }};
const workspace = {{ classList: {{ contains: (name) => name === "hidden" && hidden }} }};
async function api(path, options = {{}}) {{ return apiImpl(path, options); }}
function resetToLoggedOut() {{
  resetCalls += 1;
  hidden = true;
  loginStatus.textContent = "";
}}
function resetCase() {{
  sessionGeneration = 0;
  resetCalls = 0;
  hidden = false;
  loginStatus.textContent = "";
}}
function failure(status) {{
  const error = new Error("failure");
  if (status !== undefined) error.status = status;
  return error;
}}
{functions}
(async () => {{
  resetCase();
  const unauthorized = failure(401);
  apiImpl = async () => {{ throw unauthorized; }};
  let rethrown401 = false;
  try {{
    await sessionApi("/protected");
  }} catch (error) {{
    rethrown401 = error === unauthorized;
  }}
  const expired = {{
    resetCalls,
    message: loginStatus.textContent,
    rethrown401,
  }};

  resetCase();
  apiImpl = async () => {{ throw failure(500); }};
  try {{ await sessionApi("/protected"); }} catch {{}}
  const serverFailureResetCalls = resetCalls;

  resetCase();
  apiImpl = async () => {{ throw failure(); }};
  try {{ await sessionApi("/protected"); }} catch {{}}
  const networkFailureResetCalls = resetCalls;

  resetCase();
  const payload = {{ ok: true }};
  apiImpl = async () => payload;
  const returnedPayload = await sessionApi("/protected");
  const success = {{ returnedSamePayload: returnedPayload === payload, resetCalls }};

  resetCase();
  apiImpl = async () => {{ throw failure(401); }};
  await Promise.allSettled([sessionApi("/first"), sessionApi("/second")]);
  const concurrentResetCalls = resetCalls;

  resetCase();
  let rejectPending;
  apiImpl = () => new Promise((resolve, reject) => {{ rejectPending = reject; }});
  const staleRequest = sessionApi("/protected");
  sessionGeneration += 1;
  rejectPending(failure(401));
  await staleRequest.catch(() => {{}});
  const staleGenerationResetCalls = resetCalls;

  resetCase();
  hidden = true;
  handleSessionExpired(sessionGeneration);
  const hiddenWorkspaceResetCalls = resetCalls;

  console.log(JSON.stringify({{
    expired,
    serverFailureResetCalls,
    networkFailureResetCalls,
    success,
    concurrentResetCalls,
    staleGenerationResetCalls,
    hiddenWorkspaceResetCalls,
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


def test_session_api_recovers_only_from_current_session_401() -> None:
    states = _session_api_states()

    assert states["expired"] == {
        "resetCalls": 1,
        "message": "Your session expired. Please sign in again.",
        "rethrown401": True,
    }
    assert states["serverFailureResetCalls"] == 0
    assert states["networkFailureResetCalls"] == 0
    assert states["success"] == {"returnedSamePayload": True, "resetCalls": 0}
    assert states["concurrentResetCalls"] == 1
    assert states["staleGenerationResetCalls"] == 0
    assert states["hiddenWorkspaceResetCalls"] == 0


def test_api_call_sites_have_explicit_session_classification() -> None:
    source = (ROOT / "frontend" / "app.js").read_text(encoding="utf-8")
    call_pattern = re.compile(r"\b(sessionApi|api)\(\s*([\"`])([^\"`]+)\2")
    actual = Counter((wrapper, path) for wrapper, _, path in call_pattern.findall(source))

    expected_recover = Counter(
        {
            # require_app_session: an app-session 401 expires the normal workspace session.
            ("sessionApi", "/v1/system_status"): 1,
            ("sessionApi", "/v1/analyze"): 1,
            ("sessionApi", "/v1/analyze/detail/${payload.run_id}"): 1,
            ("sessionApi", "/v1/runs"): 2,
            ("sessionApi", "/v1/calibration"): 1,
            ("sessionApi", "/v1/analyze_batch"): 1,
            ("sessionApi", "/v1/watchlist"): 2,
            ("sessionApi", "/v1/watchlist/${encodeURIComponent(symbol)}"): 1,
        }
    )
    expected_exclude = Counter(
        {
            # Public auth route: a 401 rejects the access code, not an existing session.
            ("api", "/v1/auth/login"): 1,
            # require_app_session, but logout already owns its explicit 401 reset behavior.
            ("api", "/v1/auth/logout"): 1,
            # Public dev-auth route: a 401 rejects only the dev code.
            ("api", "/v1/auth/dev"): 1,
            # require_app_dev_session: a 401 must preserve the normal app session.
            ("api", "/v1/debug/runs"): 1,
            ("api", "/v1/debug/export/${run.run_id}"): 1,
        }
    )

    assert actual == expected_recover + expected_exclude
