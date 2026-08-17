# STATE

Updated: 2026-08-17

## Recovery block — read this first on resume
```
LOOP_STATE=PAUSED_AWAITING_OWNER (T2 built and green; stopped before secret/deploy/T4)
CURRENT_MILESTONE=Remaining Deployed Browser Evidence Closure (started 2026-08-17)
CURRENT_BRANCH=feat/session-scoped-origin (3 commits, unpushed); origin/main = 6eb632d
LAST_GREEN_SHA=bb09cb0
LAST_VERIFY=PASS 822 passed, ruff clean, 3/3 scanners · 2026-08-17
CODEX_PENDING=NONE
GPT_REQUEST_ID=NONE
GPT_THREAD_URL=NONE
GPT_REQUEST_STATE=NONE
OWNER_BOUNDARY=3 sequential, none crossed — (1) generate the smoke code and configure the HF
  secret CONTROLLED_SMOKE_CODE_HASH [T3, secret]; (2) push/PR and deploy the build [T3];
  (3) run the browser smoke, which writes CONTROLLED_SMOKE rows to production [T4, one-shot].
  Order matters: the secret must exist before the deploy is useful, and the deploy before the
  smoke.
NEXT_ACTION=owner provisions CONTROLLED_SMOKE_CODE_HASH; then deploy; then the T4 smoke
```
Update this block on every pause, every milestone change, and every GPT consultation.
`GPT_REQUEST_STATE` ∈ `NONE` · `DRAFTED` · `SENT_WAITING_RESULT` · `COMPLETED_RESULT_SAVED` ·
`SKIPPED_UNAVAILABLE`.

## v1 roadmap — progress at a glance
*Updated 2026-08-17 · `RELEASE_GATE.md`: **273 proven / 13 open***

**Completed milestones**
1. **Change A — calibration truth + skill gating.** PR #2, merged `e6ee23c`, **deployed to
   production**. Change A is closed and needs nothing further.
2. **Deploy pin + source-integrity closure.** PR #3, merged `1b06aab`; guard `HEALTHY` exit 0,
   no `PIN_DRIFT`.
3. **Operating model V2 + GPT sidecar.** PR #4, merged `a59b295`. Six process artifacts, no
   growth.
4. **Production live-smoke + release-gate reconciliation.** PR #5, merged `6eb632d`. Gate went
   271/15 → 273/13; `/v1/calibration` proven to serve in production.

**Current milestone** — **Remaining Deployed Browser Evidence Closure** (started 2026-08-17).
Close Wave 4A.2's live browser card check and Wave 1.1's deployed UI smoke **without**
misclassifying test-motivated traffic as `USER_REQUESTED`, without waiving scope, and without
widening the API unless genuinely necessary.

**Next major milestone** — **Change B: horizon-specific probability modelling.** Still
deliberately blocked. It needs a new `methodology_version`, which resets calibration to
`NO_SAMPLES`, so the 806-sample cohort must survive as the control until Change A has
re-accumulated evidence under gating. Re-accumulation is **traffic-driven, not scheduled**, so
it does not progress with time alone.

**Outstanding, but not milestones** — per-timeframe `MEASURED` needs roughly 3× more operator
traffic per timeframe (currently 134–172 against a ≥500 threshold) · the six-versus-seven
derivatives-cohort reconciliation is open and deliberately not guessed at.

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
unchanged at `30d4982` before and after, and no workflow deploys to Hugging Face or
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

**CORRECTION 2026-08-17 — one workflow *does* reference Hugging Face.** Earlier entries said
"no workflow references Hugging Face". That phrasing was wrong, though the conclusion it
supported still holds. `.github/workflows/keepalive.yml` pings the Space, but it is
`schedule` + `workflow_dispatch` **only, with no push trigger**; it issues a single
`curl GET` on `/` and hard-refuses any URL containing `/v1/`, `analyze`, `auth`, or
`calibration`. **It cannot deploy and cannot write.** The accurate claim is: *no workflow
deploys to Hugging Face, and none triggers on push to `main`* — so merging still cannot
deploy. Deployment happens only by an explicit `git push hf`.

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
*Superseded 2026-08-16: the live HTTP invocation is no longer unverified — Phase B invoked it
with a real session and it served 200. See the Phase B section below.*

