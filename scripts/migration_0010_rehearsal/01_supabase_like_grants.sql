-- Rehearsal fixture for migration 0010, part 2 (per database): Supabase's schema usage and default
-- privileges, for the role that will own the tables (psql variable "owner"). Runs ONLY in a scratch
-- local PostgreSQL on a CI runner, as that server's superuser. Never run it against a real database.
GRANT USAGE ON SCHEMA public TO anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES FOR ROLE :"owner" IN SCHEMA public
  GRANT ALL ON TABLES TO anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES FOR ROLE :"owner" IN SCHEMA public
  GRANT ALL ON SEQUENCES TO anon, authenticated, service_role;
