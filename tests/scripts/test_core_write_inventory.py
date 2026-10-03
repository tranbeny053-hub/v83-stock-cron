"""D6: the core-evidence write inventory (scripts/core_write_inventory.py) and migration 0018.

The owner's ruling (2026-10-03): "scope=six core evidence tables + two bundle functions, keep SELECT
and revoke write/EXECUTE, with deterministic inventory proving no omitted core write surface before
freeze." Behind a real PostgreSQL, the privilege rehearsal's D1-D4 run the inventory and migration
0018 (frozen after the clean production inventory); these tests pin what can be pinned without a
database: the scope, the verdicts, the read-only queries, and 0018's and its rollback's statements.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from scripts import core_write_inventory as inventory

ROOT = Path(__file__).resolve().parents[2]
DRAFT = (ROOT / "migrations/0018_narrow_service_role.sql").read_text()
ROLLBACK = (ROOT / "scripts/privilege_rehearsal/rollback_0018.sql").read_text()
_MUTATING = re.compile(
    r"\b(INSERT\s+INTO|UPDATE\s+\w+\s+SET|DELETE\s+FROM|CREATE|ALTER|DROP|GRANT|REVOKE|TRUNCATE\s+"
    r"TABLE|COPY|SET\s+ROLE)\b",
    re.I,
)


def test_the_scope_is_the_owner_s_six_tables_and_two_functions() -> None:
    assert inventory.CORE_TABLES == (
        "analysis_run_details", "analysis_runs", "prediction_derivatives_snapshots",
        "prediction_feature_snapshots", "prediction_outcomes", "predictions",
    )
    assert inventory.BUNDLE_FUNCTIONS == (
        "save_forecast_bundle(jsonb,jsonb,jsonb,jsonb,jsonb)",
        "save_prediction_bundle(jsonb,jsonb,jsonb)",
    )
    for path, function in (("migrations/0015_prediction_bundle_rpc.sql", "save_prediction_bundle"),
                           ("migrations/0017_forecast_bundle_rpc.sql", "save_forecast_bundle")):
        assert f"public.{function}(" in (ROOT / path).read_text()


def test_maintain_is_inventoried_from_postgresql_17_only() -> None:
    assert "MAINTAIN" not in inventory.parameters("service_role", 160004, ())["privileges"]
    assert "MAINTAIN" in inventory.parameters("service_role", 170006, ())["privileges"]


@pytest.mark.parametrize("kind", sorted(inventory.QUERIES))
def test_every_query_reads_catalogs_only(kind: str) -> None:
    query = inventory.QUERIES[kind]
    assert query.startswith("SELECT ") and not _MUTATING.search(query), kind
    assert "%(role)s" in query or kind == "T" and "%(role)s" in query


def test_the_inventory_runs_read_only_and_never_prints_the_url() -> None:
    source = (ROOT / "scripts/core_write_inventory.py").read_text()
    read = source.split("def read_inventory(", 1)[1].split("\ndef ", 1)[0]
    assert read.index("for statement in GUARD_STATEMENTS") < read.index("collect(")
    assert "finally:\n            connection.rollback()" in read
    assert inventory.GUARD_STATEMENTS[0] == (
        "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"
    )
    for leak in ("print(url", "{url", "print(database_url", "{database_url"):
        assert leak not in source, leak
    assert inventory.READ_ONLY_SQL == "SET TRANSACTION READ ONLY"  # the privilege rehearsal's D1-D4


def _report(**surfaces: list[list[str]]) -> dict:
    return {"surfaces": {kind: surfaces.get(kind, []) for kind in inventory.SURFACE_KINDS}}


def test_the_revoke_set_covers_core_table_and_column_privileges_and_the_two_functions() -> None:
    report = _report(
        T=[["predictions", "INSERT"], ["analysis_run_details", "UPDATE"]],
        C=[["analysis_run_details", "REFERENCES"]],
        F=[["public.save_forecast_bundle(jsonb, jsonb, jsonb, jsonb, jsonb)", "ucpe_bundle_owner"],
           ["public.save_prediction_bundle(jsonb, jsonb, jsonb)", "ucpe_bundle_owner"]],
    )
    assert inventory.omitted(report) == []
    assert inventory.verdict(report, "before") == []
    assert len(inventory.verdict(report, "after")) == 5


@pytest.mark.parametrize(
    ("kind", "row"),
    [
        ("F", ["public.another_definer()", "postgres"]),
        ("F", ["graphql_public.save_prediction_bundle(jsonb, jsonb, jsonb)", "postgres"]),
        ("V", ["public.a_view", "predictions"]),
        ("R", ["public.watchlist.a_rule", "prediction_outcomes"]),
        ("G", ["public.watchlist.a_trigger", "postgres"]),
        ("K", ["a_fkey", "predictions -> public.watchlist"]),
        ("O", ["predictions", "postgres"]),
    ],
    ids=["another-definer", "same-name-other-schema", "view", "rule", "trigger", "cascade",
         "ownership"],
)
def test_anything_else_is_an_omitted_surface(kind: str, row: list[str]) -> None:
    report = _report(**{kind: [row]})
    assert inventory.omitted(report) == [[kind, *row]]
    assert inventory.verdict(report, "before") == [" ".join([kind, *row])]


def test_collect_sorts_every_kind_and_keeps_the_information() -> None:
    def execute(sql: str, values: dict) -> list[tuple]:
        assert values["role"] == "service_role" and values["core"] == list(inventory.CORE_TABLES)
        if sql == inventory.QUERIES["T"]:
            return [("predictions", "UPDATE"), ("predictions", "INSERT")]
        if sql == inventory.INFORMATION["bypassrls"]:
            return [(True,)]
        return []

    report = inventory.collect(execute, role="service_role", server_version_num=160004)
    assert report["surfaces"]["T"] == [["predictions", "INSERT"], ["predictions", "UPDATE"]]
    assert report["information"]["bypassrls"] == [["True"]]
    assert set(report["surfaces"]) == set(inventory.SURFACE_KINDS)


def test_an_unknown_expectation_is_refused() -> None:
    with pytest.raises(ValueError):
        inventory.verdict(_report(), "sometimes")


def test_the_inventory_refuses_without_its_token_and_its_attested_runtime(capsys) -> None:
    """The route's details are in test_core_write_inventory_route.py."""

    assert inventory.main(["--mode=inventory", "--expect=before"], environ={}) == 2
    assert "--confirm must be exactly" in capsys.readouterr().err
    confirmed = ["--mode=inventory", "--expect=before", f"--confirm={inventory.CONFIRMATION}"]
    assert inventory.main(confirmed, environ={}) == 2
    assert "--wheelhouse is required" in capsys.readouterr().err