**But `/v1/calibration` will NOT report MEASURED — CONFIRMED LIVE 2026-08-16.** The endpoint never issues an unscoped
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
after — **the merge cannot deploy**: no workflow deploys to Hugging Face and `ci.yml`'s push
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

**PHASE B PASSED IN FULL — 2026-08-16, re-run with the repaired instrument.**
`PASS: production smoke phases A+B`. `/v1/calibration` served **200** at the 120s budget and
returned exactly what was predicted:
`15m WARMING_UP 172 · 1H WARMING_UP 165 · 4H WARMING_UP 172 · 1D WARMING_UP 163 ·
1W WARMING_UP 134 · 1M NO_SAMPLES 0`.

**Those counts match the 2026-08-15 read-only SQL query exactly.** That is an independent
cross-check, not a restatement: the live endpoint and the direct database query agree
per timeframe, which confirms the deployed endpoint really does read the same database the
resolver writes to. The identical counts also confirm **no new outcomes resolved since
2026-08-15**, consistent with zero operator traffic.

Three standing predictions are now confirmed by live evidence rather than inference: the
endpoint serves rather than 401-ing; it reports per-timeframe scoped results, never the
unscoped 806/`MEASURED` aggregate; and 1M reports `NO_SAMPLES`. The earlier 10s timeout was
an instrument defect, exactly as diagnosed — production was healthy throughout.

*History of that failure, kept because the diagnosis mattered:*

**PHASE B FIRST RUN — partial, 2026-08-16.**
The owner ran Phase A+B. Phase A passed again. Login succeeded and
`GET /v1/system_status` returned 200 with **`persistence_status=OK`,
`repository_type=SUPABASE_REST`, `store_status=CONFIGURED`, `circuit_state=CLOSED`** — the
first live proof the deployed runtime reaches durable persistence. It also settles which
Wave 1.2 priority tier production actually selects: **`SUPABASE_REST`**, the first tier. Note
this is the *runtime* repository; the calibration endpoint builds a separate *operator*
repository that prefers direct Postgres (`repository.py:2258`), so both tiers are in use for
different purposes. **Wave 1.2's `Persistence: OK` item is closed on this evidence.**

Then: `FAIL: production smoke phases A+B; The read operation timed out`.

*The timed-out read was `GET /v1/calibration`, identified without re-running anything.* Raw
capture proved it by absence: every earlier request wrote its body, and
`phase-b-calibration.body` was the only one missing, so no response ever arrived.

**Both defects were in the instrument, not proven in production.** (1) A single blanket 10s
timeout was applied to every request, but `/v1/calibration` fans one HTTP call out to six
sequential Space→Supabase round trips — `calibration_endpoint.py:30` iterates six
`SUPPORTED_TIMEFRAMES`, each a scoped read with `limit` defaulting to 5000 (line 90), against
the direct-Postgres operator repository. Ten seconds was never a contract-grounded budget.
(2) The failure never named *which* read died. Repaired in `20c19d3`: `--calibration-timeout`
(default 120s) separate from `--timeout` (10s, so real hangs still surface fast), and
transport errors now name method, path and elapsed budget, with the query string stripped and
the raw transport message dropped so nothing sensitive rides along. No production behaviour
was touched.

*That run proved only that the endpoint did not answer within 10 seconds — neither health nor
fault. The re-run decided it: healthy, and the predicted per-timeframe values.*

**MILESTONE: REMAINING DEPLOYED BROWSER EVIDENCE CLOSURE — started 2026-08-17.**
Target: Wave 4A.2's live browser card check and Wave 1.1's deployed UI smoke, the last two
gate items that need a browser. Investigation complete; **no code changed, no smoke run, no
production analysis.**

