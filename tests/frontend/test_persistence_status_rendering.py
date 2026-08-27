from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _extract_function(source: str, name: str) -> str:
    start = source.index(f"function {name}(")
    opening_brace = source.index("{", start)
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
    function = _extract_function(source, "updatePersistenceStatus")
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
{function}
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


def test_persistence_badge_explains_consequences_without_changing_identity() -> None:
    ok, stateless, unavailable, unrecognised, missing = _rendered_states()

    assert ok == {
        "text": "Persistence: Storage available",
        "rawStatus": "OK",
        "classes": ["status-badge", "status-ok"],
    }
    assert "saved" not in str(ok["text"]).lower()

    assert stateless == {
        "text": (
            "Persistence: No storage configured — analyses are not retained and will "
            "not appear in Recent Analysis history"
        ),
        "rawStatus": "STATELESS",
        "classes": ["status-badge", "status-warn"],
    }
    assert unavailable == {
        "text": (
            "Persistence: Storage unavailable — this analysis is not being retained "
            "and will not appear in Recent Analysis history"
        ),
        "rawStatus": "UNAVAILABLE",
        "classes": ["status-badge", "status-warn"],
    }
    assert stateless["text"] != unavailable["text"]

    assert unrecognised == {
        "text": "Persistence: Storage status unknown",
        "rawStatus": "FUTURE_STATUS",
        "classes": ["status-badge", "status-unknown"],
    }
    assert missing == {
        "text": "Persistence: Storage status unknown",
        "rawStatus": "UNKNOWN",
        "classes": ["status-badge", "status-unknown"],
    }
    for unknown in (unrecognised, missing):
        text = str(unknown["text"]).lower()
        assert "retained" not in text
        assert "history" not in text
