"""E2 (governing plan §8.3): the evidence reader's build-tied, redacted capability metadata.

The Space reads evidence over direct Postgres: the calibration endpoint and the skill-evidence
refresh read predictions joined to their outcomes, and the F1 route reads its credential registry
and writes its ledger. The accepted design (C2, migration 0016) gives that path a narrow login of
its own, ucpe_space_db. Once per process start this module reports which role the path really
connects as, and what that role may do, from the catalog alone: no row of any table is read,
nothing is written, and no secret is printed.

- **The URL.** The Space secret UCPE_SPACE_DB_URL when it is set, else SUPABASE_DB_URL. The cutover
  adds the first; deleting it again is the rollback.
- **The event.** One evidence_reader_identity event on the structured log, with the release id and
  the name of the secret in use. The role is named only when it is UCPE's own (ucpe_*), else OTHER.
  Everything else is a boolean or a count.
- **Fail closed.** DESIGNED needs every check positively proven. A missing or malformed answer, an
  error, or a timeout is UNKNOWN, never DESIGNED.
"""

from __future__ import annotations

import os
import re
import threading
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from crypto_probability_engine.config.build_info import RELEASE_ID
from crypto_probability_engine.config.settings import Settings
from crypto_probability_engine.telemetry.events import EVENTS_SINK, TelemetrySink

EVENT = "evidence_reader_identity"
DESIGNED_ROLE = "ucpe_space_db"
CUTOVER_ENV = "UCPE_SPACE_DB_URL"
LEGACY_ENV = "SUPABASE_DB_URL"
SOURCE_NONE = "none"

ROLE_NOT_APPLICABLE = "n/a"
ROLE_ERROR = "error"
ROLE_OTHER = "OTHER"
VERDICT_DESIGNED = "DESIGNED"
VERDICT_NOT_DESIGNED = "NOT_DESIGNED"
VERDICT_UNKNOWN = "UNKNOWN"
VERDICT_NOT_CONFIGURED = "NOT_CONFIGURED"

# The six core evidence tables: scripts/core_write_inventory.py's CORE_TABLES (a test keeps them
# equal).
CORE_TABLES = (
    "analysis_run_details",
    "analysis_runs",
    "prediction_derivatives_snapshots",
    "prediction_feature_snapshots",
    "prediction_outcomes",
    "predictions",
)
# Everything the reader's code needs, and all that C2 grants (migration 0016, with Correction 01):
# the calibration query, the F1 credential registry and the F1 ledger.
NEEDED = (
    ("automation_credential", "SELECT"),
    ("automation_radar_ledger", "INSERT"),
    ("automation_radar_ledger", "SELECT"),
    ("automation_radar_ledger", "UPDATE"),
    ("prediction_outcomes", "SELECT"),
    ("predictions", "SELECT"),
)
TABLE_PRIVILEGES = ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER")
# SELECT, INSERT, UPDATE and REFERENCES may also be granted per column: any column counts.
_COLUMN_PRIVILEGES = frozenset({"SELECT", "INSERT", "UPDATE", "REFERENCES"})
MAINTAIN_SINCE_SERVER_VERSION = 170000
CONNECT_TIMEOUT_SECONDS = 10
STATEMENT_TIMEOUT_MS = 5000

_ROLE_NAME = re.compile(r"[a-z_][a-z0-9_]{0,62}")
_UCPE_ROLE = re.compile(r"ucpe_[a-z0-9_]{1,58}")
_ATTRIBUTES = ("superuser", "createrole", "createdb", "replication", "bypassrls", "inherit")
_POLICY_COMMANDS = {"SELECT": "r", "INSERT": "a", "UPDATE": "w"}
_POLICY_CODES = frozenset({"r", "a", "w", "d", "*"})

