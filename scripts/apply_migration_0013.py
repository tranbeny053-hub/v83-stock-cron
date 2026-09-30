#!/usr/bin/env python
"""Apply migration 0013, the machine route's credential registry and automation ledger, ONCE.

    --mode attest     verify isolation, dispatch and runtime; touches no database
    --mode rehearse   the whole apply against a scratch local PostgreSQL: apply once, then prove
                      that a second apply refuses; never where the production secret is present,
                      never over the network
    --mode apply      THE ONE-SHOT APPLY; requires the confirmation token

Run only by ``.github/workflows/apply-migration-0013.yml``, as ``python -I -S -B``, inside the
closed trust boundary of the other database routes: exact CPython 3.13.14, CPython's bundled pip
and lock-authenticated wheels, with the dispatch verified HERE against THIS workflow in the owner
repository. The bulk scripts/apply_migrations.py applies every migration and is never used for it.

WHAT IT CHANGES, AND WHAT IT PROVES DOES NOT CHANGE. Migration 0013 creates the two tables of the
governed machine route POST /v1/automation/radar-evidence (F1):
- ``public.automation_credential``, the machine-credential registry: a SHA-256 digest per
  credential, never a value, with its primary key, a unique digest and five CHECK constraints;
- ``public.automation_radar_ledger``, the isolated idempotency and audit ledger of AUTOMATED_RADAR
  calls, with its primary key, nine CHECK constraints and one index.
It turns each table's row-level security on and revokes every privilege of PUBLIC and the three API
roles, which Supabase's default privileges grant to every new table. Neither table has a foreign
key, so the apply takes no lock on any existing table. This route refuses unless production is
ready for exactly that:
- no relation of any kind named after either table or any of their four indexes exists in
  ``public`` yet (otherwise this is not a first apply, so a second dispatch refuses and the
  one-shot property is enforced by the database itself).

ONE TRANSACTION, FAIL CLOSED. Under bounded timeouts and an advisory lock:
  1. read-only PRE-CHECKS, as above. The security of every table of migrations 0001-0009 and 0012
     is recorded, not required. The server's version decides which table privileges are asked
     about, so no check is blind to one the server can grant;
  2. exactly the pinned bytes of migration 0013, with no parameters;
  3. read-only POST-CHECKS refuse unless, for each of the two tables:
     - the table and each of its indexes is the only relation of its name in ``public``;
     - the table is an ordinary table owned by the applying role, with row-level security on and
       not forced, no policy, and no privilege, on the table or a column, for PUBLIC, anon,
       authenticated or service_role;
     - its columns are exactly the reviewed ones, in order, with their types, nullability and
       defaults, and no identity, generation or column grant;
     - its constraints are exactly the reviewed ones, validated, over exactly their columns, quoted
       literals and numbers, none a foreign key, and no constraint anywhere references it;
     - its indexes are exactly the reviewed ones, with their uniqueness and key column order, none
       partial; it has no trigger and holds no row;
     and every other table's security is exactly as it was.
Any refusal or error rolls the transaction back, so nothing is applied; only then is it committed.
If the connection fails while the COMMIT is in flight, the report says ``committed`` is UNKNOWN.
Had it committed, a second dispatch would refuse as not a first apply.
The only application data ever read is the row counts of the two tables this transaction has just
created.

Every query result is captured raw before it is judged, and written to ``--report`` on success
and on refusal alike. The database URL is never printed, logged or written. An unexpected failure
is reported by its type only, because driver messages can name the host.

THIS FILE IMPORTS ONLY THE STANDARD LIBRARY AT MODULE LEVEL, exactly like the other routes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from types import MappingProxyType
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src"
SCRIPT = "scripts/apply_migration_0013.py"
WORKFLOW = ".github/workflows/apply-migration-0013.yml"
MIGRATION = "migrations/0013_automation_radar_ledger.sql"
# The reviewed bytes. A different file on the dispatched commit refuses before any connection.
MIGRATION_SHA256 = "c1e7d7fd3aeb3328981d0fd2f3c0a94bc83cd6944d47637856d0b06c5f735c79"
CONFIRMATION = "APPLY-MIGRATION-0013-ONCE"
REPORT_SCHEMA = "migration-0013-apply-report.v1"
DISPATCH_SCHEMA = "migration-0013-dispatch.v1"
MODE_ATTEST = "attest"
MODE_REHEARSE = "rehearse"
MODE_APPLY = "apply"
REQUIRED_EVENT = "workflow_dispatch"
REQUIRED_REF = "refs/heads/main"
# The owner repository, pinned: a fork's run carries a self-consistent identity of its own.
EXPECTED_REPOSITORY = "tranbeny053-hub/v83-stock-cron"
PINNED_PYTHON = ("CPython", "3.13.14")

TIMEOUT_STATEMENTS = (
    "SET LOCAL lock_timeout = '10s'",
    "SET LOCAL statement_timeout = '120s'",
)
# A fixed key, distinct from 0008's to 0012's: two appliers of 0013 serialize.
ADVISORY_LOCK_SQL = "SELECT pg_advisory_xact_lock(5000013)"

API_ROLES = ("anon", "authenticated", "service_role")
REGISTRY = "automation_credential"
LEDGER = "automation_radar_ledger"
# The two tables 0013 creates, sorted as the checks return them.
TABLES = (REGISTRY, LEDGER)
# Every relation of ``public`` that 0013's statements name: the two tables and their four indexes
# (a primary key's or unique constraint's index carries the constraint's name). Sorted as the
# checks return them.
RELATION_NAMES = (
    "ac_secret_sha256_unique",
    "arl_credential_received",
    REGISTRY,
    "automation_credential_pkey",
    LEDGER,
    "automation_radar_ledger_pkey",
)
TIMESTAMPTZ = "timestamp with time zone"
# table -> its (name, pg_catalog.format_type, NOT NULL, the default as pg_get_expr deparses it or
# None), in the table's order. NOT NULL is judged from pg_attribute, never from pg_constraint.
EXPECTED_COLUMNS: Mapping[str, tuple[tuple[str, str, bool, str | None], ...]] = MappingProxyType(
    {
        REGISTRY: (
            ("credential_id", "text", True, None),
            ("secret_sha256", "text", True, None),
            ("status", "text", True, None),
            ("not_after_utc", TIMESTAMPTZ, False, None),
            ("created_at_utc", TIMESTAMPTZ, True, "now()"),
            ("revoked_at_utc", TIMESTAMPTZ, False, None),
        ),
        LEDGER: (
            ("credential_id", "text", True, None),
            ("client_request_id", "uuid", True, None),
            ("request_fingerprint", "text", True, None),
            ("evidence_origin", "text", True, "'AUTOMATED_RADAR'::text"),
            ("state", "text", True, None),
            ("outcome_code", "text", False, None),
            ("http_status", "integer", False, None),
            ("response_body", "jsonb", False, None),
            ("run_id", "text", False, None),
            ("analysis_hash", "text", False, None),
            ("evidence_hash", "text", False, None),
            ("release_id", "text", True, None),
            ("deadline_ms", "integer", True, None),
            ("received_at_utc", TIMESTAMPTZ, True, None),
            ("completed_at_utc", TIMESTAMPTZ, False, None),
        ),
    }
)
# Every column must have each of these off: no identity, generation or column grant.
COLUMN_FLAGS_OFF = ("identity", "generated", "column_acl")
_CREDENTIAL_ID_PATTERN = "^[a-z0-9][a-z0-9-]{2,31}$"
_PREFIXED_SHA256_PATTERN = "^sha256:[0-9a-f]{64}$"
_LEDGER_STATES = frozenset({"IN_PROGRESS", "COMPLETED"})
_REGISTRY_STATUSES = frozenset({"ACTIVE", "REVOKED"})
_OUTCOME_COLUMNS = ("analysis_hash", "evidence_hash", "http_status", "outcome_code", "run_id")
_NONE: frozenset[Any] = frozenset()
# table -> name -> (contype, the columns it references, sorted; the exact set of quoted literals in
# its definition; the exact set of unquoted integers in it). Literals and integers are compared as
# sets, never the deparsed text: its formatting is the server's. Every constraint read excludes
# contype 'n': PostgreSQL 18 records NOT NULL there, and nullability is judged from pg_attribute.
EXPECTED_CONSTRAINTS: Mapping[
    str, Mapping[str, tuple[str, tuple[str, ...], frozenset[str], frozenset[int]]]
] = MappingProxyType(
    {
        REGISTRY: MappingProxyType(
            {
                "ac_credential_id_format": (
                    "c",
                    ("credential_id",),
                    frozenset({_CREDENTIAL_ID_PATTERN}),
                    _NONE,
                ),
                "ac_expiry_after_creation": (
                    "c",
                    ("created_at_utc", "not_after_utc"),
                    _NONE,
                    _NONE,
                ),
                "ac_revocation_shape": (
                    "c",
                    ("created_at_utc", "revoked_at_utc", "status"),
                    _REGISTRY_STATUSES,
                    _NONE,
                ),
                "ac_secret_sha256_format": (
                    "c",
                    ("secret_sha256",),
                    frozenset({"^[0-9a-f]{64}$"}),
                    _NONE,
                ),
                "ac_secret_sha256_unique": ("u", ("secret_sha256",), _NONE, _NONE),
                "ac_status_valid": ("c", ("status",), _REGISTRY_STATUSES, _NONE),
                "automation_credential_pkey": ("p", ("credential_id",), _NONE, _NONE),
            }
        ),
        LEDGER: MappingProxyType(
            {
                "arl_credential_id_format": (
                    "c",
                    ("credential_id",),
                    frozenset({_CREDENTIAL_ID_PATTERN}),
                    _NONE,
                ),
                "arl_deadline_bounds": ("c", ("deadline_ms",), _NONE, frozenset({5000, 60000})),
                "arl_fingerprint_format": (
                    "c",
                    ("request_fingerprint",),
                    frozenset({_PREFIXED_SHA256_PATTERN}),
                    _NONE,
                ),
                "arl_origin_automated": (
                    "c",
                    ("evidence_origin",),
                    frozenset({"AUTOMATED_RADAR"}),
                    _NONE,
                ),
                "arl_refusal_shape": (
                    "c",
                    _OUTCOME_COLUMNS,
                    frozenset({"SUCCEEDED"}),
                    frozenset({400, 599}),
                ),
                "arl_release_id_format": (
                    "c",
                    ("release_id",),
                    frozenset({"^UCPE-[A-Z0-9-]{3,}$"}),
                    _NONE,
                ),
                "arl_state_shape": (
                    "c",
                    (
                        "completed_at_utc",
                        "http_status",
                        "outcome_code",
                        "received_at_utc",
                        "response_body",
                        "state",
                    ),
                    _LEDGER_STATES,
                    _NONE,
                ),
                "arl_state_valid": ("c", ("state",), _LEDGER_STATES, _NONE),
                "arl_success_shape": (
                    "c",
                    _OUTCOME_COLUMNS,
                    frozenset({"SUCCEEDED", "^run_[0-9a-f]{32}$", _PREFIXED_SHA256_PATTERN}),
                    frozenset({200}),
                ),
                "automation_radar_ledger_pkey": (
                    "p",
                    ("client_request_id", "credential_id"),
                    _NONE,
                    _NONE,
                ),
            }
        ),
    }
)
# table -> name -> (unique, the key columns in index order). No index of 0013 is partial.
EXPECTED_INDEXES: Mapping[str, Mapping[str, tuple[bool, tuple[str, ...]]]] = MappingProxyType(
    {
        REGISTRY: MappingProxyType(
            {
                "ac_secret_sha256_unique": (True, ("secret_sha256",)),
                "automation_credential_pkey": (True, ("credential_id",)),
            }
        ),
        LEDGER: MappingProxyType(
            {
                "arl_credential_received": (False, ("credential_id", "received_at_utc")),
                "automation_radar_ledger_pkey": (True, ("credential_id", "client_request_id")),
            }
        ),
    }
)
# Every table migrations 0001-0009 and 0012 create: the ten legacy tables and those of 0005, 0006,
# 0008, 0009 and 0012. 0013 never touches them, so their security must be exactly the same after
# the apply. A test re-derives this list from the migration files, so it cannot drift from them.
EXISTING_TABLES = (
    "analysis_run_details",
    "analysis_runs",
    "analysis_timeframe_results",
    "app_events",
    "news_clusters",
    "news_evidence_links",
    "news_items",
    "prediction_derivatives_snapshots",
    "prediction_feature_snapshots",
    "prediction_outcomes",
    "prediction_resolution_status",
    "predictions",
    "provider_observations",
    "section_5a_evaluation_seal",
    "watchlist",
)
# The table privileges of every supported server, sorted as the checks return them.
TABLE_PRIVILEGES = ("DELETE", "INSERT", "REFERENCES", "SELECT", "TRIGGER", "TRUNCATE", "UPDATE")
# PostgreSQL 17 added MAINTAIN, and production runs 17.6. On such a server every check also asks
# about MAINTAIN; on an older one, such as the CI rehearsal's 16, asking would fail.
MAINTAIN_SINCE_SERVER_VERSION = 170000
MINIMUM_SERVER_VERSION = 150000
TABLE_PRIVILEGES_WITH_MAINTAIN = tuple(sorted((*TABLE_PRIVILEGES, "MAINTAIN")))
SERVER_VERSION_SQL = "SELECT pg_catalog.current_setting('server_version_num')::integer"

_API_ROLES_SQL = ", ".join(f"'{role}'" for role in API_ROLES)


# table_privileges_for, _held and _security_sql are copied from scripts/apply_migration_0010.py,
# never imported: this route loads only the standard library, the evaluator pin and itself. A test
# requires both routes to produce the same SQL.
def table_privileges_for(server_version: int) -> tuple[str, ...]:
    """Every table privilege a server of ``server_version`` (server_version_num) can grant."""

    if server_version >= MAINTAIN_SINCE_SERVER_VERSION:
        return TABLE_PRIVILEGES_WITH_MAINTAIN
    return TABLE_PRIVILEGES


def _held(function: str, role: str, relation: str, values: str) -> str:
    """The privileges ``role`` holds on ``relation``, as a sorted text array."""

    return (
        f"ARRAY(SELECT v.privilege FROM (VALUES {values}) AS v(privilege)"
        f" WHERE pg_catalog.{function}('{role}', {relation}, v.privilege)"
        ' ORDER BY v.privilege COLLATE "C")'
    )


# The relation kinds of the audit's table facts (scripts/audit_table_privileges.py).
_TABLE_LIKE_RELKINDS_SQL = "ARRAY['r', 'p', 'v', 'm', 'f']::\"char\"[]"


def _security_sql(names: Sequence[str], privileges: Sequence[str]) -> str:
    listed = ", ".join(f"('{name}')" for name in names)
    asked = ", ".join(f"('{name}')" for name in privileges)
    return (
        "SELECT t.name,"
        # Relations of the kinds the audit measured, in any schema: a same-named index, sequence or
        # type is not a second table.
        " (SELECT count(*) FROM pg_catalog.pg_class AS k WHERE k.relname::text = t.name"
        f" AND k.relkind = ANY ({_TABLE_LIKE_RELKINDS_SQL})),"
        " c.relkind::text,"
        " pg_catalog.pg_get_userbyid(c.relowner) = current_user,"
        " c.relrowsecurity, c.relforcerowsecurity,"
        " (SELECT count(*) FROM pg_catalog.pg_policy AS p WHERE p.polrelid = c.oid),"
        " EXISTS (SELECT 1 FROM pg_catalog.aclexplode("
        "COALESCE(c.relacl, pg_catalog.acldefault('r', c.relowner))) AS a WHERE a.grantee = 0),"
        " EXISTS (SELECT 1 FROM pg_catalog.pg_attribute AS att"
        " CROSS JOIN LATERAL pg_catalog.aclexplode(att.attacl) AS a"
        " WHERE att.attrelid = c.oid AND att.attnum > 0 AND NOT att.attisdropped"
        " AND att.attacl IS NOT NULL AND (a.grantee = 0 OR a.grantee IN ("
        "SELECT r.oid FROM pg_catalog.pg_roles AS r"
        " WHERE r.rolname IN ('anon', 'authenticated')))),"
        f" {_held('has_table_privilege', 'anon', 'c.oid', asked)},"
        f" {_held('has_table_privilege', 'authenticated', 'c.oid', asked)},"
        f" {_held('has_table_privilege', 'service_role', 'c.oid', asked)}"
        f" FROM (VALUES {listed}) AS t(name)"
        " LEFT JOIN pg_catalog.pg_class AS c"
        " ON c.oid = pg_catalog.to_regclass('public.' || t.name)"
        ' ORDER BY t.name COLLATE "C"'
    )


ROLES_SQL = f"SELECT count(*) FROM pg_catalog.pg_roles WHERE rolname IN ({_API_ROLES_SQL})"


def tables_security_sql(server_version: int) -> str:
    return _security_sql(TABLES, table_privileges_for(server_version))


def existing_security_sql(server_version: int) -> str:
    return _security_sql(EXISTING_TABLES, table_privileges_for(server_version))


SECURITY_FIELDS = (
    "table",
    "relations_named_so",
    "relkind",
    "owned_by_applying_role",
    "row_level_security",
    "row_level_security_forced",
    "policies",
    "public_has_a_privilege",
    "column_grant_to_public_anon_or_authenticated",
    "anon",
    "authenticated",
    "service_role",
)
# Each new table's security row, field by field, as 0013 must leave it (the 0009 pattern): one
# ordinary table, owned by the applying role, row-level security on and not forced, no policy, and
# no privilege at all for PUBLIC or the three API roles, MAINTAIN included on a server that has it.
EXPECTED_SECURITY: Mapping[str, Any] = MappingProxyType(
    {
        "relations_named_so": 1,
        "relkind": "r",
        "owned_by_applying_role": True,
        "row_level_security": True,
        "row_level_security_forced": False,
        "policies": 0,
        "public_has_a_privilege": False,
        "column_grant_to_public_anon_or_authenticated": False,
        **dict.fromkeys(API_ROLES, ()),
    }
)
_RELATIONS_LISTED = ", ".join(f"('{name}')" for name in RELATION_NAMES)
# How many relations of ANY kind (table, index, sequence, view, composite type...) carry each name
# in ``public``. Any of them would turn the migration's IF NOT EXISTS into a silent no-op.
RELATIONS_SQL = (
    "SELECT t.name,"
    " (SELECT count(*) FROM pg_catalog.pg_class AS k WHERE k.relname::text = t.name"
    " AND k.relnamespace = pg_catalog.to_regnamespace('public'))"
    f" FROM (VALUES {_RELATIONS_LISTED}) AS t(name)"
    ' ORDER BY t.name COLLATE "C"'
)
RELATION_FIELDS = ("relation", "relations_in_public")


def _table_sql(table: str) -> str:
    """A new table's own relation, resolved in ``public`` exactly as the security check does."""

    return f"pg_catalog.to_regclass('public.{table}')"


