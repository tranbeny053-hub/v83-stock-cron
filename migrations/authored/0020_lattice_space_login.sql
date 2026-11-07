-- Migration 0020: the NG4 pilot's writer login, ucpe_lattice_space (W2; owner 2026-11-07). AUTHORED, NOT APPLIED.
--
-- Run only through scripts/apply_migration_0019.py, in the same transaction as migrations/authored/
-- 0019_lattice_evidence.sql and scripts/migration_0019_capacity.sql and right after them: one one-shot T4. (After a
-- rollback a manual run would pass this file's own guard; the route refuses a second apply.)
--
-- WHY A SEPARATE ROLE (W2, not W1). The Space's evidence reader ucpe_space_db is accepted as DESIGNED only with zero
-- role memberships (persistence/reader_identity.py); making it a member of ucpe_lattice_writer would undo that. So the
-- lattice gets its own login, which may do exactly one thing: call 0019's three writer functions.
--
-- WHAT IT IS. NOLOGIN until the owner's credential step (scripts/lattice_space_credential.py, docs/runbooks/
-- NG4_PILOT_W2.md); NOINHERIT, so no later grant is inherited by default; no other attribute; at most 3 connections.
-- One membership: ucpe_lattice_writer WITH INHERIT TRUE, SET FALSE, without ADMIN, so it uses the writer's EXECUTE on
-- the three functions, can never SET ROLE to the writer and can never grant it on. Its sessions start with three
-- role-level defaults (statement, lock and idle-in-transaction timeouts): DEFAULTS, not limits, since a session may
-- SET them and a role may ALTER ROLE its own defaults; the runner's own SET LOCAL statement_timeout is its bound, and
-- CONNECTION LIMIT (which only a CREATEROLE admin can change) is a real one. No idle_session_timeout: it would cut a
-- pooler's server connections. The limit and the three values are engineering choices, not owner rulings.
--
-- LEAST PRIVILEGE INCLUDES PUBLIC. The role's only implicit inheritance is PUBLIC, so the self-check below asks with the
-- role's own name (has_*_privilege('ucpe_lattice_space', ...)), which counts PUBLIC's grants too.
--
-- TRUSTED ADMINS. On PostgreSQL 16+ the CREATEROLE applier keeps ADMIN on this role, so the applier, any role that can
-- SET ROLE to it, and superusers can give it a login at any time — the same principals 0019's header names.
--
-- DISABLE AND ROLLBACK (docs/runbooks/NG4_PILOT_W2.md; owner steps, never automatic). NOLOGIN stops only NEW logins:
-- disabling after the pilot's end is ALTER ROLE ucpe_lattice_space NOLOGIN PASSWORD NULL, deleting the Space secret, and
-- ending the role's live sessions. Rollback (a separate T4) then adds REVOKE ucpe_lattice_writer FROM
-- ucpe_lattice_space; DROP ROLE ucpe_lattice_space.

DO $$
BEGIN
    IF pg_catalog.current_setting('server_version_num')::int < 160000 THEN
        RAISE EXCEPTION '0020: PostgreSQL 16 or later is required' USING ERRCODE = 'UP020';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_roles
                    WHERE rolname = current_user AND rolcreaterole AND NOT rolsuper) THEN
        RAISE EXCEPTION '0020: the applier must be a CREATEROLE non-superuser' USING ERRCODE = 'UP020';
    END IF;
    IF pg_catalog.current_setting('createrole_self_grant') <> '' THEN
        RAISE EXCEPTION '0020: createrole_self_grant must be empty' USING ERRCODE = 'UP020';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'ucpe_lattice_writer')
       OR NOT EXISTS (SELECT 1 FROM pg_catalog.pg_namespace WHERE nspname = 'ucpe_lattice') THEN
        RAISE EXCEPTION '0020: migration 0019 is not applied' USING ERRCODE = 'UP020';
    END IF;
    IF EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'ucpe_lattice_space') THEN
        RAISE EXCEPTION '0020: ucpe_lattice_space already exists' USING ERRCODE = 'UP020';
    END IF;
END;
$$;

CREATE ROLE ucpe_lattice_space NOLOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS
    CONNECTION LIMIT 3;
GRANT ucpe_lattice_writer TO ucpe_lattice_space WITH INHERIT TRUE, SET FALSE;
ALTER ROLE ucpe_lattice_space SET statement_timeout = '5s';
ALTER ROLE ucpe_lattice_space SET lock_timeout = '2s';
ALTER ROLE ucpe_lattice_space SET idle_in_transaction_session_timeout = '30s';

-- Self-check: exactly the one membership; nobody a member of it but its creator's ADMIN-only grant; no privilege of its
-- own anywhere; and, PUBLIC included: no relation privilege in public or ucpe_lattice, no executable SECURITY DEFINER
-- function there but the writer's three, no CREATE on any schema or the database, nothing in pg_shdepend for it.
DO $$
DECLARE
    v_space oid := (SELECT oid FROM pg_catalog.pg_roles WHERE rolname = 'ucpe_lattice_space');