_SESSION_SQL = (
    "SELECT pg_catalog.current_setting('server_version_num')::int,"
    " current_user::text, session_user::text"
)
_ATTRIBUTES_SQL = (
    "SELECT rolsuper, rolcreaterole, rolcreatedb, rolreplication, rolbypassrls, rolinherit"
    " FROM pg_catalog.pg_roles WHERE rolname = current_user"
)
_MEMBERSHIPS_SQL = (
    "SELECT count(*) FROM pg_catalog.pg_auth_members m"
    " JOIN pg_catalog.pg_roles r ON r.oid = m.member WHERE r.rolname = current_user"
)
# The owner of the schema, or of any relation or function in it, may alter, drop or disable them.
_OWNER_SQL = (
    "SELECT bool_or(pg_catalog.pg_has_role(current_user, o.owner, 'MEMBER')) FROM ("
    " SELECT n.nspowner AS owner FROM pg_catalog.pg_namespace n WHERE n.nspname = 'public'"
    " UNION ALL SELECT c.relowner FROM pg_catalog.pg_class c"
    " JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname = 'public'"
    " UNION ALL SELECT p.proowner FROM pg_catalog.pg_proc p"
    " JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace WHERE n.nspname = 'public') o"
)
# PostgreSQL may evaluate WHERE conditions in any order, and has_sequence_privilege fails on
# anything but a sequence (42809): the CASE makes sure it only ever sees one.
_SEQUENCES_SQL = (
    "SELECT count(*) FILTER (WHERE CASE WHEN c.relkind = 'S'"
    " THEN pg_catalog.has_sequence_privilege(c.oid, 'USAGE, SELECT, UPDATE') ELSE false END)"
    " FROM pg_catalog.pg_class c"
    " JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace"
    " WHERE n.nspname = 'public'"
)
_CREATE_SQL = (
    "SELECT pg_catalog.has_schema_privilege('public', 'CREATE'),"
    " pg_catalog.has_database_privilege(pg_catalog.current_database(), 'CREATE')"
)
# A SECURITY DEFINER function runs with its owner's rights: each one the role may call is a route.
_DEFINERS_SQL = (
    "SELECT count(*) FROM pg_catalog.pg_proc p"
    " JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace"
    " WHERE n.nspname = 'public' AND p.prosecdef"
    " AND pg_catalog.has_function_privilege(p.oid, 'EXECUTE')"
)
# Row security on the needed tables: a policy applies to the role itself, to a role whose rights
# it inherits, or to PUBLIC (role 0).
_POLICIES_SQL = (
    "SELECT c.relname::text, c.relrowsecurity, c.relforcerowsecurity,"
    " pg_catalog.pg_has_role(current_user, c.relowner, 'USAGE'),"
    " p.polcmd::text, p.polpermissive,"
    " pg_catalog.pg_get_expr(p.polqual, p.polrelid),"
    " pg_catalog.pg_get_expr(p.polwithcheck, p.polrelid),"
    " EXISTS (SELECT 1 FROM pg_catalog.unnest(p.polroles) AS r(role_oid)"
    " WHERE CASE WHEN r.role_oid = 0 THEN true"
    " ELSE pg_catalog.pg_has_role(current_user, r.role_oid, 'USAGE') END)"
    " FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace"
    " LEFT JOIN pg_catalog.pg_policy p ON p.polrelid = c.oid"
    " WHERE n.nspname = 'public' AND c.relname::text = ANY(%(tables)s::text[])"
    " AND c.relkind IN ('r', 'p')"
    " ORDER BY 1"
)

Connect = Callable[..., Any]


class ReaderIdentityError(Exception):
    """A catalog answer was missing or malformed. Its message never carries a secret."""


def evidence_reader_settings(
    settings: Settings, environ: Mapping[str, str] | None = None
) -> tuple[Settings, str]:
    """The settings the Space's direct Postgres uses, and the name of the secret its URL came from.

    UCPE_SPACE_DB_URL wins when it is set, so adding it is the cutover and deleting it the rollback.
    Without it nothing changes: SUPABASE_DB_URL, exactly as before.
    """

    cutover = (os.environ if environ is None else environ).get(CUTOVER_ENV, "").strip()
    if cutover:
        return (
            settings.model_copy(
                update={"supabase_db_url": cutover, "external_store_configured": True}
            ),
            CUTOVER_ENV,
        )
    return settings, LEGACY_ENV if settings.supabase_db_url else SOURCE_NONE


def _relations_sql(maintain: bool) -> str:
    checks = [
        f"pg_catalog.has_any_column_privilege(c.oid, '{privilege}')"
        if privilege in _COLUMN_PRIVILEGES
        else f"pg_catalog.has_table_privilege(c.oid, '{privilege}')"
        for privilege in _table_privileges(maintain)
    ]
    return (
        "SELECT c.relname::text, " + ", ".join(checks)
        + " FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace"
        " WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p', 'v', 'm', 'f') ORDER BY 1"
    )


