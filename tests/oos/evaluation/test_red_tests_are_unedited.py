"""The task-806 red tests are the repair contract and must not be edited to go green."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PIN = json.loads((ROOT / "ops/section_5a_red_tests_pin.json").read_text(encoding="utf-8"))


def test_red_tests_match_the_hash_pinned_before_any_repair() -> None:
    body = (ROOT / PIN["file"]).read_bytes()
    assert hashlib.sha256(body).hexdigest() == PIN["sha256"], (
        "the task-806 red tests changed after they were pinned; a repair must make them "
        "pass as written, never by editing them"
    )
