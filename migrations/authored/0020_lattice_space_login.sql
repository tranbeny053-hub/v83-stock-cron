-- Migration 0020: the NG4 pilot's writer login, ucpe_lattice_space (W2; owner 2026-11-07). AUTHORED, NOT APPLIED.
--
-- Run only by scripts/apply_migration_0019.py, in the same transaction as migrations/authored/0019_lattice_evidence.sql
-- and scripts/migration_0019_capacity.sql and right after them: one one-shot T4, never on its own, never twice.
--
-- WHY A SEPARATE ROLE (W2, not W1). The Space's evidence reader ucpe_space_db is accepted as DESIGNED only with zero
-- role memberships (persistence/reader_identity.py); making it a member of ucpe_lattice_writer would undo that. So the
-- lattice gets its own login, which may do exactly one thing: call 0019's three writer functions.
--
-- WHAT IT IS. NOLOGIN until the owner's credential step (scripts/lattice_space_credential.py, docs/runbooks/
-- NG4_PILOT_W2.md); NOINHERIT, so no later grant is inherited by default; no other attribute; at most 3 connections.
-- One membership: ucpe_lattice_writer WITH INHERIT TRUE, SET FALSE, without ADMIN, so it uses the writer's EXECUTE on
-- the three functions, can never SET ROLE to the writer and can never grant it on. Its sessions are bounded by role
-- settings that apply behind any pooler.
--
-- ROLLBACK. A separate owner T4, never automatic: ALTER ROLE ucpe_lattice_space NOLOGIN; REVOKE ucpe_lattice_writer
-- FROM ucpe_lattice_space; DROP ROLE ucpe_lattice_space. Disabling it after the pilot's end is the first statement alone.

DO $$
BEGIN
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
-- own on any schema, relation or function (its rights are the writer's and PUBLIC's only).
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
END;
$$;
