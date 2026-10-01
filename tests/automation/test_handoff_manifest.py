"""docs/automation/UOR_HANDOFF.md: every listed digest is the digest of the file as committed."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "docs" / "automation" / "UOR_HANDOFF.md"
ROW = re.compile(r"^\| `(?P<path>[^`]+)` \| [^|]+ \| `(?P<sha>[0-9a-f]{64})` \|$")


def test_every_handoff_digest_matches_its_file() -> None:
    rows = [ROW.match(line) for line in MANIFEST.read_text(encoding="utf-8").splitlines()]
    listed = {match["path"]: match["sha"] for match in rows if match}
    assert {
        "schemas/radar_evidence.schema.json",
        "schemas/radar_evidence_error.schema.json",
        "docs/automation/RADAR_EVIDENCE_V1.md",
    } <= set(listed)
    for path, digest in listed.items():
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == digest, (
            f"{path} changed: regenerate UOR_HANDOFF.md"
        )
