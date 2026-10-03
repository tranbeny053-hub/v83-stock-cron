"""Migration 0016 (Phase 3, plan §8.2; owner ruling E1 = YES, W2): the least-privilege roles.

Read from the file itself and held to the code each role serves:
- the writer gets exactly what the REST runtime requests, and no direct write to core evidence;
- the resolver gets what its due scans, outcome insert and status upsert touch;
- the Space role gets calibration's read and the live F1/UOR registry and ledger (Correction 01).
The roles' behaviour on a real PostgreSQL, through production's own code behind a real PostgREST, is
proven by P3-PRIV-R (.github/workflows/privilege-rehearsal.yml). The one-shot apply is proven by
the 0016 rehearsal.
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

from scripts import apply_migration_0016 as route

ROOT = Path(__file__).resolve().parents[2]
MIGRATION = (ROOT / "migrations/0016_least_privilege_roles.sql").read_text(encoding="utf-8")
REPOSITORY = ROOT / "src/crypto_probability_engine/persistence/repository.py"
# The REST runtime's own methods (the live Space). The resolver's and the OOS evaluator's REST
# methods never run there: those jobs reach the database directly, as their own roles.
RUNTIME_METHODS = (
    "save_run",
    "save_run_detail",
    "save_timeframe_result",
    "save_provider_observation",
    "save_news_item",
    "save_news_cluster",
    "save_news_evidence_link",
    "save_prediction_bundle",
    "list_watchlist",
    "add_watchlist",
    "remove_watchlist",
    "recent_runs",
    "recent_runs_for_origin",
    "get_run",
    "get_run_detail",
    "run_ids_with_detail",
)
VERB_PRIVILEGES = {"GET": {"SELECT"}, "POST": {"INSERT"}, "DELETE": {"DELETE", "SELECT"}}


def _rest_requests() -> dict[str, set[tuple[str, str, bool]]]:
    """method -> {(verb, target, upsert)} of SupabaseRestRepository's _request calls."""

    tree = ast.parse(REPOSITORY.read_text(encoding="utf-8"))
    rest = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "SupabaseRestRepository"
    )
    found: dict[str, set[tuple[str, str, bool]]] = {}
    for method in rest.body:
        if not isinstance(method, ast.FunctionDef):
            continue
        for node in ast.walk(method):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "_request"
                and len(node.args) >= 2
                and all(isinstance(a, ast.Constant) for a in node.args[:2])
            ):
                prefer = next(
                    (
                        k.value.value
                        for k in node.keywords
                        if k.arg == "prefer" and isinstance(k.value, ast.Constant)
                    ),
                    "",
                )
                found.setdefault(method.name, set()).add(
                    (node.args[0].value, node.args[1].value, "merge-duplicates" in prefer)
                )
    return found


def test_it_is_authored_for_its_one_shot_route_under_the_owner_s_ruling() -> None:
    assert "AUTHORED, NOT APPLIED" in MIGRATION
    assert "scripts/apply_migration_0016.py" in MIGRATION
    assert "E1 = YES, option W2" in MIGRATION and "Correction 01" in MIGRATION
    assert MIGRATION.lstrip().startswith("-- Phase 3")
    code = re.sub(r"--[^\n]*", "", MIGRATION)
    assert code.lstrip().startswith("DO $$"), "the one-shot refusal runs before any change"
    assert "USING ERRCODE = 'UP016'" in code


def test_the_writer_holds_exactly_what_the_rest_runtime_requests() -> None:
    requests = _rest_requests()
    writer = route.EXPECTED_GRANTS["ucpe_api_writer"]
    needed: dict[str, set[str]] = {}
    for method in RUNTIME_METHODS:
        for verb, target, upsert in requests[method]:
            if target.startswith("rpc/"):
                continue
            privileges = set(VERB_PRIVILEGES[verb]) | ({"UPDATE", "SELECT"} if upsert else set())
            needed.setdefault(target, set()).update(privileges)
    assert {table: set(privileges) for table, privileges in writer.items()} == needed
    # The bundle is the writer's only way into core evidence: one RPC, never the tables.
    assert ("POST", "rpc/save_prediction_bundle", False) in requests["save_prediction_bundle"]
    for core in (
        "predictions",
        "prediction_feature_snapshots",
        "prediction_derivatives_snapshots",
        "prediction_outcomes",
    ):
        assert set(writer.get(core, ())) <= {"SELECT"}, core


def test_the_resolver_and_the_space_role_hold_what_their_code_touches() -> None:
    status_store = (ROOT / "src/crypto_probability_engine/resolution/status_store.py").read_text()
    resolver = route.EXPECTED_GRANTS["ucpe_resolver"]
    assert "INSERT INTO public.prediction_resolution_status" in status_store
    assert "ON CONFLICT (prediction_id) DO UPDATE" in status_store
    assert resolver["prediction_resolution_status"] == ("INSERT", "SELECT", "UPDATE")
    assert resolver["prediction_outcomes"] == ("INSERT", "SELECT")
    assert resolver["predictions"] == ("SELECT",)
    ledger = (ROOT / "src/crypto_probability_engine/automation/ledger.py").read_text()
    registry = (ROOT / "src/crypto_probability_engine/automation/credentials.py").read_text()
    space = route.EXPECTED_GRANTS["ucpe_space_db"]
    assert "FOR UPDATE" in ledger and "UPDATE public.automation_radar_ledger" in ledger
    assert "INSERT INTO public.automation_radar_ledger" in ledger
    assert space["automation_radar_ledger"] == ("INSERT", "SELECT", "UPDATE")
    assert "FROM public.automation_credential" in registry
    assert space["automation_credential"] == ("SELECT",)
    assert space["predictions"] == space["prediction_outcomes"] == ("SELECT",)


def test_no_older_role_gains_anything_and_nothing_existing_is_revoked() -> None:
    code = re.sub(r"--[^\n]*", "", MIGRATION)
    for match in re.finditer(r"\bGRANT\b[^;]*;", code):
        assert not re.search(r"\bTO (PUBLIC|anon|authenticated|service_role)\b", match.group(0))
    revokes = [" ".join(s.split()) for s in re.findall(r"\bREVOKE\b[^;]*", code)]
    assert revokes == [
        "REVOKE CREATE ON SCHEMA public FROM ucpe_bundle_owner",
        "REVOKE ucpe_bundle_owner FROM CURRENT_USER",
    ]


def test_the_registry_vouches_it_additive_and_records_its_one_apply() -> None:
    registry = json.loads((ROOT / "ops/release/releases.json").read_text(encoding="utf-8"))
    entry = next(m for m in registry["migrations_applied"] if m["id"] == "0016")
    # Applied once by the owner-authorized dispatch, run 37110330500 (2026-10-03, adjudicated).
    assert entry["additive"] is True and entry["applied_run"] == 37110330500
    assert "nothing revoked" in entry["note"]
