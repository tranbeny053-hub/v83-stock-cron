from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SENTINEL = "SENTINEL-RAW-PAYLOAD"


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


def _messages(cases: list[object]) -> list[str]:
    source = (ROOT / "frontend" / "app.js").read_text(encoding="utf-8")
    helper = _extract_function(source, "batchErrorMessage")
    script = (
        f"{helper}\n"
        f"const cases = {json.dumps(cases)};\n"
        "console.log(JSON.stringify(cases.map(batchErrorMessage)));"
    )
    completed = subprocess.run(
        ["node", "-e", script],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)


def test_batch_error_messages_are_safe_and_actionable() -> None:
    cases: list[object] = [
        {
            "index": 0,
            "detail": {
                "error": {
                    "code": "INVALID_SYMBOL",
                    "message": "Invalid or unsupported symbol.",
                }
            },
        },
        {
            "index": 1,
            "symbol": "$NOPE",
            "detail": {
                "error": {
                    "code": "INVALID_SYMBOL",
                    "message": "Invalid or unsupported symbol.",
                }
            },
        },
        {
            "index": 2,
            "detail": {"error": {"code": "PROVIDER_DEGRADED"}},
        },
        {"index": 3},
        {
            "index": 4,
            "detail": [{"type": "string_too_long", "input": SENTINEL}],
        },
        None,
    ]

    messages = _messages(cases)

    assert messages == [
        "Item 1: Invalid or unsupported symbol. (Code: INVALID_SYMBOL)",
        "Item 2 ($NOPE): Invalid or unsupported symbol. (Code: INVALID_SYMBOL)",
        "Item 3: Batch item could not be analyzed. (Code: PROVIDER_DEGRADED)",
        "Item 4: Batch item could not be analyzed.",
        "Item 5: Batch item could not be analyzed.",
        "Batch item: Batch item could not be analyzed.",
    ]
    for message in messages:
        assert SENTINEL not in message