def columns_sql(table: str) -> str:
    """Its live columns, in physical order, each with its default as the server deparses it."""

    return (
        "SELECT a.attname::text, pg_catalog.format_type(a.atttypid, a.atttypmod), a.attnotnull,"
        " pg_catalog.pg_get_expr(d.adbin, d.adrelid),"
        " a.attidentity <> '', a.attgenerated <> '', a.attacl IS NOT NULL"
        " FROM pg_catalog.pg_attribute AS a"
        " LEFT JOIN pg_catalog.pg_attrdef AS d ON d.adrelid = a.attrelid AND d.adnum = a.attnum"
        f" WHERE a.attrelid = {_table_sql(table)} AND a.attnum > 0 AND NOT a.attisdropped"
        " ORDER BY a.attnum"
    )


COLUMN_FIELDS = ("column", "type", "not_null", "default", "identity", "generated", "column_acl")


def constraints_sql(table: str) -> str:
    """Its constraints but NOT NULL, with the server's deparse and their columns, sorted."""

    return (
        "SELECT c.conname::text, c.contype::text, c.convalidated,"
        " pg_catalog.pg_get_constraintdef(c.oid),"
        " ARRAY(SELECT a.attname::text FROM pg_catalog.pg_attribute AS a"
        " WHERE a.attrelid = c.conrelid AND a.attnum = ANY (c.conkey)"
        ' ORDER BY a.attname::text COLLATE "C")'
        " FROM pg_catalog.pg_constraint AS c"
        f" WHERE c.conrelid = {_table_sql(table)} AND c.contype <> 'n'"
        ' ORDER BY c.conname::text COLLATE "C"'
    )


