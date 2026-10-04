# Runbook: switch the Space's evidence reader to its least-privilege role (E2)

The Space reads evidence over direct Postgres with its secret `SUPABASE_DB_URL`. Two things use it:
- the calibration endpoint and the skill-evidence refresh, which read predictions and outcomes;
- the automation route (F1), which reads its credential registry and writes its ledger.

Before E2 nobody had checked which role that secret logs in as (gap G2). If it is the table owner,
the public runtime can disable the append-only triggers and rewrite evidence.

After this switch, the Space connects as `ucpe_space_db` (migration 0016). That role may only:
- read predictions and outcomes;
- read the automation credential registry;
- read, insert and update the automation ledger.

It can never write core evidence, alter a table or call a bundle function.

These are owner-only steps, because they make and enter a secret. Never paste the password, the URL
or the SQL into chat, a file in this repository, or a log.

## The order

1. **The E2 release**, a T4 (docs/runbooks/RELEASE.md). From it on, every Space start logs one
   `evidence_reader_identity` event. It holds:
   - the release id;
   - the NAME of the secret in use;
   - the role, named only if it is UCPE's own (`ucpe_*`), else `OTHER`;
   - the verdict;
   - the role's capabilities, as true/false values and counts.

   The event reads the database catalog only. It reads no table row, writes nothing and prints no
   secret.
2. **Claude reads the first event**, passively. It shows which role `SUPABASE_DB_URL` uses today,
   and what that role may do. That is the identification.
3. **This switch** (the steps below).

## What is already proven

- **The helper, `scripts/space_db_credential.py`:** it is G1's resolver helper
  (docs/runbooks/RESOLVER_CUTOVER.md) for the role `ucpe_space_db`, with the same rules:
  - the same template check;
  - PostgreSQL's own SCRAM-SHA-256 secret, so the database never gets the password;
  - owner-only files in `~/ucpe-keys`;
  - nothing secret is printed.

  Its files are `ucpe-space-db-login.sql` and `ucpe-space-db-url.txt`. They sit beside the
  resolver's and never replace them.
- **The privilege rehearsal** (CI, scratch PostgreSQL, password logins over TCP):
  - P4: production's calibration code and the F1 registry, ledger and capacity probes work as
    `ucpe_space_db`, and every other statement is refused;
  - E1: on migration 0018's catalog (production's), production's identity report says `DESIGNED`
    for the helper's login. It says `NOT_DESIGNED` for:
    - the owner;
    - `ucpe_resolver`;
    - each of three planted deviations: an extra core write, a policy that hides rows, and a missing
      privilege.

    A wrong password is `UNKNOWN`, never `DESIGNED`.
- **Production's catalog for `ucpe_space_db` equals the design.** The 0018 apply's post-checks (run
  37172530166) recorded:
  - no attribute and no membership;
  - SELECT on predictions, outcomes and the credential registry;
  - SELECT, INSERT and UPDATE on the ledger;
  - every policy is `true`, so it sees every row the owner sees;
  - no CREATE on the schema.

  The same SQL, run as this role, therefore returns the same rows: the skill evidence does not
  change.
- **Not yet proven:** that production's pooler accepts the role's login. The Space's next start is
  that proof.

## The steps (after the E2 release, and after Claude has read its first event)

1. **Copy the template.**
   - In the Supabase dashboard, open the project and click **Connect** at the top.
   - In "Connect to your project", open **Connection String**.
   - Choose the type **URI** and the method **Session pooler**, then copy the string.
   - It shows `[YOUR-PASSWORD]`: leave it as it is.
2. **Make the credential, on your Mac** (Terminal). The command reads the template from the
   clipboard:
   ```bash
   cd /Users/kha/Documents/Kha-app/UCPE && .venv/bin/python -m scripts.space_db_credential generate
   ```
   It prints the connection mode and the names of two owner-only files in `~/ucpe-keys`: the login
   SQL and the Space URL. It refuses a string that already holds a real password.
3. **Give the role its login.**
   - Open the Supabase dashboard → **SQL Editor** → **New query**.
   - Copy the SQL:
     ```bash
     cd /Users/kha/Documents/Kha-app/UCPE && .venv/bin/python -m scripts.space_db_credential copy-sql
     ```
   - Paste it (⌘V) and click **Run**. Expect "Success. No rows returned".

   This is the only database change: the role can now log in. Nothing uses it yet. If the answer is
   "permission denied", stop and tell Claude.
