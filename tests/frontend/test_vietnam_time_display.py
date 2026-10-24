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


def test_detail_and_saved_rows_pair_vietnam_with_verbatim_utc() -> None:
    functions = _functions(
        "vietnamTimeParts",
        "formatVietnamTime",
        "savedValue",
        "decisionViewRows",
        "savedRunRows",
    )
    script = f"""
{functions}
const LIST_NOT_KEPT_TEXT = "Not kept in saved history.";
const NOT_ASSESSED_TEXT = "Not assessed";
const VENUE_LABELS = {{}};
function decisionDataText() {{ return "data"; }}
function persistenceStatusText() {{ return "storage"; }}
function formatFractionPct(value) {{ return String(value); }}
function costCaveatRows() {{ return []; }}
function decisionEvidenceText() {{ return "evidence"; }}
function dispositionLabel() {{ return "Gate disposition"; }}
function gateView() {{ return null; }}
const payload = {{normalized_symbol: "BTC/USDT", frontend_display: {{}}}};
const reference = "2026-10-24T06:46:15Z";
const horizon = "2026-10-24T12:00:00Z";
const view = {{time: {{reference_close_utc: reference, horizon_end_utc: horizon}}}};
const detailRows = decisionViewRows(payload, view);
const savedRows = savedRunRows(payload, {{
  time: {{reference_close_utc: reference, horizon_end_utc: horizon}},
  range: {{}}, evidence: {{}}, cost: {{}},
}});
const missingRows = savedRunRows(payload, {{
  time: {{reference_close_utc: null, horizon_end_utc: horizon}},
  range: {{}}, evidence: {{}}, cost: {{}},
}});
console.log(JSON.stringify({{detailRows, savedRows, missingRows, reference, horizon}}));
"""
    rendered = json.loads(_run_node(script))
    expected_reference = "2026-10-24 13:46:15 (UTC+07)"
    expected_horizon = "2026-10-24 19:00:00 (UTC+07)"
    for rows in (rendered["detailRows"], rendered["savedRows"]):
        labels = [label for label, _ in rows]
        values = dict(rows)
        for name, utc, vietnam in (
            ("Reference close", rendered["reference"], expected_reference),
            ("Horizon end", rendered["horizon"], expected_horizon),
        ):
            assert labels.index(f"{name} (Vietnam)") + 1 == labels.index(f"{name} (UTC)")
            assert values[f"{name} (UTC)"] == utc
            assert values[f"{name} (Vietnam)"] == vietnam
    missing = dict(rendered["missingRows"])
    assert missing["Reference close (Vietnam)"] == "Not kept in saved history."
    assert missing["Reference close (UTC)"] == "Not kept in saved history."
    assert "1970" not in missing["Reference close (Vietnam)"]


def test_batch_as_of_rows_pair_vietnam_with_verbatim_utc() -> None:
    source = (ROOT / "frontend" / "app.js").read_text(encoding="utf-8")
    pair = re.search(
        r'\[\s*"As of \(Vietnam\)",\s*(.*?)\s*\],\s*\["As of UTC", payload\.as_of_utc\]',
        source,
        re.DOTALL,
    )
    assert pair, "the Vietnam As of row immediately precedes the verbatim UTC row"
    expression = pair.group(1)
    functions = _functions("vietnamTimeParts", "formatVietnamTime")
    utc = "2026-10-24T06:46:15Z"
    script = f"""
{functions}
const payload = {{as_of_utc: {json.dumps(utc)}}};
const row = ["As of (Vietnam)", {expression}];
console.log(JSON.stringify([row, ["As of UTC", payload.as_of_utc]]));
"""
    vietnam_row, utc_row = json.loads(_run_node(script))
    assert vietnam_row == ["As of (Vietnam)", "2026-10-24 13:46:15 (UTC+07)"]
    assert utc_row == ["As of UTC", utc]


def _enclosing_list(text: str, index: int) -> str:
    """The bracketed list or tuple that contains `index`, so a name's company can be checked."""

    opens, closes = {"(": ")", "[": "]", "{": "}"}, {")": "(", "]": "[", "}": "{"}
    depth: list[int] = []
    for position, character in enumerate(text[:index]):
        if character in opens:
            depth.append(position)
        elif character in closes and depth:
            depth.pop()
    if not depth:
        return text
    start = depth[-1]
    pending = 0
    for position in range(start, len(text)):
        if text[position] in opens:
            pending += 1
        elif text[position] in closes:
            pending -= 1
            if pending == 0:
                return text[start : position + 1]
    return text[start:]


