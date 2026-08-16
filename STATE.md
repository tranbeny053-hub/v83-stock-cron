# STATE

Updated: 2026-08-16

## Recovery block — read this first on resume
```
LOOP_STATE=PAUSED_AWAITING_OWNER (autonomous work complete; stopped at a genuine boundary)
CURRENT_MILESTONE=Production Live-Smoke + Release-Gate Closure (owner-authorized 2026-08-16)
CURRENT_BRANCH=feat/production-live-smoke (2 commits, unpushed; main still 1 docs commit ahead of origin)
LAST_GREEN_SHA=d97b553
LAST_VERIFY=PASS 785 passed, ruff clean, 3/3 scanners · 2026-08-16
CODEX_PENDING=NONE
GPT_REQUEST_ID=NONE
GPT_THREAD_URL=NONE
GPT_REQUEST_STATE=NONE
OWNER_BOUNDARY=3 batched decisions open — (1) Phase B access code, (2) Wave 4B0 write-smoke
  product decision, (3) T3 push of feat/production-live-smoke. None crossed.
NEXT_ACTION=owner answers the batched boundary; nothing is half-applied
```
Update this block on every pause, every milestone change, and every GPT consultation.
`GPT_REQUEST_STATE` ∈ `NONE` · `DRAFTED` · `SENT_WAITING_RESULT` · `COMPLETED_RESULT_SAVED` ·
`SKIPPED_UNAVAILABLE`.

## Operating model V2 — anchored 2026-08-16
- **Claude Code holds the loop.** **Codex `exec` is the implementation and debugging lane.**
  **Deterministic tooling is the verification authority** — `./verify.sh`, Git, and the three
  safety scanners decide pass/fail; no model adjudicates a gate.
- **GPT-5.6 Sol via Claude Code Chrome is an exceptional sidecar only**, outside the normal
  loop, default budget **≤1 consultation per milestone**, advisory and granting no authority.
- **No OpenAI API fallback, no API key, ever. No transcript relay.** GPT sees only the
  compact gitignored `.work/gpt-request.md` (≤2 KB) and returns `.work/gpt-result.md` (≤1 KB).
- **The owner is the sole authority** for product and scope decisions, T3/T4 boundaries,
  secrets, spend, and release.
- **PAUSE/RESUME semantics live in `CLAUDE.md`.** The recovery block above plus Git plus
  `.work/` are sufficient to resume after abrupt quota exhaustion **without repeating any
  completed Codex delegation or GPT consultation**.
- **UABO remains retired and frozen. Change A remains deployed and closed. Change B has NOT
  started.**

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

**Last green** — `main` @ `1b06aab` · `VERIFY=PASS` 776 passed, ruff clean, 3/3 scanners.
Deployed production build is `e6ee23c`; `main` is one pin commit ahead of it by design.

**Change A is merged to GitHub (2026-08-16).** PR #2 `feat/calibration-truth` → `main`,
head `44ca1d9`, CI green on that exact head, merged as merge commit
`e6ee23cc81274c2ad68e247293738bc8e81f082a` = `origin/main`. 20 files, +1252 −28. The
merged tree is byte-identical to the PR head. **Nothing was deployed** — `hf` was verified
unchanged at `30d4982` before and after, and no workflow references Hugging Face or
triggers on push to `main`, so merging cannot deploy.