CONSTRAINT_FIELDS = ("constraint", "type", "validated", "definition", "columns")


def referencing_sql(table: str) -> str:
    """Constraints anywhere whose referenced table is this one: a foreign key into it."""

    return (
        "SELECT count(*) FROM pg_catalog.pg_constraint AS c"
        f" WHERE c.confrelid = {_table_sql(table)}"
    )


def indexes_sql(table: str) -> str:
    """Its indexes: uniqueness, key columns in index order, predicate and raw definition."""

    return (
        "SELECT i.relname::text, x.indisunique,"
        " ARRAY(SELECT a.attname::text"
        " FROM pg_catalog.unnest(x.indkey) WITH ORDINALITY AS k(attnum, n)"
        " LEFT JOIN pg_catalog.pg_attribute AS a"
        " ON a.attrelid = x.indrelid AND a.attnum = k.attnum"
        " WHERE k.n <= x.indnkeyatts ORDER BY k.n),"
        " pg_catalog.pg_get_expr(x.indpred, x.indrelid),"
        " pg_catalog.pg_get_indexdef(x.indexrelid)"
        " FROM pg_catalog.pg_index AS x"
        " JOIN pg_catalog.pg_class AS i ON i.oid = x.indexrelid"
        f" WHERE x.indrelid = {_table_sql(table)}"
        ' ORDER BY i.relname::text COLLATE "C"'
    )


