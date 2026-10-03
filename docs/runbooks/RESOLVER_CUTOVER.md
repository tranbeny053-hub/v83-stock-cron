# Runbook: switch the hourly resolver to its least-privilege role (G1)

The hourly resolver (`.github/workflows/resolve-outcomes.yml`, at minute 17) connects today with the
GitHub secret `SUPABASE_DB_URL`. That is the table owner: it can ALTER and DROP tables and disable
the append-only triggers (gap G1, critical). After this switch the resolver connects as
`ucpe_resolver`, from migration 0016, which may only:
- read predictions;
- read and insert outcomes;
- read, insert and update the resolution status.

These are owner-only steps, because they make and enter a secret. Never paste the password, the URL
or the SQL into chat, a file in this repository, or a log.

**Preconditions:**
- migration 0016 is applied: `ucpe_resolver` exists, without a login;
- the resolver workflow uses `UCPE_RESOLVER_DB_URL` when that secret exists, and `SUPABASE_DB_URL`
  until then. Each run prints the secret's name and its role, by name only
  (`resolver_identity role=…`).

**What is already proven:**
- **Supabase's connection rules** (the connecting-to-postgres guide, re-read 2026-10-03): through
  the shared pooler a custom role's username is `[ROLE].[PROJECT-REF]`; a direct connection and the
  dedicated pooler use the role alone. The resolver turns prepared statements off, so session and
  transaction mode both work.
- **The helper, `scripts/resolver_credential.py`:**
  - it computes PostgreSQL's own SCRAM-SHA-256 secret, and its tests reproduce RFC 7677's worked
    example;
  - the database gets only that secret, never the password;
  - the tests prove the password in the URL file is exactly the one the SQL's secret verifies.
- **The privilege rehearsal** (CI, scratch PostgreSQL, password logins over TCP):
  - R1: the helper's secret and URL log in as `ucpe_resolver`, and a wrong password is refused;
  - P5: production's resolver code works as `ucpe_resolver` (the due scans, the outcome insert, the
    read-back, the status upsert) and is refused everything else.
- **Not yet proven:** production's pooler accepting the role's login. The next hourly run is that
  proof.

## The steps

1. **Copy the template.** In the Supabase dashboard, open your project and click **Connect** at the
   top. In "Connect to your project", open **Connection String**, choose the type **URI** and the
   method **Session pooler**, and copy the string. It shows `[YOUR-PASSWORD]`: leave it as it is.
2. **Make the credential, on your Mac** (Terminal). The command reads the template from the
   clipboard:
   ```bash
   cd /Users/kha/Documents/Kha-app/UCPE && .venv/bin/python -m scripts.resolver_credential generate
   ```
   It prints the connection mode and two owner-only files in `~/ucpe-keys`: the login SQL and the
   resolver URL. It refuses a string that already holds a real password.
3. **Give the role its login: Supabase dashboard → SQL Editor → New query.** Copy the SQL:
   ```bash
   cd /Users/kha/Documents/Kha-app/UCPE && .venv/bin/python -m scripts.resolver_credential copy-sql
   ```
   Paste it (⌘V) and click **Run**. Expect "Success. No rows returned". This is the one database
   change: the role can now log in. If the answer is "permission denied", stop and tell Claude.
4. **GitHub: the repository → Settings → Secrets and variables → Actions → New repository secret**
   (`https://github.com/tranbeny053-hub/v83-stock-cron/settings/secrets/actions/new`). Use the name
   `UCPE_RESOLVER_DB_URL`. Copy the value:
   ```bash
   cd /Users/kha/Documents/Kha-app/UCPE && .venv/bin/python -m scripts.resolver_credential copy-url
   ```
   Paste it (⌘V), then click **Add secret**.
5. Clear the clipboard:
   ```bash
   pbcopy < /dev/null
   ```

Do step 3 before step 4. Until the secret exists, the resolver keeps using the owner URL.

## How it is verified (no extra traffic)

- **The next scheduled run** (minute 17). Claude reads its log, which must show:
  - `resolver credential: UCPE_RESOLVER_DB_URL`;
  - `resolver_identity role=ucpe_resolver`;
  - a run that succeeds.
- **If that run fails:** delete the secret `UCPE_RESOLVER_DB_URL`. The resolver is back on the owner
  URL at the next run. Then tell Claude.

## Afterwards

- **Once runs pass as `ucpe_resolver`,** a small workflow change removes the fallback. From then on
  the resolver job never receives the owner URL.
- **Later (C4),** the owner URL moves into a protected GitHub Environment, used only by the
  dispatch-only apply, audit and evaluation workflows.
- **To rotate the password:** remove the two files from `~/ucpe-keys`, then repeat steps 1 to 5.
