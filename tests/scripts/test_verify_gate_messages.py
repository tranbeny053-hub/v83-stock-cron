"""Keep verify.sh's concise ruff failure detail and mandatory safety scanners."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_ruff_failure_detail_matches_concise_format() -> None:
    verify = (ROOT / "verify.sh").read_text(encoding="utf-8")
    ruff_lines = [line for line in verify.splitlines() if '"$RUFF" check' in line]

    assert len(ruff_lines) == 1
    line = ruff_lines[0]
    assert "check --output-format=concise ." in line

    match = re.search(r"grep -m1 -E '([^']+)'", line)
    assert match is not None
    detail_regex = re.compile(match.group(1))
    concise_sample = "src/x.py:3:1: I001 [*] Import block is un-sorted or un-formatted"
    full_location = " --> src/x.py:3:1"
    assert detail_regex.search(concise_sample)
    assert not detail_regex.search(full_location)


def test_verify_still_runs_all_three_safety_scanners() -> None:
    verify = (ROOT / "verify.sh").read_text(encoding="utf-8")

    assert verify.count('"$RUFF" check') == 1
    for scanner in (
        "check_no_forbidden_scope",
        "check_no_secrets",
        "check_no_full_article_body",
    ):
        assert scanner in verify
