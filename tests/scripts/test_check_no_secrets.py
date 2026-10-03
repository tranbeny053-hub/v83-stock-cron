"""The heuristic secret scan (scripts/check_no_secrets.py): one of the three mandatory scanners.

It may only ever widen. E4 adds the least-privilege writer's two secrets to the names it watches.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
_SPEC = importlib.util.spec_from_file_location(
    "check_no_secrets", ROOT / "scripts/check_no_secrets.py"
)
scanner = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(scanner)


@pytest.mark.parametrize(
    "name",
    [
        "SUPABASE_DB_URL",
        "SUPABASE_URL",
        "SUPABASE_SERVICE_ROLE_KEY",
        "SUPABASE_PUBLISHABLE_KEY",
        "SUPABASE_WRITER_JWT",
        "FRED_API_KEY",
        "NEWSAPI_KEY",
        "PASSWORD",
        "PRIVATE_KEY",
    ],
)
def test_every_watched_name_with_a_literal_value_is_found(name: str) -> None:
    match = scanner.SECRET_ASSIGNMENT.search(f"{name}=a-literal-value")
    assert match is not None and match.group(1) == name


@pytest.mark.parametrize(
    "line",
    [
        'SUPABASE_WRITER_JWT = os.environ.get("SUPABASE_WRITER_JWT")',
        "SUPABASE_PUBLISHABLE_KEY=<the owner's value>",
        "SUPABASE_WRITER_JWT=set (****)",
    ],
)
def test_reading_or_redacting_a_secret_is_not_a_finding(line: str) -> None:
    match = scanner.SECRET_ASSIGNMENT.search(line)
    assert match is not None
    value = match.group(2).strip().strip("\"'")
    assert value in scanner.ALLOWED_VALUES or value.startswith(scanner.ALLOWED_VALUE_PREFIXES)
