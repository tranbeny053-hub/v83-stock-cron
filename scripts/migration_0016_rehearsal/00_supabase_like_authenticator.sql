-- Rehearsal fixture for migration 0016 (cluster-wide), after migration 0013's 00_supabase_like_roles.sql:
-- - PostgREST's authenticator, as Supabase has it: NOINHERIT. It is a member of the three API roles,
--   which it may switch to (SET) but never inherits. It is NOLOGIN here, because no PostgREST connects
--   in this rehearsal.
-- - The tables' owner (psql variable "owner") gets CREATEROLE but stays a non-superuser, as Supabase's
--   postgres is.
-- Runs ONLY in a scratch local PostgreSQL on a CI runner, as that server's superuser.
-- Never run it against a real database.
CREATE ROLE authenticator NOLOGIN NOINHERIT;
GRANT anon, authenticated, service_role TO authenticator WITH INHERIT FALSE, SET TRUE;
ALTER ROLE :"owner" CREATEROLE;
