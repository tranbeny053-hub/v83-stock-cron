"""Scratch rehearsal of the structure-first restore proof (no secret, no real database).

    python scripts/restore_proof/rehearse.py --pg-bin <PostgreSQL 17.6 bin> --work <fresh folder> \\
        --report <report.json>

It stands in for production with scratch clusters built from the migrations exactly as the
reference is, under Supabase's names (bootstrap superuser supabase_admin, the migrations run by a
non-superuser postgres). Against each, it runs the export card's two commands, as postgres, and
then the proof (prove.py), with the export's own digests as the owner's. Each case states its
expected verdict, differences, refusals and restore errors, and passes only when they are exactly
what it sees:
- the clean export PASSES with no difference: what was exported is what the migrations declare;
- drift fails as app differences, each at its own path: a revoked or an extra table grant, one made
  by a role other than the owner, a column grant, a schema grant, a seal trigger disabled or
  dropped, a seal function's body changed, a column added, a CHECK constraint dropped (the
  probability simplex), row security off or forced, a policy dropped, widened to another role or
  given another condition, an index dropped, an extra EXECUTE grant, the default privileges of the
  owner or of a migration role changed;
- so does every privilege path into the app: a migration role's attribute, membership or setting
  changed, a predefined role or the superuser granted to an API role, an API role gaining
  BYPASSRLS, a setting on PostgREST's login role that turns the seals off, a role holding the
  owner or an API role, a role holding a predefined role that reads every table, a new superuser,
  a parameter grant to a migration role;
- the owner's documented credential steps (LOGIN on ucpe_space_db and ucpe_resolver) are reported
  as operational; a platform role's default privileges, its own BYPASSRLS, settings and membership
  in another predefined role, LOGIN and a timeout on PostgREST's login role, as platform; none of
  them fails; a setting's value never appears in the report or the work folder; and a role's
  comment, which pg_dumpall writes, passes the gate;
- a restore error on a platform role's own setting, or an API role's timeout, is platform; on a
  migration role's setting or an API role's other setting, it fails, and the refused value is not
  shown;
- the gate refuses, and nothing is restored from: an export with data (no --schema-only), a roles
  export with password verifiers (no --no-role-passwords, whose verifier never appears in the
  report), a psql meta-command (which never runs), a missing \\restrict, an export that would
  take superuser from the bootstrap role, and an escape string pg_dumpall does not write;
- Supabase's own statements for the eight differences the owner ruled exact managed-platform
  exceptions (owner ruling DP-D-FINDINGS, catalog.PLATFORM_EXCEPTIONS) PASS with each accepted at
  its path and nothing else; next to them, the same membership with other options, a look-alike
  role, another predefined role for the same role, an extra setting beside the ruled ones, the
  ruled settings on another API role, the owner's grants with grant option and CREATE on the
  schema all fail as app; so does what a ruled membership reaches: a role holding a ruled role,
  and a setting or parameter grant that turns the seals off on Storage's role, which the ruled
  membership lets act as an API role; and a setting the restore refuses on it fails;
- a role's comments and settings that pg_dumpall writes as escape strings (owner ruling
  DP-D-ESCAPE=A) PASS, and escape_string_differential holds psql 17 itself against the gate on a
  seeded corpus of them (pg_dumpall writes them, the gate passes them, psql restores every value
  unchanged, runs exactly the gate's meta-commands and sends the server exactly the gate's
  statements), while every other escape string is refused.
Every server it makes listens on a private socket only and is deleted at the end.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import secrets
import shutil
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import psycopg
from psycopg import sql as pgsql

if __package__ in {None, ""}:  # run as a script: make the repository root importable
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.restore_proof import catalog, gate, prove, scratch  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
APP_DATABASE = "ucpe"
OWNER = scratch.MIGRATION_OWNER
SUPER = scratch.BOOTSTRAP_SUPERUSER
BUNDLE = (
    "save_prediction_bundle(p_prediction jsonb, p_feature_snapshot jsonb, "
    "p_derivatives_snapshot jsonb)"
)
# The export card's two commands (docs/runbooks/RESTORE_PROOF_EXPORT.md), less their connection.
SCHEMA_EXPORT = ("pg_dump", "--schema-only", "--schema=public")
ROLES_EXPORT = ("pg_dumpall", "--roles-only", "--no-role-passwords")
# A setting value the restore refuses: it must never be shown, in the report or the work folder.
REFUSED_VALUE = "rehearsal-refused-value"


@dataclass(frozen=True)
class Case:
    name: str
    verdict: str
    differences: frozenset[tuple[str, str]] = frozenset()
    refusals: frozenset[str] = frozenset()
    errors: frozenset[str] = frozenset()  # categories of restore errors beyond the two expected
    # (role, SQL) in this case's database; with cluster_sql, in its own cluster's app database
    database_sql: tuple[tuple[str, str], ...] = ()
    cluster_sql: tuple[str, ...] = ()  # as the superuser, on a fresh cluster of its own
    edit: Callable[[Path], None] | None = None  # applied to the export after the card's commands
    with_data: bool = False
    with_passwords: bool = False
    wrong_digest: bool = False
    checks: tuple[str, ...] = field(default=())


def _app(*paths: str) -> frozenset[tuple[str, str]]:
    return frozenset(("app", path) for path in paths)


# Supabase's own statements for the eight differences the owner ruled exact managed-platform
# exceptions (DP-D-FINDINGS): its initial schema and migrations (github.com/supabase/postgres,
# migrations/, branch develop; catalog.PLATFORM_EXCEPTIONS cites each file), as Supabase runs them.
SUPABASE_ROLES = (
    "CREATE ROLE supabase_storage_admin NOINHERIT CREATEROLE LOGIN",
    "GRANT authenticator TO supabase_storage_admin",
    "CREATE ROLE supabase_etl_admin LOGIN REPLICATION BYPASSRLS",
    "GRANT pg_read_all_data TO supabase_etl_admin",
    "CREATE ROLE supabase_read_only_user LOGIN BYPASSRLS",
    "GRANT pg_read_all_data TO supabase_read_only_user",
)
SUPABASE_AUTHENTICATOR_SETTINGS = (
    "ALTER ROLE authenticator SET statement_timeout TO '8s'",
    "ALTER ROLE authenticator SET lock_timeout TO '8s'",
    "ALTER ROLE authenticator SET session_preload_libraries TO supautils, safeupdate",
)
SUPABASE_OWNER_GRANTS = (  # run as the owner, as Supabase's initial schema is
    (OWNER, f'ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO "{OWNER}"'),
    (OWNER, f'ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON FUNCTIONS TO "{OWNER}"'),
    (OWNER, f'ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO "{OWNER}"'),
    (OWNER, f'GRANT USAGE ON SCHEMA public TO "{OWNER}"'),
)
ACCEPTED = frozenset(("accepted", exception.path) for exception in catalog.PLATFORM_EXCEPTIONS)
SUPABASE_ROLE_ATTRIBUTES = frozenset(
    ("platform", f"cluster/attributes/{role}")
    for role in ("supabase_storage_admin", "supabase_etl_admin", "supabase_read_only_user")
)


def _append_role_line(line: str) -> Callable[[Path], None]:
    def edit(export: Path) -> None:
        roles = export / "roles.sql"
        lines = roles.read_text(encoding="utf-8").split("\n")
        closing = max(i for i, item in enumerate(lines) if item.startswith("\\unrestrict "))
        lines.insert(closing, line)
        roles.write_text("\n".join(lines), encoding="utf-8")

    return edit


def _meta_command(export: Path) -> None:
    schema = export / "schema.sql"
    lines = schema.read_text(encoding="utf-8").split("\n")
    opening = next(i for i, item in enumerate(lines) if item.startswith("\\restrict "))
    lines.insert(opening + 1, f"\\! touch {export / 'META_COMMAND_RAN'}")
    schema.write_text("\n".join(lines), encoding="utf-8")


def _drop_restrict(export: Path) -> None:
    schema = export / "schema.sql"
    lines = schema.read_text(encoding="utf-8").split("\n")
    schema.write_text(
        "\n".join(item for item in lines if not item.startswith("\\restrict ")), encoding="utf-8"
    )


def _carriage_return(export: Path) -> None:
    # A bare CR mid-line: psql would end the line here, the gate refuses it (CARRIAGE_RETURN).
    schema = export / "schema.sql"
    lines = schema.read_text(encoding="utf-8").split("\n")
    opening = next(i for i, item in enumerate(lines) if item.startswith("\\restrict "))
    lines.insert(opening + 1, "SET\rstatement_timeout = 0;")
    schema.write_text("\n".join(lines), encoding="utf-8")


def _demote_bootstrap(export: Path) -> None:
    roles = export / "roles.sql"
    text = roles.read_text(encoding="utf-8")
    roles.write_text(
        text.replace(f"ALTER ROLE {SUPER} WITH SUPERUSER", f"ALTER ROLE {SUPER} WITH NOSUPERUSER"),
        encoding="utf-8",
    )


CASES: tuple[Case, ...] = (
    Case("clean export", "PASS"),
    Case(
        "a revoked table grant",
        "FAIL",
        _app("relations/predictions/acl"),
        database_sql=((SUPER, "REVOKE SELECT ON public.predictions FROM ucpe_space_db"),),
    ),
    Case(
        "an extra table grant",
        "FAIL",
        _app("relations/predictions/acl"),
        database_sql=((SUPER, "GRANT INSERT ON public.predictions TO anon"),),
    ),
    Case(
        "a seal trigger disabled",
        "FAIL",
        _app("triggers/predictions/trg_pred_reject_update"),
        database_sql=(
            (SUPER, "ALTER TABLE public.predictions DISABLE TRIGGER trg_pred_reject_update"),
        ),
    ),
    Case(
        "a seal trigger dropped",
        "FAIL",
        _app("triggers/predictions/trg_pred_reject_delete"),
        database_sql=((SUPER, "DROP TRIGGER trg_pred_reject_delete ON public.predictions"),),
    ),
    Case(
        "a seal function's body changed",
        "FAIL",
        _app("functions/reject_core_evidence_mutation()/definition_sha256"),
        database_sql=(
            (
                OWNER,
                "CREATE OR REPLACE FUNCTION public.reject_core_evidence_mutation() "
                "RETURNS trigger LANGUAGE plpgsql SET search_path TO 'pg_catalog', 'pg_temp' "
                "AS $$ BEGIN RETURN NEW; END; $$",
            ),
        ),
    ),
    Case(
        "a column added",
        "FAIL",
        _app("columns/predictions/order", "columns/predictions/by_name/rehearsal_extra"),
        database_sql=((OWNER, "ALTER TABLE public.predictions ADD COLUMN rehearsal_extra text"),),
    ),
    Case(
        "row security disabled",
        "FAIL",
        _app("relations/predictions/row_security"),
        database_sql=((OWNER, "ALTER TABLE public.predictions DISABLE ROW LEVEL SECURITY"),),
    ),
    Case(
        "a policy dropped",
        "FAIL",
        _app("policies/predictions/ucpe_space_db_select"),
        database_sql=((OWNER, "DROP POLICY ucpe_space_db_select ON public.predictions"),),
    ),
    Case(
        "an index dropped",
        "FAIL",
        _app("indexes/predictions/idx_predictions_horizon_end"),
        database_sql=((OWNER, "DROP INDEX public.idx_predictions_horizon_end"),),
    ),
    Case(
        "an extra EXECUTE grant",
        "FAIL",
        _app(f"functions/{BUNDLE}/acl"),
        database_sql=((SUPER, f"GRANT EXECUTE ON FUNCTION public.{BUNDLE} TO anon"),),
    ),
    Case(
        "the owner's default privileges changed",
        "FAIL",
        _app("default_privileges/<owner> r"),
        database_sql=(
            (
                SUPER,
                f"ALTER DEFAULT PRIVILEGES FOR ROLE {OWNER} IN SCHEMA public "
                "REVOKE ALL ON TABLES FROM anon",
            ),
        ),
    ),
    Case(
        "a migration role's default privileges",
        "FAIL",
        _app("default_privileges/ucpe_bundle_owner f"),
        database_sql=(
            (
                SUPER,
                "ALTER DEFAULT PRIVILEGES FOR ROLE ucpe_bundle_owner IN SCHEMA public "
                "GRANT EXECUTE ON FUNCTIONS TO anon",
            ),
        ),
    ),
    Case(
        "a grant made by a role other than the owner",
        "FAIL",
        _app("relations/predictions/acl"),
        database_sql=(
            (SUPER, "GRANT SELECT ON public.predictions TO ucpe_resolver WITH GRANT OPTION"),
            (SUPER, "SET ROLE ucpe_resolver; GRANT SELECT ON public.predictions TO anon"),
        ),
    ),
    Case(
        "a platform role's default privileges",
        "PASS",
        frozenset({("platform", f"default_privileges/{SUPER} r")}),
        database_sql=(
            (
                SUPER,
                f"ALTER DEFAULT PRIVILEGES FOR ROLE {SUPER} IN SCHEMA public "
                "GRANT SELECT ON TABLES TO anon",
            ),
        ),
    ),
    Case(
        "a column grant",
        "FAIL",
        _app("column_acl/predictions.symbol"),
        database_sql=((SUPER, "GRANT SELECT (symbol) ON public.predictions TO anon"),),
    ),
    Case(
        "a schema grant",
        "FAIL",
        _app("schema/acl"),
        database_sql=((SUPER, "GRANT CREATE ON SCHEMA public TO anon"),),
    ),
    Case(
        "the probability simplex constraint dropped",
        "FAIL",
        _app("constraints/predictions/predictions_probability_simplex_chk"),
        database_sql=(
            (
                OWNER,
                "ALTER TABLE public.predictions "
                "DROP CONSTRAINT predictions_probability_simplex_chk",
            ),
        ),
    ),
    Case(
        "row security forced",
        "FAIL",
        _app("relations/predictions/force_row_security"),
        database_sql=((OWNER, "ALTER TABLE public.predictions FORCE ROW LEVEL SECURITY"),),
    ),
    Case(
        "a policy widened to another role",
        "FAIL",
        _app("policies/predictions/ucpe_space_db_select/roles"),
        database_sql=(
            (
                OWNER,
                "ALTER POLICY ucpe_space_db_select ON public.predictions TO ucpe_space_db, anon",
            ),
        ),
    ),
    Case(
        "a policy given another condition",
        "FAIL",
        _app("policies/predictions/ucpe_space_db_select/using"),
        database_sql=(
            (OWNER, "ALTER POLICY ucpe_space_db_select ON public.predictions USING (false)"),
        ),
    ),
    Case(
        "a platform role's setting the restore refuses",
        "PASS",
        errors=frozenset({"platform"}),
        edit=_append_role_line(f"ALTER ROLE anon SET statement_timeout TO '{REFUSED_VALUE}';"),
        checks=("setting_value_never_reported",),
    ),
    Case(
        "a migration role's setting the restore refuses",
        "FAIL",
        errors=frozenset({"fail"}),
        edit=_append_role_line(
            f"ALTER ROLE ucpe_api_writer SET statement_timeout TO '{REFUSED_VALUE}';"
        ),
        checks=("setting_value_never_reported",),
    ),
    Case(
        "an API role's other setting the restore refuses",
        "FAIL",
        errors=frozenset({"fail"}),
        edit=_append_role_line(
            f"ALTER ROLE authenticator SET session_replication_role TO '{REFUSED_VALUE}';"
        ),
        checks=("setting_value_never_reported",),
    ),
    Case(
        "a psql meta-command",
        "REFUSED_EXPORT",
        refusals=frozenset({"META_COMMAND"}),
        edit=_meta_command,
        checks=("meta_command_never_ran",),
    ),
    Case(
        "a bare carriage return in the export",
        "REFUSED_EXPORT",
        refusals=frozenset({"CARRIAGE_RETURN"}),
        edit=_carriage_return,
    ),
    Case(
        "no \\restrict",
        "REFUSED_EXPORT",
        refusals=frozenset({"RESTRICT_PAIR_MISSING"}),
        edit=_drop_restrict,
    ),
    Case(
        "the bootstrap superuser demoted",
        "REFUSED_EXPORT",
        refusals=frozenset({"BOOTSTRAP_SUPERUSER_NOT_KEPT"}),
        edit=_demote_bootstrap,
    ),
    Case(
        "an export with data",
        "REFUSED_EXPORT",
        refusals=frozenset({"DATA_ENTRY"}),
        with_data=True,
    ),
    Case(
        "a file that is not the one the owner exported",
        "REFUSED_EXPORT",
        refusals=frozenset({"DIGEST_MISMATCH"}),
        wrong_digest=True,
    ),
    Case(
        "a migration role's attribute",
        "FAIL",
        _app("cluster/attributes/ucpe_api_writer/rolbypassrls"),
        cluster_sql=("ALTER ROLE ucpe_api_writer BYPASSRLS",),
    ),
    Case(
        "a migration role's membership",
        "FAIL",
        _app(
            "cluster/memberships/service_role to ucpe_space_db admin=False inherit=False set=True"
        ),
        cluster_sql=("GRANT service_role TO ucpe_space_db",),
    ),
    Case(
        "a migration role's setting",
        "FAIL",
        _app("cluster/settings/ucpe_api_writer in all databases"),
        cluster_sql=("ALTER ROLE ucpe_api_writer SET statement_timeout TO '5s'",),
    ),
    Case(
        "an API role gaining BYPASSRLS",
        "FAIL",
        _app("cluster/attributes/anon/rolbypassrls"),
        cluster_sql=("ALTER ROLE anon BYPASSRLS",),
    ),
    Case(
        "a predefined role granted to an API role",
        "FAIL",
        _app("cluster/memberships/pg_read_all_data to anon admin=False inherit=True set=True"),
        cluster_sql=("GRANT pg_read_all_data TO anon WITH INHERIT TRUE",),
    ),
    Case(
        "the superuser granted to PostgREST's login role",
        "FAIL",
        _app(f"cluster/memberships/{SUPER} to authenticator admin=False inherit=False set=True"),
        cluster_sql=(f"GRANT {SUPER} TO authenticator",),
    ),
    Case(
        "a setting on PostgREST's login role that turns the seals off",
        "FAIL",
        _app("cluster/settings/authenticator in all databases"),
        cluster_sql=("ALTER ROLE authenticator SET session_replication_role TO replica",),
    ),
    Case(
        "a role holding the owner",
        "FAIL",
        frozenset(
            {
                ("platform", "cluster/attributes/rehearsal_holder"),
                (
                    "app",
                    "cluster/memberships/<owner> to rehearsal_holder admin=False inherit=True "
                    "set=True",
                ),
            }
        ),
        cluster_sql=(
            "CREATE ROLE rehearsal_holder LOGIN",
            f"GRANT {OWNER} TO rehearsal_holder WITH INHERIT TRUE",
        ),
    ),
    Case(
        "a platform role able to act as an API role",
        "FAIL",
        frozenset(
            {
                ("platform", "cluster/attributes/rehearsal_storage"),
                (
                    "app",
                    "cluster/memberships/service_role to rehearsal_storage admin=False "
                    "inherit=False set=True",
                ),
            }
        ),
        cluster_sql=(
            "CREATE ROLE rehearsal_storage NOINHERIT LOGIN",
            "GRANT service_role TO rehearsal_storage",
        ),
    ),
    Case(
        "a role that reads every table",
        "FAIL",
        frozenset(
            {
                ("platform", "cluster/attributes/rehearsal_reader"),
                (
                    "app",
                    "cluster/memberships/pg_read_all_data to rehearsal_reader admin=False "
                    "inherit=True set=True",
                ),
            }
        ),
        cluster_sql=(
            "CREATE ROLE rehearsal_reader LOGIN",
            "GRANT pg_read_all_data TO rehearsal_reader",
        ),
    ),
    Case(
        "a new superuser",
        "FAIL",
        _app("cluster/attributes/rehearsal_super"),
        cluster_sql=("CREATE ROLE rehearsal_super SUPERUSER",),
    ),
    Case(
        "a parameter grant to a migration role",
        "FAIL",
        _app("cluster/parameter_acl/session_replication_role"),
        cluster_sql=("GRANT SET ON PARAMETER session_replication_role TO ucpe_api_writer",),
    ),
    Case(
        "a parameter grant to PUBLIC",
        "FAIL",
        _app("cluster/parameter_acl/session_replication_role"),
        cluster_sql=("GRANT SET ON PARAMETER session_replication_role TO PUBLIC",),
    ),
    Case(
        "the bootstrap superuser granted to a plain role",
        "FAIL",
        frozenset(
            {
                ("platform", "cluster/attributes/rehearsal_grantee"),
                (
                    "app",
                    f"cluster/memberships/{SUPER} to rehearsal_grantee admin=False "
                    "inherit=True set=True",
                ),
            }
        ),
        cluster_sql=(
            "CREATE ROLE rehearsal_grantee NOINHERIT LOGIN",
            f"GRANT {SUPER} TO rehearsal_grantee WITH INHERIT TRUE",
        ),
    ),
    Case(
        "the platform's own roles, settings and memberships",
        "PASS",
        frozenset(
            {
                ("platform", "cluster/attributes/authenticator/rolcanlogin"),
                ("platform", "cluster/settings/authenticator in all databases"),
                ("platform", "cluster/attributes/rehearsal_platform"),
                ("platform", "cluster/settings/rehearsal_platform in all databases"),
                (
                    "platform",
                    "cluster/memberships/pg_monitor to rehearsal_platform admin=False "
                    "inherit=False set=True",
                ),
            }
        ),
        cluster_sql=(
            "ALTER ROLE authenticator LOGIN",
            "ALTER ROLE authenticator SET statement_timeout TO '8s'",
            "CREATE ROLE rehearsal_platform NOINHERIT LOGIN BYPASSRLS",
            "GRANT pg_monitor TO rehearsal_platform",
            "ALTER ROLE rehearsal_platform SET app.rehearsal_value TO '{scratch_value}'",
        ),
        checks=("setting_value_never_reported",),
    ),
    Case(
        "Supabase's own grants the owner ruled exact platform exceptions",
        "PASS",
        ACCEPTED | SUPABASE_ROLE_ATTRIBUTES,
        cluster_sql=(*SUPABASE_ROLES, *SUPABASE_AUTHENTICATOR_SETTINGS),
        database_sql=SUPABASE_OWNER_GRANTS,
    ),
    Case(
        "beside the ruled grants, a role holding a ruled role and Storage's role turning seals off",
        "FAIL",
        ACCEPTED
        | SUPABASE_ROLE_ATTRIBUTES
        | {("platform", "cluster/attributes/rehearsal_reach")}
        | _app(
            "cluster/memberships/supabase_read_only_user to rehearsal_reach admin=False "
            "inherit=True set=True",
            "cluster/settings/supabase_storage_admin in all databases",
            "cluster/parameter_acl/session_replication_role",
        ),
        cluster_sql=(
            *SUPABASE_ROLES,
            *SUPABASE_AUTHENTICATOR_SETTINGS,
            "CREATE ROLE rehearsal_reach LOGIN",
            "GRANT supabase_read_only_user TO rehearsal_reach",
            "ALTER ROLE supabase_storage_admin SET session_replication_role TO replica",
            "GRANT SET ON PARAMETER session_replication_role TO supabase_storage_admin",
        ),
        database_sql=SUPABASE_OWNER_GRANTS,
    ),
    Case(
        "a setting the restore refuses on Storage's role, which may act as an API role",
        "FAIL",
        SUPABASE_ROLE_ATTRIBUTES
        | {item for item in ACCEPTED if item[1].startswith("cluster/memberships/")},
        errors=frozenset({"fail"}),
        cluster_sql=SUPABASE_ROLES,
        edit=_append_role_line(
            f"ALTER ROLE supabase_storage_admin SET session_replication_role TO '{REFUSED_VALUE}';"
        ),
        checks=("setting_value_never_reported",),
    ),
    Case(
        "near the ruled memberships: other options, a look-alike role, another predefined role",
        "FAIL",
        frozenset(
            {
                *(
                    ("platform", f"cluster/attributes/{role}")
                    for role in (
                        "supabase_storage_admin",
                        "supabase_etl_admin",
                        "supabase_read_only_user",
                        "supabase_read_only_usr",
                    )
                ),
                (
                    "app",
                    "cluster/memberships/authenticator to supabase_storage_admin admin=False "
                    "inherit=True set=True",
                ),
                (
                    "app",
                    "cluster/memberships/pg_read_all_data to supabase_etl_admin admin=True "
                    "inherit=True set=True",
                ),
                (
                    "accepted",
                    "cluster/memberships/pg_read_all_data to supabase_read_only_user admin=False "
                    "inherit=True set=True",
                ),
                (
                    "app",
                    "cluster/memberships/pg_write_all_data to supabase_read_only_user admin=False "
                    "inherit=True set=True",
                ),
                (
                    "app",
                    "cluster/memberships/pg_read_all_data to supabase_read_only_usr admin=False "
                    "inherit=True set=True",
                ),
            }
        ),
        cluster_sql=(
            "CREATE ROLE supabase_storage_admin CREATEROLE LOGIN",  # INHERIT: so is its grant
            "GRANT authenticator TO supabase_storage_admin",
            "CREATE ROLE supabase_etl_admin LOGIN REPLICATION BYPASSRLS",
            "GRANT pg_read_all_data TO supabase_etl_admin WITH ADMIN OPTION",
            "CREATE ROLE supabase_read_only_user LOGIN BYPASSRLS",
            "GRANT pg_read_all_data TO supabase_read_only_user",
            "GRANT pg_write_all_data TO supabase_read_only_user",
            "CREATE ROLE supabase_read_only_usr LOGIN BYPASSRLS",
            "GRANT pg_read_all_data TO supabase_read_only_usr",
        ),
    ),
    Case(
        "near the ruled settings: one more beside them, or them on another API role",
        "FAIL",
        _app(
            "cluster/settings/authenticator in all databases",
            "cluster/settings/anon in all databases",
        ),
        cluster_sql=(
            *SUPABASE_AUTHENTICATOR_SETTINGS,
            "ALTER ROLE authenticator SET session_replication_role TO replica",
            *(
                sql.replace("ROLE authenticator", "ROLE anon")
                for sql in SUPABASE_AUTHENTICATOR_SETTINGS
            ),
        ),
    ),
    Case(
        "near the owner's ruled grants: with grant option, and CREATE on the schema",
        "FAIL",
        _app("default_privileges/<owner> r", "schema/acl"),
        database_sql=(
            (
                OWNER,
                "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
                f'GRANT ALL ON TABLES TO "{OWNER}" WITH GRANT OPTION',
            ),
            (OWNER, f'GRANT USAGE, CREATE ON SCHEMA public TO "{OWNER}"'),
        ),
    ),
    Case(
        "a role's comment",
        "PASS",
        cluster_sql=("COMMENT ON ROLE anon IS 'a rehearsal comment'",),
    ),
    Case(
        "a role's comments and settings that pg_dumpall writes as escape strings",
        "PASS",
        frozenset(
            {
                ("platform", "cluster/attributes/rehearsal_escape"),
                ("platform", "cluster/settings/rehearsal_escape in all databases"),
            }
        ),
        cluster_sql=(
            r"COMMENT ON ROLE anon IS E'C:\\path ''q'' \\\\ end'",
            r"COMMENT ON ROLE authenticated IS E'line1\nline2 \\ tab\t;\\! x --y /*z :v $$'",
            "CREATE ROLE rehearsal_escape NOLOGIN",
            r"ALTER ROLE rehearsal_escape SET application_name TO 'a\b'",
            r"ALTER ROLE rehearsal_escape SET search_path TO 'a\b', public",
        ),
    ),
    Case(
        "an escape string pg_dumpall does not write",
        "REFUSED_EXPORT",
        # psql ends nothing at the escaped quote, so the scan, reading on as a standard string,
        # takes the closing \unrestrict into a literal too: both refusals stand.
        refusals=frozenset({"ESCAPE_STRING", "RESTRICT_PAIR_MISSING"}),
        edit=_append_role_line(r"COMMENT ON ROLE anon IS E'it\'s';"),
    ),
    Case(
        "the owner's documented credential steps",
        "PASS",
        frozenset(
            {
                ("operational", "cluster/attributes/ucpe_space_db/rolcanlogin"),
                ("operational", "cluster/attributes/ucpe_resolver/rolcanlogin"),
            }
        ),
        cluster_sql=("ALTER ROLE ucpe_space_db LOGIN", "ALTER ROLE ucpe_resolver LOGIN"),
    ),
    Case(
        "a roles export with password verifiers",
        "REFUSED_EXPORT",
        refusals=frozenset({"PASSWORD_CLAUSE"}),
        cluster_sql=("ALTER ROLE ucpe_resolver LOGIN PASSWORD '{scratch_value}'",),
        with_passwords=True,
        checks=("password_never_reported",),
    ),
)


def export_with_the_card(
    cluster: scratch.Cluster,
    database: str,
    export: Path,
    *,
    with_data: bool = False,
    with_passwords: bool = False,
) -> None:
    """The card's two commands, run as the owner against a scratch stand-in for production."""

    export.mkdir(parents=True)
    schema = [str(cluster.bin / SCHEMA_EXPORT[0]), *SCHEMA_EXPORT[1:]]
    if with_data:
        schema.remove("--schema-only")
    roles = [str(cluster.bin / ROLES_EXPORT[0]), *ROLES_EXPORT[1:]]
    if with_passwords:
        # A password verifier is readable by a superuser only: the deliberate mistake under test.
        roles.remove("--no-role-passwords")
    runs = (
        # Data past forced row security is readable by a superuser only: the deliberate mistake.
        (schema, export / "schema.sql", cluster.url(database, SUPER if with_data else OWNER)),
        (roles, export / "roles.sql", cluster.url("postgres", SUPER if with_passwords else OWNER)),
    )
    for command, target, url in runs:
        subprocess.run(  # noqa: S603
            [*command, f"--file={target}", f"--dbname={url}"],
            capture_output=True,
            text=True,
            timeout=300,
            check=True,
        )