BEGIN
    IF (SELECT count(*) FROM pg_catalog.pg_auth_members m WHERE m.member = v_space) <> 1
       OR NOT EXISTS (
            SELECT 1 FROM pg_catalog.pg_auth_members m
              JOIN pg_catalog.pg_roles r ON r.oid = m.roleid
             WHERE m.member = v_space AND r.rolname = 'ucpe_lattice_writer'
               AND m.inherit_option AND NOT m.set_option AND NOT m.admin_option) THEN
        RAISE EXCEPTION '0020 self-check: the membership is not exactly the writer, inherit only'
            USING ERRCODE = 'UP020';
    END IF;
    IF EXISTS (
        SELECT 1 FROM pg_catalog.pg_auth_members m
         WHERE m.roleid = v_space
           AND (m.member <> (SELECT oid FROM pg_catalog.pg_roles WHERE rolname = current_user)
                OR m.inherit_option OR m.set_option OR NOT m.admin_option)) THEN
        RAISE EXCEPTION '0020 self-check: a member of ucpe_lattice_space beyond its creator''s ADMIN-only grant'
            USING ERRCODE = 'UP020';
    END IF;
    IF EXISTS (
        SELECT 1
          FROM (SELECT n.nspacl AS acl FROM pg_catalog.pg_namespace n
                UNION ALL SELECT c.relacl FROM pg_catalog.pg_class c
                UNION ALL SELECT p.proacl FROM pg_catalog.pg_proc p) o
         CROSS JOIN LATERAL pg_catalog.aclexplode(o.acl) a
         WHERE o.acl IS NOT NULL AND a.grantee = v_space) THEN
        RAISE EXCEPTION '0020 self-check: ucpe_lattice_space holds a privilege of its own'
            USING ERRCODE = 'UP020';
    END IF;
    IF EXISTS (
        SELECT 1 FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
         WHERE n.nspname IN ('public', 'ucpe_lattice') AND c.relkind IN ('r', 'p', 'v', 'm', 'f', 'S')
           AND (pg_catalog.has_table_privilege('ucpe_lattice_space', c.oid,
                    'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')
                OR pg_catalog.has_any_column_privilege('ucpe_lattice_space', c.oid,
                    'SELECT,INSERT,UPDATE,REFERENCES')
                OR (c.relkind = 'S' AND pg_catalog.has_sequence_privilege('ucpe_lattice_space', c.oid,
                    'USAGE,SELECT,UPDATE')))) THEN
        RAISE EXCEPTION '0020 self-check: ucpe_lattice_space can reach a relation in public or ucpe_lattice'
            USING ERRCODE = 'UP020';
    END IF;
    IF EXISTS (
        SELECT 1 FROM pg_catalog.pg_proc p JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace
         WHERE n.nspname IN ('public', 'ucpe_lattice') AND p.prosecdef
           AND pg_catalog.has_schema_privilege('ucpe_lattice_space', n.oid, 'USAGE')
           AND pg_catalog.has_function_privilege('ucpe_lattice_space', p.oid, 'EXECUTE')
           -- by catalog name: the applier has no USAGE on ucpe_lattice, so no regprocedure cast
           AND (n.nspname, p.proname, pg_catalog.pg_get_function_identity_arguments(p.oid)) NOT IN (
                ('ucpe_lattice', 'record_lattice_row', 'p_row jsonb'),
                ('ucpe_lattice', 'record_missed_instant', 'p_entry jsonb'),
                ('ucpe_lattice', 'capture_commit_receipts', 'p_limit integer'))) THEN
        RAISE EXCEPTION '0020 self-check: ucpe_lattice_space can execute a SECURITY DEFINER function beyond the three'
            USING ERRCODE = 'UP020';
    END IF;
    -- The applying session's own temporary schema grants every right to any TEMP holder (PUBLIC's default):
    -- it is excluded, since only that backend can use it and a pooled backend may keep one.
    IF EXISTS (SELECT 1 FROM pg_catalog.pg_namespace n
                WHERE pg_catalog.has_schema_privilege('ucpe_lattice_space', n.oid, 'CREATE')
                  AND n.oid <> pg_catalog.pg_my_temp_schema())
       OR pg_catalog.has_database_privilege('ucpe_lattice_space', pg_catalog.current_database(), 'CREATE') THEN
        RAISE EXCEPTION '0020 self-check: ucpe_lattice_space can CREATE in a schema or the database'
            USING ERRCODE = 'UP020';
    END IF;
    IF EXISTS (SELECT 1 FROM pg_catalog.pg_shdepend d
                WHERE d.refclassid = 'pg_catalog.pg_authid'::regclass AND d.refobjid = v_space) THEN
        RAISE EXCEPTION '0020 self-check: an object or ACL depends on ucpe_lattice_space'
            USING ERRCODE = 'UP020';
    END IF;
END;
$$;
