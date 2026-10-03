"""Migration 0017 (Phase 3, plan §8.1's wider bundle W-A; owner ruling WB1 = YES, after 0016).

Read from the file itself:
- it is authored for its own one-shot route, refuses a second application before any change, and
  needs 0016 applied first;
- it adds one function and its narrow owner's insert-and-read grants with their policies, and
  nothing else: no table changes, no older role gains a table right, nothing existing is revoked.
The function's behaviour behind a real PostgREST is proven by P3-PRIV-R's W1-W9
(.github/workflows/privilege-rehearsal.yml), and the one-shot apply by the 0017 rehearsal.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MIGRATION = (ROOT / "migrations/0017_forecast_bundle_rpc.sql").read_text(encoding="utf-8")
# The migration without its comments; its bodies (the DO block's, the function's) are kept.
CODE = re.sub(r"--[^\n]*", "", MIGRATION)
WIDE = "public.save_forecast_bundle(jsonb, jsonb, jsonb, jsonb, jsonb)"


def _statements() -> list[str]:
    """The top-level statements, each dollar-quoted body collapsed and whitespace normalized."""

    body = re.sub(r"\$(\w*)\$.*?\$\1\$", "$$ $$", CODE, flags=re.S)
    return [" ".join(part.split()) for part in re.split(r";\s*(?=\n|$)", body) if part.strip()]


def test_it_is_authored_for_its_one_shot_route_under_the_owner_s_ruling() -> None:
    assert "AUTHORED, NOT APPLIED" in MIGRATION
    assert "scripts/apply_migration_0017.py" in MIGRATION
    assert "WB1 = YES, after 0016" in MIGRATION and "option W-A" in MIGRATION
    assert MIGRATION.lstrip().startswith("-- Phase 3")
    assert CODE.lstrip().startswith("DO $$"), "the one-shot refusal runs before any change"
    head = CODE.split("CREATE FUNCTION", 1)[0]
    assert head.count("USING ERRCODE = 'UP017'") == 2
    assert "AND p.prosecdef AND o.rolname = 'ucpe_bundle_owner'" in head, "0016 comes first"


def test_it_adds_one_function_and_its_owner_s_insert_and_read_only() -> None:
    every = _statements()
    kinds = [statement.split(" ", 2)[0] + " " + statement.split(" ", 2)[1] for statement in every]
    assert kinds == [
        "DO $$",
        "CREATE FUNCTION",
        "REVOKE ALL",
        "GRANT EXECUTE",
        "GRANT SELECT,",
        "CREATE POLICY",
        "CREATE POLICY",
        "CREATE POLICY",
        "CREATE POLICY",
        "GRANT ucpe_bundle_owner",
        "GRANT CREATE",
        "ALTER FUNCTION",
        "REVOKE CREATE",
        "REVOKE ucpe_bundle_owner",
        "NOTIFY pgrst,",
    ]
    assert (
        "GRANT SELECT, INSERT ON TABLE public.analysis_runs, public.analysis_run_details "
        "TO ucpe_bundle_owner"
    ) in every
    assert f"GRANT EXECUTE ON FUNCTION {WIDE} TO ucpe_api_writer, service_role" in every
    for forbidden in ("CREATE TABLE", "ALTER TABLE", "DROP ", "UPDATE ", "DELETE ", "TRUNCATE"):
        assert forbidden not in CODE, forbidden


def test_no_older_role_gains_a_table_right_and_nothing_existing_is_revoked() -> None:
    every = _statements()
    for statement in every:
        if statement.startswith("GRANT") and " ON TABLE " in statement:
            assert statement.endswith("TO ucpe_bundle_owner"), statement
    revokes = [s for s in every if s.startswith("REVOKE")]
    assert revokes == [
        f"REVOKE ALL ON FUNCTION {WIDE} FROM PUBLIC, anon, authenticated",
        "REVOKE CREATE ON SCHEMA public FROM ucpe_bundle_owner",
        "REVOKE ucpe_bundle_owner FROM CURRENT_USER",
    ], "only the new function's defaults and the owner change's temporary powers are revoked"


def test_the_registry_vouches_it_additive_and_awaiting_its_apply_after_0016() -> None:
    registry = json.loads((ROOT / "ops/release/releases.json").read_text(encoding="utf-8"))
    ids = [m["id"] for m in registry["migrations_applied"]]
    assert ids.index("0017") == ids.index("0016") + 1
    entry = next(m for m in registry["migrations_applied"] if m["id"] == "0017")
    assert entry["additive"] is True and entry["applied_run"] is None
    assert "nothing revoked" in entry["note"] and "older code never calls it" in entry["note"]