*Findings, each verified against the code:*
- **No request shape renders the cards without writing a ledger row.** Every card is filled
  only from its own fresh `/v1/analyze` response (`frontend/app.js:733-748`), and neither
  `analysis_mode` nor `include_detail` suppresses prediction construction. Row construction
  needs live data plus a valid anchor (`api/analysis_service.py:776-787`); the only skips are
  fixture mode, failure, or degradation — none of which is a viable request shape.
- **There is no way at all to set a non-default origin over HTTP.** `AnalysisRequest` has no
  origin field and forbids extras (`api/schemas.py:77-84`); the routes pass no origin
  (`api/app.py:164-202`); CORS allows only `Content-Type`; and there is **no deployment-wide
  origin setting** — `Settings` has no such field and `from_env` reads no such variable.
- **No deployed view renders cards from stored data.** The detail endpoint reads the
  **in-memory** run store, which does not survive a Space restart
  (`api/app.py:264-272`, `persistence/run_store.py:9-14`). Persisted rows hold the three
  numbers but not the `decision_synthesis` fields the cards render from.
- **Loading the page writes nothing.** Init renders placeholders and fetches only public
  `/v1/build-info`; login calls only `/v1/system_status`. Analysis starts *only* on explicit
  user action (`frontend/app.js:2164-2168`, `1910-1921`, `1928-2127`). A browser can safely
  load and log in.

*Two corrections to the delegated investigation, both material:*
1. **An API-only field would not help a browser.** The frontend posts exactly
   `{symbol, analysis_mode, timeframe}` (`frontend/app.js:737-741`), so a UI smoke would still
   send the default. Closing these items via the origin route needs a **frontend** change too.
2. **Going stateless is far costlier than reported.** `build_persistence_repository` falls
   through REST → **Postgres** → in-memory (`persistence/repository.py:2244-2252`), and the
   Space holds all three credentials. Emptying it means removing **three** secrets and
   restoring **three** — six owner-only operations on production, where a botched restore
   silently costs durable persistence.

**CREDENTIAL BOUNDARY FAILED ONCE, THEN REPAIRED — 2026-08-17 (`bb09cb0`).**
The owner's first attempt to generate the secret was blocked before any hash existed:
`make_access_hash.py` restricted `--name` to the two original secrets, while `RELEASE_GATE.md`
already documented generating `CONTROLLED_SMOKE_CODE_HASH` with that exact command. **The
feature added a third deployment secret and never reconciled the generator** — my omission, not
the operator's error.

*Not worked around.* The hash must use the **same salt and iteration count the app uses at
login**; this script reads `UCPE_ACCESS_CODE_SALT` and `UCPE_ACCESS_CODE_PBKDF2_ITERATIONS` and
calls the app's own `pbkdf2_hash_code`, so reusing another secret's name or hand-rolling a
digest would risk a silent mismatch that surfaces only as a failed production login. A test now
pins that the digest is identical whichever `--name` is chosen. The supported names live in one
constant feeding both the argparse choices and the description, since those drifting apart is
what caused this.

*Sibling scan caught a second gap:* the frontend static **safety** test enumerated backend
secret names without the new one, so frontend code could have referenced
`CONTROLLED_SMOKE_CODE_HASH` without failing. Closed in the same commit rather than left open
while asking the owner to create that secret. Remaining incomplete lists are **documentation
only** and were reported, not changed: `README.md`, `DEPLOYMENT_CHECKLIST.md`,
`DEBUG_PACK_EXAMPLE.md`, `AI/06_TEST_COMMANDS.md`.

**RESOLVED — session-scoped origin implemented (`be2104e`, T2, branch
`feat/session-scoped-origin`).** Owner chose the session-layer approach over widening the
request contract. `VERIFY=PASS` 815 (was 803).

The origin now rides inside the session payload, which was **already HMAC-signed over its
body** (`api/auth.py:84-95`), so it cannot be forged without the signing key. A second access
code, hashed as `CONTROLLED_SMOKE_CODE_HASH`, mints a session whose analyses are recorded
`CONTROLLED_SMOKE`; both `/v1/analyze` and `/v1/analyze_batch` read it from the verified
session. **`AnalysisRequest` is untouched** — it keeps `extra="forbid"` and gains no origin
field — and **the frontend is unchanged**, so the browser simply logs in with the other code.

