# Runbook: the structure export for the restore proof (DP-D)

**Status: RUN ONCE, by the owner, on 2026-10-07.** Owner ruling DP-D=2 (2026-10-05): structure first.
The two digests and the proof's outcome are in STATE.md. Nothing here writes to the production
database; run the card again only if a later owner ruling asks for a fresh export.

The recovery drill (governing plan §12.1 and §23, "Backup") needs a scratch restore that proves the
declared recovery set. Its first half is the structure: the schema, the roles and grants, and the
seals. This card is the owner's whole part of that half: **two read-only exports, run once, by you,
on your Mac.** Claude does the rest locally, against scratch PostgreSQL 17.6, and never touches the
production database.

What the two files hold:
- `schema.sql`: the `public` schema's structure only (`--schema-only`): tables, columns, constraints,
  indexes, the append-only seals and their functions, row security, the RPCs and every grant. **No
  table row**, so nothing from the section-5A window can leave the database.
- `roles.sql`: the cluster's roles with their memberships, settings and parameter grants
  (`--roles-only`), **with no password** (`--no-role-passwords`).

Never paste the connection string, the password or either file into chat, a file in this repository
or a log. Claude needs only the folder path and the two sha256 lines from step 5.

**Preconditions:**
- PostgreSQL 17 client tools on your Mac, version **17.6 or later 17.x** (17.6 adds the `\restrict`
  safety line the proof requires). With Homebrew: `brew install postgresql@17`.
- Your database password for `postgres` (the one you use for the dashboard's SQL connections).

## The steps

1. **Choose a private folder outside this repository**, for example in your home folder. Nothing in
   it is ever committed or uploaded. In Terminal:
   ```bash
   mkdir -p ~/ucpe-restore-export && cd ~/ucpe-restore-export
   ```
2. **Find the tools and check them.** Homebrew keeps postgresql@17 off the PATH, so name its
   folder once. Both version lines must say 17.6 or a later 17.x:
   ```bash
   PGBIN="$(brew --prefix postgresql@17)/bin"
   ```
   ```bash
   "$PGBIN/pg_dump" --version && "$PGBIN/pg_dumpall" --version
   ```
3. **Copy the connection template.** In the Supabase dashboard, open the project and click
   **Connect**. In "Connect to your project", open **Connection String**, choose the type **URI**
   and the method **Session pooler**, and copy the string. In a text editor, delete
   `:[YOUR-PASSWORD]` from it, so that it reads `postgresql://postgres.<ref>@<host>:5432/postgres`.
   Then run the line below, paste the edited string and press Return: it is kept for this Terminal
   window only, never in your shell history. Each command in step 4 asks for the password itself,
   so the password never sits in a variable, a file or your history either.
   ```bash
   read -r CONNECTION
   ```
4. **Run the two exports.** Each asks for the password once:
   ```bash
   "$PGBIN/pg_dump" --schema-only --schema=public --file=schema.sql --password --dbname="$CONNECTION"
   ```
   ```bash
   "$PGBIN/pg_dumpall" --roles-only --no-role-passwords --file=roles.sql --password --dbname="$CONNECTION"
   ```
5. **Take the two digests**, and send Claude the folder path and these two lines only:
   ```bash
   shasum -a 256 schema.sql roles.sql
   ```

## What Claude does with them (local only)

```bash
python scripts/restore_proof/prove.py --pg-bin <PostgreSQL 17.6 bin> --export ~/ucpe-restore-export \
    --work <a fresh scratch folder> --report <report.json> \
    --expect-sha256 schema.sql=<your first digest> --expect-sha256 roles.sql=<your second digest>
```

1. It checks both digests against yours, then **refuses the export, and restores nothing**, unless
   it is exactly what the two commands make: a data entry, a COPY block, a password clause or
   hash, any psql meta-command but the `\restrict` pair, or anything psql would read differently
   from the gate (an escape string in any form but the one pg_dumpall writes for a role's setting,
   comment or security label, a psql variable, a changed string or encoding setting) is a refusal
   (`gate.py`). So is a setting for every role (`ALTER ROLE ALL …`) or for one database only
   (`ALTER ROLE … IN DATABASE …`): the commands never write either, and the proof could not
   compare one.
2. It checks its own PostgreSQL is 17.6 or a later 17.x, then builds a scratch cluster from the
   migrations, as every migration rehearsal does, and restores a private copy of your two files
   (checked again against your digests, deleted once restored) into a second one. Both clusters
   are private (no network listener) and deleted at the end.
3. It compares the two catalogs item by item and writes one report: your files' digests and
   versions, the PostgreSQL release it used, every restore error and every difference. It reads no
   table row, and it compares a role setting by its digest only, so no setting's value is ever
   shown. The report reproduces structure text (defaults, comments, function lines), so it stays
   out of this repository and out of chat: Claude reports the verdict and the counts.

`RESTORE_PROOF=PASS` means the structure restores into PostgreSQL 17.6, equals what the migrations
declare, and opens no privilege path into the app that they do not declare, other than the
exceptions you ruled (accepted, below). Three kinds of difference are reported without failing:
- **operational**: the documented credential steps, LOGIN on `ucpe_space_db`
  (`SPACE_DB_CUTOVER.md`) and on `ucpe_resolver` (`RESOLVER_CUTOVER.md`);
- **platform**: Supabase's own: its other roles with their own attributes (row-security bypass and
  replication included: no app table is granted to everyone, so such a role reaches no app row by
  itself), their settings and their memberships in the other predefined roles; the default
  privileges of its roles; the owner's (`postgres`) attributes, settings, memberships and parameter
  grants (it owns every app table already); LOGIN on `authenticator` (PostgREST logs in with it);
  the API roles' (anon, authenticated, service_role, authenticator) timeouts and their attributes
  that raise no privilege; a platform role's own setting and a Realtime publication entry that
  vanilla PostgreSQL refuses;