def _tables(sql: str) -> list[str]:
    return re.findall(r"public\.(\w+)", sql)


def test_migration_0018_revokes_exactly_the_ruled_scope_and_never_select() -> None:
    # Top-level statements start a line; the MAINTAIN statement is a string inside a DO block.
    revoke = re.search(r"^REVOKE ([A-Z, ]+) ON TABLE(.+?)FROM service_role;", DRAFT, re.S | re.M)
    assert revoke.group(1) == "INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER"
    assert sorted(_tables(revoke.group(2))) == sorted(inventory.CORE_TABLES)
    assert "SELECT" not in revoke.group(1) and "REVOKE SELECT" not in DRAFT
    assert "REVOKE MAINTAIN ON TABLE" in DRAFT and ">= 170000" in DRAFT
    functions = re.findall(r"REVOKE EXECUTE ON FUNCTION public\.(\w+)\(", DRAFT)
    assert sorted(functions) == ["save_forecast_bundle", "save_prediction_bundle"]
    assert "ERRCODE = 'UP018'" in DRAFT
    assert DRAFT.index("GRANT ucpe_bundle_owner TO CURRENT_USER") < DRAFT.index(
        "REVOKE EXECUTE") < DRAFT.index("REVOKE ucpe_bundle_owner FROM CURRENT_USER")


def test_the_rollback_restores_each_table_as_the_migrations_left_it() -> None:
    grants = re.findall(r"^GRANT ([A-Z, ]+) ON TABLE(.+?)TO service_role;", ROLLBACK, re.S | re.M)
    restored = {table: privileges for privileges, tables in grants for table in _tables(tables)}
    full = "INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER"
    assert restored == {
        "analysis_runs": full, "predictions": full, "prediction_feature_snapshots": full,
        "prediction_outcomes": full, "analysis_run_details": "INSERT, UPDATE",
        "prediction_derivatives_snapshots": "INSERT",
    }
    assert sorted(re.findall(r"GRANT EXECUTE ON FUNCTION public\.(\w+)\(", ROLLBACK)) == [
        "save_forecast_bundle", "save_prediction_bundle"]
    assert "GRANT MAINTAIN ON TABLE" in ROLLBACK and "GRANT SELECT" not in ROLLBACK
