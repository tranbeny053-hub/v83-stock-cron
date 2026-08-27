# STATE

Updated: 2026-08-27 (post PR #63)

## Recovery block — read this first on resume
```
LOOP_STATE=IDLE — both history lanes SHIPPED to main; no lane open. PR #56 (in-process
  Recent Analysis History) merged 2026-08-27T05:32:03Z, PR #57 (durable history) merged
  2026-08-27T06:12:00Z. Batches 1-10 remain closed and the pre-T_close audit returned BOARD
  CLEAR. PROD-SAFE-2 remains the deployed build and NOTHING was deployed by either merge. The
  section 5A envelope is UNCHANGED and still frozen: the holdout, its evaluation, the candidate
  freeze, the collector, outcome and holdout inspection, T_close itself, and any change to what
  the collector computes or persists. Ordinary safe work outside that envelope continues under
  normal risk tiers, with owner authorization for T3/T4.
CURRENT_MILESTONE=Change B tranche 1 — collection running, evaluation pending at T_close.
  Product work outside section 5A continues in parallel; it never touches the envelope.
CURRENT_BRANCH=docs/state-post-63 (this checkpoint). origin/main = 1668534.
LAST_GREEN_SHA=1668534
LAST_VERIFY=PASS ruff ok | 1100 passed | schemas+smoke ok | scanners 3/3 · 1668534 · 2026-08-27
MAIN_STATE=main = origin/main = 1668534, clean, single worktree. It is the merge of PR #63
  (parents 9e66c84 + bea1ad0) and its tree is byte-identical to the reviewed head bea1ad0, so
  the merge introduced nothing beyond what was reviewed. Post-merge CI run #113 succeeded.
SHIPPED_TO_MAIN=Recent Analysis History, in two steps.
  PR #56 (2cdc06c): operator-facing GET /v1/runs behind the ordinary app session, a Recent
    Analysis tab, and fail-closed run provenance in the in-process store.
  PR #57 (7299c6e): the same history made DURABLE. A new read-only
    recent_runs_for_origin(limit, *, prediction_origin) on the protocol and all three
    repository implementations derives origin by joining analysis_runs to predictions on
    run_id, because analysis_runs carries no prediction_origin column. /v1/runs now prefers
    durable rows, falls back to the in-process store, and reports which in a top-level
    "source" field. Rows carry detail_available, because the full detail_view is NOT persisted
    durably — only the run summary is — so a restored entry shows its summary and says the full
    breakdown is unavailable rather than firing a request that would 404.
  PR #59 (690d756): durable sanitized Detail, so a restored USER_REQUESTED entry can REOPEN
    full Detail. detail_view is ~7.4 KB and is not reconstructable from existing tables, so one
    additive table was authored: migrations/0008_analysis_run_details.sql. The write lives in
    schedule_best_effort_persist, which only the two analyze routes call, gated to
    USER_REQUESTED and sanitized through sanitize_for_export. Reads reuse the same
    EXISTS-over-predictions origin guard. save_run_detail uses its own connection and swallows
    its own failures, so the absent table cannot call mark_unavailable, cannot open the
    persistence circuit breaker, and cannot affect any other write.
  PR #61 (b8d81d3): history rows now carry primary_timeframe and a conservative source
    indicator, plus browser-local symbol/timeframe/mode filters. Every field already existed —
    durable rows carried them and the normalization was dropping them; the in-process store now
    projects the same three from the stored payload. Nothing is computed and the browser derives
    no analysis value. The indicator claims "Live data" only when is_live_data is exactly true.
    disposition and total_score are deliberately NOT surfaced: they are decision claims that
    belong in Detail. Filtered-empty is reported distinctly from genuinely-empty.
  PR #63 (1668534): the history detail-availability read is BATCHED. /v1/runs now issues ONE
    run_ids_with_detail query for all durable-only rows instead of one get_run_detail call per
    row. It reuses the same EXISTS-over-predictions origin guard, takes a required validated
    keyword-only origin, issues no query on empty input, caps its input and fails closed beyond
    the cap, and — like save_run_detail and get_run_detail — uses its own connection and
    swallows its own failures so the absent table cannot open the persistence circuit breaker.
    get_run_detail is unchanged and still serves the single /v1/analyze/detail lookup.
  MERGED IS NOT DEPLOYED: none of this is in front of users.
ACTIVE_LANE=NONE. No lane is open.
FROZEN_POST_T_CLOSE=Three branches are LOCAL-ONLY and frozen until after T_close. None is
  pushed, none is on any remote, none is on main. Do not open a PR, merge, or deploy any of
  them before T_close:
    fix/r202-01              2c35ab2  provider HTTP byte cap + wall-clock deadline (R202-01)
    fix/a203-01              b5310dc  candle ordering/future boundaries fail closed (A203-01)
    integration/b11-combined 1b10587  the two above merged, for integration evidence only
  Re-verified after the PR #57 merge: still absent from origin, still unreachable from main.
CODEX_PENDING=NONE
GPT_REQUEST_ID=NONE
GPT_THREAD_URL=NONE
GPT_REQUEST_STATE=NONE
OWNER_BOUNDARY=NONE OPEN. Five T3 origin batches are CONSUMED and must not be reused: the PR
  #56, PR #57, PR #59, PR #61 and PR #63 batches each authorized exactly one push, one PR and
  one merge, and no deploy. No T4 has been authorized or consumed for migration 0008. The PROD-SAFE-2 T3/T4 authorization remains CONSUMED. Standing prohibition while the
  holdout runs: no holdout or outcome inspection, no collector dispatch, no deploy, no model
  change, no re-freeze.
DEPLOY_PROHIBITED=NO HUGGING FACE DEPLOY OF ANY KIND WHILE THE HOLDOUT RUNS, through
  T_close = 2026-09-12T04:00:00Z. This binds every lane in this file, including work already
  merged to main. A push to origin is a separate, lesser action and never implies a deploy;
  only a push to the hf remote deploys. Production stays at hf/main = a89b45e (PROD-SAFE-2),
  confirmed unchanged immediately after every merge.
NEXT_ACTION=SECTION 5A ONLY, scheduled: WAIT until T_close = 2026-09-12T04:00:00Z, then run the
  V1_QUANT_CONTRACT.md section 5A evaluation ONCE. This is the single scheduled action. The
  date is a contract instant, NOT a reminder or automation request: create no timer, task, or
  schedule from it.
BLOCKER_BEFORE_0008_T4=CLOSED by PR #63 (merged 1668534). The owner-directed prerequisite is
  satisfied: /v1/runs no longer issues one detail query per row. It now issues exactly one
  batched run_ids_with_detail call for all durable-only rows, bounded and fail-closed, and the
  behaviour of detail_available is identical per row. No blocker now stands against migration
  0008. Applying it remains a separate T4 decision that has NOT been authorized or taken.
MIGRATION_0008_NOT_APPLIED=migrations/0008_analysis_run_details.sql is MERGED AS CODE ONLY and
  has NOT been applied to any database. Until an owner applies it (a T4 action, one-shot, with
  raw capture before parsing), analysis_run_details does not exist, every durable Detail write
  fails and is swallowed by design, and nothing else degrades: history still lists runs and
  in-process Detail still works within a runtime. Applying it is what switches the feature on.
  scripts/apply_migrations.py was NEVER run in this work.
OPEN_ITEM=check_no_secrets walks the whole repository and its SKIP_DIRS omits .work/, so it
  scans gitignored scratch logs and can fail ./verify.sh on a clean tree from an untracked file.
  Its own docstring says it scans committed files. Deliberately NOT changed before T_close,
  because adding a skip narrows a mandatory scanner. Remedy meanwhile: delete stale .work/*.log.
RUN_PROVENANCE=FAIL CLOSED, in both the in-process and the durable path. put() requires an
  explicit prediction_origin; list_runs() falls back to a local UNCLASSIFIED sentinel, never
  USER_REQUESTED. recent_runs_for_origin() takes prediction_origin as a required keyword-only
  argument and passes it through validate_prediction_origin, so the sentinel can never be
  queried and can never be persisted. A run with no prediction of the requested origin is
  EXCLUDED, so the durable list can legitimately be shorter than the in-process one. /v1/runs
  keeps an explicit USER_REQUESTED allow-list. Any successor MUST preserve this.
DEPLOY_POSTURE=Recomputed against ops/hf_runtime_baseline.json on 690d756: GitHub main is
  ahead of the deployed bundle on FIVE guarded paths, unchanged by PR #59 —
  frontend/app.js, frontend/index.html, frontend/styles.css,
  src/crypto_probability_engine/api/analysis_service.py and
  src/crypto_probability_engine/api/app.py. Recomputed against ops/hf_runtime_baseline.json on
  CURRENT_DELTA_PATHS in tests/scripts/test_source_integrity_guard.py
  records all five exactly. analysis_service.py is the structural clean-room delta and never
  clears. None of it is in front of users until a future owner-authorized deploy.
```
Update this block on every pause, every milestone change, and every GPT consultation.
`GPT_REQUEST_STATE` ∈ `NONE` · `DRAFTED` · `SENT_WAITING_RESULT` · `COMPLETED_RESULT_SAVED` ·
`SKIPPED_UNAVAILABLE`.

## Provenance repair — 2026-08-27, before any T3

The first History build defaulted a missing run origin to `USER_REQUESTED`. My review cleared
it by checking only the *currently reachable* callers, which was too lenient: `InMemoryRunStore`
is a dataclass whose `runs` field is an init parameter, so a store constructed directly holds
runs that never passed through `put()` and were reported as the operator's own. The owner
caught it and held T3.

It now fails closed on both halves — `put()` requires an explicit origin, and anything
unrecorded reads as a local `UNCLASSIFIED` sentinel that `validate_prediction_origin` rejects,
so it can never reach the `prediction_origin` CHECK constraint. Regression coverage pins all
seven cases: omitted at construction, omitted at call, smoke, shadow evidence, operator,
non-persistability of the sentinel, and eviction. Collector/OOS identity was re-established
after the repair, on local deterministic evidence only.

## Checkpoint — 2026-08-27: one lane open at T3, two lanes frozen local

Three findings that had been excluded from every batch-4-to-6 task were taken up. Two are
fixed and **frozen local**: R202-01 (provider bodies had no byte cap and no wall-clock
deadline, so an allow-listed upstream could trickle forever or exhaust RAM) and A203-01
(candle ordering and future-close boundaries failed open — a 4H series overlapping by 1h
passed because only gaps >= one full bar were rejected, and a close after `now` passed on a
negative age). Both are reviewed and green. Neither ships before `T_close`.

The third lane, Recent Analysis History, is the only active one and is stopped at T3.

**Why the History lane needed a persistence proof.** The section-5A collector passes a
`run_store` into `analyze_request`, so the in-process run store sits on the collector's code
path. The collector's *database* evidence, however, is written by `persist_analysis_now`,
which contains zero `run_store` references. Identity was established two ways, on local
deterministic evidence only, with no holdout or outcome inspection: every DB-write function in
`analysis_service.py` is byte-identical by AST hash and `analyze_request` is the only function
that changed; and a deterministic differential probe — validated against a same-commit
stability control — produced identical hashes before and after for the validated payload,
`analysis_hash`, prediction rows, feature snapshots, the persist result and its idempotent
repeat. `schemas/response.schema.json` still matches its deployed pin digest, corroborating
that the response envelope did not move.

**A structural artefact to expect, not to misread.** This checkpoint names `68a6250` as
`LAST_GREEN_SHA` while itself being a later commit. A docs checkpoint cannot name the commit
that carries it. `68a6250` is the commit the work was verified on; this commit changes only
`STATE.md` and no product blob, so the identity proof above still applies verbatim.

## Production — PROD-SAFE-2 IS DEPLOYED (2026-08-25)
hf/main moved e9d549c -> a89b45e at 2026-08-25T17:55:11Z by fast-forward, one commit.
Shipped to users: login failure states, batch-item error messages that show the backend's
message instead of a bare enum, and removal of the browser-derived "Tactical horizons"
verdict. Also shipped: the 480-character news snippet cap and a bounded best-effort
persistence backlog. The six authoritative per-timeframe cards are unchanged.

Proof captured at deploy time, all read-only:
  healthcheck  status OK, uptime 6s (fresh restart)
  build-info   UCPE-W4D3-OPS-2A0-20260622-A / HF_PRODUCTION, matching the pin
  served bytes sha256 of app.js, styles.css and index.html each byte-identical to the pin
  guard #605  HEALTHY, 3/3 rounds, delta path count 1 (the structural analysis_service.py)

No DB write, no prediction smoke, no holdout inspection, no Change-B/OOS code was included.

## Production — PROD-SAFE-1 (2026-08-23, superseded)

`hf/main` = **`e9d549c`**, deployed 2026-08-23T06:01:39Z as a fast-forward from `9933615`.
This is the first deploy since 2026-08-17 and it carries **no section-5A code whatsoever**.

**What it is.** A release candidate rooted at the then-deployed `9933615` — deliberately NOT
cut from `main`, because `main` carries the Change-B candidate and the collector, none of
which may reach production while the holdout runs. Three backports were integrated onto that
clean base: the `blocking_reasons` operator-facing UI, the login hardening, and the Docker
build-context fix. `VERIFY=PASS`, 842 passed (822 base + 11 + 9).

**Clean-room proof.** `oos/`, `probability_distributional.py`, the collector, the OOS workflow
and the freeze file are all absent from the deployed tree. A word-boundary search for
`OOSArm`, `pair_context`, `PairTarget` and `distributional` returns zero in both the base and
the candidate, and no forbidden token appears on any added line. No protected-tier path
(`quant/` `gates/` `persistence/` `config/` `schemas/` `migrations/`) is touched.

**One real adaptation, recorded because it is a divergence from `main`.** APP-1 on `main`
gates `blocking_reasons` off the collector arms via `include_blocking_reasons=arm_context is
None`. There is no `arm_context` on this lineage and no collector to protect, so the flag is
kept for parity but the call site gates nothing. `api/analysis_service.py` therefore moves by
two lines here against a large diff on `main`.

**Deploy evidence, in order.**
1. Pre-deploy baseline: guard **#573**, scheduled, on `4dc8ad5` — HEALTHY.
2. `git push hf e9d549c:refs/heads/main` — fast-forward, `9933615..e9d549c`, 06:01:39Z.
3. Space rebuilt: API `sha=e9d549c`, `stage` went `RUNNING_BUILDING` → `RUNNING`.
4. `/healthcheck`, `/v1/build-info`, `/` all 200.
5. **Decisive:** the live Space serves `app.js` whose SHA-256 is `9591fac6…`, byte-identical
   to the pinned digest. `styles.css` matches its unchanged pin. The build fingerprint does
   NOT move — `config/build_info.py` is unchanged — so it was never used as proof.
6. Pin PR #30 merged at 06:14:11Z. **`PIN_DRIFT` window: 12m 32s.** No scheduled guard fired
   inside it; the latest scheduled run at window close was still #573.
7. Post-merge CI **#47** on `074e995` — SUCCESS.
8. Guard **#574** dispatched once on `074e995` — **HEALTHY**, critical source match True,
   frontend asset match True, three probe rounds all HEALTHY.

**The pin now describes the live build.** Five literals moved on `main` and only five:
`hf_main_sha` → `e9d549c`; the digests for `frontend/app.js`, `frontend/index.html` and
`api/analysis_service.py`; and `frontend_asset_tokens.app_js` → `w4c1-ka1-20260823-a`. Eight
of eleven guarded digests, `styles_css`, and every identity field are untouched.

**Two standing consequences a future session must not misread.**
- The guard reports advisory `SCHEDULER_DIVERGENT_FROM_PIN` with `scheduler_ahead_count:
  null`, permanently, because the deployed commit is a separate lineage from `main` and the
  ancestry walk cannot resolve. It is contract-defined, non-failing, and was predicted before
  the deploy. It is NOT drift.
- `CURRENT_DELTA_PATHS` is `["src/crypto_probability_engine/api/analysis_service.py"]` and
  stays that way, because `main` carries collector code the deployed build deliberately does
  not. This does not empty until a future deploy is cut from `main` itself.

**Rollback, if ever needed.**
`git push --force-with-lease=refs/heads/main:e9d549c59f159222e763182cf0aa02564c1ed67c hf
9933615b3a9a1bdffada6cc568c2927ff9106114:refs/heads/main`, then revert the five pin literals
and the test mirror. Force is required because the restore moves the remote backwards.

**Untouched throughout:** the database, the section-5A holdout, the collector, every
`V1_QUANT_CONTRACT.md` §5A path, and `T_close` = 2026-09-12T04:00:00Z. No prediction row was
written; `live_smoke.py` and `manual_smoke.py` were deliberately not run because they create
prediction rows. Only `production_smoke.py`-class read-only GETs were used.

## Current status — 2026-08-22

`STATE.md` on `main` had not moved since `439c601` (2026-08-17) while **fourteen PRs, #8
through #21, merged**. This section reconciles the top of the file to what is provable today.
It replaces the recovery block and the roadmap only. **Everything from *Operating model V2 —
anchored 2026-08-16* downwards is the historical record as written between 2026-08-15 and
2026-08-17 and is preserved verbatim; where it conflicts with this section, this section
governs.**

**Proven this session — deterministic, local, read-only:**
- `origin/main` = `e910751` — the PR #21 merge commit, dated 2026-08-22T22:55:23+07:00.
- `./verify.sh` on that exact tree: **PASS** — ruff clean, **993 passed** in 6.05 s,
  schemas + smoke ok, scanners **3/3**.
- **Nothing is deployed from this work.** `git ls-remote hf refs/heads/main` = `9933615`.
  That SHA is a strict ancestor of `origin/main`, which is **33 commits (15 first-parent)
  ahead**, so a future deploy would be a fast-forward. No deploy is authorized.
- **No `PIN_DRIFT`.** `ops/hf_runtime_baseline.json` carries `hf_main_sha = 9933615`, which
  equals live `hf/main` exactly.
- `ci.yml` triggers on `push` to `main` **and** on `pull_request`, so merges to `main` are
  now verified in the clean room on the merge commit itself.
- Node-24-native pins (`actions/checkout@v7`, `actions/setup-python@v7`) are in place on five
  workflows: `ci.yml`, `source-integrity-guard.yml`, `derivatives-evidence-cadence.yml`,
  `derivatives-cadence-readiness-diagnostic.yml`, `derivatives-registry-diagnostic.yml`.
  **Two are deliberately still on Node-20-era pins** — `oos-pair-evidence.yml` and
  `resolve-outcomes.yml` (`@v4`/`@v5`) — frozen for the duration of the holdout.
- The holdout instants are tracked on `main` in `V1_QUANT_CONTRACT.md` §5A.2:
  `T_freeze = 2026-08-20T11:35:56Z` · `T0 = 2026-08-21T04:00:00Z` ·
  `T_close = 2026-09-12T04:00:00Z` (`= T0 + 528 h`, driven by 4H). The collector cadence
  `7,22,37,52 * * * *` is enabled in `.github/workflows/oos-pair-evidence.yml` on `main`.

**Recorded in Git during 2026-08-18…22, not re-verified in this session.** These lanes closed
on GitHub-side evidence (`gh` is not installed on this machine and no browser check was run
here), so they are reported as *recorded*, not as *re-proven today*: CI-1 `fd4684c` ·
CI-2 `a950a0f` · CI-3 `9b36f50` (guard dispatch `HEALTHY`) · CI-4 `f3daffd`
(`AVAILABLE_COMPLETE`) · CI-5 `68592f2` · TEST-1 `9605863` · GOV-1 (a branch ruleset on `main`
enforcing pull-request + CI; `main` had been unprotected) · CI-6 `e910751`.

**`NOT_RUN`, stated as a limitation and never as a pass.** The `@v7` pins on
`derivatives-evidence-cadence.yml` have never executed on any SHA. Moving that to *executed*
requires a T3 dispatch of a write-capable collector, which is refused while the holdout runs.

**Known gaps between `origin/main` and the local record — none of them fixed by this lane.**
The narrative history for 2026-08-17 → 2026-08-22 (~6 000 lines) exists only on the local,
unpushed branch `chore/session-origin-diagnostic` @ `186d0ad`; that branch is **stale on code**
— it predates PRs #8–#21 — so it must not be merged or copied wholesale, only mined. Also
unpushed and still open: `RELEASE_GATE.md` on `main` reads **273 proven / 13 open**, while the
local record has it at **275 / 11** after the authorized 2026-08-19 browser evidence run closed
Wave 4A.2 and Wave 1.1 · `CLAUDE.md` on `main` lacks the *Model routing and effort* section ·
`docs/OPERATING_DOCTRINE.md` on `main` lacks the owner-facing doctrine adopted 2026-08-19.

**Section 5A's prohibition, verbatim.** The holdout is evaluated **exactly once**, at
`T_close`. **No interim looks** — `d`, `ECE`, per-symbol tallies and window counts are not
computed or inspected before `T_close`. A NOT PASS or FAIL **may not be retuned against the
same holdout**; a second attempt requires a new candidate freeze, new `T_freeze`, new `T0` and
a new holdout. `T_close` is fixed once `T0` is observed and may not be extended, shortened or
re-declared.

**Standing environment constraints.** `gh` is off `PATH`; outbound `curl` and `git push` are
refused by the Claude Code permission classifier. Every remote write needs the owner to run it
with the `!` prefix, and GitHub settings or PR work needs the browser.

## v1 roadmap — progress at a glance
*Updated 2026-08-22 · `RELEASE_GATE.md` on `main`: **273 proven / 13 open** — stale; the local
record has it at 275 / 11 and that correction is not yet pushed.*

**Completed milestones**
1. **Change A — calibration truth + skill gating.** PR #2, merged `e6ee23c`, **deployed to
   production**. Change A is closed and needs nothing further.
2. **Deploy pin + source-integrity closure.** PR #3, merged `1b06aab`; guard `HEALTHY` exit 0,
   no `PIN_DRIFT`.
3. **Operating model V2 + GPT sidecar.** PR #4, merged `a59b295`. Six process artifacts, no
   growth.
4. **Production live-smoke + release-gate reconciliation.** PR #5, merged `6eb632d`. Gate went
   271/15 → 273/13; `/v1/calibration` proven to serve in production.
5. **Remaining deployed browser evidence closure.** Closed 2026-08-19 by an authorized T4
   evidence run in a `CONTROLLED_SMOKE` session: Wave 4A.2's card check and Wave 1.1's
   deployed UI smoke. **The `RELEASE_GATE.md` edit recording this is not yet on `main`.**
6. **Change B tranche-1 infrastructure and activation.** PRs #8–#14: paired-evidence
   collector, the section 5A acceptance contract, the `distributional-v1` candidate freeze,
   the recorded `T0`, and the recurring cadence. The collector is bounded by
   `--max-occasions`, so a canary can be exactly one occasion.
7. **CI and governance hardening.** PRs #15–#21: post-merge CI on `main`, Node-24 action pins
   across five workflows, and bare-`pytest` parity — plus GOV-1, a branch ruleset protecting
   `main`, which is a GitHub settings change rather than a PR.

**Current milestone** — **Change B tranche 1: the holdout is live and accumulating.** The
candidate `distributional-v1` is frozen; collection runs unattended on the enabled cadence
until `T_close = 2026-09-12T04:00:00Z`, when section 5A is evaluated **once**. There is no
work to do in the meantime and no interim look is permitted.

**Next major milestone** — **the section 5A evaluation at `T_close`**, and only then the
decision on whether `distributional-v1` ships. Change B remains **undeployed**; production
still runs the Change A methodology.

**Outstanding, but not milestones** — the unpushed `RELEASE_GATE.md`, `CLAUDE.md`, and
`docs/OPERATING_DOCTRINE.md` corrections listed above · `oos-pair-evidence.yml` and
`resolve-outcomes.yml` still on Node-20-era pins, frozen for the holdout, and
`oos-pair-evidence.yml` additionally lacks a `permissions:` block (low severity — the
repository default is already read-only) · per-timeframe `MEASURED` needs roughly 3× more
operator traffic per timeframe (134–172 against a ≥500 threshold) · the six-versus-seven
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

**DEPLOYED TO PRODUCTION — 2026-08-17. `9933615` IS LIVE.**
Deploy-first staging, at the owner's direction. `git push hf 9933615:refs/heads/main` was a
clean **fast-forward** (`e6ee23c..9933615`, ancestry verified beforehand, no force) and this
time needed **no credential bridging** — the earlier `osxkeychain` wall did not recur.

*Restart proven independently of the fingerprint.* `hf/main` = `9933615` exactly;
`uptime_seconds` collapsed **72539 → 94** and resumed climbing. The fingerprint stayed
`UCPE LIVE BUILD · W4D3-OPS-2A0-20260622-A` **exactly as predicted**, because
`config/build_info.py` is byte-identical across both builds — which is precisely why uptime,
not the fingerprint, was designated the proof in advance. Post-deploy Phase A: `PASS` — health
200, build-info 200, served bundle intact, `/v1/system_status` and `/v1/calibration` both
well-formed 401s.

**THE DEPLOYED FEATURE IS INERT, BY DESIGN.** `CONTROLLED_SMOKE_CODE_HASH` is **not**
configured on the Space, so `_hash_matches` returns `False` immediately (`api/auth.py:127-128`)
and the `CONTROLLED_SMOKE` branch is unreachable. Login behaviour is byte-for-byte what it was.
This deploy changed **no observable production behaviour**; it only staged the code. That is
the whole point of deploy-first: the secret becomes the single, reversible moment of change.

**PIN RE-BASELINED LOCALLY (`0237e8e`, branch `chore/deploy-pin-session-origin`).** Deploy
first, pin second. Exactly **two** literals, both computed: `hf_main_sha` `e6ee23c…` →
`9933615…`, and the `api/app.py` digest `8c559699…` → `ea55f4b3…`. Only **one of the eleven**
guarded blobs moved — `api/auth.py` and `config/settings.py` are not guarded.
*Applied by exact string substitution, not a JSON round-trip:* re-encoding escaped the
non-ASCII separator in the fingerprint to `\u00b7`, semantically identical but not
byte-identical, which would have been a third unintended literal change. `CURRENT_DELTA_PATHS`
is empty again and `PIN_SHA` follows the new pin.

**A `PIN_DRIFT` WINDOW IS OPEN** between the deploy and the pin landing on GitHub `main` — the
pinned SHA still says `e6ee23c` on `origin/main` while HF serves `9933615`. **Do not dispatch
the source-integrity guard until the pin merges.** This is the same window Change A opened and
closed by design.

**PR #6 MERGED TO GITHUB — 2026-08-17.** `feat/session-scoped-origin` @ `966e5bf` → `main`,
merged as merge commit **`9933615b3a9a1bdffada6cc568c2927ff9106114`** = `origin/main`.
Verified from Git rather than the UI: **two parents** (`6eb632d` + `966e5bf`) confirm the
merge-commit method rather than a squash or rebase, and the exact head CI went green on is an
ancestor of `main`. 7 commits, 10 files, +542 −27. CI `CI / test (pull_request)` passed on that
exact head — the first clean-room verification of this T2 auth change.

**`hf/main` re-verified `e6ee23c` after the merge — nothing deployed.** The owner generated the
smoke code locally against the existing production salt; it is **not yet configured** on the
Space, so the feature is inert in production by design. CI could not exercise it end to end for
the same reason, which is itself a tested property.

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
