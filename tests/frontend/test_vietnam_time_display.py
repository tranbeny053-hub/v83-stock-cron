from __future__ import annotations

import json
import os
import re
import shutil
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


def _functions(*names: str) -> str:
    source = (ROOT / "frontend" / "app.js").read_text(encoding="utf-8")
    return "\n".join(_extract_function(source, name) for name in names)


NODE = shutil.which("node")


def _run_node(script: str, *, env: dict[str, str] | None = None) -> str:
    # The script goes on stdin, never in argv: conftest.py enforces Linux's 128 KiB argument limit.
    assert NODE is not None, "node is required to run the real app.js"
    completed = subprocess.run(  # noqa: S603 - node on a script built here
        [NODE],
        input=script,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
        env=env,
    )
    return completed.stdout.strip()


def test_vietnam_formatters_render_known_instants_and_boundaries() -> None:
    functions = _functions("vietnamTimeParts", "formatVietnamTime", "formatVietnamClock")
    script = f"""
{functions}
console.log(JSON.stringify({{
  full: formatVietnamTime("2026-10-24T06:46:15Z"),
  clock: formatVietnamClock("2026-10-24T06:46:15Z"),
  midnight: formatVietnamTime("2026-10-23T17:00:00Z"),
}}));
"""
    assert json.loads(_run_node(script)) == {
        "full": "2026-10-24 13:46:15 (UTC+07)",
        "clock": "13:46:15 (UTC+07)",
        "midnight": "2026-10-24 00:00:00 (UTC+07)",
    }


def test_vietnam_offset_is_seven_hours_in_january_and_july() -> None:
    functions = _functions("vietnamTimeParts", "formatVietnamTime")
    script = f"""
{functions}
console.log(JSON.stringify([
  formatVietnamTime("2026-01-15T12:00:00Z"),
  formatVietnamTime("2026-07-15T12:00:00Z"),
]));
"""
    # The whole string, not just the suffix: a wrong hour must fail this test.
    assert json.loads(_run_node(script)) == [
        "2026-01-15 19:00:00 (UTC+07)",
        "2026-07-15 19:00:00 (UTC+07)",
    ]


def test_vietnam_format_is_machine_independent() -> None:
    functions = _functions("vietnamTimeParts", "formatVietnamTime")
    script = f"""
{functions}
console.log(formatVietnamTime("2026-10-24T06:46:15Z"));
"""
    base_env = os.environ.copy()
    outputs = []
    for timezone, locale in (
        ("UTC", None),
        ("America/New_York", "de_DE.UTF-8"),
        ("Asia/Tokyo", None),
    ):
        env = base_env.copy()
        env["TZ"] = timezone
        if locale is not None:
            env["LC_ALL"] = locale
        else:
            env.pop("LC_ALL", None)
        outputs.append(_run_node(script, env=env))
    assert outputs == ["2026-10-24 13:46:15 (UTC+07)"] * 3


def test_vietnam_formatters_pass_through_invalid_values_without_throwing() -> None:
    functions = _functions("vietnamTimeParts", "formatVietnamTime", "formatVietnamClock")
    script = f"""
{functions}
const values = [null, undefined, "", "not a time"];
console.log(JSON.stringify(values.map((value) => [
  formatVietnamTime(value), formatVietnamClock(value),
])));
"""
    assert json.loads(_run_node(script)) == [
        ["", ""],
        ["", ""],
        ["", ""],
        ["not a time", "not a time"],
    ]


def test_refresh_and_recent_time_use_vietnam_formatters() -> None:
    functions = _functions(
        "vietnamTimeParts",
        "formatVietnamTime",
        "formatVietnamClock",
        "markRefreshed",
        "formatRecentTime",
    )
    script = f"""
{functions}
const RealDate = Date;
globalThis.Date = class FixedDate extends RealDate {{
  constructor(value) {{ super(value === undefined ? "2026-10-24T06:46:15Z" : value); }}
}};
const lastRefreshed = {{ textContent: "" }};
function startRefreshCooldown() {{}}
markRefreshed();
console.log(JSON.stringify({{
  refreshed: lastRefreshed.textContent,
  recent: formatRecentTime("2026-10-24T06:46:15Z"),
  unavailable: formatRecentTime(null),
}}));
"""
    assert json.loads(_run_node(script)) == {
        "refreshed": "last refreshed at 13:46:15 (UTC+07)",
        "recent": "2026-10-24 13:46:15 (UTC+07)",
        "unavailable": "Time unavailable",
    }


def test_machine_dependent_locale_calls_are_absent() -> None:
    source = (ROOT / "frontend" / "app.js").read_text(encoding="utf-8")
    assert re.search(r"toLocaleTimeString\(", source) is None
    assert re.search(r"toLocaleString\(", source) is None
