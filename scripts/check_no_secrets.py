"""Heuristic secret scan for committed files."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {".git", ".venv", "__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache"}
SECRET_ASSIGNMENT = re.compile(
    r"(?i)\b(API_KEY|SECRET|PASSWORD|PASS_PHRASE|PRIVATE_KEY|SUPABASE_DB_URL|SUPABASE_URL|SUPABASE_SERVICE_ROLE_KEY)\s*=\s*([^\s#]+)"
)
ALLOWED_VALUES = {"set", "set (****)", "****", "<redacted>", "TBD", "None", "null"}
ALLOWED_VALUE_PREFIXES = ("<", "os.environ.get(")


def iter_files() -> list[Path]:
    files: list[Path] = []
    for path in ROOT.rglob("*"):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.is_file():
            files.append(path)
    return files


def main() -> int:
    findings: list[str] = []
    for path in iter_files():
        text = path.read_text(encoding="utf-8", errors="ignore")
        for match in SECRET_ASSIGNMENT.finditer(text):
            value = match.group(2).strip().strip("\"'")
            if value not in ALLOWED_VALUES and not value.startswith(ALLOWED_VALUE_PREFIXES):
                findings.append(f"{path.relative_to(ROOT)}: {match.group(1)} assignment")
    if findings:
        print("\n".join(findings))
        return 1
    print("PASS: no real secret-looking assignments found.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
