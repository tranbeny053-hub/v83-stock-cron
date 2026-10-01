# Machine credentials: issue, rotate, revoke (F1)

Status: **procedure only. Nothing here has been done.** Migration 0013 is not applied, no credential
exists, and the route is off. Every step below is an owner action on the production database, which
makes it a **T4, authorized by the owner for that specific step**. UCPE never issues a credential,
never stores, logs or returns a credential value (a presented value is only hashed in memory,
during its own request), and never writes to this table.

## What the design guarantees

- **Rotation without a restart.** Credentials live in the database table
  `public.automation_credential` (migration 0013), not in the Space's environment. The route reads
  the table on **every request, with no cache**. A new credential therefore works from the very next
  request, and the old one keeps working until it is revoked, so the two overlap. The Space is never
  restarted for a rotation. Availability still depends on the database: a registry that cannot be
  read refuses every request (below).
- **Immediate revocation.** Revoking a row refuses the very next request that presents that
  credential, including a replay of an earlier request. A call that had already passed
  authentication when the revocation landed finishes normally, under its own deadline contract
  (`RADAR_EVIDENCE_V1.md` section 8): revocation is not retroactive.
- **Fail closed.** If the table cannot be read (database unreachable, migration not applied, a
  malformed row), the route authenticates nothing and answers 503 `LEDGER_UNAVAILABLE`.
- **Proof.** Unit tests cover these properties (`tests/automation/test_credentials.py`,
  `tests/automation/test_service_route.py`). On every pull request that touches the automation
  package, the migrations or the apply route (the rehearsal workflow's path filter), the real
  PostgreSQL rehearsal (`scripts/migration_0013_rehearsal/probe_app_sql.py`) drives the production
  registry class through rotation and revocation, with no restart.

By comparison, the kill switch (`UCPE_AUTOMATION_ENABLED`) lives in the Space's environment.
Changing it restarts the Space, so revoking the credential is the faster and gentler way to stop a
consumer.

## The rules

1. **One credential per consumer and period.** Its id matches `^[a-z0-9][a-z0-9-]{2,31}$`, e.g.
   `uor-radar-2026-10`. **Never reuse an id**, even after revocation.
2. **Never store the value in UCPE.** Only the lowercase hex SHA-256 of the value goes into the
   table. The full token `ucpea.<id>.<value>` goes to the consumer's secret store, referred to by
   name only.
3. **Never update a digest in place.** A rotation is always a new row with a new id. Changing a
   digest would cut the consumer off at once.
4. **Never un-revoke.** A revoked row stays revoked forever: it is the audit record of that
   credential. The table enforces that a `REVOKED` row carries its revocation time and an `ACTIVE`
   row has none, so reactivating a row needs two deliberate changes. Do not make them: issue a new
   credential instead.
5. **Never delete a row.**

## Issue a credential (owner, on their own machine, then the Supabase SQL editor)

1. Generate the value locally. It never leaves the owner's machine except into the consumer's
   secret store:
   ```bash
   python3 -c "import secrets; print(secrets.token_urlsafe(32))"
   ```
   This prints 43 URL-safe characters.
2. Compute its digest locally:
   ```bash
   python3 -c "import hashlib, getpass; print(hashlib.sha256(getpass.getpass('value: ').encode('ascii')).hexdigest())"
   ```
3. In the Supabase SQL editor, insert the row. Paste the digest, never the value:
   ```sql
   INSERT INTO public.automation_credential (credential_id, secret_sha256, status, not_after_utc)
   VALUES ('uor-radar-2026-10', '<64 lowercase hex digest>', 'ACTIVE', '2027-01-01T00:00:00Z');
   ```
   `not_after_utc` is optional; it must be later than the insertion time.
4. Give the consumer the token `ucpea.uor-radar-2026-10.<value>`, through its secret store only.

## Rotate (no restart; the credentials overlap)

1. Issue the new credential exactly as above, under a **new** id. Both credentials now work.
2. Move the consumer to the new token.
3. Wait until the consumer has finished every request it began under the old credential. Its
   retries of those requests must still use the old token. Idempotency is per credential
   (`RETENTION_AND_IDEMPOTENCY.md`): a retry under the new token would be a new request and start a
   new analysis. For UOR, which never retries inside a cycle, one full cycle plus a few minutes is
   enough: a request is answered within its deadline (at most 60 s) plus the recording timeouts.
4. Revoke the old credential (next section).

The quota is counted per credential. The new credential starts with a fresh quota, and during the
overlap both quotas apply, so keep the overlap short.

## Revoke (takes effect on the next request)

```sql
UPDATE public.automation_credential
   SET status = 'REVOKED', revoked_at_utc = now()
 WHERE credential_id = 'uor-radar-2026-10' AND status = 'ACTIVE';
```

The command must report exactly one row updated.

## Check the registry without reading a digest

```sql
SELECT credential_id, status, not_after_utc, created_at_utc, revoked_at_utc
  FROM public.automation_credential
 ORDER BY created_at_utc;
```

The table's row-level security is on and it has no policy. Anon, authenticated and service_role
hold no privilege on it, so only the owning role (the SQL editor, and the Space through
`SUPABASE_DB_URL`) can read it.

## If a value may have leaked

Revoke that credential at once (above). Then issue a replacement under a new id. There is no need to
restart anything, and no need to change `UCPE_AUTOMATION_ENABLED`.