*Fail-closed, deliberately asymmetric:* an **absent** origin key means `USER_REQUESTED`, so
sessions minted before this change survive the deploy; an origin key that is **present but
unsupported** returns 401 rather than defaulting, because a silent downgrade would contaminate
the cohort invisibly — the precise harm this exists to prevent. Login is byte-for-byte
unchanged when the hash is unset, the normal code is still checked first, a wrong code returns
an identical error either way, the same limiter and constant-time compare apply, and a smoke
session grants no Dev Mode. All eleven of those properties have direct tests
(`tests/api/test_session_prediction_origin.py`).

*Known, accepted:* whether the smoke hash is configured is observable through login **timing**,
since an unset hash short-circuits before PBKDF2. It leaks only the existence of the feature —
which this repository documents publicly anyway — never the credential, and the attempt limiter
bounds sampling. Not worth constant-time padding; recorded rather than silently ignored.

*Guard test:* `CURRENT_DELTA_PATHS` now lists `api/app.py`, because a guarded source file is
changed on GitHub but not yet deployed. **`ops/hf_runtime_baseline.json` is deliberately NOT
re-pinned** — the pin tracks what is deployed, and the order is deploy first, pin second. The
regression test now exercises a real non-empty delta instead of an empty one, which is stronger
coverage than before.

**Original conclusion, which drove the decision: closing both items honestly does require a contract change.** Wave 1.1 says
"Manual **deployed** UI smoke" — by the same reading the audit applied, that means the real
Space, so a local render check cannot close it. No waiver, no scope reduction, and no
reinterpretation is available here.

**MILESTONE CLOSED — PR #5 MERGED TO GITHUB, 2026-08-17.**
`feat/production-live-smoke` @ `0e0c844` → `main`, merged as merge commit
**`6eb632d1417190d8517284e89a7d7dd1408aff42`** = `origin/main`. Verified from Git, not the UI:
the commit has **two parents** (`a59b295` + `0e0c844`), confirming the merge-commit method
rather than a squash or rebase, and `0e0c844` — the exact head CI went green on — is an
ancestor of `main`. 14 commits, 6 files, +1262 −61.

**CI ran clean-room for the first time on this work**: `CI / test (pull_request)`
**Successful in 29s** on head `0e0c844`, the exact commit merged.

**NOTHING WAS DEPLOYED.** `hf/main` verified `e6ee23c` **after** the merge, unchanged. No
workflow references Hugging Face and `ci.yml`'s push trigger is limited to `codex/**`, so a
merge to `main` cannot deploy. Production still runs `e6ee23c`. The branch was **kept**, not
deleted, matching how `chore/gpt-sidecar` was kept after PR #4.

**Gate: 273 proven / 13 open.** What the merge did *not* close, and why: 2 items need a real
browser session (Wave 4A.2's card-rendering check, Wave 1.1's deployed UI smoke); 1 is an
unconsumed precondition (manual collector dispatch); the rest are superseded, deferred, or
out of v1. The six-versus-seven derivatives-cohort discrepancy remains an open reconciliation,
deliberately not guessed at.

*Prior boundary, for the record:*

**T3 PUSH EXECUTED BY THE OWNER — 2026-08-16.** `feat/production-live-smoke` pushed to
`origin` and now tracks it; `origin/feat/production-live-smoke` = `28f0e4b` = the exact local
head at push time. `origin/main` unchanged at `a59b295`. **`hf` untouched — the push cannot
deploy**: no workflow deploys to Hugging Face. The long-standing `main` docs commit `22b3414`
is an ancestor of this branch, so it rode along exactly as `b52f7ca` did in PR #4.

**CI HAS NOT RUN on these commits.** `ci.yml` triggers on `push` to `codex/**` and on
`pull_request` only; this branch is `feat/**`, so the push fired nothing. The 803-test suite
has been verified locally but has **not** had clean-room verification. Opening a PR is what
triggers it.

