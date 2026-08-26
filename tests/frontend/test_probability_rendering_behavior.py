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


def _rendered_probabilities() -> list[str]:
    source = (ROOT / "frontend" / "app.js").read_text(encoding="utf-8")
    helpers = "\n".join(
        _extract_function(source, name)
        for name in ("formatNumber", "formatPct", "formatFractionPct")
    )
    script = (
        f"{helpers}\n"
        "const cases = [0.6, 0.3, 0.1, '0.6', Number.NaN];\n"
        "console.log(JSON.stringify(cases.map(formatFractionPct)));"
    )
    completed = subprocess.run(
        ["node", "-e", script],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)


def test_probability_fractions_render_as_percentages() -> None:
    assert _rendered_probabilities() == [
        "60.00%",
        "30.00%",
        "10.00%",
        "n/a",
        "n/a",
    ]
