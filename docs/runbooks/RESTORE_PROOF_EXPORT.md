# Runbook: the structure export for the restore proof (DP-D)

**Status: PREPARED, NOT RUN.** Owner ruling DP-D=2 (2026-10-05): structure first. This card is ready.
Running it is the next owner boundary: nothing here has touched the production database.

The recovery drill (governing plan §12.1 and §23, "Backup") needs a scratch restore that proves the
declared recovery set. Its first half is the structure: the schema, the roles and grants, and the
seals. This card is the owner's whole part of that half: **two read-only exports, run once, by you,
on your Mac.** Claude does the rest locally, against scratch PostgreSQL 17.6, and never touches the
production database.

What the two files hold:
- `schema.sql`: the `public` schema's structure only (`--schema-only`): tables, columns, constraints,
  indexes, the append-only seals and their functions, row security, the RPCs and every grant. **No
  table row**, so nothing from the section-5A window can leave the database.
- `roles.sql`: the cluster's roles and memberships (`--roles-only`), **with no password**
  (`--no-role-passwords`).

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
2. **Check the tools.** Both lines must say 17.6 or a later 17.x:
   ```bash
   pg_dump --version
   ```
   ```bash
   pg_dumpall --version
   ```
3. **Copy the connection template.** In the Supabase dashboard, open the project and click
   **Connect**. In "Connect to your project", open **Connection String**, choose the type **URI**
   and the method **Session pooler**, and copy the string. In a text editor, delete
   `:[YOUR-PASSWORD]` from it, so that it reads `postgresql://postgres.<ref>@<host>:5432/postgres`.
   Each command below asks for the password itself, so it never sits in a variable, a file or your
   shell history.
4. **Run the two exports**, pasting the edited string where it says `<CONNECTION>`. Each asks for
   the password once:
   ```bash
   pg_dump --schema-only --schema=public --file=schema.sql --password --dbname='<CONNECTION>'
   ```
   ```bash
   pg_dumpall --roles-only --no-role-passwords --file=roles.sql --password --dbname='<CONNECTION>'
   ```
5. **Take the two digests**, and send Claude the folder path and these two lines only:
   ```bash
   shasum -a 256 schema.sql roles.sql
   ```

## What Claude does with them (local only)

```bash
python scripts/restore_proof/prove.py --pg-bin <PostgreSQL 17.6 bin> --export ~/ucpe-restore-export \
    --work <a fresh scratch folder> --report <report.json>
```

1. It checks both digests against yours, then **refuses the export, and restores nothing**, unless
   it is exactly what the two commands make: a data entry, a COPY block, a password clause or
   hash, or any psql meta-command but the `\restrict` pair is a refusal (`gate.py`).
2. It builds a scratch cluster from the migrations, as every migration rehearsal does, and restores
   your export into a second one. Both are private (no network listener) and deleted at the end.
3. It compares the two catalogs item by item and writes one report: your files' digests and
   versions, every restore error and every difference. It reads no table row.

`RESTORE_PROOF=PASS` means the structure restores into PostgreSQL 17.6 and equals what the
migrations declare. Two kinds of difference are reported without failing:
- **operational**: the documented credential steps, LOGIN on `ucpe_space_db`
  (`SPACE_DB_CUTOVER.md`) and on `ucpe_resolver` (`RESOLVER_CUTOVER.md`);
- **platform**: Supabase's own default privileges for its roles, and a platform role's own setting
  that vanilla PostgreSQL refuses.

Any other difference is a finding: production's structure and the migrations disagree there. The
report names it, and nothing is changed to hide it.

## Stop rules

- If the proof says `REFUSED_EXPORT`, delete both files and run steps 4 and 5 again exactly. Never
  edit the files by hand.
- If a command asks for anything but the password, or fails, stop and tell Claude its error line
  only.

## What this does not prove

- **The data.** Full-data custody (encrypted dumps, an independent destination, retention) is a
  later ruling: DP-D option 3.
- **An independent copy.** The export sits on your Mac only, as long as you keep it.