**Open decisions** — one: whether to open a PR, and whether to merge. See NEXT ACTION.

**NEXT ACTION — three batched owner decisions. Nothing is half-applied.**

1. ~~**Phase B**~~ — **DONE 2026-08-16.** Ran clean end to end at the 120s budget; see the
   Phase B section above. The access code stayed in the owner's shell (`read -s`, then
   `unset`) and never entered chat, a file, or the repository. Nothing further is needed.

2. **Wave 4B0 — CLOSED ON EVIDENCE 2026-08-16 (`91254f3`). No waiver, no scope exclusion, no
   API widening, no synthetic `USER_REQUESTED` row.**
   The block was never really about authorization: `analyze_request()`
   (`api/analysis_service.py:117`) has always accepted `prediction_origin` as a keyword. Only
   the HTTP request model lacks the field. Driving that runtime primitive directly with
   `CONTROLLED_SMOKE` — the pattern the Phase 2A collector gate already blesses — produces
   correctly classified evidence with **no schema change, no API change and no redeploy**.
   Ran live via `scripts/live_smoke.py`, all six cells `CROSS_PROVIDER`: BTC 1D DOWN=0.477839
   SUFFICIENT · BTC 1W UP=0.505850 SUFFICIENT · BTC 1M UP=0.377757 LOW_SAMPLE · SOL 1D
   DOWN=0.399734 SUFFICIENT · SOL 1W UP=0.395839 SUFFICIENT · SOL 1M UP=0.365214 LOW_SAMPLE.
   Each cell asserted schema-valid, live, probability invariant within 1e-9,
   `profitability_claim=false`, `news_influence_frac=0.0`, the Wave 4B0 `1M` LOW_SAMPLE rule,
   and `CONTROLLED_SMOKE` classification read from the runtime's own non-consuming
   `_peek_prediction_persistence`.
   **Scope of the evidence, stated plainly:** local process, code byte-identical to deployed
   `e6ee23c` (`git diff e6ee23c HEAD -- src/ schemas/` is empty), `STATELESS`, zero database
   writes. Not executed against the HF Space over HTTP — impossible without cohort
   contamination. The item says "after merge/deploy", not "against the deployed instance";
   where this gate means the latter it says so (Wave 1.1's "Manual **deployed** UI smoke").
   The smoke is **non-writing by construction**: it refuses to start if any database variable
   is configured, so it cannot reach production data. Persisting CONTROLLED_SMOKE rows to the
   production DB remains an unauthorized **T4** action and no write path was built.

   *Superseded routes, kept for the record:*
   **A NOT_RUN closure was tried on 2026-08-16 and reverted as an invalid waiver** (`acfc690`
   + `3e1cf10`, reverted by `90d6d83`). The post-decision audit found `RELEASE_GATE.md`
   authorizes not-run closure exactly once, inside the item's own text (Sprint 3: "or
   explicitly recorded as not run with reason"); the Wave 4B0 item has no such clause. The
   "Pass/fail/not-run result for each relevant command" line is a *reporting* obligation, not
   a satisfying condition. "Release requires evidence" stands and the Deployment gate blocks
   release. `V1_QUANT_CONTRACT.md` is silent on live smoke, so `RELEASE_GATE.md` governs.
   No box was ever ticked (271/15 throughout), so nothing was presented as a pass.
   **Do not re-apply a not-run closure.** The remaining routes are:
   (a) **Add a prediction-origin field to `AnalysisRequest`** so a smoke can write
   `CONTROLLED_SMOKE` — T2 API/schema change plus a T3 redeploy before it is usable, and it
   widens the public contract for a test-only need;
   (b) **Record an explicit v1 scope exclusion** in the Phase 2D.3B form
   (`<!-- OUT OF v1 (owner decision <date>) -->`), which **also requires amending line 5** of
   `RELEASE_GATE.md` so its "only one owner-approved v1 scope reduction" claim stays true.
   (b) is a scope reduction and is the owner's alone. Accepting `USER_REQUESTED` smoke writes
   stays rejected: it contaminates the 806-sample control cohort.

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