# Owner ruling DP-D-ESCAPE=A: pieces of a role's comment or setting that would end or escape a
# literal, or open a comment, a dollar quote, a variable or a meta-command, were the literal lexed
# otherwise than the gate lexes it. Every corpus value holds a backslash, so pg_dumpall writes each
# as an escape string; the corpus is seeded, so every run (CI's included) sees the same one.
_PIECES = (
    "a",
    "Z",
    " ",
    "\t",
    "\n",
    ";",
    "\\",
    "\\\\",
    "'",
    "''",
    '"',
    "--",
    "/*",
    "*/",
    "$$",
    "$q$",
    ":v",
    ":'v'",
    "\\echo rehearsal-leaked",
    "\\!",
    "E'",
    "\u00e9",
    "\u2713",
)
ESCAPE_CORPUS_SIZE = 48
ESCAPE_CORPUS_SEED = 20261007
_MARK = "rehearsal-mark-"
_HIDDEN = "rehearsal-hidden"
# Escape strings pg_dumpall does not write; the last one hides a meta-command psql would run.
_OTHER_ESCAPE_STRINGS = (
    r"COMMENT ON ROLE anon IS E'it\'s';",
    r"COMMENT ON ROLE anon IS E'a\nb';",
    r"COMMENT ON ROLE anon IS e'a\\b';",
    "ALTER ROLE anon SET application_name TO E'a'\n'b';",
    "COMMENT ON ROLE anon IS E'\\'' \\echo " + _HIDDEN + "\n';",
)
_LOG_ENTRY = re.compile(r"^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d")
_LOGGED_STATEMENT = re.compile(r"^\S+ \S+ \S+ \[\d+\] LOG:  statement: (.*)$")


