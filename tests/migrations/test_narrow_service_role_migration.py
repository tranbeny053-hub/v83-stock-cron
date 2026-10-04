"""Migration 0018 (Phase 3, the privilege design's step D6; owner ruling: timing B, frozen scope).

Read from the file itself:
- it is authored for its own one-shot route, refuses a second application before any change, and
  needs 0016 and 0017 applied first;
- it takes from service_role every write privilege on the six core evidence tables and EXECUTE on
  the two bundle functions, keeps SELECT, and changes nothing else;
- its rollback gives back exactly what it takes, and the release registry records it as NOT
  additive, rollback-safe only to releases that write through the least-privilege pair.
Its behaviour behind a real PostgREST is proven by P3-PRIV-R's D1-D4
(.github/workflows/privilege-rehearsal.yml), and the one-shot apply by the 0018 rehearsal.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MIGRATION = (ROOT / "migrations/0018_narrow_service_role.sql").read_text(encoding="utf-8")
ROLLBACK = (ROOT / "scripts/privilege_rehearsal/rollback_0018.sql").read_text(encoding="utf-8")
# The migration without its comments; the DO blocks' bodies are kept.
CODE = re.sub(r"--[^\n]*", "", MIGRATION)
CORE = (
    "analysis_runs",
    "analysis_run_details",
    "predictions",
    "prediction_feature_snapshots",
    "prediction_derivatives_snapshots",
    "prediction_outcomes",
)
WA = "a2de125ffa449cd6f5ec452e4a7a3335286eb413"


def _statements(sql: str) -> list[str]:
    """The top-level statements, each dollar-quoted body collapsed and whitespace normalized."""

    body = re.sub(r"\$(\w*)\$.*?\$\1\$", "$$ $$", re.sub(r"--[^\n]*", "", sql), flags=re.S)
    return [" ".join(part.split()) for part in re.split(r";\s*(?=\n|$)", body) if part.strip()]


def test_it_is_authored_for_its_one_shot_route_under_the_owner_s_ruling() -> None:
    assert MIGRATION.lstrip().startswith("-- Phase 3")
    assert "AUTHORED, NOT APPLIED" in MIGRATION
    assert "scripts/apply_migration_0018.py" in MIGRATION
    assert "keep SELECT and revoke write/EXECUTE" in MIGRATION
    assert "run 37149774863" in MIGRATION, "frozen only after the clean production inventory"
    assert CODE.lstrip().startswith("DO $$"), "the one-shot refusal runs before any change"
    head = CODE.split("REVOKE", 1)[0]
    assert head.count("USING ERRCODE = 'UP018'") == 2
    assert "ucpe_bundle_owner" in head and "save_forecast_bundle" in head, "0016 and 0017 first"
    assert "has_table_privilege('service_role', 'public.predictions', 'INSERT')" in head


def test_it_revokes_the_frozen_scope_in_order_and_nothing_else() -> None:
    every = _statements(MIGRATION)
    kinds = [" ".join(statement.split(" ", 2)[:2]) for statement in every]
    assert kinds == [
        "DO $$",
        "REVOKE INSERT,",
        "DO $$",
        "GRANT ucpe_bundle_owner",
        "REVOKE EXECUTE",
        "REVOKE EXECUTE",
        "REVOKE ucpe_bundle_owner",
        "NOTIFY pgrst,",
    ]
    tables = re.findall(r"public\.(\w+)", every[1])
    assert sorted(tables) == sorted(CORE) and every[1].endswith("FROM service_role")
    assert "SELECT" not in every[1]
    maintain = re.search(r"\$\$(.*?)\$\$", CODE.split("REVOKE INSERT", 1)[1], re.S).group(1)
    assert ">= 170000" in maintain and "REVOKE MAINTAIN ON TABLE" in maintain
    assert sorted(re.findall(r"public\.(\w+)", maintain)) == sorted(CORE)
    for statement in every:
        assert not statement.startswith(
            ("CREATE", "ALTER", "DROP", "INSERT", "UPDATE", "DELETE", "TRUNCATE")
        ), statement
        if statement.startswith("REVOKE") and " ON " in statement:
            assert statement.endswith("FROM service_role"), statement


def test_its_rollback_gives_back_exactly_what_it_takes() -> None:
    every = _statements(ROLLBACK)
    restored: dict[str, set[str]] = {}
    for statement in every:
        match = re.fullmatch(r"GRANT ([A-Z, ]+) ON TABLE (.+) TO service_role", statement)
        if match:
            for table in re.findall(r"public\.(\w+)", match.group(2)):
                restored.setdefault(table, set()).update(
                    p.strip() for p in match.group(1).split(",")
                )
    full = {"INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER"}
    assert restored == {
        "analysis_runs": full,
        "predictions": full,
        "prediction_feature_snapshots": full,
        "prediction_outcomes": full,
        "analysis_run_details": {"INSERT", "UPDATE"},
        "prediction_derivatives_snapshots": {"INSERT"},
    }
    functions = re.findall(r"^GRANT EXECUTE ON FUNCTION public\.(\w+)\(", ROLLBACK, re.M)
    assert sorted(functions) == ["save_forecast_bundle", "save_prediction_bundle"]
    assert "migrations/0018_narrow_service_role.sql" in ROLLBACK


def test_the_registry_records_it_not_additive_applied_once_and_rollback_safe_from_wa() -> None:
    registry = json.loads((ROOT / "ops/release/releases.json").read_text(encoding="utf-8"))
    ids = [m["id"] for m in registry["migrations_applied"]]
    assert ids.index("0018") == ids.index("0017") + 1
    entry = next(m for m in registry["migrations_applied"] if m["id"] == "0018")
    assert entry["additive"] is False
    # Applied once by the owner's T4, run 37172530166 (main 82ed9c48), after the refused, unapplied
    # attempt 37170407623; never rerun.
    assert entry["applied_run"] == 37172530166
    assert entry["rollback_safe_from"] == WA
    wa = next(r for r in registry["releases"] if r["commit"] == WA)
    assert wa["release_id"] == "UCPE-PROD-WA-20261003-A" and wa["h2_hold"] is True
    assert "not additive" in entry["note"] and "least-privilege pair" in entry["note"]
