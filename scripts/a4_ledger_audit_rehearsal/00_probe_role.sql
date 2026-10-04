-- Rehearsal fixture for ucpe.a4_ledger_audit.v1: a role that can read ONLY the automation ledger.
-- Runs ONLY in a scratch local PostgreSQL on a CI runner, as that server's superuser, after every
-- applied migration. Never run it against a real database.
-- The rehearsal runs the sealed audit as this role (SET ROLE): if the audit read any other table,
-- it would fail with a privilege error instead of passing.
CREATE ROLE a4_probe NOLOGIN NOINHERIT;
GRANT USAGE ON SCHEMA public TO a4_probe;
GRANT SELECT ON TABLE public.automation_radar_ledger TO a4_probe;
CREATE POLICY a4_probe_select ON public.automation_radar_ledger FOR SELECT TO a4_probe USING (true);
GRANT a4_probe TO :"owner";
