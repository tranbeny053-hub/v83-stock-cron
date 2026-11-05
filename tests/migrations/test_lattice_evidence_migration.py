"""Static contract checks of migrations/authored/0019_lattice_evidence.sql (NG4 Route S).

Offline: no database. The behaviour is proven on a scratch cluster by
scripts/migration_0019_rehearsal (R-0..R-15); these tests pin the text that the rehearsal
exercises, so an edit that drops a guard fails here first.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / "migrations/authored/0019_lattice_evidence.sql"
SQL = PATH.read_text(encoding="utf-8")
CODE = "\n".join(line for line in SQL.splitlines() if not line.lstrip().startswith("--"))
TABLES = ("lattice_rows", "lattice_commit_receipts", "lattice_missed_instants", "lattice_capacity")
WRITER_FUNCTIONS = ("record_lattice_row", "record_missed_instant", "capture_commit_receipts")


def _function_body(name: str) -> str:
    start = CODE.index(f"CREATE FUNCTION ucpe_lattice.{name}(")
    first = CODE.index("$$", start)
    return CODE[first + 2 : CODE.index("$$", first + 2)]


def test_header_says_authored_not_applied_and_names_the_holds() -> None:
    head = SQL.split("DO $$", 1)[0]
    assert "AUTHORED, NOT APPLIED. No apply route exists." in head
    assert "scripts/apply_migrations.py refuses it by name" in head
    assert "HOLD-1" in head and "track_commit_timestamp = on" in head
    assert "TRUSTED ADMINS" in head and "ROLLBACK. A separate T4, never automatic" in head


def test_no_transaction_control_inside_the_file() -> None:
    assert not re.search(r"^\s*(BEGIN|COMMIT|ROLLBACK)\s*;", CODE, re.MULTILINE | re.IGNORECASE)


def test_first_apply_checks_refuse_with_up019() -> None:
    checks = CODE.split("CREATE ROLE", 1)[0]
    for needle in (
        "server_version_num')::int < 160000",
        "nspname = 'ucpe_lattice'",
        "rolname IN ('ucpe_lattice_owner', 'ucpe_lattice_writer')",
        "(rolcreaterole OR rolsuper)",
        "r.rolbypassrls AND NOT r.rolsuper",
        "'pg_read_all_data', 'MEMBER'",
        "'pg_write_all_data', 'MEMBER'",
        "pg_publication WHERE puballtables",
    ):
        assert needle in checks
    assert checks.count("ERRCODE = 'UP019'") == 6


def test_roles_are_created_at_line_start_without_power() -> None:
    attrs = "NOLOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;"
    for role in ("ucpe_lattice_owner", "ucpe_lattice_writer"):
        assert re.search(rf"^CREATE ROLE {role} {attrs}$", CODE, re.MULTILINE)


def test_every_object_is_created_as_the_owner_in_its_own_schema() -> None:
    set_role = CODE.index("SET ROLE ucpe_lattice_owner;")
    reset = CODE.index("RESET ROLE;")
    assert CODE.index("CREATE SCHEMA ucpe_lattice AUTHORIZATION ucpe_lattice_owner;") < set_role
    for match in re.finditer(r"^CREATE (TABLE|FUNCTION) (\S+)", CODE, re.MULTILINE):
        assert set_role < match.start() < reset
        assert match.group(2).startswith("ucpe_lattice.")
    assert "public." not in CODE
    assert CODE.index("REVOKE ucpe_lattice_owner FROM CURRENT_USER;") > reset


def test_rows_admit_only_test_only_e1_reference_rows() -> None:
    table = CODE.split("CREATE TABLE ucpe_lattice.lattice_rows (", 1)[1].split(");", 1)[0]
    for check in (
        "CHECK (protocol_version = 'E3_LATTICE_V1')",
        "CHECK (evaluation_population = 'E1_OPERATIONAL')",
        "CHECK (timing_class = 'NOT_APPLICABLE')",
        "CHECK (evidence_use = 'TEST_ONLY')",
        "CHECK (arm = 'REF')",
        "CHECK (artifact_id IS NULL)",
        "CHECK (target_version = 'tc-v1')",
        "CHECK (is_live_data)",
        "CHECK (timeframe IN ('15m', '1H', '4H', '1D'))",
        "CHECK (predicted_at_utc >= lattice_instant_utc)",
        "CHECK (abs(p_up_frac + p_down_frac + p_timeout_frac - 1) <= 1e-9)",
        "'^e3l-[0-9a-f]{32}:(15m|1H|4H|1D):REF$'",
    ):
        assert check in table
    assert "prediction_origin" not in CODE and "USER_REQUESTED" not in CODE


def test_all_four_tables_are_append_only_with_forced_rls_and_owner_only_policies() -> None:
    loop = CODE.split("FOREACH t IN ARRAY ARRAY[", 1)[1].split("END LOOP;", 1)[0]
    assert all(f"'{t}'" in loop for t in TABLES)
    for needle in (
        "BEFORE UPDATE OR DELETE ON ucpe_lattice.%I FOR EACH ROW",
        "BEFORE TRUNCATE ON ucpe_lattice.%I FOR EACH STATEMENT",
        "ENABLE ROW LEVEL SECURITY",
        "FORCE ROW LEVEL SECURITY",
        "FOR SELECT TO ucpe_lattice_owner USING (true)",
        "FOR INSERT TO ucpe_lattice_owner WITH CHECK (true)",
    ):
        assert needle in loop
    assert len(re.findall(r"CREATE POLICY", CODE)) == 2
    assert not re.search(r"CREATE POLICY \w+ ON [^']+ FOR (ALL|UPDATE|DELETE)", CODE)


def test_functions_are_security_definer_with_an_empty_search_path() -> None:
    headers = re.findall(r"CREATE FUNCTION ucpe_lattice\.(\w+)\(.*?\nAS \$\$", CODE, re.DOTALL)
    assert sorted(headers) == sorted(
        [
            "capacity_status",
            "capture_commit_receipts",
            "record_lattice_row",
            "record_missed_instant",
            "reject_mutation",
        ]
    )
    for block in re.findall(r"CREATE FUNCTION ucpe_lattice\.\w+\(.*?\nAS \$\$", CODE, re.DOTALL):
        assert "SET search_path = ''" in block
        if "reject_mutation" not in block:
            assert "SECURITY DEFINER" in block


def test_only_the_writer_is_granted_and_only_usage_and_execute() -> None:
    grants = re.findall(r"^GRANT .*?;", CODE, re.MULTILINE | re.DOTALL)
    assert grants[0] == "GRANT ucpe_lattice_owner TO CURRENT_USER WITH INHERIT FALSE, SET TRUE;"
    assert grants[1] == "GRANT USAGE ON SCHEMA ucpe_lattice TO ucpe_lattice_writer;"
    assert grants[2].startswith("GRANT EXECUTE ON FUNCTION") and grants[2].endswith(
        "TO ucpe_lattice_writer;"
    )
    assert all(f"ucpe_lattice.{fn}(" in grants[2] for fn in WRITER_FUNCTIONS)
    assert "capacity_status" not in grants[2] and len(grants) == 3
    for revoke in (
        "REVOKE ALL ON SCHEMA ucpe_lattice FROM PUBLIC;",
        "REVOKE ALL ON ALL TABLES IN SCHEMA ucpe_lattice FROM PUBLIC;",
        "REVOKE ALL ON ALL FUNCTIONS IN SCHEMA ucpe_lattice FROM PUBLIC;",
        "IN SCHEMA ucpe_lattice REVOKE ALL ON FUNCTIONS FROM PUBLIC;",
    ):
        assert revoke in CODE


def test_capture_records_only_postgresqls_commit_timestamp() -> None:
    body = _function_body("capture_commit_receipts")
    assert "pg_catalog.pg_current_xact_id_if_assigned() IS NOT NULL" in body
    assert body.index("current_setting('track_commit_timestamp') = 'on'") < body.index(
        "pg_xact_commit_timestamp(v_row.row_xmin)"
    )
    # The commit time is only ever PostgreSQL's commit timestamp, or NULL; clocks only bound it.
    assignments = re.findall(r"v_ts := ([^;]+);", body)
    assert sorted(set(assignments)) == [
        "NULL",
        "pg_catalog.pg_xact_commit_timestamp(v_row.row_xmin)",
    ]
    for clock in ("now()", "transaction_timestamp", "statement_timestamp", "CURRENT_TIMESTAMP"):
        assert clock not in body
    for bound in (
        "v_ts >= v_row.inserted",
        "v_ts <= pg_catalog.clock_timestamp()",
        "pg_catalog.clock_timestamp() - v_row.inserted <= interval '7 days'",
    ):
        assert bound in body
    assert "ON CONFLICT (lattice_row_id) DO NOTHING" in body
    assert "pg_advisory_xact_lock(190019, 2)" in body


def test_writes_take_exact_key_sets_capacity_and_never_overwrite() -> None:
    for name in ("record_lattice_row", "record_missed_instant"):
        body = _function_body(name)
        assert "IS DISTINCT FROM" in body and "jsonb_object_keys" in body
        assert "pg_advisory_xact_lock(190019, 1)" in body and "capacity_status()" in body
        assert "DO NOTHING" in body and "DO UPDATE" not in body
        assert "db_insert_clock_utc" not in body and "logged_at_db_clock" not in body
    status = _function_body("capacity_status")
    assert (
        "lattice_rows" in status
        and "lattice_missed_instants" in status
        and "CAPACITY_UNSET" in status
    )


def test_self_check_covers_schema_table_and_function_acls_and_the_hand_off() -> None:
    check = CODE.rsplit("DO $$", 1)[1]
    for needle in (
        "nspacl",
        "relacl",
        "proacl",
        "aclexplode",
        "set_option",
        "has_table_privilege('ucpe_lattice_writer'",
    ):
        assert needle in check