**Branches** — `main` = `a59b295` (one docs-only checkpoint ahead of `origin/main`) ·
`chore/gpt-sidecar` (merged by PR #4, kept) · `chore/deploy-pin-change-a` (merged by PR #3) ·
`feat/calibration-truth` (merged by PR #2) · `preserve/2d3b-readiness-packet` ·
`chore/operating-model`. Production remains `e6ee23c`, which is an ancestor of `main`.

**Production — Change A IS DEPLOYED (2026-08-16).** HF Space live at `e6ee23c`,
`stage=RUNNING`, `cpu-basic`, healthy. The prior build `30d4982` was a strict ancestor,
24 commits behind, so the deploy was the expected fast-forward.

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

**CI has now run.** `ci.yml` triggers on `push` to `codex/**` and on `pull_request`; PR #2
supplied the first real trigger. Check run `test` completed `success` on head `44ca1d9`.
Clean-room verification of this repository has now actually executed.

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

**Gate** — `./verify.sh` is now materially equivalent to GitHub CI: ruff, full pytest,
`validate_schemas.py`, `manual_smoke.py`, and all 3 safety scanners. **3.84 s**, one-line
output, first-causal-failure preserved. A local PASS is now as strong as a green CI run.

**HF production (read-only, 2026-08-15)** — Space `RUNNING`, `cpu-basic`, sha `30d4982`
(= baseline), uptime ~2.5 days. `/healthcheck` 200; `/v1/build-info` 200 with fingerprint
`UCPE-W4D3-OPS-2A0-20260622-A`. `/v1/system_status` and `/v1/calibration` both return
**401 with a well-formed UNAUTHORIZED body — the route is registered and its auth gate
works** (not 404, not 500).

**Production CAN serve calibration — configuration proven end to end (2026-08-16).**
Owner confirmed the HF Space secret key `SUPABASE_DB_URL` is PRESENT. Every file in the
calibration path is **byte-identical** between the deployed build `30d4982` and `main`:
`calibration/service.py`, `calibration/metrics.py`, `persistence/repository.py`,
`persistence/prediction_origin.py`, `config/settings.py`, `api/app.py`,
`api/calibration_endpoint.py`. So `build_operator_repository` selects
`SupabasePersistenceRepository`, the endpoint's `_EXPECTED_REPOSITORY` guard
(`SUPABASE_POSTGRES`) passes, and it reads the same database the resolver writes to.
Only the live HTTP invocation is unverified (session-gated; not circumvented).

**But `/v1/calibration` will NOT report MEASURED.** The endpoint never issues an unscoped
query: `calibration_endpoint.py:118` iterates `SUPPORTED_TIMEFRAMES` =
`("15m","1H","4H","1D","1W","1M")` and builds one scoped report per timeframe. So
production will report **WARMING_UP ×5 and NO_SAMPLES for 1M** — not MEASURED. The
806/MEASURED figure is the unscoped aggregate, which no endpoint requests. Reaching
MEASURED per timeframe needs ≥500 resolved outcomes in a single timeframe (currently
134–172), i.e. roughly 3× more operator traffic per timeframe.

**Deploy packet for Change A — prepared, verified, unpushed (2026-08-16)**
Branch `chore/deploy-pin-change-a`, **local only, never pushed**, `VERIFY=PASS` 776.
The pin commit is `1712469`; `a4bd2ac` and this checkpoint are `STATE.md`-only commits on top.
The source-integrity guard (`.github/workflows/source-integrity-guard.yml`, cron `27 */2 * * *`
→ `scripts/source_integrity_guard.py`) is a **composite pin** held as tracked literals in
`ops/hf_runtime_baseline.json`: the HF `refs/heads/main` commit SHA, SHA-256 of eleven
guarded source blobs read from that HF commit, plus build identity and frontend asset
tokens. It runs in GitHub Actions and reads the manifest from the **GitHub** checkout; it
queries HF only for its ref SHA and blobs. So the pin update belongs on GitHub `main`
only — never in the HF repo. No secret supplies any expected value.

The packet changes exactly five literals: `hf_main_sha` `30d4982` → `e6ee23c`, and the four
guarded digests Change A alters (`schemas/response.schema.json`, `api/analysis_service.py`,
`api/app.py`, `derivatives_intel/runtime.py`). `config/build_info.py` is byte-identical
across both builds, so the **fingerprint does not move** — drift would come from the SHA
and blob layers, not identity. The test's `PIN_SHA`/`CURRENT_DELTA_PATHS` mirror follows;
non-empty-delta coverage is retained by `test_shallow_checkout_advisory_is_non_failing`.

**Order held: deploy first, pin second — all four steps executed 2026-08-16.**
(1) `e6ee23c` pushed to `hf` (fast-forward); (2) health confirmed; (3)
`chore/deploy-pin-change-a` landed on GitHub `main` by PR #3; (4) guard dispatched.
The `PIN_DRIFT` window between (1) and (3) opened and closed as designed and was never
observed as a failure, because the guard was only dispatched after the pin landed.

**PIN CLOSED — PR #3 merged.** `chore/deploy-pin-change-a` @ `7290a0e` → `main`, CI check
run `test` = `success` on that exact head, merged as merge commit
`1b06aab32ed560cf890609ef9c722862c71ebf6c` = `origin/main`. The PR contained exactly three
files — `ops/hf_runtime_baseline.json`, `tests/scripts/test_source_integrity_guard.py`,
`STATE.md` — no source, schema, gate, or quant change. `mergeable_state` was `clean`.

**SOURCE-INTEGRITY GUARD — HEALTHY, exit 0** (`workflow_dispatch` run `31941852536`,
head `1b06aab`). `pinned_hf_main_sha` == `hf_main_sha` == `e6ee23c`, so **no `PIN_DRIFT`
remains**. Three probe rounds all `HEALTHY`; `critical_source_match: true`;
`mismatched_path_names: []`; `frontend_asset_match: true`; live fingerprint == intended.

*Correction to the earlier prediction:* the advisory came back
**`SCHEDULER_DIVERGENT_FROM_PIN`, not `SCHEDULER_AHEAD_OF_PIN`.** This is benign and
contract-defined. The guard workflow uses `actions/checkout@v4` with no `fetch-depth`, so
the runner has a depth-1 shallow clone and the ancestry walk in `evaluate_deployment_delta`
raises; `_safe_deployment_advisory` catches it and returns the fallback
(`scheduler_ahead_count: null`, `deployment_delta_paths: []`) — exactly what was observed.
`test_shallow_checkout_advisory_is_non_failing` covers this path, and the advisory
structurally cannot affect Q1: the summary validator raises
`"Integrity summary advisory affected Q1."` if it ever did, and
`test_advisory_internal_failure_cannot_fail_healthy_q1` pins that. So the advisory is
non-failing by contract, not by interpretation. **Expect this advisory on every run until
the workflow sets `fetch-depth: 0`** — not a fault, and not worth a change on its own.

Rollback was pre-authorized but **not used and not needed**. For reference, restoring the
previous build would need
`git push --force-with-lease=refs/heads/main:e6ee23cc81274c2ad68e247293738bc8e81f082a hf 30d4982903e6f44e063616bc3f03f334bd2544e2:refs/heads/main`
plus reverting the five pin literals on GitHub — a force is required because the restore
moves the remote backwards.

**CHANGE A DEPLOYED TO PRODUCTION — 2026-08-16.**
`e6ee23c` is live on the HF Space. Pre-deploy fail-closed checks all passed first:
`origin/main` = `e6ee23c` exactly, `hf refs/heads/main` = `30d4982` exactly, ancestry
confirmed fast-forward, packet diff exactly the five pin literals + test mirror +
`STATE.md`, `./verify.sh` = `PASS` 776.

*First attempt was blocked at the credential boundary and mutated nothing.* `git push hf`
hung ten minutes and transferred zero bytes: `credential.helper` is `osxkeychain` with no
`huggingface.co` entry, so git fell back to an interactive username prompt the harness
askpass never answers. Confirmed with `GIT_TERMINAL_PROMPT=0` →
`fatal: could not read Username for 'https://huggingface.co'`; reproduced with the sandbox
disabled, so not a sandbox effect. **Anonymous read of `hf` works — only write needs
credentials**, which is why every `git ls-remote hf` succeeded throughout.
Resolution: the owner ran `hf auth login`, which installs the CLI and writes
`~/.cache/huggingface/token` but **does not configure git over HTTPS**. The push was
completed by bridging that owner-provisioned token to git for the single push via an
inline `credential.helper`. **No token was printed, stored in the repo, or modified.**
If `osxkeychain` still lacks a `huggingface.co` entry, a future push needs the same bridge
or a one-time `hf auth login --add-to-git-credential`.

**Deploy evidence — restart proven independently of the fingerprint.** `hf refs/heads/main`
= `e6ee23c`; HF Spaces API reports `sha=e6ee23c`, `stage=RUNNING`, `cpu-basic`;
`uptime_seconds` collapsed **278648 → 28** and resumed climbing, so the runtime genuinely
rebuilt and restarted. The build fingerprint stayed
`UCPE LIVE BUILD · W4D3-OPS-2A0-20260622-A` exactly as predicted — `config/build_info.py`
is byte-identical across both builds — which is why it was never used as deploy proof.
Health after deploy: `/healthcheck` 200 `status=OK` · `/v1/build-info` 200 · `/` 200 ·
`/v1/calibration` and `/v1/system_status` both **401 `UNAUTHORIZED` with a well-formed
body — routes registered, auth gates intact, not 404 and not 500**.
No rollback was used and none was needed. No DB write, no migration, no secret change.

**CANONICAL HANDOFF CHECKPOINT — CHANGE A DEPLOYMENT CLOSURE COMPLETE (2026-08-16).**
Production `e6ee23c` · GitHub `main` `1b06aab` · guard `HEALTHY` exit 0 · no `PIN_DRIFT`.
Closure boundaries held exactly: **no production DB write, no migration applied, no secret
created or modified, no rollback used, and Change B not started.** The one secret-adjacent
act was *using* the owner's already-provisioned HF token for a single push without printing,
storing, or altering it. Nothing in this closure is pending or half-applied.

**GPT SIDECAR AMENDED INTO THE OPERATING MODEL — 2026-08-16 (T0, docs only).**
`CLAUDE.md` gains two sections — *GPT sidecar* and *Pause and resume* — and `STATE.md`
gains the recovery block above. **No new process file**: still exactly six
(`CLAUDE.md` `AGENTS.md` `STATE.md` `verify.sh` `delegate.sh` `docs/OPERATING_DOCTRINE.md`).
`.work/gpt-request.md` and `.work/gpt-result.md` are gitignored ephemera, not artifacts.
Routing is unchanged — deterministic tool > Codex > Opus > owner — and GPT sits outside the
loop at ≤1 consultation per milestone.

*Smoke test executed once, end to end, and discarded.* A temporary ChatGPT thread was
opened in the owner's logged-in Plus session via Claude Code Chrome; the Advanced menu read
**Model `GPT-5.6 Sol`, Effort High** before anything was sent; a 566-byte non-sensitive
handshake went out and a 450-byte reply came back (`UCPE-SIDECAR-OK` · self-reported
`GPT-5.6 Sol` · one clause on why advice carries no authority). Both limits held (≤2 KB
request, ≤1 KB result). **No OpenAI API and no API key**: no `OPENAI*` environment variable
exists, no key file on disk, the `openai` package is not installed in `.venv`, and the
repository contains no `openai` or `api.openai.com` reference — the only transport was the
browser UI. The smoke thread is **not** project history and is referenced nowhere.

**OPERATING MODEL V2 IS ANCHORED TO GITHUB — PR #4 MERGED (2026-08-16).**
`chore/gpt-sidecar` @ `74af3ce` → `main`, four docs-only commits (`b52f7ca` handoff
checkpoint · `93d9ecd` sidecar + pause/resume · `76eebb0` V2 preservation list · `74af3ce`
T3 pause record), exactly two files changed (`CLAUDE.md`, `STATE.md`), +147 −20. CI check
`CI / test (pull_request)` was **`Successful in 34s` on the exact latest head `74af3ce`**,
`mergeable_state` clean, merged as merge commit
`a59b295aead428fa51667b9e915b02ad7a6c4feb` = `origin/main`. `hf` was `e6ee23c` before and
after — **the merge cannot deploy**: no workflow references Hugging Face and `ci.yml`'s push
trigger is limited to `codex/**`, so nothing fires on push to `main`.

*The push needed the owner.* `git push` is refused by the Claude Code auto-mode permission
classifier and `gh` is not installed on this machine, so the loop paused at the T3 boundary
with `origin` untouched and the owner ran the one-line push in-session. The PR itself was
opened and merged through the GitHub web UI via Claude Code Chrome. If a future session
needs to push, expect the same wall: either the owner runs it, or a Bash permission rule for
`git push` is added.

**Local `main` is one docs-only commit ahead of `origin/main`** — this checkpoint. That is
the established pattern (`b52f7ca` rode along the same way and landed in PR #4); it will
ride along in the next PR. Nothing else is unpushed.

**MILESTONE: PRODUCTION LIVE-SMOKE + RELEASE-GATE CLOSURE — started 2026-08-16.**
Branch `feat/production-live-smoke`, two commits, `VERIFY=PASS` 785 (was 776).

*Change L1 — read-only production smoke (`87fd77a`, T1).* `scripts/production_smoke.py` plus
`tests/scripts/test_production_smoke.py`. **Read-only by construction**: GET only, with a
single `POST /v1/auth/login`, pinned by an AST test that fails if any other write verb or any
analyze path ever appears in the module. Gated behind `UCPE_PRODUCTION_SMOKE_ENABLED`,
mirroring `UCPE_LIVE_SMOKE_ENABLED`, so the suite never reaches the network. Raw bodies are
captured before parsing; headers are never captured; no secret is ever printed.

**PHASE A EXECUTED AGAINST LIVE PRODUCTION — exit 0, 2026-08-16.** Unauthenticated,
read-only, no write, no secret. `/healthcheck` 200 `status=OK`, `uptime_seconds=12154`;
`/v1/build-info` 200, `release_id=UCPE-W4D3-OPS-2A0-20260622-A`, `environment=HF_PRODUCTION`;
`/` 200 serving `/app.js?v=w4c1-ka1-20260621-a`, and **that served bundle contains
`prob_up_pct`, `prob_down_pct`, `prob_timeout_pct` and none of the stale markers**;
`/v1/system_status` and `/v1/calibration` both 401 with a well-formed `UNAUTHORIZED` body.
This is the first time the deployed frontend bundle has been verified from outside the app.
`frontend/index.html` references the same `w4c1-ka1-20260621-a` token production serves, so
source and production agree — **no frontend drift**.

*Change L2 — gate reconciliation (`d97b553`, T0).* `RELEASE_GATE.md` now reads 271 proven,
15 genuinely open, 27 historical ceremony items resolved inline as superseded. Every newly
ticked box carries a checkable citation; **every one of the 15 open boxes states the specific
evidence that would close it.** The Wave 4A.2 cache-bust literals are annotated as historical
(`wave4a2-b9137ee` → live `w4c1-ka1-20260621-a`).

*Deliberately left open:* the Phase-1 cohort item says **six** historical derivatives smoke
rows; the production query found **seven** (5 `CONTROLLED_SMOKE` + 2
`SCHEDULED_SHADOW_EVIDENCE`). Recorded as an open reconciliation rather than guessed at.

**BLOCKING FINDING — the live write-smoke is blocked by contract, not by authorization.**
`AnalysisRequest` (`src/crypto_probability_engine/api/schemas.py:77`) is `extra="forbid"` and
carries only `symbol`, `analysis_mode`, `timeframe`, `asset_class`, `include_detail`. **There
is no prediction-origin field on the HTTP contract**, so every production `/v1/analyze` write
is recorded `USER_REQUESTED`. The origin contract exists at the service layer and in the DB,
but the endpoint cannot reach it. Codex reported this as `BLOCKED` on task 009 and the finding
was independently confirmed. Consequence: **any live write-smoke would inject synthetic rows
into the 806-sample `USER_REQUESTED` control cohort**, destroying the very evidence separation
Change B depends on. No workaround was attempted; the write phase was removed from scope and
the capability rebuilt read-only as task 011.

*Repair record — one causal class, one consolidated repair, no blind retry.* Task 011 came
back `BLOCKED` after the same cookie-session failure twice under `MockTransport`. Root cause
was **a test-fixture defect, not a script defect**: the mocked `Set-Cookie` omitted `Path`, so
`http.cookiejar` derived the cookie path from the login URL as `/v1/auth` and never sent it to
`/v1/system_status`. Proven directly — the cookie *was* delivered to `/v1/auth/whoami` and
withheld from `/v1/system_status`. The real app emits `Path=/` (`api/auth.py:166` → Starlette
default), so the mock did not reproduce production. Sibling scan found no other `Set-Cookie`
mock in the repo. Consolidated repair: fixture corrected to production's real cookie
attributes, the redundant manual `client.cookies.update(...)` that disguised the cause removed,
and **a regression test added that asserts the real login response still sets `Path=/`**, so
the mock can never silently drift from production again.

**Open decisions** — three, batched, all at genuine owner boundaries; see NEXT ACTION.

**NEXT ACTION — three batched owner decisions. Nothing is half-applied.**

1. **Phase B access code (secret boundary).** Phase B is built and tested but never run: it
   needs `UCPE_SMOKE_ACCESS_CODE`. Never put the code in chat or in a file. The owner runs it
   in-session so the value stays in their shell only:
   `! UCPE_PRODUCTION_SMOKE_ENABLED=true UCPE_SMOKE_ACCESS_CODE='<code>' .venv/bin/python scripts/production_smoke.py --base-url https://beny053-ultimate-crypto-probability-engine.hf.space --authenticated`
   Read-only. It closes the Wave 1.2 `Persistence: OK` item and gives the **first live proof
   `/v1/calibration` serves rather than 401s** — currently only inferred from byte-identical
   source.

2. **Wave 4B0 live write-smoke — product decision, not an authorization.** Options:
   (a) **Close it as not-run with reason** — cheapest, honest, keeps the control cohort clean,
   and v1 loses only a live BTC/SOL write check already covered offline;
   (b) **Add a prediction-origin field to `AnalysisRequest`** so a smoke can write
   `CONTROLLED_SMOKE` — a T2 API/schema change plus a T3 redeploy before it is usable, and it
   widens the public contract for a test-only need;
   (c) **Accept `USER_REQUESTED` smoke writes** — rejected on the evidence: it contaminates the
   806-sample control cohort and contradicts the standing instruction to preserve the split.
   Recommendation: **(a)**, revisiting only if a live write path is needed for another reason.

3. **T3 push of `feat/production-live-smoke`** (2 commits, plus the docs commit on `main`
   riding along). Expect the same wall as last time: `git push` is refused by the auto-mode
   permission classifier and `gh` is absent, so the owner runs the push in-session.

Change A still needs nothing further.
Worth knowing before choosing: production now serves Change A's gating, but
`/v1/calibration` still reports **`WARMING_UP` ×5 and `NO_SAMPLES` for 1M**, because the
endpoint only issues per-timeframe scoped queries and no timeframe has ≥500 resolved
outcomes (134–172 each). The 806/`MEASURED` figure remains an unscoped aggregate no
endpoint requests. Since predictions are traffic-driven, that gap closes only with roughly
3× more operator traffic per timeframe — not with time alone.
Change B (horizon-specific probability modelling) stays deferred and **has not started**:
it needs a new `methodology_version`, which resets calibration to `NO_SAMPLES`, so the
806-sample cohort must survive as the control until Change A has re-accumulated evidence
under gating.
