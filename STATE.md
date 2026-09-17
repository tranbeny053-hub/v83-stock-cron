# STATE

Updated: 2026-09-17 (post-release checkpoint: PROD-SAFE-3 is live, pinned and accepted by the owner; a four-lane
post-release prep batch is built, gated and reviewed LOCALLY and waits for one owner T3; nothing has been pushed,
dispatched, applied or deployed since the release)

**Compacted on 2026-09-17.** The uncompacted record is `git show 2c6df51:STATE.md` (2,068 lines). It holds every
earlier LOOP_STATE, the full text of each boundary and ruling, the Codex verifications, the run records and the
production proofs. This branch merges 2c6df51, so that record stays reachable from main. Where the two differ, this
file governs.

## Recovery block — read this first on resume
```
LOOP_STATE=WAITING FOR THE OWNER: one T3 for the batch below, plus product decisions (OWNER_BOUNDARY).
  PROD-SAFE-3 is DEPLOYED, PINNED and ACCEPTED ("PROD-SAFE-3 is ACCEPTED", owner, 2026-09-17).
  The post-release batch is complete locally: four lanes, one composition preflight, one consolidated review.
  Since the release there has been no push, dispatch, database access, migration apply or deploy, and none is
  authorized.
  ON RESUME, check Git first: if origin/main already contains the four lane heads, the T3 has run; verify it
  against BATCH_T3 before anything else.
CURRENT_MILESTONE=Post-release prep, inside the owner's envelope of 2026-09-17:
  (1) this STATE checkpoint;
  (2) a legacy-table security migration that codifies the audited posture, NOT applied;
  (3) distributional-v2 integration prep;
  (4) the dormant wider-history path, only where v2 needs it.
  The owner excluded: a v2 freeze, a new T0, a new holdout, any database mutation, any HF deploy.
CURRENT_BRANCH=chore/state-post-106 (LOCAL; lane A), from main 08c77f09.
  - Its first commit merges the unpublished STATE history 2c6df51 (chore/state-post-104, from e5cd7ef).
  - Its second commit is this compaction. A checkpoint cannot name its own head.
  The batch lanes are all LOCAL ONLY (worktrees in the session scratchpad under lanes2/; the commits persist):
  - A chore/state-post-106: this file.
  - B prep/0010-legacy-table-security @ aaf11228: migration 0010, its one-shot route and its rehearsal
    (BATCH_0010).
  - C prep/v2-integration-prep @ 5a3b5685: the dormant v2 state builders, the proper-score skill classifier
    and the 50/50 correction (BATCH_V2).
  - D prep/v2-history-serving @ 9c53e3cb: STACKED ON C. Dormant v2 serving; candle history for 15m only.
LAST_GREEN_SHA=08c77f09 (main, PR #106, the PROD-SAFE-3 pin). Exact-main CI run 35179052192 green; tree 194a5295.
LAST_VERIFY=PASS ruff ok | 2445 passed | schemas+smoke ok | scanners 3/3 · 2026-09-17 (local).
  - Composition 0151ece2: main + B + D, where D contains C. Tree 906ccf9b.
  - Per lane: B 2393, C 2264, D 2282, against 2230 for main alone.
    2230 + 163 + 34 + 18 = 2445.
  - Lane A changes STATE.md only; its composition is gated again before the T3.
CODEX_PENDING=NONE. This batch used no Codex delegation: the owner directed that Claude owns critical reasoning
  and implementation, and that Codex is kept for bounded mechanical or adversarial verification.
  The previous change closed at 3 of its 4 delegations (task-818 to 820; .work/816/codex-818-820/).
GPT_REQUEST_ID=NONE
GPT_THREAD_URL=NONE
GPT_REQUEST_STATE=NONE
OWNER_BOUNDARY=NO ACTION IS AUTHORIZED. Requested, as one batch:
  - T3, one batch. Push B, C, D and A to origin only (never hf), open four PRs against main, and merge strictly
    in the order B, C, D, A. Each merge needs:
    - every exact-head `test` check green. B has two (ci.yml and the 0010 rehearsal); the others have one;
    - a --match-head-commit merge;
    - parents (previous main, lane head);
    - the expected tree (BATCH_T3);
    - exact-main CI green.
    Stop at the first mismatch. The lanes run one after another, so D's PR opens after C has merged and lists
    only D's files. The prepared scripts are in .work/817/t3-batch/ (run-batch.sh, then verify_batch.sh).
  - Product decisions. None is needed for the T3.
    (a) Adopt the proper-score skill gate for zero-location methodologies (R2 doc §2).
    (b) The directional display for them (R2 doc §4). The §7 correction applies: the split is a fixed skew of
        about 48-54% up, not 50/50.
    (c) §2.6 authorization to wire v2. quant/pipeline.py and config/defaults.py are evaluator-pinned.
    (d) Freeze sequencing and a new pre-registered holdout.
  - Later, separately:
    - the T4 apply of 0010: one dispatch of apply-migration-0010.yml, after B merges;
    - deleting the merged branch release/prod-safe-3, which is still on origin.
NEXT_ACTION=WAIT for the owner.
  - On the T3: bash .work/817/t3-batch/run-batch.sh, then bash .work/817/t3-batch/verify_batch.sh. It reuses
    .work/816/t3-audit's lane.sh unchanged, with a manifest of heads, files, expected trees and check counts, raw
    capture, and an independent re-check.
  - On a 0010 T4, follow the .work/816/t4-apply-0008 pattern: pre-checks, one flag-guarded dispatch, raw capture
    before parsing, then a verifier.
  - NEVER run again: §5A consume, the 0009 route, the audit, the 0008 apply, or the PROD-SAFE-3 deploy.
  - No analysis call against production. Never push to hf without a deploy authorization.
PRODUCTION=PROD-SAFE-3, live since 2026-09-17T03:39:17Z.
  - hf/main is 00705c55 (R), a convergence release: tree(R) == tree(main e5cd7ef).
  - Release UCPE-PROD-SAFE-3-20260915-A, pinned by PR #106 (main 08c77f09).
  - Guard run 35179229959: HEALTHY 3/3, deployment_delta_paths [].
  - Every user analysis runs heuristic-v1-wave4b0.
  - Scheduled guard runs report SCHEDULER_DIVERGENT_FROM_PIN. It is advisory and non-failing: the shallow checkout
    cannot prove ancestry.
  - Earlier releases: PROD-SAFE-2 a89b45e (2026-08-25) and PROD-SAFE-1 (2026-08-23).
  - Rollback is a new T4 (.work/816/l1/runbook.md).
  To watch, owner-side:
  - The functional proof of durable Detail is the operator's next genuine analysis: History should show "Detail
    available" and reopen it.
  - A203-01's strict candle adjacency and R202-01's provider deadline may surface failures that used to be silent.
DATABASE=Supabase, PostgreSQL 17 or later (the audit saw the MAINTAIN privilege granted).
  - Migrations 0001-0007 were applied before this record.
  - 0009 was applied once, 2026-09-14 (run 34861816985).
  - 0008 was applied once, 2026-09-16 (run 35164080476).
  - 0010 is AUTHORED on lane B and NOT applied.
  The older-table audit (run 35120616278, read-only) returned NOT_EXPOSED_THROUGH_AUDITED_PATHS:
  - the ten legacy tables have RLS on (not forced) and no policy;
  - anon and authenticated hold every table privilege, MAINTAIN included, yet are denied every row;
  - service_role has BYPASSRLS;
  - there is no PUBLIC grant, column grant, view, parent table or publication.
  Its findings, both addressed by lane B:
  - the migrations never enable RLS, so a rebuilt database would be open to the anon key;
  - RLS without a policy is the only barrier.
NEVER_RERUN=Consumed one-shot actions. None may run again:
  - §5A readiness runs 34863318042 (4b0a522) and 34873105124 (1d8f933).
  - The §5A ONE LOOK, consume run 34919367341 (1d8f933, population f83c31f7…). The durable seal refuses a second
    look.
  - The 0009 route: 34851608514 (refused before any DB contact) and 34861816985 (applied). Never dispatch it again.
  - The older-table audit 35120616278.
  - The 0008 apply 35164080476.
  - The PROD-SAFE-3 deploy: attempt 4, pushed at 03:39:17Z. Attempts 1-3 failed safely and changed nothing.
  - Its guard dispatch 35179229959.
  - R2 frontier research: the sealed look (folds 7-8) was consumed on 2026-09-04. Never re-run run_sealed.sh or
    edit docs/r2_evidence/SEALED_ATTESTATION.md.
  - Every T3 batch through PR #106.
SECTION_5A_RESULT=Consumed once, 2026-09-15, and recomputed offline with identical results.
  - authorized_cells = [] (NONE).
  - 15m (466 pairs), 1H (257) and 4H (86) are each NOT_PASS: "requirement(s) not met: A, B2".
  - The gate predicates were NOT_OBSERVABLE_FROM_PERSISTED_STATE, so passing A and B would still have authorized
    nothing.
  - These are pre-committed decision boundaries, not hypothesis tests, and make no profitability claim.
  - V1_QUANT_CONTRACT §5A.9 forbids retuning against this holdout. A second attempt needs a new candidate freeze,
    T_freeze, T0 and holdout.
  - distributional-v1 is not promoted.
  Evidence: .work/815/t4-consume/.
V2_STATUS=distributional-v2 is on main as an unwired module (#102). It is NOT frozen and NOT a methodology version.
  - Recipe: R2 arm CB, HAR log-variance plus a calendar profile, with empirical shape tables. BTC/USDT and
    ETH/USDT on 15m, 1H and 4H; TABLES_SHA256 f0689f29….
  - Evidence of record: docs/R2_FRONTIER_REPORT.md, docs/DISTRIBUTIONAL_V2_PREP.md and
    docs/R2_ZERO_DRIFT_GATE_AND_DISPLAY.md.
  - Lanes C and D prepare everything that touches no evaluator-pinned file.
  - Wiring needs §2.6 authorization.
  - Adopting the proper-score gate also needs per-row probabilities from persistence/repository.py, which is pinned.
  - Correction (lane C): with mu = 0, the up share is not 50/50. The shape tables fix it between 0.4794 and 0.5427.
BATCH_0010=Lane B has four commits:
  - e5677406: the route;
  - aeef379c: PostgreSQL 17 MAINTAIN;
  - 1d581367 and aaf11228: the review fixes.
  Migration 0010 (sha256 bc2ec1dd…):
  - enables RLS where it is off;
  - REVOKEs ALL on the 10 tables and 3 serial sequences from PUBLIC, anon and authenticated;
  - GRANTs the 7 portable table privileges to service_role.
  Effective access in production does not change.
  The route: scripts/apply_migration_0010.py and .github/workflows/apply-migration-0010.yml (dispatch-only; confirm
  APPLY-MIGRATION-0010-ONCE; advisory lock 5000010). It runs ONE transaction:
  - pre-checks require the audited state, so a second apply refuses ("not a first apply"). The tables of
    0005, 0006, 0008 and 0009 are recorded, not required;
  - the server's version decides which privileges are asked about;
  - it executes the exact pinned bytes;
  - post-checks, then a commit only if everything passes. If the connection fails while the COMMIT is in
    flight, the report says committed "UNKNOWN".
  The PR-time rehearsal has NEVER RUN on GitHub (.github/workflows/apply-migration-0010-rehearsal.yml; job `test`;
  scratch PostgreSQL 16; no secret). This machine has no PostgreSQL, so its first run is B's exact-head check. A
  failure there stops the T3 before any merge.
BATCH_V2=Lane C has three commits: 9101bff2 (the prep), then 679e0801 and 5a3b5685 (the review fixes).
  - quant/distributional_v2_state.py builds v1's exact probability_state and horizon_timeout_state from a v2
    triplet. Tests check field-by-field parity and the schema.
  - calibration/proper_score_skill.py is R2 §2's gate. It fails closed, uses the §5A statistics kernel, and
    counts score differences within 1e-12 as none. Nothing selects it.
  - The 50/50 correction: docs §7, plus a test that recomputes its table.
  - The unwired v2 guard lists the dormant prep modules and proves nothing imports them.
  Lane D (9c53e3cb, parent 5a3b5685): quant/distributional_v2_serving.py.
  - 1H and 4H come from the snapshot's 204 closed candles, with no request.
  - 15m is the only timeframe that needs more. It fetches exactly 673 closed candles, once, from the snapshot's own
    provider, and requires assert_history_extends_snapshot.
  - Everything else fails closed.
  - The adapters' guard allows exactly this one dormant caller and proves nothing imports it.
  C and D both extend the same guard, so D is stacked on C and must merge after it.
BATCH_T3=The expected main tree after each merge, in order, from main 08c77f09:
  - B aaf1122874d825df72aac980794714d72e552e75 -> tree 071556e3754de16f30544777db52e54c37b37966
    (files: 11; head checks: 2);
  - C 5a3b568523b580f4aad2af5d28f381b169f68774 -> tree 6bd22f37d932b8f34fa9e99c105a42e119709d28
    (files: 8; head checks: 1);
  - D 9c53e3cbe71af06eebcf0b9d5ede2ade8b1974be -> tree 906ccf9bced1fec92b3959a6ab50790b990325ea
    (files: 5; head checks: 1). This equals the gated composition;
  - A (this branch) -> STATE.md only (head checks: 1). A checkpoint cannot state its own tree; the owner
    report and .work/817/t3-batch/manifest.txt carry it.
REVIEW=One consolidated review of the composed diff (an Opus subagent, read-only, 2026-09-17), then one
  bounded re-check of the fixes. There was no CRITICAL or HIGH finding.
  - MEDIUM (C), FIXED. An exact echo of the base rates could "demonstrate" proper-score skill through float
    noise. normalize_probabilities divides by sum(...), which is compensated on Python 3.12+ and naive on 3.11.
    - Score differences within 1e-12 now count as none.
    - A regression sweep covers it, and the test fails without the fix under both summation styles.
    - The re-check: no zero-skill set reached a pass (18,618 random sets), and no real improvement was
      suppressed (40,000 trials).
  - LOW (C), for decision (a), written into the module note:
    - rows are treated as independent, so overlapping horizons and repeated analyses overstate the evidence;
      adoption must choose de-duplication or window means;
    - adoption also needs new detail-view wording (detail/frontend_display.py).
  - LOW (C), FIXED:
    - the timeout-state description;
    - R2 doc §7's DOWN-leaning list. It is now exact at the tabulated ratios, pinned by a test, and the
      finer-grid boundaries are stated.
  - LOW (B), FIXED:
    - refusal paths the audit never measured: same-named relations of other kinds, and the presence of the
      0005/0006 tables, which is now recorded rather than required;
    - a COMMIT failing in flight is reported as "UNKNOWN", including in the rehearsal's per-apply records.
  - LOW (B), RESIDUAL. The PostgreSQL 17 (MAINTAIN) branch runs only against the fake cursor, because the PR
    rehearsal uses the runner's PostgreSQL 16.
    - A defect there would refuse or roll back safely, but it would spend the 0010 T4.
    - Otherwise the statement forms are ones production has already run (0008, the audit).
  - LOW, inherited, report only. The 0008 and §5A routes would also report committed=false after a COMMIT
    failed in flight. Both are consumed, so there is nothing to change.
  - Held under attack:
    - every rehearsal step on a stock ubuntu-24.04 runner;
    - the pre-checks against the audit artifact;
    - the trust boundary: the secret in one step, plus dispatch, token and URL handling;
    - v2's probability_state parity;
    - lane D's windows, provider check and extends-snapshot check;
    - no pinned, scanner or guard file weakened.
STANDING_RULES=
  - Tiers and budget are in CLAUDE.md. Authorizations are one-shot and name exact SHAs. Owner interactions are
    batched.
  - The 69 evaluator-pinned files (ops/section_5a_evaluator_pin.json) change only with §2.6 owner authorization
    that states what changed and why. The pinned red tests (tests/oos/evaluation/test_g1_g7_red.py) are never
    edited.
  - The three safety scanners and tests/test_no_silent_skips.py are never weakened or narrowed.
  - No database access, migration apply, workflow dispatch or deploy without its own authorization.
  - Every T4 captures raw evidence before parsing it.
  - Never request or expose a secret or a database URL.
  - DEPLOY_PROHIBITED was lifted on 2026-09-15, but every push to hf is still a deploy that needs its own
    authorization.
  - Run provenance fails closed, and any successor must keep it that way:
    - put() needs an explicit prediction_origin;
    - UNCLASSIFIED is never persisted;
    - /v1/runs allows USER_REQUESTED only.
  - Owner product decisions of 2026-08-28 are closed; never re-propose them:
    - Recent History stays fixed and bounded for v1;
    - constant system_status fields stay hidden unless a real operator use case appears.
  - The collector has been stopped on main since #88; restoring its schedule fails the build. The outcome resolver
    stays scheduled (resolve-outcomes.yml, cron "17 * * * *").
  - Owner rulings D1-D4, J1-J3, K1-K2, L1-L3, M1 and N1-N3 are applied. Their full text is in 2c6df51:STATE.md.
OPEN_ITEMS=Non-blocking; none is authorized.
  - scripts/check_no_secrets.py also scans .work/ (SKIP_DIRS omits it), so a stale gitignored log can fail
    ./verify.sh on a clean tree. Fixing it narrows a mandatory scanner, which needs an explicit owner decision.
    Meanwhile, delete stale .work/*.log files.
  - oos-pair-evidence.yml and resolve-outcomes.yml still pin Node-20-era actions (checkout@v4, setup-python@v5).
    They were frozen for the holdout, which is now closed.
  - Merged branches remain on origin, including release/prod-safe-1 to -3. Deleting any of them needs the owner.
  - As of 2026-08-22, per-timeframe calibration MEASURED needed about 3x more operator traffic (134-172 samples per
    timeframe, against a threshold of 500).
EVIDENCE=.work/ is gitignored and local.
  - 805-814: the §5A evaluator's verification and its T3/T4 runs.
  - 815: the one look.
  - 816: this release cycle (evidence.sha256): the l1-l3 prep, t3-audit, audit-dispatch, codex-818-820,
    t4-apply-0008, t3-release, t4-deploy and t3-merge-guard.
  - 817: this batch.
    - t3-batch/ is the prepared T3: manifest, titles, bodies, run-batch.sh and verify_batch.sh.
    - batch/ has every lane and composition verify output, the expected-tree computation, and the review
      record (review.md) with its probes.
```
Update this block on every pause, every milestone change and every GPT consultation.
`GPT_REQUEST_STATE` ∈ `NONE` · `DRAFTED` · `SENT_WAITING_RESULT` · `COMPLETED_RESULT_SAVED` ·
`SKIPPED_UNAVAILABLE`.

## v1 at a glance
- **Change A** (calibration truth and skill gating) was deployed in 2026-08 and is closed.
- **Change B, tranche 1** (distributional-v1 against a pre-registered holdout) is closed. The §5A one look was
  NOT_PASS on every timeframe, and nothing was promoted.
- **R2 frontier research** is closed. It recommends distributional-v2 as the next candidate; the candidate is not
  frozen.
- **In production (PROD-SAFE-3):**
  - Recent Analysis History and durable Detail;
  - session and auth hardening;
  - provider byte caps and deadlines;
  - strict candle adjacency;
  - the accumulated reviewed UI work.
- **Next, owner-gated:**
  - the batch T3;
  - the v2 decisions (a) to (d);
  - the 0010 apply.
  A v2 promotion needs its own freeze, T0, holdout and one look.
