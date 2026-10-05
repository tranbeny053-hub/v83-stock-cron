"""The catalog fingerprint of the structure-first restore proof (plan §12.1; owner ruling DP-D=2).

One function reads a database's structure from the system catalogs alone (never a table row): the
public schema, its relations and columns, constraints, indexes, triggers (the seals among them),
row-security policies, functions, sequences, types, comments, owners, every grant, column grants
included, the schema's default privileges, and the cluster's roles: every role's attributes, every
membership, every role setting and every parameter grant (what a roles export restores that can
carry a privilege; a role's comment, security label and password expiry carry none and are not
read). A setting's value is kept as a digest only, so no value is ever shown. Two fingerprints, one
of a database built from the migrations and one of the restored export, are then compared item by
item.

Names are normalized so that only real differences remain:
- the role that ran the migrations (a scratch login in the reference, the project's ``postgres`` in
  production) is ``<owner>`` on each side, wherever it appears (owner, grantee, grantor, member);
- PUBLIC is ``PUBLIC``;
- a membership's grantor is not compared (it records who ran the grant, which differs by platform);
- columns are compared in their order, not by attribute number (a restore renumbers dropped ones).

Each difference is classified:
- **app**: the migrations' own structure and grants; the roles they create (attributes, settings,
  memberships either way, parameter grants); the default privileges of the owner and of those
  roles; and every privilege path into the app: an API role (one the app's grants or policies name,
  or one holding a migration role: Supabase's anon, authenticated, service_role, authenticator)
  becoming a member of any role, gaining SUPERUSER, CREATEROLE, CREATEDB, REPLICATION or
  BYPASSRLS, or LOGIN (authenticator's LOGIN is the platform's), being gone, or having any setting
  but a timeout changed (a setting such as session_replication_role on the login role would turn
  the seals off for every API session); any role but the bootstrap superuser holding the owner; a
  parameter grant to an API role or a migration role. Any app difference fails the proof, whoever
  made it: one the platform made is reported to the owner by name, never reclassified.
- **operational**: exactly the documented owner credential steps, LOGIN on ucpe_space_db
  (docs/runbooks/SPACE_DB_CUTOVER.md) and on ucpe_resolver (docs/runbooks/RESOLVER_CUTOVER.md).
  Reported, not failing.
- **platform**: the hosting platform's own: its other roles, their memberships and settings, an API
  role's timeouts and its other attributes, the owner's attributes, settings and parameter grants
  (the owner already owns every app object), the default privileges of any other role, other
  parameter grants. Reported, not failing.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SCHEMA = "public"
OWNER = "<owner>"
PUBLIC = "PUBLIC"
ROLE_ATTRIBUTES = (
    "rolsuper",
    "rolinherit",
    "rolcreaterole",
    "rolcreatedb",
    "rolcanlogin",
    "rolreplication",
    "rolbypassrls",
    "rolconnlimit",
)
# The owner's documented credential steps: these roles gain LOGIN outside the migrations.
OPERATIONAL_LOGIN_ROLES = frozenset({"ucpe_space_db", "ucpe_resolver"})
# The settings an API role may carry as the platform's: a timeout cannot raise a privilege.
TIMEOUT_SETTINGS = frozenset(
    {
        "statement_timeout",
        "lock_timeout",
        "idle_in_transaction_session_timeout",
        "idle_session_timeout",
        "transaction_timeout",
    }
)
_CREATE_ROLE = re.compile(r"^\s*CREATE\s+ROLE\s+([a-z_][a-z0-9_]*)\b", re.IGNORECASE | re.MULTILINE)


def migration_roles(migrations: Path) -> frozenset[str]:
    """The roles the migrations themselves create (one source of truth: the migration files)."""

    names: set[str] = set()
    for path in sorted(migrations.glob("[0-9][0-9][0-9][0-9]_*.sql")):
        names.update(match.lower() for match in _CREATE_ROLE.findall(path.read_text()))
    return frozenset(names)


def fingerprint(conn: Any, *, owner: str) -> dict[str, Any]:
    """The structure of one database, normalized for comparison. Catalog reads only."""

    names = {oid: name for oid, name in _rows(conn, "SELECT oid, rolname FROM pg_roles")}

    def named(name: str) -> str:
        return OWNER if name == owner else name

    def role(oid: int) -> str:
        return PUBLIC if oid == 0 else named(names.get(oid, f"<unknown role {oid}>"))

    def acl(rows: Iterable[tuple[Any, ...]]) -> dict[str, list[str]]:
        grants: dict[str, list[str]] = {}
        for key, grantor, grantee, privilege, grantable in rows:
            item = f"{role(grantee)}:{privilege}{'*' if grantable else ''} by {role(grantor)}"
            grants.setdefault(key, []).append(item)
        return {key: sorted(items) for key, items in grants.items()}

    schema_rows = _rows(
        conn,
        "SELECT nspowner, obj_description(oid, 'pg_namespace') FROM pg_namespace "
        "WHERE nspname = %s",
        (SCHEMA,),
    )
    schema = {
        "present": bool(schema_rows),
        "owner": role(schema_rows[0][0]) if schema_rows else None,
        "comment": schema_rows[0][1] if schema_rows else None,
        "acl": acl(
            _rows(
                conn,
                "SELECT 'schema', a.grantor, a.grantee, a.privilege_type, a.is_grantable "
                "FROM pg_namespace n, "
                "aclexplode(coalesce(n.nspacl, acldefault('n', n.nspowner))) a "
                "WHERE n.nspname = %s",
                (SCHEMA,),
            )
        ).get("schema", []),
    }

    relations: dict[str, dict[str, Any]] = {}
    for (
        name,
        kind,
        owner_oid,
        rls,
        force_rls,
        persistence,
        replident,
        options,
        comment,
        partkey,
        viewdef,
    ) in _rows(
        conn,
        """
        SELECT c.relname, c.relkind, c.relowner, c.relrowsecurity, c.relforcerowsecurity,
               c.relpersistence, c.relreplident, coalesce(c.reloptions, '{}'),
               obj_description(c.oid, 'pg_class'),
               CASE WHEN c.relkind = 'p' THEN pg_get_partkeydef(c.oid) END,
               CASE WHEN c.relkind IN ('v', 'm') THEN pg_get_viewdef(c.oid, true) END
        FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = %s AND c.relkind IN ('r', 'p', 'v', 'm', 'S', 'f', 'c')
          AND NOT EXISTS (SELECT 1 FROM pg_depend d WHERE d.classid = 'pg_class'::regclass
                          AND d.objid = c.oid AND d.deptype = 'e')
        """,
        (SCHEMA,),
    ):
        relations[name] = {
            "kind": kind,
            "owner": role(owner_oid),
            "row_security": rls,
            "force_row_security": force_rls,
            "persistence": persistence,
            "replica_identity": replident,
            "options": sorted(options),
            "comment": comment,
            "partition_key": partkey,
            "view": viewdef,
        }
    # Effective privileges: no ACL means the owner's default ones (acldefault), which is what a
    # dump leaves when an object's privileges equal that default.
    relation_acl = acl(
        _rows(
            conn,
            """
            SELECT c.relname, a.grantor, a.grantee, a.privilege_type, a.is_grantable
            FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace,
                 aclexplode(coalesce(c.relacl, acldefault(
                     (CASE WHEN c.relkind = 'S' THEN 's' ELSE 'r' END)::"char", c.relowner))) a
            WHERE n.nspname = %s AND c.relkind IN ('r', 'p', 'v', 'm', 'S', 'f')
            """,
            (SCHEMA,),
        )
    )
    for name, relation in relations.items():
        relation["acl"] = relation_acl.get(name, [])

    columns: dict[str, dict[str, Any]] = {}
    for relname, attname, typ, notnull, default, identity, generated, collation, comment in _rows(
        conn,
        """
        SELECT c.relname, a.attname, format_type(a.atttypid, a.atttypmod), a.attnotnull,
               pg_get_expr(d.adbin, d.adrelid), a.attidentity, a.attgenerated,
               CASE WHEN a.attcollation <> t.typcollation
                    THEN (SELECT collname FROM pg_collation WHERE oid = a.attcollation) END,
               col_description(c.oid, a.attnum)
        FROM pg_attribute a
        JOIN pg_class c ON c.oid = a.attrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        JOIN pg_type t ON t.oid = a.atttypid
        LEFT JOIN pg_attrdef d ON d.adrelid = a.attrelid AND d.adnum = a.attnum
        WHERE n.nspname = %s AND c.relkind IN ('r', 'p', 'v', 'm', 'f', 'c')
          AND a.attnum > 0 AND NOT a.attisdropped
        ORDER BY c.relname, a.attnum
        """,
        (SCHEMA,),
    ):
        relation_columns = columns.setdefault(relname, {"order": [], "by_name": {}})
        relation_columns["order"].append(attname)
        relation_columns["by_name"][attname] = {
            "type": typ,
            "not_null": notnull,
            "default": default,
            "identity": identity,
            "generated": generated,
            "collation": collation,
            "comment": comment,
        }
    column_acl = acl(
        _rows(
            conn,
            """
            SELECT c.relname || '.' || a.attname, x.grantor, x.grantee, x.privilege_type,
                   x.is_grantable
            FROM pg_attribute a JOIN pg_class c ON c.oid = a.attrelid
            JOIN pg_namespace n ON n.oid = c.relnamespace, aclexplode(a.attacl) x
            WHERE n.nspname = %s AND a.attnum > 0 AND NOT a.attisdropped
            """,
            (SCHEMA,),
        )
    )

    constraints = _keyed(
        _rows(
            conn,
            """
            SELECT coalesce(c.relname, t.typname), con.conname,
                   con.contype::text || ' ' || pg_get_constraintdef(con.oid, true)
                   || CASE WHEN con.convalidated THEN '' ELSE ' NOT VALID' END
                   || CASE WHEN con.condeferrable THEN ' DEFERRABLE' ELSE '' END
                   || CASE WHEN con.condeferred THEN ' INITIALLY DEFERRED' ELSE '' END
            FROM pg_constraint con
            LEFT JOIN pg_class c ON c.oid = con.conrelid
            LEFT JOIN pg_type t ON t.oid = con.contypid
            JOIN pg_namespace n ON n.oid = coalesce(c.relnamespace, t.typnamespace)
            WHERE n.nspname = %s
            """,
            (SCHEMA,),
        )
    )
    indexes = _keyed(
        _rows(
            conn,
            """
            SELECT t.relname, i.relname, pg_get_indexdef(i.oid)
            FROM pg_index x JOIN pg_class i ON i.oid = x.indexrelid
            JOIN pg_class t ON t.oid = x.indrelid JOIN pg_namespace n ON n.oid = t.relnamespace
            WHERE n.nspname = %s
            """,
            (SCHEMA,),
        )
    )
    triggers = _keyed(
        _rows(
            conn,
            """
            SELECT c.relname, t.tgname,
                   pg_get_triggerdef(t.oid, true) || ' [' || t.tgenabled::text || ']'
            FROM pg_trigger t JOIN pg_class c ON c.oid = t.tgrelid
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = %s AND NOT t.tgisinternal
            """,
            (SCHEMA,),
        )
    )
    policies: dict[str, dict[str, Any]] = {}
    for relname, polname, cmd, permissive, role_oids, qual, check in _rows(
        conn,
        """
        SELECT c.relname, p.polname, p.polcmd, p.polpermissive, p.polroles,
               pg_get_expr(p.polqual, p.polrelid), pg_get_expr(p.polwithcheck, p.polrelid)
        FROM pg_policy p JOIN pg_class c ON c.oid = p.polrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = %s
        """,
        (SCHEMA,),
    ):
        policies.setdefault(relname, {})[polname] = {
            "command": cmd,
            "permissive": permissive,
            "roles": sorted(role(oid) for oid in role_oids),
            "using": qual,
            "with_check": check,
        }

    functions: dict[str, dict[str, Any]] = {}
    for (
        signature,
        kind,
        owner_oid,
        definition,
        secdef,
        volatility,
        leakproof,
        config,
        comment,
    ) in _rows(
        conn,
        """
        SELECT p.proname || '(' || pg_get_function_identity_arguments(p.oid) || ')',
               p.prokind, p.proowner,
               CASE WHEN p.prokind IN ('f', 'p', 'w') THEN pg_get_functiondef(p.oid) END,
               p.prosecdef, p.provolatile, p.proleakproof, coalesce(p.proconfig, '{}'),
               obj_description(p.oid, 'pg_proc')
        FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
        WHERE n.nspname = %s
          AND NOT EXISTS (SELECT 1 FROM pg_depend d WHERE d.classid = 'pg_proc'::regclass
                          AND d.objid = p.oid AND d.deptype = 'e')
        """,
        (SCHEMA,),
    ):
        functions[signature] = {
            "kind": kind,
            "owner": role(owner_oid),
            "definition_sha256": _sha(definition),
            "definition": definition,
            "security_definer": secdef,
            "volatility": volatility,
            "leakproof": leakproof,
            "config": sorted(config),
            "comment": comment,
        }
    function_acl = acl(
        _rows(
            conn,
            "SELECT p.proname || '(' || pg_get_function_identity_arguments(p.oid) || ')', "
            "a.grantor, a.grantee, a.privilege_type, a.is_grantable "
            "FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace, "
            "aclexplode(coalesce(p.proacl, acldefault('f', p.proowner))) a "
            "WHERE n.nspname = %s",
            (SCHEMA,),
        )
    )
    for signature, function in functions.items():
        function["acl"] = function_acl.get(signature, [])

    sequences = {
        name: {
            "type": typ,
            "start": start,
            "increment": increment,
            "max": maximum,
            "min": minimum,
            "cache": cache,
            "cycle": cycle,
        }
        for name, typ, start, increment, maximum, minimum, cache, cycle in _rows(
            conn,
            """
            SELECT c.relname, format_type(s.seqtypid, NULL), s.seqstart, s.seqincrement,
                   s.seqmax, s.seqmin, s.seqcache, s.seqcycle
            FROM pg_sequence s JOIN pg_class c ON c.oid = s.seqrelid
            JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname = %s
            """,
            (SCHEMA,),
        )
    }
    types = {
        name: {
            "kind": kind,
            "owner": role(owner_oid),
            "labels": labels,
            "base": base,
            "not_null": notnull,
            "default": default,
            "comment": comment,
        }
        for name, kind, owner_oid, labels, base, notnull, default, comment in _rows(
            conn,
            """
            SELECT t.typname, t.typtype, t.typowner,
                   CASE WHEN t.typtype = 'e' THEN (SELECT array_agg(e.enumlabel ORDER BY
                        e.enumsortorder) FROM pg_enum e WHERE e.enumtypid = t.oid) END,
                   CASE WHEN t.typtype = 'd' THEN format_type(t.typbasetype, t.typtypmod) END,
                   t.typnotnull, t.typdefault, obj_description(t.oid, 'pg_type')
            FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace
            WHERE n.nspname = %s AND t.typtype IN ('e', 'd', 'r', 'm', 'b')
              AND NOT EXISTS (SELECT 1 FROM pg_depend d WHERE d.classid = 'pg_type'::regclass
                              AND d.objid = t.oid AND d.deptype = 'e')
            """,
            (SCHEMA,),
        )
    }
    extensions = dict(
        _rows(
            conn,
            "SELECT e.extname, e.extversion FROM pg_extension e "
            "JOIN pg_namespace n ON n.oid = e.extnamespace WHERE n.nspname = %s",
            (SCHEMA,),
        )
    )
    default_privileges = acl(
        (f"{role(defaclrole)} {objtype}", grantor, grantee, privilege, grantable)
        for defaclrole, objtype, grantor, grantee, privilege, grantable in _rows(
            conn,
            """
            SELECT d.defaclrole, d.defaclobjtype, a.grantor, a.grantee, a.privilege_type,
                   a.is_grantable
            FROM pg_default_acl d JOIN pg_namespace n ON n.oid = d.defaclnamespace,
                 aclexplode(d.defaclacl) a
            WHERE n.nspname = %s
            """,
            (SCHEMA,),
        )
    )

    # The cluster's roles, whole: every role's attributes (the predefined pg_ roles' are fixed by
    # PostgreSQL), every membership, every setting (its value as a digest) and every parameter
    # grant the roles export restores; _classify decides what a difference means.
    cluster_attributes = {
        named(row[0]): dict(zip(ROLE_ATTRIBUTES, row[1:], strict=True))
        for row in _rows(
            conn,
            "SELECT rolname, " + ", ".join(ROLE_ATTRIBUTES) + " FROM pg_roles "
            "WHERE rolname !~ '^pg_'",
        )
    }
    cluster_settings = {
        f"{named(name)} in {_database_scope(database, current)}": sorted(map(_setting, config))
        for name, database, current, config in _rows(
            conn,
            """
            SELECT r.rolname, s.setdatabase,
                   s.setdatabase = (SELECT oid FROM pg_database WHERE datname = current_database()),
                   s.setconfig
            FROM pg_db_role_setting s JOIN pg_roles r ON r.oid = s.setrole
            """,
        )
    }
    cluster_memberships = sorted(
        f"{named(granted)} to {named(member)} admin={admin} inherit={inherit} set={can_set}"
        for granted, member, admin, inherit, can_set in _rows(
            conn,
            """
            SELECT r.rolname, m.rolname, am.admin_option, am.inherit_option, am.set_option
            FROM pg_auth_members am JOIN pg_roles r ON r.oid = am.roleid
            JOIN pg_roles m ON m.oid = am.member
            """,
        )
    )
    parameter_acl = acl(
        _rows(
            conn,
            "SELECT p.parname, a.grantor, a.grantee, a.privilege_type, a.is_grantable "
            "FROM pg_parameter_acl p, aclexplode(p.paracl) a",
        )
    )

    return {
        "schema": schema,
        "relations": relations,
        "columns": columns,
        "column_acl": column_acl,
        "constraints": constraints,
        "indexes": indexes,
        "triggers": triggers,
        "policies": policies,
        "functions": functions,
        "sequences": sequences,
        "types": types,
        "extensions": extensions,
        "default_privileges": default_privileges,
        "cluster": {
            "attributes": cluster_attributes,
            "settings": cluster_settings,
            "memberships": cluster_memberships,
            "parameter_acl": parameter_acl,
        },
    }


@dataclass(frozen=True)
class Difference:
    category: str  # "app", "operational" or "platform"
    path: str
    reference: Any
    restored: Any


# A role attribute that raises privilege: an API role gaining one is an app difference.
ESCALATING_ATTRIBUTES = frozenset(
    {"rolsuper", "rolcreaterole", "rolcreatedb", "rolreplication", "rolbypassrls"}
)
# The API role PostgREST logs in as: LOGIN on it is the platform's (Supabase's authenticator).
API_LOGIN_ROLE = "authenticator"


def api_roles(
    reference: dict[str, Any], migration: frozenset[str], bootstrap: str | None = None
) -> frozenset[str]:
    """The API roles: the ones the reference's own grants and policies name, or that hold a
    migration role, beyond the migration roles, the owner and the bootstrap superuser."""

    holders = {
        member
        for item in reference.get("cluster", {}).get("memberships", [])
        for granted, member in [_membership(item)]
        if granted in migration
    }
    return frozenset(
        (named_roles(reference) | holders) - set(migration) - {OWNER, PUBLIC, bootstrap}
    )


def named_roles(fingerprint: dict[str, Any]) -> set[str]:
    """Every role a fingerprint's grants, default privileges and policies name."""

    names: set[str] = set()
    grant_lists = [
        fingerprint.get("schema", {}).get("acl", []),
        *(item.get("acl", []) for item in fingerprint.get("relations", {}).values()),
        *(item.get("acl", []) for item in fingerprint.get("functions", {}).values()),
        *fingerprint.get("column_acl", {}).values(),
        *fingerprint.get("default_privileges", {}).values(),
    ]
    names.update(item.split(":", 1)[0] for grants in grant_lists for item in grants)
    names.update(
        name
        for items in fingerprint.get("policies", {}).values()
        for policy in items.values()
        for name in policy.get("roles", [])
    )
    return names


