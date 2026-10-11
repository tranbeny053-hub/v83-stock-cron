from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# The header badge is storage's status when it was last asked (owner ruling "relabel",
# PROVISIONAL wording): a save receipt can say otherwise for one analysis.
BADGE_PREFIX = "Storage, last checked: "


def _extract_function(source: str, name: str) -> str:
    start = source.index(f"function {name}(")
    # Past the parameter list first: a default parameter may itself be "{}".
    depth, index = 0, source.index("(", start)
    while True:
        depth += {"(": 1, ")": -1}.get(source[index], 0)
        index += 1
        if depth == 0:
            break
    opening_brace = source.index("{", index)
    depth = 0
    for index in range(opening_brace, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[start : index + 1]
    raise AssertionError(f"Could not extract {name}")


def _rendered_states() -> list[dict[str, object]]:
    source = (ROOT / "frontend" / "app.js").read_text(encoding="utf-8")
    functions = "\n".join(
        _extract_function(source, name)
        for name in ("persistenceStatusText", "updatePersistenceStatus")
    )
    script = f"""
const persistenceStatusBadge = {{
  textContent: "",
  dataset: {{}},
  classList: {{
    values: new Set(["status-badge", "status-unknown"]),
    add(value) {{ this.values.add(value); }},
    remove(...values) {{ values.forEach((value) => this.values.delete(value)); }},
  }},
}};
{functions}
const cases = ["OK", "STATELESS", "UNAVAILABLE", "FUTURE_STATUS", undefined];
const rendered = cases.map((status) => {{
  updatePersistenceStatus(status);
  return {{
    text: persistenceStatusBadge.textContent,
    rawStatus: persistenceStatusBadge.dataset.persistenceStatus,
    classes: [...persistenceStatusBadge.classList.values].sort(),
  }};
}});
console.log(JSON.stringify(rendered));
"""
    completed = subprocess.run(
        ["node", "-e", script],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)


def _rendered_detail_overviews() -> list[list[list[object]]]:
    source = (ROOT / "frontend" / "app.js").read_text(encoding="utf-8")
    functions = "\n".join(
        _extract_function(source, name)
        for name in (
            "formatValue",
            "persistenceStatusText",
            "decisionViewOf",
            "savedRunViewOf",
            "decisionDataText",
            "notAssessedByView",
            "legacyProbabilityRows",
            "acceptedViewOf",
            "readinessText",
            "renderStructuredDetail",
        )
    )
    script = f"""
{functions}
const overviewRows = [];
const element = () => ({{
  append() {{}},
  classList: {{ remove() {{}} }},
  className: "",
  textContent: "",
}});
const document = {{ createElement: element }};
const detailPanel = {{ replaceChildren() {{}}, classList: {{ remove() {{}} }} }};
const keyValueTable = (values) => {{
  overviewRows.push(values.map(([label, value]) => [label, formatValue(value)]));
  return element();
}};
const section = () => element();
const downloadJsonButton = () => element();
const renderDecisionSynthesis = () => element();
const renderModelQualitySection = () => element();
const renderDecisionBrief = () => element();
const objectTable = () => element();
const formatPct = (value) => value;
const modelReadinessCopy = "";
const cases = [
  {{ status: "OK", live: true, includeLive: true }},
  {{ status: "STATELESS", live: false, includeLive: true }},
  {{ status: "UNAVAILABLE", live: null, includeLive: false }},
  {{ status: "FUTURE_STATUS", live: "true", includeLive: true }},
];
const rendered = cases.map((item) => {{
  overviewRows.length = 0;
  const frontend_display = {{}};
  if (item.includeLive) frontend_display.is_live_data = item.live;
  renderStructuredDetail(
    {{ frontend_display, debug: {{ persistence_status: item.status }} }},
    {{}},
  );
  return overviewRows[0];
}});
console.log(JSON.stringify(rendered));
"""
    completed = subprocess.run(
        ["node", "-e", script],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)


def test_persistence_badge_explains_consequences_without_changing_identity() -> None:
    ok, stateless, unavailable, unrecognised, missing = _rendered_states()

    assert ok == {
        "text": "Storage, last checked: Storage available",
        "rawStatus": "OK",
        "classes": ["status-badge", "status-ok"],
    }
    assert "saved" not in str(ok["text"]).lower()

    assert stateless == {
        "text": (
            "Storage, last checked: No storage configured — analyses are kept only until "
            "the server restarts"
        ),
        "rawStatus": "STATELESS",
        "classes": ["status-badge", "status-warn"],
    }
    assert unavailable == {
        "text": (
            "Storage, last checked: Storage unavailable when requested — this analysis may "
            "not be kept in Recent Analysis history"
        ),
        "rawStatus": "UNAVAILABLE",
        "classes": ["status-badge", "status-warn"],
    }
    assert stateless["text"] != unavailable["text"]

    assert unrecognised == {
        "text": "Storage, last checked: Storage status unknown",
        "rawStatus": "FUTURE_STATUS",
        "classes": ["status-badge", "status-unknown"],
    }
    assert missing == {
        "text": "Storage, last checked: Storage status unknown",
        "rawStatus": "UNKNOWN",
        "classes": ["status-badge", "status-unknown"],
    }
    for unknown in (unrecognised, missing):
        text = str(unknown["text"]).lower()
        assert "retained" not in text
        assert "history" not in text


def test_no_status_sentence_forecasts_what_a_save_receipt_can_refute() -> None:
    """The status is what storage said when it was asked. Whether one analysis is saved is for
    its save receipt to say, and that can be "Saved…" after an UNAVAILABLE status: an outage's
    cooldown ends, and the save succeeds. So no status sentence says that an analysis is not
    being kept, will not be kept, or was saved (owner ruling "relabel"; PROVISIONAL wording)."""

    states = _rendered_states()
    for state in states:
        text = str(state["text"]).lower()
        for forecast in ("will not", "not being", "not retained", "not appear", "saved"):
            assert forecast not in text, (state["rawStatus"], forecast)
    unavailable = str(states[2]["text"])
    assert states[2]["rawStatus"] == "UNAVAILABLE"
    # It names the moment it is true of, and states a possibility.
    assert "Storage unavailable when requested" in unavailable
    assert "may not be kept in Recent Analysis history" in unavailable


def test_the_deployment_checklist_quotes_the_badge_as_the_screen_shows_it() -> None:
    """DEPLOYMENT_CHECKLIST.md tells the operator what to do when the badge reads "unavailable"
    on Hugging Face. It quotes the badge, so it quotes it as the screen shows it."""

    unavailable = _rendered_states()[2]
    assert unavailable["rawStatus"] == "UNAVAILABLE"
    checklist = (ROOT / "DEPLOYMENT_CHECKLIST.md").read_text(encoding="utf-8")
    assert f"- [ ] If `{unavailable['text']}` appears on Hugging Face with only" in checklist
    assert "Persistence: UNAVAILABLE" not in checklist


def test_detail_uses_badge_persistence_wording_and_formats_live_data() -> None:
    badge_states = _rendered_states()
    detail_overviews = _rendered_detail_overviews()

    for badge, overview in zip(badge_states[:4], detail_overviews[:4], strict=True):
        rows = dict(overview)
        # The Overview's row is storage's status at request time, and its label says so: the
        # decision view's Storage row shows the save receipt, which can say otherwise.
        assert str(badge["text"]).startswith(BADGE_PREFIX)
        assert rows["Storage when requested"] == str(badge["text"]).removeprefix(BADGE_PREFIX)
        assert "Persistence" not in rows and "Storage" not in rows

    assert dict(detail_overviews[0])["Live data"] == "yes"
    assert dict(detail_overviews[1])["Live data"] == "no"
    assert dict(detail_overviews[2])["Live data"] == "n/a"
    assert "saved" not in dict(detail_overviews[0])["Storage when requested"].lower()