def escape_corpus(size: int = ESCAPE_CORPUS_SIZE, seed: int = ESCAPE_CORPUS_SEED) -> list[str]:
    rng = random.Random(seed)  # noqa: S311 - a fixed test corpus, not a secret
    values: list[str] = []
    while len(values) < size:
        value = "".join(rng.choice(_PIECES) for _ in range(rng.randint(1, 10)))
        if "\\" in value[:40]:
            values.append(value)
    return values


def escape_string_differential(pg_bin: Path, work: Path) -> dict[str, Any]:
    """psql 17 itself against the gate, on the escape strings pg_dumpall writes (owner ruling
    DP-D-ESCAPE=A). The corpus values become role comments and settings (one a list setting) on a
    scratch cluster, and pg_dumpall writes them as the card does. Then:
    - the gate passes that export, every escape string in it lexed as pg_dumpall's own form;
    - psql restores it into a second cluster, where every comment and setting reads back the same;
    - with the \\restrict pair taken out (so psql would run any meta-command it saw) and a \\echo
      marker before each statement the gate sees, psql runs exactly the gate's meta-commands (every
      marker, and none of the backslash text inside a literal) and sends the server exactly the
      gate's statements (the server's statement log), in the same order;
    - every escape string pg_dumpall does not write is refused, and psql would run the
      meta-command hidden in one of them, which is why each is refused."""

    work.mkdir(parents=True)
    values = escape_corpus()
    dump = work / "roles.sql"
    source = scratch.start(pg_bin, work, "escape-source", superuser=SUPER)
    try:
        with psycopg.connect(source.url("postgres"), autocommit=True) as conn:
            for index, value in enumerate(values):
                role = pgsql.Identifier(f"escape_{index:02d}")
                literal = pgsql.Literal(value)
                conn.execute(pgsql.SQL("CREATE ROLE {} NOLOGIN").format(role))
                conn.execute(pgsql.SQL("COMMENT ON ROLE {} IS {}").format(role, literal))
                conn.execute(
                    pgsql.SQL("ALTER ROLE {} SET rehearsal.value TO {}").format(role, literal)
                )
                conn.execute(
                    pgsql.SQL("ALTER ROLE {} SET search_path TO {}, public").format(
                        role, pgsql.Literal(value[:40])
                    )
                )
            expected = _escape_role_values(conn)
        subprocess.run(  # noqa: S603
            [
                str(pg_bin / ROLES_EXPORT[0]),
                *ROLES_EXPORT[1:],
                f"--file={dump}",
                f"--dbname={source.url('postgres')}",
            ],
            capture_output=True,
            text=True,
            timeout=300,
            check=True,
        )
    finally:
        scratch.stop(source)
    text = dump.read_text(encoding="utf-8")
    refusals = gate.check_roles_dump("roles.sql", dump.read_bytes())[1]
    found: list[tuple[int, int, str]] = []
    statements = gate.scan(text, escape_strings=found)[0]

    restored = scratch.start(pg_bin, work, "escape-restored", superuser=SUPER)
    try:
        restored.psql(file=dump, stop_on_error=False)
        with psycopg.connect(restored.url("postgres"), autocommit=True) as conn:
            actual = _escape_role_values(conn)
    finally:
        scratch.stop(restored)

    starts = {line for line, _ in statements}
    marked: list[str] = []
    markers: list[str] = []
    for number, item in enumerate(text.split("\n"), start=1):
        if item.startswith(("\\restrict ", "\\unrestrict ")):
            continue
        if number in starts:
            markers.append(f"{_MARK}{len(markers)}")
            marked.append(f"\\echo {markers[-1]}")
        marked.append(item)
    script = work / "marked.sql"
    script.write_text("\n".join(marked), encoding="utf-8")
    script_statements, script_metas, script_hazards = gate.scan(
        script.read_text(encoding="utf-8"), escape_strings=[]
    )
    gate_markers = [argument for _, command, argument in script_metas if command == "echo"]
    hidden = work / "hidden.sql"
    hidden.write_text(_OTHER_ESCAPE_STRINGS[-1] + "\n", encoding="utf-8")
    lexed = scratch.start(pg_bin, work, "escape-lexed", superuser=SUPER)
    try:
        lexed.psql(command=f"ALTER ROLE {SUPER} SET log_statement = 'all'")
        run = lexed.psql(file=script, stop_on_error=False)
        log = lexed.log.read_text(encoding="utf-8", errors="replace")
        hidden_run = lexed.psql(file=hidden, stop_on_error=False)
    finally:
        scratch.stop(lexed)
    printed = run.stdout.splitlines()
    psql_markers = [line for line in printed if line.startswith(_MARK)]
    psql_leads = [_lead(statement) for statement in _logged_statements(log)]
    gate_leads = [lead for _, lead in script_statements]
    other_refused = sum(
        "ESCAPE_STRING" in {item.kind for item in gate.check_roles_dump("roles.sql", raw)[1]}
        for raw in (_roles_file(statement) for statement in _OTHER_ESCAPE_STRINGS)
    )
    result = {
        "values": len(values),
        "escape_strings_passed": len(found),
        "gate_refusals": sorted({item.kind for item in refusals}),
        "round_trip_equal": actual == expected and len(actual) == len(values),
        "markers": {"gate": len(gate_markers), "psql": len(psql_markers)},
        "markers_equal": markers == gate_markers == psql_markers,
        "backslash_text_run": sum("rehearsal-leaked" in line for line in printed),
        "statements": {"gate": len(gate_leads), "psql": len(psql_leads)},
        "statements_equal": gate_leads == psql_leads,
        "other_forms_refused": f"{other_refused}/{len(_OTHER_ESCAPE_STRINGS)}",
        "psql_runs_the_hidden_meta_command": any(
            line.startswith(_HIDDEN) for line in hidden_run.stdout.splitlines()
        ),
    }
    result["passed"] = (
        result["gate_refusals"] == []
        and script_hazards == []
        and len(found) >= len(values)
        and result["round_trip_equal"]
        and result["markers_equal"]
        and result["backslash_text_run"] == 0
        and result["statements_equal"]
        and other_refused == len(_OTHER_ESCAPE_STRINGS)
        and result["psql_runs_the_hidden_meta_command"]
    )
    return result


