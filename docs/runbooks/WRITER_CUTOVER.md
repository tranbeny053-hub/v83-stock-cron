# Runbook: switch the REST writer to its least-privilege role (E3 and E4)

The live writer saves with Supabase's service-role key today. After this switch, it saves as
`ucpe_api_writer`, which can do only what the analysis service needs. These are owner-only steps,
because they create and enter secrets. Never paste a key or a token into chat, a file in this
repository, or a log.

**Preconditions:**
- release UCPE-PROD-WA-20261003-A or later is live (the two-header writer);
- migrations 0016 and 0017 are applied (the role, its grants, and the forecast bundle function);
- the owner's decisions (2026-10-03): E3-A YES (this plan), E3-B 30 days (the token's lifetime).

**What is already proven:**
- **The import format, from Supabase's own sources** (re-read 2026-10-03):
  - the CLI's `supabase gen signing-key --algorithm ES256` prints one private JWK, as compact JSON,
    with the members kty, kid (a random UUID), use, key_ops, alg, ext, d, crv, x, y;
  - the dashboard's "Import an existing private key" box checks kty "EC", crv "P-256", and x, y
    and d, then sends the key unchanged;
  - the Management API takes exactly those members, and takes the kid only as a UUID;
  - the signing-keys guide: a minted token's kid header must be the imported kid; its claims are
    role (an existing Postgres role) and exp (in the future; prefer short-lived tokens); sub is an
    optional UUID naming a user.
- **The helper, `scripts/writer_signing_key.py`, writes exactly that JWK.** Its tests pin the
  members, their order and the compact JSON. Three independent checks agree that the JWK and the
  PEM it signs with are one key: P-256 arithmetic written out in the test, OpenSSL, and Node's JWK
  import (the crypto the CLI itself uses). The token verifies with the JWK's public half alone.
- **The rehearsal behind a real PostgREST** (P3-PRIV-R, criterion J1):
  - the writer token, minted by the helper's own builder, runs as ucpe_api_writer, and the writer
    saves;
  - forged, expired and unknown-key tokens are refused;
  - **a service_role token signed by the same key is accepted.** So the signing key stays with
    you, and only the 30-day writer token ever goes into the Space.
- **Rotating is safe for this repository's code.** Nothing here checks tokens against the legacy
  JWT secret, and it has no Edge Functions: those are the two warnings in Supabase's rotate dialog.
- **Not yet proven:** the hosted gateway accepting the pair. The first natural receipt after the
  switch is that proof.

## The steps

Supabase throttles key changes for about 5 minutes. If the dashboard answers "Please wait for …",
wait that long and click again.

1. **Make the key, on your Mac** (Terminal):
   ```bash
   cd /Users/kha/Documents/Kha-app/UCPE && .venv/bin/python -m scripts.writer_signing_key generate
   ```
   It prints the kid and two files in `~/ucpe-keys` (the folder and both files are owner-only):
   - `ucpe-writer-signing.jwk.json`, the file you import;
   - `ucpe-writer-signing.pem`, the key the token is signed with.

   Both files are secret, and Supabase never gives the key back. Keep a backup copy of both files
   in your password manager. Never put them in a repository, a chat, GitHub or the Space.
2. **Supabase dashboard → your project → Project Settings → JWT Keys** (the "JWT Signing Keys"
   page, `https://supabase.com/dashboard/project/<your project>/settings/jwt`):
   1. If it shows "Start using JWT signing keys", click **Migrate JWT secret**, then **Migrate JWT
      secret** again in the dialog. Today's JWT secret keeps signing, and Supabase adds a standby
      key.
   2. If a key's status reads **Standby key**: its ⋮ menu → **Move to previously used**. Only one
      standby key can exist, and Supabase's own one is never used.
   3. Click **Create Standby Key**. Keep "ES256 (ECC)", and tick **Import an existing private
      key**. Copy the JWK with:
      ```bash
      cd /Users/kha/Documents/Kha-app/UCPE && .venv/bin/python -m scripts.writer_signing_key copy-jwk
      ```
      Paste it into the box (⌘V), then click **Create standby key**.
   4. **Check the kid.** The new standby key's ⋮ menu → **View key details**. The "kid" in its
      "Public key set" must be exactly the kid that step 1 printed. If it is not, stop and tell
      Claude: do not rotate, do not mint.
   5. Click **Rotate keys**, tick each confirmation box, then click **Rotate signing key**. Today's
      key becomes a "Previous key" and stays trusted, so the live app keeps working.
3. **Publishable key: Project Settings → API Keys**, the section "Publishable key". Copy the
   `sb_publishable_…` key. If there is none, click **Create new API keys**, then **Create keys**.
4. **HF Space → Settings → Variables and secrets → New secret:** the name
   `SUPABASE_PUBLISHABLE_KEY`, and the publishable key as the value.
5. **Mint the writer token:**
   ```bash
   cd /Users/kha/Documents/Kha-app/UCPE && .venv/bin/python -m scripts.writer_signing_key mint
   ```
   It checks the two files are one key, then signs a 30-day token with the JWK's kid. The token
   goes straight to the clipboard: it is never shown. The command prints only the kid, the role
   and the expiry date.
6. **HF Space → Settings → Variables and secrets → New secret:** the name `SUPABASE_WRITER_JWT`,
   and paste the token as the value. The Space restarts.
7. Clear the clipboard:
   ```bash
   pbcopy < /dev/null
   ```

Keep `SUPABASE_SERVICE_ROLE_KEY` for now. The H2-safe rollback target still authenticates with
it. The writer switches only when both new secrets are present: with just one, it keeps the
service-role key.

## How it is verified (no verification traffic)

- **The next natural USER_REQUESTED analysis.** Its `persistence_receipt` must say SAVED. Claude
  reads it passively from the Space logs. No analysis is ever run to check.
- **Supabase dashboard, API logs:** the writer's requests run as `ucpe_api_writer`.
- **If the receipt is NOT_SAVED or COMMIT_UNKNOWN after the switch:** delete the secret
  `SUPABASE_WRITER_JWT`. The Space restarts and the writer is back on the service-role key. Then
  tell Claude.

## Afterwards

- **Every 30 days, before the printed expiry:** run step 5 again, and replace the secret
  `SUPABASE_WRITER_JWT` with the new token.
  - An expired token makes every save fail: the receipts turn NOT_SAVED or COMMIT_UNKNOWN, and the
    circuit opens. Analyses are still served.
  - The signing key stays the same.
- **Never revoke the legacy JWT secret** (a "Previous key" now). The service-role key is signed by
  it, and that key stays in use until D6.
- **Optional tidy-up:** Supabase's unused key from step 2b can be revoked (⋮ → Revoke key).
- **If `~/ucpe-keys` is ever exposed:** tell Claude. The fix is a new key rotated in, the exposed
  key revoked, and a new token.
- **D6, later.** Once the switch has held for a while:
  - delete `SUPABASE_SERVICE_ROLE_KEY` from the Space;
  - a later migration (a T4) narrows service_role's grants on core evidence.
