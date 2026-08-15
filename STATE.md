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

**Open decisions** — none blocking.

**NEXT ACTION** — Packet 1 (T3, owner-gated): confirm `RESOLVER_LIMIT`, verify the hourly
outcome resolver is succeeding, apply outstanding Supabase migrations, and get
calibration `sample_gate` advancing off `NO_SAMPLES`. Highest-value item in the project:
calibration needs elapsed wall-clock time to accumulate samples, so every day of delay is
a day the engine cannot demonstrate it is calibrated. See `.work/OWNER_ACTION.md`.
