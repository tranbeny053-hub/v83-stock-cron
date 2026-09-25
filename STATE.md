# STATE

Updated: 2026-09-25. R4, the B lane, the NEXTGEN lane, D-1, NG-1 (closed) and lane H1 are published (main
83b099de, PR #122). H1 is COMPLETE, and the main checkout is now on main. **Lane H2 is done as a paper brief (v3,
after a bounded repair for the owner's review findings):** the live directional-skill gate counts near-duplicate and
overlapping outcomes as independent evidence. 1H and 4H passed it as of 2026-08-16 and are unread since. It now waits
at the methodology owner boundary (OWNER_BOUNDARY 2). 15m and 1H are
HISTORICALLY CONFIRMED with C1 carried, F3 is KEEP UNSPENT, and D-1 is CLOSED (not implemented). **NG-1 is CLOSED**
(owner ruling, 2026-09-25: close NG-1; W(b) is not run). Its record:
- Stage 0: DESIGN_OK. The kline family K is KILLED (valid for H ≤ 0.85).
- Stage 1, attempt 1: VOID at its dependency-pin guard, before any trade data was parsed.
- Stage 1, attempt 2: the owner-authorized single rerun of the reviewed repair (manifest 55c7794c…). It COMPLETED
  with **NOT_DEMONSTRATED**, and its pre-registered audit returned ACCEPT_WITH_FINDINGS (0 HIGH, 2 MEDIUM
  interpretive, 4 LOW). The governing wording is the audit's exact text: "On the admissible STRICT span (seen, mined
  data), NG-1 Stage 1 (attempt 2) returned NOT_DEMONSTRATED for the pre-declared trade-level T arm: the estimated
  reduction of C1's out-of-sample 15m log-variance forecast error was 0.9% (f̂ 0.0095, λ̂ 0.005), with one-sided
  98.75% bounds of −0.204 and 0.223 over H ∈ [0.50, 0.85], so a material reduction (≥ 19%, λ ≥ 0.10) is neither
  demonstrated nor excluded. Per pre-registration §8 the pilot stops with NG-1's free-data route not demonstrated,
  and the owner decides, including the kill-only option W(b)."
- Not concluded: that T is KILLED; any exclusion for a narrower H range; that the free-data route is closed;
  anything about depth or other trade constructions; profitability.
- The owner then closed NG-1. It ends with the free-data route not demonstrated and F3 unspent. Every NG-1 record
  and the 62 verified aggTrades ZIPs (10.06 GB) are kept read-only. The closure record is
  .work/research3/nextgen/ng1/NG1_CLOSURE.md.
No F3, collector or production path was touched. The product is unchanged and hf is unchanged at 00705c55. This
record is local; publishing it is a T3.

**Compacted on 2026-09-17.** The uncompacted record is `git show 2c6df51:STATE.md` (2,068 lines). It holds every
earlier LOOP_STATE, the full text of each boundary and ruling, the Codex verifications, the run records and the
production proofs. This branch merges 2c6df51, so that record stays reachable from main. Where the two differ, this
file governs.