4. **Add the new Space secret.**
   - On Hugging Face, open the Space → **Settings** → **Variables and secrets** → **New secret**.
   - Use the name `UCPE_SPACE_DB_URL`.
   - Copy the value:
     ```bash
     cd /Users/kha/Documents/Kha-app/UCPE && .venv/bin/python -m scripts.space_db_credential copy-url
     ```
   - Paste it (⌘V), then click **Save**.

   The Space restarts by itself. If it has not restarted after two minutes, use **Restart this
   Space**, never a factory rebuild.

   **Leave `SUPABASE_DB_URL` exactly as it is.** It is the rollback.
5. Clear the clipboard:
   ```bash
   pbcopy < /dev/null
   ```

Do step 3 before step 4. Until the new secret exists, the Space keeps using `SUPABASE_DB_URL`.

## How it is verified (fail-closed, no extra traffic)

Claude reads the restarted Space's log. Nothing is requested from the app.

**The switch is accepted only if** the new start's `evidence_reader_identity` event shows all of:
- `db_url_source` `UCPE_SPACE_DB_URL`;
- `db_role` `ucpe_space_db`;
- `verdict` `DESIGNED`;
- the live release id.

`DESIGNED` means every check passed:
- the login is the role itself, with no switch from a stronger login;
- no superuser, createrole, createdb, replication or bypassrls, and no inherit;
- no role membership;
- no owner rights in the schema;
- no core write and no definer function;
- every privilege the code needs, nothing more;
- policies that hide no row.

Anything else is a failure: `UNKNOWN`, `NOT_DESIGNED`, another role, another secret name, or no
event. On a failure, roll back.

**The Space must also stay well.** Health stays 200, build-info stays the release, and the guard stays
HEALTHY.

**Later natural evidence.** The next natural analysis refreshes the skill evidence as
`ucpe_space_db`. If the automation route is called naturally, it uses its ledger as
`ucpe_space_db`. Neither is ever triggered for the check.

If the login itself fails, everything fails closed:
- the skill evidence stays "insufficient", the conservative default;
- the calibration endpoint answers "unavailable";
- the automation route answers 503;
- analyses still save, because the writer does not use this secret.

## Rollback (instant, no secret value needed)

Delete the Space secret `UCPE_SPACE_DB_URL` (Settings → Variables and secrets). The Space restarts
and reads with `SUPABASE_DB_URL`, exactly as before. Claude confirms that the next event shows
`db_url_source` `SUPABASE_DB_URL`.

The role keeps its login, which is harmless: only the files in `~/ucpe-keys` hold its password. To
remove the login as well, run this in the SQL Editor:
```sql
ALTER ROLE ucpe_space_db NOLOGIN;
```

## Afterwards: consolidate (once the switch is LIVE_PROVEN)

The narrow URL moves into `SUPABASE_DB_URL` itself. Then every release reads as `ucpe_space_db`,
including an older rollback target that only knows `SUPABASE_DB_URL`, and the owner credential
leaves the public runtime. On Hugging Face, open the Space → **Settings** → **Variables and
secrets**, then:

1. **Replace the value of `SUPABASE_DB_URL`** with the narrow URL. Copy it with:
   ```bash
   cd /Users/kha/Documents/Kha-app/UCPE && .venv/bin/python -m scripts.space_db_credential copy-url
   ```
   The Space restarts. It still reads with `UCPE_SPACE_DB_URL`, so nothing changes yet.
2. **Delete `UCPE_SPACE_DB_URL`.** The Space restarts and now reads with `SUPABASE_DB_URL`, which holds
   the narrow URL.
3. **Delete `SUPABASE_SERVICE_ROLE_KEY`** (design C1). No code path uses it while the writer pair is
   set.
4. Clear the clipboard (`pbcopy < /dev/null`).

**Accepted only if** the last start's event shows `db_url_source` `SUPABASE_DB_URL`, `db_role`
`ucpe_space_db` and `verdict` `DESIGNED`. That proves `SUPABASE_DB_URL` itself now holds the narrow
login. The next natural receipt must still be `SAVED`.

If the event shows anything else, add `UCPE_SPACE_DB_URL` again with the narrow URL (step 4 of the
switch). It wins over `SUPABASE_DB_URL`.

Then **the final Phase 3 exit re-audit**.

**To rotate the password later:**
1. Remove the two `ucpe-space-db-*` files from `~/ucpe-keys`.
2. Repeat the switch with the new password: add `UCPE_SPACE_DB_URL`, check the event, then
   consolidate.
