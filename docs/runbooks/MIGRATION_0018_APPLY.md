# Runbook: apply migration 0018 (D6, service_role narrowed on core evidence), once

Migration 0018 takes from `service_role` every way to write the six core evidence tables, and
EXECUTE on the two bundle functions. It keeps SELECT. The least-privilege writer (`ucpe_api_writer`,
LIVE_PROVEN) and the resolver (`ucpe_resolver`) are untouched, so production keeps saving and
resolving. It is the owner's ruling D6: timing B, the frozen scope, frozen only after the production
inventory was clean (run 37149774863).

**It is a T4: one dispatch, authorized by the owner, never rerun.**

## History

- **Run 37170407623** (2026-10-04, main b7d54fcc, attempt 1) was REFUSED by its pre-checks: "the role
  ucpe_resolver holds login". The check was 0017's and predated G1's login for the resolver. **Nothing
  was applied:** the migration statement never ran, and the transaction rolled back. The captured
  production state is the pre-D6 state. The attempt is consumed and never rerun. Evidence:
  `.work/t4_0018/ADJUDICATION.md`.
- The repaired route accepts a login on exactly the design's two login roles (`ucpe_resolver` now,
  `ucpe_space_db` after E2), and its rehearsal applies G1's login, as production holds it. Dispatching
  it is a new T4, at the repaired commit.
- **Run 37172530166** (2026-10-04, main 82ed9c48, attempt 1) **APPLIED** 0018 and committed. The
  executed digest is the reviewed one. service_role holds SELECT only on the six core tables and
  executes neither bundle function, and D6's inventory is empty. Evidence:
  `.work/t4_0018_apply/ADJUDICATION.md`. The registry records `applied_run` 37172530166.

## Before

- The route (`scripts/apply_migration_0018.py`) and both workflows are merged on main, with every
  check green: the 0018 rehearsal, the privilege rehearsal's D1-D4, and CI.
- main stays at the commit you dispatch until the run starts. The route refuses any other commit.

## The apply (you)

1. **Dispatch.** Run the one command Claude gives you. It checks that main is still the reviewed
   commit, then dispatches `apply-migration-0018.yml` with `expected_sha` and the token
   `APPLY-MIGRATION-0018-ONCE`. Nothing touches production yet.
2. **Approve.** GitHub → the repository → **Actions** → **Migration 0018 narrows service_role on
   core evidence** → the waiting run → **Review deployments** → tick `production-db-owner` →
   **Approve and deploy**.

The run takes a few minutes:
1. It verifies the dispatch and the runtime.
2. It rehearses the whole apply on a throwaway database, then runs the tests.
3. Only then does it apply 0018 to production, in one transaction. The pre-checks include D6's
   inventory, read again in that transaction. The post-checks refuse anything but the reviewed
   result. Any refusal changes nothing.

## After (Claude, read only)

- Claude reads the run's raw report and adjudicates it, as for the inventory: `outcome: APPLIED`,
  `committed: true`, `service_role` SELECT only, no inventory surface, everything else unchanged.
- A registry record (`ops/release/releases.json`: 0018's `applied_run`), so the next release can
  ship (release check 5c).
- D6's inventory with `expect=after` (docs/runbooks/CORE_WRITE_INVENTORY.md): you dispatch and
  approve it, and it must find nothing.
- Then, optional hygiene: delete `SUPABASE_SERVICE_ROLE_KEY` from the Space's secrets. While the
  writer pair is set, no code path uses it. After 0018 it can no longer write core evidence anyway.

## If it must be undone

The rollback is `scripts/privilege_rehearsal/rollback_0018.sql`. It gives `service_role` back
exactly what 0018 takes, and P3-PRIV-R's D4 proves it. Running it against production is a separate
T4, never automatic.

A code rollback stays safe only to a release from a2de125f (UCPE-PROD-WA-20261003-A) on, because
those releases write through the least-privilege pair. The release tool checks this rule
(`rollback_safe_from` in the registry).