def _escape_role_values(conn: psycopg.Connection) -> dict[str, tuple[Any, ...]]:
    rows = conn.execute(
        "SELECT r.rolname, pg_catalog.shobj_description(r.oid, 'pg_authid'), s.setconfig "
        "FROM pg_catalog.pg_roles r LEFT JOIN pg_catalog.pg_db_role_setting s "
        "ON s.setrole = r.oid AND s.setdatabase = 0 "
        "WHERE r.rolname LIKE 'escape\\_%' ORDER BY 1"
    ).fetchall()
    return {row[0]: tuple(row[1:]) for row in rows}


def _logged_statements(log: str) -> list[str]:
    """The statements the server received, in order, from its log (log_statement = all)."""

    statements: list[str] = []
    current: list[str] | None = None
    for line in log.split("\n"):
        if _LOG_ENTRY.match(line):
            if current is not None:
                statements.append("\n".join(current))
            match = _LOGGED_STATEMENT.match(line)
            current = [match.group(1)] if match else None
        elif current is not None:
            current.append(line)
    if current is not None:
        statements.append("\n".join(current))
    return statements


def _lead(statement: str) -> tuple[str, ...]:
    found = gate.scan(statement, escape_strings=[])[0]
    return found[0][1] if found else ()


def _roles_file(statement: str) -> bytes:
    return (
        "--\n-- PostgreSQL database cluster dump\n--\n\n\\restrict K\n\n"
        f"{statement}\n\n\\unrestrict K\n"
    ).encode()