def compare(
    reference: dict[str, Any],
    restored: dict[str, Any],
    migration_roles: frozenset[str] = frozenset(),
    bootstrap: str | None = None,
) -> list[Difference]:
    """Every difference between the two fingerprints, classified (see api_roles)."""

    differences: list[Difference] = []
    _walk("", reference, restored, differences)
    roles = _Roles(migration_roles, api_roles(reference, migration_roles, bootstrap), bootstrap)
    return [_classify(difference, roles) for difference in differences]


@dataclass(frozen=True)
class _Roles:
    migration: frozenset[str]
    api: frozenset[str]
    bootstrap: str | None


def _walk(path: str, left: Any, right: Any, out: list[Difference]) -> None:
    if isinstance(left, dict) and isinstance(right, dict):
        for key in sorted(set(left) | set(right)):
            child = f"{path}/{key}" if path else str(key)
            if key not in left:
                out.append(Difference("app", child, None, _summary(right[key])))
            elif key not in right:
                out.append(Difference("app", child, _summary(left[key]), None))
            else:
                _walk(child, left[key], right[key], out)
        return
    if path.endswith("/definition"):
        return  # compared by its sha256; the text is only for showing where it differs
    if path.endswith("/memberships") and isinstance(left, list) and isinstance(right, list):
        for item in sorted(set(left) - set(right)):
            out.append(Difference("app", f"{path}/{item}", item, None))
        for item in sorted(set(right) - set(left)):
            out.append(Difference("app", f"{path}/{item}", None, item))
        return
    if left != right:
        out.append(Difference("app", path, left, right))


