-- Rehearsal fixture for migration 0012, part 2 (per database): Supabase's schema usage and default
-- privileges, for the role that will own the tables (psql variable "owner"). The default privileges
-- grant every new table, prediction_resolution_status included, to the three API roles, exactly as
-- production's do, so the rehearsal proves that the migration revokes them.
-- Runs ONLY in a scratch local PostgreSQL on a CI runner, as that server's superuser.
-- Never run it against a real database.
GRANT USAGE ON SCHEMA public TO anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES FOR ROLE :"owner" IN SCHEMA public
  GRANT ALL ON TABLES TO anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES FOR ROLE :"owner" IN SCHEMA public
  GRANT ALL ON SEQUENCES TO anon, authenticated, service_role;