INDEX_FIELDS = ("index", "unique", "columns", "predicate", "definition")


def triggers_sql(table: str) -> str:
    """Its triggers but the server's internal ones (the constraints check covers those)."""

    return (
        "SELECT t.tgname::text, t.tgenabled::text"
        " FROM pg_catalog.pg_trigger AS t"
        f" WHERE t.tgrelid = {_table_sql(table)} AND NOT t.tgisinternal"
        ' ORDER BY t.tgname::text COLLATE "C"'
    )


TRIGGER_FIELDS = ("trigger", "enabled")


# THE ONLY READS OF APPLICATION TABLES: the rows of each table this transaction has just created,
# which must be none. They run only after the migration, as the tables' owner, whom row-level
# security that is not forced does not restrict.
def row_count_sql(table: str) -> str:
    return f"SELECT count(*) FROM public.{table}"


NOT_A_FIRST_APPLY = "this is not a first apply"
COMMIT_UNKNOWN = "UNKNOWN"

# The rehearsal reaches only a local server through its unix socket: never a network host.
_LOCAL_SOCKET_URL = re.compile(r"postgresql:///[a-z_][a-z0-9_]*\?host=/var/run/postgresql")
REHEARSAL_URL_VARIABLE = "MIGRATION_0013_REHEARSAL_URL"
_COMMIT_SHA = re.compile(r"[0-9a-f]{40}")
_SHA256 = re.compile(r"[0-9a-f]{64}")
_DIGITS = re.compile(r"[0-9]+")
# A quoted SQL literal, as the server deparses one ('ACTIVE'::text); a doubled quote stays in.
_QUOTED_LITERAL = re.compile(r"'((?:[^']|'')*)'")
# An unquoted integer of a deparsed definition, e.g. the 5000 of (deadline_ms >= 5000).
_INTEGER = re.compile(r"\b[0-9]+\b")
PER_TABLE_CHECKS = (
    "columns",
    "constraints",
    "referencing_constraints",
    "indexes",
    "triggers",
    "row_count",
)


def pre_checks(server_version: int) -> tuple[tuple[str, str, tuple[str, ...] | None], ...]:
    """(name, query, fields) of every read before the migration, in this order.

    ``fields`` None marks a read of exactly one value rather than of rows.
    """

    return (
        ("relations", RELATIONS_SQL, RELATION_FIELDS),
        ("existing", existing_security_sql(server_version), SECURITY_FIELDS),
    )


def post_checks(server_version: int) -> tuple[tuple[str, str, tuple[str, ...] | None], ...]:
    """(name, query, fields) of every read after the migration, in this order.

    A per-table read is named ``<check>:<table>``.
    """

    per_table: list[tuple[str, str, tuple[str, ...] | None]] = []
    for table in TABLES:
        per_table += [
            (f"columns:{table}", columns_sql(table), COLUMN_FIELDS),
            (f"constraints:{table}", constraints_sql(table), CONSTRAINT_FIELDS),
            (f"referencing_constraints:{table}", referencing_sql(table), None),
            (f"indexes:{table}", indexes_sql(table), INDEX_FIELDS),
            (f"triggers:{table}", triggers_sql(table), TRIGGER_FIELDS),
            (f"row_count:{table}", row_count_sql(table), None),
        ]
    return (
        ("relations", RELATIONS_SQL, RELATION_FIELDS),
        ("tables", tables_security_sql(server_version), SECURITY_FIELDS),
        *per_table,
        ("existing", existing_security_sql(server_version), SECURITY_FIELDS),
    )


def constraint_literals(definition: str) -> frozenset[str]:
    """Pure: the quoted literals of a deparsed constraint or predicate, e.g. ``'x'::text`` -> x."""

    return frozenset(value.replace("''", "'") for value in _QUOTED_LITERAL.findall(definition))


def constraint_integers(definition: str) -> frozenset[int]:
    """Pure: the unquoted integers of a deparsed constraint, e.g. ``(x >= 5000)`` -> 5000.

    Quoted literals are removed first, so a pattern's ``{2,31}`` is never read as a number, and an
    identifier such as ``secret_sha256`` holds no word boundary before its digits.
    """

    unquoted = _QUOTED_LITERAL.sub("''", definition)
    return frozenset(int(value) for value in _INTEGER.findall(unquoted))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode", choices=[MODE_ATTEST, MODE_REHEARSE, MODE_APPLY], default=MODE_ATTEST
    )
    parser.add_argument(
        "--confirm", default="", help="required for --mode apply: the exact confirmation token"
    )
    parser.add_argument(
        "--expected-sha",
        default="",
        help="required: the full commit SHA on main that the owner reviewed and dispatched",
    )
    parser.add_argument(
        "--wheelhouse",
        default="",
        help="required: the directory of lock-authenticated wheels that were installed",
    )
    parser.add_argument(
        "--report", default=None, help="write this run's outcome, success or refusal, as JSON"
    )
    return parser


