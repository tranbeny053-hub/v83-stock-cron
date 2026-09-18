# STATE

Updated: 2026-09-19. R4's single F2 + F1 look RAN ONCE (owner T4, 2026-09-18T16:29Z, claim 95c339ef…) and is
consumed: 15m and 1H are HISTORICALLY CONFIRMED, with C1 carried at both. 4H was excluded, never read, and is still
unspent. Stage C, which is mechanical: C1 wrote the decision record. C2 (V2b) STOPPED: V2b's frozen machinery needs
F2 rows, which the look never persisted, and the freeze already records V2b as not run. C3's bounded Codex second
implementation (one delegation plus its one targeted repair) reproduced the decision exactly, and its sign-flip
Monte Carlo moved no threshold. The independent Fable re-audit is next (NEXT_ACTION). main is 9bb2cde
(#112, the freeze-4 publication, CI green). hf is unchanged at 00705c55. This record is local; publishing it is a T3.

**Compacted on 2026-09-17.** The uncompacted record is `git show 2c6df51:STATE.md` (2,068 lines). It holds every
earlier LOOP_STATE, the full text of each boundary and ruling, the Codex verifications, the run records and the
production proofs. This branch merges 2c6df51, so that record stays reachable from main. Where the two differ, this
file governs.

## Recovery block — read this first on resume
```
LOOP_STATE=WAITING FOR THE OWNER: hand R4 Stage C to the independent Fable re-audit (NEXT_ACTION). Nothing pushed.
  - Stage-C instruction (owner, 2026-09-19), verbatim: "Continue from the completed R4 Stage-B one-look. Treat the
    one-look as final: F1/F2 15m+1H are consumed and must never be reopened, rescored, retuned or rerun; 4H remains
    unread/unspent. Execute Stage C exactly as frozen: C1 create the durable R4 decision record from the
    already-persisted look evidence; C2 run V2b mechanically using only inputs already preserved by the look plus
    DEV, first proving those persisted summaries are sufficient—if any raw F1/F2 reread would be required, STOP
    instead. No model search or rule changes. Then prepare C3: one minimal bounded Codex second
    implementation/Monte-Carlo task only, optimized for minimal Codex tokens, and a separate minimal Fable MAX
    independent-audit pack. Do not substitute Codex for Fable judgment. Finish deterministic/local verification,
    update STATE locally, and stop before any push, collector activation, freeze/wiring/deploy or other T3/T4.
    Also report whether C2 changes any Stage-B status and the exact Fable handoff needed next."
  - The R4 look T4 (owner, 2026-09-18) is CONSUMED and VERIFIED. The owner's words are verbatim in
    r4/stage_b/AUTHORIZATION.txt (sha256 b344bfb1…). One command, one clean pass; evidence in
    r4/stage_b/look_evidence (R4_STAGE_B, R4_STAGE_C).
  - The freeze-4 publication T3 (owner, 2026-09-18) is CONSUMED and VERIFIED as PR #112 -> 9bb2cde. It was
    re-authorized once, only to correct the post-merge tree check. Both texts are verbatim in
    r4/stage_c/b_run/T3_112_AUTHORIZATION.txt.
  - Pre-look audit ruling (owner, 2026-09-18), verbatim in the freeze-4 commitment: "Fable NO-GO accepted:
    re-freeze #4 with I2/I8/I10 exactly tightened; fix M3 in code with deterministic pre-claim resume/no manual
    deletion, refuse --workdir in look mode, bundle L2+L4, and L3=YES only for predeclared diagnostic summaries
    (weekly block means + fixed-band deployment effects; no raw rows; never tuning). Treat this as stricter
    pre-look interpretation, not a §5.8-2 edit."
  - Stage-A rulings (owner, 2026-09-18), verbatim in r4/stage_b/STAGE_B_COMMITMENT.json:
    - the F2 + F1 confirmation look = YES (to be run only as OWNER_BOUNDARY describes);
    - 4H is excluded from R4 fresh scoring only; live/product 4H is unchanged;
    - the collector is on HOLD until a carried candidate exists;
    - D0 remedy-and-continue is ACCEPTED;
    - envelope for this step: prepare locally; no push, no F1/F2 read or score, no network, no DB, no dispatch.
  - R4 rulings (owner, 2026-09-18): O-1, O-2, O-3, O-5, O-6, O-7 = yes; O-4 = yes ONLY under the
    adjudication's §8. Stage A only; no network, F-look, F3, product, pinned, DB, collector, wiring, freeze
    or T0.
  - R4 owner amendment (2026-09-18), recorded verbatim in m0/R4_DECISION_RULES.json: F2 was touched once, in
    Wave 2, candidate-blind - only B3Dev and the references were scored on it, for the N4 real-regime null.
    No C0-C3 candidate was ever fitted or scored on F2 and no rule or constant was tuned on it. F2 was not
    re-read in Stage A, so V1 chose the reference memory on DEV alone.
  - Wave-2 rulings (owner, 2026-09-17):
    - Wave 2 GO; R3C and the three exploratory arms are research-only;
    - v2 exact symmetry, v1 unchanged;
    - Binance is canonical, with same-venue resolution and no silent provider switch;
    - the 4H slope rule stays [0.9, 1.1]; L_max = 16 weeks;
    - the F3 first block is 2026-09-21T00:00Z;
    - gate order: G1/reference repair → G2 per the audit → G3/G4;
    - still forbidden: product, pinned files, DB, collector, wiring, freeze, T0.
  - Earlier, the owner ruled on the E0/G1 questions and ran Wave 1 as a research-only step (R3). The rulings:
    - Lane D public/keyless outbound = GO;
    - W = 7 UTC days is a research candidate, not a gate;
    - 4H stays in;
    - the collector stays off;
    - the F3 exclusion ends no earlier than 2026-09-20T04:00Z.
  - Before that, the owner accepted the 0010 T4 ("no further DB action") and started R3 with E0 + G1,
    treating .work/research3/FABLE_FRONTIER_AUDIT.md as the research plan, not production authority.
  - PROD-SAFE-3 is DEPLOYED, PINNED and ACCEPTED (owner, 2026-09-17).
  - The owner-authorized batch T3 is CONSUMED and VERIFIED: B #107, C #108, D #109, A #110 (BATCH_T3).
  - The owner-authorized 0010 T4 is CONSUMED and VERIFIED: run 35190794876 (BATCH_0010).
  - Since then there has been no other dispatch, database access or deploy.
CURRENT_MILESTONE=R4 STAGE C IN PROGRESS (research only). C1 is done, C2 STOPPED, and C3's Codex second
  implementation is done and agrees. C3's independent Fable re-audit is next, then C4, the owner package. Stage B's
  look is consumed; Stage A, R3 Waves 1-2, E0 and G1 came before it. Still excluded: collector activation, a
  freeze, wiring, a new T0, any database action, any HF deploy, and any further F1/F2 read.
CURRENT_BRANCH=chore/state-post-112 (LOCAL, no upstream), from main 9bb2cde: this record, unpublished
  (OWNER_BOUNDARY). chore/state-post-110 is merged (#112) and stays on origin: its push is the commitment's timestamp.
  The batch branches are merged, and remain on origin:
  - prep/0010-legacy-table-security;
  - prep/v2-integration-prep;
  - prep/v2-history-serving;
  - chore/state-post-106.
LAST_GREEN_SHA=9bb2cde (main, PR #112: the R4 freeze-4 publication, STATE.md only).
  - Merged 2026-09-18T16:03:50Z by this loop under the owner's T3, with --match-head-commit 2860ab3e.
  - Parents (535248d1, 2860ab3e); tree f3df2035; STATE.md blob 24ae56b4. #111's three files are byte-identical to
    535248d1.
  - The exact-head check `test` passed at 15:37:46Z and the exact-main check `test` at 16:06:40Z (2026-09-18).
  Before it: 535248d1 (PR #111: the last two Node-20-era workflows moved to the reviewed Node-24 pins).
  - Merged 2026-09-17T07:36:36Z from the owner's account. It was not created or merged by this loop.
  - Parents (e22ce337, e0dd56ac). It changes only oos-pair-evidence.yml, resolve-outcomes.yml and a new
    workflow test; no src/, ops/ or STATE.md.
  - Exact-main CI run 35195392429 green.
  Before it: e22ce337 (PR #110), whose exact-main CI run 35189507625 was green. Its tree 2e1667b4 is the
  owner-authorized, locally gated composition.
LAST_VERIFY=PASS ruff ok | 2450 passed | schemas+smoke ok | scanners 3/3 · 2026-09-19 (local).
  - Run for this R4 Stage-C record on chore/state-post-112, i.e. main 9bb2cde plus this change. R4 lives in
    gitignored .work/, so the change is STATE.md alone (T0). 2450 = the earlier 2445 + the 5 tests of #111's
    workflow test file, now on main.
  - Stage C's own checks: verify_stage_c.py 12/12 (STAGE_C_VERIFIED). Since the look, nothing outside r4/stage_c
    changed under .work/research3, and src/ and the tracked tree are unchanged.
  - Re-run for this R4 freeze-4 record, on the STATE branch at acf6f95 plus this change: the same result (2445
    passed, scanners 3/3), 2026-09-18. R4 is entirely inside gitignored .work/, so the change is STATE.md alone
    (T0). The same held for the freeze-3 record at a8d7920 and the Stage-A record at da794b1.
  - Re-run for the R3 Wave-2 record, on the STATE branch at 529ec7e plus that change: the same result
    (2445 passed, scanners 3/3). The same held for the Wave-1 record at 56ca7f8.
  - Composition c641fec2 (B, C, D, A onto 08c77f09) has tree 2e1667b4, equal to main e22ce337.
  - Per lane: B 2393, C 2264, D 2282, against 2230 for main alone. 2230 + 163 + 34 + 18 = 2445.
  - Independent post-merge re-check: .work/817/t3-batch/verify_batch.sh returned BATCH_VERIFIED, 46 checks
    (verify_batch.output).
CODEX_PENDING=NONE. The owner directed that Claude owns critical reasoning and implementation, and that Codex
  is kept for bounded mechanical or adversarial verification.
  - The batch and R3 Wave 1 used no Codex.
  - R3 Wave 2 used one bounded delegation: the audit's E-7 independent re-derivation.
    - Files: .work/task-820.md, result-820.json (DONE) and codex-820.log.
    - The number repeats an earlier task kept in .work/816/codex-818-820/. That task was not touched.
    - The log shows it read only the protocol, the errata, the task file and the data. The task file
      restated the definitions, including the first implementation's reading of ambiguous points.
    - Its outputs equal the first implementation: 8,856 deterministic values, max diff 1.7e-17.
    - Scope: allowances, effects, N4 rates and method-A power. The Monte Carlo nulls, N3, N5, method B and the
      selection code were not re-derived.
  - R3 Waves 1 and 2 and R4 Stage A were each audited once by a single read-only Claude review agent,
    followed by one bounded re-check of the findings. R4 Stage A used no Codex.
  - R4 Stage C used the one bounded C3 delegation plus its one targeted repair (2 of 4 delegations).
    - task-822 stopped BLOCKED in its comparison adapter, because the task under-described the recorded layout.
      The first causal failure is preserved: result-822.json, codex-822.log and c3/second_impl.attempt1.py.
    - task-823 (DONE) changed only that adapter.
    - Codex read only the two blinded evidence files and its own task and script. It opened no sealed file, no
      snapshot copy and none of decision.py, look.py or pipeline.py.
  The previous change closed at 3 of its 4 delegations (task-818 to 820; .work/816/codex-818-820/).
GPT_REQUEST_ID=NONE
GPT_THREAD_URL=NONE
GPT_REQUEST_STATE=NONE
OWNER_BOUNDARY=NO ACTION IS AUTHORIZED. Consumed since the previous record, in order: the Fable review of freeze 4
  (GO_FOR_T3), the T3 publication (#112) and the look (T4). What remains, in order:
  1. C3's independent re-audit: one read-only Fable MAX session on r4/stage_c/FABLE_STAGE_C_AUDIT_PACK.md
     (NEXT_ACTION has the exact handoff). It must not open F1/F2 or their snapshot copies. Any finding is
     fixed by one bounded re-check, which never touches F1/F2 either. The statuses are final either way.
  2. C4, the owner package, after an ACCEPT.
  3. T3 (owner authorizes): publish this record (chore/state-post-112, STATE.md only).
  4. Owner decision now due: the collector HOLD's condition ("until a carried candidate exists") is met, since C1 is
     carried at 15m and 1H. Activating the collector is the owner's call, never an automatic step. No freeze,
     wiring or deploy follows from R4 without Stage D (adjudication §6, §9).
  5. Standing: gate research is CLOSED for this generation (V2a; C2 did not reopen it). F1/F2 at 15m and 1H are
     spent forever, and 4H is unspent.
  R3 decisions requested in
  .work/research3/wave2/WAVE2_REPORT.md §6:
  1. gate scope after the G3 exclusion:
     (a) research only, recommended;
     (b) a 15m long-holdout design (R4, L up to 52 weeks), which changes the L_max ruling and needs a
         re-audit. 15m R4 at L16 was the nearest miss: it failed only N2's d = 0.20 case and method B /
         agreement;
     (c) a window-conditional estimand, not recommended;
     (d) research toward a stronger candidate;
  2. 4H: no demonstrated Brier skill beyond a day-type base rate at the primary band, a product question. The
     kept slope rule also blocks every 4H element that leaves R3C's miscalibration in place;
  3. F3: (a) weekly public-kline accumulation from 2026-09-28T02:00Z (labels only); (b) exclusion-window klines
     as inputs for the first F3 week;
  4. the 1H BTC factor: keep R3C (recommended; the Wave-2 adoption rule), or take recompose v3's primary-band
     pick (the Wave-1 simplicity rule; sub-floor, a 6e-5 tie-break, one band only, and ETH would need BTC
     klines);
  5. the estimand sentence and the gating comparator (moot until item 1 opens a gate path);
  6. still open from Wave 1 (Lane S): H_extended; zero-location dispositions; additive fields and display.
  Wave-1 rulings already given: the candidate (R3C), the venue policy, v2/v1 symmetry, the 4H slope rule,
  Wave-2 GO. Still open from Wave-1 Lane I: the ledger columns, gate_trace storage, the evidence source (G4 now
  favours the lattice).
  CONSUMED, with each authorization kept verbatim:
  - the batch T3 (.work/817/t3-batch/authorization.txt);
  - the 0010 T4 (.work/818/t4-apply-0010/authorization.txt);
  - the R4 freeze-4 publication T3, PR #112 (.work/research3/r4/stage_c/b_run/T3_112_AUTHORIZATION.txt);
  - the R4 Stage-B look T4, claim 95c339ef… (.work/research3/r4/stage_b/AUTHORIZATION.txt).
  Open, each needing its own authorization:
  - Product decisions:
    (a) adopt the proper-score skill gate for zero-location methodologies (R2 doc §2). This needs the
        dependence decision and the detail-view wording (REVIEW);
    (b) the directional display (R2 doc §4). The §7 correction applies: the split is a fixed skew of about
        48-54% up, not 50/50;
    (c) §2.6 authorization to wire v2. quant/pipeline.py and config/defaults.py are evaluator-pinned;
    (d) freeze sequencing and a new pre-registered holdout.
  - T3: publish this STATE record.
  - T3: delete merged branches: release/prod-safe-3 and the four batch branches.
  - The OPEN_ITEMS decisions.
NEXT_ACTION=WAIT for the owner to hand Stage C to the independent Fable re-audit (OWNER_BOUNDARY 1). Use a Fable MAX
  session whose working directory is /Users/kha/Documents/Kha-app/UCPE: preferably the existing "Fable 5.1 MAX audit"
  session (7b81d821), which audited freeze 4, or a fresh one. Send it exactly:
    "R4 Stage C — C3 independent re-audit, read-only. Read
    .work/research3/r4/stage_c/FABLE_STAGE_C_AUDIT_PACK.md (sha256 f104f25f…4e97) and follow it exactly. Write
    nothing. Never open .work/research3/r4/stage_b/look_run/snapshot/, .work/research3/wave2/data/f1_sealed/,
    .work/research3/wave2/data/f2_sealed/ or .work/research3/wave2/gate/data/. Never run look.py, rehearse_b.py,
    recheck_prelook.py or c3/second_impl.py. The only command you may run is the read-only verifier: cd
    .work/research3/r4/stage_c && ../../../research2/.venv/bin/python -B verify_stage_c.py. Reply with a verdict
    per item A-G and one overall ACCEPT / ACCEPT WITH FINDINGS / REJECT."
  After it: C4, the owner package (the collector decision included), then the T3 that publishes this record.
  - look.py --look refuses forever. Never run rehearse_b.py again.
  No R3 step before a ruling on WAVE2_REPORT.md §6.
  - The prepared F3 tool (.work/research3/wave2/f3/f3_accumulate.py) refuses before 2026-09-21T00:00Z and must
    not be run without ruling 3.
  - Candidate next work, once approved (WAVE2_REPORT.md §7): W3-A long-holdout protocol (only if 1b);
    W3-B weak-fold diagnosis; W3-C 4H calibration; W3-D serving contract; W3-E F3 accumulation.
  - NEVER run again: §5A consume, the 0009 route, the audit, the 0008 apply, the 0010 apply, or the PROD-SAFE-3
    deploy.
  - No analysis call against production. Never push to hf without a deploy authorization.
R4=Research generation 4, Stage A, in .work/research3/r4 (gitignored). Analysis only; no sealed set was
  opened, no network call was made, and nothing outside r4/ was written (verified by mtime across research3).
  - Input: FABLE_R4_ARCHITECTURE_ADJUDICATION.md, sha256 5633c49b…, 610 lines. An independent review, advice
    only. It is NOT in git; the owner supplied it into the gitignored .work tree.
  - Package: r4/R4_STAGE_A_REPORT.md, R4_STAGE_A_TABLES.md (generated by render_tables.py), README.md,
    RECHECK_STAGE_A.json, and ../evidence_r4.sha256.
  - Registry frozen by digest: m0/R4_CANDIDATES.json 8249c429…, m0/R4_DECISION_RULES.json 94280cdd….
    m1/pipeline.guard() refuses to open a confirmation run if either moves; build_registry.py refuses to
    rewrite the digest log once it exists. The registry was frozen LAST, over the final lane code: what it
    binds is Stage B, and the Stage-A lanes are bound by evidence_r4.sha256 instead.
  - D0 (the gate on every other lane): 98 of 99 §1 headlines reproduce inside the 10% rule. The miss is 15m
    Brier weakest-fold weeks 22 -> 25 (13.6%, conservative), so the literal closure rule FAILED and its
    prescribed remedy was applied before anything else ran: §1 re-derived into d0/D0_SECTION1_REWRITE.md. No
    §1 verdict changes. Two definitional findings: "fold effect" has two admissible readings (rows kept by the
    block design reproduce §1.1; fold means of block means reproduce D-3), and Appendix A's delta log loss is
    measured on all rows with finite IV, not on the lattice.
  - V1 (reference generation 2, candidate-blind, DEV only): the adjudication's "strictly harder to beat" guard
    applies at all three bands, because §5.5 checks the sign at 0.003 and 0.0045. Only 15m admits a change
    (28 -> 7 days). 1H and 4H keep generation 1: the memories a band-0.002-only rule would have picked (1H 56
    days, 4H cumulative) are EASIER to beat at the sign-check bands, which would have weakened the frozen
    Stage-B test. Spec digest dd74e881….
  - M1 (the confirmation pipeline, rehearsed, never used on a sealed set): R3C's pooled DEV log loss
    reproduces exactly (1.044444 / 1.032848 / 0.910918); the E8 replay re-derives 1,416 floats and 96 booleans
    with 0 mismatches (worst 2.1e-17); the crash test passes 9 conditions, including scoring-before-claim
    refused and a m0/LOOKS_CONSUMED.log ledger that refuses a second look even after the run directory is
    deleted. On DEV, 15m and 1H pass the §5.5 primary rule and 4H fails on the Brier p-value alone
    (log loss -0.0123 at p 0.0004; Brier -0.0007). DEV is mined: these are rehearsal numbers, not claims.
  - V0 (staleness, fold-matched): 15m is flat to 361 days (0.98 / 0.98 / 0.93 / 0.97); 1H is 0.92 at 242 days
    and 0.73 at 403; 4H is 0.58 at 363. A 52-week 4H holdout is not covered by the 25% haircut.
  - V3: PSG-2's |A - B| <= 0.10 agreement rule rejects CORRECT designs up to 69% of the time (33% at the 15m
    L16 cell). The one-sided A >= B - 2*SE_A holds 96-99%. No PSG-2 verdict changes: the cell that failed had
    A above B.
  - U1 (nonlinear closure probe, never a candidate): a boosted regressor is WORSE than linear on every
    timeframe (-3.2% / -5.6% / -18.9% pooled, 2/0/0 of 6 folds improved). The family is closed for this
    generation.
  - V2a (PSG-3 design freeze for 15m, run only because O-4 = yes under §8): 30 designs, ZERO qualify. Without
    the regime allowance size is 0.093-0.197 against a 0.050 ceiling; with it, power is 0.05-0.20 against
    0.80; beyond L = 26 the allowance is not estimable at all (N_eff = 1 at L 39 and 52). N5 is 0.000
    everywhere. The pre-declared closure fires: 15m is prospectively ungateable under this estimand and GATE
    RESEARCH STOPS FOR THIS GENERATION. PSG-2 was read, never rerun or amended.
  - Design papers (advisory, binding nothing): s1/STATUS_VOCABULARY.md (four statuses, the estimand sentence,
    forbidden words) and r1/REPLACEMENT_CLAIM.md (the claim R4 cannot make, the minimal collector, and the
    18-week floor on 15m).
  - Audited once, read-only: 3 HIGH, 9 MEDIUM, 12 LOW. All bounded findings fixed; three changed results
    rather than wording (V1's band scope, V0's fold matching, M1's claim-before-score ordering). The ONE
    bounded re-check (recheck_stage_a.py) asserts every finding's fix mechanically: 40/40 pass.
R4_STAGE_B=The pre-look package, .work/research3/r4/stage_b (gitignored; nothing in it has read F1 or F2).
  - Digest commitment: FREEZE 4, frozen locally 2026-09-18T14:01:42Z (freeze-once). Freezes 1-3 were superseded
    before any push and are kept in stage_b/superseded/ with their reasons; freeze 3 (d53c404a) got the Fable
    NO-GO. These lines are what the T3 push timestamps; every other pin (49 code files, 28 sealed-input digests,
    environment, constants, rulings, 15 interpretations, the diagnostics declaration) is inside the commitment,
    and every other R4 file is inside evidence_r4.sha256:
    ```
    154a75c48d89bb3e9ff76914b4b1926d91fecc4a48bf9448c1e4f93b628e2211  r4/stage_b/STAGE_B_COMMITMENT.json
    8249c4297066127c9eb440ee62e2b7919842a7a2c98c3c1d34a51c0b54ae2b13  r4/m0/R4_CANDIDATES.json
    94280cddbf789258bdff4db03bb534f146d3a0f9d43a1dc87b9f8682a2132bd3  r4/m0/R4_DECISION_RULES.json
    81160254fce7a3fdfffbb1b17cfb4e4fb5e29189c6ec427b63d4792ba1a65c35  r4/v1/REFERENCE_SPEC_V2.json
    77a4ebc008674d01b2ff723fcc0a9593c19d1b96b311f7976c1249948f618f47  r4/stage_b/decision.py
    c69404b826ee134fe1e4ed74b7a1c4dbe07cdaf83d7bcf89f6d3e5b90d44a245  r4/stage_b/look.py
    a6a258992e50c05c99ff8129373c6d55cea091f6559263080cb329f1fa6eba24  r4/m1/pipeline.py
    a8afc590df368850c5dc7c98c1834594e64fb94e77f9a4abc70638ce8dfcd79f  r4/stage_b/F2_PROVENANCE.json
    80f4940f5cc2af078741e8e9a1752df0c6ef9ba070ed592a56d07cb393746371  r4/stage_b/REHEARSAL_B.json
    dcc2b8ff005185785cabb4f06ba83fffdbfb8f806688b0fee602f5595caa8fbc  r4/stage_b/RECHECK_PRELOOK.json
    622fbc84f29b937693048e8a628fdf4ab2f6f6f0ea11d53ba506dfc8ac8fc2f9  r4/stage_b/RECOVERY.md
    6519f495942012ec3fd0fee66b0c99f8416e70b98080ff47dbf71ab737ed7174  r4/stage_b/FABLE_PRELOOK_AUDIT_PACK.md
    93bb78751cd71dcb7664f63d7c93451d343927c9ffe14b5d33a64dac41116b93  evidence_r4.sha256
    092a93043f789b82869c06fec6dfdd16f754dc3c7fd97f7c357828cecd9bc3ad  evidence_wave2.sha256
    5633c49bb9232f906feb5a65ba5c9be8d981264be59e5428b4a2694341510bf0  r4/FABLE_R4_ARCHITECTURE_ADJUDICATION.md
    ```
  - Freeze 4 answers the Fable audit (session 'Fable 5.1 MAX audit', 2026-09-18) as the owner ruled, as a
    stricter pre-look interpretation and not a §5.8-2 edit (M0 byte-identical, no sealed score exists, the pass
    region only shrinks):
    - H1/I8, M1/I2, M2/I10: the audit's texts verbatim. Every candidate carried at any point must pass the
      primary rule; each score is counted separately on F2 deployments and F1 symbols; a knob-free 90% MCS is
      computed from the ordered-pair p-values, reported, never used.
    - M3: a crash before the claim resumes deterministically (same blind map, copies verified, completed or
      atomically replaced, the resume recorded in the claim); nothing is deleted by hand.
    - L1: look mode refuses every flag but --look and creates nothing before its checks; a single-use claim
      reserves its sets in m0/LOOKS_CONSUMED.log at claim time, so an orphaned claim can never be replaced.
    - L2: the control must demonstrably fail on EACH set, else UNINFORMATIVE; recovery re-checks the blind map.
    - L3 (owner: YES): predeclared diagnostics only - weekly block means and per-unit deployment effects of model
      minus reference, both scores, bands 0.002 / 0.003 / 0.0045; no raw rows; never read by the decision; never
      used to tune.
    - L4: AUTHORIZATION.txt is snapshotted into the claim; this digest block is extended.
    - L5: unchanged (the audit judged it irrelevant for `python look.py`).
  - Scope: 15m and 1H; 4H is excluded (owner ruling) and is never reported as a status. Candidates C1 < C0 < C2 <
    C3 in the fixed sequence (15m C1 -> C2 -> C3, since C0 = C1 there; 1H C1 -> C0 -> C2 -> C3); controls static
    day-type (must fail) and B3Dev; comparator = reference generation 2 (15m 7 days, 1H 28 days). F2 =
    build_f2.py's grid, a deployment is one grid fold; F1 = DEV folds 1-6 exactly as E8, with no cross asset
    (unused by every model). The look imports 14 product modules through R2's code (B3Dev's frozen parameters,
    calibration metrics); they are pinned and byte-identical on the main worktree (2c6df51) and on main.
  - Provenance (F2_PROVENANCE.json, from code, manifests and reports only): F2's only reader was
    wave2/gate/build_f2.py, which fitted B3Dev only and scored B3Dev and the 28-day references under the
    'reference_model' guard. No C0-C3 candidate was ever fitted or scored on F2. F1 has never been read by any
    scoring code. The audit re-derived this independently.
  - Rehearsal REHEARSAL_B.json 11/11 PASS against freeze 4 (stand-ins only, under an audit-hook tripwire): B1-B4
    and B9 data paths exact; B5 crash after the claim recovers, a crash before the claim resumes with the same
    blind map and a damaged copy repaired, and a rerun, a deleted result, a tampered copy and a changed blind map
    are refused; B6 look mode refuses every extra flag and, with no flag, passes commitment, registry, code,
    environment and constants and stops only at the missing authorization, creating nothing; B7 decision cases
    incl. the audit's counterexample; B10 diagnostics present and inert; B11 claim-time reservation. The one
    bounded re-check of the diff, RECHECK_PRELOOK.json, passes 24/24 and shows nothing outside the diff moved.
  - Disclosed: Stage A's evidence-manifest builds hashed the sealed files' bytes when re-verifying the Wave-2
    manifest (integrity only; the audit judged this consistent with "no F-look"). From the Stage-B preparation
    on, that script skips them.
  - THE LOOK RAN ONCE: owner T4, 2026-09-18T16:29:19Z-16:29:52Z, claim 95c339ef…2b40, authorization b344bfb1….
    Before any sealed open, 30/30 preconditions passed. It was one command, one clean pass, exit 0.
    - Result, code-decided: 15m HISTORICALLY CONFIRMED and 1H HISTORICALLY CONFIRMED, with C1 carried at both.
    - C1 passes 13/13 primary checks at each timeframe. The static control fails 13/13 on each set, so the look
      is informative.
    - 15m C2 and 1H C0 miss the F2 materiality floor (their deltas are about half of it), so C1 stays carried.
    - The 90% MCS is reported, never used: 15m {C2}; 1H {C0} on F2 and {C0, C3} on F1. C1 lies outside it: the
      challengers are statistically, but not materially, better.
    - 4H was excluded, never read, and is unspent. The runner's 182 sealed opens equal the 28 committed 15m/1H
      files × 5 plus the 14 pairs × 3.
    - Evidence: r4/stage_b/look_evidence (read-only), with a 45-entry manifest 1e40020e…. The ledger shows F2 15m,
      F2 1H, F1 15m and F1 1H CONSUMED. The run record is r4/stage_c/b_run/B_RUN_RECORD.md.
R4_STAGE_C=Stage C (adjudication §6), mechanical, in .work/research3/r4/stage_c (gitignored). Nothing re-read
  F1/F2: every Stage-C script runs under an audit hook that refuses the sealed paths and the 28 snapshot copies.
  - C1: R4_DECISION_RECORD.json (sha256 7618fa40…41d3; .md 78c4827a…). It restates the code-decided result
    verbatim from the look's evidence copies (17 entries re-verified; the snapshot copies are never re-read), with the
    provenance chain and the 4H accounting. make_decision_record.py --verify rebuilds it byte for byte.
  - C2: STOP (C2_V2B_SUFFICIENCY.json 64d3f272…).
    - V2b's frozen machinery (run_v2a.calibrate, and the sigma_R,UB script regime_allowance.py) consumes
      row-level score differences with fold labels, and it defines F2 deployment effects as fold means of weekly
      block means.
    - The look persisted neither: its longest array is 282 weekly blocks, against 18,014-126,418 rows scored,
      and it holds no fold or grid key.
    - A mechanical V2b would therefore need raw F2. Under the owner's rule that means STOP; nothing was computed.
    - The frozen commitment already records "V2b is not run" (V2a's closure, §5.8-3).
    - C2 changes no Stage-B status.
  - C3, Codex (bounded, one delegation plus its one repair):
    - The decision is reproduced: 189 fields, 0 mismatches.
    - Block-t was re-derived from the persisted weekly block means: the series match exactly, the pairs within
      1.8e-15. The unit edges are equal.
    - 52 sign-flip tests (N = 100,000) with 0 threshold flips.
    - Report-only sensitivity: C1's weekly series have lag-1 autocorrelation up to +0.62 (15m F2). An AR(1)
      effective-n adjustment keeps every primary p at or below 1.6e-7 (15m) and 1.1e-5 (1H). The deployment sign
      tests are 25/25 and 7/7.
  - The independent Fable re-audit of C3 is pending. Pack: FABLE_STAGE_C_AUDIT_PACK.md (f104f25f…). Read-only
    verifier: verify_stage_c.py (21d4349a…), 12/12 PASS, STAGE_C_VERIFIED.
  - Manifest: STAGE_C.sha256, 24 entries, sha256 1d9cc5195bbac10b1322f9d95000150f56a6ea1b37ee3bf5add5984a0b4c8435.
    It includes the Codex task, result and log files. The T3 and T4 run records are in stage_c/b_run/.
R3=Research in .work/research3 (gitignored).
  - E0/G1: README.md and evidence.sha256. After the audit-required G1 repair, and the Wave-2 audit's D7 label
    fix, it holds 93 files. The pre-repair manifest (74 files) is kept as evidence_pre_g1_repair.sha256.
  - Wave 1: lanes/wave1/README.md, evidence_wave1.sha256 (235 files, chained, unchanged).
  - Wave 2: wave2/README.md, evidence_wave2.sha256 (chained).
  - R4: r4/README.md, evidence_r4.sha256 (68 entries, chained to all three earlier manifests, 0 mismatches).
  - E0 PASS, exact.
    - R2's code is archived byte-identical, without the sealed attestation, so sealed folds stay refused.
    - The store was rebuilt from the digest-verified R1 cache: 6 cells × 75 arrays, bit-identical.
    - The archived selftest passes.
    - DEV reference_dev + robust_{15m,1H,4H}: 53,088 numeric leaves, all exactly equal.
    - The v2 recipe CB DEV log loss is 1.04450516 / 1.03366655 / 0.91434692.
  - G1 done. The exclusion window was re-derived from the contract and admission.py:
    - the consumed outcomes are [2026-08-21T04Z, 2026-09-13T04Z);
    - the planned window is [2026-08-12, 2026-09-14T04Z], matching the plan;
    - with the G1 7-day embargo it becomes [2026-08-12, 2026-09-20T04Z].
    Dependence of d (CB vs prequential symmetric climatology; vs B3Dev):
    - BTC-ETH same-instant correlation is 0.23-0.64;
    - within a deployment, dependence clears in 2-3 days, with VR plateaus of about 2.0 (1H) and 1.5-2.2 (4H).
      The G1 repair withdrew the 15m plateau: its corrected VR keeps rising;
    - across deployments, 15m and 1H show regime long memory;
    - d has a weekly cycle;
    - the plan's literal W rule is unreliable.
    W = 7 days (whole UTC weeks) is a design choice, not derived (G1 repair); W = 14 is a sensitivity.
  - Power preview (not G3): 15m is powered at 6-12 weeks; 1H needs about 13-17; 4H at band 0.002 cannot be
    gated (Brier is marginally worse than climatology).
  - The deployed-heuristic comparator is not replayable offline (it needs order books).
  - Wave 1 COMPLETE. The package is lanes/wave1/WAVE1_REPORT.md; its tables are generated.
    - Audit: one read-only audit found 3 HIGH and 5 MEDIUM, all fixed. Every affected lane was rerun on
      the final code, and the bounded re-check found everything FIXED with nothing new at HIGH/MEDIUM. The
      audited version is kept in lanes/wave1/pre_audit/.
    - Candidate (a DEV-rule outcome, not a freeze):
      - 15m: symmetric;
      - 1H: symmetric + deseasonal inputs + Parkinson 1-bar term;
      - 4H: symmetric.
    - Cost of symmetry: none on 15m; it helps 4H; about 0.0006 (sub-floor) on 1H session-table models.
    - E11: Binance constants on OKX fail σ/triplet parity on 15m and 1H (4H passes), but skill transfers
      (15m edge −0.0458 on OKX vs −0.0455 on Binance). Recommendation: one serving venue per cell, with
      same-venue resolution.
    - E12: historical fail-closed downtime is 0.000% on both venues.
    - G1b: a roll28 reference is recommended for G2/G3.
    - G2 pilot: the iid rule false-passes 13-24% under P1a; nothing adopted.
    - 4H: CB's own reliability slope (1.37) blocks the adoption rule there.
    - S and I designs are ready for owner decisions.
  - Wave 2 COMPLETE. The package is wave2/WAVE2_REPORT.md; its tables are generated. Manifest:
    evidence_wave2.sha256 (chained; the entry count is in its own file).
    - Audit: one read-only audit found 0 HIGH, 12 MEDIUM and 12 LOW (wave2/AUDIT_FINDINGS_W2.md).
      - All were fixed in text, code or data. Only the affected steps were rerun: E8 with a diagnostic
        cumulative reference, a report-only N2 R sensitivity, the serving check, the F3 and G1 self-tests,
        and the renderers.
      - The bounded re-check found 22 FIXED and 2 PARTIAL, the latter due to three new MEDIUM statements the
        rewrite had introduced. Those three are corrected.
      - Pre-fix E8 and serving results are kept. Every earlier value is unchanged: 3,903 of 3,903 and 223 of
        223. No verdict changed.
    - Gate:
      - G1 repaired (audit D1–D11 PASS);
      - reference frozen (gate/REFERENCE_SPEC.json, digest b0af5872…);
      - G2 protocol frozen before any run (sha256 cbe6fa46…), with one logged erratum (E1, the N1
        criterion). E1 changed no number, but under the literal text the exclusion would read as a G2
        failure.
    - G2 size: the regime-allowance rules R5/R6 hold size on every timeframe at L ≤ 16 under N2 and N3. At
      15m L16 the F2 proxy shows 0.056–0.060, allowed only because N_eff 17 < 20.
    - G3 power: no timeframe meets the audit's acceptance at L ≤ 16, so 15m, 1H and 4H are EXCLUDED under the
      pre-registered consequence. PSG-2 cannot be pre-registered as scoped (audit E-4 not met). E-7 is met.
    - Options (report only): 15m with R4 at a 52-week holdout (size 0.031, power 0.91/0.72); nothing for 1H or
      4H.
    - Nearest miss: 15m R4 at L16. It fails only N2 at d = 0.20 (0.070–0.075; ≤ 0.047 at d ≤ 0.15) and
      method B / agreement. Method A alone accepts it.
    - 4H: no demonstrated Brier skill beyond a day-type base rate at the primary band, as the audit said. The
      frozen 28-day reference's noise is 64% / 65% / 32% of R3C's 4H edge.
    - N5 diagnostic: a no-skill base rate passes the window-conditional rule R2 in up to 15% (W7) or 19% (W14)
      of 16-week 4H windows.
    - R lane: R3C kept (a judgment between two pre-declared rules).
      - No single element passes the adoption rule: 4H calibration, E9 GARCH, E6 sub-bar RV, E8 pooling.
        E6's 4H bipower is blocked only by the slope rule. E10/E10b are closed with no signal.
      - R3C transfers to LTC/LINK/TRX/ETC/XLM: every fold beats the frozen reference. On 4H the transfer is
        marginal against a cumulative day-type reference.
      - Recompose v3 (the Wave-1 simplicity rule) keeps R3C, except a 1H BTC-factor pick at band 0.002
        (sub-floor, a 6e-5 tie-break). It reproduces Wave 1's 24 shared models exactly.
    - O lane:
      - R2's corpus is bit-identical to Binance spot klines;
      - the bounded-window R3C serving prototype: builder equality 9e-16 on exact inputs, bitwise symmetric,
        refuses bad windows. It MISSED the 1e-9 criterion set before the first run against R2's stored
        features (2.1e-9 on ETH 15m/4H); the cause is measured stored-feature rounding.
    - F3 tool prepared: labels only; it refuses before 2026-09-21T00:00Z and inside the exclusion window
      without a ruling.
    - Network: public Binance GETs only (5,108 requests). F1 is stored only; F2 was used only for the
      candidate-blind B3Dev null.
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
DATABASE=Supabase, PostgreSQL 17.6 (server_version_num 170006, read by the 0010 apply).
  - Migrations 0001-0007 were applied before this record.
  - 0009 was applied once, 2026-09-14 (run 34861816985).
  - 0008 was applied once, 2026-09-16 (run 35164080476).
  - 0010 was applied once, 2026-09-17 (run 35190794876), and VERIFIED.
    - The ten legacy tables keep RLS on, with no policy.
    - anon and authenticated now hold nothing on them or on their three serial sequences.
    - service_role keeps all eight table privileges and its sequence privileges.
    - The tables of 0005, 0006, 0008 and 0009 are unchanged.
  The older-table audit (run 35120616278, read-only) returned NOT_EXPOSED_THROUGH_AUDITED_PATHS:
  - the ten legacy tables have RLS on (not forced) and no policy;
  - anon and authenticated hold every table privilege, MAINTAIN included, yet are denied every row;
  - service_role has BYPASSRLS;
  - there is no PUBLIC grant, column grant, view, parent table or publication.
  Its findings, both addressed by migration 0010, now applied:
  - the migrations never enable RLS, so a rebuilt database would be open to the anon key;
  - RLS without a policy is the only barrier.
NEVER_RERUN=Consumed one-shot actions. None may run again:
  - §5A readiness runs 34863318042 (4b0a522) and 34873105124 (1d8f933).
  - The §5A ONE LOOK, consume run 34919367341 (1d8f933, population f83c31f7…). The durable seal refuses a second
    look.
  - The 0009 route: 34851608514 (refused before any DB contact) and 34861816985 (applied). Never dispatch it again.
  - The older-table audit 35120616278.
  - The 0010 apply 35190794876. The route refuses a second apply as "not a first apply"; never dispatch it again.
  - The 0008 apply 35164080476.
  - The PROD-SAFE-3 deploy: attempt 4, pushed at 03:39:17Z. Attempts 1-3 failed safely and changed nothing.
  - Its guard dispatch 35179229959.
  - R2 frontier research: the sealed look (folds 7-8) was consumed on 2026-09-04. Never re-run run_sealed.sh or
    edit docs/r2_evidence/SEALED_ATTESTATION.md.
  - Every T3 batch through PR #106, and the post-release batch T3 (PRs #107-#110).
  - The R4 freeze-4 publication T3 (PR #112).
  - The R4 Stage-B look: claim 95c339ef…, 2026-09-18T16:29Z. look.py --look refuses forever, because of the result,
    the run log and the ledger. Never run rehearse_b.py again: AUTHORIZATION.txt exists. Never delete or edit
    r4/stage_b/look_run/, look_evidence/, AUTHORIZATION.txt or r4/m0/LOOKS_CONSUMED.log. Never read the 28 snapshot
    copies again.
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
  - PRs #108 and #109 prepared everything that touches no evaluator-pinned file. It is still unwired.
  - Wiring needs §2.6 authorization.
  - Adopting the proper-score gate also needs per-row probabilities from persistence/repository.py, which is pinned.
  - Correction (lane C): with mu = 0, the up share is not 50/50. The shape tables fix it between 0.4794 and 0.5427.
BATCH_0010=MERGED as PR #107 (merge 2b7edf0b), then APPLIED ONCE on 2026-09-17 by the owner-authorized T4.
  The T4 is recorded below. Lane B had four commits:
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
  The PR-time rehearsal (.github/workflows/apply-migration-0010-rehearsal.yml) PASSED on its first run, run
  35187843344 on PostgreSQL 16.15, with no secret:
  - one apply, committed;
  - anon and authenticated left with nothing on the 10 tables and 3 sequences;
  - service_role unchanged, RLS on, no policy, and the later tables unchanged;
  - the second apply refused as not a first apply;
  - the database rebuilt from 0001-0010 alone asserted the posture.
  Evidence: .work/817/t3-batch/raw/rehearsal-35187843344/ (the report artifact and log, hashed).
  THE T4 (.work/818/t4-apply-0010/):
  - Pre-dispatch, 17 checks PASS:
    - main e22ce337 and hf 00705c55;
    - exact-main CI green;
    - the static scope proof: the migration is exactly bc2ec1dd, and the route is byte-identical to aaf11228;
    - the workflow active with no runs, and nothing queued;
    - the secret present (name only).
  - ONE dispatch at 06:39:24Z: run 35190794876, attempt 1. Every step succeeded, including the in-job
    rehearsal on PostgreSQL 16.15.
  - Raw capture before parsing: run JSON, log, both reports and raw.sha256.
  - verify_apply.py: VERIFIED, 88 checks, 0 failures.
    - Outcome APPLIED, committed. The executed bytes bc2ec1dd equal the reviewed file.
    - server_version_num 170006, with all eight privileges asked, MAINTAIN included.
    - Before: every table matched the audit. anon and authenticated held all eight; RLS on; no policy.
    - After: anon and authenticated hold nothing on the tables and sequences. RLS and policies are
      unchanged. service_role is unchanged (all eight; sequences unchanged).
    - The later tables are identical before and after.
    - The driver helpers equal the pinned fingerprints. The provenance is e22ce337, attempt 1, CPython
      3.13.14, isolated.
    - No database URL appears, except the rehearsal's local socket.
    - The verifier was mutation-tested beforehand; it caught all 13 injected failures.
  - After: main and hf unchanged; exactly one 0010 run; no other run since the dispatch.
BATCH_V2=MERGED as PR #108 (merge fe1f0c67) and PR #109 (merge 0f60edaf). Nothing is wired.
  Lane C had three commits: 9101bff2 (the prep), then 679e0801 and 5a3b5685 (the review fixes).
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
  C and D both extend the same guard, so D was stacked on C and merged after it.
BATCH_T3=CONSUMED and VERIFIED on 2026-09-17, 05:58Z-06:24Z, by .work/817/t3-batch/run-batch.sh (raw/ per lane;
  run.output). The merges, in order:
  - B PR #107: head aaf11228, merge 2b7edf0b, parents (08c77f09, aaf11228), tree 071556e3.
    Head checks: CI 35187843347 and rehearsal 35187843344. Main CI 35188066124.
  - C PR #108: head 5a3b5685, merge fe1f0c67, parents (2b7edf0b, 5a3b5685), tree 6bd22f37.
    Head CI 35188325807. Main CI 35188524324.
  - D PR #109: head 9c53e3cb, merge 0f60edaf, parents (fe1f0c67, 9c53e3cb), tree 906ccf9b.
    Head CI 35188753430. Main CI 35188996341.
  - A PR #110: head 6be3a535, merge e22ce337, parents (0f60edaf, 6be3a535), tree 2e1667b4.
    Head CI 35189258073. Main CI 35189507625.
  Every tree equals both the owner-authorized tree and merge-tree(previous main, head). Every file set equals
  the manifest. After the batch: no open PR, hf unchanged, and no workflow dispatched.
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
  - LOW (B), RESOLVED BY THE T4. The PostgreSQL 17 (MAINTAIN) branch ran on production (170006) and
    verified.
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
  - (Resolved by #111: oos-pair-evidence.yml and resolve-outcomes.yml are now on the Node-24 pins.)
  - Merged branches remain on origin, including release/prod-safe-1 to -3. Deleting any of them needs the owner.
  - As of 2026-08-22, per-timeframe calibration MEASURED needed about 3x more operator traffic (134-172 samples per
    timeframe, against a threshold of 500).
EVIDENCE=.work/ is gitignored and local.
  - 805-814: the §5A evaluator's verification and its T3/T4 runs.
  - 815: the one look.
  - 816: this release cycle (evidence.sha256): the l1-l3 prep, t3-audit, audit-dispatch, codex-818-820,
    t4-apply-0008, t3-release, t4-deploy and t3-merge-guard.
  - research3: R3 (see R3 and its README).
  - 818: the 0010 T4 (t4-apply-0010/: authorization, scope proof, predispatch, run_apply, raw, verify_apply;
    evidence.sha256).
  - 817: this batch.
    - t3-batch/ is the executed T3: authorization.txt, manifest, titles, bodies, run-batch.sh, run.output,
      raw/ per lane, raw/rehearsal-35187843344/, verify_batch.sh and verify_batch.output.
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
- **Database:** migration 0010 is applied (2026-09-17), so the legacy tables' security is now codified in the
  migrations.
- **Merged, not in production:** the unwired v2 prep (#108, #109).
- **Next, owner-gated:** the v2 decisions (a) to (d).
  A v2 promotion needs its own freeze, T0, holdout and one look.