def rehearse(pg_bin: Path, work: Path) -> dict[str, Any]:
    with scratch.clean_pg_environment():
        return _rehearse(pg_bin, work)


def _rehearse(pg_bin: Path, work: Path) -> dict[str, Any]:
    work.mkdir(parents=True, exist_ok=False)
    reference = prove.reference_fingerprint(pg_bin, work / "reference-build")
    production = scratch.start(pg_bin, work, "production", superuser=SUPER)
    results = []
    try:
        scratch.build_from_migrations(production, ROOT, APP_DATABASE)
        for index, case in enumerate(CASES, start=1):
            results.append(
                _run_case(pg_bin, work / f"case-{index:02d}", case, production, reference)
            )
    finally:
        scratch.stop(production)
    escape_strings = escape_string_differential(pg_bin, work / "escape-strings")
    passed = all(result["passed"] for result in results) and escape_strings["passed"]
    return {
        "schema_version": "ucpe.restore_proof_rehearsal.v1",
        "cases": results,
        "escape_strings": escape_strings,
        "verdict": "PASS" if passed else "FAIL",
    }


def _run_case(
    pg_bin: Path,
    work: Path,
    case: Case,
    production: scratch.Cluster,
    reference: dict[str, Any],
) -> dict[str, Any]:
    work.mkdir(parents=True)
    scratch_value = secrets.token_hex(16)  # this case's throwaway login secret, never shown
    export = work / "export"
    own: scratch.Cluster | None = None
    try:
        if case.cluster_sql:
            own = scratch.start(pg_bin, work, "production", superuser=SUPER)
            scratch.build_from_migrations(own, ROOT, APP_DATABASE)
            for sql in case.cluster_sql:
                own.psql(command=sql.format(scratch_value=scratch_value))
            for role, sql in case.database_sql:
                own.psql(database=APP_DATABASE, user=role, command=sql)
            export_with_the_card(
                own,
                APP_DATABASE,
                export,
                with_data=case.with_data,
                with_passwords=case.with_passwords,
            )
        else:
            database = f"case_{work.name.replace('-', '_')}"
            production.psql(
                command=f'CREATE DATABASE {database} TEMPLATE {APP_DATABASE} OWNER "{OWNER}"'
            )
            try:
                for role, sql in case.database_sql:
                    production.psql(database=database, user=role, command=sql)
                export_with_the_card(production, database, export, with_data=case.with_data)
            finally:
                production.psql(command=f"DROP DATABASE {database}")
    finally:
        if own is not None:
            scratch.stop(own)
    if case.edit is not None:
        case.edit(export)
    # The owner's digests, as step 5 of the card gives them (taken after any edit under test).
    digests = {
        name: hashlib.sha256((export / name).read_bytes()).hexdigest()
        for name in ("schema.sql", "roles.sql")
    }
    if case.wrong_digest:
        digests["schema.sql"] = "0" * 64
    proof_work = work / "proof"
    report = prove.run(pg_bin, export, proof_work, reference=reference, expected_sha256=digests)
    actual = {
        "verdict": report["verdict"],
        "differences": sorted(
            (item["category"], item["path"]) for item in report.get("differences", [])
        ),
        "refusals": sorted({item["kind"] for item in report["gate_refusals"]}),
        "errors": sorted(
            {
                item["category"]
                for item in report.get("restore_errors", [])
                if item["category"] != "expected"
            }
        ),
    }
    expected = {
        "verdict": case.verdict,
        "differences": sorted(case.differences),
        "refusals": sorted(case.refusals),
        "errors": sorted(case.errors),
    }
    checks: dict[str, bool] = {}
    if case.verdict == "REFUSED_EXPORT":
        checks["nothing_restored"] = not proof_work.exists()
    if "meta_command_never_ran" in case.checks:
        checks["meta_command_never_ran"] = not (export / "META_COMMAND_RAN").exists()
    if "password_never_reported" in case.checks:
        verifier_seen = "SCRAM-SHA-256$" in json.dumps(report)
        checks["password_never_reported"] = not verifier_seen and scratch_value not in json.dumps(
            report
        )
    if "setting_value_never_reported" in case.checks:
        shown = [json.dumps(report).encode()]
        shown += [path.read_bytes() for path in proof_work.rglob("*") if path.is_file()]
        checks["setting_value_never_reported"] = not any(
            marker.encode() in item for marker in (scratch_value, REFUSED_VALUE) for item in shown
        )
    shutil.rmtree(export, ignore_errors=True)  # the scratch export: nothing of it is kept
    return {
        "case": case.name,
        "expected": expected,
        "actual": actual,
        "checks": checks,
        "passed": actual == expected and all(checks.values()),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--pg-bin", type=Path, required=True)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.work.exists():
        print(f"REFUSED: {args.work} exists; give a fresh work folder", file=sys.stderr)
        return 2
    report = rehearse(args.pg_bin, args.work)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    passed = sum(case["passed"] for case in report["cases"])
    escapes = report["escape_strings"]
    print(
        f"REHEARSAL={report['verdict']} cases={passed}/{len(report['cases'])} "
        f"escape_strings={'PASS' if escapes['passed'] else 'FAIL'}"
    )
    for case in report["cases"]:
        if not case["passed"]:
            print(f"  FAILED: {case['case']}")
    return 0 if report["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
