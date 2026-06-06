"""Check that no full article body fixtures/exports are present."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCAN_DIRS = ("src", "tests", "schemas", "frontend")
BODY_PATTERN = re.compile(
    r"(?i)(article_body|full_article_body|full_text|raw_article|article_content)\s*[:=]\s*[\"'](.{500,})"
)


def main() -> int:
    findings: list[str] = []
    for dirname in SCAN_DIRS:
        path = ROOT / dirname
        if not path.exists():
            continue
        for item in path.rglob("*"):
            if not item.is_file():
                continue
            text = item.read_text(encoding="utf-8", errors="ignore")
            if BODY_PATTERN.search(text):
                findings.append(str(item.relative_to(ROOT)))
    if findings:
        print("\n".join(findings))
        return 1
    print("PASS: no full article body patterns found.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