## Recovery block — read this first on resume
```
LOOP_STATE=WAITING FOR THE OWNER at the H2 methodology boundary. The live skill-gate dependence brief is DONE
  (paper, read-only), and v3 governs: .work/h2_skill_gate/H2_SKILL_GATE_BRIEF.v3.md, with eight questions for the
  owner (OWNER_BOUNDARY 2). H1 is COMPLETE, and NG-1 is CLOSED. Nothing is pushed.
  - H2 bounded-repair authorization (owner, 2026-09-25; it arrived as pasted text in the owner's established form),
    verbatim: "CONTINUE CURRENT — Opus 5 XHIGH. H2 bounded repair only: preserve sealed v1/v2 and create an additive
    sealed `H2_SKILL_GATE_BRIEF.v3.md`, then update local STATE to match. Close every Fable finding explicitly:
    1. Remove the false decision-strength/HIGH coupling: production analysis uses constant `INSUFFICIENT_SAMPLE`;
    calibration sample status is diagnostics-only. Reframe Q4 as non-decision-bearing reporting consistency/T1.
    2. Replace inert “untagged legacy rows” Q7: origin is NOT NULL/default USER_REQUESTED since migration 0007.
    Frame the real issue as a created_at cutoff around cohort separation/backfill; add that count to Q5. Declare the
    known 2026-08-17 CONTROLLED_SMOKE canary mis-stamped USER_REQUESTED (BTC 1M), with no effect on 1H/4H.
    3. Replace all current-status claims with: 1H/4H passed as of 2026-08-16 and are unread since; Q5 would measure
    current state. Do not say they currently license candidates. 4. Reframe Q3: D-1 adopted R2 §2 only for
    zero-location path A and left live Change-A directional wording unchanged. A proper-score/null change for the
    live gate is a new owner ruling and changes population because TIMEOUT rows enter. 5. Rename H2 failure modes
    F1–F4 to M1–M4. 6. Add a separate owner question for interim product posture while correction is designed: keep
    current 1H/4H candidate licensing behavior vs a temporary T2 measure. 7. Relabel same-candle rows as
    near-duplicates/inferred dependence, not proven identical, because the band uses request-time fees + live
    spread. 8. Correct cache wording: TTL is 900s; after expiry the gate reads INSUFFICIENT_EVIDENCE until refresh
    completes. 9. State methodology_version remains unchanged by the correction; under D1 the sample floor counts
    distinct candles. Keep Q1/Q2/Q5/Q6 otherwise intact, refound Q3/Q4/Q7, and include the new interim-posture
    question. Do not query production/DB or alter code/tests/data. Seal v3 additively, mechanically audit each
    finding FIXED/NOT_FIXED, run verification only from a safe worktree, and report the new exact branch SHA. Do not
    push, implement, access consumed F1/F2/F3 raw evidence, or fold H4 into H2." CONSUMED:
    - Each finding's fact was first re-verified in code or record: the constant reliability status
      (quant/calibration_metrics.py:8-14); migration 0007's NOT NULL default; the canary (commit 9bc195e); D-1's
      path-A scope (D1_RULING.md:15-21); the band's live spread (execution_realism/realism.py:8-22); the cache
      (calibration/skill.py:76-98).
    - v3 is d5049ac94f5dab3988d7e9bc69fcc021045463e043c2f1030aebec34c0effdcf, sealed by H2_SKILL_GATE_BRIEF.v3.sha256
      c21d99ceb8999bd3db88887a8b4d95042ff1dec1a4ae50be11231ca4f34d8de9. v1 and v2 are kept unchanged and verify.
    - Mechanical audit of v3 §§1-6: findings 1-9 all FIXED; Q1/Q2/Q5/Q6 kept (Q5 adds the created_at count); H4 not
      folded in.
    - No code, test, data, production or database access.
  - H2 authorization (owner, 2026-09-25; it arrived as pasted text in the owner's established form), verbatim:
    "CONTINUE CURRENT — Opus 5 XHIGH. H2 AUTHORIZED, paper/read-only only. Audit the current live skill gate
    end-to-end against canonical STATE/contracts/implementation/tests: identify exactly where overlapping outcomes
    or repeated rows are treated as independent evidence, what claim/status that currently licenses, and whether the
    dependence structure can inflate confidence or prematurely satisfy the gate. Produce a bounded owner brief with
    the current estimand, evidence unit, overlap/dependence failure modes, affected timeframes/paths, and 2–3
    correction designs with trade-offs; preserve USER_REQUESTED vs SCHEDULED_SHADOW evidence classes and D-1
    wording. Do not change code/tests/data, access consumed F1/F2 raw evidence, run production analysis, or touch
    DB/serving/pinned/F3. Stop at the methodology owner boundary with the exact questions requiring ruling."
    CONSUMED:
    - Brief v2 is 0918f1484e968defb5e188719ea7b3d59f1cd59e392eba22e2507866f0c4ea69, sealed by
      H2_SKILL_GATE_BRIEF.v2.sha256 08c6a9e604760b80c1ed16005d30ec4be8a1eaf3c06211ad9abb8262f71596b0. v2 governed
      until v3 superseded it (above).
    - v1 (H2_SKILL_GATE_BRIEF.md c67ddb61…) is kept unchanged: it was sealed before one §3 research citation was
      corrected, because a parallel tool batch sealed the file while one edit failed. No finding changed.
    - No code, test, data, database, serving, pinned, F3 or F1/F2 raw evidence was touched, and no production
      analysis was run.
  - H1 step (c) authorization (owner, 2026-09-25) is CONSUMED. The main checkout was switched from
    chore/state-post-104 @ 2c6df51 to main and fast-forwarded to exactly 83b099de; no other git change or deletion.
    - Its working-tree STATE.md byte-equals origin/main's.
    - The NG-1 seals verify (STAGE1_CODE.sha256 38/39 by design), and so do the R4 seals: evidence_r4.sha256 67/68,
      the documented LOOKS_CONSUMED.log difference; STAGE_C.sha256 29/29.
    - U1/V2A results are unchanged and read-only.
  - The H1 STATE T3 (push only; #122 → main 83b099de) is CONSUMED and VERIFIED (LAST_GREEN_SHA).
  Earlier in this loop:
  - NG-1 was CLOSED by owner ruling (W(b) not run; F3 unspent), and the closure was recorded and verified.
  - Lane H1 was selected, and its local steps were done: the STATE cleanup, and the two R4 result files made
    read-only.
  - H1 authorization (owner, 2026-09-25; it arrived as pasted text in the owner's established form), verbatim:
    "CONTINUE CURRENT — Opus 5 HIGH. H1 AUTHORIZED, local-only. On `chore/state-post-121`, make only
    semantic-preserving STATE cleanup: correct stale/superseded pointers, mark moot items only where current
    authority proves closure, preserve all irreversibles/open decisions/recovery facts, state the F3 guard as
    procedural-only, and require `./verify.sh` from a safe worktree rather than the stale main checkout; do not
    inspect F3 again. Separately, verify the sealed digests of `.work/research3/r4/u1/U1_RESULTS.json` and
    `r4/v2a/V2A_RESULTS.json`, chmod exactly those files `0444`, then re-hash and prove they are non-writable
    without importing/running their producers. Run `./verify.sh` in the worktree, commit STATE.md only, and report
    the exact SHA plus before/after evidence-file digests. No push, main-checkout git action, scanner
    implementation change, deletion, NG-1/R4 reopening, F3, collector, DB, serving/pinned/wiring/freeze/deploy."
    CONSUMED:
    - STATE cleanup, semantic-preserving: pointers corrected; R3 §6 items 1, 3, 4 and 5 and W3-A/W3-E marked moot or
      answered, each citing its authority; the F3 guard stated as procedural-only; the verify-in-worktree,
      no-log-deletion and F3 rules added to STANDING_RULES. No compaction; nothing irreversible or open was removed.
    - chmod 0444 on exactly r4/u1/U1_RESULTS.json and r4/v2a/V2A_RESULTS.json. Digests before = after = sealed
      (evidence_r4.sha256): U1 0e69805c8dee8d789690dec16f29976c7a68185b5721bf3407c235e652c328b4, V2A
      da5d2a9ca5d8f5b7d1ca07065bf01f51f103cfecbda2f9a7d137e053e5f4d47d. Mode 644 became 444, and `test -w` is false for
      the owner (uid 501, not root). Both producers write through r4lib.write_json → Path.write_text (in place),
      which a read-only file blocks. Their folders stay writable, so a same-user unlink or rename is still possible.
      Neither producer was imported or run.
  - Disclosure (2026-09-25, during the selection audit): one read-only helper command by this loop listed the
    directory .work/research3/wave2/f3 by mistake. That breaks the standing "never open, list or hash wave2/f3"
    rule. The output was discarded unseen (piped into a failing `head -0`). Nothing inside was opened, read or hashed,
    and no market data was fetched or seen. F3 remains unspent.
  - NG-1 closure ruling (owner, 2026-09-25), verbatim: "Owner ruling: **CLOSE NG-1; do not run W(b)**. Preserve all
    sealed NG-1 records/data and keep F3 unspent; record the closure locally and verify. Then, paper-only, audit
    current canonical STATE/Git/.work and select the single highest-value safe UCPE lane remaining after NG-1,
    using dependency-aware parallel review where independent; do not reopen NG-1/R4, start new model research,
    collector, F3, DB, serving/pinned/wiring/freeze/deploy. Return the next exact owner/T2+ boundary and why it
    outranks alternatives."
  - The NG-1 Stage-1 result STATE T3 (push only; #121 → main 21b89c5a) is CONSUMED and VERIFIED (LAST_GREEN_SHA).
  - NG-1 Stage-1 rerun authorization (owner, 2026-09-25; it arrived as pasted text in the owner's established form),
    verbatim: "CONTINUE CURRENT — Opus 5 XHIGH. First verify `origin/main` is merge commit
    `563372f07bacf9879aa4e1891196122b7e1cb618` from PR #120 and that the main project checkout is still exactly at
    `2c6df51` with no git action. Then NG-1 STAGE 1 RERUN AUTHORIZED once (attempt 2) using exactly reviewed
    `STAGE1_CODE.attempt2.sha256` = `55c7794c516676980dc3f323b60ab86374943fc6e620dffdc51e2c895de8f825` and the same
    verified download (`FETCH_SUMMARY.json` `9d69aa97…`), no network. If a precondition refusal occurs (exit 2, no
    result written), report and stop; it does not consume the rerun. Otherwise run `--stage1` exactly once with the
    captured command in `STAGE1_REPAIR.attempt2.md`, seal result + raw capture, commission the preregistered
    read-only audit confirming the result cites `55c7794c…`, and stop. No download, F3, collector, DB,
    serving/pinned/wiring/freeze/deploy." It is CONSUMED: one run, 2026-09-25T10:12:41Z → 10:25:33Z, exit 0,
    preconditions 210/210, then the audit.
  - The repair STATE T3 (push only; #120 → main 563372f0) is CONSUMED and VERIFIED (LAST_GREEN_SHA).
  - NG-1 Stage-1 repair authorization (owner, 2026-09-25), verbatim: "CONTINUE CURRENT — Opus 5 XHIGH. First verify
    `origin/main` is merge commit `fe19792c164414024628ebae8abebf7908c80046`, then prepare the NG-1 Stage-1 repair
    only, once, under all nine binding conditions in `.work/research3/nextgen/ng1/pilot/STAGE1_AUDIT.md`: change
    only `ng1_stage1.py`; pin from the exact run build path; require loaded↔pinned equality both ways; re-pin the
    unchanged 36 plus exactly the two missed 4H caches or STOP; use attempt-suffixed outputs; run both synthetic
    suites + captured preflight; digest final code; commission one independent read-only repair-diff review;
    report the reviewed manifest digest and stop. No
    rerun/network/download/F3/collector/DB/serving/pinned/wiring/freeze/deploy." It is CONSUMED: one pin run
    (09:29:16Z; a wrapper error at 09:28:38Z started nothing), the tests, one preflight (PASS) and one review.
  - The NG-1 Stage-1 STATE T3 (#119 → main fe19792c) is CONSUMED and VERIFIED (LAST_GREEN_SHA). This loop pushed
    the branch; opening the PR was refused by the Claude Code auto-mode permission check, and #119 was opened and
    merged from the owner's account on GitHub.
  - NG-1 Stage-1 authorization (owner, 2026-09-25), verbatim: "NG-1 STAGE 1 AUTHORIZED once under the frozen
    STRICT preregistration. Before network access, pin+digest the two audited out-of-tree dependencies, add the
    required row-placement guard, and synthetic-test Binance Spot timestamp parsing on both sides of the
    2025-01-01 ms→µs boundary; then digest the exact final code. Only if every preflight passes, download exactly
    the preregistered BTC/ETH Spot trade data and official checksums for the strict window, verify every file, run
    Stage 1 once, seal raw capture/results, commission the preregistered read-only audit, and stop. No
    dataset/type/window substitution, F3, collector, DB, serving/pinned/wiring/freeze/deploy." It is CONSUMED: one
    fetch (2026-09-25T06:18:59Z → 06:28:01Z, exit 0) and one run (06:28:29Z → 06:28:39Z, exit 3, VOID).
  - The NG-1 Stage-0 STATE T3 (#118 → main 91232022) is CONSUMED and VERIFIED (LAST_GREEN_SHA).
  - NG-1 Stage-0 authorization (owner, 2026-09-23), verbatim: "NG-1 PILOT STAGE 0 AUTHORIZED once using the
    **STRICT** window under `NG1_PILOT_PREREG v2` (`NG1.sha256 a6af7eec…`, externally anchored by `origin/main
    d82ca2dc`). Digest the exact pilot code before execution; run Stage 0a once, then Stage 0b only if the frozen
    rule returns `DESIGN_OK`; preserve first causal failure and report `DESIGN_OK / UNDERPOWERED / VOID` plus any
    permitted kline verdict. No network/download, Option W, Stage 1, F3, collector, DB, pinned/wiring/freeze/deploy."
    It is CONSUMED (one run, 2026-09-23T17:01:00Z → 17:01:07Z, exit 0).
  - The NG-1 pre-registration STATE T3 (#117 → main d82ca2dc) is CONSUMED and VERIFIED (LAST_GREEN_SHA).
  - NG-1 ruling (owner, 2026-09-23), verbatim: "CONTINUE CURRENT — Opus 5 XHIGH. Owner ruling: **NG-1 GO,
    research-only/free-data-only**; no collector, production path, F3, or market-data download yet. First prepare
    and audit a paper-only admissibility map for historical Spot Trades/AggTrades excluding all consumed
    F1/F2/sealed evidence, plus a preregistered bounded falsification pilot with fixed materiality/kill gates; stop
    before any fetch/network action or new owner/T2+ boundary."
  - The D-1 / new-generation brief STATE T3 (#116 → main 18d0985e) is CONSUMED and VERIFIED (LAST_GREEN_SHA).
  - D-1 ruling (owner, 2026-09-23), verbatim: "Owner D-1 ruling: (1) adopt §2 template: one-sided α=.025,
    candidate-refusal cap, A-specific predeclared H range; (2) A evidence class = USER_REQUESTED only, never mixed
    with scheduled shadow; (3) use REPLACEMENT_SUPPORTED / _NOT_SUPPORTED / _PENDING / _UNINFORMATIVE and drop the
    bare “skill” reservation; (4) adopt R2 §2 in principle only with rule/reference replaced before wiring, and
    adopt §4 display via additive backend field; (5) hide H_extended from user display until validated; (6)
    accept the revised D-1 Done criterion with research statuses kept research-only." The same message continued:
    "Record/seal D-1 locally, verify, then prepare only a separate owner brief on opening a new generation +
    order-flow collection. No collector/network/storage/product implementation or T3/T4."
  - The NEXTGEN STATE T3 (#115 → main eabf0e94) is CONSUMED and VERIFIED (LAST_GREEN_SHA).
  - F3 ruling (owner, 2026-09-23), verbatim: "Owner ruling: **keep F3 unspent** for a future generation/stronger
    candidate; do not narrow H, do not open a non-confirmatory monitor, and do not issue ruling 3 or fetch F3."
    The same instruction continued paper-only: "map the stronger-candidate path and prepare D-1
    estimand/status/display wording needed for any later A path; parallelize independent paper work, audit once,
    and stop at the next true owner/T2+ boundary."
  - The B-lane closure STATE T3 (#114 → main 08cb148f) is CONSUMED and VERIFIED (LAST_GREEN_SHA).
  - D-5 ruling (owner, 2026-09-23), verbatim: "Owner ruling: **D-5 = B NOW, A LATER**. B is model-skill-only; A
    remains a separate future serving-fidelity/replacement-claim path. Proceed paper-only: H-explicit duration → fix
    look length → digest preregistration; if A may share B’s calendar period, digest A’s design/prereg before
    reading B. No ruling 3, F3 fetch, collector, DB/pinned/wiring/freeze/deploy is authorized."
  - B-lane closure instruction (owner, 2026-09-23): close the accepted milestone locally only; preserve the
    digested B-lane bytes; record Fable's four non-blocking findings in an additive correction record; carry the
    D-5 ruling, `B_LANE.sha256`, Fable's ACCEPT and the narrow conclusion into STATE; stop before any T3/push or
    new research/F3 action.
  - The R4 STATE publication T3 (#113) is CONSUMED and VERIFIED (LAST_GREEN_SHA).
  - Prepared for the owner, not a repo artifact: the GPT successor handoff package
    .work/gpt_successor_handoff_20260920 (v1.0.2, 11 files, manifest f2a109e9…). Its use is the owner's decision.
  - Stage-C closure ruling (owner, 2026-09-20), verbatim in r4/stage_c/c4/FABLE_C3_VERDICT.txt: the independent
    Fable C3 re-audit returned ACCEPT WITH FINDINGS; apply its six corrections exactly (the F2-15m long-memory
    caveat and range; no 1e-28-class evidence-strength claim; the thinnest robustness margin is F2 15m; C3 is 173
    computed plus 16 presence-only fields; the sign flip addresses non-normality, not serial dependence; the 1H-F2
    MCS exclusion is marginal); keep 15m and 1H HISTORICALLY CONFIRMED with C1 carried and 4H unread and unspent;
    build C4 from persisted evidence only; the collector stays OFF and the next lane is its pre-registration and
    dependency plan; remove the proven foreign housekeeping only if re-confirmed; stop before any push, collector,
    wiring, freeze or deploy.
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
CURRENT_MILESTONE=H2 PAPER BRIEF v3 COMPLETE (the live skill gate's dependence; the owner's review findings closed;
  methodology owner boundary). H1
  COMPLETE. NG-1 CLOSED (owner ruling, 2026-09-25): K KILLED (valid for H ≤ 0.85); T NOT_DEMONSTRATED; the free-data
  route not demonstrated; W(b) not run; F3 unspent. Still excluded:
  - any change to the live skill gate, its tests or its data before the owner's H2 rulings, then each change's own
    authorization (it is a hard gate, so treat it as T2), and any production read to measure it (H2 Q5);
  - any NG-1 run, fetch or W(b); reopening NG-1 or R4; any new model research;
  - ruling 3, any F3 fetch, and any collector (product evidence or research data);
  - a freeze, wiring, a new T0, any database action and any HF deploy;
  - any further F1/F2 read, and any implementation of the D-1 rulings without its own authorization
    (OWNER_BOUNDARY 5).
CURRENT_BRANCH=chore/state-post-122 (LOCAL, no upstream), from main 83b099de: this record, unpublished
  (OWNER_BOUNDARY). chore/state-post-121 (#122), -120 (#121), -119 (#120), -118 (#119), -117 (#118), -116 (#117),
  -115 (#116), -114 (#115), -113 (#114), -112 (#113) and -110 (#112) are merged and stay on origin; -110's push is
  the R4 commitment's timestamp.
  The main checkout (/Users/kha/Documents/Kha-app/UCPE) is on main at 83b099de (H1 step (c), 2026-09-25), clean,
  and its working-tree STATE.md is current as of that commit. Before that it was frozen on chore/state-post-104 at
  2c6df51 through the NG-1 Stage-1 rerun (repair review F3; audit L3). That branch is kept. STATE records are still
  made in separate worktrees, and ./verify.sh never runs in the main checkout (STANDING_RULES).
  The batch branches are merged, and remain on origin:
  - prep/0010-legacy-table-security;
  - prep/v2-integration-prep;
  - prep/v2-history-serving;
  - chore/state-post-106.
LAST_GREEN_SHA=83b099de (main, PR #122: the NG-1 closure, H1 selection and H1 cleanup STATE record, STATE.md only).
  - This loop pushed chore/state-post-121 at 79acf1e5 under the owner's push-only T3; the merge tree 7606c5b0 was
    recorded before the push. #122 was opened and merged from the owner's account on GitHub (2026-09-25T15:39:47Z).
  - Verified by this loop: parents (21b89c5a, 79acf1e5); tree 7606c5b0 equals the recorded tree; STATE.md blob
    02d22e2e; the only change is STATE.md (three commits: f283738f, c6170032, 79acf1e5).
  - The exact-head check `test` passed at 15:25:52Z and the exact-main check `test` at 15:42:34Z (2026-09-25).
  - This publication is the external timestamp of the NG-1 closure record and of lane H1's selection and cleanup.
  Before it: 21b89c5a (PR #121: the NG-1 Stage-1 attempt-2 result and audit STATE record, STATE.md only).
  - This loop pushed chore/state-post-120 at ea4d5b33 under the owner's push-only T3; the merge tree a36b096b was
    recorded before the push. #121 was opened and merged from the owner's account on GitHub (2026-09-25T14:02:38Z).
  - Verified by this loop: parents (563372f0, ea4d5b33); tree a36b096b equals the recorded tree; STATE.md blob
    5461be13; the only change is STATE.md (two commits: 0a5600cf, then the §9 wording fixes ea4d5b33).
  - The exact-head check `test` passed at 14:00:35Z and the exact-main check `test` at 14:05:58Z (2026-09-25).
  - This publication is the external timestamp of the attempt-2 result, seal and audit digests.
  Before it: 563372f0 (PR #120: the NG-1 Stage-1 repair STATE record, STATE.md only).
  - This loop pushed chore/state-post-119 at a880ebff under the owner's push-only T3; tree f9467c52 was recorded
    before the push. #120 was opened and merged from the owner's account on GitHub (2026-09-25T10:05:31Z).
  - Verified by this loop: parents (fe19792c, a880ebff); tree f9467c52 equals the recorded tree; STATE.md blob
    ce70158b; the only change is STATE.md.
  - The exact-head check `test` passed at 10:04:55Z and the exact-main check `test` at 10:07:57Z (2026-09-25).
  - This publication is the repair's external timestamp: manifest 55c7794c…, pins and prep seal (the review by
    digest prefix only). It preceded the rerun (10:12:41Z).
  Before it: fe19792c (PR #119: the NG-1 Stage-1 VOID and audit STATE record, STATE.md only).
  - This loop pushed chore/state-post-118 at 6118883c under the owner's T3 (tree f32c70c7 recorded before the
    push). Opening the PR was refused by the Claude Code auto-mode permission check ("Out-of-Place Publication");
    #119 was opened and merged from the owner's account on GitHub (2026-09-25T09:14:10Z).
  - Verified by this loop: parents (91232022, 6118883c); tree f32c70c7 equals the recorded tree; STATE.md blob
    036fd6f8; the only change is STATE.md.
  - The exact-head check `test` passed at 08:54:22Z and the exact-main check `test` at 09:17:02Z (2026-09-25).
  - This publication is the external timestamp of the attempt-1 Stage-1 code, pin, result and audit digests.
  Before it: 91232022 (PR #118: the NG-1 pilot Stage-0 STATE record, STATE.md only).
  - Merged 2026-09-25 by this loop under the owner's T3, with --match-head-commit 52d51fd0.
  - Parents (d82ca2dc, 52d51fd0); tree 8a7afcd2, recorded before the push and matched after; STATE.md blob 4bfe9ba1.
  - The exact-head check `test` passed at 05:46:45Z and the exact-main check `test` at 05:50:37Z (2026-09-25).
  - This publication is the external timestamp of the Stage-0 code and result digests (Stage-0 audit LOW 3).
  Before it: d82ca2dc (PR #117: the NG-1 opening and pilot pre-registration STATE record, STATE.md only).
  - Merged 2026-09-23 by this loop under the owner's T3, with --match-head-commit 6f9f1b25.
  - Parents (18d0985e, 6f9f1b25); tree 6bc53f54, recorded before the push and matched after; STATE.md blob c8ceda7a.
  - The exact-head check `test` passed at 16:33:15Z and the exact-main check `test` at 16:37:23Z (2026-09-23).
  - This publication is the NG-1 pre-registration's external timestamp (NG1.sha256 a6af7eec…).
  Before it: 18d0985e (PR #116: the D-1 closure, new-generation brief and archive-note STATE record,
  STATE.md only).
  - Merged 2026-09-23 by this loop under the owner's T3, with --match-head-commit a7407f5a.
  - The first push was refused by GitHub (HTTP 500) and published nothing. After every precondition was re-checked,
    one identical push succeeded.
  - Parents (eabf0e94, a7407f5a); tree abe678d3, recorded before the push and matched after; STATE.md blob 9efa8e43.
  - The exact-head check `test` passed at 14:48:39Z and the exact-main check `test` at 14:52:43Z (2026-09-23).
  Before it: eabf0e94 (PR #115: the NEXTGEN STATE record, STATE.md only).
  - Merged 2026-09-23 by this loop under the owner's T3, with --match-head-commit 7ceafdeb.
  - Parents (08cb148f, 7ceafdeb); tree 30a7b313, recorded before the push and matched after; STATE.md blob 66ab63c4.
  - The exact-head check `test` passed at 13:31:40Z and the exact-main check `test` at 13:34:59Z (2026-09-23).
  Before it: 08cb148f (PR #114: the B-lane closure STATE record, STATE.md only).
  - Merged 2026-09-23 by this loop under the owner's T3, with --match-head-commit f7d87f94.
  - Parents (075133cc, f7d87f94); tree 596d740a, recorded before the push and matched after; STATE.md blob a1bb5e39.
  - The exact-head check `test` passed at 09:25:36Z and the exact-main check `test` at 09:29:00Z (2026-09-23).
  - The publication gives the B lane's pre-result freeze its external anchor (Fable finding 1).
  Before it: 075133cc (PR #113: the R4 closure STATE record, STATE.md only).
  - Merged 2026-09-20T08:19:05Z by this loop under the owner's T3, with --match-head-commit bc27ef6c.
  - Parents (9bb2cde, bc27ef6c); tree 87b6e2fa, recorded before the push and matched after; STATE.md blob ef6d9e78.
  - The exact-head check `test` passed at 08:18:44Z and the exact-main check `test` at 08:22:31Z (2026-09-20);
    re-verified 2026-09-21, with scheduled ping/verify/resolve green on the same commit.
  Before it: 9bb2cde (PR #112: the R4 freeze-4 publication, STATE.md only).
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
LAST_VERIFY=PASS ruff ok | 2450 passed | schemas+smoke ok | scanners 3/3 · 2026-09-25 (local).
  - Run for this H2 record on chore/state-post-122 (main 83b099de plus this STATE.md change; T0), in its worktree.
  - H2's own checks, read-only: H2_SKILL_GATE_BRIEF.v3.sha256 1/1, v2 1/1 and v1 1/1.
  - Re-run after the H2 v3 repair, on the same branch, in its worktree: the same result.
  - Earlier, for the NG-1 closure record on chore/state-post-121 (main 21b89c5a plus that change; T0).
  - Re-run after the lane-selection commit and again after the H1 cleanup, on the same branch, in its worktree:
    the same result each time.
  - The closure's own checks, local and read-only:
    - NG1_CLOSURE.sha256 1/1;
    - every NG-1 seal listed in NG1_CLOSURE.md verifies (STAGE1_CODE.sha256 38/39 by design; all others
      complete);
    - data/ is read-only, with 127 files and FETCH_SUMMARY.json 9d69aa97…;
    - no file under nextgen/ng1/ is writable.
  - Earlier, for the NG-1 Stage-1 result record on chore/state-post-120 (main 563372f0 plus that change; T0).
  - Re-run after the §9 wording re-check's fixes, on the same branch: the same result.
  - The run's own checks, local and read-only:
    - attempt 2: STAGE1_RESULTS.attempt2.sha256 11/11, STAGE1_AUDIT.attempt2.sha256 1/1,
      STAGE1_CODE.attempt2.sha256 40/40, STAGE1_PREP.attempt2.sha256 22/22 and
      STAGE1_REPAIR_REVIEW.attempt2.sha256 1/1 OK;
    - attempt 1: STAGE1_RESULTS.sha256 16/16 and STAGE1_AUDIT.sha256 1/1 OK.
  - Earlier, for the NG-1 Stage-1 repair record on chore/state-post-119 (main fe19792c plus that change; T0).
  - The repair's own checks, local and read-only: STAGE1_CODE.attempt2.sha256 40/40, STAGE1_PREP.attempt2.sha256
    22/22 and STAGE1_REPAIR_REVIEW.attempt2.sha256 1/1 OK; attempt 1's STAGE1_RESULTS.sha256 16/16 and
    STAGE1_AUDIT.sha256 1/1 OK; the 38 pinned files unchanged after this verification; the main checkout still at
    2c6df51 with src/ clean.
  - Earlier, for the NG-1 Stage-1 record on chore/state-post-118 (main 91232022 plus that STATE.md change; T0).
  - Stage 1's own checks, local and read-only: STAGE1_CODE.sha256 39/39, STAGE1_RESULTS.sha256 16/16 and
    STAGE1_AUDIT.sha256 1/1 OK; the 36 pinned files unchanged; the synthetic tests pass 37/37 (Stage 1) and 51/51
    (Stage 0); PILOT_CODE.sha256 37/37, PILOT_RESULTS.sha256 8/8, STAGE0_AUDIT.sha256 1/1 and NG1.sha256 4/4 OK.
  - Earlier, for the NG-1 Stage-0 record on chore/state-post-117 (main d82ca2dc plus that STATE.md change; T0).
  - Stage 0's own checks, local and read-only: PILOT_CODE.sha256 37/37, PILOT_RESULTS.sha256 8/8,
    STAGE0_AUDIT.sha256 1/1 and NG1.sha256 4/4 OK. The pilot's synthetic tests pass 51/51. U1_RESULTS.json still
    matches evidence_r4.sha256, and DEV_INPUTS.json still matches B_LANE.sha256.
  - Earlier, for the NG-1 record on chore/state-post-116 (main 18d0985e plus that STATE.md change; T0).
  - NG-1's own checks, local and read-only: NG1.sha256 4/4 OK; CLOSURE_CHECK=PASS (81 checks); NEXTGEN.sha256 7/7,
    NEXTGEN_ADDENDUM.sha256 2/2, ARCHIVE_NOTE.sha256 1/1 and B_LANE.sha256 6/6 still OK; r4/u1/U1_RESULTS.json
    still matches evidence_r4.sha256.
  - Earlier, for the D-1 closure record on chore/state-post-115 (main eabf0e94 plus that STATE.md change; T0).
  - Local checks: NEXTGEN.sha256 7/7 and NEXTGEN_ADDENDUM.sha256 2/2 OK; the D-1 draft is unchanged.
  - Re-run after the archive note: ARCHIVE_NOTE.sha256 1/1 OK; the NEXTGEN manifests are unchanged.
  - Run for this NEXTGEN record on chore/state-post-114 (main 08cb148f plus this STATE.md change; T0).
  - NEXTGEN's own checks, local and read-only:
    - NEXTGEN.sha256 7/7 OK;
    - the audit's 16 findings mechanically closed (CLOSURE_CHECK=PASS);
    - B_LANE.sha256 still 6/6 OK;
    - no other lane, record or ledger changed.
  - Earlier, for the B-lane closure record on chore/state-post-113 (main 075133cc plus that change; T0).
  - The B lane's own checks, local and read-only: B_LANE.sha256 6/6 OK; B_LANE_ADDENDUM.sha256 1/1 OK; the plan
    digest matches both scripts; the three write-once outputs are unchanged and read-only.
  - Run for this R4 Stage-C record on chore/state-post-112, i.e. main 9bb2cde plus this change. R4 lives in
    gitignored .work/, so the change is STATE.md alone (T0). 2450 = the earlier 2445 + the 5 tests of #111's
    workflow test file, now on main.
  - Re-run after the C4 closure, on the same branch: the same result (2450 passed, scanners 3/3), 2026-09-20.
  - Stage C's own checks: verify_stage_c.py 16/16 (STAGE_C_VERIFIED). Since the look, nothing outside r4/stage_c
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
  - The GPT successor handoff package used one read-only Codex verification (task-824; 9 of 10 checks passed and
    the tenth was BLOCKED by the sandbox's lack of DNS, compensated by live reads). The B lane used no Codex.
  - The NEXTGEN lane used one bounded read-only Codex inventory (task-825, DONE). It read product wording only
    through git at origin/main, because the working tree is stale, and wrote one file. It then had one read-only
    Claude audit (ACCEPT_WITH_FINDINGS; all 16 findings closed).
  - The NG-1 lane used no Codex. It had one read-only Claude audit (REJECT: 1 HIGH, 4 MEDIUM, 4 LOW), one bounded
    repair, a mechanical closure check and one bounded re-check by the same auditor (RECHECK: PASS; its seven new
    LOW items were fixed before sealing and verified mechanically).
  - NG-1 pilot Stage 0 used no Codex. Claude wrote the pilot, and it was tested on synthetic data (51/51) and
    digested before the one run. One independent read-only Claude audit of the result followed (ACCEPT_WITH_FINDINGS:
    0 HIGH, 2 MEDIUM wording, 6 LOW), then one bounded re-check of this record's wording.
  - NG-1 pilot Stage 1 used no Codex. Claude wrote the Stage-1 code; it was tested on synthetic data (37/37,
    including the 2025-01-01 ms→µs boundary) and digested before the fetch and the one run. One independent
    read-only Claude audit of the VOID followed (ACCEPT_WITH_FINDINGS: 0 HIGH, 1 MEDIUM, 6 LOW).
  - The Stage-1 repair (attempt 2) used no Codex. Claude wrote it; one independent read-only Claude review of the
    repair diff followed (ACCEPT_WITH_FINDINGS: 0 HIGH, 0 MEDIUM, 6 LOW).
  - The Stage-1 rerun used no Codex. One pre-registered independent read-only Claude audit of its result followed
    (ACCEPT_WITH_FINDINGS: 0 HIGH, 2 MEDIUM interpretive, 4 LOW). It recomputed every statistic with a largest
    difference of 0.0.
  The previous change closed at 3 of its 4 delegations (task-818 to 820; .work/816/codex-818-820/).
GPT_REQUEST_ID=NONE
GPT_THREAD_URL=NONE
GPT_REQUEST_STATE=NONE
OWNER_BOUNDARY=NO ACTION IS AUTHORIZED. Consumed since the previous record: the H1 STATE T3 (#122), the H1 step (c)
  authorization, and the H2 paper authorization (LOOP_STATE). What remains, in order:
  1. T3 (owner authorizes): publish this record (chore/state-post-122, STATE.md only). It also timestamps the H2
     brief's digest externally.
  2. CURRENT LANE, H2: the METHODOLOGY OWNER BOUNDARY for the live directional-skill gate. Brief:
     .work/h2_skill_gate/H2_SKILL_GATE_BRIEF.v3.md (d5049ac9…; it supersedes v2 0918f148… and v1 c67ddb61…, both
     kept). Its findings:
     - The gate counts every USER_REQUESTED resolved row (all symbols pooled) as an independent trial.
       - The test is z = (2h − n)/√n ≥ 1.96 with n ≥ 100, against a 50% coin.
       - Sources: calibration/skill.py:43-58; calibration/service.py:112-131; the repository's calibration query
         has no DISTINCT; the ledger's only key is prediction_id.
       - Origin has been NOT NULL DEFAULT 'USER_REQUESTED' since migration 0007, so the query's coalesce is inert.
       - The cache TTL is 900 s. After expiry, the gate reads INSUFFICIENT_EVIDENCE until a refresh completes.
     - Its dependence mechanisms:
       - M1: same-candle near-duplicates. They share one window and price path, but the band uses request-time fees
         and the live spread, so they are not proven identical; the dependence is inferred.
       - M2: overlapping 6-bar windows. M3: cross-symbol pooling. M4: regime runs.
       - Research measured a design effect of 1.4–4.1 (.work/research3/g1/G1_REPORT.md:99).
     - A pass lifts the SKILL_NOT_DEMONSTRATED hard block and licenses LONG/SHORT_CANDIDATE ("for planning only").
       1H (z 2.85) and 4H (z 4.31) passed as of 2026-08-16 (V1_QUANT_CONTRACT.md:18-26, 107-108) and are unread
       since; Q5 would measure the current state.
       - On those numbers, 1H's pass would not survive a design effect above 2.12, and 4H's above 4.84.
       - Against the contract's majority-direction baselines, neither passed even as independent rows (z ≈ 0.68 and
         1.18).
     - Decision strength never reaches HIGH in production: analysis uses the constant reliability status
       INSUFFICIENT_SAMPLE, and the calibration sample status is diagnostics-only.
     - The one known mis-stamped row is the 2026-08-17 CONTROLLED_SMOKE canary, recorded as USER_REQUESTED (BTC 1M,
       run_0294f782…; commit 9bc195e). It has no effect on 1H or 4H.
     - Correction designs:
       - D1: one row per candle; the sample floor then counts distinct candles;
       - D2: one row per non-overlapping window;
       - D3: a window-mean block test, the §5A A1 pattern; recommended.
       Each keeps USER_REQUESTED-only counting, the D-1/Change-A wording and methodology_version unchanged, and fits
       the unpinned calibration/service.py and skill.py. It changes a hard gate, so treat it as T2, with no deploy
       without its own authorization.
     Questions for the owner's ruling:
     - Q1 — the evidence unit: one row per candle? Recommended: yes.
     - Q2 — D1, D2 or D3, and for D3 the windows and their minimum count? Recommended: D3.
     - Q3 — reference and scoring. This is a new ruling, outside D-1: D-1 adopted R2 §2 only for zero-location path A
       and left the live Change-A directional wording unchanged. Keep the 50% directional null, or change it for the
       live gate? A proper score would change the population, because TIMEOUT rows enter.
     - Q4 — reporting consistency (non-decision-bearing, T1): should the diagnostic calibration report use the same
       unit?
     - Q5 — a read-only aggregate production query of counts (its own database authorization) before any change,
       and acceptance of the product change if 1H or 4H flips? It would count, per timeframe: n, h, distinct candles,
       and rows created before migration 0007's cohort separation.
     - Q6 — may the display wording "resolved outcomes" change to name the unit, given D-1 keeps Change-A wording?
     - Q7 — cohort cutoff: exclude rows created before a created_at cutoff at cohort separation or backfill (0007)?
       Q5 counts them first.
     - Q8 — interim product posture while the correction is designed: keep the current behaviour (the gate may
       license 1H/4H candidates if it still passes), or a temporary T2 measure?
  2-H1. H1, resumability and evidence-integrity hardening: COMPLETE 2026-09-25. Its steps: (a) and (d) as below;
     (b) #122 → main 83b099de; (c) the main checkout on main @ 83b099de. It was selected paper-only on 2026-09-25 at the
     owner's direction, after three parallel read-only reviews (the STATE decisions; Git, CI and production health;
     the .work lanes). Its steps:
     (a) T0 on chore/state-post-121, semantic-preserving STATE cleanup: DONE, owner-authorized, in this record.
         The proposed compaction was not done, because the owner limited H1 to semantic-preserving cleanup;
     (b) T3: push that exact commit, then the owner opens and merges the PR. NEXT: item 1;
     (c) after the merge, fast-forward the main checkout (/Users/kha/Documents/Kha-app/UCPE) from 2c6df51 to main.
         This is local and reversible, makes its working-tree STATE.md current, and needs its own authorization;
     (d) chmod 0444 on r4/u1/U1_RESULTS.json and r4/v2a/V2A_RESULTS.json: DONE, owner-authorized (digests
         unchanged; LOOP_STATE).
     Not in H1: any scanner change (narrowing needs its own owner decision), the resolver, runtime dependencies,
     workflows, product code, the database or any deploy.
     Why H1 outranks the alternatives (doctrine: safe learning, "leave it resumable"; evidence, not argument):
     - Its hazards fire on a fresh session's most routine steps:
       - the working-tree STATE.md is the 2c6df51 record from 09-17, 58 commits behind main, with no NG-1, 0010
         apply or run_u1/run_v2a import warnings;
       - ./verify.sh in the main checkout runs check_no_secrets.py over ROOT.rglob("*"), and .work is not in
         SKIP_DIRS. It would read every sealed path and the 10 GB of NG-1 data;
       - OPEN_ITEMS told readers to "delete stale .work/*.log files", yet codex-822/823.log are digested in
         r4/stage_c/STAGE_C.sha256 (codex-822.log is C3's preserved first failure) and codex-825.log in
         nextgen/NEXTGEN.sha256. Corrected in place below;
       - U1_RESULTS.json and V2A_RESULTS.json are writable (0644), and their scripts rewrite them on import;
       - F3's tool date guard lapsed on 2026-09-21. Once the first F3 week completes (2026-09-28T02:00Z), only the
         written rule protects F3.
     - Cost: $0, no product risk, every step reversible, one owner message.
     - The alternatives rank lower now:
       - H2, a paper brief on dependence in the live directional-skill gate: the most product-relevant, but latent.
         The gate needs n ≥ 100 per timeframe; sampled resolver logs show outcomes accruing only a few per day; the
         fix is serving or pinned work, excluded now. It is next after H1.
         CORRECTED 2026-09-25 by the H2 audit: "latent" was wrong. On the contract's 2026-08-16 cohort, 1H
         (142 directional rows, z 2.85) and 4H (151, z 4.31) had already passed the gate as of 2026-08-16
         (V1_QUANT_CONTRACT.md:18-26, 107-108). They are unread since; H2's Q5 would measure the current state;
       - H3, verify.sh speed to the doctrine's 30 s (now about 110–180 s, almost all pytest): loop cost only;
       - H4, recording the resolver's 50-bar coupling and the unpinned runtime dependencies as known hazards
         (their fixes touch the database writer or serving);
       - low value: the H_extended scope ruling (it shows only in raw JSON and the download); the C4 "25 to about
         76" addendum (5 passages in 3 write-once files); merged-branch deletion (T3); R3 §6 bookkeeping; the GPT
         package's disposition; CLAUDE.md's Codex delegation against the owner's Claude-implements directive.
  3. NG-1: CLOSED by the owner, 2026-09-25. W(b) is not run, and option W closes with NG-1.
  4. F3: RULED 2026-09-23 — KEEP UNSPENT for a future generation or a stronger candidate. Narrowing H and a
     non-confirmatory monitor are declined by that ruling. Ruling 3 is not issued and no F3 fetch is authorized.
     Spending F3 later requires a candidate that clears the entry bar (NEXTGEN, STRONGER_CANDIDATE_PATH §1) inside a
     newly opened generation.
     - The F3 tool's date guard expired on 2026-09-21, so only this written rule now stops a run.
     - See LOOP_STATE for the 2026-09-25 disclosure: an accidental listing of wave2/f3; nothing was read.
  5. D-1: CLOSED, owner-ruled 2026-09-23. nextgen/D1_RULING.md governs; the draft is kept as digested. Fixed for
     path A:
     - the §2 template: one-sided α 0.025, a candidate-refusal cap, and an A-specific H range declared before any
       collection;
     - the evidence class: USER_REQUESTED only;
     - the verdicts REPLACEMENT_SUPPORTED / _NOT_SUPPORTED / _PENDING / _UNINFORMATIVE, with no new bare "skill"
       and Change-A wording untouched;
     - R2 §2 in principle only, with its rule and reference replaced before any wiring;
     - R2 §4's display through an additive backend field;
     - H_extended hidden from user display until validated (the API field stays);
     - research statuses kept research-only.
     Implementing any of it is future T1/T2 work, each needing its own authorization. Path A still needs D-2, D-3,
     D-4, D-6 (§2.6), D-7 (T4), collector activation, an H-explicit analysis on the serving lattice at the
     USER_REQUESTED arrival rate, and Stage D. The standing rule stays: if A may use B's calendar period, A's design
     and preregistration are digested before any B look is read.
  6. New generation: NG-1 RULED GO 2026-09-23 (research-only, free-data-only; no collector, production path, F3
     or download yet; the only download since is Stage 1's, separately authorized).
     NG-1 is CLOSED (owner, 2026-09-25): K KILLED (valid for H ≤ 0.85), T NOT_DEMONSTRATED, W(b) not run. NG-2 and
     NG-3, the collector routes, were not chosen. The archive question is RESOLVED
     (nextgen/ARCHIVE_VERIFICATION_NOTE.md): spot trades and aggTrades are archived, and no depth archive is listed.
     A research data collector and path A's evidence collector are both OFF. Implied volatility stays barred by
     invariant 5.
  7. The collector stays OFF (owner, 2026-09-20); activation remains the owner's call.
  8. Additive reconciliation of the superseded "25 to about 76" wording in the write-once C4 record: open, not
     authorized. Its only admissible form is a separately digested addendum. R4_STAGE_C below carries a notice.
  9. Standing: gate research is CLOSED for this generation (V2a). F1/F2 at 15m and 1H are spent forever, and 4H is
     unspent. No freeze, wiring or deploy follows from R4 or the B lane without Stage D (§6, §9).
  R3 decisions requested in
  .work/research3/wave2/WAVE2_REPORT.md §6:
  1. gate scope after the G3 exclusion (MOOT for this generation: gate research is CLOSED by V2a, OWNER_BOUNDARY 9):
     (a) research only, recommended;
     (b) a 15m long-holdout design (R4, L up to 52 weeks), which changes the L_max ruling and needs a
         re-audit. 15m R4 at L16 was the nearest miss: it failed only N2's d = 0.20 case and method B /
         agreement;
     (c) a window-conditional estimand, not recommended;
     (d) research toward a stronger candidate;
  2. 4H: no demonstrated Brier skill beyond a day-type base rate at the primary band, a product question. The
     kept slope rule also blocks every 4H element that leaves R3C's miscalibration in place. STILL OPEN;
  3. F3: (a) weekly public-kline accumulation from 2026-09-28T02:00Z (labels only); (b) exclusion-window klines
     as inputs for the first F3 week. ANSWERED by the F3 ruling of 2026-09-23 (KEEP UNSPENT, OWNER_BOUNDARY 4):
     neither (a) nor (b) is authorized;
  4. the 1H BTC factor: keep R3C (recommended; the Wave-2 adoption rule), or take recompose v3's primary-band
     pick (the Wave-1 simplicity rule; sub-floor, a 6e-5 tie-break, one band only, and ETH would need BTC
     klines). MOOT: R4 carried C1, the plain symmetric CB, not R3C, at 15m and 1H (c4/R4_CLOSURE_RECORD.json
     "carried"; the owner's Stage-C closure ruling of 2026-09-20);
  5. the estimand sentence and the gating comparator (moot until item 1 opens a gate path). MOOT for this
     generation (item 1);
  6. from Wave 1 (Lane S): H_extended, zero-location dispositions, additive fields and display — RULED by D-1
     (2026-09-23; nextgen/D1_RULING.md). Implementation pending authorization.
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
    (a) the proper-score gate for zero-location methodologies (R2 doc §2): RULED IN PRINCIPLE by D-1 (2026-09-23)
        — adopt the principle only; the rule and reference are replaced before any wiring and the dependence
        decision is taken. Implementation is not authorized;
    (b) the directional display (R2 doc §4): RULED by D-1 (2026-09-23) — P(move beyond ±band) against P(timeout),
        "no directional claim", through an additive backend field. Implementation is not authorized;
    (c) §2.6 authorization to wire v2. quant/pipeline.py and config/defaults.py are evaluator-pinned;
    (d) freeze sequencing and a new pre-registered holdout.
  - T3: publish this STATE record.
  - T3: delete merged branches: release/prod-safe-3 and the four batch branches.
  - The OPEN_ITEMS decisions.
NEXT_ACTION=WAIT for the owner (OWNER_BOUNDARY 1-2: the T3 for this record; the H2 rulings Q1–Q7). Never run
  ./verify.sh in the main checkout: its secret scanner walks .work, sealed paths included. Verify only in a clean
  worktree. Read first:
  - .work/h2_skill_gate/H2_SKILL_GATE_BRIEF.v3.md: the H2 brief (it governs; v2 and v1 are superseded, kept
    unchanged);
  - .work/research3/nextgen/ng1/NG1_CLOSURE.md: the closure, the preserved records and the governing wording;
  - pilot/STAGE1_AUDIT.attempt2.md and STAGE0_AUDIT.md (the governing Stage-1 and Stage-0 wording).
  The B lane's record is b_lane/B_LANE_CLOSURE_ADDENDUM.md.
  - Never run ng1_stage1.py --stage1 again: attempt 2's result is final, and the run refuses once
    STAGE1_RESULT.attempt2.json exists.
  - Never edit attempt 1's files or any attempt-2 file. Never run --pin-deps again: it refuses once
    STAGE1_DEPS.attempt2.json exists.
  - Never run fetch_stage1.py again: the download is consumed, verified and read-only.
  - Never run ng1_pilot.py --stage0 again: it refuses once STAGE0A_RESULT.json exists (NEVER_RERUN).
  - Never import or run r4/u1/run_u1.py: it executes at import and rewrites U1_RESULTS.json. Since 2026-09-25
    that file is read-only (0444), so an accidental import would fail at its in-place write_text; the rule stands.
  - No F3 action of any kind: F3 is ruled KEEP UNSPENT, the tool stays unrun, and ruling 3 is not issued.
  - Never import r4/v2a/run_v2a.py: it runs main() on import and rewrites V2A_RESULTS.json. Since 2026-09-25 that
    file is read-only (0444) too; the rule stands.
  - look.py --look refuses forever. Never run rehearse_b.py again.
  No R3 step before a ruling on WAVE2_REPORT.md §6. Item 2 (4H) is the only one still open; items 1, 3, 4 and 5
  are moot or answered, and 6 is ruled (OWNER_BOUNDARY, R3 decisions).
  - The prepared F3 tool (.work/research3/wave2/f3/f3_accumulate.py) must not be run without ruling 3. Its
    built-in date guard (refusing before 2026-09-21T00:00Z) has expired, so this rule is now PROCEDURAL ONLY.
  - Candidate next work, once approved (WAVE2_REPORT.md §7):
    - W3-A long-holdout protocol (only if 1b): MOOT for this generation (item 1);
    - W3-B weak-fold diagnosis; W3-C 4H calibration; W3-D serving contract: not ruled, and currently excluded by
      the owner's 2026-09-25 constraints (new model research, serving);
    - W3-E F3 accumulation: not authorized (the F3 ruling, OWNER_BOUNDARY 4).
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
    - The decision is reproduced: of the 189 recorded fields, 173 are computed independently and 16 are
      presence-only (the 15 interpretation names and the one 4H exclusion entry, which C3 does not compute).
      The agreement claim covers the 173. 0 mismatches.
    - Block-t was re-derived from the persisted weekly block means: the series match exactly, the pairs within
      1.8e-15. The unit edges are equal.
    - 52 sign-flip tests (N = 100,000) with 0 threshold flips. The sign flip permutes signs within the same
      blocks, so it addresses non-normality of the block means, NOT serial dependence.
    - Report-only sensitivity: C1's weekly series are serially dependent, lag-1 up to +0.62 at 15m on F2, where
      R3's G1 also recorded regime long memory. A single AR(1) adjustment is a lower bound, so the honest
      statement is a range of effectively independent units at 15m on F2, from 25 (the deployments, 25/25
      negative) to about 76 (AR(1) on the 282 weekly blocks); every check the decision used holds across it. The
      nominal p-values, down to 1.9e-28, are the frozen test's output under an independence assumption that does
      not hold, and are never cited as evidence strength. The thinnest robustness margin is F2 15m, not 1H F2,
      whose lag-1 is negative and whose test is therefore conservative.
    - SUPERSEDED-WORDING NOTICE (2026-09-23; the sentence above is left as published). The "25 to about 76"
      range and "every check … holds across it" are superseded. The governing statement: the long-memory
      sensitivity crosses the 0.025 bar within H = 0.80–0.85 (p 0.017/0.020 at H = 0.80; 0.065/0.072 at 0.85, per
      the C3 re-audit), so the result is not robust across that range; the status is unchanged. The same wording
      stands in the write-once c4/R4_CLOSURE_RECORD.json; its reconciliation is additive-only and not authorized
      (OWNER_BOUNDARY 8). Pointer corrected 2026-09-25: the item was OWNER_BOUNDARY 5 when this was written. The
      superseded wording also stands in c4/C4_OWNER_PACKAGE.md (line 17), and c4/PROSPECTIVE_COLLECTOR_PLAN.md
      works from the same AR(1) figure (line 43).
  - C3's independent Fable re-audit: ACCEPT WITH FINDINGS, relayed by the owner 2026-09-20
    (c4/FABLE_C3_VERDICT.txt). Its six required corrections are applied, in c4/R4_CLOSURE_RECORD.json
    ("corrections"), in c4/C4_OWNER_PACKAGE.md and here. No status, carried candidate or number changed: the
    corrections are about what may be claimed. Pack: FABLE_STAGE_C_AUDIT_PACK.md (f104f25f…).
  - C4: R4_CLOSURE_RECORD.json (2d345356…) and C4_OWNER_PACKAGE.md (3725ad02…), built only from the persisted
    Stage-B and Stage-C records: nothing was recomputed, re-read or re-tested. The 1H-F2 MCS exclusions of C1
    (p 0.0196) and C3 (0.0236) against a 0.0333 threshold are marginal, and the MCS is reported, never used.
    The collector stays OFF; the next lane is c4/PROSPECTIVE_COLLECTOR_PLAN.md, on paper, carrying the F2-15m
    dependence caveat into any duration arithmetic (r1's 18-week floor assumed independent weeks).
    SUPERSEDED as "next lane": that paper lane was taken (COLLECTOR_LANE). Later rulings govern: collector OFF
    (OWNER_BOUNDARY 7), D-5 (B now, A later), F3 KEEP UNSPENT, D-1 CLOSED and NG-1 CLOSED. The current next lane
    is in OWNER_BOUNDARY 2.
  - Verification: verify_stage_c.py, 16/16 PASS, STAGE_C_VERIFIED (it rebuilds C1, C2 and C4 byte for byte,
    checks C3's recorded outcome, the manifest and the publication commit).
  - Manifest: STAGE_C.sha256, 29 entries, sha256 c2913d364439dd9410d7995895a68819282dd142d6b0690993f781ed6fcce4ca.
    It includes the Codex task, result and log files. The T3 and T4 run records are in stage_c/b_run/. The
    Fable-audited manifest was 1d9cc519…, the same files without the C4 additions.
  - Housekeeping (owner-authorized, mechanical, outside every evidence and freeze input): the foreign IDRM memory
    note and its one MEMORY.md index line, written into Claude's UCPE memory by an IDRM session on 2026-09-18,
    and the two deferred Finder files (the repo root .DS_Store and .work/.DS_Store) were moved to
    ~/.Trash/UCPE-foreign-quarantine-2026-09-20/ with a MEMORY.md backup. Untouched: r4/.DS_Store, which IS an
    entry in evidence_r4.sha256 (digest 70207ebf…), and the other .DS_Store files inside .work/research3.
  - evidence_r4.sha256 verifies 67 of 68 entries. The single difference is m0/LOOKS_CONSUMED.log, which the look
    appended to by design; the manifest's own digest is unchanged at 93bb7875….
COLLECTOR_LANE=Paper only, in .work/research3/collector_lane (gitignored).
  - COLLECTOR_LANE.sha256 03bcd906… covers the D-1…D-7 matrix, the Fable review pack and the plan.
  - The D-5 decision brief D5_EVIDENCE_SOURCE_BRIEF.md (32056f5d…) was added additively, with its own digest file
    COLLECTOR_LANE_ADDENDUM.sha256 (e72a0dc1…). Resolved by the D-5 ruling (LOOP_STATE).
B_LANE=The B lane (D-5 = B NOW, A LATER), paper and DEV only, in .work/research3/b_lane (gitignored).
  CLOSED, accepted.
  - B tests the model-skill estimand ONLY: C1 vs the generation-2 reference at 15m, digest-frozen constants replayed
    on F3. It cannot prove serving fidelity or the replacement claim; A is the separate future path for those.
  - Manifest B_LANE.sha256 cfc6da68dd374a8f3f129e04dc57d95eeb5bd3d7d930620e795a198e5d41503e covers six files:
    - ANALYSIS_PLAN.sha256, the plan frozen before any run;
    - dev_inputs.py and h_duration.py;
    - DEV_INPUTS.json and H_DURATION.json;
    - LOOK_LENGTH_DECISION.md.
    Those bytes are preserved and verify. The additive closure record B_LANE_CLOSURE_ADDENDUM.md (a828e231…) has its
    own digest file B_LANE_ADDENDUM.sha256 (9c20cb01…) and governs the decision record's wording.
  - Declared before any run: α 0.025 one-sided; power 0.80 at the median effect and 0.50 at the weakest; both scores;
    band 0.002; H ∈ [0.50, 0.85], certified at the worst case; look lengths 13-260 weeks. Inputs are DEV only and
    reproduce V2a's fold effects exactly (C0 ≡ C1 at 15m). Per-week SNR is 0.890 (log loss) and 0.901 (Brier).
  - Result: NO_FEASIBLE_LOOK_LENGTH.
    - Certifying H = 0.85 takes about 1,900-3,100 weeks; a 260-week look certifies only up to H ≈ 0.78.
    - Worst-case power is ≤ 0.55 at the median effect and ≈ 0 at the weakest.
    - The studentised Monte Carlo is below the analytic favourable case everywhere.
    - So no look length is fixed and no preregistration is digested.
    - This is consistent with V2a's closure: V2a closed on size and an inestimable regime allowance, not on this
      frontier.
  - Fable MAX review (read-only, 2026-09-23): ACCEPT. Five checks PASS, and both decisions yes. Four non-blocking
    findings, all closed by the addendum:
    1. carry the ruling and the digest into STATE (this record);
    2. write "consistent with";
    3. use the bound 0.55;
    4. add the lag-1 corroboration of H_MAX (persisted F2-15m lag-1 0.576 / 0.622 imply H ≈ 0.83 / 0.85 under
       fGn), and label option 2's figures as favourable-case.
  - NARROW CONCLUSION (governing): confirmatory B is infeasible ONLY for the current C1, under the declared design and
    H = [0.50, 0.85]. It says nothing about A, a non-confirmatory monitor, or another candidate or generation. In
    the favourable case at H = 0.85, a candidate would need a per-week median SNR of about 1.22 (five-year look),
    1.40 (two years) or 1.55 (one year), against 0.89 today.
  - F3 RULED 2026-09-23: KEEP UNSPENT (LOOP_STATE). No H narrowing, no monitor, no ruling 3, no F3 fetch.
NEXTGEN=Next-generation dependency closure, paper only, in .work/research3/nextgen (gitignored). Manifest
  NEXTGEN.sha256 fb090b866cd185d93af19c3110f04eab664e79dc26be4d36b78769ddba5cdee7 (7 entries, including the Codex
  task, result and log). Nothing was fitted, fetched, run or changed in the product.
  - STRONGER_CANDIDATE_PATH.md (451f9942…).
    - Bottom line, the adjudication's §3: "a materially stronger candidate … does not exist within UCPE's
      constraints".
    - Proposed entry bar for spending F3: per-week SNR ≥ 1.22 / 1.40 / 1.55 median and 0.85 / 0.98 / 1.08 weakest
      for 5- / 2- / 1-year looks, favourable case at H = 0.85. C1 is 0.89–0.90 and 0.59–0.62. The H range may
      only widen; at H = 0.90 the 5-year bars are 1.61 / 1.12.
    - Closed routes: more OHLCV; cross-crypto factor and altcoin pooling for BTC/ETH (§10); a weaker comparator;
      implied volatility (invariant 5).
    - Admissible: order flow — the only class rated plausible, which needs months of collected data; kline trade
      flow and a macro calendar (λ ≈ 0.01–0.02, below the 15m floor).
    - F3 is prospective only for a candidate whose digest was published first (§7.4).
    - The staged path runs development → digest freeze → T3 publication → entry test.
  - D1_ESTIMAND_STATUS_DISPLAY.md (04e1138b…): a DRAFT for owner ruling, not closed.
    - An estimand template for path A: paired rows the product produced, one evidence class, 6 bars, α 0.025
      one-sided, a test valid for long memory over A's own declared H range, and a candidate refusal cap.
    - Research statuses stay research-only. A gets REPLACEMENT_SUPPORTED / _NOT_SUPPORTED / _PENDING /
      _UNINFORMATIVE.
    - No new bare "skill": it proposes superseding S1/r1 on that word, because Change A's live directional-skill
      wording would collide.
    - R2 §2 is adoptable in principle only. R2 §4's no-direction display comes through an additive backend field.
    - It lists the six owner decisions D-1 needs.
  - d1_inventory/INVENTORY_D1.md (8501184c…): the Codex read-only inventory of live wording at origin/main
    08cb148f; its errata are in D-1 §6.
  - AUDIT_AND_CLOSURE.md (7598884e…): the one audit, ACCEPT_WITH_FINDINGS (2 HIGH, 7 MEDIUM, 7 LOW), with every
    finding closed by one bounded repair and a mechanical closure check.
  - Added 2026-09-23, additively; NEXTGEN.sha256 is unchanged. NEXTGEN_ADDENDUM.sha256
    31abac07896faef4180967c5e8a41149304c4f479721d686fb849f99d47f46b2 covers:
    - D1_RULING.md (b477c6ed…): the owner's D-1 ruling verbatim, with what is now fixed. D-1 is CLOSED and this
      record governs the draft;
    - NEWGEN_ORDERFLOW_BRIEF.md (aa14a798…): the owner brief on opening a new generation and on order-flow
      collection — options NG-0 to NG-3, the realistic timeline, the archive question to verify, and the
      authorizations each option needs. Paper only; nothing is started.
  - Added 2026-09-23, additively: ARCHIVE_VERIFICATION_NOTE.md (b6401d14…), digested by ARCHIVE_NOTE.sha256
    d0db23ea1f1bb8b2c2a821d8004ea5dba5cbd1f902d6ba6b2c07fc3bcd0111bc. It is the owner-authorized, bounded, read-only
    check of the official binance-public-data docs. Two network reads, both documentation (the repo README and
    the python/README), and no market data. It resolves the brief's open question:
    - spot trades and aggTrades archives exist (daily and monthly ZIP files, with the buyer-maker flag);
    - the official downloader defaults from 2020-01-01; earlier archive depth is not stated and not inferred;
    - no spot order-book or depth archive is listed, and none is inferred.
    It may remove the need for a collector for retrospective trade-flow research. It does not prove candidate
    value, and the evidence budget still binds. The brief and D1_RULING bytes are unchanged.
NG1=Next generation 1 (owner GO 2026-09-23: research-only, free-data-only), in
  .work/research3/nextgen/ng1 (gitignored). Manifest NG1.sha256
  a6af7eec6fe02c124f275d528c89de7298a58045b35b79fc9adf177dff816db0 (4 entries). Nothing changed in the product.
  Pilot Stage 0 ran once. Stage 1 fetched its data, ran once (VOID), was repaired and reran once: NOT_DEMONSTRATED.
  - NG1_ADMISSIBILITY_MAP.md (c5f4212a…):
    - Rule R-1: trade data are resolution-free, so a UTC day is admissible only if no timeframe's consumed, sealed
      or reserved span covers it.
    - Admissible BTC/ETH calendar [2024-08-20T09:30Z, 2025-04-14T00:00Z), about 34 weeks, seen or mined, never
      confirmatory.
    - Download envelope: spot aggTrades, UTC days 2024-08-21 → 2025-04-13 (236 days); monthly files only for whole
      admissible months; nothing else. Not authorized.
    - Option W (owner only): per-timeframe accounting for trade data, to 2026-03-03 (about 80 weeks).
    - Additive corrections to STRONGER_CANDIDATE_PATH §4: the 4H R2 sealed span (2025-04-14T12:00Z → 2026-08-11)
      and the 4H DEV cells; pre-2019 EXCLUDED; F3 weeks archived for trade flow (an inference).
  - NG1_PILOT_PREREG.md (6ce529d6…) and NG1_PILOT_PREREG.json (ddff855d…), v2: the bounded falsification pilot.
    - Question: does free flow and activity information (K: kline fields; T: aggTrades) reduce C1's out-of-sample
      15m log-variance forecast error materially?
    - f = the error fraction removed; f_mat 0.19 (λ 0.10); f_floor 0.065; α 0.0125 one-sided; H ∈ [0.50, 0.85], the
      audited ceiling.
    - Verdicts: VOID first; KILLED if UCB < 0.19; CONTINUE only if f̂ ≥ 0.19, LCB > 0.065, every fold, each symbol,
      ≥ 70% of blocks and the translation guard; otherwise NOT_DEMONSTRATED.
    - Stages: 0a controls (anchors, causality, NEG, POS_low must be KILLED, POS_high) → 0b K arm (local) → 1 T arm
      (fetch). W(b), after NOT_DEMONSTRATED, is kill-only.
    - Under the audited ceiling the strict envelope is a kill test: it kills f̂ below about 0.068 and cannot
      demonstrate below about 0.335. Option W (the 68-block W(a), lapsed; not W(b), which is kill-only) kills below
      about 0.087 and demonstrates above about 0.233 [I: power sketch].
  - NG1_AUDIT_AND_CLOSURE.md (1e324df9…): one read-only Claude audit, one bounded repair, CLOSURE_CHECK=PASS (81)
    and one bounded re-check (PASS). The audit's REJECT findings: H_max 0.70 lacked a basis and acted as a rescue;
    Stage 0 ran K alongside its precision gate; NEG was blind to look-ahead; anchor A1 would have rewritten
    U1_RESULTS.json; the features were missing from the .md; plus LOW items.
  - The pre-registration was externally anchored by main d82ca2dc (PR #117) before Stage 0 ran.
  - PILOT STAGE 0 (owner-authorized, STRICT window; run once 2026-09-23T17:01:00Z → 17:01:07Z, exit 0, preconditions
    51/51), in .work/research3/nextgen/ng1/pilot:
    - Code digested before the run: PILOT_CODE.sha256 a3eefa2c12e4e302fe30bb8e75964e6ddea5380ab3f736f6e7a5d3c52df1e881
      (37 entries; the pilot, both anchors, the synthetic tests (51/51) and the 33 archived modules imported).
    - Results: PILOT_RESULTS.sha256 5332fc3abfbba39b774b0990cd0d4ff89d77ed3bbce0a66e49a02dbad5071c6e (8 entries:
      PILOT_CODE.sha256, the five RUN_STAGE0.* capture files, STAGE0A_RESULT.json c55ba7e5…, STAGE0B_RESULT.json
      cc70dd37…). Write-once and read-only.
    - Stage 0a: DESIGN_OK.
      - A1 (U1 fold-1 linear MSE 0.3470401766089732, 15,388 rows) and A2 (B-lane fold-1 effects) reproduced
        bit-exactly.
      - Data: 339,840 minutes and 1,040 verified raw pages per symbol; raw equals npz.
      - Causality: 1,000 samples, 0 failures.
      - Controls: NEG f̂ −0.0027; POS_low f̂ 0.035, UCB 0.073, KILLED as required; POS_high f̂ 0.213, UCB 0.392.
      - 22 blocks, 29,348 evaluation rows.
    - Stage 0b: the K arm (all 12 kline features) is KILLED. On the admissible span the pre-declared kline family's
      reduction of C1's out-of-sample 15m log-variance error is below 19% (λ < 0.10) at one-sided 98.75%
      confidence, valid for H ≤ 0.85.
      - Estimate: f̂ 0.0100 (λ̂ 0.005); UCB 0.156; LCB −0.136.
      - At the report-only H 0.90 the UCB is 0.205.
      - Folds −3.3% / +5.1%; BTC −4.0%, ETH +5.7%; blocks 14/22.
      - The translation guard failed on both scores.
    - Not concluded: that klines carry no information; anything about the trade-level T family or depth; anything
      for H > 0.85; that NG-1's free-data route is closed.
    - STAGE0_AUDIT.md (632c882b…; STAGE0_AUDIT.sha256 fc87bda056c279721df71fe88edbc4161bf497693333bf7f9d575322d2c5e22f):
      one independent read-only Claude audit, ACCEPT_WITH_FINDINGS. Every statistic was recomputed exactly; there
      is no HIGH finding. The MEDIUM findings govern the wording above (H dependence; K-only scope).
      - LOW 3 closes when this record is published: that is the digests' external timestamp.
      - LOW 5: §9's "never touched" means never used in any statistic. Archived whole-array loaders held
        out-of-envelope values in memory only (the masking-wrapper exception).
      - LOW 4 and 7 are Stage-1 requirements: digest the out-of-tree imports; assert row placement.
      - LOW 6 and 8 are report-only.
  - PILOT STAGE 1 (owner-authorized 2026-09-25, STRICT window, once), in .work/research3/nextgen/ng1/pilot:
    - Before the network: the out-of-tree loads were pinned (STAGE1_DEPS.json 0825fd0d…, 36 files: the product
      package from src/ at 2c6df51 (clean; 32 files), research1's dataset.py and its .pyc, and the two 15m candle
      caches); the row-placement guard was added; the synthetic tests pass 37/37, including both sides of the
      2025-01-01 ms→µs timestamp boundary and a mixed-unit refusal. Code digested: STAGE1_CODE.sha256
      b1e31fbd4ccb0029776fa29d3e852bbff533648ee855ce73c238f7f5e5ef7649 (39 entries). The preflight passed 108/108
      (its output was not captured to a file; audit LOW 5).
    - Fetch (2026-09-25T06:18:59Z → 06:28:01Z, exit 0): sized first (10,062,297,617 bytes, under the 30 GB cap),
      then exactly the 62 pre-registered spot aggTrades ZIPs and their 62 official checksums. Every ZIP equals its
      official checksum and passes the ZIP integrity test. FETCH_SUMMARY.json 9d69aa97…; the files are read-only
      and gitignored in nextgen/ng1/data/.
    - Run (06:28:29Z → 06:28:39Z, exit 3): preconditions 173/173 and the data checks passed, then VOID at step
      dependency_pins. The first causal failure, preserved: two unpinned out-of-tree files were loaded,
      .work/research/cache/datasets/BTCUSDT_4H.pkl and ETHUSDT_4H.pkl (38 loaded, 36 pinned). The shared row build
      (arms.prepare → week_from_4h) reads the 4H caches, while the pin and preflight modes exercised only the 15m
      loads. No aggTrades file was parsed; no T feature, statistic or Stage-0b reproduction exists.
    - Results: STAGE1_RESULTS.sha256 78954b230887d19cdb283f5c934cba302625e802b5cd18a440d90494a43ead3e (16 entries,
      including STAGE1_RESULT.json 95fd8d14…, the RUN_FETCH.* and RUN_STAGE1.* capture and the fetch manifests).
      Write-once and read-only.
    - STAGE1_AUDIT.md (73c802d2…; STAGE1_AUDIT.sha256 68c9a1313b9a93df32070039c6fcf5953e91152cd1e7b8d0e2715e5de07b1ca9):
      one independent read-only Claude audit, ACCEPT_WITH_FINDINGS. It re-derived the 62-file plan, re-hashed all
      62 ZIPs (0 mismatches), and confirmed the VOID, the pre-network provenance and the one-run rule.
      - MEDIUM 1: the pins came from a stand-in path, not the run's exact path (the VOID's cause).
      - LOW: the pin check runs once; the 4H inputs are undeclared but inert (mf=False; their digests equal the
        read-only R2 archive manifest); venue_parity's trade-id flag is hard-coded; no log of the pin and preflight
        runs; the row-placement guard is untested and never ran; the data folder was writable (now 0555).
    - Concluded: Stage 1 is VOID and no T verdict exists. Nothing is claimed about trade-level data, depth, or the
      free-data route beyond Stage 0's kline result.
  - STAGE-1 REPAIR, attempt 2 (owner-authorized 2026-09-25, preparation only; not run), in the same folder:
    - The change is to ng1_stage1.py only; attempt 1's bytes are kept as ng1_stage1.attempt1.py (a5bfef6d…).
      - The pin and preflight modes run the run's own steps before its pin check: preconditions, data
        preconditions, P.research_imports, P.load_minutes for both symbols, P.build_stage.
      - The preflight requires loaded = pinned in both directions; verification hashing is not counted as a load.
      - The pin mode stops unless the new pins are attempt 1's 36 unchanged plus exactly the two 4H caches.
      - Outputs are attempt-suffixed. Attempt 1's record, the fetch summary, src/ cleanliness and the
        unchanged-code rule are preconditions.
      - Step order, constants, seeds, features and gates are unchanged. Repair note: STAGE1_REPAIR.attempt2.md
        (3d1ed069…).
    - Re-pin (RUN_PIN_DEPS.attempt2.*, 09:29:16Z, exit 0): preconditions 121/121; 38 files = 36 unchanged +
      BTCUSDT_4H.pkl 45cc136f… + ETHUSDT_4H.pkl c98b5059…; HEAD 2c6df51, src/ clean. STAGE1_DEPS.attempt2.json is
      e3babf74…. A first wrapper invocation failed before Python started (zsh, exit 127) and wrote nothing; its
      capture is kept as RUN_PIN_DEPS.attempt2.wrapper_error.*.
    - Code digested: STAGE1_CODE.attempt2.sha256 55c7794c516676980dc3f323b60ab86374943fc6e620dffdc51e2c895de8f825
      (40 entries: attempt 1's 39, with ng1_stage1.py at 125076d7… and the new pins in place of the old, plus the
      note).
    - Then, against the digested code: the synthetic tests pass 37/37 and 51/51 (RUN_TESTS.attempt2.*); the
      preflight (RUN_PREFLIGHT.attempt2.*) passes, with preconditions 210/210 and loaded 38 = pinned 38.
    - Sealed: STAGE1_PREP.attempt2.sha256 5f225f11de512d0925eda55f424a8bf8e646f823586e98a979f7afa8bf10046a (22
      entries: the captures, the code manifest and the attempt-1 copy).
    - STAGE1_REPAIR_REVIEW.attempt2.md (f8623310…; STAGE1_REPAIR_REVIEW.attempt2.sha256 87bb0d9e…): one
      independent read-only Claude review, ACCEPT_WITH_FINDINGS (0 HIGH, 0 MEDIUM, 6 LOW). The reviewed repair
      (manifest 55c7794c…) was named in the one rerun authorization (LOOP_STATE). Two corrections are recorded there:
      - the review brief wrongly said the synthetic suites write nothing; they use temporary folders and test the
        hook's refusals;
      - "sealed" overstates R2_ARCHIVE_MANIFEST.json: it is read-only, and its 4H digests are anchored in git
        elsewhere.
    - At preparation, no T data was read and no pilot statistic was computed.
  - STAGE-1 RERUN, attempt 2 (owner-authorized 2026-09-25; run once 10:12:41Z → 10:25:33Z, 772 s, exit 0):
    - Preconditions 210/210, and every step passed:
      - dependency pins: 38 loaded, none unpinned or unused;
      - row placement: 0 violations;
      - Stage-0b reproduction: exact (difference 0.0);
      - schema: 31 files per symbol, 416,220,475 BTC and 337,797,026 ETH aggTrades, units ms and µs, 0 negative
        gaps;
      - venue parity: 1.0 on all four checks;
      - causality: K and T, 500 samples per symbol; streaming = direct within 8.7e-13.
    - T arm vs B0 (22 blocks, 29,348 rows): f̂ 0.0095 (λ̂ 0.005); UCB 0.223 (at H 0.85); LCB −0.204; folds −3.2% /
      +4.9%; BTC −7.3%, ETH +8.6%; blocks 13/22; translation guard failed. Verdict **NOT_DEMONSTRATED**.
    - T vs K (report-only): f̂_TK −0.0006.
    - Result STAGE1_RESULT.attempt2.json 2b3aeb9b… (it cites manifest 55c7794c…). It is sealed with its raw capture
      in STAGE1_RESULTS.attempt2.sha256 d7c4e8ad9bffcd6b4a3489a80983e03f43bc0fc884e49c45ede4f70d184894f5
      (11 entries).
    - STAGE1_AUDIT.attempt2.md (f20ef34a…; STAGE1_AUDIT.attempt2.sha256
      e86072c489befef21fb6a5ac1d37e707370b6d4e5616264625ddeb248ebe90fb): the pre-registered independent read-only
      audit, ACCEPT_WITH_FINDINGS (0 HIGH, 2 MEDIUM interpretive, 4 LOW). Every statistic recomputed with a largest
      difference of 0.0, and the verdict stands.
      - M1: not being KILLED depends on the top of the H grid (the UCB crosses 0.19 at H ≈ 0.815). The crossing may
        be disclosed only as a caveat; reading "KILLED for H ≤ 0.80" would pick H after seeing the result.
      - M2: no sub-group claim (fold 2, ETH); W(b) is kill-only.
      - L3: the verification `git fetch` on the main repository ran 25 s before the run. It changed only the
        remote-tracking ref, not HEAD, index or worktree.
    - Governing wording: the audit's exact text, quoted in the header above.
    - Not concluded: that T is KILLED; any exclusion for a narrower H range; that the free-data route is closed;
      anything about depth or other trade constructions; "T adds nothing beyond K"; profitability.
    - §9's one bounded re-check of this record's wording (read-only Claude, 2026-09-25) FAILED on two blocking
      points: the Stage-0 claim in OWNER_BOUNDARY 6 lacked "valid for H ≤ 0.85", and the audit seal was cited only by
      prefix. It also made five LOW notes: stale rerun pointers, the verification fetch, the review carried by digest
      prefix only, "was parsed", and the W(a) label. All were applied word for word and confirmed mechanically.
  - CLOSED by the owner, 2026-09-25 ("CLOSE NG-1; do not run W(b)").
    - Closure record: NG1_CLOSURE.md (97afaffc…; NG1_CLOSURE.sha256
      9b2a37ec12742641332a4883d170e7340766cc13239994e6a7a7146e152c31e4).
    - Every seal was re-verified at closure, and every record and data file is kept read-only.
    - W(b) is not run, and F3 stays unspent.
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
      without a ruling. That date guard has since expired: running it is now barred only procedurally
      (NEXT_ACTION; OWNER_BOUNDARY 4).
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
  - NG-1 pilot Stage 0: run once 2026-09-23T17:01:00Z (DESIGN_OK; K KILLED, valid for H ≤ 0.85). ng1_pilot.py
    --stage0 refuses once STAGE0A_RESULT.json exists. Never delete or edit nextgen/ng1/pilot/STAGE0*_RESULT.json
    or the RUN_STAGE0.* capture.
  - NG-1 pilot Stage 1: fetched once (2026-09-25T06:18:59Z) and run once (06:28:29Z, VOID). The attempt-1 code
    (ng1_stage1.attempt1.py) refused once STAGE1_RESULT.json existed; its one rerun was attempt 2 (below). Never
    delete or edit STAGE1_RESULT.json, the RUN_STAGE1.* and RUN_FETCH.* capture, or anything in nextgen/ng1/data/;
    never re-download.
  - The NG-1 Stage-1 repair's pin run (attempt 2, 2026-09-25T09:29:16Z): ng1_stage1.py --pin-deps refuses once
    STAGE1_DEPS.attempt2.json exists. Never edit or delete any attempt-2 file or capture.
  - The NG-1 Stage-1 rerun (attempt 2, 2026-09-25T10:12:41Z, NOT_DEMONSTRATED): final. ng1_stage1.py --stage1
    refuses once STAGE1_RESULT.attempt2.json exists. Never delete or edit it, the RUN_STAGE1.attempt2.* capture,
    STAGE1_RESULTS.attempt2.sha256 or the audit record.
  - NG-1 is CLOSED (owner, 2026-09-25): no NG-1 stage, fetch or W(b) may run. Never edit or delete any NG-1 file,
    seal or data file (NG1_CLOSURE.md).
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
  - Run ./verify.sh only in a clean worktree made from origin/main (as every STATE record here is), never in the
    main checkout. scripts/check_no_secrets.py walks ROOT.rglob("*") and .work is not in SKIP_DIRS, so there it
    would read every sealed path and the NG-1 data. Narrowing the scanner needs its own owner decision.
  - Never delete .work logs or evidence files: several are digested in sealed manifests (OPEN_ITEMS).
  - Never run the F3 tool without ruling 3. Its date guard expired on 2026-09-21, so this rule is procedural only.
  - Owner rulings D1-D4, J1-J3, K1-K2, L1-L3, M1 and N1-N3 are applied. Their full text is in 2c6df51:STATE.md.
    They are an earlier series: their D1-D4 are not the D-1 to D-7 decisions of 2026-09-23.
OPEN_ITEMS=Non-blocking; none is authorized.
  - scripts/check_no_secrets.py also scans .work/ (SKIP_DIRS omits it), so a stale gitignored log can fail
    ./verify.sh on a clean tree. Fixing it narrows a mandatory scanner, which needs an explicit owner decision.
    CORRECTED 2026-09-25: the old advice here, "delete stale .work/*.log files", was unsafe. codex-822.log and
    codex-823.log are digested in r4/stage_c/STAGE_C.sha256, and codex-825.log in nextgen/NEXTGEN.sha256. Never
    delete .work logs. Verify only in a clean worktree, never in the main checkout.
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
- **Owner-gated, still open:** the v2 decisions (a) to (d); D-1 ruled (a) and (b) in principle, not implemented
  (OWNER_BOUNDARY, product decisions). The current next lane is H1 (OWNER_BOUNDARY 2).
  A v2 promotion needs its own freeze, T0, holdout and one look.
