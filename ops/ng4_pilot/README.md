# NG4 pilot database routes

These workflows are **AUTHORED BUT DISABLED**. GitHub registers only workflow files directly under `.github/workflows`; the owner's T3 enablement is a pure rename there (`git diff -M100%`). Dispatch remains a separate owner authorization. The preflight is a production read. Applying 0019 is a one-shot T4 and must never be rerun.

`ng4-pilot-preflight.yml` runs `scripts/ng4_pilot_preflight.py`. Its first statement is `SET TRANSACTION READ ONLY`; it inspects catalogs and rolls back. READY means every first-apply condition currently checked is true. The event-trigger allowlist is empty: no Supabase platform event-trigger names are referenced by this repository, so every DDL event trigger is counted as not allowlisted.

`apply-migration-0019.yml` runs `scripts/apply_migration_0019.py`, which pins the authored 0019 migration and its capacity SQL by SHA-256, checks preconditions, applies both in one transaction, checks the resulting catalogs, and commits only if all checks pass. Both routes use the same pinned-action, Python 3.13.14, hash-locked wheel, dispatch, protected environment, and concurrency boundary as the existing database workflows. The database URL is never included in output or reports.

The rehearse interface is local-only and accepts socket or localhost URLs without passwords or a Supabase host. It is intended for scratch PostgreSQL; it is not a production route. `MIGRATION_0019_REHEARSAL_URL` and `NG4_PILOT_PREFLIGHT_REHEARSAL_URL` are the respective rehearsal variables.

The apply's outside-schema post-check compares, before and after, everything outside schema `ucpe_lattice`: roles and their attributes, memberships, relation and schema ACLs, policies, functions, publications, default ACLs and event triggers. It does not compare database, column, type or parameter ACLs, role settings or extensions; 0019's pinned bytes touch none of these.

The runner's day-7 checkpoint counts statuses in-process since the process started; its `logged` count covers missed instants at their own wake, not the NOT_ISSUED gap entries a later step adds for instants it never woke for. The authoritative counts come from the T4 package's read-only EXP-09 queries (counts, statuses and timestamps only).
