"""The Codex red tests are the repair contract; they change only by recorded owner amendment."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PIN = json.loads((ROOT / "ops/section_5a_red_tests_pin.json").read_text(encoding="utf-8"))
CODEX_ORIGINAL = "efe36649582ecbfe3a9835d159bd3ea1bd54befe4a55269dd165084d265f07df"


def test_red_tests_match_their_pinned_hash() -> None:
    body = (ROOT / PIN["file"]).read_bytes()
    assert hashlib.sha256(body).hexdigest() == PIN["sha256"], (
        "the red tests changed without a recorded amendment; a repair must make them pass as "
        "written, never by editing them"
    )


def test_every_change_is_a_recorded_amendment_chained_from_the_codex_original() -> None:
    """Provenance cannot be silently rewritten: the chain must start at Codex's hash and end
    at the current one, with each step naming who authorized it."""

    assert PIN["original_sha256"] == CODEX_ORIGINAL
    chain = PIN.get("amendments", [])
    current = CODEX_ORIGINAL
    for amendment in chain:
        assert amendment["from_sha256"] == current
        assert amendment["authorized_by"].strip()
        current = amendment["to_sha256"]
    assert current == PIN["sha256"]
