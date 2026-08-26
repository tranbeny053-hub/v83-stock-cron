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


def _rendered_permissions() -> list[str]:
    source = (ROOT / "frontend" / "app.js").read_text(encoding="utf-8")
    helper = _extract_function(source, "permissionNo")
    script = (
        f"{helper}\n"
        "const cases = [false, true, undefined];\n"
        "console.log(JSON.stringify(cases.map(permissionNo)));"
    )
    completed = subprocess.run(
        ["node", "-e", script],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)


def test_permissions_render_authoritative_backend_values() -> None:
    assert _rendered_permissions() == [
        "No",
        "Unavailable",
        "Unavailable",
    ]