- **accepted**: exactly the nine differences you ruled exact managed-platform exceptions
  (DP-D-FINDINGS on 2026-10-07, the first eight; DP-D-STORAGE-SETTINGS on 2026-10-08, the ninth;
  `scripts/restore_proof/catalog.py` `PLATFORM_EXCEPTIONS` cites Supabase's source for each):
  `postgres`'s own default privileges in `public` and its USAGE on `public`; `authenticator`'s three
  settings, by name and value digest; `supabase_storage_admin`'s membership in `authenticator`; the
  memberships of `supabase_etl_admin` and `supabase_read_only_user` in `pg_read_all_data`, each with
  its exact options; and `supabase_storage_admin`'s two settings (`log_statement`, `search_path`) in
  all databases, by name and value digest. Each is listed by name in the report. Anything else at
  those places, or near them (another option, setting, value, database or grant, or the same on an
  API, app or API-acting role), is still a finding; the same settings on another of Supabase's own
  roles stay the platform's, as they always were. So is any path through them: a role holding one of
  those three roles; and, since its accepted membership lets `supabase_storage_admin` act as an API
  role, a role it gains, any setting on it but timeouts alone or exactly its two ruled ones, and a
  parameter grant to it. A setting for one database only is not exported at all (see What this does
  not prove), so the proof cannot see one.

**Trust note (C3).** Supabase's Access Control docs say the SQL snippets a Read-Only project member
runs are run as `supabase_read_only_user`, which has `pg_read_all_data`. So assigning anyone
Supabase Read-Only access to the project grants them broad read access to the database. That is a
platform/admin-plane trust boundary, not UCPE application intent: assign it only to someone you
would let read every table.

Any other difference is a finding and fails the proof: production's structure and the migrations
disagree there. That includes every privilege path into the app the migrations do not declare,
whoever made it: an API role becoming a member of another role or gaining SUPERUSER, BYPASSRLS or
the like; any setting on an API role but a timeout (one setting can turn the seals off for every API
session); any role but Supabase's superuser and `postgres` able to act as `postgres`, an app role or
an API role, or holding a predefined role that reads or writes every table or the server's files;
any new superuser; a parameter grant to an API or app role; a parameter grant of `ALTER SYSTEM` to
any role at all, `postgres` included (once the server reloads, the value it sets holds for every
session, the app's included; only your exact exception would accept one; a parameter's default
access, which PostgreSQL writes beside any grant, is no grant and is not compared); a setting for
every role; and any role whose name is not a plain lowercase identifier (the proof reads names back
from text, so a name that could be misread fails instead). **A proof may say FAIL for privilege
paths Supabase itself made** (for example one of its service roles able to act as an API role, a
read-only role that reads every table, or a setting on PostgREST's `authenticator`): each is a
finding Claude reports to you by name, for you to decide on, not a broken restore. The first proof
(2026-10-07) found eight such paths, and you ruled them exact exceptions. The rerun (2026-10-08)
then held `supabase_storage_admin` to an API role's rules and found a ninth, its two settings, which
you also ruled exact. Any other one is a new finding. The report names every finding, and nothing is
changed or reclassified to hide one: only your exact ruling turns one into `accepted`, and an
accepted one is still listed.

## Stop rules

- If the proof says `REFUSED_EXPORT` because of `DIGEST_MISMATCH`, `DATA_ENTRY` or a `PASSWORD_`
  kind, delete both files and run steps 4 and 5 again exactly, once. If the same kind comes back,
  stop: the commands make it every time. For any other refusal kind, stop at once: running the
  same commands again gives the same files. Claude adjusts the tooling and reruns the proof on the
  files you already made. Never edit the files by hand.
- If a command asks for anything but the password, or fails, stop and tell Claude its error line
  only.

## What this does not prove

- **The data.** Full-data custody (encrypted dumps, an independent destination, retention) is a
  later ruling: DP-D option 3.
- **An independent copy.** The export sits on your Mac only, as long as you keep it.
- **What the two commands do not export:** default privileges set for all schemas at once (an
  `ALTER DEFAULT PRIVILEGES` with no `IN SCHEMA`), a role's settings for one database only
  (`ALTER ROLE … IN DATABASE … SET`), a setting applied to every role at once (`ALTER ROLE ALL
  SET …`, which `pg_dumpall --roles-only` does not write and the proof therefore cannot compare;
  an export that carries either is refused),
  the database's own settings, every schema but `public` (Supabase's `auth`, `storage`,
  `extensions` and the rest), and a role's comment, security label and password expiry, which
  carry no privilege and are not compared. Supabase's settings outside the database (the API keys,
  the JWT secret, network rules) are not in any export.
