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
Outcome resolver: 670 runs, last 100 all successful. Source-integrity guard green.
**Database: all 7 migrations (0001–0007) APPLIED. No migration work is required.**
965 predictions, 813 resolved outcomes (DOWN 376 / UP 327 / TIMEOUT 110).

**Prediction generation is traffic-driven, not scheduled.** A prediction row is written
only as a best-effort background side-effect of a session-gated `/v1/analyze` or
`/v1/analyze_batch` call (`app.py:164,185` → `analysis_service.py:510`). No scheduled
workflow calls it: keepalive GETs `/` only; the other two schedules resolve outcomes and
check source integrity. So `predictions_last_7d = 0` means **no operator used the app
since 2026-08-05 04:25:18Z** — the month spent on UABO. It is not a fault.

**CI has never run** (`ci.yml` total_count 0). It triggers only on `push` to `codex/**`
or on `pull_request`; the two pushed branches match neither. Clean-room verification of
this repository has never actually executed.

**Calibration — MEASURED (verified 2026-08-15, read-only production query)**
Default cohort **806 samples → `MEASURED`** (threshold ≥500). Nothing is lost to data
quality: `excluded_prediction_not_live = 0`, `excluded_outcome_not_live = 0`,
`excluded_bad_label = 0`. The only exclusions are 7 correctly-cohorted rows
(5 `CONTROLLED_SMOKE` + 2 `SCHEDULED_SHADOW_EVIDENCE`), so the derivatives smoke rows are
**already reclassified** — the contamination query returned no rows.
Single `model_version=phase1a-wave4b0` and `methodology_version=heuristic-v1-wave4b0`
across all 806 → **no `VERSION_MIX_WARNING`**. A clean single-version sample.

Per-timeframe, all `WARMING_UP` (100–299): 15m 172 · 4H 172 · 1H 165 · 1D 163 · 1W 134.
**1M has zero resolved outcomes** (its horizons sit among the 152 still-unresolved).
So unscoped reports are MEASURED; per-timeframe reports warn; per-symbol will warn more.

*This is the second time live evidence beat the documentation: the strategic audit
assumed calibration was stuck at `INSUFFICIENT_SAMPLE`. It is at `MEASURED`.*

**Open decisions** — none blocking. DEPLOY not authorized. PR #1 open, not merged.

**NEXT ACTION** — the product question is now answerable and is the real v1 work: read the
actual calibration report for those 806 samples (Brier score, reliability buckets,
top-label hit rate) and judge whether the stated probabilities are honest. Blocker to
check first: `build_operator_repository` needs `SUPABASE_DB_URL`; the Supabase REST
repository raises `NotImplementedError` for calibration reads. If the HF runtime is
configured for REST only, production cannot serve `/v1/calibration` even though the data
exists. Verify HF runtime configuration before assuming the endpoint works.
