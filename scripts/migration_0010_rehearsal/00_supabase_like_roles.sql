-- Rehearsal fixture for migration 0010, part 1 (cluster-wide): the Supabase API roles.
-- Runs ONLY in a scratch local PostgreSQL on a CI runner, as that server's superuser. Never run it
-- against a real database.
CREATE ROLE anon NOLOGIN NOINHERIT;
CREATE ROLE authenticated NOLOGIN NOINHERIT;
CREATE ROLE service_role NOLOGIN NOINHERIT BYPASSRLS;
