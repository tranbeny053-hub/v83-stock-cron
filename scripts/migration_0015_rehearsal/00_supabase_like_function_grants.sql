-- Rehearsal fixture for migration 0015 (per database), after migration 0013's two fixtures:
-- - Supabase's default privileges on new functions in public, for the role that will own them
--   (psql variable "owner"): EXECUTE for the three API roles, exactly as production's are, on top
--   of PostgreSQL's own EXECUTE for PUBLIC. So the rehearsal proves that 0015 revokes them from
--   PUBLIC, anon and authenticated and keeps only service_role.
-- - Membership in the API roles for that role, as PostgREST's authenticator has, so the probes and
--   the PostgREST-compatible rehearsal can SET ROLE to each of them.
-- Runs ONLY in a scratch local PostgreSQL on a CI runner, as that server's superuser.
-- Never run it against a real database.
ALTER DEFAULT PRIVILEGES FOR ROLE :"owner" IN SCHEMA public
  GRANT ALL ON FUNCTIONS TO anon, authenticated, service_role;
GRANT anon, authenticated, service_role TO :"owner";