def _classify(difference: Difference, roles: _Roles) -> Difference:
    parts = difference.path.split("/")

    def as_(category: str) -> Difference:
        return Difference(category, difference.path, difference.reference, difference.restored)

    if parts[0] == "default_privileges" and len(parts) > 1:
        holder = parts[1].split(" ")[0]
        return difference if holder == OWNER or holder in roles.migration else as_("platform")
    if parts[0] != "cluster" or len(parts) < 3:
        return difference
    section, subject = parts[1], parts[2]
    if section == "attributes":
        attribute = parts[3] if len(parts) > 3 else None
        if subject in roles.migration:
            operational = (
                subject in OPERATIONAL_LOGIN_ROLES
                and attribute == "rolcanlogin"
                and difference.reference is False
                and difference.restored is True
            )
            return as_("operational") if operational else difference
        if subject in roles.api:
            if attribute is None and difference.restored is None:
                return difference  # an API role the app's grants name is gone
            raised = difference.reference is False and difference.restored is True
            if raised and (
                attribute in ESCALATING_ATTRIBUTES
                or (attribute == "rolcanlogin" and subject != API_LOGIN_ROLE)
            ):
                return difference
        return as_("platform")
    if section == "memberships":
        granted, member = _membership(subject)
        if granted in roles.migration or member in roles.migration or member in roles.api:
            return difference
        if granted == OWNER and member != roles.bootstrap:
            return difference  # a role holding the owner holds every app object
        return as_("platform")
    if section == "settings":
        role = subject.split(" in ")[0]
        changed = set(difference.reference or []) ^ set(difference.restored or [])
        names = {item.split(" ", 1)[0] for item in changed}
        if role in roles.migration or (role in roles.api and not names <= TIMEOUT_SETTINGS):
            return difference
        return as_("platform")
    if section == "parameter_acl":
        changed = set(difference.reference or []) ^ set(difference.restored or [])
        grantees = {item.split(":", 1)[0] for item in changed}
        return difference if grantees & (roles.migration | roles.api) else as_("platform")
    return difference


