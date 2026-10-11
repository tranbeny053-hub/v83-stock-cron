"""The gate brief's lists when a value is not a list.

A saved run read back from the durable store carries a mask where its `key_reasons` were (the
export sanitizer withholds a key whose name reads as a credential's; utils/sanitize.py is not
changed here). The detail panel used to list a string one character a line. The real app.js
renders each kind of value here: a list is listed, a missing list reads "none" as before, and
anything else that is not a list says in one line that it is not kept: never the value, never its
characters. The same renderer shows the brief's four lists, so the same holds for each, and the
last test proves it on a real analysis read back as the store exports it.
"""

from __future__ import annotations

import copy
import json
import subprocess

import pytest
import test_accepted_state_rendering as harness

from crypto_probability_engine.utils.sanitize import sanitize_for_export

NOT_KEPT = "Not kept in saved history."
MASK = "set (****)"
LISTS = ("Key Reasons", "Hard Blockers", "Watchlist Triggers", "Invalidation Conditions")

_RENDER = r"""
const mask = "set (****)";
const shown = (node) => visibleTexts(fakeElement("div", "", [node]));
const group = (items) => shown(briefListGroup("Key Reasons", items));
const out = {
  constant: LIST_NOT_KEPT_TEXT,
  groups: {
    list: group(["One reason.", "Another reason."]),
    emptyList: group([]),
    missing: group(undefined),
    nothing: group(null),
    mask: group(mask),
    emptyText: group(""),
    number: group(0),
    object: group({ 0: "s", length: 1 }),
    flag: group(true),
  },
  // A stored brief whose four lists are all withheld, through the section that shows them.
  everyListWithheld: shown(
    renderDecisionBrief(
      {
        key_reasons: mask,
        hard_blockers: mask,
        watchlist_triggers: mask,
        invalidation_conditions: mask,
      },
      [],
      {},
    ),
  ),
  // The backend's blocking reasons are shown first, as before, whatever the brief stores.
  blockingReasons: shown(
    renderDecisionBrief(
      { key_reasons: mask, hard_blockers: ["SKILL_NOT_DEMONSTRATED"] },
      [{ headline: "A headline", detail: "Its detail." }],
      {},
    ),
  ),
};
process.stdout.write(JSON.stringify(out), () => process.exit(0));
"""


@pytest.fixture(scope="module")
def rendered() -> dict:
    assert harness.NODE is not None, "node is required to run the real app.js"
    script = "\n".join(
        [
            harness._DOM_STAND_IN,
            (harness.ROOT / "frontend" / "app.js").read_text(encoding="utf-8"),
            _RENDER,
        ]
    )
    done = subprocess.run(  # noqa: S603 - node on a script built here
        [harness.NODE, "-"],
        input=script,
        capture_output=True,
        encoding="utf-8",
        check=True,
        timeout=60,
    )
    return json.loads(done.stdout)


def test_a_list_is_listed_and_a_missing_list_reads_none_as_before(rendered: dict) -> None:
    groups = rendered["groups"]
    assert groups["list"] == ["Key Reasons", "One reason.", "Another reason."]
    for name in ("emptyList", "missing", "nothing"):
        assert groups[name] == ["Key Reasons", "none"], name


def test_a_value_that_is_not_a_list_is_said_in_one_line(rendered: dict) -> None:
    assert rendered["constant"] == NOT_KEPT
    for name in ("mask", "emptyText", "number", "object", "flag"):
        assert rendered["groups"][name] == ["Key Reasons", NOT_KEPT], name


def test_each_of_the_briefs_lists_is_shown_by_the_same_renderer(rendered: dict) -> None:
    texts = rendered["everyListWithheld"]
    for title in LISTS:
        assert harness._value(texts, title) == NOT_KEPT, title
    assert texts.count(NOT_KEPT) == 4 and texts[-8:] == [
        line for title in LISTS for line in (title, NOT_KEPT)
    ]
    assert not any(MASK in text or len(text) == 1 for text in texts)


def test_the_backends_blocking_reasons_still_come_first(rendered: dict) -> None:
    texts = rendered["blockingReasons"]
    assert harness._between(texts, "Key Reasons", "Hard Blockers") == [
        "Key Reasons",
        "A headline: Its detail.",
    ]
    assert harness._value(texts, "Hard Blockers") == "SKILL_NOT_DEMONSTRATED"
    assert NOT_KEPT not in texts and not any(MASK in text for text in texts)


_RENDER_SAVED_RUN = r"""
(async () => {
  renderStructuredDetail(saved.row, saved.detail);
  for (let tick = 0; tick < 5; tick += 1) await new Promise((done) => setTimeout(done, 0));
  const texts = visibleTexts(detailPanel, ["raw-json", "calibration-timeframe-card"]);
  process.stdout.write(JSON.stringify(texts), () => process.exit(0));
})();
"""


@pytest.fixture(scope="module")
def saved_run() -> dict:
    """A real analysis as a saved run is read back: a history row, and the detail as the store
    exports it."""

    payload = harness._analysis("1H")
    row = {
        "run_id": payload["run_id"],
        "symbol": payload["symbol"],
        "normalized_symbol": payload["normalized_symbol"],
        "analysis_mode": payload["analysis_mode"],
        "as_of_utc": payload["as_of_utc"],
        "prediction_origin": "USER_REQUESTED",
        "detail_available": True,
        "primary_timeframe": "1H",
    }
    return {
        "live": payload,
        "row": row,
        "detail": sanitize_for_export(copy.deepcopy(payload["detail_view"])),
    }


def test_a_real_saved_run_says_its_key_reasons_are_not_kept(saved_run: dict) -> None:
    live_brief = saved_run["live"]["detail_view"]["decision_brief"]
    stored_brief = saved_run["detail"]["decision_brief"]
    assert isinstance(live_brief["key_reasons"], list) and live_brief["key_reasons"]
    assert stored_brief["key_reasons"] == MASK, "the store's export withholds the list"
    assert stored_brief["hard_blockers"] == live_brief["hard_blockers"]

    assert harness.NODE is not None, "node is required to run the real app.js"
    script = "\n".join(
        [
            harness._DOM_STAND_IN,
            (harness.ROOT / "frontend" / "app.js").read_text(encoding="utf-8"),
            f"const saved = {json.dumps(saved_run, default=str)};",
            _RENDER_SAVED_RUN,
        ]
    )
    done = subprocess.run(  # noqa: S603 - node on a script built here
        [harness.NODE, "-"],
        input=script,
        capture_output=True,
        encoding="utf-8",
        check=True,
        timeout=60,
    )
    texts = json.loads(done.stdout)

    assert harness._between(texts, "Key Reasons", "Hard Blockers") == ["Key Reasons", NOT_KEPT]
    assert texts.count(NOT_KEPT) == 1, "the brief's other lists are stored, and listed"
    blockers = harness._between(texts, "Hard Blockers", "Watchlist Triggers")
    assert blockers == ["Hard Blockers", *live_brief["hard_blockers"]]
    assert not any(MASK in text for text in texts)
    lists = harness._between(texts, "Key Reasons", "Invalidation Conditions")
    assert not any(len(text) == 1 for text in lists), "no list is shown a character a line"
