# STATE

Updated: 2026-08-15

**Goal** — Complete UCPE v1: a production-quality, analysis-only crypto probability engine.

**v1 scope** — resolver + calibration activation · deploy the GitHub↔HF gap · full
hard-gating · horizon-specific probability modelling · live smokes · release-gate closure.
**Out of v1 (owner decision 2026-08-15):** Phase 2D.3B derivatives first-write. Preserved
in Git on `preserve/2d3b-readiness-packet`; must not block v1.

**Repo** — canonical working copy is this directory, `/Users/kha/Documents/Kha-app/UCPE`.
`origin` = `github.com/tranbeny053-hub/v83-stock-cron` (CI + cron).
`hf` = the Hugging Face Space — **pushing to `hf` is a deployment (T3)**.
Pre-Git copy preserved read-only at `/Users/kha/Documents/Kha-app/v8-crypto-api-clean`;
proven byte-identical to `676fafb` except the four files now committed. Retire it after v1.

**Last green** — `main` @ `676fafb` · `VERIFY=PASS` 754 passed, ruff clean, 3/3 scanners.

**Branches** — `main` (= origin, undeployed work ahead of production) ·
`preserve/2d3b-readiness-packet` · `chore/operating-model`. Nothing pushed.

**Production** — HF Space live at `30d4982`, healthy, fingerprint
`UCPE-W4D3-OPS-2A0-20260622-A`. `origin/main` is **44 files / +10,098 / −350 ahead** of it,
entirely the default-off derivatives shadow track.

**Live operations (verified 2026-08-15, read-only)** — all 7 GitHub workflows active.
Outcome resolver: **670 runs, last 100 all successful**, most recent 09:40. Its
config-validation step passes, so `SUPABASE_DB_URL` is set and `RESOLVER_LIMIT` is valid;
and since the resolver exits non-zero on any exception, migrations **0003 and 0004 are
proven applied**. Source-integrity guard green. *This corrects the strategic audit, which
inferred the resolver was blocked on an unset secret — it is not, and the calibration
clock is already running.*

**Open decisions** — none blocking.

**NEXT ACTION** — Packet 1, owner-gated (`.work/OWNER_ACTION.md`): run
`sql/migration_status_readonly.sql` in the Supabase SQL editor to determine which of
migrations 0002/0005/0006/0007 are outstanding and how far calibration has accumulated;
then authorize the two T3 actions (push branches to `origin`; deploy the 44-file gap to
`hf`). Applying any migration is T4 and unauthorized.
