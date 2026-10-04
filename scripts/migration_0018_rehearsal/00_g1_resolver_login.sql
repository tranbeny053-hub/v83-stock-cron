-- Migration 0018 rehearsal: G1 on the scratch database. On 2026-10-03 the owner gave ucpe_resolver a login
-- of its own (docs/runbooks/RESOLVER_CUTOVER.md), outside the migrations, so production's roles are 0016's
-- plus that login. The scratch database takes the same step, so the route's pre-checks meet production's
-- roles (run 37170407623 was refused, unapplied, on exactly this). No password: nothing logs in here.
-- Runs ONLY in a scratch local PostgreSQL on a CI runner. Never run it against a real database.
ALTER ROLE ucpe_resolver LOGIN;