def _membership(item: str) -> tuple[str, str]:
    granted, member = item.split(" admin=")[0].split(" to ", 1)
    return granted, member


def function_diff(reference: dict[str, Any], restored: dict[str, Any]) -> dict[str, Any]:
    """Where two function definitions with different digests first differ (line and both texts)."""

    shown: dict[str, Any] = {}
    for signature in sorted(set(reference["functions"]) & set(restored["functions"])):
        left = reference["functions"][signature]["definition"] or ""
        right = restored["functions"][signature]["definition"] or ""
        if left == right:
            continue
        left_lines, right_lines = left.split("\n"), right.split("\n")
        for number, (a, b) in enumerate(zip(left_lines, right_lines, strict=False), start=1):
            if a != b:
                shown[signature] = {"line": number, "reference": a[:200], "restored": b[:200]}
                break
        else:
            shown[signature] = {
                "line": min(len(left_lines), len(right_lines)) + 1,
                "reference": f"{len(left_lines)} lines",
                "restored": f"{len(right_lines)} lines",
            }
    return shown


def _setting(item: str) -> str:
    """A role setting as "name sha256:<digest>": compared exactly, its value never shown."""

    name, _, value = item.partition("=")
    return f"{name} sha256:{_sha(value)}"


def _database_scope(database: int, current: bool) -> str:
    if database == 0:
        return "all databases"
    return "this database" if current else "another database"


def _keyed(rows: Iterable[tuple[Any, ...]]) -> dict[str, dict[str, Any]]:
    keyed: dict[str, dict[str, Any]] = {}
    for parent, name, value in rows:
        keyed.setdefault(parent, {})[name] = value
    return keyed


def _rows(conn: Any, sql: str, params: tuple[Any, ...] = ()) -> list[tuple[Any, ...]]:
    with conn.cursor() as cursor:
        cursor.execute(sql, params)
        return list(cursor.fetchall())


def _sha(text: str | None) -> str | None:
    return None if text is None else hashlib.sha256(text.encode("utf-8")).hexdigest()


def _summary(value: Any) -> Any:
    """A missing or extra item, shown compactly: a function's text gives way to its digest."""

    if isinstance(value, dict) and "definition" in value:
        return {key: item for key, item in value.items() if key != "definition"}
    return value