def _table_privileges(maintain: bool) -> tuple[str, ...]:
    return TABLE_PRIVILEGES + (("MAINTAIN",) if maintain else ())


def _one(cursor: Any, statement: str, params: Mapping[str, Any] | None = None) -> tuple:
    cursor.execute(statement, params)
    row = cursor.fetchone()
    if row is None:
        raise ReaderIdentityError("a catalog read returned no row")
    return tuple(row)


def _boolean(value: Any) -> bool:
    if not isinstance(value, bool):
        raise ReaderIdentityError("a catalog answer was not a boolean")
    return value


def _count(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ReaderIdentityError("a catalog answer was not a count")
    return value


def read_facts(url: str, *, connect: Connect | None = None) -> dict[str, Any]:
    """The catalog facts about the role that ``url`` connects as: one read-only transaction,
    rolled back, on its own short-lived connection."""

    if connect is None:
        import psycopg

        connect = psycopg.connect
    # As the F1 ledger's connections: no server-side prepared statements (they break behind
    # Supabase's transaction pooler), and a stalled network after connecting is bounded too.
    conn = connect(
        url,
        connect_timeout=CONNECT_TIMEOUT_SECONDS,
        autocommit=False,
        prepare_threshold=None,
        tcp_user_timeout=CONNECT_TIMEOUT_SECONDS * 1000,
    )
    try:
        with conn.cursor() as cursor:
            cursor.execute("SET TRANSACTION READ ONLY")
            cursor.execute(f"SET LOCAL statement_timeout = {STATEMENT_TIMEOUT_MS}")
            version, current, session = _one(cursor, _SESSION_SQL)
            maintain = _count(version) >= MAINTAIN_SINCE_SERVER_VERSION
            attributes = _one(cursor, _ATTRIBUTES_SQL)
            memberships = _one(cursor, _MEMBERSHIPS_SQL)[0]
            owner_rights = _one(cursor, _OWNER_SQL)[0]
            cursor.execute(_relations_sql(maintain))
            relations = [tuple(row) for row in cursor.fetchall()]
            sequences = _one(cursor, _SEQUENCES_SQL)[0]
            schema_create, database_create = _one(cursor, _CREATE_SQL)
            definers = _one(cursor, _DEFINERS_SQL)[0]
            cursor.execute(
                _POLICIES_SQL, {"tables": sorted({table for table, _ in NEEDED})}
            )
            policies = [tuple(row) for row in cursor.fetchall()]
        conn.rollback()
    finally:
        conn.close()
    return {
        "maintain": maintain,
        "current_user": current,
        "session_user": session,
        "attributes": dict(zip(_ATTRIBUTES, attributes, strict=True)),
        "memberships": memberships,
        "owner_rights": owner_rights,
        "relations": relations,
        "sequences": sequences,
        "schema_create": schema_create,
        "database_create": database_create,
        "definers": definers,
        "policies": policies,
    }


def _policy_row(row: Any) -> tuple:
    """One row of the policies read, checked whole: a table without a policy has NULLs only."""

    if not (isinstance(row, tuple | list) and len(row) == 9 and isinstance(row[0], str)):
        raise ReaderIdentityError("a policy row was malformed")
    for value in row[1:4]:
        _boolean(value)
    if row[4] is None:
        if any(value is not None for value in row[5:8]) or row[8] is not False:
            raise ReaderIdentityError("a table without a policy was malformed")
    elif (
        row[4] not in _POLICY_CODES
        or not isinstance(row[5], bool)
        or not isinstance(row[8], bool)
        or not all(value is None or isinstance(value, str) for value in row[6:8])
    ):
        raise ReaderIdentityError("a policy row was malformed")
    return tuple(row)


def _rls_allows(rows: Sequence[tuple], command: str, bypass: bool) -> bool:
    """Whether row security lets the role reach every row of one table for one command."""

    if not rows:
        return False
    rowsecurity, forced, acts_as_owner = rows[0][1:4]
    if not rowsecurity or bypass or (acts_as_owner and not forced):
        return True
    code = _POLICY_COMMANDS[command]
    applicable = [row for row in rows if row[4] in (code, "*") and row[8]]

    def unrestricted(row: tuple) -> bool:
        # PostgreSQL: a policy without WITH CHECK checks new rows with its USING expression.
        using, check = row[6], row[7]
        effective_check = check if check is not None else using
        if command == "SELECT":
            return using == "true"
        if command == "INSERT":
            return effective_check == "true"
        return using == "true" and effective_check == "true"

    # Restrictive policies must all pass; at least one permissive policy must let every row in.
    if any(not row[5] and not unrestricted(row) for row in applicable):
        return False
    return any(row[5] and unrestricted(row) for row in applicable)


def classify(facts: Mapping[str, Any]) -> dict[str, Any]:
    """The event's redacted fields and verdict. Raises ReaderIdentityError on a malformed fact."""

    current, session = facts["current_user"], facts["session_user"]
    if not (isinstance(current, str) and _ROLE_NAME.fullmatch(current)):
        raise ReaderIdentityError("the connected role is not a plain role name")
    attributes = {name: _boolean(facts["attributes"][name]) for name in _ATTRIBUTES}
    privileges = _table_privileges(_boolean(facts["maintain"]))
    held: set[tuple[str, str]] = set()
    for row in facts["relations"]:
        if len(row) != len(privileges) + 1 or not isinstance(row[0], str):
            raise ReaderIdentityError("a relation's privileges were malformed")
        held.update(
            (row[0], privilege)
            for privilege, value in zip(privileges, row[1:], strict=True)
            if _boolean(value)
        )
    extra = (
        len(held - set(NEEDED))
        + _count(facts["sequences"])
        + int(_boolean(facts["schema_create"]))
        + int(_boolean(facts["database_create"]))
    )
    bypass = attributes["superuser"] or attributes["bypassrls"]
    by_table: dict[str, list[tuple]] = {}
    for row in facts["policies"]:
        checked = _policy_row(row)
        by_table.setdefault(checked[0], []).append(checked)
    fields: dict[str, Any] = {
        "db_role": current if _UCPE_ROLE.fullmatch(current) else ROLE_OTHER,
        # The login is the role itself: no stronger login that switched to it with SET ROLE.
        "login_is_role": session == current,
        **attributes,
        "role_memberships": _count(facts["memberships"]),
        "owner_rights": _boolean(facts["owner_rights"]),
        "core_write": any(
            table in CORE_TABLES and privilege != "SELECT" for table, privilege in held
        ),
        "definer_execute": _count(facts["definers"]),
        "needed_privileges": set(NEEDED) <= held,
        "rls_allows_all": all(
            _rls_allows(by_table.get(table, []), privilege, bypass) for table, privilege in NEEDED
        ),
        "extra_privileges": extra,
    }
    designed = (
        current == DESIGNED_ROLE
        and fields["login_is_role"]
        and not any(attributes.values())
        and fields["role_memberships"] == 0
        and not fields["owner_rights"]
        and not fields["core_write"]
        and fields["definer_execute"] == 0
        and fields["needed_privileges"]
        and fields["rls_allows_all"]
        and extra == 0
    )
    fields["verdict"] = VERDICT_DESIGNED if designed else VERDICT_NOT_DESIGNED
    return fields


def report(
    url: str | None,
    source: str,
    *,
    connect: Connect | None = None,
    sink: TelemetrySink = EVENTS_SINK,
) -> dict[str, Any]:
    """Record one evidence_reader_identity event and return its fields. Never raises."""

    try:
        if not url:
            fields: dict[str, Any] = {
                "db_role": ROLE_NOT_APPLICABLE,
                "verdict": VERDICT_NOT_CONFIGURED,
            }
        else:
            fields = classify(read_facts(url, connect=connect))
    except Exception as exc:  # noqa: BLE001 - fail closed: the class name only, never the message
        fields = {
            "db_role": ROLE_ERROR,
            "verdict": VERDICT_UNKNOWN,
            "error_class": type(exc).__name__,
        }
    fields.update(release_id=RELEASE_ID, db_url_source=source)
    sink.record(EVENT, fields)
    return fields


def start_report(settings: Settings, source: str) -> None:
    """One report per process start, off the startup path: a daemon thread when there is a URL to
    probe, else the NOT_CONFIGURED event at once. Never raises, never delays startup."""

    try:
        url = settings.supabase_db_url
        if not url:
            report(None, source)
            return
        threading.Thread(
            target=report, args=(url, source), name="ucpe-reader-identity", daemon=True
        ).start()
    except Exception:  # noqa: BLE001 - the report is evidence only; startup must never fail on it
        return
