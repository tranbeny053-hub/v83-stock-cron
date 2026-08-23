from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SENTINEL = "SENTINEL-SECRET-CODE"


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


def _messages(cases: list[dict[str, object]]) -> list[str]:
    source = (ROOT / "frontend" / "app.js").read_text(encoding="utf-8")
    helper = _extract_function(source, "loginFailureMessage")
    encoded_cases = json.dumps(cases)
    script = (
        f"{helper}\n"
        f"const cases = {encoded_cases};\n"
        "console.log(JSON.stringify(cases.map((item) => "
        "loginFailureMessage(item.status, item.payload))));"
    )
    completed = subprocess.run(
        ["node", "-e", script],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)


def test_login_failure_messages_are_safe_and_actionable() -> None:
    cases: list[dict[str, object]] = [
        {
            "status": 401,
            "payload": {
                "detail": {
                    "error": {"message": "Invalid access code."},
                    "submitted": SENTINEL,
                }
            },
        },
        {
            "status": 429,
            "payload": {
                "detail": {
                    "error": {
                        "message": "Too many attempts.",
                        "retry_after_seconds": 60,
                    },
                    "submitted": SENTINEL,
                }
            },
        },
        {
            "status": 429,
            "payload": {
                "detail": {
                    "error": {"message": "Too many attempts."},
                    "submitted": SENTINEL,
                }
            },
        },
        {
            "status": 422,
            "payload": {
                "detail": [
                    {
                        "type": "string_too_long",
                        "input": SENTINEL,
                    }
                ]
            },
        },
        {"status": 500, "payload": None},
        {"status": None, "payload": None},
    ]

    messages = _messages(cases)

    assert messages == [
        "Invalid access code.",
        "Too many attempts. Try again in 60 seconds.",
        "Too many attempts. Wait a moment, then try again.",
        "The access code was not accepted. Check the entry and try again.",
        "Login is temporarily unavailable. Try again shortly.",
        "Unable to reach the service. Check your connection and try again.",
    ]
    for message in messages:
        assert SENTINEL not in message
        assert str(len(SENTINEL)) not in message
