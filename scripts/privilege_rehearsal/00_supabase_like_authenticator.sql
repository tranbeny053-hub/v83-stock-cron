-- Rehearsal fixture for P3-PRIV-R (cluster-wide), after migration 0013's 00_supabase_like_roles.sql:
-- - PostgREST's authenticator, as Supabase has it: LOGIN and NOINHERIT. It is a member of the three API
--   roles, which it may switch to (SET) but never inherits. Its password is a scratch value that the
--   workflow generates for this one run and passes in the environment, never on a command line.
-- - The tables' owner (psql variable "owner") gets CREATEROLE but stays a non-superuser, as Supabase's
--   postgres is. So the draft's role creation is rehearsed with the authority production's applying
--   role has.
-- Runs ONLY in a scratch local PostgreSQL on a CI runner, as that server's superuser.
-- Never run it against a real database.
\getenv authenticator_password PRIVILEGE_REHEARSAL_AUTHENTICATOR_PASSWORD
CREATE ROLE authenticator LOGIN NOINHERIT;
ALTER ROLE authenticator PASSWORD :'authenticator_password';
GRANT anon, authenticated, service_role TO authenticator WITH INHERIT FALSE, SET TRUE;
ALTER ROLE :"owner" CREATEROLE;