def ensure_source_path() -> None:
    """Make the first-party source importable, AFTER the interpreter's own library."""

    if str(SOURCE) not in sys.path:
        sys.path.append(str(SOURCE))


def enter_isolated_runtime(wheelhouse: str):
    """The isolated process and its authenticated import surface, verified first (J1=B)."""

    ensure_source_path()
    from crypto_probability_engine import runtime_isolation

    if not wheelhouse:
        raise _refusal("--wheelhouse is required; installed code is authenticated against it")
    return runtime_isolation.enter(ROOT, wheelhouse=Path(wheelhouse))


def observe(environ: Mapping[str, str], isolation) -> tuple[dict[str, str], dict[str, Any]]:
    """The dispatch facts GitHub sets, and this process's and checkout's. Nothing is judged."""

    from crypto_probability_engine import runtime_isolation

    dispatch = {
        field: str(environ.get(variable, ""))
        for field, variable in (
            ("github_actions", "GITHUB_ACTIONS"),
            ("event_name", "GITHUB_EVENT_NAME"),
            ("repository", "GITHUB_REPOSITORY"),
            ("workflow_ref", "GITHUB_WORKFLOW_REF"),
            ("ref", "GITHUB_REF"),
            ("sha", "GITHUB_SHA"),
            ("run_id", "GITHUB_RUN_ID"),
            ("run_attempt", "GITHUB_RUN_ATTEMPT"),
        )
    }
    status = _git("status", "--porcelain=v1", "--untracked-files=no")
    runtime = {
        "git_head": _git("rev-parse", "HEAD") or "",
        "tracked_tree_clean": status == "" if status is not None else None,
        "python_implementation": platform.python_implementation(),
        "python_version": platform.python_version(),
        "interpreter_flags": runtime_isolation.interpreter_flags(),
        "installed_files_sha256": getattr(isolation, "installed_files_sha256", ""),
    }
    return dispatch, runtime


def verify_dispatch(
    dispatch: Mapping[str, str], runtime: Mapping[str, Any], *, expected_sha: str
) -> dict[str, Any]:
    """Pure: a manual dispatch of THIS workflow, in the owner repository, on main, at the SHA."""

    from crypto_probability_engine.runtime_isolation import REQUIRED_FLAGS_TEXT

    failures: list[str] = []

    def need(condition: bool, message: str) -> None:
        if not condition:
            failures.append(message)

    repository = str(dispatch.get("repository", ""))
    need(dispatch.get("github_actions") == "true", "not running inside GitHub Actions")
    need(
        repository == EXPECTED_REPOSITORY,
        f"repository is {repository!r}, not the owner repository {EXPECTED_REPOSITORY}",
    )
    need(
        dispatch.get("event_name") == REQUIRED_EVENT,
        f"event is {dispatch.get('event_name')!r}, not a manual {REQUIRED_EVENT}",
    )
    need(dispatch.get("ref") == REQUIRED_REF, f"ref is {dispatch.get('ref')!r}, not {REQUIRED_REF}")
    need(
        dispatch.get("workflow_ref") == f"{EXPECTED_REPOSITORY}/{WORKFLOW}@{REQUIRED_REF}",
        f"workflow is {dispatch.get('workflow_ref')!r}, not {WORKFLOW} on {REQUIRED_REF}",
    )
    sha_is_canonical = isinstance(expected_sha, str) and bool(_COMMIT_SHA.fullmatch(expected_sha))
    need(
        sha_is_canonical,
        "expected_sha must be the full 40-character lowercase commit SHA of the reviewed commit",
    )
    need(
        sha_is_canonical and dispatch.get("sha") == expected_sha,
        f"the dispatched commit {dispatch.get('sha')!r} is not expected_sha",
    )
    need(
        sha_is_canonical and runtime.get("git_head") == expected_sha,
        f"the checked-out commit {runtime.get('git_head')!r} is not expected_sha",
    )
    need(
        runtime.get("tracked_tree_clean") is True,
        "tracked files differ from the checked-out commit",
    )
    interpreter = (runtime.get("python_implementation"), runtime.get("python_version"))
    need(
        interpreter == PINNED_PYTHON,
        f"interpreter is {runtime.get('python_implementation')} {runtime.get('python_version')}, "
        f"not {PINNED_PYTHON[0]} {PINNED_PYTHON[1]}",
    )
    need(
        runtime.get("interpreter_flags") == REQUIRED_FLAGS_TEXT,
        f"the process did not start isolated (flags [{runtime.get('interpreter_flags')}])",
    )
    need(
        bool(_SHA256.fullmatch(str(runtime.get("installed_files_sha256", "")))),
        "the installed files were not verified against their records",
    )
    need(
        bool(_DIGITS.fullmatch(str(dispatch.get("run_id", "")))),
        "run_id is not a GitHub run id",
    )
    need(
        bool(_DIGITS.fullmatch(str(dispatch.get("run_attempt", "")))),
        "run_attempt is not a number",
    )
    if failures:
        raise _refusal("the dispatch does not verify: " + "; ".join(failures))
    return {
        "schema_version": DISPATCH_SCHEMA,
        "dispatch_verified": True,
        "workflow": WORKFLOW,
        "event_name": str(dispatch["event_name"]),
        "repository": repository,
        "workflow_ref": str(dispatch["workflow_ref"]),
        "ref": str(dispatch["ref"]),
        "sha": str(dispatch["sha"]),
        "expected_sha": expected_sha,
        "git_head": str(runtime["git_head"]),
        "run_id": str(dispatch["run_id"]),
        "run_attempt": str(dispatch["run_attempt"]),
        "python_version": str(runtime["python_version"]),
        "interpreter_flags": str(runtime["interpreter_flags"]),
        "installed_files_sha256": str(runtime["installed_files_sha256"]),
    }


def attest_dispatch(expected_sha: str, environ: Mapping[str, str], isolation) -> dict[str, Any]:
    dispatch, runtime = observe(environ, isolation)
    return verify_dispatch(dispatch, runtime, expected_sha=expected_sha)


def attest_loaded_modules(isolation) -> int:
    """Every loaded module came from the stdlib, a locked file, the evaluator pin or this script."""

    from crypto_probability_engine import runtime_isolation
    from crypto_probability_engine.oos.evaluation.evaluator_pin import pinned_files

    return runtime_isolation.attest_loaded_modules(
        isolation, pinned=(*pinned_files(ROOT), SCRIPT), root=ROOT
    )


