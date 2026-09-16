-- Rehearsal fixture, part 1: the Supabase roles, grants and defaults the privilege audit reasons about.
-- Runs ONLY in a scratch local PostgreSQL on a CI runner, as that server's superuser, BEFORE the real
-- migrations 0001-0004 and 0007 are applied. Never run it against a real database.
CREATE ROLE anon NOLOGIN NOINHERIT;
CREATE ROLE authenticated NOLOGIN NOINHERIT;
CREATE ROLE service_role NOLOGIN NOINHERIT BYPASSRLS;
CREATE ROLE authenticator NOLOGIN NOINHERIT;
GRANT anon, authenticated, service_role TO authenticator;
ALTER ROLE authenticator SET pgrst.db_schemas = 'public, graphql_public';
GRANT USAGE ON SCHEMA public TO anon, authenticated, service_role;
-- Supabase grants every API role everything on each new table in public by default.
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
  GRANT ALL ON TABLES TO anon, authenticated, service_role;
