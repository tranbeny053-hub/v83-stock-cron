"""The shared fold's size (F-4): frontend/app.js nestedValueBlock, and the renderers that use it.

A list or an object the backend gives is shown whole, as a fold over its JSON. A list's fold names
its size: "0 items", "1 item", "2 items" (the plural for every size but one). An object's fold
reads "View". Two renderers show the fold: a key/value row whose value is a list of objects
(appendDefinitionRows, through keyValueTable: the News Authority's "Provider status" row, for one;
test_news_addon_rows.py reads it over the real backend's answers), and a detail table's nested
value (objectTable). What the fold does not reach is as it was: a key/value row's empty list reads
"none", and a list of plain values is joined (formatValue).

The whole of app.js runs under Node on the goldens' DOM stand-in. The script holds all of app.js,
so node reads it on stdin (conftest.py).
"""

from __future__ import annotations

import json
import re
import subprocess
from typing import Any

import fullscreen_goldens as goldens
import pytest

harness = goldens.harness

FRED = {"provider": "fred", "status": "OK"}
GDELT = {"provider": "gdelt", "status": "UNAVAILABLE", "last_failure_error_code": "RATE_LIMITED"}
# name -> a value the backend could give, and the summary its fold must read.
FOLDS: dict[str, tuple[Any, str]] = {
    "no_items": ([], "0 items"),
    "one_object": ([FRED], "1 item"),
    "one_number": ([7], "1 item"),
    "two_objects": ([FRED, GDELT], "2 items"),
    "three_numbers": ([1, 2, 3], "3 items"),
    "eleven_items": (list(range(11)), "11 items"),
    "twenty_one_items": (list(range(21)), "21 items"),
    "an_object": ({"status": "OK", "providers": [FRED]}, "View"),
    "an_empty_object": ({}, "View"),
}
# The key/value rows (label, value) of one table, as appendDefinitionRows is given them.
ROWS = [
    ["Provider status", [FRED]],
    ["Providers", [FRED, GDELT]],
    ["Some objects", ["a", {"b": 1}]],
    ["No providers", []],
    ["Plain values", ["a", "b"]],
    ["One plain value", ["a"]],
]
# A detail table's object, as objectTable is given it: its keys are its labels.
TABLE = {
    "no_items": [],
    "one_item": [FRED],
    "two_items": [FRED, GDELT],
    "an_object": {"status": "OK"},
    "a_number": 3,
    "missing": None,
}

_CALLS = r"""
const shown = (node) => visibleTexts(fakeElement("div", "", [node]));
const foldsIn = (node) =>
  node.querySelectorAll("details").map((fold) => ({
    parts: fold.children.map((child) => child.tagName),
    summary: fold.children[0].textContent,
    json: fold.children[1].textContent,
  }));
const out = { folds: {}, rows: {}, table: {} };
for (const [name, value] of Object.entries(folds)) {
  const node = nestedValueBlock(value);
  out.folds[name] = { tag: node.tagName, folds: foldsIn(fakeElement("div", "", [node])) };
}
const rowsTable = keyValueTable(rows);
out.rows = { tag: rowsTable.tagName, texts: shown(rowsTable), folds: foldsIn(rowsTable) };
const detailTable = objectTable(table);
out.table = { tag: detailTable.tagName, texts: shown(detailTable), folds: foldsIn(detailTable) };
process.stdout.write(JSON.stringify(out), () => process.exit(0));
"""


@pytest.fixture(scope="module")
def rendered() -> dict[str, Any]:
    """What the real app.js draws for each value, each row and the table."""

    assert harness.NODE is not None, "node is required to run the real app.js"
    script = "\n".join(
        [
            harness._DOM_STAND_IN,
            (harness.ROOT / "frontend" / "app.js").read_text(encoding="utf-8"),
            f"const folds = {json.dumps({name: value for name, (value, _) in FOLDS.items()})};",
            f"const rows = {json.dumps(ROWS)};",
            f"const table = {json.dumps(TABLE)};",
            _CALLS,
        ]
    )
    done = subprocess.run(  # noqa: S603 - node on a script built here, read on stdin
        [harness.NODE, "-"], input=script, capture_output=True, encoding="utf-8", timeout=60
    )
    assert done.returncode == 0, done.stderr[-2000:]
    return json.loads(done.stdout)


def _json(value: Any) -> str:
    """The fold's JSON as app.js prints it (JSON.stringify(value, null, 2))."""

    return json.dumps(value, indent=2)


@pytest.mark.parametrize("name", list(FOLDS))
def test_a_lists_fold_names_its_size_and_an_objects_reads_view(
    rendered: dict[str, Any], name: str
) -> None:
    """0, 1 and N: "0 items", "1 item", "N items"; an object, empty or not: "View". The fold is a
    details element whose summary names the size, over the value's JSON, whole."""

    value, summary = FOLDS[name]
    drawn = rendered["folds"][name]
    assert drawn["tag"] == "DETAILS"
    (fold,) = drawn["folds"]
    assert fold == {"parts": ["SUMMARY", "PRE"], "summary": summary, "json": _json(value)}
    assert json.loads(fold["json"]) == value


def test_the_singular_is_for_one_alone() -> None:
    """The cases above hold the boundary: one is singular; none, two and the larger sizes whose
    last digit is one are plural."""

    sizes = {len(value): summary for value, summary in FOLDS.values() if isinstance(value, list)}
    assert sizes == {
        0: "0 items",
        1: "1 item",
        2: "2 items",
        3: "3 items",
        11: "11 items",
        21: "21 items",
    }


def test_a_key_value_row_holding_a_list_of_objects_shows_the_fold(
    rendered: dict[str, Any],
) -> None:
    """appendDefinitionRows, through keyValueTable: a list that holds an object is shown whole,
    as the fold, with its size in the same words; any other list is text as before ("none" for an
    empty one, joined values for plain ones)."""

    rows = rendered["rows"]
    assert rows["tag"] == "DL"
    assert rows["texts"] == [
        "Provider status",
        "1 item",
        _json([FRED]),
        "Providers",
        "2 items",
        _json([FRED, GDELT]),
        "Some objects",
        "2 items",
        _json(["a", {"b": 1}]),
        "No providers",
        "none",
        "Plain values",
        "a, b",
        "One plain value",
        "a",
    ]
    assert [fold["summary"] for fold in rows["folds"]] == ["1 item", "2 items", "2 items"]


def test_a_detail_tables_nested_list_shows_the_fold(rendered: dict[str, Any]) -> None:
    """objectTable: a nested list is the fold with its size (none, one, two); a nested object is
    the fold that reads "View"; a plain value is text as before."""

    table = rendered["table"]
    assert table["tag"] == "TABLE"
    assert table["texts"] == [
        "no items",
        "0 items",
        "[]",
        "one item",
        "1 item",
        _json([FRED]),
        "two items",
        "2 items",
        _json([FRED, GDELT]),
        "an object",
        "View",
        _json({"status": "OK"}),
        "a number",
        "3",
        "missing",
        "n/a",
    ]
    assert [fold["summary"] for fold in table["folds"]] == ["0 items", "1 item", "2 items", "View"]


def test_no_whole_screen_golden_holds_a_fold_in_the_wrong_number() -> None:
    """Every list's fold a committed golden shows is the fold of an empty list: "0 items", which
    stays. None reads "1 items", or "N item"."""

    lines = [
        line
        for content in goldens.committed().values()
        for line in goldens.decode(content)
        if re.fullmatch(r"\d+ items?", line)
    ]
    assert lines and set(lines) == {"0 items"}