def load_driver():
    """The locked driver, imported WITHOUT connecting. enter() authenticated its files first."""

    import psycopg

    return psycopg


def migration_bytes() -> bytes:
    """The file on this commit, refused unless it is exactly the reviewed bytes."""

    data = (ROOT / MIGRATION).read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if digest != MIGRATION_SHA256:
        raise _refusal(f"{MIGRATION} is sha256 {digest}, not the reviewed {MIGRATION_SHA256}")
    return data


def main(argv: list[str] | None = None, *, environ: Mapping[str, str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    captured: dict[str, Any] = {}
    try:
        outcome = _run(args, os.environ if environ is None else environ, captured)
    except Exception as exc:  # noqa: BLE001 - every failure is reported, then fails the step
        record = _refusal_record(args.mode, exc, captured)
        if args.report:
            _write_report(Path(args.report), record)
        print(f"{record['outcome']}: {record['error_type']}: {record['detail']}", file=sys.stderr)
        return 2 if record["outcome"] == "REFUSED" else 1
    print(json.dumps(outcome, indent=2, sort_keys=True))
    if args.report:
        _write_report(Path(args.report), outcome)
    return 0


def _run(
    args: argparse.Namespace, environ: Mapping[str, str], captured: dict[str, Any]
) -> dict[str, Any]:
    if args.mode == MODE_APPLY and args.confirm != CONFIRMATION:
        raise _refusal(f"--confirm must be exactly {CONFIRMATION}")
    if args.mode == MODE_REHEARSE:
        return rehearse(args, environ, captured)

    isolation = enter_isolated_runtime(args.wheelhouse)
    record = attest_dispatch(args.expected_sha, environ, isolation)
    attest_loaded_modules(isolation)
    data = migration_bytes()
    base = {
        "schema_version": REPORT_SCHEMA,
        "migration": MIGRATION,
        "migration_sha256": hashlib.sha256(data).hexdigest(),
        "run_provenance": record,
    }
    if args.mode == MODE_ATTEST:
        # Load the driver WITHOUT connecting, and attest again, before any step holds the secret.
        load_driver()
        attest_loaded_modules(isolation)
        from crypto_probability_engine import runtime_isolation

        return {
            **base,
            "mode": MODE_ATTEST,
            "touches_database": False,
            "driver_helpers": runtime_isolation.loaded_dynamic_helpers(),
        }

    database_url = environ.get("SUPABASE_DB_URL", "")
    if not database_url:
        raise _refusal("SUPABASE_DB_URL is not set")
    driver = load_driver()
    attest_loaded_modules(isolation)  # the driver's origin, verified before it reaches the network
    applied = apply_in_one_transaction(
        lambda: driver.connect(database_url, connect_timeout=8), data.decode("utf-8"), captured
    )
    return {**base, "mode": MODE_APPLY, **applied}


def rehearse(
    args: argparse.Namespace, environ: Mapping[str, str], captured: dict[str, Any]
) -> dict[str, Any]:
    """The apply, end to end, on the scratch database the rehearsal built: once, then refused.

    The scratch database is built from migrations 0001-0012, production's expected state, as the
    role this process connects as, so that role owns the new tables exactly as production's
    applying role will. Supabase's default privileges there grant every new table to the API
    roles, so the post-checks prove the migration's revocations.
    """

    url = environ.get(REHEARSAL_URL_VARIABLE, "")
    if not _LOCAL_SOCKET_URL.fullmatch(url):
        raise _refusal(
            f"{REHEARSAL_URL_VARIABLE} must be a local unix-socket URL, e.g. "
            "postgresql:///migration_0013_rehearsal?host=/var/run/postgresql"
        )
    if environ.get("SUPABASE_DB_URL"):
        raise _refusal("the rehearsal never runs where the production database secret is present")
    isolation = enter_isolated_runtime(args.wheelhouse) if args.wheelhouse else None
    data = migration_bytes()
    driver = load_driver()
    if isolation is not None:
        attest_loaded_modules(isolation)

    def open_connection():
        return driver.connect(url, connect_timeout=8)

    first_captured: dict[str, Any] = {}
    captured["first_apply"] = first_captured
    first = apply_in_one_transaction(open_connection, data.decode("utf-8"), first_captured)
    second_captured: dict[str, Any] = {}
    captured["second_apply"] = second_captured
    try:
        apply_in_one_transaction(open_connection, data.decode("utf-8"), second_captured)
    except Exception as exc:  # noqa: BLE001 - only the one-shot refusal is the expected outcome
        if not (_is_refusal(exc) and NOT_A_FIRST_APPLY in str(exc)):
            raise
        second_refusal = str(exc)
    else:
        raise _refusal("a second apply was not refused, so the one-shot property does not hold")
    return {
        "schema_version": REPORT_SCHEMA,
        "mode": MODE_REHEARSE,
        "outcome": "REHEARSED",
        "migration": MIGRATION,
        "migration_sha256": hashlib.sha256(data).hexdigest(),
        "first_apply": first,
        "second_apply_refusal": second_refusal,
        "second_apply_captured": second_captured,
    }


def apply_in_one_transaction(
    open_connection: Callable[[], Any],
    migration_sql: str,
    captured: dict[str, Any],
) -> dict[str, Any]:
    """Pre-checks, the migration and post-checks in ONE transaction, committed only if all pass.

    ``captured`` receives every raw result as it arrives, so a refusal still reports what was seen.
    """

    with open_connection() as connection:
        with connection.cursor() as cursor:
            for statement in TIMEOUT_STATEMENTS:
                cursor.execute(statement)
            cursor.execute(ADVISORY_LOCK_SQL)

            cursor.execute(ROLES_SQL)
            roles = _row(cursor.fetchone(), 1, "roles")[0]
            captured["api_roles_present"] = roles
            if roles != len(API_ROLES):
                raise _refusal(f"{roles!r} of the {len(API_ROLES)} Supabase API roles exist")

            cursor.execute(SERVER_VERSION_SQL)
            server_version = _row(cursor.fetchone(), 1, "server version")[0]
            captured["server_version_num"] = server_version
            if (
                not isinstance(server_version, int)
                or isinstance(server_version, bool)
                or server_version < MINIMUM_SERVER_VERSION
            ):
                raise _refusal(
                    f"the server version {server_version!r} is not PostgreSQL 15 or later"
                )
            privileges = table_privileges_for(server_version)
            captured["table_privileges_asked"] = list(privileges)

            # Every pre-read first, each captured as it arrives; then one verdict naming them all.
            pre = _read_checks(cursor, pre_checks(server_version), captured, "pre")
            failures = pre_check_failures(pre)
            if failures:
                raise _refusal(
                    "the database is not in the state a first apply of 0013 requires: "
                    + "; ".join(failures)
                )

            cursor.execute(migration_sql)
            captured["executed_migration_sha256"] = hashlib.sha256(
                migration_sql.encode("utf-8")
            ).hexdigest()

            post = _read_checks(cursor, post_checks(server_version), captured, "post")
            failures = post_check_failures(pre, post)
            if failures:
                raise _refusal(
                    "the applied result is not the reviewed one, so the transaction is rolled "
                    "back: " + "; ".join(failures)
                )
        captured["commit_attempted"] = True
        connection.commit()
        captured["committed"] = True
    return {
        "outcome": "APPLIED",
        "api_roles_present": captured["api_roles_present"],
        "server_version_num": server_version,
        "table_privileges_asked": list(privileges),
        **{f"pre_{name}": value for name, value in pre.items()},
        "executed_migration_sha256": captured["executed_migration_sha256"],
        **{f"post_{name}": value for name, value in post.items()},
        "committed": True,
    }


def pre_check_failures(pre: Mapping[str, Any]) -> list[str]:
    """Pure: every way the database differs from the state a first apply of 0013 requires.

    Only the relations are required. The existing tables' security is recorded: the post-checks
    require it unchanged, whatever it is.
    """

    return relation_pre_check_failures(pre["relations"]) + existing_pre_check_failures(
        pre["existing"]
    )


def relation_pre_check_failures(rows: Sequence[Mapping[str, Any]]) -> list[str]:
    """No relation of any kind carries a table's or an index's name in ``public`` yet."""

    names = [row.get("relation") for row in rows]
    if names != list(RELATION_NAMES):
        return [f"the relations read were {names}"]
    failures: list[str] = []
    for row in rows:
        count = row.get("relations_in_public")
        if not isinstance(count, int) or isinstance(count, bool) or count < 0:
            failures.append(f"{row['relation']}: its count {count!r} is unreadable")
        elif count != 0:
            failures.append(
                f"{NOT_A_FIRST_APPLY}: {count} relations named {row['relation']} already exist "
                "in public"
            )
    return failures


def existing_pre_check_failures(rows: Sequence[Mapping[str, Any]]) -> list[str]:
    """The existing tables are recorded, not required.

    0013 never touches them, and the post-check requires their security to be identical after the
    apply, whatever it is. Only a malformed read refuses.
    """

    if [row.get("table") for row in rows] != list(EXISTING_TABLES):
        return [f"the existing tables read were {[row.get('table') for row in rows]}"]
    return []


def post_check_failures(pre: Mapping[str, Any], post: Mapping[str, Any]) -> list[str]:
    """Pure: every way the applied database differs from the reviewed result."""

    failures = relation_post_check_failures(post["relations"]) + table_post_check_failures(
        post["tables"]
    )
    for table in TABLES:
        failures += (
            column_post_check_failures(table, post[f"columns:{table}"])
            + constraint_post_check_failures(table, post[f"constraints:{table}"])
            + _none_failures(
                post[f"referencing_constraints:{table}"], f"constraints reference {table}"
            )
            + index_post_check_failures(table, post[f"indexes:{table}"])
            + trigger_post_check_failures(table, post[f"triggers:{table}"])
            + _none_failures(post[f"row_count:{table}"], f"rows are in {table}")
        )
    return failures + _unchanged_failures(
        "security of table", "table", pre["existing"], post["existing"]
    )


def relation_post_check_failures(rows: Sequence[Mapping[str, Any]]) -> list[str]:
    """Each table and each of its indexes is the one relation of its name in ``public``."""

    names = [row.get("relation") for row in rows]
    if names != list(RELATION_NAMES):
        return [f"the relations read after were {names}"]
    return [
        f"{row['relation']}: {row.get('relations_in_public')!r} relations in public have this "
        "name after the apply, not one"
        for row in rows
        if not _same(row.get("relations_in_public"), 1)
    ]


def table_post_check_failures(rows: Sequence[Mapping[str, Any]]) -> list[str]:
    """Pure: each new table's security row is exactly EXPECTED_SECURITY."""

    if [row.get("table") for row in rows] != list(TABLES):
        return [f"the new tables' security read was {[row.get('table') for row in rows]}"]
    return [
        f"{row['table']}: {field} is {row.get(field)!r}, not {_plain(expected)!r}"
        for row in rows
        for field, expected in EXPECTED_SECURITY.items()
        if not _same(_plain(row.get(field)), _plain(expected))
    ]


def column_post_check_failures(table: str, rows: Sequence[Mapping[str, Any]]) -> list[str]:
    """Pure: exactly the reviewed columns of ``table``, in order, each exactly as reviewed."""

    expected_columns = EXPECTED_COLUMNS[table]
    expected_names = [name for name, *_ in expected_columns]
    failures: list[str] = []
    names = [row.get("column") for row in rows]
    if names != expected_names:
        failures.append(f"{table}: the columns are {names}, not {expected_names}")
    for name, type_name, not_null, default in expected_columns:
        found = [row for row in rows if row.get("column") == name]
        if len(found) != 1:
            failures.append(f"{table}.{name}: {_count_after(found)}")
            continue
        expected = {
            "type": type_name,
            "not_null": not_null,
            "default": default,
            **dict.fromkeys(COLUMN_FLAGS_OFF, False),
        }
        failures += [
            f"{table}.{name}: {field} is {found[0].get(field)!r}, not {value!r}"
            for field, value in expected.items()
            if not _same(found[0].get(field), value)
        ]
    return failures


def constraint_post_check_failures(table: str, rows: Sequence[Mapping[str, Any]]) -> list[str]:
    """Pure: exactly the reviewed constraints, validated, over their columns, literals, integers."""

    expected_constraints = EXPECTED_CONSTRAINTS[table]
    failures: list[str] = []
    names = [row.get("constraint") for row in rows]
    if names != sorted(expected_constraints):
        failures.append(f"{table}: the constraints are {names}, not {sorted(expected_constraints)}")
    failures += [
        f"{table}.{row.get('constraint')}: is a foreign key, and 0013 creates none"
        for row in rows
        if row.get("type") == "f"
    ]
    for name, (kind, columns, literals, integers) in expected_constraints.items():
        found = [row for row in rows if row.get("constraint") == name]
        if len(found) != 1:
            failures.append(f"{table}.{name}: {_count_after(found)}")
            continue
        row = found[0]
        if row.get("type") != kind:
            failures.append(f"{table}.{name}: is of type {row.get('type')!r}, not {kind!r}")
        if row.get("validated") is not True:
            failures.append(f"{table}.{name}: is not validated")
        if row.get("columns") != list(columns):
            failures.append(
                f"{table}.{name}: references {row.get('columns')!r}, not {list(columns)}"
            )
        definition = row.get("definition")
        if not isinstance(definition, str):
            failures.append(f"{table}.{name}: its definition {definition!r} is unreadable")
            continue
        if constraint_literals(definition) != literals:
            failures.append(
                f"{table}.{name}: its literals are {sorted(constraint_literals(definition))}, "
                f"not {sorted(literals)}"
            )
        if constraint_integers(definition) != integers:
            failures.append(
                f"{table}.{name}: its integers are {sorted(constraint_integers(definition))}, "
                f"not {sorted(integers)}"
            )
    return failures


def index_post_check_failures(table: str, rows: Sequence[Mapping[str, Any]]) -> list[str]:
    """Pure: exactly the reviewed indexes: uniqueness and key column order, none partial."""

    expected_indexes = EXPECTED_INDEXES[table]
    failures: list[str] = []
    names = [row.get("index") for row in rows]
    if names != sorted(expected_indexes):
        failures.append(f"{table}: the indexes are {names}, not {sorted(expected_indexes)}")
    for name, (unique, columns) in expected_indexes.items():
        found = [row for row in rows if row.get("index") == name]
        if len(found) != 1:
            failures.append(f"{table}.{name}: {_count_after(found)}")
            continue
        row = found[0]
        if row.get("unique") is not unique:
            failures.append(f"{table}.{name}: unique is {row.get('unique')!r}, not {unique}")
        if row.get("columns") != list(columns):
            failures.append(
                f"{table}.{name}: its key columns are {row.get('columns')!r}, not {list(columns)}"
            )
        if row.get("predicate") is not None:
            failures.append(
                f"{table}.{name}: is partial ({row.get('predicate')!r}), not over every row"
            )
    return failures


def trigger_post_check_failures(table: str, rows: Sequence[Mapping[str, Any]]) -> list[str]:
    return [
        f"{table}: has the trigger {row.get('trigger')!r}, and 0013 creates none" for row in rows
    ]


def _none_failures(value: Any, what: str) -> list[str]:
    """A count that must be exactly zero."""

    if _same(value, 0):
        return []
    return [f"{value!r} {what}, not none"]


def _same(value: Any, expected: Any) -> bool:
    """Equal AND of the same type: True is never 1, and 0 is never False."""

    return type(value) is type(expected) and value == expected


def _count_after(found: Sequence[Mapping[str, Any]]) -> str:
    if not found:
        return "is missing after the apply"
    return f"appears {len(found)} times after the apply, not once"


def _unchanged_failures(
    what: str, key: str, pre: Sequence[Mapping[str, Any]], post: Sequence[Mapping[str, Any]]
) -> list[str]:
    """Pure: nothing when ``post`` is exactly ``pre``; otherwise every difference, by ``key``."""

    if list(post) == list(pre):
        return []
    before = {row.get(key): row for row in pre}
    after = {row.get(key): row for row in post}
    failures: list[str] = []
    for name in sorted({*before, *after}, key=repr):
        if name not in after:
            failures.append(f"the {what} {name!r} is gone after the apply")
        elif name not in before:
            failures.append(f"the {what} {name!r} appeared during the apply")
        elif after[name] != before[name]:
            fields = sorted({*before[name], *after[name]})
            changed = ", ".join(
                f"{field} {before[name].get(field)!r} -> {after[name].get(field)!r}"
                for field in fields
                if before[name].get(field) != after[name].get(field)
            )
            failures.append(f"the {what} {name!r} changed during the apply: {changed}")
    return failures or [f"the {what} rows changed in order or number during the apply"]


def _read_checks(
    cursor: Any,
    checks: Sequence[tuple[str, str, tuple[str, ...] | None]],
    captured: dict[str, Any],
    when: str,
) -> dict[str, Any]:
    results: dict[str, Any] = {}
    for name, query, fields in checks:
        if fields is None:
            cursor.execute(query)
            results[name] = _plain(_row(cursor.fetchone(), 1, name)[0])
        else:
            results[name] = _rows(cursor, query, fields)
        captured[f"{when}_{name}"] = results[name]
    return results


def _rows(cursor: Any, query: str, fields: Sequence[str]) -> list[dict[str, Any]]:
    cursor.execute(query)
    rows = []
    for row in cursor.fetchall():
        if row is None or len(row) != len(fields):
            raise _refusal(f"a check returned {row!r}, not a row of {len(fields)} values")
        rows.append({field: _plain(value) for field, value in zip(fields, row, strict=True)})
    return rows


def _plain(value: Any) -> Any:
    return list(value) if isinstance(value, (list, tuple)) else value


def _row(row: Any, width: int, what: str) -> tuple[Any, ...]:
    if row is None or len(row) != width:
        raise _refusal(f"the {what} query returned {row!r}, not one row of {width} values")
    return tuple(row)


def _git(*arguments: str) -> str | None:
    try:
        completed = subprocess.run(
            ["git", *arguments],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout.strip()


def _refusal(message: str) -> Exception:
    ensure_source_path()
    from crypto_probability_engine.runtime_isolation import ProvenanceRefused  # stdlib-only

    return ProvenanceRefused(f"migration 0013 refused; nothing is applied: {message}")


def _refusal_record(mode: str, exc: BaseException, captured: Mapping[str, Any]) -> dict[str, Any]:
    """Deliberate refusals name no secret; any other failure is reported by type only."""

    refused = _is_refusal(exc)
    return {
        "schema_version": REPORT_SCHEMA,
        "mode": mode,
        "outcome": "REFUSED" if refused else "FAILED",
        "error_type": type(exc).__name__,
        "detail": str(exc)
        if refused
        else "unexpected failure; the detail is withheld because driver messages can name the host",
        "committed": _commit_state(captured),
        "captured": dict(captured),
    }


def _commit_state(captured: Mapping[str, Any]) -> bool | str:
    """Whether anything was committed; UNKNOWN after a failure while a COMMIT was in flight.

    A rehearsal nests one record per apply (``first_apply``, ``second_apply``).
    """

    records = [captured, *(value for value in captured.values() if isinstance(value, Mapping))]
    if any(record.get("committed") is True for record in records):
        return True
    if any(record.get("commit_attempted") for record in records):
        return COMMIT_UNKNOWN
    return False


def _is_refusal(exc: BaseException) -> bool:
    ensure_source_path()
    from crypto_probability_engine.runtime_isolation import ProvenanceRefused  # stdlib-only

    return isinstance(exc, ProvenanceRefused)


def _write_report(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    sys.exit(main())
