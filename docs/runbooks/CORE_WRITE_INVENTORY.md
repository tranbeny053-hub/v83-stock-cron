# Runbook: D6's read-only production core-write inventory

The owner's D6 ruling (2026-10-03): "scope=six core evidence tables + two bundle functions, keep
SELECT and revoke write/EXECUTE, with deterministic inventory proving no omitted core write surface
before freeze." This route reads production's catalogs once, read only, and says whether anything
outside that revoke set lets `service_role` write core evidence. It changes nothing.

**When:**
- `expect=before`: only after E3 is LIVE_PROVEN by a natural USER_REQUESTED receipt (the owner's
  rule, 2026-10-03), once this route is merged. A clean result is what allows 0018's freeze.
- `expect=after`: once migration 0018 is applied. Nothing may remain then.

**What it reads:** PostgreSQL catalogs only, in one READ ONLY snapshot that is always rolled back.
It never reads an application row.

**What it publishes (the repository and its logs are public):** the surfaces by kind and the
verdict. A role name appears only if it is an API role (anon, authenticated, authenticator,
service_role), PostgreSQL's own (`pg_*`) or UCPE's (`ucpe_*`). Every other name is withheld. The
connecting role, the database URL and the server version never appear.

## The steps

1. **Dispatch.** Claude may run this; nothing reads production until you approve:

   `gh workflow run core-write-inventory.yml --ref main -f expected_sha=<main's full 40-character SHA> -f expect=before -f confirm=READ-ONLY-CORE-WRITE-INVENTORY-ONCE`

2. **Approve (you).** GitHub → the repository → **Actions** → **Core-write inventory** → the
   waiting run → **Review deployments** → tick `production-db-owner` → **Approve and deploy**.
3. **Read the result.** The run uploads the artifact `core-write-inventory`.
   - `verdict: PASS` with `expect=before`: nothing outside D6's revoke set. 0018 can be frozen.
   - `verdict: FAIL`: `failures` lists each omitted surface (`F public.some_function() …`). The red
     run changed nothing. Whether D6's scope changes is the owner's decision.
   - `outcome: REFUSED` or `FAILED`: nothing changed (the snapshot is read only and rolled back).
     The report says why; an unexpected failure is reported by its type only.

## What every run proves before it reads production

- The dispatch is this workflow, in the owner repository, on main, at exactly `expected_sha`, under
  the exact CPython and the lock-authenticated wheels.
- A rehearsal on a scratch PostgreSQL, built from migrations 0001-0015 plus one planted surface of
  each kind (F, V, R, G, K), connected as a role with no privilege on any core table, catches every
  planted surface and nothing else. That proves it reads catalogs only and catches an omission in
  this exact runtime.
- The inventory's tests pass under that runtime.
