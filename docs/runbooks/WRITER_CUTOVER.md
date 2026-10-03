# Runbook: switch the REST writer to its least-privilege role (E3 and E4)

The live writer saves with Supabase's service-role key today. After this switch, it saves as
`ucpe_api_writer`, which can do only what the analysis service needs. These are owner-only steps,
because they create and enter secrets. Never paste a key or a token into chat, a file in this
repository, or a log.

**Preconditions:**
- release UCPE-PROD-WA-20261003-A or later is live (the two-header writer);
- migrations 0016 and 0017 are applied (the role, its grants, and the forecast bundle function);
- the owner has decided E3-A (this plan) and E3-B (the token's lifetime).

**What is already proven:**
- **Supabase's documents** (the signing-keys guide): you import your own key, rotate it in, then
  sign ES256 tokens with its kid and the role and exp claims, preferring short-lived tokens.
- **The rehearsal behind a real PostgREST** (P3-PRIV-R, criterion J1):
  - a writer token signed this way runs as ucpe_api_writer, and the writer saves;
  - forged, expired and unknown-key tokens are refused;
  - **a service_role token signed by the same key is accepted.** So the signing key stays with
    you, and only the short-lived writer token ever goes into the Space.
- **Not yet proven:** the hosted gateway accepting the pair. The first natural receipt after the
  switch is that proof.

## The steps

1. **Generate the signing key on your own machine, outside this repository:**
   ```bash
   mkdir -p ~/ucpe-keys && chmod 700 ~/ucpe-keys && openssl ecparam -name prime256v1 -genkey -noout -out ~/ucpe-keys/ucpe-writer-signing.pem
   ```
   Keep the file offline, for example in your password manager. It never goes into this repository,
   the Space, GitHub or a chat.
2. **Supabase dashboard, JWT signing keys:**
   - import that private key, in the format the dashboard asks for;
   - note its key ID (the kid);
   - rotate it in.
   Today's key becomes "previously used" and stays trusted, so the live app keeps working.
3. **Supabase dashboard, API keys:** create a publishable key (`sb_publishable_…`) if there is none.
4. **Mint the writer token** from your key, with the lifetime of E3-B. 30 days is 2592000 seconds:
   ```bash
   cd /Users/kha/Documents/Kha-app/UCPE && .venv/bin/python -c "import os; from scripts.privilege_rehearsal import es256; print(es256.mint(os.path.expanduser('~/ucpe-keys/ucpe-writer-signing.pem'), 'ucpe_api_writer', kid='YOUR-KID', lifetime=2592000, subject='ucpe-writer'), end='')" | pbcopy
   ```
   The token goes straight to your clipboard and is never shown.
5. **HF Space, Settings, Variables and secrets:**
   - add the secret `SUPABASE_PUBLISHABLE_KEY` (the publishable key);
   - add the secret `SUPABASE_WRITER_JWT` (paste the token);
   - the Space restarts.

   Keep `SUPABASE_SERVICE_ROLE_KEY` for now. The H2-safe rollback target still authenticates with
   it. The writer switches only when both new secrets are present: with just one, it keeps the
   service-role key.

## How it is verified (no verification traffic)

- **The next natural USER_REQUESTED analysis.** Its `persistence_receipt` must say SAVED. Claude
  reads it passively from the Space logs. No analysis is ever run to check.
- **Supabase dashboard, API logs:** the writer's requests run as `ucpe_api_writer`.
- **If the receipt is NOT_SAVED or COMMIT_UNKNOWN after the switch:** delete the two new secrets.
  The Space restarts and the writer is back on the service-role key. Then tell Claude.

## Afterwards

- **Rotation.** Mint a new token (step 4) and replace `SUPABASE_WRITER_JWT` before the old one
  expires.
  - An expired token makes every save fail: the receipts turn NOT_SAVED or COMMIT_UNKNOWN, and the
    circuit opens. Analyses are still served.
  - The signing key itself stays the same.
- **D6, later.** Once the switch has held for a while:
  - delete `SUPABASE_SERVICE_ROLE_KEY` from the Space;
  - a later migration (a T4) narrows service_role's grants on core evidence.