def test_every_site_that_assembles_a_vietnam_caller_also_assembles_the_formatter() -> None:
    """A dependency travels with the function, wherever app.js is cut up.

    This class of defect bit three times while this change was made: `markRefreshed`,
    `formatRecentTime`, the two Detail/Saved row builders and `renderStructuredDetail` each gained a
    call to a Vietnam formatter, and every place that assembles those functions out of app.js — two
    test cut-lists, then `scripts/ux_comprehension/card.py`, then another test — broke with
    "formatVietnamTime is not defined" until its list was extended. The dependency set is read from
    app.js here, so a new caller is covered without touching this test.
    """

    source = (ROOT / "frontend" / "app.js").read_text(encoding="utf-8")
    formatters = ("formatVietnamTime", "formatVietnamClock")
    callers: dict[str, str] = {}
    for name in re.findall(r"^function ([A-Za-z0-9_]+)\(", source, re.M):
        if name in formatters or name == "vietnamTimeParts":
            continue
        body = _extract_function(source, name)
        for formatter in formatters:
            # The identifier, not a call: savedRunRows passes formatVietnamTime to savedValue by
            # reference, and that is just as much a dependency as calling it.
            if re.search(rf"\b{formatter}\b", body):
                callers[name] = formatter
    assert set(callers) >= {
        "markRefreshed",
        "formatRecentTime",
        "decisionViewRows",
        "savedRunRows",
        "renderStructuredDetail",
    }, callers

    # Only files that actually cut functions out of app.js by name are in scope.
    assembles = ("_extract_function", "extract_javascript_function", "_extract(", "_FUNCTIONS")
    # A file that hands node the WHOLE of app.js has every function by construction. Each exemption
    # must prove that, so it cannot go stale into a real gap.
    whole_file = ("APP_JS.read_text", 'app.js").read_text(')
    exempt = {
        "tests/frontend/test_ux_comprehension_card.py",
        "tests/frontend/fullscreen_goldens.py",
    }
    roots = (ROOT / "tests", ROOT / "scripts")
    checked = 0
    for path in sorted(p for root in roots for p in root.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        relative = path.relative_to(ROOT).as_posix()
        if relative in exempt:
            assert any(marker in text for marker in whole_file), (
                f"{relative} is exempted as loading the whole of app.js, but no longer does: "
                f"it must declare the formatters it assembles"
            )
            continue
        if not any(marker in text for marker in assembles):
            continue
        for caller, formatter in callers.items():
            quoted = f'"{caller}"'
            if quoted not in text:
                continue
            # The formatter must be in the SAME list as the caller, not merely somewhere in the
            # file: a file that mentions the name in prose or in an assertion would otherwise
            # satisfy a whole-file search while its cut-list stayed short.
            block = _enclosing_list(text, text.index(quoted))
            # Only a list of names is a cut-list that gets run. A single name inside a call, as in
            # `_function_text(js, "decisionViewRows")`, is a static read of that function's source
            # for inspection: nothing executes, so nothing has to be assembled with it.
            if len(re.findall(r'"[A-Za-z_][A-Za-z0-9_]*"', block)) < 2:
                continue
            # A cut-list is a tuple or a list, because the assembled order matters. A set literal is
            # something else — this test's own completeness check, for one — and never assembles.
            if block.startswith("{"):
                continue
            checked += 1
            assert formatter in block and "vietnamTimeParts" in block, (
                f"{path.relative_to(ROOT)} assembles {caller}, which needs {formatter}, "
                f"but that name list does not include it: node would raise "
                f"'{formatter} is not defined'"
            )
    assert checked >= 6, f"expected several assembly sites, found {checked}"


def test_a_falsy_stored_time_is_not_kept_rather_than_the_epoch() -> None:
    """A stored 0 must not become a 1970 time beside a UTC row that shows 0.

    `savedValue` only treats null and undefined as absent, so a falsy-but-present value would
    otherwise reach the formatter and render the epoch. The saved rows pass `|| null` for exactly
    that reason; this pins both the helper's behaviour and the call sites.
    """

    functions = _functions("vietnamTimeParts", "formatVietnamTime", "savedValue")
    script = f"""
{functions}
const LIST_NOT_KEPT_TEXT = "Not kept in saved history.";
console.log(JSON.stringify({{
  guarded: savedValue(0 || null, formatVietnamTime),
  unguarded: savedValue(0, formatVietnamTime),
  utc_row_keeps_raw: savedValue(0),
  real_instant: savedValue("2026-06-06T18:00:00Z", formatVietnamTime),
}}));
"""
    shown = json.loads(_run_node(script))
    assert shown["guarded"] == "Not kept in saved history.", shown
    assert "1970" in shown["unguarded"], "without the guard a 0 renders the epoch: that is the risk"
    assert shown["utc_row_keeps_raw"] == 0, shown
    assert shown["real_instant"] == "2026-06-07 01:00:00 (UTC+07)", shown

    # Both saved Vietnam rows must carry the guard, or the row would show a 1970 time.
    source = (ROOT / "frontend" / "app.js").read_text(encoding="utf-8")
    rows = _extract_function(source, "savedRunRows")
    for field in ("reference_close_utc", "horizon_end_utc"):
        assert f"savedValue(time.{field} || null, formatVietnamTime)" in rows, field
