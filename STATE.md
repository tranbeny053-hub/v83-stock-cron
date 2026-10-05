# STATE

Updated: 2026-10-05 (**THE CARD-04 COMPANION IS PUBLISHED** under the owner's T3: #230 merged as 267a6eaf, a merge
commit on the exact head 93ab50de; this record is the batch's last PR. **The owner ruled Phase 7/8 (DP-A to DP-F)**, and
Claude runs Lane P and Lane R locally under those rulings, unpublished. MODEL SUBSTITUTION: Codex is unavailable, so
Claude implements, tests and reviews directly).
**Production is unchanged: D 1caa8b08 / UCPE-PROD-E2-20261004-A (R bb2a49bd). The rollback target is 6f4420a9 (R1A).**
- **The owner (2026-10-05), verbatim. First, the T3:**
```text
CONTINUE CURRENT — Opus XHIGH. Codex remains unavailable.
T3 AUTHORIZE A4C-PUBLISH exactly as prepared:

* `feat/a4-card04-companion@93ab50dea783724c0db9fbdbeccc4d44bafb77f9`
* artifact `ucpe.a4_card04_companion.v1`
* SHA256 `0b3cbb753210833d6776cab921fc6f2fa07ec89489ea150be28e2b77adddb646`
* STATE branch currently `chore/state-a4-card04-companion@2ac100e2392f015a55a491742d82596bd38a9196`.

Publish the lane, verify exact head/file set, required CI including PostgreSQL 17.6 rehearsal, and merge with MERGE COMMIT ONLY if every gate is green. No squash/rebase. Then refresh the STATE record onto resulting main, record exact merge/run identities, verify, publish and merge STATE LAST. Stop on SHA/diff/conflict/red-CI mismatch.
IMPORTANT: UOR is only one lane. Do NOT idle or focus exclusively on UOR while its PR/CI runs.
In parallel, use one separate worktree as lane 2 and re-read canonical STATE + governing Phase 0–8 plan from current main. Select and exhaust the highest-value genuinely dependency-safe reversible UCPE T0/T1/T2 work that is independent of A4C/UOR/STATE/shared live surfaces. Claude owns repo search, implementation, tests, debugging and review directly.
Priority is actual UCPE product/engineering progress, not UOR support. Prefer Phase-7/Phase-8 work that improves product value, reliability, recovery, maintainability or measured performance without needing an unresolved owner ruling or manufactured traffic. Do not spend effort on further pytest speed-up or historical archival while higher-value safe product work exists.
Max 2 proven-independent lanes total. Keep shared surfaces serial. Lane 2 remains local-only unless separately authorized for T3; do not mix its unmerged state into the A4C STATE publication.
If no genuine implementation lane is currently executable because every remaining item depends on natural evidence or owner product/methodology rulings, do NOT invent busywork. Instead, while A4C CI runs, produce one consolidated owner-decision package that resolves the minimum set of Phase-7/8 blockers needed to unlock the largest amount of next implementation work, with recommended options and consequences. Batch those decisions rather than returning one at a time.
After A4C + STATE publication finishes, immediately continue lane 2 or the first newly-unblocked safe UCPE work. Do not return merely because the UOR artifact merged.
Preserve unchanged: Phase-4 INFEASIBLE; D4 consumed; F3 KEEP_UNSPENT; H2 hold; UX-1/Q1 and B5 unless explicitly ruled; evidence-origin semantics; no manufactured USER_REQUESTED traffic.
No production A4/A4C query, HF deploy, DB mutation, secret operation, F3/protected access or T4 is authorized here.
Return only at the next genuine owner/product/methodology/T3/T4/secret/protected-evidence boundary, with all dependency-safe UCPE work exhausted and one batched owner action.
```
  **Then, in Manual mode, the continuation and the Phase-7/8 rulings:**
```text
A4C continue — Manual mode. Complete the already-authorized T3 exactly: open the PR from `feat/a4-card04-companion@93ab50dea783724c0db9fbdbeccc4d44bafb77f9`, verify exact head/diff and all required CI including PG17.6, merge by merge commit only if green, then refresh/publish/merge the STATE PR last. Stop on any drift/red check; no production A4/A4C query.

Owner Phase-7/8 rulings:
DP-A=2.
DP-B=2 NARROW: allow app-lifetime pooled clients, exact identical in-flight single-flight/coalescing, and passive deadline/latency measurement only. Preserve current provider request/retry/error/freshness semantics exactly. NO new retries, retry-policy change, negative/failure cache, candle/data cache or freshness-changing cache until natural baseline evidence.
DP-C=2: observe-only measurement only; refuse nobody, change no response/payload, record no user/session identifier.
DP-D=2: structure-first. Build/rehearse all safe local restore tooling and prepare the exact minimum owner export card, but do not access/export production schema or roles until the next genuine owner boundary.
DP-E=1: retain named per-change §2.6 crossings.
DP-F=2: bundle locally with DP-A, human-route only. `radar_evidence.v1` and AUTOMATED_RADAR semantics/values must remain byte/semantic compatible until a separately governed UOR contract revision; if clean separation is impossible, HOLD rather than alter UOR evidence.

Execution: after A4C publication, continue continuously. Max 2 proven-independent implementation lanes:
Lane P = DP-A + DP-F product work.
Lane R = narrowed DP-B + DP-C runtime/measurement work.
Use separate worktrees; shared surfaces serial. Claude implements/tests/debugs/reviews directly; no Codex. Exhaust all dependency-safe T0/T1/T2 work, mutation/adversarial tests, full gates and fresh reviews. Prepare DP-D tooling after capacity frees.

DP-A product work stays LOCAL ONLY: do not publish/release regenerated UOR examples, analysis-hash goldens, UX-1, DecisionView or B5 changes until the UOR qualification episode closes or I explicitly authorize that publication. Lane R publication also remains a new T3 boundary.

Preserve Phase-4 INFEASIBLE, D4 consumed, F3 KEEP_UNSPENT, H2 hold and evidence-origin semantics. No manufactured USER_REQUESTED traffic, production deploy, DB mutation, secret action, F3/§5A access or new T4.

Do not return on routine milestones. Return only after all safe work under these rulings is exhausted, with one batched next owner boundary.
```
- **The publication** (the owner's T3 A4C-PUBLISH, consumed):
  - Checked before the push: origin/main fc03be8e unchanged; the lane exactly 93ab50de (15 files); STATE 2ac100e2.
  - The lane branch was pushed at 93ab50de. Auto refused `gh pr create` ([Data Exfiltration]); after the owner switched
    to Manual mode, #230 was opened with the same title and body.
  - The PR's checks on 93ab50de, all green, and its file set equal to the reviewed lane's:
    - CI 37269416943 (test);
    - the companion rehearsal 37269417063 (rehearse): A4C_REHEARSAL=PASS on server 17.6, the card's python -I -B
      command ok;
    - the reproducible build 37269416910 (build-a, build-b, compare).
  - Merged at 06:19:38Z as **267a6eaf** with --match-head-commit: a merge commit (parents fc03be8e and 93ab50de) whose
    tree equals the lane head's. SOURCE_COMMIT d263c090 is reachable from main; MANIFEST.json on main hashes to
    0b3cbb75….
  - Main 267a6eaf: push CI 37271854804 and the reproducible build 37271854824, both success.
- **The UOR side is the owner's:** carry UOR_HANDOFF §14 and §15 (and this record's final values) to UOR. Running either A4
  artifact against production stays a future owner decision at the UOR episode.
- **Lane 2, before the rulings:** no Phase-7/8 implementation lane was executable without a ruling or natural evidence.
  The owner-decision package (.work/roadmap/phase7/P7_P8_DECISION_PACKAGE_2026-10-05.md) led to the rulings above.
- **Next, locally, and not part of this record's publication:**
  - Lane P (DP-A + DP-F): UX-1, DecisionView and the human-route DEGRADED;
  - Lane R (DP-B as narrowed + DP-C): the pooled transport, identical in-flight single-flight, passive measurement and the
    observe-only budget counter;
  - then DP-D's local restore tooling and the owner export card.

  Lane P stays local until the UOR qualification episode closes or the owner authorizes its publication. Lane R's
  publication is a new T3.
- **Unchanged:** Phase 4 INFEASIBLE; D4 consumed; F3 KEEP_UNSPENT; the H2 hold; evidence-origin semantics; no
  manufactured USER_REQUESTED traffic; no production query, deploy, database write, secret or §5A access.
Previously (**THE CARD-04 COMPANION IS PREPARED AND VERIFIED LOCALLY**, with the owner's cross-credential
count and the owner-authorized third repair, and the A4 handoff's two documentation defects are corrected. Both wait
only on the owner's T3. MODEL SUBSTITUTION: Codex is unavailable, so Claude implemented, tested and reviewed directly).
**Production is unchanged: D 1caa8b08 / UCPE-PROD-E2-20261004-A (R bb2a49bd). The rollback target is 6f4420a9 (R1A).**
- **The owner (2026-10-05), verbatim:**
```text
CONTINUE CURRENT — Opus XHIGH. Codex remains unavailable: Claude directly owns implementation/tests/review; no paid fallback.
UOR OWNER DECISION: KEEP UOR Card 04 unchanged. UOR already accepts the existing sealed component exactly as:
`ucpe.a4_ledger_audit.v1`
SHA256 `2007fa28a52048e13c1cadbc8e7d5c67fd317dcb9d3bb9e57d1a581a728b6577`
source `e468f1f118870f904d90505a3cdbb74446d5a495`.
DO NOT modify/reseal that package or weaken/rewrite Card 04.
Build one NEW UCPE-governed sealed READ-ONLY companion artifact proving only Card-04's remaining durable facts:

1. `deadline_ms` for the exact AUTOMATED_RADAR request;
2. `analysis_hash` for that exact successful response/run;
3. count of `predictions` rows for the bound `run_id`;
4. count of `automation_radar_ledger` rows for the bound `credential_id` since `qualification_activation_utc`.

First independently prove the authoritative durable source of each fact from current migrations/code. Current schema indicates likely sources:

* ledger `deadline_ms`;
* ledger `analysis_hash`;
* `predictions.run_id` count only;
* ledger `credential_id` + `received_at_utc`.
Do not assume this summary is authoritative: verify it. If any fact is not durably recoverable, STOP with `COMPANION_STATUS=BLOCKED` and the minimum future upstream schema/contract change; do not invent or infer the fact and do not mutate production.

The companion must remain minimal. Prefer binding the target row by `(credential_id, client_request_id)` plus expected `run_id`; take only the additional non-secret expectations required to prove the facts, likely `expected_deadline_ms`, `expected_analysis_hash`, and canonical `qualification_activation_utc`. Do not require release_id/evidence_hash again unless technically necessary, because the accepted A4 artifact already proves those. Explain every input.
The SQL/result may inspect ONLY the minimum required columns:

* `public.automation_radar_ledger`: only columns necessary for exact row/success binding, deadline_ms, analysis_hash and credential-row count since activation;
* `public.predictions`: `run_id` only for `count(*) WHERE run_id = expected_run_id`;
* minimal pg_catalog metadata for schema proof.
No prediction probabilities, labels, outcomes, feature snapshots, calibration, §5A seal/holdout, analysis payloads, full response_body output, credential registry, secrets or broad dumps.

Reading `predictions` solely to return the scalar run-id count is audit/isolation evidence, never model/directional evidence. Do not create USER_REQUESTED, CONTROLLED_SMOKE or other traffic.
Output one deterministic canonical JSON/scalar result containing only:

* companion artifact identity/version and sealed SQL digest;
* verdict PASS|FAIL and first deterministic failure reason;
* minimum bound request/run identities;
* `deadline_ms`, `deadline_ms_matches`;
* `analysis_hash`, `analysis_hash_matches`;
* `predictions_rows_for_run_id`;
* `credential_ledger_rows_since_activation`;
* only minimal schema/read-only proof fields.
Do not embed UOR's acceptance threshold for either count unless the existing Card 04 itself proves that requirement; report the durable scalar fact and let unchanged UOR Card 04 adjudicate it.

Fail closed on schema drift, missing/ambiguous target row, wrong AUTOMATED_RADAR origin, non-success/non-200 target, run mismatch, deadline mismatch, analysis-hash mismatch, invalid activation timestamp or activation after the bound request, database/read-only failure, or any unexpected shape. Never output the stored response body.
Use a sealed SELECT plus a runner that:

* begins/sets a PostgreSQL READ ONLY transaction and positively proves `transaction_read_only=on` before the audit;
* uses bounded statement/lock timeouts and unconditional rollback;
* refuses unexpected args/credential token values and never echoes DB errors/URLs/secrets;
* pins and verifies SQL/package digests before execution;
* has static structural guards restricting relations/columns/functions to the declared minimum.

Testing/review requirements:

* migration/schema proof against the current governed migrations;
* structural SQL guard;
* adversarial SQL mutants and runner mutants;
* synthetic/local tests;
* scratch PostgreSQL at the governed version;
* least-privilege rehearsal with a role allowed to read only the exact ledger columns and `predictions.run_id` needed by the companion, with all other relevant tables/columns refused;
* prove INSERT/UPDATE/DELETE/MERGE/CREATE/ALTER/DROP/TRUNCATE cannot execute in the runner's read-only session and database state is unchanged;
* exact sealed MANIFEST/digests;
* full repo gate;
* one fresh separate-context read-only Claude review of the EXACT FINAL bytes, given only the requirements/source paths/commit, no implementation transcript or implementer summary. If findings require any material repair, repair them and run ANOTHER fresh exact-final-byte review. Do not stop with “repaired without re-review.” Truthfully state same-model-family limits.

Also repair the two known documentation-only defects from the final review of the EXISTING A4 component, without changing any sealed A4 package byte or its accepted SHA:

1. `UOR_HANDOFF.md §14` / STATE OUTPUT_CONTRACT omitted the actual `audit` output key;
2. INDEPENDENT_REVIEW cites local pre-rebase `3ba2486` / `dd1093a`; verify and replace with their reachable byte-identical merged-history equivalents (`dbc5c47` / `491b460`) if Git proves that mapping.
These are documentation corrections only. Preserve UOR's acceptance of `ucpe.a4_ledger_audit.v1` and its SHA exactly.

Do NOT “fix” the existing A4 package's non-blocking guard/path/test observations in this task if doing so would change its accepted seal. Record them historically only if needed.
Update the UCPE→UOR handoff with a separate companion section and produce exactly:
COMPANION_STATUS=PREPARED_AND_VERIFIED|BLOCKED
ARTIFACT_NAME=
ARTIFACT_SHA256=
SOURCE_COMMIT=
UPSTREAM_RELEASE_IDENTITY=
INPUT_BINDING=
OUTPUT_CONTRACT=
DEADLINE_MS_PROOF=
ANALYSIS_HASH_PROOF=
PREDICTIONS_RUN_ID_COUNT_PROOF=
CREDENTIAL_ROWS_SINCE_ACTIVATION_PROOF=
READ_ONLY_PROOF=
ISOLATION_PROOF=
TESTS=
INDEPENDENT_REVIEW=
PRODUCTION_QUERY_EXECUTED=NO
PRODUCTION_MUTATED=NO
PROTECTED_5A_ACCESSED=NO
PACKAGE_PATH=
If BLOCKED also return:
UNPROVABLE_FACT=
MINIMUM_FUTURE_UPSTREAM_CHANGE=
OWNER_BOUNDARY_REQUIRED=
No production query, deploy, database mutation, secret action, F3/protected access or UOR edit is authorized. This is local T0/T1/T2 preparation only.
Exhaust all safe implementation, mutation tests, scratch-PG rehearsal, full verification and exact-final review continuously. Do not return on routine substeps.
STOP only when the companion is fully PREPARED_AND_VERIFIED locally and the sole remaining boundary is publication, or if a real upstream/schema blocker is proven. Return the exact branch/head/files/digests and one batched T3 publication action; do not push/open PR/merge yet without a new owner T3 authorization.
```
- **The owner's ruling A4-CRID-UNIQUENESS (2026-10-05), verbatim:**
```text
CONTINUE CURRENT — Opus XHIGH.
OWNER RULING A4-CRID-UNIQUENESS = YES.
Do NOT publish the currently reviewed `feat/a4-card04-companion@4f3f00c`; the new UOR addendum changes the required companion contract, so Review 3 PASS is no longer final for the new requirement.
Keep every previously required and verified Card-04 companion fact unchanged, and add exactly one new read-only scalar:
`ledger_rows_for_client_request_id_across_all_credentials`
for the bound `client_request_id`.
Purpose: UOR Card 04 literally requires exactly one automation-ledger row for the admitted client_request_id, while the existing accepted A4 artifact proves identity using `(credential_id, client_request_id)`.
Govern this narrowly:

* authoritative source must be `public.automation_radar_ledger` only;
* count rows matching the bound `client_request_id` across ALL credential_id values;
* do NOT output any other credential_id, row identity, body, timestamp, fingerprint or secret;
* preserve AUTOMATED_RADAR isolation and every existing companion field;
* no §5A/holdout/protected access;
* no production execution or mutation;
* this scalar is audit evidence only.
The UOR target acceptance value is exactly `1`. Prefer reporting the durable scalar and let unchanged UOR Card 04 adjudicate `== 1`; do not silently rewrite Card 04 or weaken any existing companion verdict rule.

Before implementation, independently verify from migration 0013/current schema that this cross-credential count is durably and unambiguously recoverable without exposing credential-sensitive data. If not, STOP with the exact governance/schema conflict instead of inventing an alternative.
Update the sealed SQL/runner/output contract/manifest/tests/CARD and §15 handoff minimally. The output must now include the new scalar in addition to every previous key; update exact key-count assertions accordingly. Keep all previous deadline_ms, analysis_hash, predictions run-id count, activation count, read-only, RLS/least-privilege and schema-drift guarantees.
Extend the structural guard so the new query can read only `automation_radar_ledger.client_request_id` for this global count beyond the already-authorized ledger columns. Prove it cannot project or aggregate credential_id values. No GROUP BY credential_id, no arrays/json aggregation, no row dump.
Tests/rehearsal:

* add positive cases for global count 0, 1, and >1 across different credentials;
* prove duplicate client_request_id under a second credential changes only this scalar and is visible even though the target row remains uniquely bound by `(credential_id, client_request_id)`;
* prove RLS/filtered readers are still refused rather than allowed to undercount;
* extend adversarial SQL/runner mutants and scratch PostgreSQL 17.6 rehearsal;
* rerun the full repo gate.

Because bytes will change, regenerate the companion seal and ARTIFACT_SHA256 and update SOURCE_COMMIT truthfully. The existing accepted `ucpe.a4_ledger_audit.v1` and SHA `2007fa28...` MUST remain byte-identical and untouched.
Then run a NEW fresh separate-context exact-final-byte review on the resulting companion head. The reviewer must receive the full original companion requirements plus this A4-CRID-UNIQUENESS addendum, and specifically verify:

1. the new scalar counts client_request_id across all credentials;
2. no credential-sensitive identity is exposed;
3. all earlier companion facts remain intact;
4. exact output keys/schema/seal/docs match;
5. scratch-PG/read-only/RLS evidence still holds.

If that review finds any material issue, repair and re-review the new exact final bytes. Do not stop at “repaired without re-review.”
Also preserve the already-planned doc-only corrections for the accepted A4 artifact (`audit` key and reachable review commit citations); do not reseal that accepted package.
Return only when the revised companion is `PREPARED_AND_VERIFIED` and ready for one T3 publication authorization, or on a genuine governance/schema blocker. Do not push, open PR or merge yet.
```
- **The third-repair decision** (2026-10-05). Review 4 found the static guard's class a third time; the project's
  rules allow two repair attempts per class, so the session put this to the owner (question and chosen option,
  verbatim):
```text
QUESTION: Review 4 found a third gap of the same kind in the companion's SQL guard (a test, not a sealed file). Text inside quotes passes the guard's checks as if it were real SQL. A keyword such as current_user also passes as a column name, and PostgreSQL then returns the database role name (I checked this on PostgreSQL 17.6). The sealed SQL itself is clean, and the seal and rehearsal results still hold. The project rules allow two repair attempts per kind of failure, and both are used, so a third repair needs your go-ahead. How should I proceed?
OPTION 1 (chosen): Guard + runner, reseal (Recommended) — Close the guard, so text in quotes counts only as a value and the exact quoted values, function uses, names and outputs are pinned, with every review-4 probe added as a refused test case. Also harden the runner: it checks every value before printing and prints no database value on a disagreement. That changes sealed files, so a new seal (UOR has not pinned the current one). Then rehearsal, full gate, fresh review 5, stop at T3.
```
  **The owner's answer, verbatim:**
```text
AUTHORIZE third repair: use Option 1 — guard + runner hardening + reseal. Also incorporate UOR’s new addendum now: keep the global client_request_id row count separate from the activation count, and harden the NEW companion CARD with exact file-set verification plus python -I -B if rehearsal proves it works. Do not modify/reseal the already-accepted A4 artifact; report any hardening of that artifact as a separate identity. Rehearse, full-gate, fresh exact-byte review again; no production query; stop at T3.
```
- **Superseded, never published on its own:**
  - 4f3f00cd (ARTIFACT_SHA256 d7c269b5…), which review 3 passed for the requirements of that time; the ruling
    changed the contract (13d3b16a added the count and resealed; 0652c431 named it in §15);
  - 0652c431 (ARTIFACT_SHA256 64078cb4…), which review 4 found the guard's class in (FINDINGS); the owner-authorized
    third repair replaced it (d263c090 repaired and resealed; 93ab50de named it in §15).
  - A merge commit of the final head carries both as ancestors, as it carries every commit of the branch; the
    published artifact is the final seal alone.
- **The cross-credential count's durable source,** checked before any change. Migration 0013 makes `client_request_id`
  UUID NOT NULL and part of the primary key `(credential_id, client_request_id)`. The route inserts a row only for a
  new pair (a replay or a conflict writes nothing), never rewrites either key column, and deletes nothing; only an
  owner-run purge removes rows older than 90 days. So the count is the number of credentials that reserved the id,
  read from `client_request_id` alone, with no credential named. No blocker.
- **The accepted A4 component stays as it is** (the owner: report any hardening of it as a separate identity).
  `ucpe.a4_ledger_audit.v1` (2007fa28…) lacks what the companion's third repair added: its card starts
  `python ops/a4_ledger_audit/a4_ledger_audit.py` without `-I -B`, its runner checks no exact folder and prints the
  SQL's facts on RUNNER_DISAGREES, and its test guard reads literal text as SQL (review 4's class). Giving it those
  protections would be a separate identity (for example `ucpe.a4_ledger_audit.v2`, with its own seal, review and UOR
  pin). It is not built.
- **The final A4 acceptance review** (2026-10-04, a fresh context, read-only, on main fc03be8e): FINAL_A4_REVIEW=FAIL on
  two documentation defects in UOR_HANDOFF §14, and no defect in the package.
  - Both are corrected in `e882d81`, documentation only. OUTPUT_CONTRACT now names `audit`. INDEPENDENT_REVIEW now cites
    `dbc5c47` and `491b460`: Git proves them byte-identical on every A4 path to the pre-rebase `3ba2486` and `dd1093a`
    (each pair's diff is exactly the rebase base's, `7a5ca4f` to `cd8b508`). ARTIFACT_SHA256 2007fa28… is unchanged.
  - This record's own copy of the A4 OUTPUT_CONTRACT (the 2026-10-04 block below) is corrected in place, marked.
  - Two non-blocking observations are recorded only, because fixing either would change the accepted seal:
    - the A4 manifest's `route_unchanged_since` names `api/automation_endpoint.py`, shorthand for
      `src/crypto_probability_engine/api/automation_endpoint.py` (the claim holds at the real path);
    - the A4 static guard misses an unqualified relation that no migration creates when it comes first inside a
      parenthesized join or after `SELECT DISTINCT FROM`. No such relation exists, and the probe-role rehearsal proves
      isolation at runtime.
  - **Retracted:** that review's third observation said §14's per-file digests were untested. That was wrong:
    tests/automation/test_handoff_manifest.py checks every digest row of UOR_HANDOFF.md.
  - Recorded too, from the companion's fresh reviews (2026-10-05). None is changed, by the owner's scope:
    - the A4 test guard models less SQL than PostgreSQL parses, as the companion's guard did before its repairs: a
      derived-table `SELECT *`, an `E''` escape string, and (review 4's class) literal text standing in for a pinned
      fragment pass it. The A4 sealed SQL has none of them, and the A4 seal is unaffected: its guard is a test,
      outside the seal;
    - §14's OUTPUT_CONTRACT lists the audited line's keys, including `audit` now; a runner stop also prints
      `error_class` (on DATABASE_ERROR and INTERNAL_ERROR), which §14 does not name (review 3's MINOR). A later
      doc-only change, with its own review, can name it.
- **The Card-04 companion, `ucpe.a4_card04_companion.v1`** (ops/a4_card04_companion/), on branch
  feat/a4-card04-companion. The handoff is UOR_HANDOFF §15. Final values:
```text
COMPANION_STATUS=PREPARED_AND_VERIFIED (locally, on this branch: the offline tests, the scratch-PostgreSQL 17.6 rehearsal and the full suite; not production-executed; its pull-request rehearsal and the full suite must be green on the pull request that merges it, and STATE records those runs)
ARTIFACT_NAME=ucpe.a4_card04_companion.v1
ARTIFACT_SHA256=0b3cbb753210833d6776cab921fc6f2fa07ec89489ea150be28e2b77adddb646
SOURCE_COMMIT=d263c090a903d1de8fd9e1172340b5cad50b3d32: the commit on branch feat/a4-card04-companion that introduced these sealed bytes; it reaches main through a merge commit (never a rebase or a squash), and STATE records the merge; the reviewed head of the branch is 93ab50dea783724c0db9fbdbeccc4d44bafb77f9
UPSTREAM_RELEASE_IDENTITY=UCPE-PROD-E2-20261004-A (commit 1caa8b08ebfc45b79a9b14d8217dad3b112cda8d) serves radar_evidence.v1 through the route introduced by UCPE-PROD-F1-AUTOMATION-20261001-A (5a3ef022db10462675361e8d15aa8f4f572dc1aa); src/crypto_probability_engine/automation/, src/crypto_probability_engine/api/automation_endpoint.py, migration 0013 and both radar schemas are byte-identical from 5a3ef022 to 1caa8b08 and to this branch's base, main fc03be8e; public.predictions.run_id is migration 0003's, unchanged since; each request's own release is the one the accepted A4 audit proves for the same row, so the companion takes no release input
INPUT_BINDING=(credential_id, client_request_id), the ledger's primary key, from UOR's own request (client_request_id alone is not unique across credentials), plus the received 200 response's run_id (RUN_MISMATCH otherwise; it also keys the predictions count); deadline_ms from UOR's own request and analysis_hash from the response, each compared with the row (DEADLINE_MISMATCH, ANALYSIS_HASH_MISMATCH), never trusted; qualification_activation_utc, a canonical UTC instant YYYY-MM-DDTHH:MM:SS[.ffffff]Z that opens the credential count's window and must not follow the bound request's receipt (ACTIVATION_AFTER_REQUEST); the bound client_request_id alone also keys the cross-credential count; release_id and evidence_hash are not taken, because the accepted A4 audit proves them for the same row; every input is non-secret and format-checked against migration 0013's CHECKs and the route's request contract before any contact
OUTPUT_CONTRACT=one canonical JSON line (sorted keys), exactly these 19 keys: analysis_hash, analysis_hash_matches, artifact, artifact_sha256, bound_client_request_id, bound_credential_id, bound_qualification_activation_utc, bound_run_id, credential_ledger_rows_since_activation, deadline_ms, deadline_ms_matches, ledger_rows_for_client_request_id_across_all_credentials, predictions_rows_for_run_id, reason, row_security_off, schema_ok, sql_sha256, transaction_read_only, verdict; verdict PASS only with reason OK, else FAIL with the first failing check of SCHEMA_DRIFT, NO_ROW, AMBIGUOUS, WRONG_ORIGIN, NOT_COMPLETED, NOT_SUCCEEDED, RUN_MISMATCH, DEADLINE_MISMATCH, ANALYSIS_HASH_MISMATCH, ACTIVATION_AFTER_REQUEST, or RUNNER_DISAGREES; artifact_sha256 is the sha256 of the MANIFEST.json the run verified; bound_qualification_activation_utc echoes the validated activation input, so the credential count names its own window; ledger_rows_for_client_request_id_across_all_credentials counts the ledger rows carrying the bound client_request_id under any credential and in any state (owner ruling A4-CRID-UNIQUENESS; Card 04 accepts exactly 1): it is at least 1 whenever the row is bound, it is reported and never judged, and it names no credential; schema_ok is the SQL's schema proof (both tables ordinary tables in public with no inheritance child, every column read with its migration's type and nullability, the ledger's primary key the pair), and transaction_read_only and row_security_off are the session proofs the runner establishes before the SELECT; exit 0 only for PASS, and the five facts are evidence only on a PASS; every value printed is an input, a boolean, a count, a reason, or a deadline or analysis hash in the ledger's own format; a runner stop prints artifact, verdict FAIL and its reason, plus sql_sha256 and the four bound identities (bound_credential_id, bound_client_request_id, bound_run_id, bound_qualification_activation_utc) once the inputs are accepted, and error_class for a database or internal error, and nothing else: RUNNER_DISAGREES (exit 1, an answer the runner cannot reproduce, none of which is printed), NOT_ISOLATED (exit 2, not started as python -I -B; refused before any input is read), INPUT_REFUSED:<input> (exit 2), SEAL_MISMATCH (exit 3: a package file, the SQL, or a folder holding anything but its five files), DATABASE_URL_MISSING, NOT_READ_ONLY, ROW_SECURITY_NOT_OFF, DATABASE_ERROR, UNEXPECTED_RESULT_SHAPE or INTERNAL_ERROR (exit 4); never the stored response body, another row, a stored timestamp, a fingerprint or a secret
DEADLINE_MS_PROOF=the bound row's public.automation_radar_ledger.deadline_ms (migration 0013: INTEGER NOT NULL, CHECK 5000 to 60000); the route writes it once, when it reserves the row, from the validated request (automation/service.py: reserve(deadline_ms=request.deadline_ms)), and never updates it (automation/ledger.py: the completion UPDATE does not set it); it is part of the request fingerprint, so a repeat under the same key with another deadline is a 409 IDEMPOTENCY_CONFLICT, never a replay; no response body carries it, so the ledger is its only durable source; reported as deadline_ms and compared NULL-safely with UOR's own value (deadline_ms_matches, DEADLINE_MISMATCH)
ANALYSIS_HASH_PROOF=the bound row's analysis_hash (migration 0013: TEXT; for a SUCCEEDED row its CHECKs require sha256:<64 hex> and equality with the stored 200 body's analysis_hash); the route writes it when it records the success, from the same evidence object it returns (automation/service.py: complete_success(analysis_hash=evidence["analysis_hash"]), then AutomationResult(200, evidence)), and a replay returns that stored body byte for byte; judged only after the row is bound as a completed 200 success of the bound run; reported as analysis_hash and compared with the response's (analysis_hash_matches, ANALYSIS_HASH_MISMATCH)
PREDICTIONS_RUN_ID_COUNT_PROOF=count(*) of public.predictions rows whose run_id (migration 0003: TEXT NOT NULL, unchanged by every later migration) equals the bound run_id; the human route and the isolated automation route draw run ids from one generator (run_<uuid4 hex>, api/analysis_service.py), and the isolated route never writes a prediction (analyze_request_isolated: record_prediction=False, prediction_origin=None), so a nonzero count would mean an automated run reached the shared cohort; it reads predictions.run_id and nothing else, so no probability, label, outcome, snapshot or section 5A data (isolation evidence only, never model or directional evidence, by the owner's ruling of 2026-10-05); with row security off the count cannot be silently filtered; reported as predictions_rows_for_run_id, never judged
CREDENTIAL_ROWS_SINCE_ACTIVATION_PROOF=count(*) of public.automation_radar_ledger rows with the bound credential_id and received_at_utc at or after qualification_activation_utc (inclusive), whatever their state, outcome or client_request_id, the bound request's own row included; a fact separate from the cross-credential count, which has no window and no credential filter; received_at_utc is TIMESTAMPTZ NOT NULL, the server's clock at admission, written once at reservation (index arl_credential_received); ledger rows are kept at least 90 days and never purged automatically; with row security off the count cannot be silently filtered; reported as credential_ledger_rows_since_activation, never judged
READ_ONLY_PROOF=one sealed WITH...SELECT (the static structural guard in tests/automation/test_a4_card04_companion.py has two layers: the first checks every property on one token stream in which a literal is a value, never SQL: printable ASCII and standard literals only, no backslash, prefixed literal, dollar quote, quoted identifier, block comment or two adjacent literals, only the modelled operators, keywords, types and functions, every other identifier a declared name, none of them a name PostgreSQL evaluates as a value; no write, lock, SET, TABLE, comma-join, derived table, DDL or side-effect function; exactly the declared reads, literals, function calls and names; the binding, the bound row and its facts, the three counts, the checks and the final SELECT pinned token by token; the second layer admits only the sealed SQL's own token stream; 100 adversarial SQL mutants, each rejected by the first layer alone; the runner executes only those guarded bytes, pinned by sha256), run only inside SET TRANSACTION READ ONLY with statement and lock timeouts (5 s, 1 s) and row_security off, with transaction_read_only=on and row_security=off both proven before it runs, and an unconditional rollback; the runner starts only as the card runs it, python -I -B ops/a4_card04_companion/a4_card04_companion.py (NOT_ISOLATED otherwise), and before any contact checks that its folder holds exactly its five files, each a regular file, all four sealed files against MANIFEST.json and the SQL against its pinned sha256; the rehearsal runs that exact command against PostgreSQL 17.6: it PASSES with the in-process line, the folder is unchanged, every other start is refused, and a folder with one more module is refused without running it (without -I that module runs: shown); on PostgreSQL 17.6 the rehearsal refuses all 10 writes it tries under that preamble (INSERT, UPDATE, DELETE, MERGE, CREATE, ALTER, DROP, TRUNCATE), and the database, rows and catalog, is unchanged across every audit
ISOLATION_PROOF=reads ten ledger columns (credential_id, client_request_id, evidence_origin, state, outcome_code, http_status, run_id, analysis_hash, deadline_ms, received_at_utc), predictions.run_id and five pg_catalog relations, and nothing else; the static guard allows exactly those reads (each relation's uses, every data column reference: the ledger three times, the third reading only client_request_id for one count) and pins every count token by token, so no credential_id is projected, grouped or aggregated and the two ledger counts stay separate; every value the runner prints is an input, a boolean, a count, a reason, or a deadline or analysis hash in the ledger's own format, and an answer it cannot reproduce is never printed; the guard denies every other column of both tables, any star but count(*) and the decision's k.*, any derived table, any whole-row use of a table, alias or CTE, and every other table, view and function any migration creates; it requires evidence_origin AUTOMATED_RADAR on the bound row; with row security off, a reader that a row-level policy applies to is refused rather than counted through the policy (without it, a hidden reader would count zero: rehearsed); on PostgreSQL 17.6 it PASSES as a BYPASSRLS role granted exactly those eleven columns, which is refused every other column and table; no application code changed, so USER_REQUESTED, CONTROLLED_SMOKE and SCHEDULED_SHADOW_EVIDENCE are untouched; it never names the section 5A seal or reads a holdout probability
TESTS=tests/automation/test_a4_card04_companion.py: 231 (the structural guard's two layers: one token stream, the exact declared reads, literals, calls and names, the pinned binding, counts, checks and output, no star, derived table or whole-row use, the decision order, and the exact token stream; the schema equal to migrations 0013 and 0003, with the route's writers pinned; 100 adversarial SQL mutants; the runner offline, 87; 33 runner mutants, each breaking a promised behaviour (among them the exact folder, the python -I -B start, the ledger's formats and a disagreement printing nothing); the seal, the accepted A4 seal unchanged, this section and section 14's corrected contract); tests/workflows/test_a4_card04_companion_rehearsal_workflow.py: 7; the scratch-PostgreSQL 17.6 rehearsal (39 audit cases, among them the cross-credential count at 0, 1 and 2, a reused request id that moves only that count and an activation that moves only the credential count; the card's exact command, python -I -B, with every other start refused and a planted module refused; the eleven-column probe, two row-security readers refused, 10 refused writes): A4C_REHEARSAL=PASS locally, with the same scripts as the pull-request workflow; the full suite: VERIFY=PASS locally (6376 passed); both must be green on the pull request that merges this package, and STATE records those runs
INDEPENDENT_REVIEW=PASS: the fifth fresh separate-context read-only Claude review of the exact head 93ab50dea783724c0db9fbdbeccc4d44bafb77f9, given the original requirements, the A4-CRID-UNIQUENESS addendum and the owner's third-repair authorization verbatim, returned REVIEW_VERDICT=PASS with all ten points VERIFIED (one MINOR and three NITs, none needing a material repair, recorded in STATE), after review 1 of db176ec1 (FINDINGS, repaired in 116b68cf), review 2 of 4edd6e4b (FINDINGS, the same class, repaired at its root in 4f3f00cd), review 3 of 4f3f00cd (PASS for the requirements of that time, superseded by the owner's ruling A4-CRID-UNIQUENESS) and review 4 of 0652c431 (FINDINGS, the same class a third time, escalated and repaired with the owner's authorization in d263c090); each was a new context given only the owner's texts, the source paths and the commit (the same model family, so not organizationally independent)
PRODUCTION_QUERY_EXECUTED=NO
PRODUCTION_MUTATED=NO
PROTECTED_5A_ACCESSED=NO
PACKAGE_PATH=ops/a4_card04_companion/
```
- **The review:** five fresh separate-context reviews, each a new Claude context given only the owner's texts (from review 4 on, the
  A4-CRID-UNIQUENESS addendum too; for review 5, the owner's third-repair authorization too), the source paths and the
  exact commit, with no transcript and no implementer summary (the same model family, so not organizationally
  independent):
  - Review 1, of db176ec1: FINDINGS.
    - MAJOR: the static guard passed a star, a derived table, or a whole-row read through a CTE alias or name. The
      sealed SQL never had them.
    - MINOR: the card's database role. NITs: an inheritance child was not schema drift; stop-line wording; three gaps
      in the runner battery; small text.
    - Repaired in 116b68cf (the SQL now refuses an inheritance child: resealed d7c269b5…) and 4edd6e4b.
  - Review 2, of 4edd6e4b: FINDINGS.
    - MAJOR, the same causal class: the guard's literal scanner knew no `E''` escape strings, so `E'\''` hid a
      subquery from it; a non-ASCII alias passed too.
    - The bounded-repair rule's second attempt, at the root, in 4f3f00cd: the guard's model of SQL is closed
      (printable ASCII, standard literals, modelled operators, keywords, types and functions, declared names, listed
      catalog columns), and the declared reads are exact. No sealed byte changed.
  - Review 3, of 4f3f00cd: PASS for the requirements of that time (one MINOR: §14 does not name A4's `error_class`;
    NITs), recorded and not changed. The owner's ruling A4-CRID-UNIQUENESS then superseded that head.
  - Review 4, of 0652c431 (the original requirements and the addendum): FINDINGS.
    - MAJOR, the guard's class a third time: the fragment pins, the decision checks, the 'OK' count and the output
      names read text that kept the literals' contents, so a literal could stand in for pinned SQL (11 probes passed
      with no violation; one, resealed on scratch PostgreSQL 17.6, printed three credential ids as a count). The
      sealed SQL was clean. NITs: §15 said "four facts"; the card said "neither count".
    - The session's sibling scan: a name PostgreSQL evaluates as a value, declared as a column (`current_user`),
      passed the guard; on 17.6 it returns the role.
    - Both repair attempts of the class were used, so it went to the owner, who authorized one consolidated repair
      with runner hardening and a reseal, with UOR's addendum (verbatim above): d263c090 (resealed 0b3cbb75…) and
      93ab50de (§15's SOURCE_COMMIT).
  - Review 5, of 93ab50de: PASS, all ten points VERIFIED. Recorded here and not changed, because a change would leave
    the reviewed bytes:
    - MINOR: the guard's first layer alone can still be satisfied by a second, nested CTE that shadows a pinned one
      (or leaves it unused), or by `OR TRUE` added to the schema proof, which it pins only in part; the second layer,
      the exact token stream, refuses every such SQL, so the guard as a whole holds. The test docstring and §15 credit
      the first layer with the counts' separation, which the two layers guarantee together.
    - NITs: "only an answer it can reproduce" (the card, the runner's docstring, §15) overstates what the runner
      checks for the three counts (their types and the invariants it can derive, not their values); the card's exit-4
      line names fewer stops than §15, which matches the runner; the card's "nothing else" leaves out the five
      catalog relations of the schema proof.
    - Its own checks added: `ucpe_space_db` and an owner under FORCE ROW LEVEL SECURITY were both refused (exit 4);
      the card's exact command, run from a git-backed checkout, PASSED with the folder clean before and after.
- **The owner's download approval** (2026-10-05, in chat): postgresql-17.6.tar.bz2 (21,623,975 bytes) and its .sha256
  (90 bytes) from https://ftp.postgresql.org/pub/source/v17.6/, to build the local scratch server. The published sha256
  e0630a3600aea27511715563259ec2111cd5f4353a4b040e0be827f94cd7a8b0 is pinned in
  scripts/a4_card04_companion_rehearsal/build_postgres.sh, which CI also runs.
- **Evidence:** .work/a4c/ (LANE_RECORD.md, the rehearsal report, the verify lines, the review outputs).
- **Not done, by design:** no push, PR or merge (T3, the owner's); no production query or write; no secret; no F3, §5A
  or protected access; no UOR edit; no traffic.
Previously (**THE PUBLICATION BATCH IS COMPLETE** under the owner's T3: lane A #226, lane B #227 and the
UOR A4 upstream artifact #228 merged on exact heads; this record is the batch's last PR. MODEL SUBSTITUTION: Codex quota
exhausted, so Claude implemented A4 directly). **Production is D 1caa8b08 / UCPE-PROD-E2-20261004-A (R bb2a49bd). The
rollback target is 6f4420a9 (R1A).**
- **The owner (2026-10-04), verbatim:**
```text
CONTINUE CURRENT — Opus XHIGH. Codex quota is exhausted: do not invoke Codex, delegate.sh/codex exec, wait for quota, or use any paid fallback. Claude directly owns repo search, implementation, tests, debugging and T2 diff review; record MODEL SUBSTITUTION in STATE.
Before publishing the already-completed lanes, add one bounded UCPE-owned upstream deliverable required by UOR qualification A10. UOR MUST NOT author UCPE SQL. Build and govern a sealed READ-ONLY A4 per-request audit artifact/package for the existing AUTOMATED_RADAR / radar_evidence.v1 interface.
The artifact's sole purpose is: during one future bounded UOR qualification episode, prove the exact `public.automation_radar_ledger` row corresponding to that qualification request so UOR can adjudicate A4. Derive the minimum contract independently from current UCPE source, migration 0013, automation contract, UOR_HANDOFF and isolation evidence. Do not broaden it into a general DB inspection tool.
Hard requirements:

* no §5A/protected access and no prediction/cohort/shared prediction table as evidence authority;
* no mutation and no production query now;
* never output/read a credential VALUE; credential_id is non-secret identity only;
* preserve USER_REQUESTED / CONTROLLED_SMOKE / SCHEDULED_SHADOW_EVIDENCE semantics unchanged;
* preserve exact AUTOMATED_RADAR isolation;
* bind the exact request using the minimum unambiguous existing non-secret identity. Because the ledger key is `(credential_id, client_request_id)`, assess that pair as the primary binding and cross-check the response `run_id`; do not rely on client_request_id alone unless you can prove that is sufficient;
* output only the minimum deterministic scalar ledger facts needed by UOR A4; never return the stored full response body, unrelated rows, secrets or cohort data;
* explicitly prove expected table/schema/columns against `migrations/0013_automation_radar_ledger.sql`;
* prove response/ledger identity consistency as needed: AUTOMATED_RADAR, exact request binding, successful completed state/status, run_id and release/evidence identity, but add no field that A4 does not need;
* make the SQL/card fail closed on zero rows, duplicate/ambiguous identity, wrong origin, wrong state/outcome/status, run mismatch, release/body identity mismatch or schema drift;
* enforce/read-prove read-only semantics, preferably with a READ ONLY transaction plus static structural guards; PostgreSQL-specific syntax is acceptable because this ledger is PostgreSQL;
* explicit upstream release/source identity. Do not blindly reuse the stale statement that F1 is the only release serving radar_evidence.v1: reconcile it against current production `UCPE-PROD-E2-20261004-A` / source and the actual inherited F1 route. Correct only the minimum handoff wording needed if stale;
* seal the artifact/package and publish its SHA-256;
* synthetic/local tests, preferably scratch PostgreSQL using existing rehearsal infrastructure where available; no production DB;
* mutation/adversarial tests proving the audit cannot widen scope, touch cohort tables, omit AUTOMATED_RADAR isolation, accept ambiguity, or mutate;
* after implementation/tests, perform one fresh serial read-only UCPE review in a separate Claude context/worktree with no implementation transcript. It must inspect the exact diff/artifact and return findings. If genuine independent context cannot be obtained, say NOT_INDEPENDENT rather than claiming PASS and stop only at that acceptance boundary;
* add the minimum UCPE→UOR handoff reference needed so UOR can pin the artifact read-only. Do not change or weaken UOR Card-5/A4 acceptance to accommodate the gap.

The downstream handoff MUST contain exactly these named fields with truthful values:
A4_ARTIFACT_STATUS=
ARTIFACT_NAME=
ARTIFACT_SHA256=
UPSTREAM_RELEASE_IDENTITY=
INPUT_BINDING=
OUTPUT_CONTRACT=
READ_ONLY_PROOF=
ISOLATION_PROOF=
TESTS=
INDEPENDENT_REVIEW=
PRODUCTION_QUERY_EXECUTED=NO
PACKAGE_PATH=
Do not execute the audit against production now. Artifact PREPARED/VERIFIED locally is not production-executed evidence.
Continue UCPE work aggressively as well. Existing completed local lanes are:

* `feat/t1-test-wallclock@ebbabe6`
* `docs/p8-tooling-inventory@953fe26`
* pending STATE history `chore/state-phase4-infeasible`: pushed `cd4563c`, plus local `a44ccf6`.

Keep the A4 lane isolated from those where possible. Max 2 proven-independent lanes; shared surfaces and STATE remain serial. Preserve Phase-4 INFEASIBLE, D4 consumed, F3 KEEP_UNSPENT, H2 hold, UX-1/Q1 and B5/deferred decisions unchanged.
T3 AUTHORIZE one bounded publication batch after all local gates/reviews pass:

1. publish/open/verify/merge the already-verified Lane A and Lane B exact heads;
2. publish/open/verify/merge the exact A4 upstream-artifact branch;
3. only after those merges, refresh the pending STATE record onto resulting main so it records Phase 4 + both lanes + UOR A4 truthfully; verify it, then publish/open/merge that STATE PR LAST.
Do not treat `a44ccf6` as the final STATE if its LAST_GREEN/main references become stale. Preserve its history and rebuild/rebase the record correctly.

For every PR: exact-head/diff check + required CI; merge only if green. STOP on SHA drift, unexpected files, conflict, acceptance failure or review finding that cannot be bounded-repaired. No hf deploy, production DB write/read for A4, secrets, F3/protected access or T4 in this authorization.
After the publication batch, continue automatically through every remaining dependency-safe reversible T0/T1/T2 UCPE lane using Claude directly. Batch work/tests/reviews and do not return on routine milestones. Return only at a genuine product/methodology/T3/T4/secret/protected-evidence boundary or an unresolved causal blocker.
```
- **The publication, exact-head merges, every check green:**
  - #226, lane A: `ebbabe64` became `3216992e` at 15:17:46Z. test, build-a, build-b and compare passed.
  - #227, lane B: `953fe26c` became `cd8b508c` at 15:18:15Z. The same four passed. Main's push CI on `cd8b508c`
    passed too (37212488457, 37212488451).
  - #228, the A4 artifact: `16222c6f` became `e468f1f1` at 15:48:09Z.
    - test, build-a, build-b, compare and rehearse all passed (CI 37213822939).
    - The scratch-PostgreSQL rehearsal is run 37213822890: A4_REHEARSAL=PASS, 23 of 23 cases, isolation ok,
      read-only ok, ledger restored.
    - **The first causal failure:** run 37212719640 on `dde2118` failed one test, 6134 passing. CI writes bytecode,
      unlike the local `PYTHONDONTWRITEBYTECODE=1`, so `ops/a4_ledger_audit/__pycache__/*.pyc` was counted by the
      inventory's recursive ops/ scope.
    - **One targeted repair,** `16222c6`: the inventory ignores `__pycache__` at every depth, with a regression test.
      The failure was reproduced and fixed with bytecode on (VERIFY=PASS 6136).
    - After the rebase, the reviewed files are byte-identical. The rebase added only the package's inventory rows.
- **The UOR A4 handoff (UCPE→UOR), final values.** docs/automation/UOR_HANDOFF.md §14 carries these fields as of its
  commit; this block adds the merge and the CI runs:
```text
A4_ARTIFACT_STATUS=PREPARED_AND_VERIFIED: local tests, the separate-context review, and the scratch-PostgreSQL rehearsal on PR #228 (run 37213822890, A4_REHEARSAL=PASS); merged to main e468f1f1 (#228); not production-executed
ARTIFACT_NAME=ucpe.a4_ledger_audit.v1
ARTIFACT_SHA256=2007fa28a52048e13c1cadbc8e7d5c67fd317dcb9d3bb9e57d1a581a728b6577
UPSTREAM_RELEASE_IDENTITY=UCPE-PROD-E2-20261004-A (commit 1caa8b08ebfc45b79a9b14d8217dad3b112cda8d) serves radar_evidence.v1 through the route introduced by UCPE-PROD-F1-AUTOMATION-20261001-A (5a3ef022db10462675361e8d15aa8f4f572dc1aa), byte-identical since; each request's own release is the expected build_info.release_id from its response; the artifact's source is main e468f1f118870f904d90505a3cdbb74446d5a495 (#228)
INPUT_BINDING=(credential_id, client_request_id), the ledger's primary key, both from UOR's own request (client_request_id alone is not unique across credentials, rehearsed); cross-checked against the received 200 response: run_id, build_info.release_id, evidence_hash
OUTPUT_CONTRACT=one canonical JSON line (sorted keys) of scalar facts: artifact, audit, sql_sha256, verdict (PASS|FAIL), reason (OK, or the first of SCHEMA_DRIFT, NO_ROW, AMBIGUOUS, WRONG_ORIGIN (the row), NOT_COMPLETED, NOT_SUCCEEDED, WRONG_ORIGIN (the stored body of a completed success), BODY_IDENTITY_MISMATCH, RUN_MISMATCH, RELEASE_MISMATCH, EVIDENCE_MISMATCH, or a runner stop), bound_credential_id, bound_client_request_id, schema_ok, matched_rows, evidence_origin, origin_automated_radar, state, outcome_code, http_status, run_id, run_id_matches, release_id, release_id_matches, evidence_hash, evidence_hash_matches, body_identity_consistent, transaction_read_only; exit 0 only for PASS; never the stored body, another row, a timestamp, a fingerprint or a secret
READ_ONLY_PROOF=one sealed WITH...SELECT (static guard: no write, lock, SET, TABLE, comma-join, DDL or side-effect function; 23 adversarial mutants rejected), run only inside SET TRANSACTION READ ONLY with transaction_read_only=on proven first, a 5 s timeout and an unconditional rollback; on real PostgreSQL (run 37213822890) INSERT, UPDATE, ALTER, CREATE, DELETE and TRUNCATE were all refused under that preamble and the ledger was unchanged across every audit
ISOLATION_PROOF=reads only public.automation_radar_ledger and four pg_catalog relations; the static guard denies every other table, view and function any migration creates; requires evidence_origin AUTOMATED_RADAR on the row and in a success's stored body; on real PostgreSQL it PASSES as a role that can read only the ledger, which was refused predictions, prediction_outcomes, analysis_runs and automation_credential; no application code changed (USER_REQUESTED, CONTROLLED_SMOKE and SCHEDULED_SHADOW_EVIDENCE untouched)
TESTS=tests/automation/test_a4_ledger_audit.py 75 (guard with the decision order enforced; schema equal to migration 0013; 23 SQL mutants; the runner offline; 14 runner mutants); tests/workflows/test_a4_ledger_audit_rehearsal_workflow.py 4; full suite PASS on PR #228 (CI 37213822939) and locally with bytecode on (6136); scratch-PostgreSQL rehearsal 23/23 (run 37213822890)
INDEPENDENT_REVIEW=separate-context Claude review (a fresh context given only the commit and the requirements, no implementation transcript; the same model family, so not organizationally independent): first pass FINDINGS (1 blocker: in-progress and refused rows reported WRONG_ORIGIN; 6 minor), all repaired; delta review PASS with 3 minor findings, repaired without a further review
PRODUCTION_QUERY_EXECUTED=NO
PACKAGE_PATH=ops/a4_ledger_audit/
```
- **Corrected 2026-10-05:** the OUTPUT_CONTRACT above omitted `audit`, which every audited line carries (the sealed
  SQL's own name for the artifact). It is added in place; UOR_HANDOFF §14 is corrected the same way (`e882d81`).
- **Stale handoff wording, corrected in place (#228):**
  - §5: F1 introduced the route, which is inherited unchanged; E2 serves it now.
  - §12: the named rollback target `2096af6d` is below migration 0018's floor (WA `a2de125f`). The current target, R1A
    `6f4420a9`, keeps the route.
- **This record's history is preserved.** `cd4563c` (Phase 4) and `a44ccf6` (lanes) were merged with main `e468f1f1`
  (`640ba97`), then this record was added. Nothing was rewritten or force-pushed.
- **MODEL SUBSTITUTION:** Codex's quota is exhausted (owner, 2026-10-04). Claude did the repo search, implementation,
  tests, debugging and T2 diff review. The review was a separate-context Claude agent. No Codex, no wait, no paid
  fallback.
- **Unchanged:**
  - Phase 4 is INFEASIBLE, D4 is consumed, F3 is KEEP_UNSPENT;
  - the H2 hold, UX-1/Q1 and B5 stand;
  - no hf deploy, no production read or write, no secret, no F3 or §5A access.
Previously (**POST-PHASE-4: two dependency-safe lanes are DONE LOCALLY** under the owner's Codex resume. Both are T0/T1
and wait only on T3 publication; nothing else is safe without an owner decision).
- **The owner (2026-10-04), verbatim:** "CONTINUE CURRENT — Opus XHIGH. Recover from STATE.md + Git + .work; do not
  repeat completed work. Codex resume is authorized for safe local T0/T1/T2 only. Exhaust every dependency-safe
  reversible lane continuously, max 2 proven-independent lanes; batch implementation/tests/reviews, preserve
  H2/F3/protected evidence and all gates. Stop only at a true owner/T3/T4/secret/product/methodology blocker and
  return one batched owner action."
- **Recovered:**
  - main is 7a5ca4f9 (#225).
  - This record's first commit (cd4563c, the Phase 4 verdict) is pushed but has no PR: Auto refused `gh pr create`
    ([Data Exfiltration]).
  - Lanes were taken from plan §18: Phase 4 INFEASIBLE leads to the reference/risk product. Every open item there
    waits on an owner ruling (UX-1/D3/Q1, P7-1, custody, OD6, B5), except two.
- **Lane A, T1: feat/t1-test-wallclock @ ebbabe6** (tests only; Codex task 902):
  - **Measured cause:** macOS assesses a newly written executable on its first run (0.14–0.49 s; a later run, or a run
    through a symlink to an assessed file, costs 0.01 s). install_stub wrote a new stub per test, so ~600 workflow
    tests each paid it.
  - **Fix:** one read-only stub body per process, linked into each test's bin dir, with the test's log path in a
    sidecar. Behaviour unchanged; no assertion changed.
  - **A/B on tests/workflows, interleaved:** 39 s and 91 s with the fix, against 155 s and 150 s without. Whole-suite
    wall time swings 166–438 s with another session's load, so only the A/B is quoted.
  - VERIFY=PASS 6018; mutants 4/4 killed.
- **Lane B, T0/T1: docs/p8-tooling-inventory @ 953fe26** (Codex task 901, corrected by Claude):
  - docs/TOOLING_INVENTORY.md classifies all 100 scripts/, workflow, ops/ and runbook entries (plan Phase 8: "document
    active versus historical tooling"). Every consumed entry quotes STATE.md, and consumed workflows are dispatch-only.
  - Claude corrected four labels: the privilege audit is a read-only reference; the two production-probability report
    CLIs are references whose run is an owner decision (the §5A window, H2's rows).
  - tests/docs/test_tooling_inventory.py keeps it complete (36 checks, under 1 s). VERIFY=PASS 6050; mutants 5/5 killed.
- **Composition:** A and B share no file. Merged in a scratch tree: VERIFY=PASS 6054 (165.71 s).
- **Evidence:** .work/roadmap/lanes_20261004/ (LANES_RECORD.md a2938b16…, MANIFEST 45197cbd…).
- **Not done, by design:**
  - no push, PR or merge (T3, the owner's);
  - no production, database, secret, F3 or H2 contact, and no traffic;
  - no STATE compaction: coordination files are 12.8% of source and test bytes, under the 20% trigger.
Previously (**PHASE 4 VERDICT: INFEASIBLE**, final under the owner's rulings of 2026-10-04. The one D4 execution, OP-1 +
OP-2, ran once and is consumed. No gate is weakened; the product proceeds as an honest reference and risk application).
- **The owner (2026-10-04), verbatim:** "Owner rulings for Phase 4: 1) AUTHORIZE one bounded D4 DEV-only execution
  containing OP-1 + OP-2 together. Use a one-time truncated BTC/ETH 1H DEV extract only, horizon_end <
  2025-09-23T11:00Z; no folds 7-8, §5A, F1/F2, F3 or other protected/consumed rows. OP-1 fits the exact
  r4-c1-symmetric-cb recipe; OP-2 measures coverage-hit dependence/H only. No promotion, production wiring or claim
  acceptance. 2) F3 remains KEEP_UNSPENT. Authorize scope derivation only from canonical non-outcome metadata; do not
  open protected outcomes/artifacts. If exact scope cannot be proven without protected access, STOP and return the
  exact minimum file/field the owner must supply. 3) Staleness = Option C for now: conservative age cap. Do not train
  on consumed folds and do not introduce scheduled refits yet. Use OP-1/OP-2 plus existing drift/staleness evidence
  to derive the cap; if this makes C1 infeasible, preserve that result. 4) Freeze target margin δ = 0.03 for this
  Phase-4 claim; do not silently widen to 0.05. Execute OP-1/OP-2 with deterministic extraction hashes, pre/post
  corpus guards, mutation/adversarial checks and sealed evidence. Then exhaust all remaining safe Phase-4
  protocol/reference/dependence work and independent Phase-7 work continuously. Return only with the Phase-4
  FEASIBLE/INFEASIBLE verdict or a genuine protected/T3/T4/product boundary."
- **The D4 execution (ruling 1), once, at 2026-10-04T11:15Z** (.work/roadmap/phase4/d4_run/D4_RUN_RECORD.md, sha256
  8bb4f264…; the evidence is in .work/research3/phase4_d4, MANIFEST 66253115…). **It is CONSUMED: never rerun.**
  - **Sealed before any real read:** run_d4.py (afb929f2…) under ANALYSIS_PLAN.json (11:15:38Z). All 23 mutants were
    killed. The synthetic smoke crossed the cutoff, with a candle gap and an irregular candle.
  - **Guards:**
    - the corpus guard read 46/46 before and after;
    - the code matched 48/49 (settings.py differs, as since R4), and the environment matched the commitment;
    - no protected path was opened;
    - the store was read only by the guards and by the one-time extract.
  - **The extract:**
    - source: store/{BTC,ETH}USDT_1H, with sealed bytes, read twice with identical digests;
    - cut: R2's fold-7 train mask, horizon_end < 2025-09-23T10:59:59.999Z (one row stricter than authorized);
    - 27,065 rows per symbol, no labels, 144 files at 0444 (BTC 719fd464…, ETH f09d9e44…);
    - it lies only in R2's initial training span and DEV folds 1–6.
  - **OP-1:** r4-c1-symmetric-cb's DEV constants, n = 26,915 per symbol. validate_constants accepts them and
    independent code rebuilds them bit-identically (OP1_CONSTANTS.json 7b1dcf61…). **They are not wired, not
    promoted and not accepted.**
  - **OP-2 (dependence only):**
    - the primary local Whittle gives H 0.538 (upper 95% 0.608), so **H_c = 0.65 and L = 156 weeks**;
    - the long-scale estimators read higher: aggregated variance 0.56 / 0.65 / 0.69 at 4 / 8 / 13 weeks, weekly local
      Whittle 0.85 ± 0.10;
    - s_week is 0.060;
    - every walk-forward fit is identical on a store poisoned after its split (OP2_DEPENDENCE.json 84ffb06e…).
  - **Declared deviations:** the store, not the pickles (R4's own C1 input; the pickles were refused). The D4 note's
    "93 entries" is corrected to 46.
- **F3's scope (ruling 2), derived from canonical non-outcome metadata only** (F3_SCOPE_DERIVATION.md 0da95fe4…):
  - F3 is every BTCUSDT and ETHUSDT kline (15m, 1H, 4H) from 2026-09-21T00:00Z on, with no end date. The sources are
    G2_PROTOCOL.json, NG1_ADMISSIBILITY_MAP row 12 and R-4, and STRONGER_CANDIDATE_PATH §4.
  - No owner-supplied field is needed.
  - **Every prospective window lies inside F3, so none is admissible under KEEP_UNSPENT.**
- **Staleness (ruling 3, Option C)** (STALENESS_CAP.md 9f5b7412…):
  - The cap is 242 days. Source: V0, 1H 0.92 at 242 days and 0.73 at 403, against R4's 25% haircut.
  - C1's constants passed the cap on 2026-05-23 and are 376 days old today.
  - **C1 is INFEASIBLE under Option C. That result is preserved.**
- **δ = 0.03 is frozen (ruling 4).**
- **PHASE 4 VERDICT: INFEASIBLE** (PHASE4_VERDICT_FINAL.md be8c630f…; MANIFEST_FINAL 2114723e…):
  - Grounds: there is no admissible window (F3), and the age cap has expired. Each is sufficient alone. OP-2's
    long-scale H corroborates them.
  - Plan §17: no forced gate weakening. The product proceeds as an honest reference/risk application.
  - Phase 5 does not start for this claim.
- **Phase 7 (P7-1), passive read** (.work/roadmap/phase7/passive_20261004/P7_PASSIVE_READ.md 4404e6c0…):
  - since the 09:47:42Z restart there have been 0 analyses and 0 receipts, so there is no baseline data;
  - nothing is built that can refuse a user;
  - no dependency-independent Phase 7 step remains.
- **Nothing else changed.** Production, the database, secrets, F3, the H2 and UX-1 holds and the Codex pause are
  untouched, and no traffic was created.
- **MODEL SUBSTITUTION:** Claude alone (CODEX_PAUSED_BY_OWNER). The GPT sidecar was not consulted: no trigger.
Previously (PHASE 4 PREPARED. **The verdict is CONDITIONAL:** FEASIBLE for one claim only if the real
hit-sequence H is low enough and a window outside F3 exists; INFEASIBLE for every other claim type. The R4-C1 identity
module is unwired and has no constants).
- **Phase 4 under P4-1 and P4-2**, all T0 or synthetic, sealed in .work/roadmap/phase4 and .work/roadmap/feas2:
  - CANDIDATE_IDENTITY.md (8f961fa0…): distributional-v2 ≠ C1; C1's recipe is reproducible (48/49 frozen files).
  - D4_CLASSIFICATION_NOTE.md (aafe3292…), NO EXECUTION. It prepares OP-1 (the C1 DEV refit) and OP-2 (the DEV
    hit-sequence H) on the R2 DEV rows (1H horizon_end < 2025-09-23T11:00Z). Both are outside F3, §5A, the R2 sealed
    folds and F1/F2. It recommends a truncated DEV extract, because the pickles also hold the consumed folds 7-8.
  - INCUMBENT_BRIDGE.md (bf3e6496…): the incumbent is heuristic-v1-wave4b0; the bridge is tc-v1 on Binance rows,
    descriptive only.
  - **FEAS-2** (feas2.py sealed f27777cc…, run once, report 8e9c3a94…): the C1 recipe as frozen, year-stale constants
    in FEAS-1's four worlds.
    - Its bias is negligible (≤ 0.1 pp).
    - Its hits carry H 0.52–0.57 under short-memory volatility and 0.61–0.67 under long memory.
    - Power ≥ 0.80 at δ 0.03 holds up to H ≈ 0.55 / 0.60 / 0.62 / 0.65 at 52 / 78 / 104 / 156 weeks.
    - The NW rules are anti-conservative (size 0.05–0.20). The certified-H rule is size-valid only if H_c ≥ the true H.
    - Declared overall: NOT_FEASIBLE (the long-memory worlds fail).
  - PROTOCOL_DRAFT.md (4e693046…) and PHASE4_VERDICT.md (0fded469…): CONDITIONAL. STALENESS_ADDENDUM.md (785ab672…):
    R4 V0 shows 1H frozen-constant edge 0.73 at 403 days, so DEV-only constants start a late-2026 window about 400 days
    stale.
- **The R4-C1 identity module** (this record's PR): quant/candidate_r4_c1.py, `r4-c1-symmetric-cb`, recipe digest
  2f4742c6…
  - It is unwired, has no constants, and fails closed (CandidateNotFrozenError).
  - Its validator refuses any non-symmetric table, a wrong coefficient count, another recipe and 4H. It refuses
    distributional-v2's own tables.
  - 36 tests; mutation 16/16. It shares no code with distributional-v2.
- **Phase 7 under P7-1** (.work/roadmap/phase7/P7_PASSIVE_DESIGN.md, ba51474b…): the analysis-budget design is deferred
  and refuses no one; the performance baseline is passive; the recovery drill waits on the custody ruling.
- **MODEL SUBSTITUTION:** Claude implemented and reviewed everything (CODEX_PAUSED_BY_OWNER); nothing was independently
  reviewed (the plan reserves frontier quant review for Fable 5.1, at the owner's choice).
Previously (**PHASE 3 CLOSED: the exit is MET.** E2 is complete: consolidated, and C1's hygiene step done. Phase 4 has
begun under the owner's rulings P4-1, P4-2 and P7-1).
- **The owner (2026-10-04), verbatim:** "consolidated. Owner rulings: P4-1 = exact R4 C1 recipe gets a new separately
  named Phase-4 candidate identity; repository distributional-v2 remains integration-feasibility only, not champion.
  P4-2 = authorize all no-execution D4 classification/artifact/protocol/DEV-synthetic preparation, but no real-data
  refit yet. P7-1 = defer any user-refusing analysis-budget threshold; passive measurement/design only. Verify
  consolidation fail-closed: SUPABASE_DB_URL → ucpe_space_db → DESIGNED, and UCPE_SPACE_DB_URL +
  SUPABASE_SERVICE_ROLE_KEY absent. If PASS, close Phase 3 with the final contract re-audit, then immediately exhaust
  all safe Phase-4 work plus dependency-independent Phase-7 work in parallel. Batch implementation/tests/reviews; do
  not return on routine PRs. Preserve D4 execution gate, UX-1 hold, H2 hold, F3/protected evidence and Codex pause.
  Return only at a genuine methodology/product/T3/T4/protected-evidence/secret boundary or Phase-4
  FEASIBLE/INFEASIBLE verdict."
- **The consolidation is ACCEPTED** (.work/e2/consolidation/CONSOLIDATION_PROOF.md, sealed):
  - UCPE_SPACE_DB_URL and SUPABASE_SERVICE_ROLE_KEY are ABSENT; SUPABASE_DB_URL was updated at 09:46:23Z;
  - the restarted Space (startup 09:47:48Z) logged evidence_reader_identity at 09:47:52Z: SUPABASE_DB_URL →
    ucpe_space_db, **DESIGNED**, release E2;
  - health 200, build-info E2.

  The owner's credential and the service-role key are gone from the public runtime.
- **PHASE 3 EXIT: MET** (.work/roadmap/phase3/exit_final/PHASE3_EXIT_FINAL.md, sha256 6d515aaa…, sealed):
  - X1 PASS; X2 PASS (rehearsal-proven, not yet exercised live); **X3 PASS (live-proven)**: the writer is
    ucpe_api_writer (now its only credential), the evidence reader ucpe_space_db, and the jobs ucpe_resolver. The owner
    URL lives only in the protected Environment, and service_role is SELECT-only on core evidence;
  - W1, W2, W3, W5 and W6 DONE. W4 is DONE for its authored scope, with the §8.2 gaps recorded unchanged.

  **Phase 3 is CLOSED.**
- **Phase 4, step 1** (T0, .work/roadmap/phase4/CANDIDATE_IDENTITY.md, sha256 8f961fa0…): repository distributional-v2
  is NOT IDENTICAL to the carried C1. They differ on symmetry, the 1H shape (G4 vs G1), rv_day dedup and the training
  rows; only the venue (Binance) and the family match. R4's status attaches to C1's RECIPE under refits. The recipe is
  exactly reproducible: 48/49 frozen code files are byte-identical, and settings.py comes from git history.
  - P4-1 ruled: C1's exact recipe gets a NEW, separately named candidate identity. distributional-v2 stays
    integration-feasibility only.
- **Natural and pending:** the first natural receipt without the service-role key; the first natural skill refresh
  and F1 call as ucpe_space_db.
Previously (the E2 cutover is ACCEPTED: the Space reads as ucpe_space_db, DESIGNED. Next: the owner's
consolidation, then the Phase 3 exit).
- **The owner (2026-10-04), verbatim:** "switched. CONTINUE CURRENT — Opus 5 XHIGH. Verify E2 fail-closed; if DESIGNED,
  drive consolidation/C1 cleanup to the exact owner-secret boundary and then close Phase 3. After closure, immediately
  advance Phase 4 plus any dependency-independent Phase 7 work, batching/parallelizing all safe T0/T1/T2 work. Do not
  stop on routine substeps; preserve H2/F3/protected evidence and all acceptance gates."
- **The cutover is ACCEPTED** (.work/e2/cutover/CUTOVER_PROOF.md, sealed). The passive read at 09:17:26Z: the restarted
  Space (startup 09:16:30Z, still D 1caa8b08) logged evidence_reader_identity at 09:16:35Z:
  - db_url_source UCPE_SPACE_DB_URL, db_role ucpe_space_db, login_is_role true;
  - every attribute false; 0 memberships; no owner rights, no core write, no definer route;
  - needed privileges true, row security hides nothing, extra privileges 0;
  - **verdict DESIGNED**, release E2.

  Health 200 and build-info E2. The secret names now include UCPE_SPACE_DB_URL. It also proves production's pooler
  accepts the role's login.
- **Pending, natural only:** the next natural analysis's skill refresh and any natural F1 call, both as ucpe_space_db.
- **Next: the consolidation** (the owner's secret steps; docs/runbooks/SPACE_DB_CUTOVER.md, "Afterwards"):
  1. SUPABASE_DB_URL takes the narrow URL (copy-url);
  2. delete UCPE_SPACE_DB_URL;
  3. delete SUPABASE_SERVICE_ROLE_KEY (C1).

  Accepted only on DESIGNED from SUPABASE_DB_URL as ucpe_space_db, with both names gone. Then the final Phase 3 exit
  re-audit.
Previously (E2 RELEASED, and the existing SUPABASE_DB_URL role IDENTIFIED: it is the migration owner, so G2 is
CONFIRMED. Next: the owner's cutover).
- **The owner (2026-10-04), verbatim:** "MERGED. Canonical main is now 892713951a790d04c978ed1773a802b098fc3803.
  Continue the full E2 governed release chain from current main ... Do not touch HF/Supabase secrets or create analysis
  traffic yet. ... After deploy, identify the existing SUPABASE_DB_URL role passively before any credential cutover."
  Then: "deployed".
- **The release chain** (.work/release_e2/CHAIN.md, sealed):
  - #219 → main 89271395 (merged by the owner); identity #220 → **D 1caa8b08** (merged by Claude on its exact head;
    main frozen until the deploy). Push CI 37188882397 and the reproducible build 37188882398 on D: success.
  - The guard on D (run 37188913224): GUARD_VERIFY=PASS 8/8, delta [app.py, build_info.py].
  - Rollback findings, target 6f4420a9 (R1A): 5/5. 0018 is rollback-safe from a2de125f.
  - The re-pin, precomputed twice: 1fc0e504.
  - The runtime delta: 4 files, digest 87d560e1…, identical to the independent diff. Preflight: 9/9.
- **The owner's T4 is CONSUMED:** a fresh preflight 9/9, then DEPLOY=PASS at 08:35:32Z, 6f4420a..1caa8b0, with no
  force. Never rerun.
- **After the deploy:**
  - SETTLE=PASS: RUNNING at D after 1 poll; health 200; build-info E2; D's frontend bytes; the F1 probe 401;
  - ROLLBACK_CHECK=PASS 7/7: target 6f4420a9;
  - re-pin → **R bb2a49bd**, equal to the precomputed 1fc0e504. Push CI 37190040672 and the reproducible build 37190040630:
    success;
  - the guard on R (run 37190049170): GUARD_VERIFY=PASS, pin == live == 1caa8b08, delta [].
- **The owner's rollback command** (a T4, never automatic):
  `git push --force-with-lease=refs/heads/main:1caa8b08ebfc45b79a9b14d8217dad3b112cda8d hf
  6f4420a9e9b7f027deeaff92a53d6cbeab56b5f8:refs/heads/main`. R1A reads only SUPABASE_DB_URL, so it runs at every E2
  stage.
- **The identification** (.work/e2/identification/IDENTIFICATION.md, sealed). The first evidence_reader_identity event
  (08:35:52Z, release E2, db_url_source SUPABASE_DB_URL) shows:
  - db_role OTHER, logged in as itself;
  - NOSUPERUSER; CREATEROLE, CREATEDB, REPLICATION, BYPASSRLS, INHERIT;
  - 13 memberships; owner rights in public; core write;
  - no definer EXECUTE; extra privileges 135;
  - verdict NOT_DESIGNED.

  By elimination against the sealed 0018 report:
  - after D6 only the ucpe_* writers and the owner of all 17 public relations can write core evidence (PUBLIC holds
    nothing), and this role is no superuser;
  - the migration owner's recorded attributes are exactly these.

  **So SUPABASE_DB_URL is the migration owner, the role of the protected owner URL. G2 CONFIRMED:** the public runtime
  holds owner authority.
- **Next: the owner's cutover** (docs/runbooks/SPACE_DB_CUTOVER.md):
  1. the template, then the helper's generate;
  2. the login SQL in the SQL Editor;
  3. the new Space secret UCPE_SPACE_DB_URL.

  Accepted only if the restarted Space's event shows UCPE_SPACE_DB_URL, ucpe_space_db and DESIGNED. The rollback is
  to delete that secret.
Previously (E2 LIFTED by the owner. Its package is this record's PR: the evidence reader's identity
report, the cutover secret, the owner's helper, the rehearsal's E1 and the runbook. Next: the E2 release, then the
owner's cutover).
- **The owner (2026-10-04), verbatim:** "Owner ruling: LIFT E2 now. Complete E2 as the final Phase-3 blocker under
  the governing plan: identify and prove the exact role/privileges used by the Space's SUPABASE_DB_URL without
  exposing secret values, then migrate the Space reader to the designed narrow role `ucpe_space_db` with
  fail-closed verification and rollback. Do not change product behavior, create analysis traffic, touch
  F3/H2/UX-1/D4, or weaken existing least-privilege boundaries. Exhaust all safe T0/T1/T2 preparation first and
  return only at the exact owner secret/T3/T4 cutover boundary. After E2 is live-proven, prepare removal of
  SUPABASE_SERVICE_ROLE_KEY and run the final Phase-3 exit re-audit."
- **What the Space's direct Postgres does** (read from the code):
  - the calibration endpoint, and the skill-evidence refresh after each analysis, read predictions joined to
    prediction_outcomes;
  - the F1 route reads automation_credential, and reads, inserts and updates automation_radar_ledger (advisory
    lock, FOR UPDATE). UCPE_AUTOMATION_ENABLED is 1 on the Space;
  - the persistence fallback uses it only without REST, which is not production.

  That is exactly ucpe_space_db's grants (migration 0016, C2 with Correction 01).
- **Production's ucpe_space_db equals the design** (the 0018 apply's post-checks, run 37172530166):
  - no attribute and no membership;
  - SELECT on predictions, prediction_outcomes and automation_credential;
  - SELECT, INSERT and UPDATE on the ledger;
  - every policy is `true`;
  - no CREATE on the schema, and PUBLIC has none either.

  So the same SQL returns the same rows as today: the skill evidence (H2's input) cannot change.
- **The package (this record's PR):**
  - src/crypto_probability_engine/persistence/reader_identity.py (plan §8.3, build-tied and redacted). Once per
    process start it makes one catalog-only read: READ ONLY and rolled back, a 10 s connect and a 5 s statement
    timeout, no table row read. It logs one evidence_reader_identity event:
    - the release id and the secret's NAME;
    - the role (ucpe_* or OTHER);
    - the verdict: DESIGNED, NOT_DESIGNED, UNKNOWN or NOT_CONFIGURED;
    - booleans and counts: the attributes, memberships, owner rights, core write, definer execute, needed
      privileges, row security and extra privileges.

    DESIGNED needs every check positively proven. Any error is UNKNOWN.
  - The cutover secret: the Space uses UCPE_SPACE_DB_URL when it is set, else SUPABASE_DB_URL, which is unchanged
    without it. Adding it is the cutover. Deleting it is the instant rollback, and needs no secret value.
  - scripts/space_db_credential.py: G1's helper for ucpe_space_db. resolver_credential.py takes the role as a
    parameter; its behavior and tests are unchanged.
  - The privilege rehearsal's E1, on 0018's catalog:
    - DESIGNED for the helper's login;
    - NOT_DESIGNED for the owner, for ucpe_resolver and for three planted deviations;
    - UNKNOWN for a wrong password.
  - docs/runbooks/SPACE_DB_CUTOVER.md. app.py stands in the guard's delta until the release.
  - Product behavior is unchanged: no response, receipt, probability or gate reads the report. The only addition
    is one short connection per start.
  - MODEL SUBSTITUTION: Claude implemented it (CODEX_PAUSED_BY_OWNER). Review: CLAUDE_ADVERSARIAL_REVIEW.
- **Next:**
  1. The E2 release (docs/runbooks/RELEASE.md), ending at the owner's T4 deploy.
  2. Its first start's event identifies the role of today's SUPABASE_DB_URL, read passively.
  3. The owner's cutover (docs/runbooks/SPACE_DB_CUTOVER.md): the login SQL, then the new Space secret. It is
     accepted only on DESIGNED, from UCPE_SPACE_DB_URL, as ucpe_space_db.
  4. The consolidation:
     - the narrow URL replaces SUPABASE_DB_URL's value, then UCPE_SPACE_DB_URL is deleted. Every release, an
       older rollback target included, then reads as ucpe_space_db, and the owner credential leaves the Space;
     - SUPABASE_SERVICE_ROLE_KEY is deleted (C1);
     - it is accepted on DESIGNED from SUPABASE_DB_URL.
  5. The final exit re-audit.
Previously (D6 COMPLETE; the Phase 3 exit re-audit is done: NOT MET IN FULL, solely because E2 is
DEFERRED).
- **The owner (2026-10-04), verbatim:** "POST-D6 INVENTORY DONE and independently verified PASS: run 37181855518,
  attempt 1, exact main 9a8a1c0415e56c6d18fdf674f6626bb50ff7f6de, expect=after, failures=[], all D6 surfaces empty.
  Seal the raw post-D6 evidence and mark D6 COMPLETE in canonical STATE. Then perform the full Phase-3 exit
  re-audit against the governing contracts and current deterministic/production evidence. Preserve E2 as DEFERRED
  exactly; do not convert any deferred/hold/NOT_RUN item into PASS."
- **D6: COMPLETE.** 0018 is APPLIED (run 37172530166, .work/t4_0018_apply). The inventory with expect=after (run
  37181855518, re-verified from the raw report: dispatch at 9a8a1c04, attempt 1, approved in production-db-owner,
  verdict PASS, failures [], all eight surface kinds empty) is sealed in .work/d6_inventory_after/.
- **The Phase 3 exit re-audit** (.work/roadmap/phase3/exit/PHASE3_EXIT_REAUDIT.md, sealed), against the governing
  plan's PHASE 3, §8.1-§8.3 and §23:
  - X1, a complete bundle or no SAVED: **PASS**. X2, unknown commits reconcilable: **PASS** (rehearsal-proven;
    not yet exercised live).
  - X3, the runtime cannot mutate core evidence beyond the design: **NOT DEMONSTRATED, blocked by E2
    (DEFERRED).** The writer, the bundle owner and the resolver equal their design in production, service_role
    has no core write surface, and owner authority is only in the Environment. But the Space's SUPABASE_DB_URL
    role is uninspected.
  - Work: W1 pin transition, W2 bundle, W3 receipts and W5 privilege rehearsal are DONE. W4 DB constraints are DONE
    for 0014's scope, with §8.2 gaps recorded as they are: no outcome foreign key and no outcome chronology
    (engineering choices); additive correction records NOT BUILT; legacy rows not validated (OD-DB-1 = D). W6
    transport is PARTIAL (the evidence reader's role is E2).
  - §23 Persistence: every item PASSES on the production route as ucpe_api_writer after D6 (PERS-0 run
    37181034616). The legacy direct-Postgres route still fails C1b, C3 and C5; it is not production's writer.
- **This record's PR** also closes the D6 adjudication's follow-up: the inventory route's success report now
  carries its snapshot's own evidence (transaction_read_only, rolled_back).
- **Open, preserved exactly:**
  - E2 (DEFERRED by the owner).
  - Design C1 hygiene (owner T3): SUPABASE_SERVICE_ROLE_KEY is still a Space secret.
  - The writer JWT expires 2026-11-02; renew it by 2026-10-30.
  - The first post-D6 natural SAVED receipt (passive).
  - The H2 hold, B5's DEGRADED half, D3, D4, F3, UX-1 and OD6, unchanged.
Previously (D6 APPLIED: migration 0018 committed by run 37172530166; applied_run recorded; the expect=after inventory
was the owner's next step).
- **The owner (2026-10-04), verbatim:** "0018 NEW RUN DONE. Adjudicate the exact latest apply-migration-0018 workflow
  run from raw logs + artifacts; do not infer PASS from workflow conclusion alone. ... If APPLIED: seal evidence,
  record applied_run in the registry/STATE, then prepare the required expect=after inventory boundary."
- **0018 is APPLIED** (.work/t4_0018_apply/ADJUDICATION.md, sealed with the raw logs and artifacts):
  - Run 37172530166, attempt 1, main 82ed9c48, approved in production-db-owner. Every step succeeded. The in-job
    rehearsal applied once and refused a second apply; 173 in-job tests passed.
  - outcome APPLIED, committed true. executed_migration_sha256 = 0d334da9..., the digest pinned at main and
    the file's.
  - Post-state, read in the same transaction before the COMMIT:
    - service_role holds SELECT only on all six core tables (before: 31 write privileges plus SELECT);
    - service_role executes neither bundle function, while the writer and the owner still do;
    - ucpe_api_writer and ucpe_resolver are unchanged (grants and attributes; the resolver keeps G1's login);
    - D6's inventory is empty: T 31 -> 0, F 2 -> 0;
    - everything else is identical.
  - The run is consumed and never rerun. The earlier attempt 37170407623 was refused, unapplied, and is consumed.
- **This record's PR:**
  - The registry records 0018's applied_run 37172530166 (additive false, rollback_safe_from a2de125f). No
    migration is unapplied now, so releases may ship again (check 5c).
  - PERS-0 now writes and reads as ucpe_api_writer, as production does, instead of service_role. Its scratch
    database includes 0018, and its RPC criterion is D6's: service_role executes neither function. On real
    PostgreSQL, the persistence fault rehearsal proves the production writer's path after D6.
- **Next:** the owner dispatches the read-only inventory with expect=after at this PR's merge commit and approves
  it in production-db-owner. It must find nothing (docs/runbooks/CORE_WRITE_INVENTORY.md).
Previously (0018's T4 attempt REFUSED, NOT_APPLIED, consumed; the route was repaired by #216).
- **The owner (2026-10-04), verbatim:** "0018 RUN FAILED — DO NOT RERUN under any circumstance." Then: "If
  NOT_APPLIED: keep 0018 NOT_APPLIED and prepare a new governed repair/T4 boundary, not a rerun."
- **The attempt: run 37170407623, attempt 1, main b7d54fcc, approved in production-db-owner** (.work/t4_0018/
  ADJUDICATION.md, sealed with the raw logs and artifacts).
  - Steps 1-7 succeeded: the attest, the in-job scratch rehearsal and the tests. Step 8, the apply, was REFUSED
    by its pre-checks (exit 2): "the role ucpe_resolver holds login". That was the only failure.
  - **Committed: NO.** The report says committed false, and captured holds pre-reads only: no
    executed_migration_sha256, no commit_attempted. The migration statement never ran, and the transaction
    rolled back.
  - **Production (read in that transaction):** service_role holds all 31 pre-D6 write privileges plus SELECT
    on the six core tables, and EXECUTE on both bundle functions; the inventory is T 31, F 2, others 0.
    **0018 is NOT_APPLIED.** The attempt is consumed and never rerun.
- **Root cause:** the 0018 route copied 0017's role check (0016's four roles hold no attribute), which predates
  G1's login for ucpe_resolver (the owner's credential step, 2026-10-03, by design C3). The route's tests used
  0017's pre-G1 fixtures, and the scratch rehearsal never ran the owner's step.
- **Sibling scan:** every other pre-check matched production at the attempt. Production has no column ACLs,
  so the REVOKE cannot change the fingerprint. On the core tables, anon and authenticated already lost
  Supabase's default grants to owner-run revokes, so service_role's identical grants are the owner's to
  revoke.
- **The repair (this record's PR):** the route accepts a login on exactly the design's two login roles
  (ucpe_resolver now, ucpe_space_db after E2) and refuses every other attribute, as before. The rehearsal
  applies G1's login after migrations 0001-0017, and the probe asserts the logins. A regression test replays
  the attempt's captured roles. Mutation: 29/29 killed. The migration's bytes and the registry are unchanged
  (0018 applied_run null).
- **Next:** a NEW T4 (not a rerun): dispatch apply-migration-0018.yml at this PR's merge commit and approve it
  in production-db-owner.
Previously (D6 FROZEN: migration 0018, its one-shot route and its gates merged by #215; the owner's T4 apply was
the boundary).
- **The owner (2026-10-03), verbatim:** "If and only if the inventory is clean under the frozen D6 scope, seal the
  evidence, record STATE, then prepare migration 0018 + rollback + rehearsal/mutation gates continuously. Do not
  apply 0018 yet; return with the exact one-shot T4 apply boundary."
- **The inventory was CLEAN** (record #214, main 8c900a0; .work/d6_inventory/ADJUDICATION.md, sealed).
- **The D6 freeze package (this record's PR):**
  - migrations/0018_narrow_service_role.sql: the rehearsed draft's statements, now frozen. service_role loses
    INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES and TRIGGER (and MAINTAIN on PostgreSQL 17) on the six core
    evidence tables, and EXECUTE on both bundle functions. It keeps SELECT. A second application is refused
    (UP018). The draft file is removed; P3-PRIV-R's D1-D4 now run 0018's reviewed bytes.
  - scripts/apply_migration_0018.py: 0017's one-shot route, its trust machinery verbatim (tests enforce it).
    - Pre-checks: 0016 and 0017 exactly; ADMIN on ucpe_bundle_owner; service_role's exact pre-D6 privileges; and
      D6's inventory, read in the same transaction (no surface outside the revoke set).
    - Post-checks: service_role SELECT only; EXECUTE gone; no inventory surface; everything else unchanged.
    - Its printed and written output withholds every role name that is not an API, pg_* or ucpe_* role (the
      repository is public). 0016 and 0017 predate that rule.
  - .github/workflows/apply-migration-0018.yml: dispatch-only, in production-db-owner. It rehearses the whole apply
    on a scratch PostgreSQL before its only secret step. migration-0018-rehearsal.yml does the same on pull
    requests, followed by an independent probe.
  - The release tool: a non-additive migration may name a registered release (rollback_safe_from); a rollback to
    it, or to a descendant, stays allowed. The 0018 entry: additive false, applied_run null, rollback_safe_from
    a2de125f (WA). No release ships before 0018 is applied and recorded (check 5c).
  - Mutation gate: 25/25 killed. Tests: the route 116, both workflows, the migration, the release rule.
  - docs/runbooks/MIGRATION_0018_APPLY.md: the T4, the approval, what follows, and the rollback.
  - MODEL SUBSTITUTION: Claude implemented it (CODEX_PAUSED_BY_OWNER). Review: CLAUDE_ADVERSARIAL_REVIEW.
- **Next:** the owner's one-shot T4: dispatch apply-migration-0018.yml at this PR's merge commit and approve it in
  production-db-owner. Then Claude adjudicates the raw report, records the registry entry (applied_run), and the
  owner runs the inventory with expect=after.
Previously (E3 LIVE_PROVEN naturally; #212 MERGED; the D6 production inventory is CLEAN; 0018's freeze was being
prepared).
- **The owner (2026-10-03), verbatim:**
  - "RESUME CURRENT — check passive E3 evidence first. If E3 is naturally LIVE_PROVEN, continue the governed D6
    sequence from draft #212; otherwise continue no production action and do not manufacture traffic."
  - "INVENTORY RUN. Read and adjudicate the exact latest Core-write inventory workflow run on main
    946145bcd35722bc1ad5436faa305f86af832c56. Do not infer PASS from workflow SUCCESS alone: verify expected_sha,
    expect=before, rehearsal, READ ONLY/rollback evidence, and the raw production inventory verdict. If and only if the
    inventory is clean under the frozen D6 scope, seal the evidence, record STATE, then prepare migration 0018 +
    rollback + rehearsal/mutation gates continuously. Do not apply 0018 yet; return with the exact one-shot T4 apply
    boundary. If inventory finds any omitted write surface, HOLD and report it without narrowing/waiving scope."
- **E3: LIVE_PROVEN, naturally** (.work/e3_live_proof/E3_PROOF.md, sealed):
  - 5 USER_REQUESTED analyses at 19:41:33Z; each persistence_receipt is SAVED via SupabaseRestRepository. By 19:42:30Z
    there were 10, all SAVED, with no NOT_SAVED or COMMIT_UNKNOWN.
  - The writer pair is present by name, so SAVED means saved as ucpe_api_writer. Claude created no traffic and cannot
    see who requested the analyses.
- **#212 MERGED** (ready, then merged on its exact head f9e0e481, 7/7 green) → main 946145bc at 19:44:47Z; push CI
  37149005706 and the reproducible build 37149005710: success.
- **The D6 production inventory: CLEAN** (.work/d6_inventory/ADJUDICATION.md, sealed with the raw artifacts):
  - The auto-mode classifier refused Claude's dispatch. The owner dispatched run 37149774863 (the only run) and
    approved it in production-db-owner.
  - Verified from the raw report, not the run's status: expected_sha = sha = git_head = 946145bc; expect=before; the
    in-run rehearsal REHEARSED (exactly the six planted surfaces); 119 in-job tests passed; READ ONLY and rollback by
    the pinned code path; verdict PASS, failures [].
  - Production holds 31 table-privilege rows on the six core tables (MAINTAIN included: PostgreSQL 17 or later) and
    EXECUTE on both bundle functions (definers owned by ucpe_bundle_owner). There is no C, O, V, R, G or K surface.
  - Informational, not waived: default privileges grant service_role ALL on FUTURE objects in public, storage, graphql
    and graphql_public. A future core table must revoke explicitly.
- **Next, the owner's sequence:** freeze migration 0018 (the frozen D6 scope) with its rollback and one-shot route,
  behind rehearsal and mutation gates; then the owner's T4 apply.
Previously (C4 SET by the owner, verified by name; the D6 production-inventory route was DRAFT PR #212; E3 not yet
proven). **Production was then, as now, D 6f4420a9 / UCPE-PROD-R1A-20261003-A (R d4c25f2a).**
- **The owner (2026-10-03), verbatim:** "RESUME CURRENT — C4 SET confirmed by owner: production-db-owner configured with
  required reviewer, self-review allowed, main-only deployment branch, environment secret SUPABASE_DB_URL present, and
  repository-level SUPABASE_DB_URL deleted." Then: "Finish the D6 production-inventory route completely ... then open a
  DRAFT PR only. Do not dispatch inventory or apply D6 until E3 is naturally LIVE_PROVEN."
- **C4: SET, verified by NAME only** (GitHub API metadata; no value can be read):
  - the Environment production-db-owner: required reviewer the owner, prevent_self_review false, can_admins_bypass
    false, deployment branches main only;
  - its one secret is SUPABASE_DB_URL; the repository's only secret is UCPE_RESOLVER_DB_URL.
  - Every owner-URL workflow (14 now, 15 once #212 merges) waits for the owner's "Approve and deploy".
- **#206 MERGED** on its exact green head 4f6d9180 (11/11) → main 9d2f109c at 17:46:39Z; push CI 37141757629 and the
  reproducible build 37141757688: success. G1 is closed.
- **The D6 production-inventory route: DRAFT PR #212, all 7 checks green at c08f722; never dispatched:**
  - scripts/core_write_inventory.py gains --mode attest|rehearse|inventory, inside the other database routes' trust
    boundary. It reads one REPEATABLE READ, READ ONLY snapshot, always rolled back. Inputs: --expect before|after and
    the token READ-ONLY-CORE-WRITE-INVENTORY-ONCE.
  - The logs are public: only API, pg_* and ucpe_* role names are published. The connecting role, the URL and the
    server version never are.
  - .github/workflows/core-write-inventory.yml: dispatch-only, in production-db-owner, concurrency
    section-5a-evaluation. Before the secret step it rehearses on a scratch PostgreSQL (migrations 0001-0015 plus one
    planted surface per kind, as a role with no core privilege). It must catch every planted surface and nothing else.
  - .github/workflows/core-write-inventory-rehearsal.yml runs the same rehearsal on pull requests, with no secret.
  - A gap is fixed: privilege-rehearsal.yml now also runs D1-D4 when scripts/core_write_inventory.py changes.
  - The rehearsal on a real PostgreSQL 16 (run 37147050963) caught exactly the six planted surfaces and nothing
    else. Its 27 T rows match the migrations, and every non-allowlisted role name was withheld.
  - The steps for the owner: docs/runbooks/CORE_WRITE_INVENTORY.md (in #212).
  - Code proof for D6's owner step: deleting SUPABASE_SERVICE_ROLE_KEY from the Space is safe while the writer pair is
    set. _rest_repository uses the pair, and /v1/system_status reads repository_type from the live repository.
  - MODEL SUBSTITUTION: Claude implemented it (CODEX_PAUSED_BY_OWNER). The review is CLAUDE_ADVERSARIAL_REVIEW.
- **E3: still NOT_YET_LIVE_PROVEN.** No natural USER_REQUESTED analysis since the R1A container started (17:24:55Z):
  0 receipts at 19:17Z (read-only checks, no traffic).
- **D6's order (the owner's):** E3 live-proven → merge #212 → dispatch it with expect=before (Claude may; the owner
  approves the run in production-db-owner) → a clean inventory → freeze 0018 → its one-shot T4. The steps are in
  docs/runbooks/CORE_WRITE_INVENTORY.md (in #212).
Previously (UCPE-PROD-R1A-20261003-A RELEASED; G1 LIVE_PROVEN; #206 closes here). **Production was then, as now, D
6f4420a9 / UCPE-PROD-R1A-20261003-A (R d4c25f2a).**
- **The owner's rulings (2026-10-03), verbatim:**
  - "CONTINUE CURRENT — Opus 5 XHIGH. Owner rulings: WB3/R-1a AUTHORIZED for the exact pinned crossing only: add
    `read_core_strict(run_id, prediction_ids)` to persistence/repository.py with no in-memory fallback, returning only
    the database answer or unreadable; re-pin the evaluator and wire it into analysis_service.py. S8 = Option 1: honest
    NOT_SAVED during the open-circuit/outage window; no payload retry, no durable outbox, no new HF dataset/secret."
  - "CONTINUE CURRENT. #210 is green at exact head 7c7f2d2e80d430bd8811570d5b1272e4305c6572. Merge it on that exact
    head under standing authorization and treat its merge commit as D; freeze main at D." (then the pre-deploy chain,
    and the one-click T4).
- **R-1a: MERGED and LIVE.** #209 → 12ffb727.
  - read_core_strict is the authorized pinned crossing; the evaluator re-pin went 23c176a5… → ea5d8052….
  - The reconciler lives in analysis_service.py, with the persistence_reconciled event.
  - PERS-0 C6 PASS through read_core_strict (run 37138983552); mutation 20/20; S8 = Option 1.
- **The release chain** (.work/release_r1a/CHAIN.md, sealed):
  - identity #210 → D 6f4420a9 (main was frozen at D until the deploy);
  - push CI 37139929799 and the reproducible build 37139929766: both success;
  - the guard on D, 37139946098: PASS 8/8, delta [analysis_service.py, build_info.py];
  - rollback findings, target a2de125f (WA): 5/5;
  - the re-pin precomputed ×2: 67a9223f;
  - the preflight: 9/9, digest 4130a48c…, byte-identical to the independent diff.
- **The owner's T4 is CONSUMED:** a fresh preflight 9/9, then DEPLOY=PASS: a2de125..6f4420a, with no force. Never rerun.
- **After the deploy:**
  - SETTLE=PASS: RUNNING at D after 1 poll (17:25:16Z); health 200; build-info R1A; D's frontend bytes; the F1 probe
    401 CREDENTIAL_REQUIRED;
  - ROLLBACK_CHECK=PASS 7/7: target a2de125f, no migration after it;
  - re-pin #211 → R d4c25f2a, equal to the precomputed 67a9223f (push CI 37140995581 (success));
  - the guard on R: run 37141007416, GUARD_VERIFY=PASS, pin == live == 6f4420a9, delta [].
- **The owner's rollback command** (a T4, never automatic):
  `git push --force-with-lease=refs/heads/main:6f4420a9e9b7f027deeaff92a53d6cbeab56b5f8 hf
  a2de125ffa449cd6f5ec452e4a7a3335286eb413:refs/heads/main`. WA saves through the least-privilege pair.
- **G1: LIVE_PROVEN** (.work/g1_cutover/G1_PROOF.md, sealed). The natural scheduled run 37139970258 at D showed
  "resolver credential: UCPE_RESOLVER_DB_URL", "resolver_identity role=ucpe_resolver", and success.
  - This PR closes #206: the fallback removal, C4, C4-PIN. It merges after the deploy, because main was frozen at D.
  - Rebased onto main, the evaluator pin now combines C4-PIN and R-1a: closure 7097afd2….
- **E3: still NOT_YET_LIVE_PROVEN.** No natural USER_REQUESTED analysis yet (the R1A container started 17:24:55Z).
- **D6: B's first condition is met** (the next release is live). It stays PREPARED until E3 is live-proven and the
  production inventory is clean; then freeze and apply.
- **Next:** C4's Environment steps (the owner card; docs/runbooks/OWNER_URL_ENVIRONMENT.md); E3, read passively.
Previously (G1 SET by the owner: the resolver's own login is CONFIGURED, NOT_YET_LIVE_PROVEN; C4 prepared; the D6 design
note). **Production code was then unchanged: D a2de125f / UCPE-PROD-WA-20261003-A (R 4130a6cd).**
- **The owner's message (2026-10-03), verbatim:** "G1 SET. Verify the new GitHub secret by NAME only, never value. G1
  remains CONFIGURED/NOT_YET_LIVE_PROVEN until the next natural scheduled Resolve Prediction Outcomes run uses current
  main and proves: resolver credential=UCPE_RESOLVER_DB_URL, resolver_identity role=ucpe_resolver, terminal SUCCESS.
  Do not manually dispatch resolver traffic just to prove it. While waiting, continue the highest-value safe UCPE
  roadmap work; do not yield merely because the scheduled proof is pending. E3 writer also remains
  NOT_YET_LIVE_PROVEN until a natural USER_REQUESTED SAVED receipt."
- **Verified by name, 15:07Z** (.work/g1_cutover, sealed): UCPE_RESOLVER_DB_URL is PRESENT (created 15:03:32Z), and
  SUPABASE_DB_URL (the owner URL) is still present.
  - No resolver run on current main yet: the last was at 12:34Z, at 38b9860b.
  - GitHub's schedule is irregular: 06:33Z and 12:34Z today.
- **G1 = CONFIGURED, NOT_YET_LIVE_PROVEN.** The proof is the next natural scheduled run on current main showing
  "resolver credential: UCPE_RESOLVER_DB_URL", "resolver_identity role=ucpe_resolver" and a terminal SUCCESS. No
  manual dispatch.
- **Merged since:**
  - #203 (STATE) and #204 (G1 prep) → main 7d07b87;
  - #205 → main 70a03e4 (push CI 37131173306 and the reproducible build 37131173329, both success). The identity
    line now names only ucpe_* roles, OTHER otherwise, because this repository's Actions logs are public. No
    resolver run had used #204's unmasked line.
- **This PR, a DRAFT until G1's proof:**
  - **G1 completed:** the resolver job connects only with UCPE_RESOLVER_DB_URL, and the workflow no longer
    references secrets.SUPABASE_DB_URL. That is the design's "remove the resolver from the owner secret's users".
  - **C4 prepared:** the 13 dispatch-only workflows that use the owner URL declare `environment:
    production-db-owner`. Behavior is unchanged until the owner configures it (docs/runbooks/OWNER_URL_ENVIRONMENT.md).
    A test pins the invariant.
  - **One named exception, C4-PIN:** section-5a-evaluation.yml is on the evaluator pin, so its change needs the
    owner's authorization.
- **The D6 design note: SEALED** (.work/roadmap/phase3/d6/D6_DESIGN.md, sha fdbe2ff5…; read-only).
  - The decision: D6 versus the rollback target 17c9c053, which writes as service_role.
  - Recommended, B: D6 only after the next release, so that the rollback target itself uses the pair.
- **E3 is still NOT_YET_LIVE_PROVEN:** 0 natural analyses since the 12:49Z restart (checked 15:29Z).
- **The owner's rulings (2026-10-03), verbatim:** "CONTINUE CURRENT — Opus 5 XHIGH. Rulings: C4-PIN YES; add only the
  production-db-owner environment line to section-5a-evaluation.yml and re-pin it, but do not merge #206 until G1
  natural-run PASS. D6 timing=B after the next release; scope=six core evidence tables + two bundle functions, keep
  SELECT and revoke write/EXECUTE, with deterministic inventory proving no omitted core write surface before freeze.
  Continue all safe prep; no manual resolver dispatch."
- **C4-PIN, done in this PR:**
  - section-5a-evaluation.yml gains only `environment: production-db-owner`;
  - the evaluator pin is re-pinned: closure 23c176a5… → e1ff5f54…. Only the digest changed, the 69 pinned files are
    the same, and the red tests are untouched;
  - 511 evaluation and workflow tests pass. All 14 dispatch-only users of the owner URL are now in the Environment.
- **D6: ruled B** (after the next release). Scope: the six core evidence tables and the two bundle functions; keep
  SELECT, revoke write and EXECUTE.
  - **Its package is MERGED, prepared only:** #207 → main 1a0bfdd4 (the owner's "merge it if exact head is still
    c0dc6e8e…"; push CI and the reproducible build both success).
  - **What it holds:** the draft of migration 0018 and its rollback (scripts/privilege_rehearsal/), and
    scripts/core_write_inventory.py, a deterministic, catalog-only, READ ONLY inventory. Its kinds are T, C, O, F,
    V, R, G and K, run with --expect before or --expect after.
  - **The privilege rehearsal's D1-D4 PASS** on PostgREST v14.18 and v16.4 (run 37135065108):
    - the inventory finds exactly the revoke set, and every planted surface is caught;
    - after the draft no surface remains, SELECT stays, and PostgREST refuses with 42501;
    - the catalog changes by exactly the revoked entries, and the writer SAVES;
    - UP018 on a second application; the rollback is exact.
  - **Application stays BLOCKED** until B's conditions hold, in order: the next release, E3 live-proven, a clean
    production inventory, then freeze and apply. The production inventory needs an owner-dispatched read-only
    route. It belongs in D6's freeze package (the inventory before freeze, then the one-shot apply with the
    inventory after), not before.
- **WB3/S8 (the owner: "WB3/S8 durable recovery/reconciliation design and deterministic local tests where
  dependency-safe"):**
  - **The design: SEALED** (.work/roadmap/phase3/wb3_s8/WB3_S8_DESIGN.md, sha fa58bd24…).
    - R-1a: since W-A, one strict read decides an unknown commit. That is the run as sent (run_id, analysis_hash)
      plus every forecast prediction. Identities only, no payload, no pretended durability.
    - S8, recommended: option 1, accept the honest NOT_SAVED (CIRCUIT_OPEN) for now. The alternatives are
      in-memory replay, or a durable outbox in an independent failure domain such as a private HF dataset.
  - **#208:** the model (api/commit_reconciliation.py, unwired) and 18 deterministic tests; PERS-0's new fault
    lost_before_commit, its scenario S10 and its criterion C6, a gate on rest_rpc.
  - **R-1a's wiring needs the owner:** a strict read in the pinned persistence/repository.py. Today
    SupabaseRestRepository.get_run falls back to its in-memory mirror, which could falsely confirm a commit. The
    wiring then ships with the next release.
Previously (E3 SWITCHED by the owner: the least-privilege writer is CONFIGURED, NOT_YET_LIVE_PROVEN).
**Production code is unchanged: D a2de125f / UCPE-PROD-WA-20261003-A, the guard HEALTHY at R 4130a6cd. The H2-safe
rollback target is 17c9c053.**
- **The owner's message (2026-10-03), verbatim:** "SWITCHED. Verify HF secret metadata by NAME only, Space
  RUNNING/health/build-info, and startup logs read-only; never read secret values or generate analysis traffic.
  Treat the least-privilege writer as NOT_YET_LIVE_PROVEN until the next natural USER_REQUESTED persistence receipt
  proves SAVED as ucpe_api_writer. Do not wait idle for that receipt: continue the highest-value safe UCPE roadmap
  work and record the cutover state accurately."
- **Verified read-only, 2026-10-03T12:57Z** (evidence .work/e3_cutover, sealed; no analysis traffic; no secret value
  read):
  - **the HF secret NAMES**, names only: SUPABASE_PUBLISHABLE_KEY and SUPABASE_WRITER_JWT are PRESENT;
    SUPABASE_SERVICE_ROLE_KEY is kept, because the rollback target uses it;
  - the Space is RUNNING at a2de125f; /healthcheck 200 OK; /v1/build-info 200 UCPE-PROD-WA-20261003-A;
  - **the run logs:** the container started at 12:49:33Z, after the secret changes (the WA deploy was 10:49:56Z).
    Uvicorn's startup completed at 12:49:38Z, with no Traceback or error line. Since then: 0 persistence_receipt
    and 0 analysis_completed events.
- **LEAST_PRIVILEGE_WRITER = CONFIGURED, NOT_YET_LIVE_PROVEN.**
  - **What proves it, passively:** the next natural USER_REQUESTED analysis whose persistence_receipt is SAVED, in a
    container that has both secrets.
    - With both set, the writer sends the pair (apikey = the publishable key; Authorization = the writer JWT). It
      has no service-role fallback. PostgREST runs the request as the token's role, ucpe_api_writer.
    - The receipt's repository field is only the class name. So the proof is that SAVED plus this code path. The
      Supabase API logs (the owner's side) show the role too.
  - **If the receipt is NOT_SAVED or COMMIT_UNKNOWN:** the owner deletes SUPABASE_WRITER_JWT, and the service-role
    writer is back.
  - **The token's expiry:** 30 days after the owner minted it, between #202's merge (11:58Z) and the restart
    (12:49Z), so 2026-11-02 between 11:58Z and 12:49Z. The owner's mint printed the exact time. Renew by
    2026-10-30 (the runbook's step 5).
- **The helper and the runbook: MERGED** (#202 → 38b9860b).
  - PR checks 6/6, including the privilege rehearsal's J1 with the helper's own builder.
  - Push CI 37121324613 and the reproducible build 37121324647: both success.
  - Auto mode refused `gh pr create` ([Data Exfiltration]); the owner ran the one Run action.
- **Next (Claude), while the receipt is awaited:** the highest-value safe roadmap item, prepared only (no credential,
  no database write, no workflow switch). It is the privilege design's resolver cutover: G1, critical, because the
  hourly resolver runs as the table owner.
- **G1, the resolver cutover: PREPARED** (PR #204, head 4b0ff683; ./verify.sh PASS 5556).
  - **scripts/resolver_credential.py** (owner-only; generate, copy-sql, copy-url). From the dashboard's connection URI
    template (with [YOUR-PASSWORD]), it writes owner-only in ~/ucpe-keys:
    - the login SQL, holding PostgreSQL's SCRAM-SHA-256 secret computed client-side, never the password (RFC 7677's
      worked example is reproduced in the tests);
    - the resolver URL, whose user is the role: [ROLE].[PROJECT-REF] through the shared pooler, per Supabase's
      connecting-to-postgres guide.
    Nothing secret is printed.
  - **resolve-outcomes.yml** uses UCPE_RESOLVER_DB_URL once the owner adds it, and SUPABASE_DB_URL until then
    (identical until then). It prints the secret's NAME only.
  - **The resolver prints `resolver_identity role=<current_user>` on stderr** (stdout's two-line contract is
    unchanged), from the status store's new connected_role(). Production runs Route C (status_store=active), so
    the next hourly run's log is the evidence.
  - **The privilege rehearsal** grants every login with the helper's SCRAM secret. R1 logs in through the helper's
    URL builder and refuses a wrong password. Run 37127635969: P1-P8, R1, W1-W10 and J1 all PASS on PostgREST v14.18
    and v16.4.
  - The secrets scanner also watches UCPE_RESOLVER_DB_URL (widened). The owner's steps:
    docs/runbooks/RESOLVER_CUTOVER.md.
  - **Auto mode refused merging #203** ([Merge Without Review]). The owner gets one Run action that merges #203 and
    #204, each on its exact head after its checks.
Previously (E3-A YES and E3-B 30 DAYS ruled; the signing-key helper and the repaired runbook). **Production
is unchanged: D a2de125f / UCPE-PROD-WA-20261003-A, the guard HEALTHY at R 4130a6cd. The H2-safe rollback target is
17c9c053.**
- **The owner's ruling (2026-10-03), verbatim:** "CONTINUE CURRENT. E3-A YES; E3-B 30 DAYS. Before asking the owner
  to create any real credential, repair `WRITER_CUTOVER.md` so the signing-key generation/import format is exact and
  proven against current official Supabase guidance. Prefer `supabase gen signing-key --algorithm ES256` if the CLI
  already exists; otherwise prepare and test a local helper that produces the exact importable private JWK outside
  the repo from the same key used to mint the writer JWT. Create no real key/token yet. Then return one minimal owner
  card with exact UI path, exact command, exact file to import, exact `kid` handling, exact publishable-key location,
  and exact two HF secret names. Never expose any secret value."
- **The import format, from Supabase's own sources (re-read 2026-10-03).** The Supabase CLI is not installed here,
  and was not installed:
  - the CLI's `supabase gen signing-key --algorithm ES256` (supabase/cli develop 28b8aa04a1a5, signing-key.handler.ts)
    prints one private JWK as compact JSON: kty, kid (randomUUID), use, key_ops, alg, ext, d, crv, x, y;
  - the dashboard's "Import an existing private key" box (apps/studio create-key-dialog.tsx) checks kty EC, crv
    P-256 and x, y, d, then sends the object unchanged;
  - the Management API's CreateSigningKeyBody allows exactly those members for ES256, with the kid in UUID format;
  - the signing-keys guide: a token's kid must be the imported kid; claims role and exp; sub an optional UUID.
- **The helper, scripts/writer_signing_key.py (generate, copy-jwk, mint), in this record's PR**
  (feat/e3-writer-signing-key-helper):
  - generate writes the PEM and that exact JWK in ~/ucpe-keys. The folder is 0700 and the files 0600; never inside
    the repository; it never overwrites;
  - copy-jwk and mint first check the two files are one key: the JWK's d, x and y are the PEM's, and OpenSSL computes
    the point from d alone;
  - mint signs the 30-day writer token (role ucpe_api_writer, iat, exp; no sub) with the JWK's kid, to the clipboard.
    Nothing secret is printed;
  - 36 tests, on throwaway keys only: the CLI's members, order and compact JSON; the dashboard's check and the API
    schema; P-256 arithmetic written in the test; `openssl dgst -verify` with the JWK's public half alone; Node's JWK
    import (the crypto the CLI uses);
  - J1 now mints its writer token with the helper's own builder. es256 mints no sub by default, and the scratch kid is
    a UUID;
  - **no real key or token was created.**
- **docs/runbooks/WRITER_CUTOVER.md repaired:** the dashboard's exact labels (Migrate JWT secret → Move to previously
  used → Create Standby Key with "Import an existing private key" → View key details, to check the kid → Rotate
  keys), the publishable key (Project Settings → API Keys), and the two HF secrets.
- **Next: the owner's credential switch**, by the runbook and the one owner card. Claude creates no value.
Previously (UCPE-PROD-WA-20261003-A RELEASED; the chain is complete). **Production is D a2de125f /
UCPE-PROD-WA-20261003-A. The guard is HEALTHY at that pin (R 4130a6cd). The H2-safe rollback target is 17c9c053.**
- **The writer now saves each forecast bundle in ONE transaction** (the run, its detail, the prediction and its
  snapshots: W-A, migration 0017's function). It still uses the service-role key until the owner's switch (E3).
- **The chain** (evidence .work/release_wa, sealed; CHAIN.md):
  - STATE #198 → a6f881c9. It also carries a one-clause fix of a flaky JWKS test from #197.
  - identity #199 → D a2de125f; push CI 37116841080 and the reproducible build 37116841053, both success;
  - the guard on D: run 37116850129, GUARD_VERIFY=PASS 8/8;
  - rollback findings, 17c9c053 over D: 5/5;
  - the re-pin precomputed twice: a4082e59;
  - preflight review and accept: PASS 9/9. The delta is 4 files (analysis_service.py, build_info.py, settings.py,
    repository.py), digest a517aecc….
- **The T4 deploy is CONSUMED** (the owner's one Run action): a fresh preflight (PASS 9/9), then DEPLOY=PASS.
  - It was one fast-forward push, 17c9c05..a2de125 at 10:49:56Z, with no force. Never rerun.
- **After the deploy:**
  - SETTLE=PASS: RUNNING at D after 1 poll; health 200; build-info WA; D's index.html, app.js and styles.css bytes;
    the F1 probe 401 CREDENTIAL_REQUIRED;
  - ROLLBACK_CHECK=PASS 7/7 against the live build: target 17c9c053, every migration after it additive (0016,
    0017);
  - re-pin #200 → R 4130a6cd, equal to the precomputed a4082e59;
  - the guard on R: run 37118169873, GUARD_VERIFY=PASS, pin == live == a2de125f, delta [].
- **The owner's rollback command** (a T4, never automatic):
  `git push --force-with-lease=refs/heads/main:a2de125ffa449cd6f5ec452e4a7a3335286eb413 hf
  17c9c053d420b0f06ee860ff18944660ea407acf:refs/heads/main`. It needs no database change.
- **E3, the credential switch, is at the owner.** The runbook is docs/runbooks/WRITER_CUTOVER.md. Open decisions:
  - E3-A: approve the plan (the owner's offline ES256 key, imported and rotated in; a writer token in the Space,
    never the key);
  - E3-B: the token's lifetime, 30 days (recommended) or 90.
  - Its steps are secret entry, so the owner does them. Claude creates no value.
- **Confirmation in production, observed only:** the next natural USER_REQUESTED analysis logs a persistence_receipt.
  No verification traffic is created.
Previously (the §2.6 package and E3's executable proof MERGED; the release package is next). **The production
app is unchanged: D 17c9c053 / UCPE-PROD-RCPT-20261003-A. Migrations 0016 and 0017 are applied. Main is c909915e, plus
this record.**
- **The §2.6 package (E4 + the W-A client): MERGED** (#196 → b29ef4e4; evidence .work/roadmap/phase3/pr196, sealed).
  - **The pinned crossing** is exactly repository.py and settings.py (E4: "only repository.py+settings.py").
    - The pin closure went af2f2641… → 23c176a5….
    - The 69 pinned files are identical, and the red tests are untouched.
  - **The writer:**
    - With SUPABASE_PUBLISHABLE_KEY and SUPABASE_WRITER_JWT both set, the API key goes in `apikey` and the writer's
      JWT in `Authorization`, so requests run as ucpe_api_writer.
    - Otherwise today's service-role key is used. Half a configuration keeps it, so the transport never switches.
  - **save_forecast_bundle:** one RPC call per forecast bundle, carrying the run and the detail.
    - The separate run upsert is no longer sent on that path: it could overwrite a conflicting stored run.
    - The W-B path stays for writers without the function.
  - **Evidence:**
    - P3-PRIV-R 18/18 on both PostgREST versions. **W10**, the released writer in two-header mode: SAVED through
      one RPC call; run + detail + prediction + snapshot stored; run and prediction conflicts NOT_SAVED with
      nothing changed; service_role SAVED.
    - PERS-0 v3: rest_rpc C1a-C5 PASS. **S9**, a conflicting run, is NOT_SAVED and the stored run is unchanged.
    - VERIFY 5466; mutation 24/24.
- **E3, the supported Supabase signing path, proven by execution: MERGED** (#197 → c909915e; evidence
  .work/roadmap/phase3/pr197, sealed). **J1** ran on a second PostgREST that trusts only a scratch ES256 key with a
  kid, with identical results on v14.18 and v16.4:
  - a short-lived writer token runs as ucpe_api_writer: runs 200, outcomes 403, and production's writer SAVED;
  - an unknown kid, a tampered signature, another key under the same kid, an expired token and the HS256 secret
    are each refused with 401;
  - **a service_role token signed by the same key is accepted (200)**. So the signing key must stay with the owner,
    and only a short-lived writer token ever goes into the Space;
  - not yet proven: the hosted gateway and Supabase's JWKS. That needs the owner's key import, a secret-entry
    boundary.
- **Next (Claude): the release package UCPE-PROD-WA-20261003-A** through the B4 chain, up to the owner's T4 deploy.
  - After that deploy, the writer uses the forecast RPC with the service-role key.
  - Least privilege begins when the owner sets the two new secrets. That is E3's credential plan, an owner step.
Previously (migrations 0016 and 0017 APPLIED in production, and the registry records both). **The production
app is unchanged: D 17c9c053 / UCPE-PROD-RCPT-20261003-A. The database now has the least-privilege roles and the
forecast bundle RPC. Main is 8cbfdbc3, plus this record.**
- **The T4 applies are CONSUMED.** The owner, in chat on 2026-10-03, wrote "please run this instead:", followed by the
  exact command. Claude ran it once, unmodified. Evidence: .work/t4_0016_0017 (COMMAND.sh, RAW_OUTPUT.txt, both
  reports, ADJUDICATION.md), with its MANIFEST sealed.
  - **0016: run 37110330500**, APPLIED and committed, at 8cbfdbc3, on PostgreSQL 17.6.
    - The route's own verdicts, re-run on the raw rows: pre [] and post [].
    - The CREATEROLE path. The four roles have no power. The writer is in authenticator (SET, no INHERIT).
      40 policies.
    - The bundle RPC is now SECURITY DEFINER of ucpe_bundle_owner (EXECUTE: service_role, the writer, its owner).
      Its body is unchanged.
    - **F1/UOR:** ucpe_space_db holds exactly the registry read and the ledger read, insert and update.
  - **0017: run 37110375659**, APPLIED and committed. Re-adjudicated: pre [] and post [].
    - save_forecast_bundle is exactly as reviewed: SECURITY DEFINER of ucpe_bundle_owner (EXECUTE: service_role,
      the writer, its owner).
    - The owner gained INSERT and SELECT on runs and details. Policies 40 → 44. Everything else is unchanged.
  - **Never re-dispatch either workflow.**
- **The registry** (this record) records 0016 = 37110330500 and 0017 = 37110375659. No migration is unapplied, so release
  check 5c allows a release again.
- **Live effect, by design:** nothing existing was revoked. The live writer (service_role) keeps executing the bundle
  RPC, now as its definer (P6, PERS-0). It is observed only passively, through the next natural persistence_receipt.
  No verification traffic is created.
- **Next (Claude):** the §2.6 package (E4 plus the W-A client) and E3's executable proof. Then the release, up to its T4.
  Claude creates no credential value.
Previously (migrations 0016 and 0017 MERGED with their one-shot T4 packages; NOTHING IS APPLIED). **Production
is unchanged: D 17c9c053 / UCPE-PROD-RCPT-20261003-A, guard HEALTHY. Main is a53c50b0, plus this record.**
- **The owner's rulings (2026-10-03), verbatim:** "E1 YES W2; E2 DEFER—do not inspect/expose SUPABASE_DB_URL; E3 YES
  in principle after proving the supported Supabase JWT/signing path; E4 YES only repository.py+settings.py; WB1 YES
  after 0016; WB3 YES later with S8. Build/rehearse migration 0016 and its one-shot T4 package, preserving corrected
  F1/UOR grants. Then prepare 0017/WB1; create no credential values yet. Auto remains default; return only at exact
  T4, secret-entry, security conflict, or failure boundary."
- **Migration 0016, the least-privilege roles (E1, W2): MERGED** (#192 → 77dbe59e; evidence
  .work/roadmap/phase3/pr192, sealed). Main push CI 37106452298 and the reproducible build 37106452296: success.
  - migrations/0016_least_privilege_roles.sql (sha256 5d89f5bd…) is P3-PRIV-R's rehearsed statements, byte for byte.
  - **The one-shot route** is scripts/apply_migration_0016.py (lock 5000016, token APPLY-MIGRATION-0016-ONCE). Its
    trust machinery is 0011's, verbatim.
    - Pre-checks:
      - PostgreSQL 16 or later, and authenticator exists;
      - the applier holds CREATEROLE (or SUPERUSER) and schema public's owner privileges, and owns every table;
      - the bundle RPC is exactly 0015's;
      - none of the four roles or 40 policies exists (otherwise "not a first apply").
    - Post-checks:
      - the four roles have no power at all;
      - the only new memberships are authenticator → writer (SET, no INHERIT) and PG16's creator ADMIN grants;
      - the table, sequence and schema grants are exact, with the 40 policies;
      - the bundle RPC is SECURITY DEFINER of ucpe_bundle_owner, with its body, search_path and EXECUTE list as
        reviewed;
      - everything else is unchanged.
  - **Evidence:**
    - the rehearsal on scratch PostgreSQL 16.15: APPLIED, then a second apply refused, then the probe PASS;
    - PERS-0 on 0001-0016: PASS;
    - P3-PRIV-R P1-P8 and W1-W9: PASS on PostgREST v14.18 and v16.4;
    - mutation 20/20.
  - **F1/UOR (Correction 01) is preserved:** ucpe_space_db holds SELECT on automation_credential and INSERT, SELECT and
    UPDATE on automation_radar_ledger. The route, the probe and P4 each assert it.
- **Migration 0017, the forecast bundle RPC (WB1, W-A): MERGED** (#193 → a53c50b0; evidence
  .work/roadmap/phase3/pr193, sealed).
  - migrations/0017_forecast_bundle_rpc.sql (sha256 53591dfa…) is the rehearsed draft, byte-identical from `DO $$` on.
    The draft is retired. P3-PRIV-R now applies the migration itself, plus rollback_0017.sql.
  - **The one-shot route** is scripts/apply_migration_0017.py (lock 5000017, token APPLY-MIGRATION-0017-ONCE). Its trust
    machinery is 0011's, verbatim; its checks are 0016's reviewed SQL plus the new function's.
    - Pre-checks:
      - 0016 is applied exactly: roles, memberships, grants, schema rights, the 40 policies and the bundle RPC;
      - the applier holds ADMIN on ucpe_bundle_owner (or SUPERUSER) and schema public's rights, and owns every table;
      - none of 0017's objects exists (otherwise "not a first apply").
    - Post-checks:
      - save_forecast_bundle is exactly as reviewed: SECURITY DEFINER of ucpe_bundle_owner, its fixed search_path, its
        body;
      - its EXECUTE list holds the owner, the writer and service_role, and never PUBLIC, anon, authenticated, the
        resolver or the Space role;
      - ucpe_bundle_owner gains exactly INSERT and SELECT on analysis_runs and analysis_run_details;
      - there are 44 policies, and everything else is unchanged.
  - **Evidence:**
    - the rehearsal on scratch PostgreSQL 16.15, built from 0001-0016: APPLIED, then a second apply refused for three
      reasons, then the probe PASS;
    - PERS-0 on 0001-0017: PASS;
    - P3-PRIV-R 17/17 PASS on both PostgREST versions, applying the migration's own bytes;
    - mutation 29/29; VERIFY=PASS 5382.
- **Registry:** 0016 and 0017 are additive and unapplied (applied_run null). Release check 5c therefore blocks every
  release until both are applied and recorded. No release is pending.
- **E3, the supported Supabase path** (Supabase's docs, re-read 2026-10-03; nothing was created):
  - **Minting your own JWT** (the signing-keys guide): import a private key, which starts in standby; rotate it in;
    then sign with alg ES256, its kid, and the claims role and exp (sub is optional). The guide says to prefer
    shorter-lived tokens. Previously used keys stay trusted until revoked, so the legacy keys keep working through a
    rotation.
  - **Custom roles** need `grant <role> to authenticator`. Migration 0016 does exactly that, for ucpe_api_writer only.
  - **The new API keys** (sb_publishable_, sb_secret_) are not JWTs and go only in `apikey`. A secret key still maps
    to service_role (BYPASSRLS), so it is not least privilege by itself (G4).
  - **Supabase deprecates the legacy anon and service_role keys by the end of 2026.** Today's REST client sends one
    key in both `apikey` and `Authorization`, which a secret key cannot do. **E4's two-header change is needed before
    that date regardless.**
  - **Caveat:** the JWT guide no longer recommends overriding the Authorization header in Supabase *clients* that also
    carry an Auth session. UCPE's writer is a server-side httpx client with no Auth session.
  - **Not yet proven by execution:**
    - ES256 + kid through a real PostgREST (provable in CI, with scratch keys);
    - the hosted gateway accepting a publishable key plus the writer JWT (this needs the owner's key import).
  - **For the credential plan:** the signing key must never sit in the Space. It can sign any role, service_role
    included. A pre-minted, short-expiry writer JWT carries only ucpe_api_writer.
Previously (W-A REHEARSED and merged; WB1 is now evidence-backed). **Production is unchanged: D 17c9c053 /
UCPE-PROD-RCPT-20261003-A, guard HEALTHY. Main is 53e83537.**
- **W-A, the whole §8.1 core bundle in ONE transaction: REHEARSED** (#190 → 53e83537; evidence
  .work/roadmap/phase3/pr190, sealed).
  - **The draft of migration 0017** (scripts/privilege_rehearsal/, outside migrations/):
    public.save_forecast_bundle. It inserts or compares the run (on every column but persistence_status) and the
    detail, then calls 0015's unchanged save_prediction_bundle. Any refusal rolls back the run and the detail.
    - It is SECURITY DEFINER, owned by ucpe_bundle_owner (W2), with INSERT and SELECT only (never UPDATE).
    - EXECUTE: the writer and, until D6, service_role.
  - **Criteria W1-W9, all PASS on PostgREST v14.18 and v16.4** (P1-P8 unchanged, PASS):
    - W2: all four parts stored in one call; W3: an identical replay changes nothing;
    - W4 and W5: run and detail conflicts refused, with nothing written;
    - W6: a CHECK failure inside, or a refusal inside 0015, keeps nothing, the run and the detail included;
    - W7: 22023;
    - W8: every caller but the writer refused;
    - W9: one-shot (UP017), and the rollback is exact.
  - **Static mutation:** 12/12.
  - **WB1 now means:** promote this rehearsed draft to migration 0017 (after 0016, with the same §2.6 crossing as E4).
Previously (RCPT RELEASED). **THE THREE-STATE RECEIPTS AND W-B ARE LIVE. Production is D 17c9c053 /
UCPE-PROD-RCPT-20261003-A. The guard is HEALTHY at that pin (R 06e4733e). The H2-safe rollback target is f046140b.**
- **The chain** (evidence .work/release_rcpt, sealed; CHAIN.md):
  - STATE #186 → ac7cd4a1;
  - identity #187 → D 17c9c053, then push CI 37062479974 and the reproducible build 37062479904, both success;
  - the guard on D: run 37062503316, GUARD_VERIFY=PASS;
  - the rollback findings, f046140b over D: 5/5;
  - the re-pin precomputed twice: c7a5591e;
  - preflight review and accept, PASS 9/9: the delta is 3 files (analysis_service.py, build_info.py, events.py),
    digest 70259379…; 5b and 5c PASS.
- **The T4 deploy is CONSUMED.** The owner ran the one chained Run action: a fresh preflight (PASS 9/9), then
  DEPLOY=PASS. That was a single fast-forward push, f046140..17c9c05 at 2026-10-03T04:47:03Z, with no force.
  Never rerun.
- **After the deploy:**
  - SETTLE=PASS: RUNNING at D after 1 poll, health 200, build-info RCPT, D's index/app.js/styles.css bytes, the
    F1 probe 401 CREDENTIAL_REQUIRED;
  - ROLLBACK_CHECK=PASS 7/7 against the live build: target f046140b, no migration after it;
  - re-pin #188 → R 06e4733e, equal to the precomputed c7a5591e;
  - the guard on R: run 37098323783, GUARD_VERIFY=PASS, pin == live == 17c9c053, delta [].
- **The owner's rollback command** (a T4, never automatic):
  `git push --force-with-lease=refs/heads/main:17c9c053d420b0f06ee860ff18944660ea407acf hf
  f046140b121d4e4ed8969e58d3c137538b661725:refs/heads/main`. It needs no database change.
- **Confirmation in production, observed only:** the next natural USER_REQUESTED analysis logs a
  persistence_receipt carrying receipt and receipt_reason. No verification traffic is created.
- **Still open (Phase 3), for the owner:**
  - E1-E4: the privilege design, rehearsed;
  - WB1: W-A, the atomic wider bundle (migration 0017 plus §2.6);
  - WB3: R-1 with S8.
Previously (Phase 3: the privilege rehearsal MERGED and PASSING; W-B MERGED; the wider-bundle design
SEALED; the receipts + W-B release package next, up to the owner's T4). **Production is unchanged: D f046140b /
UCPE-PROD-B9-20261002-A, guard HEALTHY. Main is 99908969.**
- **Item 1, the privilege rehearsal (P3-PRIV-R): MERGED** (#184 → 84280b6c; evidence .work/roadmap/phase3/pr184,
  sealed).
  - **What is rehearsed:**
    - the DRAFT of migration 0016 (scripts/privilege_rehearsal/, outside migrations/, so release check 5c ignores
      it): design C1-C3 with W2 and Correction 01;
    - its rollback;
    - a harness that runs production's own code under each role, on scratch PostgreSQL 16.15 behind a real
      PostgREST (v14.18 and v16.4, each a release binary checked against its sha256).
  - **The criteria, all PASS on both versions:**
    - P1, the exact matrix (40 policies);
    - P2, the REST runtime as ucpe_api_writer: SAVED, read back, replay SAVED, conflict NOT_SAVED;
    - P3, 18 out-of-list requests and 5 foreign-role JWTs refused (403/42501), anon 401;
    - P4, calibration and F1 24/24 as ucpe_space_db;
    - P5, the resolver;
    - P6, the API roles unchanged and service_role still SAVED;
    - P7, the second application refused (UP016);
    - P8, the rollback restores the catalog exactly.
  - **Non-vacuity:** relation ACL entries 219 → 261 → 219. The 42 added equal the design's grant count.
  - **Static mutation:** 14/14.
  - **Production runs PostgreSQL 17.6.** MAINTAIN is checked only from 17, so the 0016 apply route will check the
    live catalog itself.
- **Item 3, the wider §8.1 bundle: design SEALED** (.work/roadmap/phase3/WIDER_BUNDLE_DESIGN.md, sha f6c62371…).
  - W-A, the atomic RPC with the run identity and the detail in one transaction (migration 0017 plus §2.6): the
    recommended end state, for the owner (WB1).
  - W-B, the interim honest receipt: MERGED.
  - R-1, the COMMIT_UNKNOWN reconciliation: deferred with S8 (WB3).
- **W-B: MERGED** (#185 → 99908969). The required detail joins the persistence work and is written before the
  bundle. SAVED now needs the run identity and that detail confirmed:
  - unconfirmed gives COMMIT_UNKNOWN (RUN_UNCONFIRMED / DETAIL_UNCONFIRMED);
  - a detail never sent gives NOT_SAVED (INCOMPLETE_BUNDLE).
  - Its evidence: PERS-0 rest_rpc C1a-C5 PASS, and the privilege rehearsal P1-P8 PASS ×2, with the detail now
    inside P2. Mutation 10/10.
- **Not live yet:** the receipts (#182) and W-B ship together as release UCPE-PROD-RCPT-20261003-A.
Previously (Phase 3 resumed: three-state receipts MERGED; the privilege audit and design SEALED; the
privilege rehearsal next). **Production is unchanged: D f046140b / UCPE-PROD-B9-20261002-A, guard HEALTHY. Main is
43d5b543.**
- **The owner's instruction** (2026-10-02, verbatim excerpt): "Resume Phase 3. Priority: (1) privilege/role design,
  (2) three-state receipts, then wider §8.1 bundle; S8 stays later." Also: "Do not treat replacing legacy
  service_role with a new Supabase secret key as least privilege by itself."
- **Item 1, the privilege audit and role design: SEALED, read-only**
  (.work/roadmap/phase3/PRIVILEGE_AUDIT_AND_DESIGN.md, sha 2d6a80f0937a8f0c…). No secret was read, no database was
  contacted, nothing changed.
  - **The gaps:**
    - G1, critical: the hourly resolver and the collectors run as the table owner (migration authority);
    - G2, high: the role behind the Space's SUPABASE_DB_URL. Correction 01 infers it is owner-level: no migration
      grants the automation tables to any role, yet the live F1 ledger works. Only the owner can confirm it;
    - G3, high: the REST runtime is service_role (BYPASSRLS plus ALL) and can write labels and core rows outside
      the bundle RPC;
    - G4: a new sb_secret_ key still maps to service_role. It improves rotation, not privilege.
  - **The design:**
    - C1: ucpe_api_writer, reached through authenticator by a writer JWT. Option W2: the bundle RPC becomes SECURITY
      DEFINER, owned by a NOLOGIN ucpe_bundle_owner, so the runtime has no direct INSERT path to core evidence;
    - C2, corrected: ucpe_space_db. The Space's DB URL also serves the live F1/UOR registry and ledger, so C2 must
      keep SELECT on automation_credential and SELECT, INSERT and UPDATE on automation_radar_ledger;
    - C3: ucpe_resolver;
    - C4: the owner URL is kept only in a protected GitHub Environment.
  - **The order** D1-D6: 0016 (additive) → credentials → the resolver cutover → the reader cutover → the writer
    cutover (§2.6 plus a release) → revoke the excess.
  - **Owner decisions E1-E4:** 0016's scope (W2 or INVOKER); the Space DB_URL role; the credential plan; the §2.6
    crossing of repository.py and settings.py for the two-header writer.
  - **Correction 01** (.work/roadmap/phase3/PRIVILEGE_DESIGN_CORRECTION_01.md, sha d036173f…, sealed): the sealed
    design called the F1 route OFF. It has been ON since F1-ENABLE-A (2026-10-01): the settle probe got 401, not
    503. Its C2 role would have broken F1/UOR. Corrected before any rehearsal or apply.
- **Item 2, three-state receipts: MERGED** (#182, head 59244b9a, 9/9 green → main 43d5b543). Two free files,
  api/analysis_service.py and telemetry/events.py. No pinned file and no migration.
  - **The receipt values:**
    - SAVED only for a complete bundle confirmed stored;
    - NOT_SAVED when it is known not stored: CIRCUIT_OPEN, CONFLICT, INCOMPLETE_BUNDLE, NO_DURABLE_STORE,
      NOT_ATTEMPTED;
    - COMMIT_UNKNOWN whenever an attempted write is unconfirmed: NO_CONFIRMATION, UNCONFIRMED_EXCEPTION;
    - several bundles report the least certain one. The receipt is added to the persistence_receipt event.
  - **The evidence** (.work/roadmap/phase3/pr182, sealed):
    - PERS-0 run 37049183159 adds criterion C5, "no false receipt". **rest_rpc: C1a-C5 all PASS.** Re-derived from
      the raw observations: 0 false receipts, the receipts exactly as expected (report 1bacc208…);
    - the postgres route (not production's) fails C5 on S5 only: data, the same defect as its C1b and C3;
    - locally: VERIFY 5030; mutation 10/10.
  - **Not live:** production f046140b does not carry it. A release (T4) ships it.
  - **Recorded, not claimed:** plan §8.1's "COMMIT_UNKNOWN is reconciled by idempotent read/retry logic". The RPC is
    idempotent (S7b: an identical replay is SAVED), but no automatic reconciliation runs. It meets the circuit
    breaker and S8 (later).
Previously (B9 RELEASED). **B9 IS LIVE. Production is D f046140b / UCPE-PROD-B9-20261002-A. The REST writer
now persists each forecast bundle through migration 0015's RPC, in one transaction. The guard is HEALTHY at that pin
(R 7f2b26e1). The H2-safe rollback target is bc90e69b.**
- **The chain** (evidence .work/release_b9, sealed: 153 files, manifest ded617aa…):
  - registry #178 → main 157daf3d (0015 applied_run);
  - identity #179 → D f046140b, then push CI, the reproducible build and the guard on D all PASS;
  - the rollback binding bc90e69b over D: 5/5;
  - the re-pin precomputed twice: c8560980;
  - preflight PASS 9/9: the delta is 3 files (analysis_service.py, repository.py, build_info.py), digest 433a36d5…;
    check 5c PASS.
- **T4-2, the deploy, is CONSUMED.**
  - The auto-mode classifier refused Claude's deploy ([Production Deploy]).
  - The owner ran the one chained Run action: a fresh preflight (PASS 9/9), then DEPLOY=PASS, fast-forward
    bc90e69..f046140, no force. Never rerun.
- **After the deploy:**
  - SETTLE=PASS: RUNNING at D, health 200, build-info B9, D's index/app.js/styles.css bytes, the radar probe 401
    CREDENTIAL_REQUIRED;
  - ROLLBACK_CHECK=PASS 7/7 against the live build: target bc90e69b; 0015 is additive;
  - re-pin #180 → R 7f2b26e1, equal to the precomputed c8560980;
  - GUARD_VERIFY=PASS on R: run 37043734896, HEALTHY ×3, pin == live == f046140b, delta [].
- **The owner's rollback command** (a T4, never automatic):
  `git push --force-with-lease=refs/heads/main:f046140b121d4e4ed8969e58d3c137538b661725 hf
  bc90e69be9b948e5dc6c1e8b78e6ea0d345c6b42:refs/heads/main`. It needs no database change: bc90e69b never calls the
  RPC.
- **Confirmation in production, observed only:** the first natural USER_REQUESTED analysis will log a
  persistence_receipt from SupabaseRestRepository with the bundle's outcome. No verification traffic is created.
- **Phase 3 residuals (not closed by B9):**
  - three-state receipts;
  - the privilege rehearsal and role design (the Space keeps the full-privilege service-role key);
  - the wider §8.1 core bundle;
  - S8 durable recovery (an owner item);
  - the direct-Postgres writer unchanged (not production's).
Previously (B9-REST merged; migration 0015 APPLIED; the B9 release is next). **B9 (plan §8.1) is built as
the owner ruled (RD-1 = R1), MERGED (#177 → main c9637469), and its database half is APPLIED to production. The
production app is unchanged (bc90e69b) until the release (T4-2).**
- **The owner's ruling RD-1 = R1** (2026-10-02, verbatim excerpt): "preserve the production REST writer; do not cut HF
  runtime over to direct Postgres. Implement B9 as the minimum REST atomic-bundle route: migration 0015 exposes one
  tightly scoped POST RPC that atomically persists prediction + required snapshots, distinguishes identical replay
  from conflicting same-ID content, and rolls back the whole bundle on any failure."
- **What #177 merged** (head de5699dc; merge c9637469; 9/9 checks green):
  - **migrations/0015**: one function, public.save_prediction_bundle(jsonb, jsonb, jsonb):
    - SECURITY INVOKER, search_path=pg_catalog, pg_temp, EXECUTE for service_role only;
    - one transaction: insert, or compare column by column (IDENTICAL_DUPLICATE or CONFLICT); any CONFLICT rolls
      back everything the call wrote ("refused": true);
    - strict keys; OOS ids and snapshots of another prediction refused; no table change.
  - **§2.6, the one pinned file persistence/repository.py**: SupabaseRestRepository.save_prediction_bundle makes ONE
    RPC POST, with a strict answer reader.
    - The pin closure 3ffc21e9… → af2f2641b3bcdc9b8269981cde174d3e4dfc817d52bc58ae00421bb8038ddc69, and only the
      closure changed.
    - The 69 files and the red tests are untouched.
  - **api/analysis_service.py**: non-OOS bundles go through the RPC. A CONFLICT is never acknowledged; OOS rows and
    the other writers keep their per-row path.
  - **PERS-0 gains the rest_rpc route**: PostgREST-compatible, gated by --require-route rest_rpc.
  - **The 0015 one-shot route**, its rehearsal, the registry entry, and release preflight check 5c (no release while
    a migration is unapplied).
  - F1/UOR artifacts unchanged.
- **The evidence**, adjudicated from the raw reports (.work/roadmap/b9/pr177, sealed):
  - PERS-0 run 37016859049: **rest_rpc C1a, C1b, C2, C3 and C4 all PASS**, re-derived CONSISTENT;
    - privileges: invoker, service_role-only EXECUTE, the fixed search_path;
    - refusals: anon and authenticated 42501; malformed bundles unavailable; 0 rows written;
    - the postgres route (not production's writer, unchanged) still C1b and C3 FAIL: data.
  - The 0015 rehearsal run 37016859295: PASS, with the second apply refused.
  - Locally: VERIFY 5005; mutation 14/14.
- **T4-1, the 0015 apply, is CONSUMED.**
  - Auto refused Claude's dispatch ([Production Deploy]); nothing ran then.
  - The owner ran the one frozen Run action: apply-migration-0015.yml, run 37033014490, attempt 1, at c9637469.
  - APPLIED and committed on PostgreSQL 170006. The independent adjudication PASSED 37/37 (.work/t4_0015, sealed):
    - one new function, exactly as reviewed, EXECUTE for service_role only;
    - every other catalog item unchanged;
    - the in-run rehearsal REHEARSED, with its second apply refused.
  - Never rerun.
  - This record also writes the registry: 0015 applied_run 37033014490.
- **Phase 3 residuals, verified separately and not claimed closed:**
  - B9 closes C1b and C3 for the production (REST) transport only once the release ships.
  - Still open:
    - three-state receipts (SAVED / NOT_SAVED / COMMIT_UNKNOWN);
    - the privilege rehearsal and role design (the Space still holds the full-privilege service-role key);
    - the wider §8.1 core bundle (run summary and detail sit outside the bundle);
    - durable recovery of circuit-open drops (S8, an owner item);
    - the direct-Postgres writer is unchanged (not production's).
Previously (M1 CONFIG_PROVEN: the writer is REST; the B9 routing decision RD-1). **M1 is resolved
read-only, by configuration: production's analysis writer is `SupabaseRestRepository` (CONFIG_PROVEN). No runtime
receipt is claimed. D2's condition is not met, so the Postgres B9 is not implemented. One owner decision remains:
RD-1. Production is unchanged (bc90e69b).**
- **M1's evidence.** The method used the HF API's Space secret and variable metadata, with the existing local
  token used in place. It printed booleans only.
  - SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY and SUPABASE_DB_URL are all present as Space secrets. No value field
    was returned.
  - All three are absent as variables, and all were configured before the running container started.
  - The canonical selection at main 9e997f0a is byte-identical at the deployed bc90e69b: create_app →
    build_persistence_repository → REST when both REST keys are set.
  - **The residual:** secret values are write-only, so an empty REST secret would select Postgres. Nothing
    indicates that.
  - Record: .work/roadmap/b9/M1_CONFIG_PROOF.md (sha256 2a92fe30…).
- **Plan §8.3's capability metadata is now:**
  - writer: REST (config-proven);
  - evidence reader: direct Postgres. Reads are runtime-proven (H2 smoke); writes through the Space's DB URL have
    never been exercised;
  - resolver: direct Postgres (the workflow requires secrets.SUPABASE_DB_URL).
- **PERS-0 measured the Postgres transport, not production's.** By code reading, unmeasured, the REST writer has
  the same C1b and C3 gaps: one POST per row, and predictions ignore-duplicates.
- **RD-1** (.work/roadmap/b9/B9_REST_DECISION.md, sha256 c7ec1347…):
  - **R2a, recommended:** route the writer to direct Postgres, in this order:
    1. an owner-run, catalog-only privilege check of the Space DB URL's role, against the writer's exact
       table/privilege list;
    2. D2 re-issued for the Postgres variant, then its release;
    3. the owner deletes SUPABASE_SERVICE_ROLE_KEY from the Space. No routing code changes.
  - **R1:** keep REST and add an RPC function: migration 0015, a REST-variant §2.6 and two T4s.
- **The log watcher** stopped at its 2-hour limit (10:07Z), 39 reads with 0 receipts. It is not restarted.
  - The owner withdrew the "run one analysis" action: it would be verification traffic, never USER_REQUESTED.
Previously (the owner's D1-D4 guidance; M1 pending; S8 verified; the D4 classification note). **The owner
answered the decision pack (2026-10-02; verbatim in OWNER_BOUNDARY):
- D1: resolve M1 read-only from the Space logs.
- D2: B9 is approved ONLY IF D1 proves SupabasePersistenceRepository.
- D3: NO FOR NOW.
- D4: HOLD behind a classification note.
M1 is NOT yet resolved: no analysis has run since the OBS-2 restart, so the logs hold no persistence_receipt.
Nothing pinned has changed. Production is unchanged: bc90e69b / UCPE-PROD-OBS2-20261002-A.**
- **CORRECTION (loud):** the decision pack named the REST class "SupabaseRestPersistenceRepository". No such class
  exists.
  - The REST writer is `SupabaseRestRepository` (repository_type SUPABASE_REST).
  - The Postgres writer is `SupabasePersistenceRepository` (SUPABASE_POSTGRES).
  - The old line below is annotated.
- **M1 (D1), read-only.** The existing local Hugging Face login was used in place, never printed or inspected.
  - The Space run logs (the container started 2026-10-02T05:59:32Z) answered HTTP 200 to 10 bounded reads
    (07:29Z-08:07Z).
  - persistence_receipt events: 0. Only http_request events appear, so no analysis was served.
  - **The evidence on record does not settle M1:**
    - the H2 smoke proved that the skill-evidence *reader* runs on direct Postgres;
    - but the *writer* prefers REST (SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY), and RELEASE_GATE's secrets table
      names REST.
  - **The one owner action:** run one analysis in the app (any symbol; signing in is the owner's). A bounded
    background reader then extracts only the receipt's repository class.
- **S8 against §23 (verified, read-only):** the circuit-open drop violates no §23 criterion and no Phase 3 exit
  criterion. It is an honestly reported NOT_SAVED:
  - no commit is attempted, and nothing is acknowledged;
  - when the circuit is open at request time, the badge reads "Storage unavailable — this analysis is not being
    retained".
  - **So durable reconciliation of drops is not a deferred acceptance criterion.** It would need an outbox (a
    migration and a T4); it stays an open availability limitation for the owner.
  - **B9 closes C1b and C3 only. Phase 3 is NOT complete after B9.** Still open: three-state receipts
    (SAVED / NOT_SAVED / COMMIT_UNKNOWN), M1, the privilege rehearsal and the role design.
  - Also stated: the run summary, timeframe, provider and news rows stay outside the bundle, as today. A failed
    bundle can leave them without a prediction, never acknowledged. Plan §8.1's full core bundle would be a
    further widening.
  - Record: .work/roadmap/b9/S8_SECTION23_VERDICT.md.
- **B9 is designed for both D1 outcomes** (.work/roadmap/b9/B9_DESIGN.md):
  - A, Postgres: D2's exact scope;
  - B, REST: R1, an RPC function plus migration 0015; or R2, route the writer to direct Postgres. R2(b) is
    recommended; it widens D2 and needs a ruling.
- **D4 (HOLD): the no-execution classification note is SEALED.** .work/roadmap/d4/D4_CLASSIFICATION_NOTE.md, sha256
  9cde2f1e95af2450ad08d86073de2ecb8d508a8e5f32257724ecff2da2fcbc51.
  - Verdict CLASSIFIED_OUTSIDE, provable from the governing records. The dataset is outside F3, §5A, every
    protected or sealed span and every consumed lane:
    - Binance Spot 1h klines, BTCUSDT and ETHUSDT;
    - UTC days 2024-08-21 → 2025-04-13 (236 days), strictly inside the governing admissible calendar
      [2024-08-20T09:30Z, 2025-04-14T00:00Z);
    - exactly 62 data.binance.vision archive files plus 62 official checksums, listed in
      .work/roadmap/d4/D4_FILE_LIST.txt (124 URLs, sha256 2df697de…).
  - The span is seen/mined DEV, never fresh: a run may measure FEAS-1 item (d), never confirm.
  - Nothing was fetched. The run needs the owner's own authorization. F3 stays KEEP_UNSPENT.
- **D3:** NO FOR NOW. UX-1 stays held. The F1/UOR examples and the analysis_hash goldens are not regenerated.
Previously (PERS-0 measured; the owner decision pack D1-D4). **PERS-0 (plan §22 item 7) is MERGED (#173 →
c386acd5) and adjudicated. The current Postgres writer under injected faults, on scratch PG built from 0001-0014:
C1a PASS, C1b FAIL, C2 PASS, C3 FAIL, C4 PASS. The critical path (B9, Phase 3) now waits only on owner decisions.
Production is unchanged: bc90e69b / UCPE-PROD-OBS2-20261002-A.**
- **PERS-0:** run 36973936528, REPORT_CONSISTENT (the criteria re-derived from the raw observations). Record:
  .work/roadmap/pers0/PERS0_RECORD.md (sealed).
  - C1b FAIL: a crash or a lost response between the prediction and snapshot writes leaves a prediction without
    its snapshot (S2, S7a). It is reported UNAVAILABLE, never OK.
  - C3 FAIL: a conflicting prediction retry is acknowledged OK (ON CONFLICT DO NOTHING, no comparison; S5), and the
    stored row stays the original. A conflicting snapshot is refused (S6).
  - C1a, C2 and C4 PASS. S8: after one failure, the open circuit drops the next bundle entirely.
  - Scope: the Postgres transport only; production's transport is UNKNOWN (M1).
- **The B9 proposal** (design only; NOT implemented, because pinned files need prior authorization):
  - persistence/repository.py gains save_prediction_bundle(prediction, feature snapshot, derivatives snapshot):
    ONE transaction (all or nothing);
  - the prediction's conflict is detected by comparing stored and incoming content: IDENTICAL_DUPLICATE or
    CONFLICT, as the snapshot path already does. No migration;
  - _persist_work_confirmed uses it when present;
  - the evaluator pin is regenerated, red tests are untouched, and the §2.6 RECORD is written (as for 35545f4d);
  - durable reconciliation of circuit-open drops (S8) is a later step and needs a table.
- **M1 is now one log line:** OBS-1 is live, so every persistence_receipt event in the Space logs carries
  repository=<class>: SupabasePersistenceRepository (Postgres) or SupabaseRestPersistenceRepository (REST)
  [WRONG NAME, corrected 2026-10-02: the REST class is SupabaseRestRepository].
Previously (REL-1 and OBS-2 merged; the OBS-2 release; UX-1 still held). **OBS-2 IS LIVE. Production is D
bc90e69b / UCPE-PROD-OBS2-20261002-A, and the guard is HEALTHY at that pin. The H2-safe rollback target is 51a15fd0.**
- **REL-1** #168 → 5cfd60d4 (release tooling): preflight check 5b refuses a changed app.js or styles.css under its
  old ?v= token. The asset-token test is conditional on a pending frontend delta. Mutation 4/4.
- **OBS-2** #169 → 4b3fb592 (plan §9.4):
  - per-stage analysis timings (provider, quant, gate, news, present, total) in analysis_completed, through
    CURRENT_STAGE_MS;
  - the payload is unchanged: the analysis_hash golden and the F1 examples pass untouched;
  - mutation 5/5.
- **The OBS-2 release:** identity → D bc90e69b (UCPE-PROD-OBS2-20261002-A).
  - B3 REPRODUCIBLE=PASS (sha256:19c741a79496…) + SMOKE=PASS.
  - The guard on D: PASS (run 36971213769).
  - The rollback target 51a15fd0: PASS, local.
  - The re-pin precomputed: fa9f99b3.
  - The runtime delta reviewed: digest 70259379…; preflight PASS.
- **Deploy, settle, live checks, re-pin #171 → R 904fb048**: GUARD_VERIFY=PASS (run 36971940072).
  Main R: CI success (run 36971919795); reproducibility PASS (run 36971919733).
- **UX-1** stays HELD (the F1/UOR artifact boundary, the owner's Q1).
Previously (SEC-1 RELEASED; UX-1 held for an owner ruling; REL-1 next). **SEC-1 IS LIVE. The owner ran
the one Run action: PREFLIGHT=PASS 7/7, then DEPLOY=PASS, 46a1de6..51a15fd with no force, consumed. Production is
D 51a15fd0 / UCPE-PROD-SEC1-20261002-A, and the guard is HEALTHY at that pin. The H2-safe rollback target is
46a1de68.**
- **SETTLE=PASS** at 04:38:44Z:
  - RUNNING at D, healthcheck 200;
  - build-info UCPE-PROD-SEC1-20261002-A with its fingerprint; the frontend bytes are D's;
  - F1 answers 401 CREDENTIAL_REQUIRED.
- **Live, read-only checks:**
  - CSP, nosniff, no-referrer and no-store are on / and /v1/build-info;
  - a cross-site login is refused with 403 CROSS_SITE_REFUSED;
  - in a real browser, the live UI loads with every asset at 200, and the only console entry is the expected
    pre-login 401;
  - the huggingface.co Space page renders the embedded app: no frame-ancestors or CSP error.
- **ROLLBACK_CHECK=PASS 7/7** against live production D: 46a1de68 keeps the H2 hold, and no migration follows it.
- **The re-pin** #167 = 258b969c, exactly as precomputed, → **R 504ddd5d**.
  - GUARD_VERIFY=PASS 8/8 (run 36966123856): HEALTHY x3, hf = pin = D, live = intended = SEC1, delta [].
- **Main R:** push CI success (run 36966111025); reproducibility PASS (run 36966111011).
- **UX-1 HELD, for an owner ruling on F1/UOR artifacts.**
  - Its backend explanation copy changes the analysis payload. That changes the analysis_hash goldens and the
    committed F1 radar_evidence.v1 example files, which are UOR handoff artifacts. Schema and semantics are
    unchanged; the example digests change.
  - The frontend-only half alone would contradict the Detail view's backend text.
  - The branch is kept: feat/ux1-in-band-label @ f92ff055, rebased onto the re-pin. Its first verify failure is
    preserved.
- **Found in passing:** test_release's asset-token equality refuses any pending frontend release; REL-1 fixes it.
  The release tools (settle, re-pin) already handle new tokens.
Previously (SEC-1 merged; its release frozen and handed to the owner as one Run action; FEAS-1 sealed).
**SEC-1 (plan §13) is MERGED, and its release package is frozen with every gate passed. Auto refused the exact
deploy command, so it waits on the owner's single Run action. Production stays D 46a1de68 /
UCPE-PROD-OBS1-20261001-A. MAIN STAYS AT THE RELEASE COMMIT 51a15fd0 UNTIL THAT DEPLOY AND ITS RE-PIN. FEAS-1
(plan §22 item 8) is sealed. F1 stays CLOSED and delegated. CODEX_PAUSED_BY_OWNER stands.**
- **Owner ruling (2026-10-02):**
  - AUTO is the permanent default for UCPE.
  - For a T4, stay in Auto through preparation, waiting, CI and verification.
  - Only if Auto blocks the exact frozen production command, give the owner one Run/approval action for it, then
    continue automatically.
- **#161** (the T4-results record) merged as 39c6d518: exact head 25068d8e, STATE.md only, CI and B3 green.
- **SEC-1:** #164 → 04074527, exact head 318431b5.
  - api/request_guard.py, a pure ASGI middleware. It sits inside the request events; F1 is untouched.
    - Cross-site unsafe-method requests get 403 CROSS_SITE_REFUSED (CORS allowlist excepted).
    - Bodies over 16 KiB get 413 REQUEST_TOO_LARGE, before any route runs.
    - Every response gets nosniff, no-referrer and a self-only CSP (frame-ancestors 'self' https://huggingface.co).
    - /v1/ responses that set no Cache-Control get no-store.
  - api/auth.py (T2): new sessions carry iat and jti, plus the operator auth epoch UCPE_AUTH_EPOCH ("Session
    revoked."). It is read in auth.py, because config/settings.py is evaluator-PINNED.
  - The first verify failed with 94 EvaluatorPinMismatch (settings.py touched). The failure is preserved;
    settings.py was reverted and the read rerouted.
  - VERIFY=PASS 4824 on the exact commit. Mutation 23/23.
  - A real browser (local, fixture mode): no CSP violation. curl probes: 403/403/413/401.
  - CLAUDE_ADVERSARIAL_REVIEW, not independent: no HIGH or MEDIUM. Record: .work/roadmap/sec1/.
- **The SEC-1 release:** identity #165 → **D 51a15fd0**, UCPE-PROD-SEC1-20261002-A (exact head 0a69e7b3).
  - Push CI success (run 36963641188).
  - B3 (run 36963641128): REPRODUCIBLE=PASS sha256:f28ac93d…, SMOKE=PASS.
  - The guard on D (run 36963992290): GUARD_VERIFY=PASS 8/8, delta [api/app.py, config/build_info.py].
  - The rollback target 46a1de68 (h2_hold): ROLLBACK_FINDINGS=PASS 5/5, local only.
  - The re-pin precomputed twice, deterministic: 258b969c8ed9… (parent D).
  - The runtime delta reviewed: 5 files, digest 999610da…. Preflight PASS 7/7 at 04:20:49Z.
  - **The deploy was refused by Auto before execution ([Production Deploy]).** Nothing was consumed.
- **FEAS-1** (plan §22 item 8; synthetic only; sealed, .work/roadmap/feas1/, manifest d995d3be):
  - An absolute ±3 pp calibration claim for the 6h central range is precision-feasible within 52 weeks. Hits are
    short-memory, H ≈ 0.45.
  - It still needs a conservative variance rule (the naive HAC is anti-conservative) and a calibration recipe
    (HAR raw +1.4 to +2.8 pp).
  - A comparative claim (HAR vs EWMA) is NOT feasible: per-week SNR 0.15-0.38 against the 0.99-1.55 required.
- **UX-1** (plan §14.3), local branch feat/ux1-in-band-label @ d60ecaa:
  - "In band" replaces "Timeout" in the UI and in the backend explanation;
  - it joins the next release after the SEC-1 re-pin.
- **Unchanged:** OD-DB-1 = D; the H2 hold LIVE; F3 KEEP_UNSPENT; M1 (writer transport) UNKNOWN; B5's DEGRADED half
  deferred.
Previously (0014 APPLIED; OBS-1 RELEASED; the envelope is complete). **Both T4s ran exactly once, with the
owner approving each in Manual mode, and both were adjudicated from raw evidence. Production is D 46a1de68 /
UCPE-PROD-OBS1-20261001-A, and the guard is HEALTHY at that pin. Migration 0014 is APPLIED. The H2-safe rollback
target stays D2 5a3ef022. F1 stays CLOSED and delegated to the UOR thread. CODEX_PAUSED_BY_OWNER stands.**
- In auto mode the classifier refused both T4s (no run). The owner switched the session to Manual, and the T4s then
  ran with the owner's per-command approval.
- **T4-0014:** run 36952902214 (workflow_dispatch on main at 46a1de68, attempt 1). It is consumed: never rerun.
  - The in-run scratch-PG rehearsal: REHEARSED, the second apply refused. 132 in-run tests passed.
  - APPLIED and committed at 01:51:55Z on PostgreSQL 17.6.
  - Independent adjudication of the raw report, 44/44 PASS (.work/t4_0014/, sealed):
    - dispatch provenance;
    - the executed digest = the pin = the file at D;
    - every other column, index, table, security fingerprint and event trigger unchanged; the 14 earlier
      constraints intact;
    - 4 new CHECKs, NOT VALID;
    - 9 BEFORE triggers with event bits 19/11/34 per table;
    - one plpgsql SECURITY INVOKER function with a fixed search_path and no EXECUTE for PUBLIC or the API roles.
  - The first adjudication attempt STOPPED on a defect in the adjudicator itself (a schema-qualified function
    reference compared with a bare name). It is preserved as attempt1 with its cause; one targeted repair, then PASS.
  - Registered applied by #163 → 93c55f97.
- **T4-OBS1-DEPLOY:**
  - a fresh preflight PASSED 7/7 at 02:13Z;
  - DEPLOY=PASS at 02:15:32Z: 5a3ef02..46a1de6 fast-forward, no force; consumed, never rerun.
  - SETTLE=PASS at 02:17:05Z:
    - RUNNING at D, healthcheck 200;
    - build-info UCPE-PROD-OBS1-20261001-A with its fingerprint; the frontend bytes equal D's;
    - the F1 route answers 401 CREDENTIAL_REQUIRED.
  - ROLLBACK_CHECK=PASS 7/7 against live production D: D2 keeps the H2 hold, and 0014 is additive. The owner's
    rollback command is in .work/release_obs1/rollback_check_post.
  - The re-pin #162 = c82822e0 (exactly the twice-precomputed commit; CI and B3 green) → R 00b6fa94.
  - The guard on R (run 36955866384): GUARD_VERIFY=PASS 8/8: HEALTHY x3; hf = pin = D; live = intended =
    UCPE-PROD-OBS1-20261001-A; delta [].
- **Main 93c55f97:** push CI success (run 36956596549); the reproducibility proof PASS (run 36956596656).
- **Watch, read-only:** the resolver's next scheduled runs on the 0014-applied database (error_save_* stays 0) and
  the scheduled guard (HEALTHY at pin D).
- **Unchanged:** OD-DB-1 = D; the H2 hold LIVE; F3 KEEP_UNSPENT; writer transport UNKNOWN (M1); B5's DEGRADED half
  deferred.
- Evidence (sealed): .work/t4_0014/ and .work/release_obs1/.
Previously (0014 route merged; OBS-1 release package bound; both T4s classifier-refused, never run). **The
one-shot apply route for migration 0014 (#159 → 3e69430e) and the OBS-1 release identity (#160 → D 46a1de68,
UCPE-PROD-OBS1-20261001-A) are MERGED. Both T4s are frozen and gated. NEITHER RAN: the auto-mode classifier refused
the 0014 dispatch and the deploy before execution. Production stays D2 5a3ef022 / UCPE-PROD-F1-AUTOMATION-20261001-A.
Migration 0014 stays UNAPPLIED. MAIN STAYS AT D UNTIL BOTH T4s COMPLETE: the deploy preflight requires D = origin/main,
and the precomputed re-pin's parent is D.**
- **#159 → 3e69430e (the 0014 route).**
  - scripts/apply_migration_0014.py: attest / rehearse / apply; the migration digest pinned (ab1b77c7…).
    - Pre-checks; post-check fingerprints of the constraints, triggers, function, security, RLS, every other table's
      schema and the event triggers. One transaction: any refusal rolls back. No bulk route.
  - apply-migration-0014.yml: dispatch-only. The scratch-PG rehearsal re-runs in the job before the only step that
    holds the secret.
  - The first PR rehearsal FAILED on 42de7cc (run 36907244079): `ORDER BY 1 COLLATE "C"` is an expression, not a
    column position (42804). 9630d19 names every column and adds a regression test.
  - The rehearsal then PASSED (run 36908039753): applied once; the second apply refused NOT_A_FIRST_APPLY; probes PASS.
  - VERIFY=PASS 4785 at 9630d19. Push CI success on 3e69430e (run 36909602746); reproducibility PASS (run 36909602738).
- **#160 → 46a1de68 = D (the release identity, written by scripts/release.py identity).** VERIFY=PASS 4785.
  - Push CI success (run 36911573827).
  - B3 on D (run 36911573784): REPRODUCIBLE=PASS, sha256:ae4eb5b17351…bbbef. SMOKE=PASS.
  - The guard on D (dispatched, run 36911609195): GUARD_VERIFY=PASS, delta [Dockerfile, api/analysis_service.py,
    api/app.py, config/build_info.py]. Scheduled on D at 19:39Z: success (run 36915853051).
- **The 0014 package at D is byte-identical to the rehearsed head 9630d19.** 9630d19..D changes only STATE.md,
  build_info.py and two tests. The migration sha256 equals the pin.
- **Writer compatibility, at D and at the rollback target D2:**
  - nothing UPDATEs, DELETEs or TRUNCATEs predictions, prediction_outcomes or prediction_feature_snapshots;
  - every ON CONFLICT DO UPDATE targets other tables;
  - writes to the three tables use DO NOTHING.
- **The OBS-1 release package (frozen):**
  - D 46a1de68, UCPE-PROD-OBS1-20261001-A.
  - The runtime delta, reviewed: 7 files, digest e5f08c56….
    - B3: the Dockerfile and requirements.txt; the base image pinned by digest; 36 packages pinned by version, with
      581 hashes.
    - OBS-1's four source files, and build_info.py.
  - Preflight PASS 7/7 at 19:13:39Z (.work/release_obs1/preflight_accept). It has EXPIRED; the deploy needs a fresh one.
  - The rollback target D2 5a3ef022 (H2 hold): ROLLBACK_FINDINGS=PASS 5/5 over D (local git only; sealed).
  - The settle probe: POST /v1/automation/radar-evidence → 401 error.code=CREDENTIAL_REQUIRED.
  - The re-pin, precomputed twice, deterministic: c82822e00c92… (parent D).
- **The resolver on the DBI-1 code:**
  - run 36910462197 (3e69430e): resolved=1, error_candle_invalid=0, the same shape as the run before DBI-1;
  - run 36939566271 (D): nothing due, no errors.
- **Both T4s were refused before execution.** No 0014 run exists. Standing rule: stop, no workaround.
- **Unchanged:** OD-DB-1 = D; the H2 hold LIVE; F3 KEEP_UNSPENT; F1 CLOSED and delegated; CODEX_PAUSED_BY_OWNER.
- Evidence (sealed): .work/release_obs1/ and lanes17.
Previously (OBS-1 and DBI-1 merged; 0014 rehearsal PASS; 0014 UNAPPLIED). **OBS-1 (plan §10 structured
events) and DBI-1 (§8.2 core-evidence invariants) are MERGED. Nothing deployed: production stays D2 5a3ef022 /
UCPE-PROD-F1-AUTOMATION-20261001-A (the guard HEALTHY x3 at main 05a5d1ad). Migration 0014 is merged and
UNAPPLIED. The resolver's candle-price check is LIVE from main. F1 stays CLOSED and delegated to the UOR thread.
CODEX_PAUSED_BY_OWNER stands.**
- The STATE closure #155 merged at 17:55:08Z as b0bf17ca with --match-head-commit (head 1ab8b9d3; STATE.md only;
  CI and the reproducibility proof green). The owner merged it in Manual mode after the auto-mode classifier had
  refused it.
- **OBS-1** (plan §10; the logging half of B5): PR #156 merged at 18:01:13Z as c44da688 with --match-head-commit
  (head b9ca157).
  - Bounded, sanitized structured events: one per request (the F1 route passes through untouched), per analysis,
    and per persistence result.
  - The unbounded telemetry list is replaced; persistence failures are no longer silent.
  - VERIFY=PASS 4631; mutation 20/20.
  - It is guarded: CURRENT_DELTA_PATHS adds api/app.py and api/analysis_service.py until a release carries them.
- **DBI-1** (§8.2): PR #157 merged at 18:01:30Z as 05a5d1ad with --match-head-commit (head 4a1c557).
  - Migration 0014, AUTHORED and **UNAPPLIED**: NOT VALID checks (the probability simplex at the pipeline's own
    1e-6; positive, finite prices; horizon and chronology) and append-only triggers on predictions,
    prediction_outcomes and prediction_feature_snapshots. It is registered additive (applied_run null).
  - **The real-PG rehearsal PASSED on the exact head** (run 36903166874): WRITER_PROBE=PASS (18 production-writer
    rows, a feature snapshot and an outcome accepted; refused rows not persisted); MIGRATION_0014_REHEARSAL=PASS.
    The tested merge tree 36407ec differs from the head only by STATE.md.
  - **The resolver (LIVE at merge; it runs from main):**
    - an in-window candle with a non-finite price or a non-positive close fails as error_candle_invalid (the
      existing rq-v1 policy);
    - valid data resolves unchanged;
    - RESOLVER_VERSION is unchanged.
  - VERIFY=PASS 4650; mutation 7/7 + 15/15.
- **Independence (OD7):** 0 shared files. The OBS-1 + DBI-1 combination gave VERIFY=PASS 4671. Main 05a5d1ad
  differs from that verified combination only by STATE.md.
- **Push CI success:** c44da688 (run 36903708584) and 05a5d1ad (run 36903744546). The reproducibility proofs on
  main PASS: runs 36903708859 and 36903744369.
- **The guard,** dispatched once on 05a5d1ad (run 36903795271): GUARD_VERIFY=PASS 8/8.
  - HEALTHY x3; live = pinned = D2 5a3ef022.
  - The delta is [Dockerfile, api/analysis_service.py, api/app.py].
- **Next (owner standing authorization, conditional):**
  - the dedicated one-shot apply route for 0014, its gates, then the single production apply;
  - then the OBS-1 release package with the B4 tooling and the B3 gate.
- **Unchanged:** OD-DB-1 = D; writer transport UNKNOWN; B5's DEGRADED half deferred; the H2 hold LIVE; F3
  KEEP_UNSPENT.
- Evidence (sealed): .work/roadmap/post_merge_obs1_dbi1/ and lanes17.
Previously (B3 and LOW-1 merged; B3 reproducibility PASS). **PHASE 2 FOUNDATION: B3 (reproducible build)
and LOW-1 (the release-probe allowlist) are MERGED. These merges deployed nothing: production stays D2 5a3ef022 /
UCPE-PROD-F1-AUTOMATION-20261001-A (the guard HEALTHY x3 at main 52965cc2, delta [Dockerfile]). F1 stays CLOSED and
delegated to the UOR thread. CODEX_PAUSED_BY_OWNER stands.**
- **B3** (governing plan §11.1): PR #153 merged at 16:45:16Z as d9e42a60 with --match-head-commit (head 2af26f0c).
  - The governed proof on the exact head (run 36893825631):
    - two independent clean builds of 2af26f0c ran on runners in Azure centralus and westus2, with
      SOURCE_DATE_EPOCH 1790861810;
    - both produced the manifest digest sha256:aed92917ba819d8896f569c4bc69cf4638e29d1928754d66bd11c8644be6cc0e,
      and the image archives were byte-identical (sha256 8ddd698d…). REPRODUCIBLE=PASS;
    - build A's image smoke: SMOKE=PASS (health 200; build-info UCPE-PROD-F1-AUTOMATION-20261001-A);
    - CI test was green on the same head.
  - The proofs on main, each REPRODUCIBLE=PASS and SMOKE=PASS:
    - d9e42a60 (run 36894354216): sha256:8e5af54b2f505811804b6e3aaf8ed426e18d0dac5d1b1e5a9b13b144c2787ed8;
    - 52965cc2 (run 36894534728): sha256:2a393ecadaea8c443acdcee14dc92c85428fae1ba8c00c707ad1cfbcc049dc75.
  - The pinned inputs:
    - the base image python:3.11-slim@sha256:e41613d4… (Python 3.11.16) and BuildKit
      moby/buildkit:v0.33.1@sha256:cec9f139…;
    - requirements.txt is a uv hash lock (36 pins, 581 sha256, exclude-newer 2026-10-01T00:00:00Z). It equals the
      environment CI installed unpinned on the same day (33 Linux pins);
    - PYTHONHASHSEED=0 applies to the install step only.
  - The Dockerfile is the guarded delta (CURRENT_DELTA_PATHS = [Dockerfile]) until a release carries it (T4).
  - Gates: VERIFY=PASS 4602; mutation 19/19. Four pre-proof review findings were fixed before any push: the PR-head
    checkout, a docker-loadable archive, the build-time hash seed, and main proofs that cannot be cancelled.
- **LOW-1** (closed; the B4 review's accepted LOW finding): PR #154 merged at 16:46:43Z as 52965cc2 with
  --match-head-commit (head 9afa2dbd).
  - Settle probes stay on base_url, and a POST probe must be listed in ops/release/config.json post_probe_paths
    (fail closed).
  - VERIFY=PASS 4597; mutation 8/8.
- Independence (OD7: two proven-independent lanes): 0 shared files. Main's tree 1ad97975 equals the locally
  verified combination of both (VERIFY=PASS 4610).
- Push CI success: main 52965cc2 (run 36894534715) and d9e42a60 (run 36894354349).
- The guard, dispatched once on main 52965cc2 (run 36894604710): GUARD_VERIFY=PASS 8/8 with scripts/release.py.
  - Every round was HEALTHY; live = pinned = D2 5a3ef022; the live release = the intended one; the delta is
    [Dockerfile].
- **OD-DB-1 = D** (owner ruling, 2026-10-01): the structural/data-row DB precheck does not run yet.
  - No probability, label, return, §5A, F3 or protected material is read.
  - The pack stays prepared only: .work/roadmap/db_precheck/. 01_catalog.sql is catalog-only; 02 is gated.
  - Phase 3 constraints should be added NOT VALID, so old rows are never scanned.
- Writer transport (plan §8.3): still **UNKNOWN**. The owner-run M1 is prepared.
- B5 stays deferred: radar_evidence.v1 and its data-quality semantics are frozen while the UOR handoff is active.
- The H2 hold stays LIVE; F3 stays KEEP_UNSPENT.
- Evidence (sealed): .work/roadmap/b3/, b3_proof/, low1/ and post_merge_b3_low1/.
Previously (B2 and B4 merged; roadmap resumed). **ROADMAP_RESUMED: F1 is CLOSED (owner routing,
2026-10-01). All UOR implementation and activation belong to the separate UOR owner-facing thread; UCPE reopens F1
only for a concrete upstream contract defect returned from there. B2 and B4 are MERGED. These merges deployed
nothing: no runtime or guarded file changed, and production stays D2 5a3ef022. CODEX_PAUSED_BY_OWNER stands.**
- The governing plan is UCPE_FINAL_UPGRADE_MASTER_PLAN_v1.0 (sha256 2873c8e7…). The owner's rulings on
  OD-FINAL-1…7 apply, recorded verbatim in OD_FINAL below. The H2 rulings and the live hold are unchanged.
  - An earlier local draft (041c57e) said these ODs were never ruled. It was never published, and it is superseded
    here.
- **B2** (governing plan §11.1): PR #150 merged at 12:27:29Z as fc441c52 with --match-head-commit (head 52cb9a2).
  - Every workflow action is pinned to a reviewed Node-24 SHA, with timeouts and least-privilege permissions.
  - VERIFY=PASS 4571, including a fresh re-verify of the exact commit. Mutation 4/4.
- **B4** (plan §11.2-§11.3): PR #151 merged at 12:27:35Z as fdfefd2c with --match-head-commit (head 9ac70a2).
  - scripts/release.py covers identity, preflight, deploy, settle, repin, guard-verify, rollback-check and
    rollback. Data: ops/release/config.json and releases.json. Docs: docs/runbooks/RELEASE.md and ROLLBACK.md.
  - The rollback check is H2-safe by both code marker and registry. The pre-hold 00705c55 is never a target.
  - VERIFY=PASS 4586, including a fresh re-verify of the exact commit. Mutation 13/13.
  - Live read-only validation against production: guard-verify PASS, settle PASS, rollback-check TC-V1-STAMP
    PASS, PROD-SAFE-3 STOP.
- The gate for both: a CLAUDE_ADVERSARIAL_REVIEW (NOT independent), in fresh detached worktrees.
  - Verdict CLEAN: no HIGH or MEDIUM.
  - LOW-1 (operator POST probes, bounded) is accepted.
  - LOW-2 (DISASTER_RECOVERY_RUNBOOK called OD6 "undecided") is fixed in this record.
  - The review: .work/roadmap/CLAUDE_ADVERSARIAL_REVIEW_B2_B4.md.
- Main fdfefd2c: push CI success (run 36861888464).
- Writer transport (plan §8.3): **UNKNOWN**.
  - The one read-only request the owner allowed (GET /v1/system_status, no session) returned 401 "Valid session
    is required." and nothing about transport. No mutation.
  - Proven: the reader, the automation route and the resolver use Postgres. The analysis writer is NOT inferred.
  - The owner-run measurement contract: .work/roadmap/writer_transport/MEASUREMENT_CONTRACT.md.
- B3 (reproducible build) started on fresh main; its acceptance needs two independent clean CI builds of the same
  commit with identical image digests.
- B5 stays deferred by the owner: radar_evidence.v1 and its data-quality semantics are frozen while the UOR handoff
  is active.
- The dependency map and evidence: .work/roadmap/ (sealed).
Previously (F1 canary PASS; live isolation PASS; the UOR handoff package). **F1_CANARY=PASS,
LIVE_ISOLATION=PASS: the owner issued the credential uor-radar-2026-10 (T4; named here by id only, its value never
requested, printed or stored) and ran the one canary. The governed UCPE→UOR handoff package is finalized
(docs/automation/UOR_HANDOFF.md). UOR is untouched, UOR Cron is not re-enabled, and CODEX_PAUSED_BY_OWNER stands.**
- The canary (the owner ran canary_f1.py, attempt_01, at 2026-10-01T10:25:15Z): HTTP_PASS 13/13.
  - BTC 4H, client_request_id 3e8ca8f0-5016-4e45-9ea1-0aedbe815260 → 200; run_id
    run_d33406cea53648829428b829198577d3; evidence_hash sha256:58191ef5…a846; release
    UCPE-PROD-F1-AUTOMATION-20261001-A. The replay was byte-identical, with Idempotent-Replay: true.
  - Claude's independent re-check of the raw bytes: 12/12. That includes the evidence_hash recomputed with no JCS
    code (the member cut from the canonical bytes) and with the pinned canonical.py.
- The owner's read-only SQL (owner-attested):
  - one ledger row for that key: COMPLETED / SUCCEEDED / 200, with the same run_id, evidence_hash and release;
  - predictions for that run_id: 0;
  - the global isolation query (contract §3): 0.
- Verdicts: F1_CANARY=PASS (all 7 release-plan criteria) and LIVE_ISOLATION=PASS.
  - Evidence (the main checkout, read-only): .work/f1_release/activation/canary/attempt_01_20261001T102515Z/ and
    CANARY_ADJUDICATION.md.
- The handoff package (this record): UOR_HANDOFF.md now carries:
  - the exact states, the endpoint and the governed origin;
  - the pinned schemas and files, with their sha256;
  - the release identity, and the JCS and hash contract;
  - the examples, and the G6 quota and capacity facts;
  - the errors and timeouts;
  - the credential, by name and role only;
  - the isolation and audit proof, the kill switch and rollback, and the UOR-side boundary.
  Also:
  - New pinned files: the canary's exact answer (docs/automation/examples_live/, LIVE_SAVED, with PROVENANCE.json).
    It is a non-holdout example carrying the real release identity, as UOR file 05 §13 asks.
  - The pinned docs' status lines now state the current facts: CREDENTIAL_ROTATION, F1_RELEASE_PLAN,
    RETENTION_AND_IDEMPOTENCY, and RADAR_EVIDENCE_V1 (its status and §13). No runtime change.
- Next: the UOR-side handoff and activation (OWNER_BOUNDARY). Claude stops here.
Previously (F1 enabled by the owner; post-enable PASS): **F1_ENABLED_NO_CREDENTIAL: the owner set
UCPE_AUTOMATION_ENABLED=1 on the Space (T3; the restart landed about 09:04Z). The post-enable check PASSED. No
credential is issued, so every call is refused. UOR and Cron are untouched. CODEX_PAUSED_BY_OWNER stands.**
- post_enable_check_f1.sh (the prepared kit, KIT_MANIFEST 3/3 before the run): ENABLE_CHECK=PASS 7/7 at 09:05Z.
  - RUNNING at D2 5a3ef022 (1 replica, no error); build-info UCPE-PROD-F1-AUTOMATION-20261001-A; healthcheck
    200 with uptime 79 s (the restart landed); the frontend digests unchanged.
  - No credential: 401 CREDENTIAL_REQUIRED, so the kill switch is open.
  - A well-formed token under the reserved, never-issued id `probe-never-issued`: 401 CREDENTIAL_INVALID.
    - In code, that answer follows only a successful registry read: any database failure answers 503
      LEDGER_UNAVAILABLE.
    - So the route's own production connection is proven for the registry path, with no credential.
- The extra read-only checks (readonly_extra_checks_f1.sh): PASS 6/6 at 09:16Z.
  - A human session cookie: 403 HUMAN_SESSION_REFUSED. A malformed token: 401 CREDENTIAL_INVALID.
  - Cache-Control: no-store; absent from /openapi.json; GET not served (404).
  - CORS as documented (below).
- F1-ACT-1 (LOW), adjudicated: .work/f1_release/activation/POST_ENABLE_ADJUDICATION.md.
  - What: the Hugging Face edge answers CORS preflights itself, reflects any origin, and grants the credential
    header. UCPE's own CORS policy refuses it (tested in process).
  - Not exploitable: the token is never ambient; human cookies are refused (403), are SameSite=Lax, and
    hf.space is a public suffix.
  - The owner chose option A (this record): RADAR_EVIDENCE_V1.md section 2 now states the edge behaviour and
    that the route never relies on CORS, with a consumer rule (the token is never used from a browser).
    UOR_HANDOFF.md carries the new digest and status. No runtime change.
- Evidence (the main checkout, read-only): .work/f1_release/activation/post_enable_20261001T090517Z/ and
  readonly_extra_20261001T09*/.
- Next: the owner issues the credential (a T4 secret entry), then runs the canary. Claude stops here.
Previously (F1 released; re-pinned): **F1_RELEASED_ROUTE_OFF: production is D2 5a3ef022 /
UCPE-PROD-F1-AUTOMATION-20261001-A, RUNNING and guard-HEALTHY. The automation route is present and OFF
(503 AUTOMATION_DISABLED). No credential is issued; UOR and Cron are untouched. CODEX_PAUSED_BY_OWNER stands.**
- F1 is MERGED: M = 5da10ef3 (PR #144, an exact-head merge commit). Its gate was a CLAUDE_ADVERSARIAL_REVIEW
  (not independent: Codex is paused) with 48 bounded mutants, all killed.
- Migration 0013 is APPLIED (T4, CONSUMED, PASS; run 36820986264). Both tables are locked (RLS on, no policy,
  no API-role privilege) and were empty when applied.
- The release (T4, CONSUMED, PASS; never rerun):
  - D2 = 5a3ef022db10462675361e8d15aa8f4f572dc1aa, the merge of PR #145 (the identity). Push CI success
    (36825516122). The guard on D2 (run 36825556001): HEALTHY x3, delta [analysis_service, app, build_info],
    pin = live = 2096af6d.
  - The deploy precheck: PASS 7/7 at 06:39:36Z, including the dry run.
  - One push at 06:40Z: `2096af6..5a3ef02 -> main`, exit 0, no force.
  - Settle PASS at 06:40:54Z: RUNNING at D2 on the first poll; healthcheck 200; build-info
    UCPE-PROD-F1-AUTOMATION-20261001-A with its fingerprint; the /, app.js and styles.css digests unchanged;
    POST /v1/automation/radar-evidence answered 503 AUTOMATION_DISABLED (present and OFF).
  - Raw evidence: .work/f1_release/deploy/ in the main checkout (push/ and settle_20261001T064053Z/,
    read-only, with manifests).
- The re-pin (T3): P = 4ef8f14578b2702b8095524583d6ffe034a63320, built by make_repin_f1.py. A fresh rebuild
  from D2 gave the identical SHA, and VERIFY=PASS 4568 on P.
  - PR #146 merged at 07:07:42Z with --match-head-commit: R = 3ad53b87614341043399d7ed11674fd62b149393
    (parents D2 and P; tree 884ea627, P's). PR CI success on P; push CI success (run 36828550280) on R.
  - Its first push was refused by the Claude Code auto-mode classifier. Nothing was retried or worked
    around; the owner switched the session to Manual permissions and the chain resumed.
- The guard after the re-pin (run 36828594390, dispatched once at 07:08:10Z on R), verified from its log:
  HEALTHY in all 3 rounds, exit 0, delta [], hf_main_sha = pinned = D2, live = intended = F1.
  - Its advisory SCHEDULER_DIVERGENT_FROM_PIN is the guard's shallow checkout: it cannot prove ancestry,
    and the same advisory appears on every earlier run. R's first parent is D2.
  - Raw evidence: .work/f1_release/guard_repin/ (read-only, EVIDENCE.sha256).
- This record also clarifies RADAR_EVIDENCE_V1.md section 9 ("Refusals that write no row"). A later edit had
  broken a referent: the text read as if the capacity refusals and the pre-reservation 503s were recorded
  against the key. They write no row, as the code and the ledger's outcome catalogue have always done. The
  contract's behaviour is unchanged; UOR_HANDOFF.md carries the new digest and the current status.
- Next: the owner's activation chain (OWNER_BOUNDARY). Claude stops here: issuing the credential is an owner
  secret entry (T4), and enabling is a T3 the owner performs. The prepared kit (local, nothing executed) is
  .work/f1_release/activation/.
Previously (F1 merged; 0013 applied; release identity): **F1 is MERGED, and migration 0013 is APPLIED
in production. The F1 release identity UCPE-PROD-F1-AUTOMATION-20261001-A is prepared (this PR). The route is
NOT deployed, NOT enabled, and no credential exists. Production is still D 2096af6d / UCPE-PROD-TC-V1-STAMP.**
- PR #144 merged at 05:34:45Z with an exact-head merge commit: M = 5da10ef38a2480000b5ae359519d7a3022a1e2c2.
  - Parents f19d7575 and b3bde2ec; tree d798502b = merge-tree.
  - Push CI on M succeeded (36820447090); VERIFY at M PASS 4568.
- The merge gate (CODEX_PAUSED_BY_OWNER): a CLAUDE_ADVERSARIAL_REVIEW, NOT independent.
  - Round 1 at 3a37e49: M1 MEDIUM (prepared statements on the 0013 apply connections behind the
    pooler), L1, L2 and T1, repaired in b3bde2e.
  - Round 2 at b3bde2e: CLEAN.
  - 48 bounded mutants, all killed in round 2.
  - The report: .work/f1-claude-review/ in the lanes12/f1 worktree.
- The 0013 production apply (T4, CONSUMED, PASS; never rerun):
  - run 36820986264 at M, dispatched once at 05:41:26Z after PRECHECK=PASS;
  - APPLIED, committed true, digest = pin c1a60c04…, PostgreSQL 17.6;
  - 42 constraint probes as reviewed;
  - both tables locked (RLS on, no policy, no API-role privilege) and empty;
  - the existing tables' security and schema fingerprints, and the event triggers, unchanged.
  Raw evidence: .work/f1_release/apply_0013/ (EVIDENCE.sha256, ADJUDICATION.md, files 0444).
- The release identity (this PR): 30ce73e changes config/build_info.py, its test, and the guard delta
  mirror [analysis_service, app, build_info]. That is the W26 three-file pattern.
- Next, under the standing authorization (deterministic T3/T4, stop on any mismatch or failure):
  merge this PR (D2); a guard run on D2; the deploy precheck; one fast-forward push of D2 to hf; the
  settle checks; the re-pin; a guard run HEALTHY. Then STOP at the credential issuance (owner secret
  entry).
Previously (F1 merge gate, round 2): **ROUTING OVERRIDE: CODEX_PAUSED_BY_OWNER (owner ruling, 2026-10-01)
until the owner explicitly resumes it.**
- Every pending Codex retry was cancelled. Codex is not invoked.
- The merge gate is now a CLAUDE_ADVERSARIAL_REVIEW (Opus 5 MAX; explicitly NOT an independent
  review) plus deterministic evidence: verify on the exact head, green CI and real-PG rehearsal, and
  bounded mutation tests. CLAUDE.md is unchanged for this temporary override.
**Round 1 on the frozen head 3a37e49f (fresh detached clean worktree):**
- VERIFY=PASS 4559, scanners 3/3; the CI and the 0013 real-PG rehearsal on the exact head are green.
- Mutation tests: 45 mutants, 44 KILLED (one by the full suite), 1 survived: the body copy cap was
  untested (T1).
- Findings: **M1 MEDIUM.** The 0013 apply connections allowed psycopg's automatic named prepared
  statements; the probes repeat 3 savepoint statements 42 times, a risk behind Supabase's
  transaction pooler for the one-shot T4. Also L1 LOW (Content-Length parse) and L2 LOW (the
  deadline instant was early by the body-read time, conservative).
- One consolidated repair (this commit): CONNECT_OPTIONS with prepare_threshold=None, the
  Content-Length bound, the deadline instant from the current wall clock, and the copy-cap test.
  The report is .work/f1-claude-review/CLAUDE_ADVERSARIAL_REVIEW.md in the worktree.
- Next: full verify, the PG rehearsal and CI on this head; freeze it; Claude adversarial review
  round 2; merge only if no HIGH/MEDIUM remains.
Previously (F1 merge gate): **F1-MERGE-GATE-A: PR #144 now carries the frozen ledger
capacity contract (8b22efe) and the consolidated repair of independent Codex review 2 (8f7923c). The
final independent Codex review (review 3) runs on the head that carries this record. The PR is merged
only if review 3 leaves no unresolved HIGH/MEDIUM and every gate passes; main then becomes M, the merge
commit whose parents are f19d7575 and that head (the owner's standing authorization of 2026-10-01).**
- Codex review 2 at eb6976d: 4 MEDIUM, 5 LOW (.work/f1-review2/REVIEW.md in the worktree). All were
  adjudicated against code, and each is repaired or is a disclosed design point
  (docs/automation/F1_NODE_CLASSIFICATION.md, "Independent review 2"):
  - R2-01: 42 in-transaction constraint probes, full index structure, existing-schema and
    event-trigger fingerprints;
  - R2-02: an explicit deadline contract with a 0.25 s commit reserve;
  - R2-03: admission before any body byte, a bounded body read, tcp_user_timeout;
  - R2-04: ledger invariants (pending identities NULL, the outcome catalogue with its statuses, the
    body tied to its columns, a 16 KB text bound);
  - R2-05/06/09: fixed. R2-07/08: by design.
- The capacity contract (owner, 2026-10-01): at least 90 days kept; a 25,000-row cap (503, nothing
  written); a per-credential 2 x quota rolling-day row ceiling (429, nothing written); an 8 KB stored
  body; the quota bounded at 120/day. It fails closed, never deletes, and runs no recurring job. G6
  stays provisional.
- CI at 8f7923c:
  - the 0013 real-PG rehearsal passed (run 36811117675): APPLIED with all 42 probes, the second
    apply refused, 33/33 role probes refused, PROBE PASS 27, the rebuild APPLIED;
  - the 0010 rehearsal passed;
  - the full suite: success (run 36811117609).
  VERIFY=PASS 4559, scanners 3/3; no pinned file.
- After the merge: nothing is applied, deployed, enabled or issued. The next boundary is the 0013
  production apply T4 (the owner), whose contract is prepared from M.
- MODEL SUBSTITUTION: none in this step. Codex ran review 2 and runs review 3.
Previously (F1 merge readiness): **F1-MERGE-READINESS-A: draft PR #144 (feat/f1-governed-automation),
published without force and NOT merged. The code gaps the owner named are closed. The mandatory independent Codex
security review is OPEN: the Codex quota is exhausted until about 19:35Z. No PASS is substituted.**
- Credentials: a DB registry (public.automation_credential, migration 0013), read on every request with no cache.
  Rotation has zero downtime and revocation applies at the next request, with no Space restart. Proven on real
  PostgreSQL.
- Migration 0013 now holds the registry and the ledger. Its CHECKs are now NULL-safe: a CHECK that evaluates to NULL
  passes, so a SUCCEEDED row without its run id or hashes used to be accepted. Found while writing the probe.
- The dedicated one-shot 0013 apply route is BUILT, in the 0012 pattern: scripts/apply_migration_0013.py and the
  dispatch-only apply-migration-0013.yml, which rehearses on scratch PostgreSQL before its one secret step.
- The PR rehearsal apply-migration-0013-rehearsal.yml (no secret) passed on real PostgreSQL at d9df2371, run
  36747080987:
  - APPLIED, then the second apply refused;
  - all 33 API-role probes refused;
  - PROBE PASS 49 checks (rotation, revocation, JCS replay through JSONB, the DB-clock deadline, quota, every
    constraint hazard, fail-closed transport);
  - the rebuild from 0001-0010 APPLIED.
- Retention and idempotency are audited (at least 90 days; no automated purge; an owner capacity item). The
  transport is reconfirmed fail-closed; the Space's connectivity is not assumed.
- The bulk apply_migrations.py stays forbidden for 0013, and no workflow runs it (tested).
- VERIFY=PASS 4496; scanners 3/3; no evaluator-pinned file touched.
- Nothing is applied, deployed, enabled or issued. Production is unchanged: D 2096af6d.
- MODEL SUBSTITUTION: Codex was unavailable (usage limit), so Claude implemented this change. It is recorded here.
Previously (F1 LOCAL): **F1-GOVERNED-AUTOMATION-LOCAL-A is committed and verified
LOCALLY on feat/f1-governed-automation (028ded8, 4f9ae93, 0bc11ff plus this record), VERIFY=PASS 4324. It is NOT
pushed, NOT deployed and NOT enabled. No credential was issued, and migration 0013 is authored, NOT applied.**
- The machine route POST /v1/automation/radar-evidence (radar_evidence.v1) ships OFF (503 AUTOMATION_DISABLED). Even
  enabled, it fails closed (503 LEDGER_UNAVAILABLE) until 0013 is applied.
- Cohort isolation is structural. AUTOMATED_RADAR is not a PredictionOrigin. analyze_request_isolated writes no
  cohort row, and its analysis is proven byte-identical. The isolated ledger is the only store.
- No evaluator-pinned file changed. The guarded delta on this branch is analysis_service.py and api/app.py.
- Production is unchanged: D 2096af6d / UCPE-PROD-TC-V1-STAMP-20260930-A. The rollback target is 080f20a9.
- The Codex quota was exhausted mid-milestone (it resets 2026-10-01 02:35 +07). The repair's test updates and its
  delta review were done by Claude instead, and that substitution is recorded here.
Previously (W26 RELEASE CLOSED): **W26_RELEASE_CLOSED: the tc-v1 writer stamp is deployed and PROVEN stored in
production. SAFE_MILESTONE_REACHED_FOR_AD_HOC_INTEGRATION.**
- Production: D = 2096af6d1b3d54461b40c47fd96c265882e5af40 / UCPE-PROD-TC-V1-STAMP-20260930-A.
  - Deploy PASS, with settle PASS.
  - Post-deploy guard run 36715108033: HEALTHY in all 3 rounds, delta [], pin = live = D.
- The real CONTROLLED_SMOKE, run once by the owner (run_af48fd1e0dea4e69a231b64d6569cc63): PASS_HTTP.
- The one-row DB read, run once by the owner in the Supabase SQL editor: pack §6 PASS → **PASS_PROVEN**.
  - The row is CONTROLLED_SMOKE, tc-v1, OKX_PUBLIC.
  - Both stamp timestamps lie inside the logged request window, and all four invariant checks are true.
- The H2 hold is unchanged. This proves operation and storage only: there is no directional, skill or model PASS.
- From now on, eligible USER_REQUESTED rows are stamped at write time. RC1 resolves them on their stored
  reference_venue in scheduled runs (the owner ruling of 2026-09-30). There is no legacy reclassification.
- The only rollback target is 080f20a95241504bd7cf96088bf075d1ebaf4f55 (H2-HOLD); never 00705c55.
- This record: chore/state-tc-v1-release, published and merged under the owner's standing authorization.
Previously (TC-V1-STAMP released): **PRODUCTION IS D = 2096af6d1b3d54461b40c47fd96c265882e5af40 /
UCPE-PROD-TC-V1-STAMP-20260930-A (the W26 tc-v1 writer stamp). It was deployed under the owner's standing authorization
of the prepared chain.**
- Claude merged identity PR #141 at 12:19:50Z, giving D (parents 86c9496f + 0c015a59, tree 68917d99).
- The deploy T4 is CONSUMED, with PASS: one fast-forward push, 080f20a..2096af6, at 12:24:01Z; settle PASS.
- The re-pin PR #142 (P 24c66816) was merged, giving main 6becb100. Guard run 36715108033 is HEALTHY in all 3 rounds,
  with delta [] and pin = live = D.
- The smoke tools are SEALED (W26_SMOKE_TOOLS.sha256 26ae7064…). The real CONTROLLED_SMOKE and the one-row DB
  read are NOT_RUN: the owner enters the access code.
- The only rollback target is 080f20a95241504bd7cf96088bf075d1ebaf4f55 (H2-HOLD); never 00705c55.
- Operational success is not directional or model evidence: the H2 hold and every skill gate are unchanged.
- This record is local (chore/state-tc-v1-release).
Previously (identity prepared): **The owner MERGED #140 (the STATE repair, 10:39:37Z → main 86c9496f) and
CLOSED #139 unmerged (10:39:50Z).**
**The release identity UCPE-PROD-TC-V1-STAMP-20260930-A is PREPARED LOCALLY: e7309c31 on
prep/release-identity-tc-v1-stamp. It is NOT PUBLISHED.**
- The deploy, re-pin, smoke and DB read are NOT_RUN. Production stays 080f20a9 / UCPE-PROD-H2-HOLD-20260927-A.
- The only rollback target is 080f20a95241504bd7cf96088bf075d1ebaf4f55.
- This record is local (prep/release-identity-tc-v1-stamp).
Previously (STATE repair after #138): **W26 is MERGED: the owner merged PR #138 at 09:56:11Z, giving main
d790e0ff. Its tree is 9de0f067, exactly the W26-first tree recorded before the push; CI success (run 36699280110).**
**The release identity, the deploy, the re-pin, the new smoke and the DB read are NOT_RUN.**
- Production stays 080f20a9 / UCPE-PROD-H2-HOLD-20260927-A.
- This record, chore/state-w26-repair, reconstructs #139's intended semantics on fresh main and supersedes #139. #139 is
  left open and unmodified.
Previously (post-merge): **The owner MERGED PR #136 (RC1, 07:45:03Z → 200e6ad6) and PR #137 (the STATE
record, 07:45:22Z → e09dee01). Main e09dee01 has tree 098bddfa, exactly the final tree recorded before the push.**
**W26 is reconciled onto e09dee01 as 79d43d38.**
- Its diff is byte-identical to the reviewed be4b9939, and the pin is unchanged (closure 3ffc21e9…, 69 files).
- VERIFY=PASS 3999.
- It was PUSHED as PR #138, which the owner has since MERGED (09:56:11Z → d790e0ff). This record was first pushed as
  #139 and is superseded by chore/state-w26-repair.
- No deploy: production stays 080f20a9 / UCPE-PROD-H2-HOLD-20260927-A.
Previously (post-W26, before the merges): **RC1 and the migration-apply STATE record are PUSHED, and Claude opened
PRs #136 (RC1) and #137 (STATE); neither is merged. The owner-authorized §2.6 package W26 (the writer stamps tc-v1;
a conditional stamp INSERT in the pinned repository.py) is EXECUTED AND COMMITTED LOCALLY: be4b9939 on RC1 f1924495.**
- Only the evaluator pin's closure_digest changed, 212ea637… → 3ffc21e9…; the 69-file membership is unchanged.
- VERIFY=PASS 3999; bounded Codex review NONE.
- W26 is not pushed, merged or deployed. Production stays 080f20a9 / UCPE-PROD-H2-HOLD-20260927-A. The release
  preparation is complete (read-only).
- This record is local (chore/state-w26-local).
Previously (post-0012 T4): **MIGRATION 0012 IS APPLIED IN PRODUCTION. The owner-authorized one-shot T4
APPLY-MIGRATION-0012-ONCE is CONSUMED and PASSED: run 36586262979 on main b11a8e53, committed.**
- public.prediction_resolution_status now exists, exactly the adopted D5 schema, and empty.
- Row-level security is on with no policy and no privilege for PUBLIC, anon, authenticated or service_role.
- Every existing table's security is unchanged, and 0011's four columns are present before and after.
- Both migrations are live. Nothing writes the new columns or the new table yet: the writer does not stamp, and the
  resolver does not use the status table.
- No deploy, DB console or manual SQL: hf and the running Space stay at 080f20a9.
- This record is local (chore/state-post-0011-0012-apply).
Previously (post-0011 T4): **MIGRATION 0011 IS APPLIED IN PRODUCTION. The owner-authorized one-shot T4
APPLY-MIGRATION-0011-ONCE is CONSUMED and PASSED: run 36583531813 on main b11a8e53, committed.**
- The owner merged #133 (the post-132 record), #134 (the 0011 route) and #135 (the 0012 route). Main is
  b11a8e53; each merge tree equals the tree recorded before the push; CI success.
- The exact production delta: predictions gained the four nullable, no-default stamp columns and the three validated
  CHECKs. Everything else was verified unchanged.
- 0012 is merged, NOT applied. No row is stamped yet: the writer does not stamp.
- No deploy, DB console or manual SQL: hf and the running Space stay at 080f20a9.
- This record is local (chore/state-post-0011-apply).
Previously (post-132): **The owner MERGED three PRs:**
- **#130,** the post-129 STATE record, at 12:49:38Z;
- **#131,** N1, target contract v1, at 12:53:59Z;
- **#132,** N2, resolver hardening, at 12:58:46Z.
**Main is 30b40662, CI success; each merge tree equals the recomputed merge of its parents.** D4 (retry/quarantine
policy rq-v1) and D5 (status table 0012) are owner-adopted.
**Migrations 0011 and 0012, with their one-shot dispatch-only apply routes, are REBUILT on 30b40662 as local
publication candidates (500e5b83, 6ccf60eb).** Both pass VERIFY in a clean worktree, and bounded Codex reviews found
NONE. They are not pushed, merged or applied.
The writer/resolver integration pack is decision-ready (OWNER_BOUNDARY 1). The first scheduled resolver run on
6fb3e8b4 printed due=0; no run has happened on 30b40662 yet. No deploy, dispatch or DB action: hf and the running
Space stay at 080f20a9. That record was published as PR #133 (main f844452b).
Earlier on 2026-09-29: **RESOLVER_P1 is MERGED: PR #129, main 6fb3e8b4 (merged by the owner at 2026-09-29T06:42:05Z;
CI success). Its §2.6 publication T3 is CONSUMED and §2.6 is CLOSED for publication.** c7cb70f8 and fb765188 remain
unaccepted and are on main as history only. The 2026-09-27 record below was published as PR #128 (main 6f5038d0).
Previously (2026-09-27). R4, the B lane, the NEXTGEN lane, D-1, NG-1 (closed), lane H1 and the H2 record through H2-G2
are published (main 597e5c95, PR #123), the H2 record through the Q5 adjudication too (main 1dfe2d22, PR #124), and
the T2 fail-closed hold with its record (main fa5c0da7, PR #125), the release identity (main 080f20a9, PR #126), and
the production re-pin (main 9a1db2dd, PR #127). **PRODUCTION IS PROD-H2-HOLD: hf/main and the running commit are
080f20a9, build UCPE-PROD-H2-HOLD-20260927-A (deployed 2026-09-26T19:47:36Z). The canonical guard is HEALTHY (run
36310977790).** **The CONTROLLED_SMOKE returned PASS_PROVEN (2026-09-27): production held the legacy 4H and 1H
SKILL_DEMONSTRATED verdicts closed, with no USER_REQUESTED contamination (below).** H1 is COMPLETE, and the main
checkout is now on main. **Lane H2:** its paper
brief (v3) found that the live directional-skill gate counts near-duplicate and overlapping outcomes as independent
evidence; 1H and 4H passed it as of 2026-08-16 and are unread since. **The owner ruled Q1–Q8 on 2026-09-26:** one
contribution per candle, D3 window means, a drift-aware directional reference, and an interim FAIL-CLOSED posture.
The four paper deliverables are prepared, audited once (REJECT), repaired on paper and sealed (H2_PREP.sha256
ea4bc8de…). Nothing is implemented, queried or deployed, and the product is unchanged. After a second review, the
owner also ruled point 12(a) on 2026-09-26: a predeclared fail-closed drift guard. The additive v2 records are sealed
(H2_PREP_12A.sha256 c795c177…).
- An owner-ordered analytic validation then rejected that guard's thresholds (g 0.2407; 0.10 as error control;
  H2_GUARD_VALIDATION.sha256 745075ad…).
- The owner ruled an error budget: ≤ 5% across four timeframes, ≤ 1.25% per timeframe, 0.9375% of it modeled. They
  froze the v3 candidate: α_look 0.001, g 0.09 SE.
- **The v3 candidate FAILED its predeclared modeled acceptance in 1 of 36 scenarios (S01, the design rule's
  envelope; upper bound 0.95485% > 0.9375%).** The 35 actual-gate scenarios passed.
- The v3 candidate stays permanently FAILED on record, unreplaced.
- **The owner then selected a new candidate generation, H2-G2**, not a retry: α_look 0.001, g 0.07 SE, and 0.10 as
  coverage-only, with the same budget.
- **Its single predeclared acceptance PASSED all 36 binding scenarios.** The envelope S01 has an upper bound of
  0.90519% ≤ 0.9375%. Across four timeframes with the reserve: 4.8707% ≤ 5%.
- **H2-G2 is PASSED pending Q5 operating-density confirmation, not fully accepted.**
- **The owner-run Q5 count-only read** (Q1–Q3 and Q5; Q4 excluded as performance) passed every provenance check
  after one correction. A smoke-row expectation had been built from an outcome-linked count; a follow-up count
  (6 | 5) confirmed the cause.
- **Q5 adjudication: UNAVAILABLE.**
  - Operating density is 1–6 contributions per counted window.
  - The informative-call floor (m ≥ 100, k ≥ 12) is unmet everywhere; the best is m 10 and k 4. At the observed
    rates it would be met around 2028 or later.
  - H2-G2 keeps its modeled PASS, but the frozen gate would return INSUFFICIENT_EVIDENCE for years. The interim
    fail-closed posture stands (OWNER_BOUNDARY 2).
- **The H2 fail-closed hold is DEPLOYED and VERIFIED LIVE: production 080f20a9 / UCPE-PROD-H2-HOLD-20260927-A.**
  - The CONTROLLED_SMOKE returned **PASS_PROVEN**. The legacy SKILL_DEMONSTRATED verdicts on 4H (n 164) and 1H (n 154)
    were held (NO_TRADE, "Directional evidence under review"), with no directional candidate and no USER_REQUESTED
    contamination.
  - The re-pin is MERGED (PR #127, main 9a1db2dd), and the canonical guard dispatch is HEALTHY (run 36310977790).
  - Q5 stays UNAVAILABLE.
- History (2026-09-27, before PR #127 and the smoke): **The H2 fail-closed hold is DEPLOYED: production 080f20a9 /
  UCPE-PROD-H2-HOLD-20260927-A (2026-09-26T19:47:36Z).**
  - Its functional CONTROLLED_SMOKE is NOT_RUN; the contract is sealed, paper only.
  - The baseline re-pin is PREPARED LOCALLY (release/prod-h2-hold: edc64df2, then this record). It is NOT PUSHED and
    NOT MERGED. With the new pin, the guard is HEALTHY against production.
  - Q5 stays UNAVAILABLE.
- History (2026-09-26, before the deploy): **The T2 fail-closed hold (Q8) is MERGED (PR #125 → main fa5c0da7) but
  NOT DEPLOYED. Q8 is NOT LIVE.**
  - The owner-authorized deploy (T4) stopped before any mutation and was not consumed. The local HF credential is
    invalid, and the release identity had not moved since PROD-SAFE-3.
  - **The release identity UCPE-PROD-H2-HOLD-20260927-A is PREPARED LOCALLY:** branch prep/release-identity-h2-hold,
    from main fa5c0da7: 2b575abb, then this record. It is NOT PUSHED, NOT MERGED, NOT DEPLOYED and NOT LIVE.
  - Production is still 00705c55 / UCPE-PROD-SAFE-3-20260915-A, and the live gate behaves as today.
  - Q5 stays UNAVAILABLE.
- History (2026-09-26, before PR #125): **The T2 fail-closed hold (Q8) is IMPLEMENTED LOCALLY only. Q8 is NOT LIVE.**
  - Branch feat/h2-failclosed-hold, from main 1dfe2d22: e669e06f (the hold), ebfe2073 (the owner's final detail
    wording), 9d7fdc4d (the first STATE record) and 4ea42593 (the owner's final headline), then this record.
  - It is NOT PUSHED, NOT MERGED, NOT DEPLOYED and NOT LIVE. The live gate behaves as today, and hf is unchanged at
    00705c55.
  - Q5 stays UNAVAILABLE.
15m and 1H are
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
LOOP_STATE=IN PROGRESS (2026-10-05): the Card-04 companion is PUBLISHED (#230 → main 267a6eaf; this record
  last). Claude continues Lane P and Lane R locally under the owner's Phase-7/8 rulings (DP-A to DP-F), then
  DP-D's local tooling. Each publication is a new owner T3; Lane P also waits for the UOR qualification
  episode's close or the owner's authorization.
  Before it: AT THE OWNER (2026-10-05): the Card-04 companion (ucpe.a4_card04_companion.v1) and the A4
  handoff's two documentation corrections are PREPARED AND VERIFIED LOCALLY on feat/a4-card04-companion @ 93ab50de,
  with the owner's cross-credential count (A4-CRID-UNIQUENESS) and the owner-authorized third repair; 4f3f00cd
  and 0652c431 are superseded. The fresh review of the exact head: PASS. The one owner action is the T3.
  Before it: IN PROGRESS (2026-10-04): the owner's T3 publication batch is COMPLETE (#226, #227, #228; this record
  last). Claude continues with dependency-safe local lanes; any new pull request needs a new owner T3 batch.
  Before it: AT THE OWNER (2026-10-04): POST-PHASE-4 lanes A and B are DONE LOCALLY (VERIFY=PASS, composed). The
  one batched owner action is T3 publication of three branches. No other lane is safe without an owner decision.
  Before it: AT THE OWNER (2026-10-04): PHASE 4 VERDICT: INFEASIBLE (final under the 2026-10-04 rulings). The D4
  execution (OP-1 + OP-2) is consumed. No safe Claude step remains in Phase 4 or in Phase 7's independent work.
  Before it: AT THE OWNER (2026-10-04): Phase 4 is prepared and the verdict is CONDITIONAL. The boundaries are
  methodology and protected-evidence ones: OP-2's D4 execution (the real H), F3's exact scope, and the
  staleness option.
  Before it: IN PROGRESS (2026-10-04): PHASE 3 CLOSED (the exit is MET). Phase 4 is advancing under P4-1 and P4-2,
  with Phase 7's independent work under P7-1 (passive measurement and design only).
  Before it: AT THE OWNER (2026-10-04): the E2 cutover is ACCEPTED (ucpe_space_db, DESIGNED). The boundary is
  the owner's consolidation (secret steps). Claude meanwhile prepares the Phase 3 exit and Phase 4/7 work.
  Before it: AT THE OWNER (2026-10-04): E2 RELEASED (D 1caa8b08, R bb2a49bd), and the existing
  SUPABASE_DB_URL role is identified (the migration owner; G2 CONFIRMED). The boundary is the owner's cutover
  (credential and Space secret steps).
  Before it: IN PROGRESS (2026-10-04): E2 LIFTED by the owner. Its package is this record's PR. Next:
  the E2 release chain, up to the owner's T4 deploy.
  Before it: AT THE OWNER (2026-10-04): D6 COMPLETE. The Phase 3 exit is NOT MET IN FULL only because E2 is
  DEFERRED (X1 PASS, X2 PASS, X3 NOT DEMONSTRATED). No safe Claude step remains in Phase 3.
  Before it: AT THE OWNER (2026-10-04): D6 is APPLIED (run 37172530166, committed, adjudicated from the raw
  report). The boundary is the read-only inventory with expect=after.
  Before it: AT THE OWNER (2026-10-04): 0018's T4 attempt (run 37170407623) was REFUSED, NOT_APPLIED and is
  consumed. The route is repaired by this record's PR. The boundary is a NEW T4 at the repaired commit.
  Before it: AT THE OWNER (2026-10-03): D6 is FROZEN (migration 0018 with its route and gates, merged by
  this record's PR). The boundary is the owner's one-shot T4 apply of 0018. Nothing is applied yet.
  Before it: IN PROGRESS (2026-10-03): E3 LIVE_PROVEN; the D6 inventory is CLEAN (run 37149774863). Claude
  prepares 0018's freeze (migration, rollback, one-shot route, gates). Nothing is applied before the owner's T4.
  Before it: IN PROGRESS (2026-10-03): C4 SET (verified by name). The D6 production-inventory route is a DRAFT PR, never
  dispatched. E3 is read passively; D6 waits for E3's natural proof.
  Before it: AT THE OWNER (2026-10-03): UCPE-PROD-R1A-20261003-A is RELEASED and its chain is complete (R d4c25f2a). G1 is
  LIVE_PROVEN, and #206 closes with this record. The owner's next step is C4's Environment (a card). E3 is read passively;
  D6 stays PREPARED.
  Before it: IN PROGRESS (2026-10-03): G1 SET. G1 and E3 each await a natural proof, read passively. This record's PR
  (a draft) completes G1 and prepares C4. It merges after G1's proof, by an owner Run action if Auto refuses.
  Before it: AT THE OWNER (2026-10-03): E3 SWITCHED; the least-privilege writer is CONFIGURED, NOT_YET_LIVE_PROVEN
  (verified read-only at 12:57Z; .work/e3_cutover; 0 natural receipts at 13:32Z). G1 is PREPARED (#204, R1 PASS ×2).
  The owner has one Run action (merge #203 and #204), then G1's secret steps (docs/runbooks/RESOLVER_CUTOVER.md).
  Before it: IN PROGRESS (2026-10-03): E3 SWITCHED by the owner. The least-privilege writer is CONFIGURED,
  NOT_YET_LIVE_PROVEN (verified read-only at 12:57Z; .work/e3_cutover). Claude confirms the first natural receipt
  passively and meanwhile prepares the resolver cutover (G1). No owner action is pending.
  Before it: AT THE OWNER (2026-10-03): E3-A YES and E3-B 30 days are ruled. The signing-key helper and the repaired
  runbook are in this record's PR (no real key or token was created). Next is the owner's credential switch
  (docs/runbooks/WRITER_CUTOVER.md), by one owner card.
  Before it: AT THE OWNER (2026-10-03): UCPE-PROD-WA-20261003-A is RELEASED and its chain is complete (R 4130a6cd). Next is
  E3's credential switch: the decisions E3-A and E3-B, then the owner's secret steps (docs/runbooks/WRITER_CUTOVER.md).
  Before it: IN PROGRESS (2026-10-03): the §2.6 package (#196) and E3's executable proof (#197) are merged. Next is the
  release package UCPE-PROD-WA-20261003-A through the B4 chain: identity → D → push CI and B3 → the guard on D →
  the rollback findings → the re-pin precomputed twice → preflight review and accept. Then the owner's T4.
  Before it: IN PROGRESS (2026-10-03): migrations 0016 and 0017 are APPLIED (runs 37110330500 and 37110375659, both
  adjudicated), and the registry records both. Next:
  - the §2.6 package: E4 plus the W-A client;
  - E3's executable proof;
  - then the release package, up to its T4.
  Before it: AT THE OWNER (2026-10-03): migrations 0016 and 0017 are merged with their one-shot T4 packages. Main is
  frozen at this record's merge for the dispatch. The owner's one Run action applies 0016, then 0017 only if 0016
  succeeded. Nothing is applied yet. The rulings E1-E4, WB1 and WB3 are answered (verbatim in the header).
  Before it: AT THE OWNER (2026-10-03): RCPT is RELEASED and its chain is complete (R 06e4733e). Next are the batched
  Phase 3 decisions E1-E4, WB1 and WB3.
  Before it: IN PROGRESS (2026-10-03): the release package UCPE-PROD-RCPT-20261003-A (the receipts #182 + W-B #185) goes
  through the B4 chain: identity → D → push CI and B3 → the guard on D → the rollback findings (target f046140b over
  D) → the re-pin precomputed twice → preflight PASS. Then AT THE OWNER, for the T4 deploy and the batched decisions.
  Main is frozen at D until the deploy, or until the owner abandons the package.
  Before it: IN PROGRESS (2026-10-03): Phase 3, in the owner's priority order. Receipts are merged. Next:
  - the privilege rehearsal (P3-PRIV-R) on scratch PostgreSQL. The draft roles stay outside migrations/, so release
    check 5c is untouched;
  - then the wider §8.1 bundle design (T0);
  - then the batched owner boundary.
  Before it: AT THE OWNER (2026-10-02): B9 is RELEASED and the chain is complete. The remaining Phase 3 items
  (three-state receipts, the privilege and role design, the wider §8.1 bundle, S8 recovery) each need an owner
  decision or design ruling.
  Before it: IN PROGRESS (2026-10-02): T4-2, the B9 app release, is being prepared through the B4 chain: identity → D →
  CI/B3 → guard → rollback binding → re-pin precompute → preflight → deploy (T4) → settle → rollback-check → re-pin →
  guard. Migration 0015 is applied (T4-1 consumed).
  Before it: AT ONE OWNER DECISION (2026-10-02): RD-1, how B9 reaches the REST writer (R2a recommended, or R1).
  M1 is CONFIG_PROVEN (REST). The Postgres B9 is not implemented, because D2's condition failed.
  Before it: AT ONE OWNER ACTION (2026-10-02): M1 needs one analysis in the app. Claude then resumes automatically:
  D1, then B9 per D2, or the REST design. S8 is verified, the D4 note is sealed (HOLD), and D3 is NO FOR NOW.
  Before it: AT THE OWNER DECISION PACK (2026-10-02): D1 M1 (one log line), D2 the B9 §2.6 crossing, D3 the
  F1-artifact
  ruling (UX-1), D4 FEAS-1 real-data authorization. The decision-free work is exhausted for the critical path.
  Before it: IN PROGRESS (2026-10-02): OBS-2 is released. Next: PERS-0, the §22 item 7 persistence
  fault-injection
  measurement on scratch PG.
  Before it: IN PROGRESS (2026-10-02): SEC-1 is released.
  - Next: REL-1, the release tooling's cache-bust rule.
  - UX-1 waits on the owner's F1-artifact ruling.
  Before it: AT THE OWNER'S RUN ACTION (2026-10-02): the SEC-1 deploy.
  - The package is frozen and gated. Auto refused the exact command.
  - Main stays at 51a15fd0 until the deploy and its re-pin.
  - Continuing after it: settle, rollback-check, re-pin (258b969c), guard; then UX-1; then this record.
  - **ROADMAP-SEC1-FEAS1-A (2026-10-02; owner AUTO standing authorization; Codex paused; Claude implemented and
    reviewed; deterministic gates).**
  Before it: ENVELOPE COMPLETE (2026-10-02): OBS-1 is released, migration 0014 is applied, and both are adjudicated.
  Main is 93c55f97. Nothing is in flight. F1 is CLOSED and delegated to the UOR thread.
  - **PHASE3-T4-0014-OBS1-A (2026-10-02; owner standing authorization; T4s approved by the owner in Manual mode).**
    - 0014: run 36952902214, APPLIED (44/44). OBS-1: DEPLOY, SETTLE, ROLLBACK_CHECK and GUARD all PASS.
    - Re-pin #162 → 00b6fa94; registry #163 → 93c55f97.
  Before it: PAUSED AT OWNER T4 (2026-10-01).
  - The 0014 apply route (#159) and the OBS-1 release identity (#160) are merged.
  - Both T4s (the 0014 production apply; the OBS-1 deploy) are frozen and gated. The auto-mode classifier refused both
    before execution.
  - Production is unchanged (D2 5a3ef022); 0014 is UNAPPLIED. Main stays at D 46a1de68 until both T4s complete.
  - F1 is CLOSED and delegated to the UOR thread.
  - **PHASE3-0014-ROUTE-OBS1-RELEASE-A (2026-10-01; owner standing authorization; Codex paused; Claude implemented
    and reviewed; deterministic and real-PG gates).**
    - The route: #159 → 3e69430e (rehearsal PASS on 9630d19, run 36908039753). The identity: #160 → 46a1de68.
    - The release package is bound: preflight PASS (expired); rollback D2 PASS; re-pin c82822e0 precomputed.
  Before it: IN PROGRESS: the UCPE roadmap, Phases 2-3. B2, B4, B3, LOW-1, OBS-1 and DBI-1 are merged (no deploy).
  Next: the 0014 one-shot apply route, then its single production apply (owner standing authorization,
  conditional), then the OBS-1 release package. F1 is CLOSED and delegated to the UOR thread.
  - **PHASE2-OBS1-DBI1-A (2026-10-01; owner T3 authorization in Manual mode; Codex paused; Claude implemented and
    reviewed; deterministic gates).**
    - OBS-1: #156 → c44da688. DBI-1: #157 → 05a5d1ad (0014 rehearsal PASS; 0014 UNAPPLIED).
    - The resolver's candle check is live; production is unchanged.
  Before it: IN PROGRESS: the UCPE roadmap, Phase 2. B2, B4, B3 and LOW-1 are merged (no deploy); the next lane
  starts from fresh main 52965cc2. F1 is CLOSED and delegated to the UOR thread.
  - **PHASE2-B3-LOW1-A (2026-10-01; owner T3 authorization; Codex paused; Claude implemented and reviewed;
    deterministic gates).**
    - B3: #153 → d9e42a60 (REPRODUCIBLE=PASS on the exact head and on main). LOW-1: #154 → 52965cc2.
    - OD-DB-1 = D. Writer transport: UNKNOWN.
  Before it: IN PROGRESS: the UCPE roadmap, Phase 2. B2 and B4 are merged; B3 (reproducible build) is next. F1 is
  CLOSED and delegated to the UOR thread.
  - **ROADMAP-RESUME-A (2026-10-01; the owner's routing update and OD rulings; Codex paused; Claude implemented and
    reviewed; deterministic gates).**
    - B2: #150 → fc441c52. B4: #151 → fdfefd2c. No deploy.
    - Writer transport: UNKNOWN (session-gated; an owner-run M1 is prepared).
  Before it: PAUSED AT THE UOR-SIDE BOUNDARY. F1 is live and proven on the UCPE side (F1_CANARY=PASS,
  LIVE_ISOLATION=PASS), and the governed handoff package is finalized. UOR's activation happens in its own
  sessions.
  - **F1-CANARY-A (2026-10-01; the owner issued uor-radar-2026-10 and ran the canary; Claude adjudicated read-only
    and finalized the package).**
    - The canary: HTTP_PASS 13/13; Claude's independent re-check: 12/12.
    - The owner's SQL: the ledger row exact, predictions 0, global isolation 0.
    - The package: UOR_HANDOFF.md plus the LIVE_SAVED example. The local bundle
      (.work/f1_release/uor_handoff_package/) is built from main after this record merges.
  Before it: PAUSED AT THE OWNER BOUNDARY: the credential issuance (F1 released, re-pinned and enabled; no
  credential).
  - **F1-ENABLE-A (2026-10-01; the owner set UCPE_AUTOMATION_ENABLED=1, a T3; Claude ran read-only checks only).**
    - post_enable_check_f1.sh: ENABLE_CHECK=PASS 7/7. readonly_extra_checks_f1.sh: 5 PASS and 1 STOP (CORS).
    - F1-ACT-1 (LOW) adjudicated. The owner chose option A: the contract was corrected (this record), and the
      corrected check now passes 6/6.
  Before it: F1 released and re-pinned (production D2 5a3ef022, guard HEALTHY), the route OFF, no credential.
  - **F1-RELEASE-A (2026-10-01; the owner's prompts: CODEX_PAUSED_BY_OWNER; a Claude adversarial merge gate;
    the standing authorization for the deterministic T3/T4 chain; Manual permissions for the re-pin).**
    - The chain:
      1. M 5da10ef3 (PR #144);
      2. the 0013 apply PASS (run 36820986264);
      3. D2 5a3ef022 (PR #145), with the guard HEALTHY on D2 (36825556001);
      4. the precheck 7/7, one push to hf, and the settle checks PASS;
      5. the re-pin: P 4ef8f145, merged as R 3ad53b87 (PR #146);
      6. the guard HEALTHY on R (36828594390), delta [].
    - Evidence: .work/f1_release/ in the main checkout (apply_0013/, deploy/, guard_repin/; read-only).
    - The activation kit (local; nothing executed): .work/f1_release/activation/.
  Before it: IN PROGRESS: F1 merge gate. Final independent Codex review (review 3) on this head, then merge if
  clean, then 0013 T4 preparation from M. Stop at the 0013 production apply boundary.
  - **F1-MERGE-GATE-A (2026-10-01; the owner's prompt: finish the review, repair, capacity contract,
    merge under standing authorization, prepare the 0013 T4, return at the apply boundary).**
    - Review 2 (Codex, eb6976d): run once fully. A first attempt was killed and left no report; its
      log is kept in scratchpad p1/f1-delegations. Verdict NEEDS_DECISION: R2-01..04 MEDIUM, R2-05..09
      LOW.
    - The capacity contract 8b22efe (built in worktree lanes12/f1cap while review 2 ran, then
      fast-forwarded).
    - The consolidated repair 8f7923c: one commit for R2-01..09 (see the header).
    - Then this record. Review 3: .work/task-f1-review3.md, report .work/f1-review3/REVIEW.md.
    - The merge rule: exact-head merge commit, only with review 3 clean, VERIFY and the scanners
      PASS, the 0013 real-PG rehearsal PASS, the human-route and non-cohort suites PASS, and main
      still f19d7575.
  - **F1-MERGE-READINESS-A (2026-09-30; the owner's prompt: G2 accepted; G6 provisional at 6 per 5 minutes and 120 per
    day, not an activation or spend approval; do not merge, release or enable).**
    - PR: verified 446260c16cd21fb972082d6e94b702f55803e6d7 = main f19d7575 + 4 commits.
      - Pushed without force → draft PR #144 (base main, not merged). CI on 446260c: success.
      - d9df2371: the merge-readiness commit, pushed as a fast-forward.
    - (a) Rotation and revocation: DB registry public.automation_credential (0013).
      - It is read per request with no cache; bounded (2 s timeouts; at most 2 reads in flight, refused not queued);
        fail closed (503 LEDGER_UNAVAILABLE, no row).
      - The env credential path is removed. Owner procedure: docs/automation/CREDENTIAL_ROTATION.md (issue, rotate
        and revoke are owner T4 SQL).
    - (b) The retention and idempotency audit: docs/automation/RETENTION_AND_IDEMPOTENCY.md.
      - At least 90 days; no automated purge (a test scans for one); idempotency per credential for the row's
        lifetime.
      - Capacity: about 150 MB/year at the G6 maximum, so a future purge route is an owner item (not a merge
        blocker).
    - (c) The 0013 apply route: scripts/apply_migration_0013.py.
      - attest / rehearse / apply; the pinned digest; advisory lock 5000013; pre-checks make a second apply refuse.
      - Post-checks cover both tables: columns, constraints with literal and integer sets, indexes, RLS, privileges,
        no row, no FK or trigger, and every existing table's security unchanged.
      - .github/workflows/apply-migration-0013.yml is dispatch-only; the rehearsal runs before the one secret step.
      - .github/workflows/apply-migration-0013-rehearsal.yml runs on PRs with no secret.
    - (d) Tests: hazards, reapply, refusals, RLS and privileges.
      - Unit: tests/scripts/test_apply_migration_0013.py (97), tests/workflows/test_apply_migration_0013_workflow.py,
        tests/migrations/test_automation_radar_ledger_migration.py.
      - Real PG: scripts/migration_0013_rehearsal/probe_app_sql.py and 20_assert_api_roles_refused.sql.
    - (e) Transport fail-closed: tests/automation/test_transport_fail_closed.py.
      - Nothing connects at startup; refused callers never reach the database; prepare_threshold=None (the
        transaction pooler); 503 when the database is missing or unreachable.
      - The Space's connectivity is NOT assumed. The human persistence reaches the database (W26 PASS_PROVEN); the
        route's own connections stay unproven until the canary.
    - Release, apply, canary and handoff prep: docs/automation/F1_RELEASE_PLAN.md (owner-gated, nothing executed).
      UOR_HANDOFF.md pins the new docs.
    - Real-PG proof: PR rehearsal run 36747080987 at d9df2371: success (see the header).
    - Found and fixed: the 0013 ledger CHECKs passed on NULL (arl_success_shape accepted a SUCCEEDED row without its
      run id or hashes). They are now guarded by IS NOT NULL and proven on real PG.
    - OPEN: the mandatory independent Codex security and adversarial review. Task:
      scratchpad/lanes12/f1/.work/task-f1-review2.md. BLOCKED by the Codex usage limit until about 19:35Z.
      **Never substituted.**
  - **F1-GOVERNED-AUTOMATION-LOCAL-A (2026-09-30; the owner's pasted prompt; local T0/T1/T2 only).**
    - Source: UOR's proposal files 04 and 05 in UCPE-Radar/.work/HANDOFF_FINAL_PHASE, read only. The owner-only
      grading key and the trap prompt were NOT opened. UCPE canon wins.
    - Commits on feat/f1-governed-automation (from main f19d7575; local):
      - 028ded8: the implementation;
      - 4f9ae93: the test suites, examples and docs;
      - 0bc11ff: the review repair;
      - this STATE record.
    - Design: see docs/automation/RADAR_EVIDENCE_V1.md.
      - The route is POST /v1/automation/radar-evidence, off by default.
      - Route-only machine auth: the header X-UCPE-Automation-Credential, SHA-256 digests only, compared in constant
        time. Human session cookies are refused (403), and machine credentials get 401 on all 14 human
        method-paths.
      - The origin is server-stamped AUTOMATED_RADAR, in the isolated automation domain.
      - The contract is strict radar_evidence.v1 plus radar_evidence_error.v1 (schema sha256 pins), with RFC 8785
        JCS for the evidence_hash and the wire bytes.
      - Deadlines run to the ledger commit. Quota is 6 per 5 minutes and 120 per day by default (owner G6). One
        analysis slot.
      - Strict idempotency and audit live in the isolated ledger (migration 0013).
      - The kill switch is UCPE_AUTOMATION_ENABLED.
      - The handoff is docs/automation/UOR_HANDOFF.md: every file with its digest, plus two synthetic examples and
        one error example.
    - analysis_service: analyze_request keeps its exact signature. Its body moved into _analyze, and the new
      analyze_request_isolated takes no origin, run store, pair or cadence. It never builds a prediction row or
      parks persistence.
    - Tests: 325 automation and migration tests (Codex D1 plus Claude). They cover isolation, security, refusals,
      idempotency, quota, deadlines, the hashes, JCS vectors, human-route non-regression and the examples.
    - Codex delegations:
      - D1, the tests: DONE; one spec clarification (the full build-info payload).
      - D2, the adversarial review plus the cohort-reader audit: 10 findings (F1 HIGH; F2-F6 MEDIUM; F7-F10 LOW),
        all repaired in 0bc11ff. The audit verdict is that sharing AUTOMATED_RADAR would leak through generic
        readers; it is kept as docs/automation/COHORT_READER_AUDIT.md.
      - D3, the test updates: FAILED on the Codex quota and changed nothing. Claude did the work.
      - The delta review is NOT_RUN (quota), replaced by Claude's diff review plus the regression tests.
    - Residual, honest:
      - the Postgres ledger path is fake-connection tested only: NOT_RUN on real PostgreSQL;
      - SUPABASE_DB_URL on the Space is unverified;
      - the deadline compares the app clock with the database clock;
      - there is one analysis slot per app process.
    - Pin boundary: NONE required. Evaluator-pinned files touched: 0.
    - NOT_RUN / not done: push, PR, deploy, enablement, credential issuance, the 0013 apply route and its apply, any
      UOR mutation.
  - **W26 RELEASE CLOSED (2026-09-30): the CONTROLLED_SMOKE is PASS_HTTP and the DB proof is PASS_PROVEN. Both are
    CONSUMED and never rerun.**
    - Run directory: .work/w26_smoke/run_20260930T124617Z. The marker .work/w26_smoke/EXECUTED names it, so the
      smoke is CONSUMED and never runs again.
    - Integrity, verified before adjudication:
      - MANIFEST.sha256 25/25 with nothing unlisted; the tool seal W26_SMOKE_TOOLS.sha256 8/8;
      - the run pins EXPECT_SHA = D 2096af6d… and EXPECT_GUARD_RUN = 36715108033; the executor sha256 equals the
        sealed 2e08a59f…;
      - no secret leakage: the login and logout bodies are {"ok"} only, with no echo; no cookie or token string in any
        file; the jar is deleted; the only "code" keys are the enums SKILL_NOT_DEMONSTRATED and RUN_NOT_FOUND.
    - Route (run.log), one pass: every pre-check OK; one login (200); S (200); detail 404 RUN_NOT_FOUND; /v1/runs 200
      (S not listed); logout 200.
    - Sealed adjudicator: **PASS_HTTP**, with 27 PASS, 5 INFO and 0 ERROR/FAIL.
      - Schema-valid, and no stamp key anywhere in the response.
      - hard_gate_passed false, with the SKILL_NOT_DEMONSTRATED block; disposition NO_TRADE; no candidate label.
      - The probabilities sum to 1 on both horizons. Legacy verdict INSUFFICIENT_EVIDENCE (n 0), so there is no hold
        key and the ordinary text appears.
    - run_id run_af48fd1e0dea4e69a231b64d6569cc63; request window 12:47:23.840027Z .. 12:47:29.547042Z (operator
      clock).
    - Expectation, an inference and not proof: data_quality.data_source is OKX_PUBLIC (single-provider fallback;
      cross_provider_state UNAVAILABLE) with live data, so the row should carry a tc-v1 stamp.
    - DB PROOF (pack §6): run once by the owner in the Supabase SQL editor, with DB_READ_FILLED.sql (pack §6 byte for
      byte, only the literal filled; sha256 4b712902a7bb94a8411977da58832e8a1c4334903464e5086f247ce8284f9742).
      - The untouched CSV, /Users/kha/Downloads/Supabase Snippet Untitled query.csv (257 bytes, sha256
        cd3e04cc48b82f2105498fcddd8dcdeb1834a5f60096e0cc1f1c37e44f7470ae), is copied byte-identically to
        .work/w26_release/W26_DB_READ.csv (0444).
      - One row: CONTROLLED_SMOKE, tc-v1, OKX_PUBLIC.
        - core_computed_at_utc 12:47:28.904687Z and issued_at_utc 12:47:28.907957Z, both inside the logged request
          window: 5.06 s after its start and 0.64 s before its end.
        - i1_asof_le_core, i1_core_le_issued, i3_time_left and i8_venue_ok are all true.
      - The sealed adjudicator, with the tools and run manifest re-verified first:
        - D1-D7 MET;
        - D8 (the NOT_EXERCISED shape) and D9 (the listed FAIL cases) NOT_MET;
        - D_OUTCOME PASS → **PASS_PROVEN**, recorded in ADJUDICATION_DB_READ.json in the run directory.
    - Operational PASS only, not directional or model evidence.
  - **TC-V1-STAMP RELEASE EXECUTED (2026-09-30; the owner's standing authorization of the prepared chain).**
    Raw evidence: .work/w26_release/exec/ (one directory per consequential step), deploy/precheck_20260930T122340Z
    and deploy/settle_20260930T122426Z.
    - IDENTITY (T3), with the PR merged by Claude:
      - pushed 0c015a59 without force → PR #141; CI run 36713563857 succeeded on the exact head;
      - the pre-merge checks passed: the head, MERGEABLE and CLEAN, base 86c9496f, merge tree 68917d99;
      - merged with a merge commit (--match-head-commit) at 12:19:50Z → D =
        2096af6d1b3d54461b40c47fd96c265882e5af40, parents 86c9496f + 0c015a59, tree 68917d99;
      - push CI on D: run 36714014523 succeeded.
    - PRE-DEPLOY GUARD: one dispatch, run 36714103648 on D. HEALTHY in all 3 rounds, delta [AS, BI], pin = live =
      080f20a9.
    - DEPLOY (T4, CONSUMED; never rerun):
      - the precheck passed 7/7, including the authenticated dry run;
      - one push at 12:24:01Z, `git push hf 2096af6d1b3d54461b40c47fd96c265882e5af40:refs/heads/main`:
        rc 0, `080f20a..2096af6 -> main`; hf/main = D.
    - SETTLE: PASS.
      - RUNNING at D on the first poll (12:24:26Z); health 200.
      - build-info UCPE-PROD-TC-V1-STAMP-20260930-A, with its fingerprint.
      - The GET /, app.js and styles.css digests are unchanged.
      - A confirmation probe at 12:25:12Z agreed. No rollback condition arose, and no rollback ran.
    - RE-PIN (T3), with the PR merged by Claude:
      - P = 24c66816e938550015bec3daebd75e472393db86, tree 1a0aa6df, parent D, authored by UCPE release at D's commit
        date. Built by make_repin_commit.py.
      - Exactly the 17 expected lines were added. VERIFY=PASS 3999.
      - The first push attempt failed without pushing: zsh's :r modifier broke `$P:refs`. The literal-SHA push
        created release/prod-tc-v1-stamp → PR #142.
      - CI run 36714701041 succeeded on the exact head. Merged at 12:29:19Z →
        main 6becb1002ed6517122f58a40c09f92ad4f602f9b; its tree 1a0aa6df equals merge-tree(D, P).
    - POST-RE-PIN GUARD: one dispatch, run 36715108033 on 6becb100. HEALTHY in all 3 rounds; delta [];
      hf_main_sha = pinned = D; live release UCPE-PROD-TC-V1-STAMP-20260930-A.
    - SMOKE TOOLS SEALED:
      - EXPECT_SHA = D and EXPECT_GUARD_RUN = 36715108033;
      - the 127.0.0.1-only dry run met every expectation;
      - .work/w26_smoke/W26_SMOKE_TOOLS.sha256, sha256
        26ae7064f8dbe8e087fd20b9deedb8fb3d30eda7f3fc49a789f1b962e6ee6214; the tools are read-only.
    - NOT_RUN: the real CONTROLLED_SMOKE (the owner enters the access code) and the one-row DB read.
    - PIN_DRIFT window: 12:24:01Z → 12:29:19Z. No scheduled guard run fell inside it: at 12:29:52Z the latest guard
      run was still the pre-deploy dispatch 36714103648.
    - Operational PASS only. It is not directional or model evidence: the H2 hold and every skill gate are unchanged.
  - **RELEASE IDENTITY PREPARED LOCALLY (2026-09-30; the owner's pasted prompt authorized local-only identity prep).**
    - The owner merged #140 (the STATE repair) at 10:39:37Z, giving main 86c9496f, whose tree equals the recomputed
      merge. CI succeeded (run 36703760641). The owner closed #139 UNMERGED at 10:39:50Z. #138 (W26) had merged
      earlier (d790e0ff).
    - IDENTITY: prep/release-identity-tc-v1-stamp = main 86c9496f + e7309c31878626096af8aa68d2b776418671f7b6.
      It changes exactly three non-STATE files, mirroring precedent 2b575abb:
      - config/build_info.py: RELEASE_ID UCPE-PROD-TC-V1-STAMP-20260930-A; RELEASE_LABEL "PROD-TC-V1-STAMP release of
        main"; SOURCE_MILESTONE prod-tc-v1-stamp. The fingerprint is derived: UCPE LIVE BUILD ·
        PROD-TC-V1-STAMP-20260930-A.
      - tests/api/test_build_info.py: the three asserts.
      - tests/scripts/test_source_integrity_guard.py: CURRENT_DELTA_PATHS = [src/crypto_probability_engine/api/
        analysis_service.py, src/crypto_probability_engine/config/build_info.py]. PIN_SHA (080f20a9), the
        pinned-identity asserts and ops/hf_runtime_baseline.json are unchanged.
      - scripts/check_build_info.py: PASS. VERIFY=PASS 3999 on e7309c31.
      - Codex review: DONE (read-only, high effort, base a20a46c9): (1)-(5) PROVEN; findings NONE. The reviewer did
        not independently verify PR closure timestamps, CI or live deploy status.
      - Blob sha256 at e7309c31, for the re-pin: build_info.py 96625788be27ef127d42ecbd7bbbcf3c7bf1f0ff5265c35103600f9487ec1412;
        analysis_service.py cff4c98e7210777dd47eba3c96e30d43e85a1476d651976725dc652ba7ea0306.
    - STATUS:
      - identity PREPARED, NOT_PUBLISHED: its T3 (push, PR, merge) is owner-gated;
      - deploy NOT_RUN;
      - re-pin NOT_RUN;
      - new smoke NOT_RUN;
      - DB read NOT_RUN.
    - Sealed documents (unchanged):
      - .work/w26_release/W26_RELEASE_PACK.md, sha256 a37fc49003d3b377362bd4866d252ad23c74f413518fbc5463af3792d9ce47bb;
      - .work/w26_release/W26_STAMP_SMOKE_CONTRACT.md, sha256 063975a7045f90cff35a3b70826e8c33055661b85f957c3d6b3287f5a3b16570.
    - ROLLBACK: only to 080f20a95241504bd7cf96088bf075d1ebaf4f55 (UCPE-PROD-H2-HOLD-20260927-A, which carries the H2
      hold). 00705c55 is retired.
    - READ-ONLY RELEASE PREP (local, untracked, under .work/; nothing pushed, dispatched or deployed):
      - Deploy tools, hashed in .work/w26_release/PREP_TOOLS.sha256
        (sha256 1a8be7e91e4c40939c971f0aaba0dcac2d33e51fc5f3794eb4bf86aadb7f775a). The operational order is in
        deploy/RUNBOOK.md.
        - deploy/precheck.sh runs pack §3 preconditions 1-7. Check 7, the dry-run push, runs only with RUN_DRY_PUSH=1.
        - deploy/settle.sh polls for RUNNING at D, then runs the five settle checks. It makes no analysis call.
        - repin/make_repin_commit.py builds P from D deterministically (pack §4).
      - Rehearsals, read-only, 2026-09-30:
        - precheck against stand-in Ds: every check passed or stopped exactly as predicted. The check-7 regex matches
          a fast-forward and rejects non-fast-forward and forced pushes; it was proven on a local bare repo only.
        - settle against the live 080f20a9: it stopped only on build-info, as expected before the deploy.
        - re-pin on stand-in D 5094f408 (this branch's pre-amend head): P' 815e3a53, identical on two runs;
          VERIFY=PASS 3999; four negative cases stopped.
      - Smoke tools, drafts under .work/w26_smoke/, hashed in DRAFT_TOOLS.sha256
        (sha256 8e64f3bbc6d946eccf17d14500faadcf2f6918432a9a5fe4fcdbcb2f02848418):
        - drafted by one subagent lane, then reviewed by Claude: the credential path, the marker, the pre-checks and
          the pack §6 rules. Claude made three fail-closed edits: NOT_EXERCISED only on a CONTROLLED_SMOKE row; an
          explicit note when FAIL rules fire under an ERROR verdict; a pre-filled DB_READ_FILLED.sql.
        - Claude re-ran the dry run, 127.0.0.1 only: every expectation met (9 scenarios, 6 DB-read variants, the
          second-run refusal). No non-loopback connection; the real marker is absent.
        - NOT sealed. EXPECT_SHA (D) and EXPECT_GUARD_RUN (G, the post-re-pin guard dispatch) are set after the deploy
          and re-pin. Then the dry run is repeated and W26_SMOKE_TOOLS.sha256 seals the tools.
      - Production snapshot (read-only GETs, 10:59:50Z):
        - the Space is RUNNING at 080f20a9, with build-info H2-HOLD and health 200;
        - GET / 70928eb4…, app.js c683d20a… and styles.css c7be1c9d… equal the pack's settle values;
        - hf/main is 080f20a9 and origin/main is 86c9496f (CI run 36703760641 success). No PR is open.
      - Guard facts:
        - a run concluding success does NOT prove HEALTHY: the guard also exits 0 on TRANSITIONING or
          PROBE_UNAVAILABLE. The tools read the summary JSON in the run log;
        - the latest run is 36674987970 (05:46Z, on b11a8e53): HEALTHY in all 3 rounds, deployment_delta_paths [];
        - precondition 6 needs a HEALTHY run on D with delta [AS, BI]: a scheduled run, or one owner-authorized
          dispatch.
      - zsh hazard, proven: `$D:refs/heads/main` expands wrongly in zsh (the :r modifier). Hand-typed refspecs use
        "${D}:…" or literal SHAs.
    - This record: VERIFY=PASS 3999.
  - **STATE REPAIR AFTER #138 (2026-09-30).**
    - The owner merged PR #138 (W26, 79d43d38) at 09:56:11Z. main is d790e0ff (parents e09dee01 + 79d43d38), with tree
      9de0f067 = the recorded W26-first tree. CI succeeded on d790e0ff (run 36699280110).
      - W26 is on main but NOT deployed.
      - Main's CURRENT_DELTA_PATHS is [analysis_service.py].
    - NOT_RUN: the release identity commit, the HF deploy T4, the re-pin T3, the new CONTROLLED_SMOKE, and the one-row
      DB read.
    - This record is chore/state-w26-repair, from main d790e0ff, with STATE.md the only tracked file changed.
      - It reconstructs by content the intended semantics of #139's head 03e99fb0, plus the local sealed-digest
        record 4f1842e1, and updates only the facts #138 made stale.
      - It was not a wholesale cherry-pick. Main's STATE.md was byte-identical to db8f229a, #139's base, so the
        reconstruction's diff against main equals the intended diff against db8f229a.
      - #139 is superseded, and was neither closed nor modified.
      - GitHub reported #139 MERGEABLE and CLEAN at 10:07Z, but its content described #138 as open.
    - Unchanged, and preserved:
      - the §2.6 what and why;
      - the migration 0011 and 0012 PASS records;
      - the pin closure 212ea637… → 3ffc21e9…;
      - the release-pack and smoke-contract digests (a37fc490…, 063975a7…);
      - the rollback target 080f20a9, and the retirement of 00705c55.
    - This repair: VERIFY=PASS 3999.
  - **W26 RELEASE PREPARATION SEALED (2026-09-30; read-only prep plus two local sealed documents; nothing executed).**
    - `.work/w26_release/W26_RELEASE_PACK.md`, sha256 a37fc49003d3b377362bd4866d252ad23c74f413518fbc5463af3792d9ce47bb
      (read-only; with its .sha256). It covers:
      - the exact identity commit: UCPE-PROD-TC-V1-STAMP-<YYYYMMDD>-A, as in precedent 2b575abb;
      - CURRENT_DELTA_PATHS by step: [] → [AS] → [AS, BI] → [];
      - the HF T4 deploy contract of exactly D: 7 preconditions, including hf/main 080f20a9, a fast-forward, exactly
        8 runtime src files and an authenticated dry run; `git push hf D:refs/heads/main` once, never --force; the
        settle checks, with identity and asset digests;
      - the post-deploy re-pin T3 P (the precedent edc64df2), followed by one guard run HEALTHY;
      - the rollback conditions (a)-(f), to 080f20a9 ONLY (00705c55 retired);
      - the one-row DB-read contract (PASS, NOT_EXERCISED or FAIL);
      - the step order and tiers.
    - `.work/w26_release/W26_STAMP_SMOKE_CONTRACT.md`, sha256 063975a7045f90cff35a3b70826e8c33055661b85f957c3d6b3287f5a3b16570
      (read-only; with its .sha256). It is a NEW CONTROLLED_SMOKE contract:
      - one analysis, BTC 4H METRICS_ONLY;
      - proves the identity, the unchanged response contract (no stamp keys), the H2 hard block, and provenance;
      - PASS_PROVEN only together with the DB read PASS;
      - a new executor and marker under `.work/w26_smoke/`, still to be written, sealed and dry-run. The old
        `.work/h2_smoke/` marker and tools are never reused.
    - The sealed documents are local files. W26 is MERGED (#138 → d790e0ff). This STATE line was first published
      as #139, which is superseded by chore/state-w26-repair.
  - **POST-MERGE RECONCILIATION AND THE W26 T3 (2026-09-30).**
    - The owner merged #136 (RC1 → 200e6ad6, tree 51b7f9a6, the recorded RC1-first tree) and #137 (the STATE record →
      e09dee01, tree 098bddfa, the recorded final tree). CI succeeded on both merge commits (runs 36685512304 and
      36685544014).
    - W26 RECONCILED onto e09dee01 (the owner's pasted prompt: "reconcile … without changing their reviewed semantics"):
      - be4b9939 → 79d43d3838cc345373b4e6d5f7967ca0cab72038;
      - git diff e09dee01..79d43d38 equals git diff f1924495..be4b9939 byte for byte (ignoring index lines);
      - repository.py is still sha256 03ddb511…;
      - no pin drift: the recomputed closure_digest equals the manifest, 3ffc21e93b9f…; assert_evaluator_pin passes;
        membership is identical to main's 69; only closure_digest differs from main; repository.py is the only pinned
        file changed;
      - 959 targeted tests and VERIFY=PASS 3999, both unchanged.
    - T3 CONSUMED: main e09dee01 was verified at 07:48:45Z, and again before the push at 07:54:25Z.
      feat/writer-tc-v1-stamp-w26 was pushed at exactly 79d43d38, with no force.
      - Claude opened PR #138 (PR creation permitted) and did not merge it. The owner merged it at 09:56:11Z →
        d790e0ff.
      - This STATE record, chore/state-w26 = e09dee01 + b4baad10 (the reconciled 0e830b4a, a byte-identical diff) +
        this addendum, was pushed alongside it as #139. It is superseded by chore/state-w26-repair, which carries
        these semantics on main d790e0ff.
    - This addendum: VERIFY=PASS 3917.
  - **W26 EXECUTED LOCALLY UNDER §2.6; RC1 AND THE STATE RECORD PUBLISHED FOR REVIEW (2026-09-30).**
    - T3 CONSUMED (the owner's pasted prompt): origin/main was b11a8e53 (fetch and ls-remote) at 06:10:17Z and again at
      06:10:43Z. feat/resolver-route-c-rq-v1 was pushed at exactly f1924495, and chore/state-post-0011-0012-apply at
      exactly db8f229a, both with no force.
      - PR creation was PERMITTED this time. Claude opened #136 (RC1) and #137 (STATE), bound them to the session,
        and merged nothing.
      - The expected merge trees, recorded before the push: RC1 first gives 51b7f9a6, then 098bddfa; STATE first
        gives 214e7c47, then 098bddfa. The final tree, 098bddfa, is the same in either order.
    - OWNER RULING (2026-09-30): future stamped USER_REQUESTED CROSS_PROVIDER outcomes resolve via the stored
      reference_venue and enter normal USER_REQUESTED evidence. There is no legacy reclassification and no H2 lift:
      the H2 fail-closed hold stays in force.
    - §2.6 AUTHORIZATION (owner, 2026-09-30), verbatim: "execute owner-authorized local §2.6 W26 using the reviewed
      `writer26-on-rc1.patch`: `_insert_prediction` adds `target_version,reference_venue,core_computed_at_utc,
      issued_at_utc` only when all four stamp values are present; every other INSERT must remain byte-identical.
      `analysis_service.py` stamps only eligible genuine rows after row/snapshot construction with the reviewed
      injectable clock; never stamp OOS/SCHEDULED_SHADOW_EVIDENCE. Regenerate evaluator pin via the canonical pin
      writer; 69-file membership must remain identical and only the authorized closure digest may change."
      - WHAT: the pinned persistence/repository.py `_insert_prediction` names the four tc-v1 stamp columns only
        for rows that carry all four values. Every other INSERT is byte-identical, including the OOS
        reject_conflict path.
      - WHY (PIN_CONTRACT.md): production writes through the direct-Postgres repository, whose fixed 25-column
        INSERT silently dropped the stamp. Without the change no prediction could be stored as tc-v1.
    - W26 = feat/writer-tc-v1-stamp-w26 = RC1 f1924495 + be4b99390eb31ed19a6b3bdceb9aadbe19707b30 (9 files).
      - It applies writer26-on-rc1.patch (sha256 3360eca6…). Its pinned and guarded hunks are byte-identical to the
        Codex-reviewed writer26.patch.
      - repository.py sha256 is now 03ddb511…, as predicted before the apply.
      - The pin boundary check: repository.py is the ONLY evaluator-pinned file changed.
      - The pin was regenerated by evaluator_pin.write_pin(). Only closure_digest changed:
        212ea63764663a4e… → 3ffc21e93b9f30c638a44aeca5f00d4b3e2b8643417c7602fa9e9c312fcae540 (as predicted).
        pinned_files (69), entrypoints, declared_surfaces and schema_version are identical.
      - The writer (api/analysis_service.py, runtime-guarded, not pinned) uses the injectable _stamp_clock, captures
        core_computed_at after run_quant_pipeline, and stamps after _prediction_row and both snapshots. It never
        stamps OOS arms or SCHEDULED_SHADOW_EVIDENCE.
      - The N1 allowlist adds analysis_service.py, and CURRENT_DELTA_PATHS = [analysis_service.py].
      - Tests:
        - 959 targeted passed: the new writer and SQL tests, invariance, the red tests (unchanged), the pin, the OOS
          freeze, the runtime guard, N1 and the resolver;
        - three mutation checks were all caught (unconditional stamp columns, partial stamps accepted, the clock
          bypassed);
        - VERIFY=PASS 3999.
      - Codex (be4b9939): (1)-(6) PROVEN, NONE: the pinned change is confined and byte-identical, the pin differs
        only in its digest, the writer's placement and guards hold, there is no H2 or legacy effect, the allowlist
        and delta are right, and the red tests are unchanged.
    - RELEASE PREPARATION (read-only; session scratchpad p1/task-release-prep.md and the lane's report):
      - 0011 is live: run 36583531813 committed the four columns and three CHECKs. W26 therefore needs no further
        migration.
      - Guarded delta: against the deployed pin (080f20a9), be4b9939 differs ONLY in api/analysis_service.py (blob
        sha256 cff4c98e…). The identity bump adds config/build_info.py.
      - Proposed identity (owner decision): RELEASE_ID UCPE-PROD-TC-V1-STAMP-<commit date>-A, label
        "PROD-TC-V1-STAMP release of main", milestone prod-tc-v1-stamp, in a separate identity commit like
        2b575abb.
      - CURRENT_DELTA_PATHS by step: [AS] once W26 merges; [AS, BI] once the identity merges; unchanged after the
        deploy until the re-pin (PIN_DRIFT is expected); [] after the re-pin.
      - ROLLBACK TARGET PRESERVING H2: 080f20a9 (UCPE-PROD-H2-HOLD-20260927-A), which carries the H2 hold
        (calibration/skill.py LEGACY_PASS_LIFTS_HARD_BLOCK False; tests/api/test_h2_failclosed_hold.py).
        - 00705c55 (PROD-SAFE-3) predates the hold and is RETIRED as a rollback target. The two older lines naming
          it describe the rollback of the H2-hold deploy itself.
        - Stamped rows are inert for the Space after a rollback.
      - SMOKE: the old executor refuses a second run through the marker .work/h2_smoke/EXECUTED, which must never
        be edited. A new sealed contract, executor and marker are needed, bound to the new SHA and identity.
        - The minimal run proves the live identity, the response shape (no stamp keys) and the hard block over HTTP.
        - It cannot prove the stamp was stored: the write runs in the background, and no endpoint returns it.
      - MINIMUM DB READ (owner-authorized, read-only): one SELECT of the smoke row, by prediction_id '<run_id>:4H',
        returning origin, the four stamps and the I1/I3/I8 booleans. PASS = one row, tc-v1, a venue label and all
        booleans true. There is also an optional count-only query by origin since the deploy.
    - Not done: no W26 push, merge, deploy, workflow dispatch, DB access, production request, live API, smoke or F3.
  - **PHASE-1 PREPARATION AFTER 0012 (2026-09-29; local only; no T3, T4, pin, deploy, production or F3 boundary
    crossed).**
    - RC1, the Route C resolver: feat/resolver-route-c-rq-v1 = main b11a8e53 + f1924495 (18 files; no pinned,
      runtime-guarded or OOS-frozen file). VERIFY=PASS 3917; Codex review: dc4ec20f drew one LOW finding, L1 (the status counters included CAS-rejected upserts). It was fixed in f241b84e (each upsert RETURNs its id; only applied rows count), whose delta review PROVED (1)-(5) with one LOW docstring note, fixed in f1924495 (docstring only).
      - Every row resolves on contract_v1.resolution_venue.
      - Route C runs with the direct-Postgres repository after a passing preflight. Its due scan is the pinned
        query's semantics, widened to stamped CROSS_PROVIDER tc-v1 rows, with the status LEFT JOIN excluding
        QUARANTINED and backing-off rows before LIMIT.
      - A saved outcome is read back (the new error_outcome_conflict).
      - rq-v1 writes statuses after the run, in one compare-and-set batch. A failed batch gives status_error=1
        and exit 1.
      - The legacy path is unchanged for REST and in-memory repositories.
      - RESOLVER_VERSION is resolver-v2b-tc-v1-rq-v1.
      - It needs no deploy. Merging it (a T3) changes the next scheduled run: route=c, and status rows for
        unresolved exact-venue rows.
    - W26, the writer §2.6 package: PATCH ONLY, never applied. The pinned persistence/repository.py was never
      modified in any checkout (sha256 719f6ece…); ops/** is untouched; write_pin was not run.
      - Session scratchpad p1/writer26/:
        - writer26.patch (sha256 bc84fa80…, against main b11a8e53, 7 files);
        - writer26-on-rc1.patch (3360eca6…, built on RC1 dc4ec20f and applying cleanly on f1924495, 8 files;
          the same pinned hunk, with the allowlist union and the docs merged);
        - PIN_CONTRACT.md: the proposed §2.6 what and why. Only closure_digest changes, 212ea637… → 3ffc21e9…
          (predicted); the 69-file set is unchanged;
        - VALIDATION.md and an out-of-repo harness (77 passed).
      - The pinned hunk: _insert_prediction names the four stamp columns only when all four are present and not
        None; every other INSERT stays byte-identical.
      - The guarded hunk: api/analysis_service.py stamps after _prediction_row and both snapshots, with an
        injectable clock, never for OOS arms or SCHEDULED_SHADOW_EVIDENCE.
      - Codex (W26): all six properties PROVEN; one LOW wording note, fixed.
  - **MIGRATION 0012 APPLIED: T4 APPLY-MIGRATION-0012-ONCE CONSUMED, PASS (2026-09-29).**
    - The authorization came from the owner's pasted prompt: verify origin/main = b11a8e53 and zero prior 0012
      dispatches; dispatch exactly once; any refusal => STOP, NO RERUN.
    - Preconditions:
      - origin/main was b11a8e53 (fetch and ls-remote) at 14:55:09Z and again at 14:55:37Z;
      - apply-migration-0012.yml (id 370217427, active) had zero prior runs (list and API total_count);
      - the 0012 route on main is byte-identical to the reviewed 6ccf60eb;
      - the migration's sha256 is e7f6cbda… and equals the pinned value;
      - CI succeeded on b11a8e53;
      - nothing was queued or running.
    - The dispatch: exactly once, at 14:55:40Z, with expected_sha=b11a8e53… and confirm=APPLY-MIGRATION-0012-ONCE.
      Run 36586262979 (workflow_dispatch, main, attempt 1) completed with success at 14:56:20Z. Every step succeeded:
      - attest: dispatch_verified; CPython 3.13.14; no database;
      - rehearse: PostgreSQL 16 (160015), with 0001-0010 plus 0011. APPLIED once, then refused the second apply
        ("1 relations named prediction_resolution_status already exist in public") before any migration ran. The
        assertions and 31 probes passed on the rehearsal database and on the rebuild without 0011;
      - in-job tests: 437 passed;
      - apply: the only step with the secret;
      - upload.
    - Raw capture before parsing, in the session scratchpad t4-0012/:
      - run.json (sha256 ff4e2700…), run.log (cf03fe53…, 2599 lines) and artifacts.json;
      - the artifact migration-0012-apply-report, id 11041507410; its zip sha256 16f6802c… equals GitHub's digest.
        Inside it: migration-0012-apply-report.json (4ebd293b…) and migration-0012-rehearsal-report.json
        (4f23704a…).
    - The apply report:
      - outcome APPLIED, committed true;
      - the executed migration sha256 equals the pinned e7f6cbda…;
      - server_version_num 170006; 3 API roles; eight table privileges asked, MAINTAIN included.
    - The exact production shape, re-derived by Claude from the raw post reads:
      - Relations in public named prediction_resolution_status, its pkey and its retry index went from 0/0/0 to 1/1/1.
      - The table is ordinary and owned by the applying role, with row-level security on and not forced, 0 policies,
        no PUBLIC or column grant, and NO privilege for anon, authenticated or service_role.
      - Its 13 columns are exactly the adopted ones. The only default is updated_at_utc now(). There is no identity,
        generation or column ACL.
      - Its 9 constraints are the pkey plus 8 CHECKs, all validated, with the exact columns and literals.
      - There is no foreign key into or out of it, and no trigger.
      - Indexes: the pkey (unique, prediction_id), and prediction_resolution_status_retry_idx on (next_eligible_utc,
        prediction_id) WHERE resolution_status = 'RETRYABLE'::text.
      - Row count: 0.
      - The security of all 14 existing tables is unchanged, including predictions.
      - 0011's columns were present before and after, identically.
    - 0011's column types and checks were read by 0011's own post-check (run 36583531813). 0012's statements name
      only public.prediction_resolution_status, as its migration test proves.
    - The log's only connection string is the rehearsal's local socket. The secret appears only masked.
    - NEVER dispatch apply-migration-0012 again: it is consumed, and the route refuses a second apply.
  - **MIGRATION 0011 APPLIED: T4 APPLY-MIGRATION-0011-ONCE CONSUMED, PASS (2026-09-29).**
    - Preconditions:
      - origin/main was b11a8e53 (fetch and ls-remote) at 14:32:28Z and again at 14:33:12Z;
      - the merge trees of #133, #134 and #135 equal e6971e2b, d47aa6e9 and c95d4431;
      - the 0011 route on main is byte-identical to the reviewed 500e5b83;
      - the migration's sha256 is de83e973… and equals the pinned value;
      - the workflow was registered and active (id 370213093), with zero prior runs;
      - CI succeeded on b11a8e53 (run 36580184092);
      - nothing was queued or running.
    - The dispatch: exactly once, at 14:33:16Z, with expected_sha=b11a8e53… and confirm=APPLY-MIGRATION-0011-ONCE.
      Run 36583531813 (workflow_dispatch, main, attempt 1) completed with success at 14:33:59Z. Every step succeeded:
      - attest: dispatch_verified; CPython 3.13.14, isolated; no database;
      - rehearse: PostgreSQL 16 (160015) scratch databases. The route APPLIED once and refused the second apply as
        "not a first apply", before any migration ran. 20_assert_contract.sql passed on the rehearsal database
        and on the rebuild;
      - in-job tests: 261 passed;
      - apply: the only step with the secret;
      - upload.
    - Raw capture before parsing, in the session scratchpad t4-0011/:
      - run.json (sha256 baf6b00f…), run.log (ebedb0b9…, 3605 lines) and artifacts.json;
      - the artifact migration-0011-apply-report, id 11040916714; its zip sha256 0700f54e… equals GitHub's digest.
        Inside it: migration-0011-apply-report.json (b0df023d…) and migration-0011-rehearsal-report.json
        (bf0f6657…).
    - The apply report:
      - outcome APPLIED, committed true;
      - the executed migration sha256 equals the pinned de83e973…;
      - server_version_num 170006; 3 API roles; eight table privileges asked, MAINTAIN included.
    - The exact production delta, re-derived by Claude from the raw pre and post reads:
      - predictions' columns went from 26 to 30. The 26 are unchanged and in order. Appended: target_version text,
        reference_venue text, core_computed_at_utc timestamptz and issued_at_utc timestamptz. All are nullable,
        with no default, identity, generation or column grant.
      - Its constraints went from 2 to 5. The 2 are unchanged. Added, each type c and validated:
        - predictions_target_version_chk ({tc-v1});
        - predictions_reference_venue_chk ({BINANCE_PUBLIC, OKX_PUBLIC});
        - predictions_target_stamp_chk (all four or none; core <= issued).
      - Unchanged: the 5 indexes; the triggers (none); predictions' security (RLS on, not forced, 0 policies, no
        PUBLIC, anon or authenticated privilege, service_role's eight); and the security of the 13 other tables.
    - The log's only connection string is the rehearsal's local socket. The secret appears only masked.
    - NEVER dispatch apply-migration-0011 again: it is consumed, and the route refuses a second apply.
    - Not done: no 0012 dispatch, DB console, manual SQL, deploy or F3. Nothing writes the new columns yet, so every
      row stays v0.
  - **POST-132 (2026-09-29, continuous mode; everything local).**
    - The owner merged three PRs: #130 (chore/state-post-129 → 133c68f6), #131 (N1 → 201bdd22) and #132 (N2 →
      30b40662). Claude verified:
      - each merge tree equals the recomputed merge of its parents;
      - the N1, N2 and STATE content on main equals the pushed heads;
      - CI success on 30b40662 (run 36571791856), 201bdd22 and 133c68f6, and on each PR head.
    - Owner decisions in force:
      - D1 = B;
      - D2: provenance first;
      - D3 = hybrid;
      - D4 rq-v1 and D5 schema 0012: ADOPTED.
    - The earlier local candidates 3433d306 (0011), bc92e873 (0012) and e11ded96 (their STATE record) are
      superseded. They were built on pre-merge ancestry and never published, and are kept on local archive/*
      branches.
    - MIGRATION 0011, rebuilt: feat/migration-0011-provenance = main 30b40662 + 500e5b83. Its diff equals the reviewed
      candidate's except:
      - The file is renamed to migrations/0011_prediction_target_provenance.sql; the content (sha256 de83e973…) is
        unchanged. N1's guard test_nothing_in_the_product_imports_the_target_contract substring-matches
        "contract_v1" in scripts/*.py. That test was not narrowed.
      - docs/TARGET_CONTRACT_V1.md now says 0011 is authored and not applied.
      - The values test imports the merged contract_v1 directly.
      VERIFY=PASS 3221. Codex: on 20fbd542 the delta was PROVEN, NONE; the one-file delta to 500e5b83 was PROVEN,
      NONE.
    - MIGRATION 0012, rebuilt: feat/migration-0012-resolution-status = 500e5b83 + 6ccf60eb. Its diff equals the
      reviewed candidate's except:
      - the renamed 0011 file in its rehearsal;
      - its values test, which now requires N2's SKIP_REASONS and ERROR_REASONS to equal the reviewed keys.
      VERIFY=PASS 3673. Codex: both deltas PROVEN, NONE.
    - Neither package touches an evaluator-pinned, runtime-guarded or OOS-frozen file. No SQL has run on a real
      PostgreSQL. The first real execution is each dispatch job's no-secret rehearsal, before its secret step.
    - The scheduled resolver, read-only, never dispatched: the workflow is active. The latest run is still
      36543287240 on 6fb3e8b4 (due=0); none had run on 30b40662 as of 13:19Z.
    - The writer/resolver integration map (read-only) is summarized in OWNER_BOUNDARY 1. Its key facts, verified
      in code:
      - The Postgres writer's pinned INSERT (persistence/repository.py `_insert_prediction`) names 25 columns and
        silently drops the four stamp fields. Persisting them needs either §2.6 (Route B: a conditional INSERT) or
        an unpinned extraction.
      - Stamping must follow `_prediction_row`: a byte-invariance test calls it twice.
      - Stamping needs an injected clock: a whole-row invariance test compares two runs, and validate_v1's I3
        depends on the current time.
      - The resolver side (Route C) needs no pinned, guarded or frozen file.
    - Not done: no push, merge, workflow enablement, dispatch, DB access, migration apply, deploy, production
      request, live API or F3.
  - **RESOLVER_P1 IS MERGED (post-129, 2026-09-29): PR #129 -> main 6fb3e8b4, merged by the owner at 06:42:05Z (merge
    parents 6f5038d0 + 9de97e0d; its tree 82ed6bad equals the candidate tree recorded before the push). CI success on
    main 6fb3e8b4 (run 36532446966) and on the PR head 9de97e0d (run 36531824106).**
    - The T3 (owner, 2026-09-29) is CONSUMED. Claude verified origin/main = 6f5038d0 at 06:22:38Z, recorded the
      candidate tree and pushed the branch at 9de97e0d (no force). Claude's `gh pr create` was refused by the Claude
      Code auto-mode classifier, so the owner opened PR #129 and merged it in the GitHub UI (a merge commit).
    - §2.6 is CLOSED for publication: the T3 stated the final what and why (RESOLVER_P1).
    - First scheduled resolver run on 6fb3e8b4: NOT_YET_OBSERVED. The latest scheduled run, 36510363045, ran on
      6f5038d0 at 01:57:57Z; there was none on 6fb3e8b4 as of 06:50Z. Scheduled runs arrive every few hours, not hourly.
    - No deploy, workflow dispatch, DB action or F3 access.
  - Pre-merge record (2026-09-29, superseded above): RESOLVER_P1 was a local candidate, feat/resolver-eligibility-phase1b
    = main 6f5038d0 + 517887fc + c7cb70f8 + fb765188 + 35545f4d + 9de97e0d (its STATE-only record).
    - 517887fc (P1-A) is owner-authorized local execution; its read-only closure audit returned LOCAL_MILESTONE_PASS.
    - c7cb70f8 and fb765188 are local unaccepted execution without prior explicit owner authorization. They are never
      to be marked authorized or PASS, retroactively or otherwise (owner ruling, 2026-09-29).
    - The owner later authorized keeping fb765188 only as an unaccepted candidate and prospectively authorized the
      repair that produced 35545f4d. Code PASS on 35545f4d (RESOLVER_P1).
    - §2.6 publication closure was then pending a T3; that T3 is now consumed (above).
  - The chore/state-post-127 record below was published as PR #128 (main 6f5038d0).
  - **THE H2 HOLD IS VERIFIED LIVE: the CONTROLLED_SMOKE returned PASS_PROVEN (2026-09-27).**
    - Production: 080f20a9 / UCPE-PROD-H2-HOLD-20260927-A. The canonical guard dispatch on main 9a1db2dd is HEALTHY
      (run 36310977790).
    - Branch chore/state-post-127 (LOCAL, no upstream), from main 9a1db2dd: this STATE record. NOT PUSHED.
    - The Q5 adjudication stays UNAVAILABLE (below).
  - Smoke adjudication (owner, 2026-09-27T10:27Z; a direct instruction), verbatim:
    "The authorized H2 controlled smoke has run once. Do not make any new production request or DB query. Adjudicate
    only the sealed raw files with the predeclared adjudicator, record the exact terminal state PROVEN / NOT_EXERCISED
    / FAIL / ERROR, run IDs, provenance checks, actions/hold wording, and whether any USER_REQUESTED contamination
    occurred. Then record PR #127 + guard run 36310977790 + smoke result additively in STATE on a fresh branch, verify
    locally, commit only, and stop with the exact SHA." CONSUMED:
    - No new production request or database query: the adjudication read only the sealed raw files.
    - Seals verified:
      - the tools: H2_HOLD_SMOKE_TOOLS.sha256, digest 5a7aa1bc… (executor bebcdab8…, adjudicator 35b02282…);
      - the run's raw files: MANIFEST.sha256, digest e1f5b64d…, 21 of 21 OK;
      - no STOPPED file.
    - The sealed adjudicator, run from a 9a1db2dd checkout: **PASS_PROVEN**, 0 errors, 0 fails.
      - W, 4H, run_32235dd8013547c4ad56ff041926b374: legacy INSUFFICIENT_EVIDENCE (n 0; the cache was cold after the
        restart). The ordinary block "Directional skill has not been evaluated"; NO_TRADE.
      - B1, 4H, run_8acc966078ef4e1d8a823d9e90c573f6: legacy SKILL_DEMONSTRATED (n 164), HELD:
        - the exact hold record {active, EVIDENCE_UNIT_UNDER_CORRECTION, SKILL_DEMONSTRATED}, equal in detail_view;
        - "Directional evidence under review" with the approved detail;
        - NO_TRADE.
      - B2, 1H, run_ef3b3dde9126411fa91e9a47964d8e0f: legacy SKILL_DEMONSTRATED (n 154), HELD, the same way.
      - For all three:
        - hard_gate_passed false, and SKILL_NOT_DEMONSTRATED blocked;
        - no LONG or SHORT candidate, and disposition NO_TRADE;
        - every probability triplet sums to 1.
      - observed_directional_rate was not transcribed.
    - Provenance: /v1/analyze/detail returned 404 RUN_NOT_FOUND for all three runs, and /v1/runs listed none of them.
      There was NO USER_REQUESTED contamination; the 3 prediction rows are CONTROLLED_SMOKE (13 → 16).
    - Result seal: H2_HOLD_SMOKE_RESULT.sha256, digest 52898b3b…. It covers the run manifest, ADJUDICATION.json
      (adbdb84a…) and the adjudicator's output (91103e3e…); all are 0444.
    - **Correction.** Before the run, Claude predicted NOT_EXERCISED.
      - The reasoning: production persists through Supabase REST (per RELEASE_GATE's HF-secrets table), and the
        skill-evidence refresh runs only for the direct Postgres repository.
      - The smoke disproved it: 60 s after W (n 0), B saw refreshed verdicts (n 164 and 154). Production therefore
        runs the SUPABASE_POSTGRES repository, and the table does not describe the live configuration.
      - So before the hold, the legacy 4H and 1H passes COULD lift the hard block in production. The hold now provably
        blocks them.
      - The table discrepancy is recorded for the owner, not changed here.
    - This record.
  - Smoke execution (owner, 2026-09-27T10:08Z; pasted text in the owner's established form), verbatim:
    "CONTINUE CURRENT — Opus 5 XHIGH. Canonical source-integrity guard is HEALTHY on `main` after PR #127. Owner
    AUTHORIZES exactly one execution of the sealed `H2_HOLD_SMOKE_CONTRACT.md`; first verify its seal, canonical main
    `9a1db2dddd117ce832e44bd1a93fd62ed3004a9a`, production/running `080f20a95241504bd7cf96088bf075d1ebaf4f55`, build
    `UCPE-PROD-H2-HOLD-20260927-A`, health 200, and guard HEALTHY.

    Before any request, give me the exact owner execution steps without asking for or displaying the secret: the
    plaintext credential is `UCPE_SMOKE_ACCESS_CODE`, stored in my password manager/secure record; production verifies
    it via `CONTROLLED_SMOKE_CODE_HASH`. Execute only through a session authenticated with that controlled-smoke
    credential. Follow the sealed contract exactly: one BTC 4H warm-up, wait 60 seconds, then one batch containing BTC
    4H and BTC 1H; no extra exploratory calls or retries.

    Capture the raw responses/run IDs before adjudication. Require CONTROLLED_SMOKE provenance, no USER_REQUESTED
    contamination, no directional candidate, and when a legacy SKILL_DEMONSTRATED verdict appears require the exact
    hold record/approved wording. Terminal rules stay frozen: PROVEN if at least one old pass is shown held;
    NOT_EXERCISED if no old pass appears, with no additional calls; FAIL/ERROR on any provenance/behavior mismatch and
    stop immediately. Record the smoke plus PR #127/guard run additively in STATE, verify from a safe worktree, but do
    not push yet. No F3, Q5/methodology change, collector, resolver, deploy or extra DB query."
    CONSUMED (executed once by the owner):
    - Pre-checks (Claude):
      - the contract seal is OK (28f995fb…; seal fe174497…);
      - main 9a1db2dd, with the local main fast-forwarded and clean;
      - production: 080f20a9 RUNNING; /healthcheck 200; build UCPE-PROD-H2-HOLD-20260927-A;
      - the local guard is HEALTHY.
    - Tools, sealed before the run in H2_HOLD_SMOKE_TOOLS.sha256 (0444):
      - the owner-run executor .work/h2_smoke/run_h2_hold_smoke.sh:
        - it reads the credential at a hidden prompt and pipes it to one login, so it is never in argv or on disk;
        - the cookie jar is private and deleted on exit;
        - a one-shot EXECUTED marker is set just before the login;
        - any failure stops and seals the run; the raw files are sealed in MANIFEST.sha256;
      - the adjudicator .work/h2_smoke/adjudicate_h2_hold_smoke.py.
    - A local dry run validated both: 127.0.0.1, fixture data, stateless, test codes, and 4H seeded as
      SKILL_DEMONSTRATED.
      - The seeded run gave PASS_PROVEN.
      - A tampered provenance file gave FAIL.
      - A wrong code stopped at the 401 login, sealed, and gave ERROR.
      - It caught one bug before sealing (a log line appended after the seal), which was fixed.
    - The owner ran it once, 2026-09-27T10:21:23Z to 10:26:47Z:
      - login 200; W 200; the 60 s wait; B 200;
      - detail 404 ×3; runs 200; logout 200.
      The raw files are sealed in .work/h2_smoke/run_20260927T102123Z.
  - Canonical guard verification (owner, 2026-09-27T09:55Z; a direct instruction), verbatim:
    "CONTINUE CURRENT — Opus 5 HIGH. Verify `origin/main` is PR #127 merge `9a1db2dddd117ce832e44bd1a93fd62ed3004a9a`
    and production remains HF/running `080f20a95241504bd7cf96088bf075d1ebaf4f55` with build
    `UCPE-PROD-H2-HOLD-20260927-A`. Then, using only the current canonical workflow/runbook, dispatch exactly one
    source-integrity guard verification on `main` and wait for its terminal result.

    Require the canonical re-pinned baseline to report HEALTHY/PASS with no pending production delta; report exact
    workflow/run identity, commit checked, guard verdict and any warning. No code/STATE change, push, deploy, smoke,
    DB, F3, Q5/methodology, collector or resolver action." CONSUMED:
    - main 9a1db2dd was verified as the PR #127 merge:
      - parents (080f20a9, e4f601fa);
      - tree 16fa5289, the recorded merge tree;
      - exactly the 3 files;
      - the exact-main check CI (run 36310830119) passed.
      Production: 080f20a9, RUNNING, 200, PROD-H2-HOLD.
    - One workflow_dispatch of source-integrity-guard.yml on main: run 36310977790 (job verify 108596704479,
      09:57:06Z to 09:57:53Z), success.
      - final_classification HEALTHY, exit 0;
      - hf_main and pinned are both 080f20a9;
      - critical_source_match and frontend_asset_match are true;
      - the live id is PROD-H2-HOLD;
      - deployment_delta_paths is [].
    - Advisory SCHEDULER_DIVERGENT_FROM_PIN: the shallow CI checkout cannot prove ancestry. It is non-failing.
    - One notice: ubuntu-latest moves to Ubuntu 26 from 2026-10-19.
    - The 3 earlier failed scheduled runs (36272601454, 36283410894, 36306125622) were PIN_DRIFT against 00705c55, in
      the expected window between the deploy and the re-pin.
  - T3 for release/prod-h2-hold (owner, 2026-09-27T08:27Z; pasted text in the owner's established form), verbatim:
    "CONTINUE CURRENT — Opus 5 HIGH. T3 AUTHORIZED once for the completed production re-pin. Verify canonical
    `origin/main=080f20a95241504bd7cf96088bf075d1ebaf4f55`, branch `release/prod-h2-hold` is exactly
    `e4f601fa2f35e3e5a74d9833908b9d74ae5b97bb`, and the complete Git diff is only `ops/hf_runtime_baseline.json`,
    `tests/scripts/test_source_integrity_guard.py`, and `STATE.md`. Reconfirm the baseline names production `080f20a9`
    / `UCPE-PROD-H2-HOLD-20260927-A`, all 11 watched hashes match production, evaluator pin is 0/69, full verify is
    green, and the source-integrity guard is HEALTHY.

    Then push only this exact branch/SHA to GitHub origin, never hf, and stop after confirming the remote branch. No
    PR/merge, Space push/restart, smoke, DB, F3, methodology/Q5, collector, resolver or deploy action." CONSUMED:
    - The pre-push checks passed:
      - origin/main 080f20a9; the branch exactly e4f601fa; the 3 files;
      - the baseline names 080f20a9 / PROD-H2-HOLD, and all 11 watched hashes equal production;
      - evaluator pin 0/69; verify PASS 2470; guard HEALTHY;
      - the merge tree 16fa5289, recorded before the push.
    - Exactly e4f601fa was pushed to origin release/prod-h2-hold, never to hf.
    - PR #127: the head CI (run 36310550050) passed, and it was merged from the owner's account at
      2026-09-27T09:54:04Z (LAST_GREEN_SHA).
  - History (before PR #127 and the smoke): **PRODUCTION IS PROD-H2-HOLD: hf/main and the running commit are
    080f20a9, build UCPE-PROD-H2-HOLD-20260927-A.**
    - Deployed 2026-09-26T19:47:36Z by one non-force fast-forward from 00705c55, RUNNING at 19:48:20Z. The H2
      fail-closed hold is live in the deployed code.
    - The functional CONTROLLED_SMOKE is NOT_RUN. Its contract is sealed, paper only
      (.work/h2_skill_gate/H2_HOLD_SMOKE_CONTRACT.md).
    - **The baseline re-pin is PREPARED LOCALLY:** branch release/prod-h2-hold (LOCAL, no upstream), from main
      080f20a9: edc64df28a22ded3ae56d27a63e4ebc4bfe15dcb (the pin), then this STATE record. It is NOT PUSHED and NOT
      MERGED.
      - Against production, the guard is HEALTHY with the new pin (local read-only run).
      - The committed pin on main still describes 00705c55, so every guard run from main reports PIN_DRIFT until
        the re-pin merges. That is expected and is not an incident.
    - The Q5 adjudication stays UNAVAILABLE (below).
  - Re-pin and smoke contract (owner, 2026-09-27T06:44Z; pasted text in the owner's established form), verbatim:
    "CONTINUE CURRENT — Opus 5 HIGH. Production deploy PASSed at `080f20a95241504bd7cf96088bf075d1ebaf4f55` with build
    `UCPE-PROD-H2-HOLD-20260927-A`; functional smoke is still NOT_RUN. Start a fresh local change from canonical main
    and, following the current source-integrity runbook exactly, re-pin the production baseline to this deployed
    revision/build and the two expected watched-file hashes (`analysis_service.py`, `build_info.py`), clear only the
    changed-but-not-deployed declarations that the runbook permits after deployment, update directly required guard
    tests and STATE, and preserve the full failed-auth/dry-run/deploy history additively.

    In parallel, paper-only, prepare the smallest CONTROLLED_SMOKE verification contract for the live H2 hold: exact
    route/input, evidence class, expected blocked action/hold wording, how to prove the legacy pass cannot lift the
    hard block, what DB/write side effects are expected, rollback/stop conditions, and how to avoid contaminating
    USER_REQUESTED evidence. Do not execute the smoke yet and do not touch F3.

    Run targeted guard tests + full `./verify.sh`, run the source-integrity guard read-only against production, and
    require `HEALTHY` before committing locally. Inspect the final diff, commit locally only on a fresh branch, and
    report exact SHA/files/tests/guard result plus the prepared smoke contract. No push, deploy, DB query/write beyond
    the future smoke plan, or production analysis call." CONSUMED:
    - The re-pin follows .work/816/l1/runbook.md §2 with .work/816/l1/prepare_pin_commit.py, run as a scratch copy
      adapted in exactly 3 places, each asserted to occur once:
      - (1) the declaration anchor, because the guard test now reads `CURRENT_DELTA_PATHS: list[str] = [` and the
        original searched `CURRENT_DELTA_PATHS = [` (0 occurrences, so the original would have crashed);
      - (2) the PROD-SAFE-3 comment text becomes PROD-H2-HOLD;
      - (3) the PROD-SAFE-3 commit message becomes PROD-H2-HOLD, with the Co-Authored-By line.
      The manifest logic is unchanged: R's bytes, read through the guard's own helpers. The original tool
      (sha256 44787d07…) is untouched; the adapted copy is ed264603….
    - Pin commit edc64df2: parent 080f20a9; exactly ops/hf_runtime_baseline.json and
      tests/scripts/test_source_integrity_guard.py; author "UCPE release" with R's date, so it is deterministic.
      - The manifest: hf_main_sha 080f20a9; release_id, label, milestone and fingerprint PROD-H2-HOLD. Only the
        digests of analysis_service.py (c77663f5…) and build_info.py (ab6eb72d…) change; the other 9 and the
        frontend tokens are unchanged.
      - The guard test: PIN_SHA 080f20a9; the identity assertions become PROD-H2-HOLD; CURRENT_DELTA_PATHS becomes
        [], the only declaration the runbook clears after a deploy.
    - Checked independently:
      - the new pin's hf_main_sha equals the fetched hf/main;
      - all 11 guarded digests equal HF main's bytes;
      - the 6 test files that touch the baseline, the guard or build-info passed 113;
      - ./verify.sh PASS 2470 on edc64df2 (LAST_VERIFY).
    - The guard, read-only against production from the re-pin checkout (2026-09-27T06:49:02Z): HEALTHY, exit 0.
      - hf_main and pinned are both 080f20a9;
      - critical_source_match and frontend_asset_match are true;
      - the live release_id, fingerprint and milestone equal the intended PROD-H2-HOLD values;
      - deployment_delta_paths is [], and the advisory is SCHEDULER_AHEAD_OF_PIN (1 ahead). This is what runbook §6
        expects.
    - The smoke contract is sealed (predeclared, not executed): H2_HOLD_SMOKE_CONTRACT.md, sha256 28f995fb…;
      H2_HOLD_SMOKE_CONTRACT.sha256, digest fe174497…; both 0444.
      - Calls: 3 CONTROLLED_SMOKE analyses (a BTC 4H warm-up; a batch of BTC 4H and 1H 60 s later) through the
        controlled-smoke login only.
      - Provenance, in-app: detail must return 404, and the runs must be absent from /v1/runs.
      - Verdicts: PASS_PROVEN, PASS_NOT_EXERCISED, FAIL, ERROR.
      - Declared: CONTROLLED_SMOKE predictions rise from 13 to 16.
    - This record.
  - T4 deploy (owner, 2026-09-26T19:46Z; pasted text in the owner's established form), verbatim:
    "CONTINUE CURRENT — Opus 5 XHIGH. Fresh T4 AUTHORIZED once. The authenticated dry-run already PASSed and proved
    the exact non-force fast-forward `00705c55e7eb291d01b4e02d4cca859122083f28 →
    080f20a95241504bd7cf96088bf075d1ebaf4f55`. Reconfirm immediately before mutation that canonical/local main is
    clean at `080f20a95241504bd7cf96088bf075d1ebaf4f55`, HF main/running is still
    `00705c55e7eb291d01b4e02d4cca859122083f28`, build is still `UCPE-PROD-SAFE-3-20260915-A`, health is 200, and auth
    is beny053.

    If and only if those anchors still match, execute exactly one real non-force push of
    `080f20a95241504bd7cf96088bf075d1ebaf4f55` to HF main. Do not retry or perform a second deploy. After the push,
    perform only read-only settle checks until the Space is RUNNING: HF main and running revision, `/healthcheck`,
    `/v1/build-info` which must be exactly `UCPE-PROD-H2-HOLD-20260927-A`, relevant source/frontend hashes, and the
    local source-integrity guard. Record the earlier FAILED_AUTH/NO_MUTATION attempt and both dry-runs additively for
    the next STATE update. Do not run product-analysis smoke yet; no DB, F3, Q5/methodology, collector, resolver,
    workflow, secret or other production mutation. Report exact deployed/running SHA, runtime/build identity, guard
    result, baseline re-pin requirement and rollback readiness." CONSUMED:
    - Reconfirmed at 19:47:28Z; every anchor matched:
      - origin and local main 080f20a9, and the local main clean;
      - hf/main and runtime.sha 00705c55, RUNNING;
      - build UCPE-PROD-SAFE-3-20260915-A; /healthcheck 200;
      - user=beny053; no guard run in progress or queued.
    - The single push, `GIT_TERMINAL_PROMPT=0 git push hf 080f20a95241504bd7cf96088bf075d1ebaf4f55:refs/heads/main`,
      at 19:47:36Z: exit 0, `00705c5..080f20a  080f20a95241504bd7cf96088bf075d1ebaf4f55 -> main`.
    - Settle: RUNNING_BUILDING at 19:47:59Z, then RUNNING with runtime.sha 080f20a9 at 19:48:20Z.
    - Post-deploy checks (19:49:01Z):
      - /healthcheck 200;
      - /v1/build-info exactly UCPE-PROD-H2-HOLD-20260927-A, the whole payload equal to 080f20a9's;
      - the live index.html, app.js and styles.css are byte-identical to 080f20a9;
      - on HF main, 9 of the 11 guarded files match the old pin, and the 2 declared ones differ;
      - the local guard with the old pin: PIN_DRIFT, exit 1, as expected.
    - Raw captures: .work/deploy-080f20a9/ (ATTEMPT_RECORD.md, sections A to D).
  - Dry-run 2 (owner, 2026-09-26T19:35Z; a direct instruction), verbatim:
    "CONTINUE CURRENT — Opus 5 HIGH. The owner has now used `hf auth switch --add-to-git-credential`; macOS reports
    `HF_GIT_CREDENTIAL=FOUND` and `hf auth whoami=beny053`. Do not deploy. Verify canonical/local
    main=`080f20a95241504bd7cf96088bf075d1ebaf4f55` and production remains HF/running `00705c55` with build
    `UCPE-PROD-SAFE-3-20260915-A`; then run exactly one non-mutating `git push --dry-run hf
    080f20a95241504bd7cf96088bf075d1ebaf4f55:refs/heads/main`. Stop after reporting authentication success/failure and
    the exact fast-forward `from → to`. No real push, deploy, DB, F3, smoke or other mutation." CONSUMED:
    - One `git push --dry-run` at 19:36:37Z: exit 0, `00705c5..080f20a … -> main`.
    - AUTHENTICATED: the push endpoint returns 401 without credentials. The update is a fast-forward, 00705c55 →
      080f20a9.
    - hf/main was unchanged afterwards.
  - Dry-run 1 (owner, 2026-09-26T19:15Z; a direct instruction), verbatim:
    "CONTINUE CURRENT — Opus 5 HIGH. The owner refreshed the HF Git credential. Do not deploy yet. Verify `hf auth
    whoami=beny053`, production is still HF/running `00705c55` with build `UCPE-PROD-SAFE-3-20260915-A`, and canonical
    main remains `080f20a95241504bd7cf96088bf075d1ebaf4f55`; then run exactly one non-mutating `git push --dry-run hf
    080f20a95241504bd7cf96088bf075d1ebaf4f55:refs/heads/main`. Record the prior rejected deploy attempt additively for
    the next STATE update. Stop after reporting whether the dry-run authenticates and would fast-forward. No real
    push, deploy, DB, F3, smoke or other production mutation." CONSUMED:
    - One dry-run at 19:17:27Z: exit 128, "could not read Username for 'https://huggingface.co': terminal prompts
      disabled".
    - NOT authenticated: osxkeychain held no huggingface.co credential. hf/main was unchanged.
  - First fresh T4 (owner, 2026-09-26T18:55Z; pasted text in the owner's established form), verbatim:
    "CONTINUE CURRENT — Opus 5 XHIGH. Fresh owner T4 AUTHORIZED once for exact canonical `main` merge
    `080f20a95241504bd7cf96088bf075d1ebaf4f55`. Before mutation verify origin/local main exact and clean, PR #126 CI
    green, all H2/Q5 seals intact, `hf auth whoami=beny053`, and production is still HF/running `00705c55` with
    `/v1/build-info=UCPE-PROD-SAFE-3-20260915-A`; re-derive the sanctioned deploy path from current
    RELEASE_GATE/STATE/runbook and STOP on any conflict.

    If all pass, deploy exactly `080f20a95241504bd7cf96088bf075d1ebaf4f55` once by the sanctioned non-force
    fast-forward path to HF. Make no DB/secret/F3/Q5/methodology/collector/resolver/workflow changes. Afterward
    perform only read-only settle checks: HF main/running revision, RUNNING state, `/healthcheck`, `/v1/build-info`
    which must be exactly `UCPE-PROD-H2-HOLD-20260927-A`, relevant frontend/source hashes, and local source-integrity
    guard. Do not run an analysis/product smoke yet and do not redeploy/retry. Report exact deployed/running SHA,
    health/build identity, guard state, whether baseline re-pin is required, and the exact remaining
    production-verification boundary." CONSUMED as FAILED_AUTH / NO_MUTATION:
    - Every precondition passed, and the release tool routed the release to a fast-forward.
    - The single push at 18:58:37Z exited 128: "remote: Invalid username or password" / "Authentication failed". The
      stale git keychain credential was the cause; `hf auth login` saves the token for git only with
      --add-to-git-credential.
    - Production was byte-identical afterwards, and the guard was HEALTHY. It was not retried.
  - T3 for prep/release-identity-h2-hold (owner, 2026-09-26T18:31Z; a direct instruction), verbatim:
    "CONTINUE CURRENT — Opus 5 HIGH. T3 AUTHORIZED once: verify `origin/main` is still PR #125 merge
    `fa5c0da7439b926f95c03a8a1e60898e0a9737e5`, branch `prep/release-identity-h2-hold` is exactly
    `8e1b98f09259193ab2357c54c953e336b0b95491`, and the complete diff is only `config/build_info.py`,
    `tests/api/test_build_info.py`, `tests/scripts/test_source_integrity_guard.py`, and `STATE.md`. Confirm build
    identity is exactly `UCPE-PROD-H2-HOLD-20260927-A`, evaluator pin remains 0/69, and verify remains green; then
    push only that exact branch/SHA to origin, never hf, and stop. No PR/merge, deploy, DB, F3, Q5/methodology, smoke
    or production mutation." CONSUMED:
    - The pre-push checks passed; the merge tree 474f4fe1 was recorded before the push.
    - Exactly 8e1b98f0 was pushed to origin prep/release-identity-h2-hold, never to hf.
    - PR #126 was merged from the owner's account at 2026-09-26T18:51:28Z (LAST_GREEN_SHA).
  - History (2026-09-26, before PR #126 and the deploy): **The next production build's name,
    UCPE-PROD-H2-HOLD-20260927-A, is PREPARED LOCALLY.**
    - Branch prep/release-identity-h2-hold (LOCAL, no upstream), from main fa5c0da7:
      - 2b575abb0ad9a3e428bdd669d7a6210eae197272 (the release identity);
      - then this STATE record.
    - It is NOT PUSHED, NOT MERGED, NOT DEPLOYED and NOT LIVE.
  - History (before the deploy): **The H2 T2 fail-closed hold (Q8) is MERGED (PR #125 → main fa5c0da7) but NOT
    DEPLOYED. Q8 is NOT LIVE.**
    - Production is still 00705c55 / UCPE-PROD-SAFE-3-20260915-A. Until a deploy, a cached or shadow-arm
      SKILL_DEMONSTRATED still lifts the hard block in production.
    - The Q5 adjudication stays UNAVAILABLE (below).
  - Release-identity preparation (owner, 2026-09-26T18:04Z; pasted text in the owner's established form), verbatim:
    "CONTINUE CURRENT — Opus 5 HIGH. Production deploy remains NOT_RUN; the prior T4 was not consumed. Prepare a new
    local release-identity change from canonical `origin/main=fa5c0da7439b926f95c03a8a1e60898e0a9737e5`: set the
    production build name exactly to `UCPE-PROD-H2-HOLD-20260927-A`, update only the directly required build-info
    test/source-integrity declaration and STATE record, preserving the fail-closed hold unchanged.

    Preflight the actual files/pin status first; no evaluator-pinned crossing. Record STATE as PREPARED LOCALLY /
    NOT PUSHED / NOT MERGED / NOT DEPLOYED / NOT LIVE, with current production still `00705c55` /
    `UCPE-PROD-SAFE-3-20260915-A`. Run targeted tests and full `./verify.sh` in a safe worktree, inspect the actual
    diff, commit locally on a fresh branch, and report exact SHA/files/tests. No push, HF mutation, DB, F3,
    methodology/Q5, smoke or deploy." CONSUMED:
    - Preflight:
      - none of the touched files is evaluator-pinned (config/build_info.py, tests/api/test_build_info.py,
        tests/scripts/test_source_integrity_guard.py, STATE.md; config/defaults.py is the only pinned config
        file), so no §2.6 crossing;
      - config/build_info.py is a production-source-guard path (one of the 11 guarded files);
      - the frontend reads the fingerprint from /v1/build-info at run time, so no frontend file names the build;
      - the name fits the schema pattern ^UCPE-[A-Z0-9-]{3,}$.
    - task-830 (Codex, DONE) followed the fd0e1f0 precedent, in 3 files. Commit 2b575abb:
      - config/build_info.py: RELEASE_ID UCPE-PROD-H2-HOLD-20260927-A. The label "PROD-H2-HOLD release of main"
        and milestone "prod-h2-hold" match it (Claude's derivation from the name, as in fd0e1f0). The fingerprint
        derives to "UCPE LIVE BUILD · PROD-H2-HOLD-20260927-A".
      - tests/api/test_build_info.py: the build-info contract expects the new identity.
      - tests/scripts/test_source_integrity_guard.py: CURRENT_DELTA_PATHS = [api/analysis_service.py,
        config/build_info.py]. Its pinned-identity assertions stay PROD-SAFE-3, because the pin is unchanged.
    - Checked independently:
      - the diff is the 3 files;
      - the build-info payload is exact;
      - the hold files and ops/ are unchanged;
      - the actual guarded delta against the pin equals the declaration;
      - the targeted suites passed 111;
      - ./verify.sh PASS 2470 (LAST_VERIFY).
    - This record.
  - T4 deploy authorization (owner, 2026-09-26T17:44Z; pasted text in the owner's established form), verbatim:
    "CONTINUE CURRENT — Opus 5 XHIGH. Owner T4 AUTHORIZED once for the H2 fail-closed hold merged by PR #125. First
    fetch/verify canonical `origin/main=fa5c0da7439b926f95c03a8a1e60898e0a9737e5`, CI green, exact 7-file merge, all
    H2/Q5 seals intact, clean local main, and the current production/HF pre-deploy anchor. Derive the exact
    sanctioned production deployment procedure only from current `RELEASE_GATE.md`, STATE and deterministic release
    evidence; if any anchor/procedure conflicts, STOP before mutation.

    If all preconditions pass, deploy exactly this main commit once using the sanctioned production path. Do not
    change DB, secrets, methodology/Q5, F3, collector, resolver, workflows or any other code. After deployment,
    perform only read-only settle/health/build-identity/source-integrity checks sufficient to prove what revision is
    running; do not run product-analysis smoke yet. Report exact deployed revision/build identity, runtime state,
    source-guard status, whether a post-deploy baseline re-pin is still required, rollback readiness, and any
    remaining production-verification boundary. No second deploy." NOT CONSUMED: it stopped before any mutation,
    and the owner confirmed it was not consumed.
    - Preconditions passed:
      - origin/main fa5c0da7: parents (1dfe2d22, 19b24a6b); tree 1dc79429, the recorded merge tree; exactly the 7
        files;
      - CI green (LAST_GREEN_SHA);
      - all 13 H2/Q5 seal files verify;
      - the local main is clean and was fast-forwarded to fa5c0da7.
    - The pre-deploy production anchor (public reads only; no analysis call):
      - hf/main 00705c55;
      - the Space API reports runtime.stage RUNNING and runtime.sha 00705c55;
      - /healthcheck 200; /v1/build-info UCPE-PROD-SAFE-3-20260915-A;
      - no guard run was queued or in progress.
    - The derived path: 00705c55 is an ancestor of main (through the pin PR #106), so the release is a plain
      fast-forward, git push hf <main>:refs/heads/main, never --force. build_release_candidate.sh refuses this case
      by design and names that route. The §5 checks follow .work/816/l1/runbook.md, with runtime.sha == <main>.
    - The runtime delta 00705c55 → fa5c0da7: the hold (3 files) and the unwired v2 prep (proper_score_skill.py,
      distributional_v2_serving.py, distributional_v2_state.py). Nothing imports the prep files, and the app's
      start-up loads none of them.
    - Blockers:
      1. `hf auth whoami` returned "Invalid user token". Only the owner can refresh it; Claude never handles tokens.
      2. The release identity had not moved since PROD-SAFE-3, so the deploy would not be independently provable:
         fd0e1f0's owner-ruled discipline, a blind STALE_RUNTIME check, and a UI label naming the wrong build. This
         preparation resolves it.
    - Rollback, prepared but not run (a new T4): git push --force-with-lease=refs/heads/main:<deployed> hf
      00705c55e7eb291d01b4e02d4cca859122083f28:refs/heads/main.
  - T3 authorization for feat/h2-failclosed-hold (owner, 2026-09-26T17:16Z, a direct instruction), verbatim:
    "CONTINUE CURRENT — Opus 5 HIGH. T3 AUTHORIZED once: verify `origin/main` is still
    `1dfe2d22cbe3b7df4c2f38aac099db9f225176b9`, `feat/h2-failclosed-hold` is exactly
    `19b24a6b1f1001af9cd8c9a290ae9d8412031389`, the complete diff is only the expected 7 hold/test/STATE files,
    evaluator pin remains 0/69, and `analysis_service.py` is the only declared changed-but-not-deployed source-guard
    path. Then push only that exact branch/SHA to origin, never hf; stop after confirming the remote branch. No
    PR/merge, DB, F3, methodology/Q5 change, deploy or production action." CONSUMED:
    - The pre-push checks passed:
      - origin/main 1dfe2d22; the branch exactly 19b24a6b; the diff exactly the 7 files;
      - evaluator pin 0/69;
      - the actual guarded delta = the declaration = [analysis_service.py];
      - the merge tree 1dc79429, recorded before the push.
    - Exactly 19b24a6b was pushed to origin feat/h2-failclosed-hold, never to hf. A first attempt failed locally
      with nothing sent (a zsh modifier garbled the refspec).
    - PR #125 was merged from the owner's account at 2026-09-26T17:41:34Z (LAST_GREEN_SHA).
  - History (2026-09-26, before PR #125): **The H2 T2 fail-closed hold (Q8) is IMPLEMENTED LOCALLY only. Q8 is NOT
    LIVE.**
    - Branch feat/h2-failclosed-hold (LOCAL, no upstream), from main 1dfe2d22:
      - e669e06ff629dda7d367a27106e2da2b8f6206f5 (the hold);
      - ebfe20730c99285967958fc4350de95f7349c719 (the owner's final detail wording);
      - 9d7fdc4de2a9f62f0e1a192b5597425bf75e645d (the first STATE record);
      - 4ea425931b086e686a103d528e850bba7d339637 (the owner's final headline);
      - then this STATE record.
    - It is NOT PUSHED, NOT MERGED, NOT DEPLOYED and NOT LIVE. Until a deploy, the live gate behaves as today: in
      production (hf 00705c55), a cached or shadow-arm SKILL_DEMONSTRATED still lifts the hard block.
    - The Q5 adjudication stays UNAVAILABLE (below).
  - Headline polish (owner, 2026-09-26; pasted text in the owner's established form), verbatim:
    "CONTINUE CURRENT — Opus 5 HIGH. Final local polish before T3 on
    `feat/h2-failclosed-hold @ 9d7fdc4de2a9f62f0e1a192b5597425bf75e645d`: use the remaining Codex delegation to
    change only the short hold headline to exactly `Directional evidence under review`; keep the approved detail
    exactly `Directional candidates are paused while evidence is being corrected. Diagnostic evidence, when
    available, is still reported.` Update only directly affected tests and any STATE pointer/current-head field
    required for accuracy.

    Then independently inspect the diff, run the targeted hold/gating tests and full `./verify.sh` from the safe
    worktree, and commit locally only. Preserve Q5=UNAVAILABLE and Q8=NOT LIVE. No other wording, logic, gate
    behavior, pin/source-guard semantics, DB, F3, collector, resolver, workflow, push or deploy change. Return exact
    new SHA and verify results." CONSUMED:
    - task-829 (Codex, DONE; the fourth and last delegation) set the headline to exactly "Directional evidence under
      review". The detail is unchanged, and the focused test pins both. Commit 4ea42593.
    - The overview card now reads "Directional evidence under review: Directional candidates are paused while
      evidence is being corrected. Diagnostic evidence, when available, is still reported."
    - Checked independently:
      - the diff is two lines (the headline constant and its test literal);
      - the targeted suites passed 167;
      - ./verify.sh PASS on 4ea42593 (LAST_VERIFY);
      - both rollback routes were re-checked on 4ea42593 (T2 entry below).
    - This record updates the STATE pointers only.
  - Hold wording finalization and STATE (owner, 2026-09-26; pasted text in the owner's established form), verbatim:
    "CONTINUE CURRENT — Opus 5 HIGH. Before T3, make one bounded local finalization on
    `feat/h2-failclosed-hold @ e669e06ff629dda7d367a27106e2da2b8f6206f5`: replace the hold display wording with
    exactly “Directional candidates are paused while evidence is being corrected. Diagnostic evidence, when
    available, is still reported.” Update focused tests accordingly.

    Then update STATE.md additively to record the hold as IMPLEMENTED LOCALLY only: exact branch/SHA, NOT
    PUSHED/MERGED/DEPLOYED/LIVE, evaluator pin 0/69 touched, `analysis_service.py` as the declared
    changed-but-not-deployed production-source-guard path, tests/verify results and both rollback routes. Keep
    Q5=UNAVAILABLE and Q8=NOT LIVE. Use Codex for code/test edits per doctrine; STATE may be updated in the normal
    orchestration loop. Re-run targeted tests + full `./verify.sh`, inspect the final diff, commit locally only and
    report exact new SHA/files/results. No push, DB, F3, collector, resolver, workflow or deploy." CONSUMED:
    - task-828 (Codex, DONE) set the hold's blocking-reason detail to exactly that text. The headline stays
      "Directional candidates are paused", and the focused test pins both. Commit ebfe2073.
    - The overview card joins the two as "Directional candidates are paused: Directional candidates are paused while
      evidence is being corrected. Diagnostic evidence, when available, is still reported."
    - This record.
  - T2 hold authorization (owner, 2026-09-26; pasted text in the owner's established form), verbatim:
    "CONTINUE CURRENT — Opus 5 XHIGH. First fetch and fast-forward the clean local `main` to canonical PR #124
    merge `1dfe2d22cbe3b7df4c2f38aac099db9f225176b9`. Then T2 AUTHORIZED, local-only: implement the smallest
    temporary fail-closed H2 hold at the single analysis-path consumption point so neither cached nor shadow-arm
    `SKILL_DEMONSTRATED` can lift the product hard block while corrected H2 evidence is UNAVAILABLE;
    probabilities/model outputs and diagnostics must remain unchanged.

    Use an explicit non-secret `hold_reason`; missing/None evidence must also remain blocked. Cover `/v1/analyze`
    and `/v1/analyze_batch`, existing passing verdicts, missing evidence, probability byte-identity,
    blocking-reason display/export, and rollback behavior. Preflight actual pin membership before editing and
    avoid evaluator-pinned files; if a pinned change is truly required, STOP and report rather than crossing §2.6.
    Do not change DB, methodology_version, H2 thresholds, Q5 records, F3, collector, resolver, workflow,
    release/deploy or production.

    Run targeted tests plus full verification from a safe worktree, inspect the actual diff, and perform one
    consolidated self-audit for bypass paths, schema/export masking, single/batch parity and rollback. Commit
    locally only on a fresh branch from `1dfe2d2`, no push. Return exact changed files, tests, audit findings,
    rollback, pin status and local commit SHA." CONSUMED:
    - main was fast-forwarded to the PR #124 merge 1dfe2d22 (LAST_GREEN_SHA).
    - **What the hold does** (e669e06f, 6 files):
      - calibration/skill.py: a rollback switch, LEGACY_PASS_LIFTS_HARD_BLOCK = False, and evidence_for_gate().
        When the verdict is SKILL_DEMONSTRATED, or evidence is missing or malformed, the gate receives an
        INSUFFICIENT_EVIDENCE copy plus a non-secret hold record: {active: true, hold_reason:
        EVIDENCE_UNIT_UNDER_CORRECTION, legacy_verdict}.
      - api/analysis_service.py: the single consumption point hands the gate that copy and attaches the hold as
        gate_result.directional_evidence_hold. The response's skill_evidence still reports the legacy verdict, for
        diagnostics.
      - detail/frontend_display.py: the interim blocking-reason copy while the hold is active.
      - tests/api/test_h2_failclosed_hold.py (new, 20 tests); tests/api/test_skill_gating.py (its pass-through
        branch now runs with the switch on; every assertion kept); tests/scripts/test_source_integrity_guard.py.
      - Unchanged: probabilities and model outputs, methodology_version, the H2 thresholds, gates/composite.py, the
        cache, the schemas, the database and every evaluator-pinned file.
    - **Pins:**
      - the evaluator pin (ops/section_5a_evaluator_pin.json): 0 of 69 files touched, so no §2.6 crossing;
      - the production source guard (ops/hf_runtime_baseline.json, pin 00705c55):
        src/crypto_probability_engine/api/analysis_service.py is the declared changed-but-not-deployed path
        (CURRENT_DELTA_PATHS in tests/scripts/test_source_integrity_guard.py; precedent be2104e).
        - The baseline is NOT re-pinned. The declaration clears only when a deploy re-pins it.
        - After a merge, the scheduled guard lists the path as an advisory delta (SCHEDULER_AHEAD_OF_PIN). Its exit
          code depends only on the runtime probe.
    - **Tests and verify:**
      - the new tests:
        - T1: the helper's matrix;
        - T2: /v1/analyze is blocked;
        - T3: /v1/analyze_batch blocks BTC and ETH;
        - T4: the existing blocking verdicts are unchanged;
        - T5: missing evidence stays blocked;
        - T6: probability bytes are identical;
        - T7: seniority;
        - T8: both OOS arms are held;
        - T9: the text, and export leaves the hold unmasked;
        - T10: rollback;
      - targeted suites: 167 passed;
      - ./verify.sh PASS (ruff ok | 2470 passed | schemas+smoke ok | scanners 3/3), on e669e06f, again on
        ebfe2073 and again on 4ea42593, in worktree lanes2/h2hold (LAST_VERIFY).
    - **Self-audit** (one, consolidated):
      - bypass: none. Every skill-gate route goes through the one held point:
        - /v1/analyze and /v1/analyze_batch (a per-item loop);
        - the OOS arms;
        - scripts/live_smoke.py;
        - the shadow collector, via analyze_request.

        The pipeline's own gate call passes no evidence and is re-gated afterwards;
      - no evidence feedback: no evidence-counting query filters on gate outcome;
      - schemas and export: responses validate against the unchanged schemas, and the hold survives
        sanitize_for_export unmasked;
      - a leaf-by-leaf probe against 1dfe2d22 (fixture mode, no database; run_id and analysis_hash excluded):
        - with the hold active, 80 decision fields change per result and 0 probability fields;
        - single and batch change the same set;
        - the NO_DEMONSTRATED and INSUFFICIENT paths are identical.
    - **Deviations from H2_FAILCLOSED_T2_DESIGN.md, following the owner's words:**
      - the key is hold_reason; the design's reason_code would be masked on export;
      - missing evidence is held; the design let it pass;
      - the detail text is now the owner's final wording (ebfe2073), and so is the headline (4ea42593).
    - **Rollback: two routes, both checked against 1dfe2d22 on 4ea42593 (earlier on ebfe2073):**
      1. Set LEGACY_PASS_LIFTS_HARD_BLOCK = True in calibration/skill.py. Result: 0 differing fields in all 6 probe
         scenarios. The guard declaration stays until a deploy re-pins or the commits are reverted.
      2. Revert the three hold code commits, newest first: git revert 4ea42593 ebfe2073 e669e06f (before the
         headline commit: git revert ebfe2073 e669e06f). Result: the code tree equals 1dfe2d22, and only STATE.md
         differs (dry run). CURRENT_DELTA_PATHS returns to [].

      Either route reaches users only through verify, a T3 and a separate deploy authorization.
    - Codex, 3 of 4 delegations (CODEX_PENDING):
      - task-826: BLOCKED at the source-integrity guard test (the first causal failure, preserved);
      - task-827: DONE (the one targeted repair);
      - task-828: DONE (the wording).
  - T3 authorization for chore/state-post-123 (owner, 2026-09-26, a direct instruction), verbatim:
    "CONTINUE CURRENT — Opus 5 HIGH. T3 AUTHORIZED once: verify `origin/main` is still PR #123 merge
    `597e5c958a2d2bcb11abaab0808f2dfb1149c9cf`, all H2/Q5 seals verify, and `chore/state-post-123` is exactly
    `2e0ecfd722a780eed3052320de34ae9f31fbe73c` with STATE.md-only diff. Push only that exact branch/SHA to origin,
    never hf, and stop. No PR/merge, DB/query, simulation, cutoff ruling, F3, hold implementation,
    serving/pinned/wiring/freeze/deploy." CONSUMED:
    - The pre-push checks passed.
    - Exactly 2e0ecfd7 was pushed to origin chore/state-post-123, never to hf. The merge tree 188f8419 was recorded
      before the push.
    - PR #124 was merged from the owner's account at 2026-09-26T15:52:23Z (LAST_GREEN_SHA).
  - **The Q5 adjudication is UNAVAILABLE** (H2_Q5_ADJUDICATION.md; OWNER_BOUNDARY 2).
    - H2-G2 keeps its modeled PASS (36/36).
    - Its operating-density confirmation is UNAVAILABLE: provenance passes, but the density is not yet validated
      and the floor is unmet.
  - H2 v3 (g 0.09) stays permanently FAILED.
  - Every seal and result is preserved. H1 is COMPLETE, and NG-1 is CLOSED. This record is unpushed.
  - Q5 adjudication ruling (owner, 2026-09-26; pasted text in the owner's established form; its anchors verify:
    the sealed follow-up 37b87c28…, 6 | 5, and the expected-12 stop), verbatim:
    "CONTINUE CURRENT — Opus 5 XHIGH. Confirmation for the sealed Q5 follow-up: the single SELECT was run exactly
    once, unedited, and no other query was run in that session. Owner ruling: accept the predeclared `6 | 5`
    confirmation; preserve the original expected-12 stop failure historically and record additively that it came
    from mixing outcome-linked counts with prediction-row counts. Correct the prediction-row expectation to 13
    total CONTROLLED_SMOKE rows, 7 at/after 2026-08-19, and lift the Q5 interpretation stop.

    Now interpret only the already-sealed Q5 count/density/provenance results. Apply the frozen H2-G2 design
    without retuning: report each cutoff/timeframe’s min/median/max density, informative-call density, counted
    windows and provenance checks; adjudicate whether actual operating density lies inside the frozen G2
    validation envelope and whether the informative-call floor can be satisfied. Do not query DB again,
    expose/derive performance, change `g=.07`, `alpha=.001`, N/CI/scenarios, or touch F3. Record the Q5
    adjudication additively, update local STATE, verify in the safe worktree, and return PASSED / BLOCKED /
    UNAVAILABLE plus the exact new SHA. No push, hold implementation or deploy." CONSUMED:
    - Recorded in H2_Q5_RULING.md:
      - the attestation: the follow-up ran once, unedited, with no other query;
      - the expected-12 stop failure kept as history;
      - its cause: an outcome-linked count mixed with a prediction-row count;
      - R2 corrected to 13 in total, 7 at or after (I);
      - the stop lifted.
    - Adjudicated (H2_Q5_ADJUDICATION.py/.out/.md). All of it, with H2_Q5_RULING.md, is sealed as
      H2_Q5_ADJUDICATION.sha256 d3e3dd01a847cbc70f557b35527987956a267477d4cc669b7ab5738674ca7a23.
      - **Provenance PASS:** R1–R4, the follow-up, and consistency (admitted rows M 72 ≤ 97; I 17 ≤ 26).
      - **Density min/median/max per counted window (k, m):**
        - (M) 15m 1/1/2 (3, 4); 1H 2/2.5/4 (4, 10); 4H 1/2/4 (4, 9); 1D 1/2/6 (3, 8);
        - (I) 15m none (0, 0); 1H 2/2/2 (1, 2); 4H 2/2/2 (1, 2); 1D 1/1/1 (1, 1).
      - **Envelope:** inside by construction, but NOT YET VALIDATED. H2-G2's modeled acceptance was density-free
        (Gaussian windows), and §13.3 has not been run.
      - **Floor (m ≥ 100, k ≥ 12):** unmet on every timeframe and cutoff. At the observed rates, under (M): 1H
        about 2028-06, 4H about 2028-08, 1D about 2029-05, and 15m not within the plan; (I) later still.
      - **Verdict rule** (set in the adjudication script before it ran): BLOCKED if provenance fails; PASSED only
        if provenance passes, the density is validated and the floor is met; otherwise UNAVAILABLE. Result:
        **UNAVAILABLE**.
      - No new query, no performance read, and nothing retuned (g 0.07, α 0.001, N, CI and the scenarios all kept).
  - Q5 follow-up authorization (owner, 2026-09-26, a direct instruction), verbatim:
    "CONTINUE CURRENT — Opus 5 HIGH. Owner selects Q5 option B. Authorize exactly one additional count-only
    production read to test the sealed discrepancy hypothesis: verify `H2_Q5_CHECK.md` §4, print its exact single
    SELECT verbatim plus expected columns/rows and stop; do not touch the DB yourself. The query may only
    determine whether the older CONTROLLED_SMOKE set contains 6 predictions but 5 outcome-linked predictions. Do
    not rerun Q1/Q2/Q3/Q5, inspect or interpret Q5 density/call figures, expose performance, modify the query, or
    touch F3/hold/serving/deploy." CONSUMED:
    - The owner ran the single sealed SELECT (H2_Q5_CHECK.md §4) at 21:50 BKK. **6 | 5 → CONFIRMED** by the rules
      fixed before the run. The raw result was saved first; sealed as H2_Q5_FOLLOWUP.sha256
      37b87c28fc2cd4c4c4ad8c330ecd9d70dbefafdbccd20f1ceff7b85f8d2cdb04.
  - Q5 count-only read authorization (owner, 2026-09-26; pasted text in the owner's established form), verbatim:
    "CONTINUE CURRENT — Opus 5 HIGH. First fetch and verify canonical `origin/main` is PR #123 merge
    `597e5c958a2d2bcb11abaab0808f2dfb1149c9cf`, then fast-forward the clean local main checkout to it if needed.
    Q5 count-only production read is AUTHORIZED, but you must not access the DB yourself: verify the sealed H2
    query plan and print the exact five SELECT statements from `H2_COUNT_QUERY_PLAN.v2.md` verbatim, with the
    precise Supabase SQL Editor run order, expected columns, and a single result template for me to paste back.

    Q5 may measure only frozen density/provenance facts needed for H2-G2: min/median/max contributions per window,
    informative directional-call counts, and cutoff/provenance counts. Do not compute or expose skill/performance
    outcomes, up/down success rates, scores, probabilities, or anything usable to retune `g=0.07`, `alpha=0.001`,
    N, CI, or the 36-scenario family. No writes, temp tables, functions, migrations, DB settings, F3, collector,
    hold implementation, serving/pinned/wiring/freeze/deploy. Stop after giving the exact owner runbook."
    CONSUMED:
    - origin/main was verified as the PR #123 merge 597e5c95, and the main checkout was fast-forwarded to it
      (LAST_GREEN_SHA).
    - The runbook gave Q1, Q2, Q3 and Q5 of H2_COUNT_QUERY_PLAN.v2.md verbatim. Q4 was excluded because it computes
      directional hits and a z-score, which the owner's constraint forbids.
    - The owner ran them at 14:34:23Z. The raw capture was saved unchanged first (H2_Q5_RAW_RESULTS.txt 1f838996…)
      and is complete.
    - **Stop rule R2 fired** (13 against an expected 12): STOP, with no count used. Sealed as H2_Q5.sha256
      dbc9987d396dfb54ce537806e7196751eccbaa0d36a91838d448803356e8dc02 (H2_Q5_CHECK.py/.out/.md).
  - T3 authorization for chore/state-post-122 (owner, 2026-09-26, a direct instruction), verbatim:
    "CONTINUE CURRENT — Opus 5 HIGH. T3 AUTHORIZED once: verify `origin/main` is still the canonical post-PR#122
    main, all H2 seals including G2 still verify, branch `chore/state-post-122` is exactly
    `57b8443f055a16e70aff1f890d04b0a31276ac5c`, and the complete Git diff vs main is STATE.md only. Then push only
    that exact branch/SHA to origin, never hf; stop after confirming the remote branch. No PR/merge, Q5/DB,
    code/tests implementation, F3, hold build/deploy, serving/pinned/wiring/freeze/deploy." CONSUMED:
    - The pre-push checks passed.
    - Exactly 57b8443f was pushed to origin chore/state-post-122, never to hf. The merge tree 8b4f07d8 was recorded
      before the push.
    - PR #123 was opened and merged from the owner's account at 2026-09-26T13:57:52Z (LAST_GREEN_SHA).
  - H2-G2 selection (owner, 2026-09-26; it arrived as pasted text in the owner's established form; its anchors
    verify: option A of H2_V3_RESULT.md §6, and v3 kept FAILED), verbatim:
    "CONTINUE CURRENT — Opus 5 XHIGH. Owner selects option A as a NEW candidate generation, not a repair/retry:
    preserve H2 v3 `g=0.09` permanently as FAILED and freeze H2-G2 at `α_look=0.001`, drift guard `g=0.07 SE`,
    absolute 0.10 coverage-only, product FWER≤5%, per-timeframe total≤1.25%, modeled allowance≤0.9375%,
    reserve=0.3125%. Predeclare additively before execution; use the same frozen 36-scenario family updated only
    where `g` mechanically changes the admitted-bias envelope, fixed N=400,000/scenario, fresh independent seeds,
    one-sided exact 95% binomial UCB≤0.9375%, and derive the exact pass-count threshold mechanically.

    Run exactly one acceptance execution after the new prereg seal; no adaptive stopping, scenario removal,
    confidence/sample-size change, or parameter retuning. Do not justify acceptance by prior “chance of passing”;
    adjudicate only the fresh frozen run. If any binding scenario fails, H2 remains BLOCKED and parameter search
    STOPS—do not try 0.06/0.05/etc.; return to owner for architecture reconsideration. If all pass, record H2-G2
    as PASSED pending Q5 operating-density confirmation, not fully accepted. Preserve all earlier seals/results,
    update local STATE additively, verify from the safe worktree, and report prereg/result seals, all binding
    scenario rates/UCBs, exact budget accounting and new SHA. No push, Q5/DB, F3, code/tests implementation, hold
    deployment or serving change." CONSUMED:
    - Predeclared, then sealed BEFORE the run as H2_G2_PREREG.sha256
      06af15c7b149fb1dadf4ac6cab3046539df9e2e077a125a1fbdc6e0c700dbbc1 (14:38:50+07:00). It covers:
      - H2_G2_RULING.md, the ruling verbatim;
      - H2_G2_D3_PREREG.md, identical to v3 except g = 0.07;
      - H2_G2_ACCEPTANCE_PROTOCOL.md: v3's 36-scenario family, changed only in S01's admitted residual
        (0.09 → 0.07); a fixed N = 400,000 each; fresh seeds default_rng([20261002, s]); pass iff x ≤ 3,649, derived
        mechanically. It uses no prior pass estimate;
      - H2_G2_ACCEPTANCE.py: model code byte-identical to v3's, and it refuses to run without the seal.
    - **The single run** (14:39:16+07:00; H2_G2_ACCEPTANCE.out 6fb6c9ed…): **ALL 36 PASS.**
      - S01, the admitted-bias envelope (0.07 at every look, no guard): x = 3,522, p̂ 0.88050%, upper bound
        0.90519%.
      - The actual gate's worst is S03 (ρ → 0, δ 0.015): p̂ 0.75650%, upper bound 0.77943%.
      - With no bias (S02): p̂ 0.74675%, upper bound 0.76953%.
      - Analytic checks: at δ = g, one look runs ×1.21–×1.25 of 0.001 with the exact t-test, and ×1.05–×1.16 with the
        real guard. The normal approximation gives ×1.263.
    - **Budget accounting:**
      - per-timeframe modeled 0.90519% ≤ 0.9375% (+0.03231 pp);
      - with the 0.3125% reserve, 1.21769% ≤ 1.25%;
      - four timeframes: modeled union 3.6207% (independent 3.5719%); with the reserve, union 4.8707% ≤ 5%.
    - Recorded in H2_G2_RESULT.md with H2_G2_CLOSURE_CHECK.py/.out, sealed as H2_G2_RESULT.sha256
      070b62765851871a3b896ddec4e5aa948e6d28ea2b0ba30341fe8dc4534260d5.
      - All checks OK: every seal intact; the seal preceded the run; the family differs from v3 only in S01; the model
        code is identical; the record matches the raw output.
    - **Not fully accepted.** Still required: the Q5 read; the §13.3 validation of the total ≤ 1.25% per timeframe
      at the observed densities (N = 400,000, exact 95% bound, coverage envelope off); the other §13 items; and the
      open points (b), (d), (e) and (f).
    - **Parameter search is closed** by the ruling: had G2 failed, no other g would be tried.
    - No push, Q5/DB, F3, code or test implementation, hold deployment or serving change.
  - Before that, the v3 candidate (α_look 0.001, g 0.09 SE, 0.10 as coverage-only) FAILED its predeclared
    modeled-error acceptance in scenario S01. It stays on record, unreplaced (below).
  - H2 error-budget ruling and frozen v3 candidate (owner, 2026-09-26; it arrived as pasted text in the owner's
    established form; its anchors verify against H2_GUARD_VALIDATION.md §2 and §6), verbatim:
    "CONTINUE CURRENT — Opus 5 XHIGH. Owner ruling: control false-unblock FWER at ≤5% across the four evaluated
    timeframes over the full plan. Allocate ≤1.25% total per timeframe, of which only 75% = 0.9375% may be
    consumed by modeled error; reserve 0.3125% per timeframe for unmodelled effects. Freeze candidate repair at
    per-look α=0.001 and drift bound=0.09 SE; keep absolute 0.10 as coverage-only with zero error-budget credit.

    Create additive v3 records only; preserve every existing seal. Validate the frozen design
    analytically/numerically where possible and, for Monte Carlo acceptance, use a predeclared fixed N=400,000
    independent cohorts per frozen adversarial scenario and require the one-sided exact 95% binomial upper bound
    on modeled false-unblock probability to be ≤0.9375% per timeframe. No adaptive simulation stopping or retuning
    after results. Include repeated-look and four-timeframe budget accounting explicitly. If any scenario fails,
    methodology stays BLOCKED and do not alter parameters without returning to owner.

    Update local STATE only if the frozen design passes; otherwise record BLOCKED without replacing the failed
    candidate. Verify in the safe worktree and report the additive seal, exact probabilities/upper bounds, finding
    closure, and new SHA. No push, Q5/DB, code/tests implementation, F3, hold deployment or serving change."
    CONSUMED:
    - Predeclared, then sealed BEFORE the run as H2_V3_PREREG.sha256
      cfcf773b9494e5fa5636e28123b7f9da7959dc62ffae15b298405f01e392b19d (14:11:06+07:00). It covers:
      - H2_RULING_V3.md, the ruling verbatim;
      - H2_D3_PREREG.v3.md, the full candidate specification, which supersedes v2;
      - H2_V3_ACCEPTANCE_PROTOCOL.md: 36 frozen adversarial scenarios, a fixed N = 400,000 cohorts each with its own
        seed, and pass iff x ≤ 3,649, i.e. an exact one-sided 95% upper bound ≤ 0.9375%. It disclosed before the
        run that S01 had about a 62% chance to pass;
      - H2_V3_ACCEPTANCE.py, which refuses to run without that seal.
    - **The single run** (14:11:31+07:00; H2_V3_ACCEPTANCE.out 54411982…): **FAIL in 1 of 36.**
      - S01, the design rule's envelope (the residual 0.09 admitted at every look, no guard): x = 3,718,
        p̂ 0.92950%, upper bound 0.95485% > 0.9375%. With an earlier independent run (0.908%), the pooled estimate
        is about 0.919%, too close to the limit to certify at N = 400,000.
      - The 35 actual-gate scenarios all PASS. The worst is S05 (ρ → 0, δ 0.045): p̂ 0.80550%, upper bound
        0.82914%. With no bias (S02): 0.72725%, upper bound 0.74974%.
      - Analytic checks: at the residual 0.09, the one-look rate is ×1.28–×1.33 of 0.001 with the exact t-test, and
        ×1.07–×1.21 with the real guard.
    - **Budget accounting** (binding, S01 included):
      - per-timeframe modeled 0.95485% > 0.9375%;
      - with the reserve, 1.26735% > 1.25%;
      - four timeframes, union 5.0694% > 5%.
      - For information only: without S01, 0.82914%, 1.14164% and 4.5666%.
    - Recorded in H2_V3_RESULT.md with H2_V3_CLOSURE_CHECK.py/.out, sealed as H2_V3_RESULT.sha256
      01839fd18fc0fb6d8d78439e8a1fa3c7e4398da56b9ef064cbdc2a67c5d9ac1c.
      - All checks OK: every seal intact; the seal preceded the run; the record matches the raw output; the
        repairs for findings V1–V5 are recorded.
      - The candidate is NOT accepted.
      - The owner's options are in H2_V3_RESULT.md §6. The recommendation is (A), a new candidate at g = 0.07 with a
        fresh predeclared run. Nothing was changed.
    - No push, Q5/DB, code or test implementation, F3, hold deployment or serving change.
  - H2 guard validation (owner, 2026-09-26, a direct instruction), verbatim:
    "CONTINUE CURRENT — Opus 5 XHIGH. Before any T3/Q5, analytically validate the frozen drift guard: derive the
    maximum admissible positive drift residual relative to SE under the actual one-look test and the repeated
    weekly-look rule, and separately quantify four-timeframe any-false-unblock risk. Do not assume `0.24 SE` or
    absolute `0.10` are valid; prove or reject each, including the simple sanity case where α=.002 and +0.24 SE
    bias increases one-look false-pass above nominal. Preserve all sealed records; paper-only, no DB/Q5, tuning on
    production density, code/tests, push, F3, implementation or deploy. Return a derivation, target error budget,
    verdict on both guard thresholds, and exact repair needed if either fails." CONSUMED:
    - H2_GUARD_VALIDATION.md, with its CALC and REFINE scripts and outputs, sealed as H2_GUARD_VALIDATION.sha256
      745075ad39a8e3ace0f67a3e4fa4348cb1469fb813c97f73755a768b045d05ff. It is density-free, in SE units.
    - One look: the admissible residual at the nominal level is 0; +0.24 SE turns 0.002 into 0.0042.
    - 41 looks:
      - the idealized rate at α 0.002 is 2.34% with the residual 0.2407 admitted (1.31% with no residual);
      - the real guard is lower (1.755%);
      - four timeframes: up to 9.4%.
    - Verdicts: **g 0.2407 REJECTED**; **0.10 REJECTED as error control** (harmless as a withholding rule).
      Recommended repair: α 0.001 with g 0.09, which the owner then froze and which failed above.
  - H2 ruling on point 12(a) (owner, 2026-09-26; it arrived as pasted text in the owner's established form; its
    anchors verify: the sealed package ea4bc8de… and point 12(a) of H2_D3_PREREG.md §12), verbatim:
    "CONTINUE CURRENT — Opus 5 XHIGH. Owner H2 ruling for unresolved point 12(a): use a predeclared fail-closed
    drift guard; do NOT use F3/contemporaneous data and do NOT use same-cohort conditional margins as the
    reference. Preserve the sealed `ea4bc8de…` package and create additive repaired paper records only.

    Close the HIGH finding by freezing the guard construction/bound before Q5 results, making `UNAVAILABLE`
    mandatory when realized drift exceeds it or when observed density lies outside the validated envelope, and
    requiring validation at Q5 min/median/max contributions per window before the permanent gate can be accepted.
    Repair the LOW findings too: settle-filter before collapse; define a call by sign(`p_up-p_down`) with exact
    ties NO_CALL; clarify cutoff-M evidence/direct-serving observation plus stale-local-writer class; declare
    per-timeframe vs cross-timeframe multiplicity; declare informative directional-call count and prepare a
    non-arbitrary directional-call floor rule; add exact PLAN_COMPLETED dates when k>52. Preserve
    methodology_version and all prior owner rulings.

    Update local STATE to say methodology remains BLOCKED pending the separately authorized Q5 count-only density
    read. Mechanically audit every second-review finding FIXED/NOT_FIXED, verify from the safe worktree, commit
    STATE.md only, and report the new exact SHA. No push, DB query, code/tests implementation, hold deployment,
    F3, collector or serving change." CONSUMED:
    - Recorded additively in .work/h2_skill_gate/H2_RULING_12A.md: the ruling verbatim, the second review's
      findings, and the closure table. The second review's own text is not in the repository or .work; its findings
      are taken from the ruling (one HIGH, in three parts, and six LOW).
    - The v2 records (they supersede the v1 documents, which stay sealed and unchanged): H2_D3_PREREG.v2.md,
      H2_CUTOFF_DERIVATION.v2.md and H2_COUNT_QUERY_PLAN.v2.md. Support files: H2_DRIFT_GUARD_CALC.py/.out and
      H2_PLAN_DATES.py/.out. H2_FAILCLOSED_T2_DESIGN.md is unaffected.
    - HIGH fixed:
      - The drift guard is frozen before any Q5 result. Either part makes the verdict UNAVAILABLE (DRIFT_GUARD):
        - the bias bound |β̂| > g·SE, where β̂ = (π̂ − π_T)·Δq̂ and g = 0.2407, the headroom between α_look 0.002 and
          the calibrated 0.004177;
        - the drift envelope |π̂ − π_T| > 0.10.
      - The density envelope [D_lo, D_hi] comes from Q5. Outside it, the verdict is UNAVAILABLE (DENSITY_ENVELOPE).
      - Validation must run at each timeframe's Q5 minimum, median and maximum density before the permanent gate
        can be accepted.
      - The synthetic check: without the guard, false passes reached 73.6% and 99.9% at 30 contributions per
        window; with the bias bound, every scenario stayed at or below 1.51%.
    - LOW fixed:
      - the settle filter now comes before the collapse;
      - the call is sign(p_up − p_down), with exact ties NO_CALL;
      - the cutoff-(M) evidence is classified: dbe9bf8 is a deployment-source record, and the only direct-serving
        observation in the interval is 2026-08-16T09:44Z (a4bd2ac). This repository has no commits from
        2026-07-13T15:37Z to 2026-08-15T09:49Z. The stale-local-writer class is declared for both cutoffs;
      - multiplicity is declared: controlled per timeframe, not across timeframes;
      - the informative count m is declared, with the floor rule m ≥ 100 (point (f));
      - the exact PLAN_COMPLETED dates, at the earliest: 15m/1H/4H 2027-07-21T00:00Z (M) and 2027-08-25T00:00Z (I);
        1D 2030-07-24T00:00Z (M) and 2030-08-21T00:00Z (I).
    - Mechanical audit (H2_SECOND_REVIEW_CHECK.py/.out): ALL PASS. HIGH H-1 to H-3 and LOW 1–6 are FIXED
      (mechanical); the v1 seal is intact (15/15); Q1–Q4 are byte-identical to v1; the new texts contain no bare
      "skill". It checks presence and absence only, not correctness. No independent re-audit was run.
    - Seal: H2_PREP_12A.sha256 c795c17757919498e5e9db5cd53af05ac09aab21259973e9578ffd0d1e58a512 (10/10 files, all
      0444). H2_PREP.sha256 ea4bc8de… still verifies 15/15.
    - No push, database query, code or test implementation, hold deployment, F3, collector or serving change.
      methodology_version and every prior owner ruling are preserved.
  - H2 rulings (owner, 2026-09-26; they arrived as pasted text in the owner's established form), verbatim:
    "CONTINUE CURRENT — Opus 5 XHIGH. Owner H2 rulings: Q1 YES—max one candle-level contribution per
    `(symbol,timeframe,reference_close)` before further aggregation, with exact collapse rule frozen on paper; Q2
    D3—non-overlapping time-window means as inference units, aggregating same-window cross-symbol evidence, with
    anchor/min-window rule preregistered; Q3 replace the 50% coin with a predeclared drift-aware **directional**
    reference estimated outside the evaluation cohort—do not convert the live gate to proper scoring; Q4 YES,
    diagnostics use the same corrected unit but remain non-decision-bearing; Q5 YES, prepare a count-only
    current-state/provenance query for separate DB authorization and accept that corrected 1H/4H may lose pass; Q6
    YES, diagnostics may name the new evidence unit; Q7 admit only rows after the earliest deterministically
    proven clean provenance/cohort-separation cutoff, excluding default-backfilled earlier rows and declaring the
    known BTC-1M controlled-smoke misclassification; Q8 interim posture = fail-closed: current skill pass must not
    lift the product hard block until the corrected gate is implemented and validated, while diagnostics may still
    report. Keep methodology_version unchanged. Record these rulings additively, prepare only the D3/drift-aware
    preregistration, exact cutoff derivation, count-only query plan, and bounded T2 fail-closed
    implementation/test/rollback design; update local STATE, audit once, verify from the safe worktree, and stop.
    No DB query, code/test implementation, push, serving/pinned/F3/deploy." CONSUMED:
    - Recorded additively in .work/h2_skill_gate/H2_RULINGS.md: the rulings verbatim, the deliverables, the audit
      and the repair. Prepared, paper only:
      - H2_D3_PREREG.md, the D3 preregistration:
        - the earliest request per candle is kept; exact ties are no-calls;
        - Monday-anchored 7-day windows (28-day for 1D; 1W and 1M out of scope), purged, and counted only once
          closed and settled (48 h); k ≥ 12 and n ≥ 100;
        - π_T from NG-1's R-1 span;
        - a one-sided window t-test at a per-look level of 0.002, over looks k = 12…52;
        - the outputs, and the replacement texts;
      - H2_CUTOFF_DERIVATION.md, two cutoffs:
        - (M) 2026-07-13T04:20:01Z, the default and the literal Q7 reading: dbe9bf8 pins production to 30d4982,
          which writes the origin on every insert;
        - (I) 2026-08-19T08:31:57Z, stricter: 5df51cd is the first proof that HTTP test traffic is classifiable;
        - the canary is declared and excluded by run id;
      - H2_COUNT_QUERY_PLAN.md: five SELECT-only aggregate statements, with stop and report rules fixed in
        advance;
      - H2_FAILCLOSED_T2_DESIGN.md: the interim hold (a switch and one helper in calibration/skill.py, the single
        consumption point, one display branch), ten tests, and the rollback.
    - The audit ran ONCE, as authorized, and returned REJECT (2 HIGH, 5 MEDIUM, 2 LOW).
      - It is kept verbatim in H2_PREP_AUDIT.md; the audited files are kept read-only as *.audited.md.
      - Each finding was verified, then repaired on paper. The mechanical closure check (H2_REPAIR_CHECK.out) reads
        ALL PASS.
      - NOT re-audited: the auditor asked for one re-audit, but the owner authorized one audit, now consumed.
    - Digests (SHA-256, first 16 hex):
      - H2_RULINGS.md da476caa52d0c840; H2_D3_PREREG.md 0ad0e2fcd8954a57;
      - H2_CUTOFF_DERIVATION.md 7088b54a15d1d5fd; H2_COUNT_QUERY_PLAN.md 6dc9731fce44253b;
      - H2_FAILCLOSED_T2_DESIGN.md 7600cfacb753a915; H2_PREP_AUDIT.md 4f15ba95ec1a98cf.
      - The seal is H2_PREP.sha256 ea4bc8de785689e8c2d6921455cab49803e302a6d2d4ec9601283603ada7033e. It covers 15
        files (15/15 OK), all 0444.
    - Found during the repair:
      - on 2026-08-19 the 15m, 1H, 4H and 1M cards read Up = Down exactly (RELEASE_GATE.md:127), and the legacy count
        scores every such tie as an UP call;
      - the audited single-look design would falsely pass about 10.7% of the time over a year of weekly looks
        (H2_ALPHA_LOOK_CALC.out);
      - a production query had found 5 legacy CONTROLLED_SMOKE and 2 SCHEDULED_SHADOW rows by 2026-08-16
        (RELEASE_GATE.md:408-409).
    - No code, test, data, database, production, serving, pinned, F3 or deploy action. methodology_version is
      unchanged.
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
CURRENT_MILESTONE=POST-PHASE-4 / PHASE 7 LANES (2026-10-05): the Card-04 companion is published (main
  267a6eaf, #230). Phase 7/8 proceeds under the owner's rulings DP-A to DP-F, with Lane P and Lane R local.
  Before it: POST-PHASE-4 / UOR CARD 04 (2026-10-05): the Card-04 companion, with the cross-credential
  count and the third repair, is prepared and verified locally (0b3cbb75...); the A4 component is unchanged
  (2007fa28...), its handoff corrected.
  Before it: POST-PHASE-4 (2026-10-04): lane A, lane B and the UOR A4 upstream artifact are MERGED
  (#226-#228). The reference/risk product's remaining items wait on owner rulings.
  Before it: POST-PHASE-4 (2026-10-04): the Phase 8 tooling inventory (lane B) and the local test wall time
  (lane A) are done locally. The reference/risk product's remaining items wait on owner rulings.
  Before it: PHASE 4 (2026-10-04): VERDICT INFEASIBLE (final). OP-1 and OP-2 ran once (sealed, consumed);
  F3 is open-ended forward time, so there is no window; the Option C cap (242 days) expired on 2026-05-23; H_c 0.65
  (L 156 weeks). Phase 7: passive only, and there is no natural traffic yet.
  Before it: PHASE 4 (2026-10-04): identity DONE; the D4 note, bridge, FEAS-2, protocol draft and verdict
  sealed; the R4-C1 module unwired. The FEASIBLE/INFEASIBLE verdict waits on OP-2 and F3's scope.
  Before it: PHASE 4 (2026-10-04): candidate identity + protocol feasibility.
  - Step 1 (identity) DONE.
  - Next: C1's new identity artifact (unwired), the D4 classification note, the incumbent
    bridge, and the protocol with DEV-synthetic feasibility.
  - Real-data refit NOT authorized.
  Before it: PHASE 3 (2026-10-04): E2 cutover ACCEPTED. Remaining: the consolidation (owner) and
  the final exit re-audit. Then Phase 4, with Phase 7's independent work alongside.
  Before it: PHASE 3 (2026-10-04): E2 released and identified. Remaining:
  - the cutover, then LIVE_PROVEN;
  - the consolidation and C1;
  - the final exit re-audit.
  Before it: PHASE 3 (2026-10-04): E2 LIFTED, the final blocker. The package is in review. Then:
  - the E2 release (T4) and the identification;
  - the owner's cutover, then LIVE_PROVEN;
  - the C1 hygiene and the final exit re-audit.
  Before it: PHASE 3 (2026-10-04): D6 COMPLETE; the exit re-audit is done: NOT MET IN FULL (E2 DEFERRED blocks X3).
  Everything else in Phase 3 is complete or recorded as it is.
  Before it: PHASE 3 (2026-10-04): G1 and E3 LIVE_PROVEN; C4 SET; D6 APPLIED (0018, run 37172530166);
  the expect=after inventory and the Phase 3 exit evidence remain.
  Before it: PHASE 3 (2026-10-04): G1 and E3 LIVE_PROVEN; C4 SET; D6: inventory CLEAN, 0018 FROZEN
  and NOT_APPLIED (one refused attempt, consumed); the repaired route awaits a new T4.
  Before it: PHASE 3 (2026-10-03): R1A RELEASED; G1 and E3 LIVE_PROVEN; C4 SET; D6: inventory CLEAN,
  0018 FROZEN, its T4 apply at the owner.
  Before it: PHASE 3 (2026-10-03): R1A RELEASED (production 6f4420a9); G1 and E3 LIVE_PROVEN; C4 SET;
  D6: the inventory is CLEAN, and 0018's freeze is in preparation.
  Before it: PHASE 3 (2026-10-03): R1A RELEASED (production 6f4420a9); G1 LIVE_PROVEN; C4 SET; E3 CONFIGURED,
  NOT_YET_LIVE_PROVEN; D6 PREPARED, with its production-inventory route as a DRAFT PR.
  Before it: PHASE 3 (2026-10-03): R1A RELEASED (production 6f4420a9; R d4c25f2a); G1 LIVE_PROVEN; E3 CONFIGURED,
  NOT_YET_LIVE_PROVEN; C4 merged (the owner configures the Environment); D6 PREPARED (B: release live).
  Before it: PHASE 3 (2026-10-03): the writer (E3) and the resolver (G1) cutovers are CONFIGURED,
  NOT_YET_LIVE_PROVEN. C4 is prepared; D6 is designed.
  Before it: PHASE 3 (2026-10-03): the writer cutover is CONFIGURED, NOT_YET_LIVE_PROVEN (E3 switched). The
  resolver cutover (G1) is PREPARED (#204); its credential steps are the owner's.
  Before it: PHASE 3 (2026-10-03): E3-A YES, E3-B 30 days. The signing-key helper and the repaired runbook; the
  owner's credential switch is next. Production is unchanged (a2de125f).
  Before it: PHASE 3 (2026-10-03): WA RELEASED (production a2de125f / UCPE-PROD-WA-20261003-A; R 4130a6cd). The writer
  saves the whole core bundle in one transaction.
  Before it: PHASE 3 (2026-10-03): the §2.6 package (E4 + the W-A client, #196) and E3's proof (#197, J1)
  merged. The release is next.
  Before it: PHASE 3 (2026-10-03): migrations 0016 and 0017 APPLIED in production (runs 37110330500 and
  37110375659). The app is unchanged (17c9c053).
  Before it: PHASE 3 (2026-10-03): migrations 0016 (E1, W2; #192 → 77dbe59e) and 0017 (WB1, W-A; #193 → a53c50b0)
  are MERGED and unapplied. Their T4 applies are at the owner. Production is unchanged (17c9c053).
  Before it: PHASE 3 (2026-10-03): RCPT RELEASED (production 17c9c053 / UCPE-PROD-RCPT-20261003-A; R 06e4733e).
  The receipts and W-B are live.
  Before it: PHASE 3 (2026-10-03): the privilege rehearsal merged (#184 → 84280b6c, P1-P8 PASS ×2); W-B merged
  (#185 → 99908969); the release package UCPE-PROD-RCPT-20261003-A next.
  Before it: PHASE 3 (2026-10-03): three-state receipts merged (#182 → 43d5b543). The privilege audit and design
  are sealed; the rehearsal is next.
  Before it: PHASES 2-3 and 7 (2026-10-02): B9 RELEASED (production f046140b / UCPE-PROD-B9-20261002-A; R
  7f2b26e1).
  Before it: PHASES 2-3 and 7 (2026-10-02): B9-REST merged (#177 → c9637469). Migration 0015 is APPLIED (run
  37033014490, 37/37). The B9 release (T4-2) is next.
  Before it: PHASES 2-3 and 7 (2026-10-02): M1 CONFIG_PROVEN (REST). B9 waits on RD-1.
  Before it: PHASES 2-3 and 7 (2026-10-02): the owner's D1-D4 guidance is applied. M1 is pending (no receipt in
  the logs yet), and B9 waits on it.
  Before it: PHASES 2-3 and 7 (2026-10-02): PERS-0 measured (C1b and C3 FAIL: B9 is needed). OBS-2 RELEASED
  (production bc90e69b). The owner decision pack D1-D4.
  Before it: PHASES 2-3 and 7 (2026-10-02): OBS-2 RELEASED (production bc90e69b / UCPE-PROD-OBS2-20261002-A);
  REL-1 merged; UX-1 held.
  Before it: PHASES 2-3 and 7 (2026-10-02):
  - SEC-1 RELEASED: production 51a15fd0 / UCPE-PROD-SEC1-20261002-A;
  - FEAS-1 sealed;
  - UX-1 held.
  Before it: PHASES 2-3 and 7: SEC-1 (§13) MERGED and its release at the owner's Run action; FEAS-1 (§22 item
  8) sealed (2026-10-02). Production is unchanged: 46a1de68 / UCPE-PROD-OBS1-20261001-A.
  Before it: PHASES 2-3: OBS-1 RELEASED, 0014 APPLIED (2026-10-02).
  - Production: D 46a1de68 / UCPE-PROD-OBS1-20261001-A; the guard HEALTHY; rollback target D2 (H2-safe).
  - Core-evidence invariants (§8.2) are live in the database. F1 is CLOSED and delegated to the UOR thread.
  Before it: PHASES 2-3, AT OWNER T4 (2026-10-01).
  - Merged and gated: the 0014 one-shot apply route and the OBS-1 release package.
  - Awaiting the owner (classifier-refused): the 0014 apply and the OBS-1 deploy.
  - Production is unchanged. F1 is CLOSED and delegated to the UOR thread.
  Before it: PHASES 2-3 IN PROGRESS (2026-10-01): OBS-1 (structured events) and DBI-1 (migration 0014,
  UNAPPLIED; its rehearsal PASS) are MERGED on top of B2, B4, B3 and LOW-1. No deploy. F1 is CLOSED and delegated
  to the UOR thread.
  Before it: PHASE 2 IN PROGRESS (2026-10-01): B2, B4, B3 (reproducible build, REPRODUCIBLE=PASS) and LOW-1
  are MERGED; B5 is deferred by the owner; no deploy. F1 is CLOSED and delegated to the UOR thread.
  Before it: PHASE 2 IN PROGRESS (2026-10-01): B2 (workflow pinning) and B4 (release and H2-safe rollback
  tooling) are MERGED; B3 is next. F1 is CLOSED and delegated to the UOR thread.
  Before it: F1 CANARY PASS, LIVE ISOLATION PASS (2026-10-01): the owner issued the credential
  uor-radar-2026-10 (ACTIVE); the UCPE→UOR handoff package is finalized; next is the UOR-side boundary.
  Before it: F1 ENABLED, NO CREDENTIAL (2026-10-01): the owner enabled the route; the post-enable check
  PASSED; every call is refused until a credential exists.
  Before it: F1 RELEASED, ROUTE OFF (2026-10-01): production D2 5a3ef022 / UCPE-PROD-F1-AUTOMATION-20261001-A,
  re-pinned (R 3ad53b87), guard HEALTHY; no credential; UOR and Cron untouched.
  Before it: F1 MERGED (M 5da10ef3) and 0013 APPLIED (production, PASS); the release identity
  UCPE-PROD-F1-AUTOMATION-20261001-A is prepared. Before it: F1-MERGE-GATE-A (2026-10-01). The final review on this head, then the merge, then the 0013 T4
  preparation. Before it: F1-MERGE-READINESS-A (2026-09-30). Draft PR #144 is published, not merged. The code gaps are
  closed, and the real-PG rehearsal passed. The Codex review gate is OPEN (quota). Nothing is applied, deployed,
  enabled or issued.
  Before it: F1-GOVERNED-AUTOMATION-LOCAL-A (2026-09-30), committed and verified LOCALLY
  (feat/f1-governed-automation). Not pushed, deployed or enabled; 0013 is not applied.
  Before it: W26 RELEASE CLOSED (2026-09-30): W26_RELEASE_CLOSED; SAFE_MILESTONE_REACHED_FOR_AD_HOC_INTEGRATION.
  - the W26 CONTROLLED_SMOKE ran once: PASS_HTTP. The one-row DB proof: PASS_PROVEN (run_af48fd1e…);
  - the H2 hold is unchanged; there is no directional, skill or model PASS;
  - production is D 2096af6d / UCPE-PROD-TC-V1-STAMP-20260930-A;
  - re-pinned (#142 → 6becb100); guard 36715108033 HEALTHY;
  - the smoke tools are SEALED and CONSUMED (marker .work/w26_smoke/EXECUTED).
  This record: chore/state-tc-v1-release, published and merged under the owner's standing authorization.
  Before it: RELEASE IDENTITY PREPARED (2026-09-30):
  - UCPE-PROD-TC-V1-STAMP-20260930-A at e7309c31, local and NOT_PUBLISHED;
  - main 86c9496f (#140 merged; #139 closed unmerged);
  - deploy, re-pin, smoke and DB read are NOT_RUN.
  This record is local (prep/release-identity-tc-v1-stamp).
  Before it: W26 MERGED (2026-09-30):
  - #138 → main d790e0ff, with the §2.6 pin closure 3ffc21e9…;
  - identity, deploy, re-pin, smoke and DB read are NOT_RUN;
  - production is unchanged.
  This record is chore/state-w26-repair, superseding #139.
  Before it: W26 PUBLISHED FOR REVIEW (2026-09-30):
  - PR #138 (79d43d38 on main e09dee01), with the §2.6 pin closure 3ffc21e9…;
  - RC1 and the migration-apply record are merged (#136, #137);
  - no deploy.
  Before it: W26 EXECUTED LOCALLY (2026-09-30):
  - be4b9939 on RC1, §2.6; pin closure 212ea637… → 3ffc21e9…; VERIFY 3999; Codex NONE;
  - RC1 (#136) and the STATE record (#137) are published for review, not merged;
  - the release preparation is complete.
  This record is local (chore/state-w26-local).
  Before it: PHASE-1 PREPARED (2026-09-29): RC1 (the Route C resolver, f1924495) committed locally and
  verified; W26 (the writer §2.6 package) prepared as patches, never applied. Both await owner boundaries.
  Before it: MIGRATIONS 0011 AND 0012 APPLIED (T4 PASS: run 36583531813, then run 36586262979, 2026-09-29):
  - predictions carries the tc-v1 stamp columns;
  - prediction_resolution_status exists, empty and locked down;
  - nothing writes either yet.
  This record is local (chore/state-post-0011-0012-apply).
  Before it: MIGRATION 0011 APPLIED (T4 PASS, run 36583531813, 2026-09-29):
  - main is b11a8e53, with #133, #134 and #135 merged;
  - predictions carries the four tc-v1 stamp columns and three CHECKs, and no row is stamped;
  - 0012 is merged, not applied.
  This record is local (chore/state-post-0011-apply).
  Before it: POST-132 (2026-09-29):
  - PRs #130, #131 and #132 MERGED (main 30b40662, CI success);
  - D4 rq-v1 and D5 0012 ADOPTED;
  - migrations 0011 (500e5b83) and 0012 (6ccf60eb) REBUILT on 30b40662 as local publication candidates, verified
    and reviewed, not pushed or applied;
  - the writer/resolver integration pack is decision-ready.
  This record is local (chore/state-post-132).
  Before it: RESOLVER_P1 MERGED (post-129): PR #129, main 6fb3e8b4; CI success; §2.6 CLOSED for publication. Its
  STATE record merged as PR #130. Earlier on 2026-09-29: the local candidate 35545f4d (code PASS) and its STATE record 9de97e0d;
  c7cb70f8 and fb765188 stay unaccepted.
  Previous milestone, 2026-09-27: H2 HOLD VERIFIED LIVE: production 080f20a9 / UCPE-PROD-H2-HOLD-20260927-A.
  The CONTROLLED_SMOKE
  returned PASS_PROVEN (the legacy 4H and 1H SKILL_DEMONSTRATED verdicts held; no contamination). The re-pin is MERGED
  (PR #127, main 9a1db2dd), and the canonical guard is HEALTHY (run 36310977790). This STATE record is local
  (chore/state-post-127).
  H2 Q5 ADJUDICATED: UNAVAILABLE. H2-G2 (α 0.001, g 0.07) keeps its modeled PASS (36/36). Its
  operating density (1–6 contributions per counted window) is not yet validated, and the informative-call floor is
  unmet everywhere (at the observed rates, around 2028 or later). History: the v2 guard was analytically REJECTED;
  the budget was RULED; v3 (g 0.09) FAILED (S01) and stays on record. H1
  COMPLETE. NG-1 CLOSED (owner ruling, 2026-09-25): K KILLED (valid for H ≤ 0.85); T NOT_DEMONSTRATED; the free-data
  route not demonstrated; W(b) not run; F3 unspent. Still excluded:
  - any second CONTROLLED_SMOKE (the executor refuses a second run), and any rollback or later deploy without a new
    T4;
  - any implementation of D3, and any other change to the live skill gate, its tests or its data, without its own
    authorization (it is a hard gate, so treat it as T2); and the count-only production read without its own
    database authorization;
  - any NG-1 run, fetch or W(b); reopening NG-1 or R4; any new model research;
  - ruling 3, any F3 fetch, and any collector (product evidence or research data);
  - a freeze, wiring, a new T0, any database action and any HF deploy;
  - any further F1/F2 read, and any implementation of the D-1 rulings without its own authorization
    (OWNER_BOUNDARY 5).
CURRENT_BRANCH=chore/state-a4-card04-companion (this record, merged with main 267a6eaf). Local and unpublished:
  feat/p7r-provider-pool-singleflight (Lane R, worktree scratchpad/wtR of session ba4955d3) and Lane P's branch.
  Before it: chore/state-a4-card04-companion (this record, on main fc03be8e) and feat/a4-card04-companion @
  93ab50de (e882d81, 66133c5, db176ec, 116b68c, 4edd6e4, 4f3f00c, 13d3b16, 0652c43, d263c09, 93ab50d;
  worktree scratchpad/wt of session ba4955d3).
  Before it: chore/state-phase4-infeasible (this record, rebuilt on main e468f1f1 by a merge that keeps
  cd4563c and a44ccf6; worktree lanes30/state).
  Before it: chore/state-phase4-infeasible (a44ccf6; worktree lanes30/state). Lanes:
  feat/t1-test-wallclock @ ebbabe6 (lanes31/testwall) and docs/p8-tooling-inventory @ 953fe26 (lanes31/inventory).
  Before it: chore/state-phase4-infeasible (the Phase 4 record, cd4563c; worktree lanes30/state).
  Before it: feat/phase4-r4-c1-candidate (#225; worktree lanes29/c1).
  Before it: chore/state-phase3-closed (this record; worktree lanes29/state).
  Before it: chore/state-e2-cutover (this record; worktree lanes28/state2).
  Before it: chore/state-e2-released (this record; worktree lanes28/state).
  Before it: feat/e2-space-reader-identity (this record; worktree lanes28/e2).
  Before it: chore/phase3-exit-reaudit (this record; worktree lanes30/close).
  Before it: chore/d6-0018-applied (this record; worktree lanes29/reg).
  Before it: fix/d6-0018-login-roles (this record; worktree lanes28/fix).
  Before it: feat/d6-migration-0018 (this record; worktree lanes27/m0018).
  Before it: chore/state-d6-inventory-clean (this record). Next: feat/d6-migration-0018 (the freeze).
  Before it: chore/state-c4-set (this record; worktree lanes26/state). DRAFT #212 is feat/d6-core-write-inventory-route
  (worktree lanes26/inv), from main 9d2f109c.
  Before it: feat/g1-remove-owner-fallback (#206; worktree lanes24/nofallback), rebased after the deploy.
  Merged since: #209 (R-1a), #210 (identity → D), #211 (re-pin → R).
  Before it: fix/g1-mask-owner-role (#205 → 70a03e4); feat/g1-resolver-cutover-prep (#204); chore/state-e3-switched
  (#203).
  Before it: feat/e3-writer-signing-key-helper (#202 → 38b9860b; worktree lanes24/helper).
  Before it: chore/state-wa-released (#201 → 4f970785; worktree lanes23/state_rel).
  - Merged: release/prod-wa (#199 → D a2de125f) and release/prod-wa-repin (#200 → R 4130a6cd).
  Before it: chore/state-s26-e3-merged (#198 → a6f881c9; worktree lanes23/state).
  - Merged: feat/s26-e4-writer-wa-client (#196 → b29ef4e4) and feat/e3-es256-signing-proof (#197 → c909915e).
  Before it: chore/registry-0016-0017-applied (#195 → ee9173c9; worktree lanes22/registry_m17).
  Before it: chore/state-migrations-0016-0017 (#194 → 8cbfdbc3; worktree lanes22/state_m17).
  - Merged: feat/migration-0016-least-privilege-roles (#192 → 77dbe59e) and feat/migration-0017-forecast-bundle
    (#193 → a53c50b0).
  Before it: chore/state-wa-rehearsed (#191 → 22b2a6ae; worktree lanes21/state_wa).
  - Merged: feat/phase3-wa-rehearsal (#190 → 53e83537).
  Before it: chore/state-rcpt-released (#189 → cb5d50d8; worktree lanes21/state_rel).
  - Merged: release/prod-rcpt (#187 → D 17c9c053) and release/prod-rcpt-repin (#188 → R 06e4733e).
  Before it: chore/state-phase3-rehearsed (#186 → ac7cd4a1; worktree lanes21/state_p3b).
  - Merged: feat/phase3-privilege-rehearsal (#184 → 84280b6c) and feat/phase3-wider-core-receipt (#185).
  Before it: chore/state-phase3-resume (#183 → 6ef98f89; worktree lanes21/state_p3).
  - Merged: feat/phase3-three-state-receipts (#182 → 43d5b543).
  Before it: chore/state-b9-released (#181 → 9f4f3f27; worktree lanes19/state_rel).
  - Merged: release/prod-b9 (#179 → D f046140b) and release/prod-b9-repin (#180 → R 7f2b26e1).
  Before it: chore/registry-0015-applied (this record and the registry; worktree lanes19/registry).
  - Merged: feat/b9-rest-atomic-bundle (#177 → c9637469).
  Before it: chore/state-m1-config-proven (#176 → bf86f4c0; worktree lanes18/state_m1).
  Before it: chore/state-d1-guidance-s8-d4 (#175 → 9e997f0a; worktree lanes18/state_d1).
  - Local, held: feat/ux1-in-band-label @ f92ff055.
  Before it: chore/state-sec1-release-feas1 (PR #166, this record), extended after the SEC-1 release, with main R
  merged in. Worktree lanes18/state.
  - Merged: release/prod-sec1 (#167 → 504ddd5d).
  - Local, held: feat/ux1-in-band-label @ f92ff055.
  Before it: chore/state-sec1-release-feas1 (this record; a draft PR, merged after the SEC-1 re-pin), from main
  51a15fd0. Worktree lanes18/state.
  - Merged: feat/sec1-app-security-controls (#164 → 04074527); prep/release-identity-sec1 (#165 → 51a15fd0);
    chore/state-0014-route-obs1-release (#161 → 39c6d518).
  - Local: feat/ux1-in-band-label @ d60ecaa.
  Before it: chore/state-0014-route-obs1-release (PR #161, this record), extended after both T4s, with main
  93c55f97 merged into it. Worktree lanes17/state2.
  - Merged: release/prod-obs1 (#162 → 00b6fa94); chore/registry-0014-applied (#163 → 93c55f97).
  Before it: chore/state-0014-route-obs1-release (this record), from main 46a1de68. Worktree lanes17/state2.
  - It is a draft PR, merged only after both T4s.
  - Merged: feat/apply-migration-0014 (#159 → 3e69430e); prep/release-identity-obs1 (#160 → 46a1de68);
    chore/state-obs1-dbi1-closure (#158 → dcfc7aa0).
  Before it: chore/state-obs1-dbi1-closure (PR #158, merged as dcfc7aa0), from main 05a5d1ad. Worktree
  lanes17/state.
  - Merged: feat/obs1-structured-events (#156 → c44da688) and feat/dbi1-core-evidence-invariants (#157 →
    05a5d1ad); chore/state-b3-low1-closure (#155 → b0bf17ca).
  Before it: chore/state-b3-low1-closure (PR #155, merged as b0bf17ca), from main 52965cc2. Worktree
  lanes16/state.
  - Merged: feat/b3-reproducible-build (#153 → d9e42a60) and fix/release-probe-allowlist (#154 → 52965cc2).
  Before it: chore/state-b2-b4-merged (PR #152, merged as a490ff2b), from main fdfefd2c. Worktree lanes15/state.
  - Merged: feat/b2-workflow-pinning (#150) and feat/b4-release-tooling (#151).
  - Local and superseded, never published: chore/state-roadmap-resume (041c57e).
  Before it: chore/state-f1-canary-pass (PR #149, merged as 0ce9694f). Its worktree was lanes13/state3 in
  the session scratchpad.
  Before it: chore/state-f1-route-enabled (PR #148, merged as 2992842f), from main c2bd1247.
  Before it: chore/state-f1-release (PR #147, merged as c2bd1247), from main 3ad53b87.
  Before it: release/prod-f1-automation (PR #146, merged as R 3ad53b87) and prep/release-identity-f1-automation
  (PR #145, merged as D2 5a3ef022).
  Before it: feat/f1-governed-automation (PR #144, merged as M 5da10ef3), from main f19d7575:
  - 028ded8, 4f9ae93, 0bc11ff and 446260c (the earlier record);
  - d9df2371 (merge readiness);
  - bf50005 (the readiness record), eb6976d (pre-review hardening);
  - 8b22efe (the capacity contract), 8f7923c (the review-2 repair);
  - this STATE record.
  Its worktree is lanes12/f1 in the session scratchpad.
  Before it: feat/f1-governed-automation (then LOCAL): 028ded8, 4f9ae93, 0bc11ff and its STATE record.
  Before it: chore/state-tc-v1-release (PUBLISHED; merged under the standing authorization), from main 6becb100: the
  release STATE records a80c54e5 and c61adbb, plus this W26-closure record. Its worktree is lanes11/state in the session
  scratchpad.
  - Merged by Claude under the standing authorization: prep/release-identity-tc-v1-stamp (#141 → D 2096af6d) and
    release/prod-tc-v1-stamp (#142 → 6becb100).
  Before it: prep/release-identity-tc-v1-stamp (then LOCAL), from main 86c9496f: the identity commit e7309c31 and its
  STATE record. Its worktree is lanes10/identity in the session scratchpad.
  - Merged: chore/state-w26-repair (#140 → 86c9496f) and feat/writer-tc-v1-stamp-w26 at 79d43d38 (#138 → d790e0ff).
  - Closed unmerged: chore/state-w26 at 03e99fb0 (#139), superseded by #140.
  - Merged, and staying on origin: feat/resolver-route-c-rq-v1 (#136) and chore/state-post-0011-0012-apply (#137).
  - Superseded and never published: be4b9939 (W26 on RC1) and 0e830b4a (this record before reconciliation), both on
    local branches.
  - Merged, and staying on origin:
    - chore/state-post-132 (#133, 853f1eb2);
    - feat/migration-0011-provenance (#134, 500e5b83);
    - feat/migration-0012-resolution-status (#135, 6ccf60eb).
  - Superseded local candidates, never published:
    - archive/migration-0011-on-6fb3e8b (3433d306);
    - archive/migration-0012-on-3433d30 (bc92e873);
    - archive/state-e11ded9-on-7f59be5 (e11ded96).
  - Merged, and staying on origin: chore/state-post-129 (#130), feat/target-contract-v1 (#131) and
    feat/resolver-hardening-b80 (#132).
  - A read-only checkout of 30b40662 is lanes7/read-30b4066.
  feat/resolver-eligibility-phase1b (#129) is merged and stays on origin. feat/resolver-exactness-phase1a (local,
  517887fc) is contained in it.
  chore/state-post-127 was published and merged as PR #128 (main 6f5038d0); its worktree was lanes2/state127.
  release/prod-h2-hold (#127), prep/release-identity-h2-hold (#126) and feat/h2-failclosed-hold (#125) are merged and
  stay on origin.
  chore/state-post-123 (#124), chore/state-post-122 (#123), -121 (#122), -120 (#121), -119 (#120), -118 (#119),
  -117 (#118), -116 (#117), -115 (#116), -114 (#115), -113 (#114), -112 (#113) and -110 (#112) are merged and stay on origin;
  -110's push is the R4 commitment's timestamp.
  The main checkout (/Users/kha/Documents/Kha-app/UCPE) is on main at 9a1db2dd, clean, and its working-tree STATE.md is
  current as of that commit. It was fast-forwarded under the smoke authorization's pre-checks, on 2026-09-27. Before
  that it was on 080f20a9 (the fresh T4's preconditions), fa5c0da7 (the first T4's preconditions), 1dfe2d22 (T2 hold
  authorization) and 597e5c95 (Q5 authorization). Before that it was frozen on chore/state-post-104 at 2c6df51
  through the NG-1 Stage-1 rerun (repair review F3; audit L3). That branch is kept.
  STATE records are still made in separate worktrees, and ./verify.sh never runs in the main checkout
  (STANDING_RULES).
  The batch branches are merged, and remain on origin:
  - prep/0010-legacy-table-security;
  - prep/v2-integration-prep;
  - prep/v2-history-serving;
  - chore/state-post-106.
LAST_GREEN_SHA=267a6eaf (main, #230: the Card-04 companion; push CI 37271854804 and the reproducible build
  37271854824 green).
  Before it: fc03be8e (main, #229: the STATE record; push CI 37215106950 and the reproducible build green).
  Before it: e468f1f1 (main, #228: the A4 artifact; push CI green).
  Before it: 7a5ca4f9 (main, #225: the R4-C1 identity and the Phase 4 record).
  Before it: c10af044 (main, #224: Phase 3 closed).
  Before it: e344d002 (main, #223: the E2 cutover accepted).
  Before it: 6827e631 (main, #222: E2 released and identified). Push CI 37190639311 and the reproducible
  build 37190639232: success.
  Before it: bb2a49bd (main = R, the E2 re-pin over D 1caa8b08, deployed). Push CI 37190040672 and the
  reproducible build 37190040630: success. The guard PASS on R (run 37190049170).
  Before it: 1830bbc6 (main, #218: the Phase 3 exit re-audit). Push CI 37182940609 and the reproducible
  build 37182940636: success.
  Before it: 9a8a1c04 (main, #217: 0018's applied_run). Push CI 37181351658 and the reproducible build 37181351716: success.
  Before it: 82ed9c48 (main, #216: the repaired route). Push CI 37172067820 and the reproducible build 37172067764: success.
  Before it: b7d54fcc (main, #215: the freeze). Push CI 37153310915 and the reproducible build 37153310966: success.
  Before it: 8c900a0b (main, #214: the inventory record).
  Before it: 946145bc (main, #212 merged). Push CI 37149005706 and the reproducible build 37149005710: success.
  Before it: 9d2f109c (main, #206 merged). Push CI 37141757629 and the reproducible build 37141757688: success.
  Before it: d4c25f2a (main = R, the R1A re-pin, over D 6f4420a9, deployed). Push CI 37140995581 (success). The guard PASS on R (run 37141007416).
  Before it: 70a03e4 (main, PR #205: the identity line names only UCPE's roles). Push CI success (run 37131173306);
  reproducibility success (run 37131173329).
  Before it: 38b9860b (main, PR #202: the signing-key helper and the runbook). Push CI success (run
  37121324613); reproducibility success (run 37121324647).
  Before it: 4f970785 (main, PR #201: the WA STATE record and the runbook). Push CI success (run 37118661804);
  reproducibility success (run 37118661825).
  Before it: 4130a6cd (main = R, the WA re-pin, over D a2de125f, deployed). The guard PASS on R (run 37118169873).
  Before it: a2de125f (D). Push CI 37116841080; reproducibility 37116841053.
  Before it: c909915e (main, PR #197: E3's proof). Its PR checks are all green; its push CI is running at this
  record's commit.
  Before it: 8cbfdbc3 (main, PR #194: the STATE record). Push CI success (run 37109433419); reproducibility success
  (run 37109433420). Both T4 applies ran at this SHA.
  Before it: a53c50b0 (main, PR #193: migration 0017). Push CI success (run 37108186970); reproducibility success
  (run 37108186949); its PR checks 13/13 at ad29b24. Production is unchanged (D 17c9c053).
  Before it: 77dbe59e (main, PR #192: migration 0016). Push CI 37106452298; reproducibility 37106452296.
  Before it: 53e83537 (main, PR #190: W-A rehearsed). Push CI success (run 37100317594); reproducibility success (run
  37100317641). Production is unchanged (D 17c9c053).
  Before it: cb5d50d8 (main, PR #189). Push CI 37099614461; reproducibility 37099614519.
  Before it: 06e4733e (main = R, the RCPT re-pin, over D 17c9c053, deployed). Push CI success (run 37098315075); the guard
  PASS on R (run 37098323783).
  Before it: 99908969 (main, PR #185: W-B). Push CI success (run 37059683889); reproducibility success (run
  37059683937).
  Before it: 84280b6c (main, PR #184: the privilege rehearsal). Push CI 37057967928; reproducibility 37057967930.
  Before it: 43d5b543 (main, PR #182: three-state receipts). Push CI success (run 37049878403); reproducibility
  success (run 37049878335).
  Before it: 7f2b26e1 (main = R, the B9 re-pin; over D f046140b, deployed). Guard PASS on R (run 37043734896).
  Before it: c9637469 (main, PR #177: B9-REST). Push CI success (run 37017429357); reproducibility PASS (run
  37017429630).
  Before it: 9e997f0a (main, PR #175: the D1-D4 guidance record). Push CI success (run 36982811888);
  reproducibility PASS (run 36982811701).
  Before it: fd24a873 (main, PR #174: the decision-pack STATE record). Push CI success (run 36975298295);
  reproducibility PASS (run 36975298258).
  Before it: 904fb048 (main = R, the OBS-2 re-pin; over D bc90e69b). Push CI success (run 36971919795);
  reproducibility PASS (run 36971919733).
  Before it: 504ddd5d (main = R, PR #167: the SEC-1 re-pin; over 51a15fd0 = D, deployed).
  - Push CI success (run 36966111025); reproducibility PASS (run 36966111011).
  - The guard on R: PASS 8/8 (run 36966123856), delta [].
  Before it: 51a15fd0 (main = the SEC-1 release commit D, PR #165; over 04074527, PR #164: SEC-1; over 39c6d518, PR
  #161).
  - Push CI success (run 36963641188).
  - B3 REPRODUCIBLE=PASS + SMOKE=PASS (run 36963641128).
  - The guard on D: PASS (run 36963992290).
  Before it: 93c55f97 (main, PR #163: the 0014 registry; over 00b6fa94, PR #162: the re-pin; over 46a1de68 = D).
  - Push CI success (run 36956596549); reproducibility PASS (run 36956596656).
  - The guard on 00b6fa94: GUARD_VERIFY=PASS 8/8 (run 36955866384), delta [].
  Before it: 46a1de68 (main = D, PR #160: the OBS-1 release identity; over 3e69430e, PR #159: the 0014 route;
  over dcfc7aa0, PR #158).
  - Push CI success (run 36911573827).
  - B3 on D: REPRODUCIBLE=PASS sha256:ae4eb5b17351…bbbef, SMOKE=PASS (run 36911573784).
  - The guard: GUARD_VERIFY=PASS on D (run 36911609195), delta [Dockerfile, api/analysis_service.py, api/app.py,
    config/build_info.py]. Scheduled on D at 19:39Z: success (run 36915853051).
  Before it: 05a5d1ad (main, PR #157: DBI-1; over c44da688, PR #156: OBS-1; over b0bf17ca, PR #155). push CI
  success (run 36903744546). The reproducibility proof on main: PASS (run 36903744369). The guard: HEALTHY on it
  (run 36903795271), delta [Dockerfile, api/analysis_service.py, api/app.py].
  Before it: b0bf17ca (main, PR #155: the STATE closure; STATE.md only).
  Before it: 52965cc2 (main, PR #154: LOW-1; over d9e42a60, PR #153: B3). push CI success (run 36894534715). The
  reproducibility proof on main: PASS (run 36894534728). The guard: HEALTHY on it (run 36894604710), delta
  [Dockerfile].
  Before it: a490ff2b (main, PR #152: the corrected STATE record). push CI success (run 36868480424).
  Before it: fdfefd2c (main, PR #151: B4; over fc441c52, PR #150: B2). push CI success (run 36861888464).
  Before it: 0ce9694f (main, PR #149: the canary record and the handoff package). Push CI success (run 36842825376).
  Before it: 2992842f (main, PR #148: the enable record and the CORS correction). Push CI success (run
  36842825376).
  Before it: c2bd1247 (main, PR #147: the F1 release record). Push CI success (run 36831002541).
  Before it: 3ad53b87 (main, PR #146: the re-pin). PR CI success on P; push CI success (run 36828550280); the guard HEALTHY
  on it (run 36828594390), delta [].
  Before it: 5a3ef022 (D2, main, PR #145: the identity). Push CI success (run 36825516122); tree 18883f47.
  Before it: 5da10ef3 (main, PR #144: F1). Push CI success (run 36820447090); tree d798502b.
  Before it: f19d7575 (main, PR #143: the W26 closure record). CI success (run 36722645234).
  Before it: 6becb100 (main, PR #142: the re-pin). CI success (run 36715048291).
  Before it: 2096af6d (D, main, PR #141: the identity). CI success (run 36714014523); tree 68917d99 as recorded.
  Before it: 86c9496f (main, PR #140: the STATE repair). CI success (run 36703760641); its tree equals the
  recomputed merge.
  Before it: d790e0ff (main, PR #138: W26). CI success (run 36699280110); its tree is the recorded 9de0f067.
  Before it: e09dee01 (main, PR #137: the migration-apply STATE record), after 200e6ad6 (PR #136: RC1). CI succeeded
  on both (runs 36685544014 and 36685512304). The trees equal the recorded 098bddfa and 51b7f9a6.
  Before them: b11a8e53 (main, PR #135: the 0012 route), after b207a1a6 (PR #134: the 0011 route) and f844452b (PR #133:
  the post-132 record).
  - CI success on b11a8e53 (run 36580184092), b207a1a6 and f844452b.
  - Each merge tree equals the tree recorded before the push: c95d4431, d47aa6e9 and e6971e2b.
  - The 0011 apply ran on b11a8e53 (run 36583531813, PASS).
  Before them: 30b40662 (main, PR #132: N2), after 201bdd22 (PR #131: N1) and 133c68f6 (PR #130: the post-129 record).
  CI success on each (runs 36571791856, 36571237239 and 36570739861). Each merge tree equals the recomputed merge of
  its parents.
  Before them: 6fb3e8b4 (main, PR #129: RESOLVER_P1). CI success (run 36532446966); its tree equals the locally verified
  9de97e0d tree (clean worktree VERIFY=PASS 2757). Before it: 6f5038d0 (main, PR #128) and 9a1db2dd (main, PR #127:
  the production re-pin and its STATE record).
  - This loop pushed release/prod-h2-hold at e4f601fa under the owner's push-only T3. The merge tree 16fa5289 was
    recorded before the push. #127 was merged from the owner's account at 2026-09-27T09:54:04Z.
  - Verified by this loop:
    - parents (080f20a9, e4f601fa);
    - tree 16fa5289, equal to the recorded tree;
    - exactly the 3 files.
  - Checks, 2026-09-27, all passed:
    - the exact-head check CI (run 36310550050, created 09:48:42Z);
    - the exact-main check CI (run 36310830119, 09:54:06Z);
    - the canonical guard dispatch (run 36310977790), HEALTHY.
  Before it: 080f20a9 (main, PR #126: the release identity UCPE-PROD-H2-HOLD-20260927-A and its STATE record).
  - This loop pushed prep/release-identity-h2-hold at 8e1b98f0 under the owner's push-only T3. The merge tree
    474f4fe1 was recorded before the push. #126 was merged from the owner's account at 2026-09-26T18:51:28Z.
  - Verified by this loop:
    - parents (fa5c0da7, 8e1b98f0);
    - tree 474f4fe1, equal to the recorded tree;
    - exactly the 4 files.
  - Checks, 2026-09-26, both passed:
    - the exact-head check CI (run 36263793970, created 18:47:35Z);
    - the exact-main check CI (run 36264018888, 18:51:31Z).
  - 080f20a9 is also the production commit (deployed 2026-09-26T19:47:36Z).
  Before it: fa5c0da7 (main, PR #125: the H2 fail-closed hold and its STATE record).
  - This loop pushed feat/h2-failclosed-hold at 19b24a6b under the owner's push-only T3. The merge tree 1dc79429 was
    recorded before the push. #125 was merged from the owner's account at 2026-09-26T17:41:34Z.
  - Verified by this loop:
    - parents (1dfe2d22, 19b24a6b);
    - tree 1dc79429, equal to the recorded tree;
    - exactly the 7 files.
  - Checks, 2026-09-26, both passed:
    - the exact-head check CI (run 36259485425, created 17:34:07Z);
    - the exact-main check CI (run 36259927237, 17:41:36Z).
  Before it: 1dfe2d22 (main, PR #124: the H2 Q5-adjudication record, STATE.md only).
  - This loop pushed chore/state-post-123 at 2e0ecfd7 under the owner's push-only T3. The merge tree 188f8419 was
    recorded before the push. #124 was merged from the owner's account at 2026-09-26T15:52:23Z.
  - Verified by this loop:
    - parents (597e5c95, 2e0ecfd7);
    - tree 188f8419, equal to the recorded tree;
    - STATE.md blob dfe3a28b.
  - Checks, 2026-09-26, all passed:
    - the exact-head check CI (run 36253224197, created 15:48:34Z);
    - the exact-main check CI (run 36253449747, 15:52:25Z);
    - the scheduled Runtime Source Integrity Guard on 1dfe2d22 (run 36255867709, 16:33:16Z).
  Before it: 597e5c95 (main, PR #123: the H2 record through H2-G2, STATE.md only).
  - This loop pushed chore/state-post-122 at 57b8443f under the owner's push-only T3. The merge tree 8b4f07d8 was
    recorded before the push. #123 was merged from the owner's account at 2026-09-26T13:57:52Z.
  - Verified by this loop:
    - parents (83b099de, 57b8443f);
    - tree 8b4f07d8, equal to the recorded tree;
    - STATE.md blob 2906e80e;
    - the only change is STATE.md, over six commits.
  - The exact-head check `CI` passed (run created 08:46:36Z), and so did the exact-main check `CI` (13:57:54Z),
    2026-09-26.
  Before it: 83b099de (main, PR #122: the NG-1 closure, H1 selection and H1 cleanup STATE record, STATE.md only).
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
LAST_VERIFY=PASS 2026-10-05 on this record's PR tree (main 267a6eaf plus STATE.md; the exact line is in the PR
  body).
  Before it: PASS 2026-10-05 on feat/a4-card04-companion @ 93ab50d, bytecode on: ruff ok | 6376 passed |
  schemas+smoke ok | scanners 3/3; the scratch-PostgreSQL 17.6 rehearsal A4C_REHEARSAL=PASS (39 cases and the
  card's python -I -B command). Before it: PASS on 0652c43 (6332; 38 cases) and 4f3f00c (6314; 35 cases),
  both superseded.
  Before it: PASS on this record's PR tree, 2026-10-04 (the exact line is in the PR body).
  Before it: PASS 2026-10-04: lane A 6018, lane B 6050, their composition 6054 (6e5dae9, scratch); a44ccf6's tree
  (the exact line is in the PR body).
  Before it: PASS on this record's PR tree, 2026-10-04 (the exact line is in the PR body).
  Before it: PASS on #225's PR tree, 2026-10-04 (the exact line is in #225's body).
  Before it: PASS on this record's PR tree, 2026-10-04 (the exact line is in the PR body).
  Before it: PASS on this record's PR tree, 2026-10-04 (the exact line is in the PR body).
  Before it: PASS on this record's PR tree, 2026-10-04 (the exact line is in the PR body).
  Before it: PASS on this record's PR tree, 2026-10-04 (the exact line is in the PR body).
  Before it: PASS on this record's PR tree, 2026-10-04 (the exact line is in the PR body).
  Before it: PASS on this record's PR tree, 2026-10-04 (the exact line is in the PR body).
  Before it: PASS on this record's PR tree, 2026-10-04 (the exact line is in the PR body).
  Before it: PASS on this record's PR tree, 2026-10-03 (the exact line is in the PR body).
  Before it: PASS on this record's PR tree, 2026-10-03 (the exact line is in the PR body).
  Before it: PASS on this record's PR tree, 2026-10-03 (the exact line is in the PR body). #212's tree: PASS 5726
  (c08f722). #206's tree: PASS 5645.
  Before it: PASS ruff ok | 5561 passed, 23 warnings | schemas+smoke ok | scanners 3/3 · 2026-10-03 (this record's PR,
  with C4-PIN and the re-pin, in its clean worktree lanes24/nofallback, before its push). Before it: the code at e9777a6, in its clean worktree lanes24/nofallback; this STATE commit adds docs only).
  - The first run failed the secrets scanner on the new test's constant named SECRET. It was renamed, and the scanner
    was not narrowed.
  Before it: PASS ruff ok | 5517 passed, 23 warnings | schemas+smoke ok | scanners 3/3 · 2026-10-03 (#203, at
  38b9860b, in its clean worktree lanes24/state_cutover, before its push).
  Before it: PASS ruff ok | 5517 passed, 23 warnings | schemas+smoke ok | scanners 3/3 · 2026-10-03 (#202, on
  4f970785, in its clean worktree lanes24/helper, before its push).
  - The first run failed one test, the repository's no-silent-skips rule: the Node check had a skipif. Node is already
    required (the frontend tests run it), so the check is now unconditional. The rerun passed.
  Before it: PASS ruff ok | 5382 passed, 23 warnings | schemas+smoke ok | scanners 3/3 · 2026-10-03 (this record, at 8cbfdbc3).
  Before it: PASS ruff ok | 5382 passed, 23 warnings | schemas+smoke ok | scanners 3/3 · 2026-10-03.
  - At #193's head (ad29b24), in its clean worktree, before its push. This record is verified before its own push.
  Before it: PASS ruff ok | 5077 passed, 23 warnings | schemas+smoke ok | scanners 3/3 · 2026-10-03.
  - This record at R 06e4733e, verified before its push.
  Before it: PASS ruff ok | 5077 passed, 23 warnings | schemas+smoke ok | scanners 3/3 · 2026-10-03.
  - This record at main 99908969, verified before its push.
  Before it: PASS ruff ok | 5030 passed, 23 warnings | schemas+smoke ok | scanners 3/3 · 2026-10-03.
  - This record at main 43d5b543, verified before its push.
  Before it: PASS ruff ok | 4824 passed, 23 warnings | schemas+smoke ok | scanners 3/3 · 2026-10-02.
  - This record at R, verified before its push (the PR body).
  Before it: PASS ruff ok | 4824 passed, 23 warnings | schemas+smoke ok | scanners 3/3 · 2026-10-02.
  - SEC-1 at its exact commit 318431b5, and #165's identity change.
  - This record is verified before its push (the PR body).
  Before it: PASS ruff ok | 4785 passed, 23 warnings | schemas+smoke ok | scanners 3/3 · 2026-10-02.
  - #163's registry change, at c82822e0 plus the change.
  - This record is verified before its push (the PR body).
  Before it: PASS ruff ok | 4785 passed, 23 warnings | schemas+smoke ok | scanners 3/3 · 2026-10-01.
  - At 9630d19 (#159's head), and again for #160's identity change.
  - This record is verified before its push (the PR body).
  Before it: PASS ruff ok | 4671 passed, 23 warnings | schemas+smoke ok | scanners 3/3 · 2026-10-01 (local, OBS-1 +
  DBI-1 combined; main 05a5d1ad differs from it only by STATE.md). OBS-1 alone: PASS 4631 at b9ca157. DBI-1 alone:
  PASS 4650 at 4a1c557. This record is verified before its push (the PR body).
  Before it: PASS ruff ok | 4610 passed, 23 warnings | schemas+smoke ok | scanners 3/3 · 2026-10-01 (local, B3 + LOW-1
  combined, on tree 1ad97975, which equals main 52965cc2's tree). B3 alone: PASS 4602 at 2af26f0c. LOW-1 alone:
  PASS 4597 at 9afa2dbd. This record is verified before its push (the PR body).
  Before it: PASS ruff ok | 4586 passed, 23 warnings | schemas+smoke ok | scanners 3/3 · 2026-10-01 (a fresh detached
  verify of B4 at 9ac70a2; B2 at 52cb9a2: PASS 4571). This record is verified before its push (the PR body).
  Before it: PASS ruff ok | 4568 passed, 23 warnings | schemas+smoke ok | scanners 3/3 · 2026-10-01 (local, the
  enable record, PR #148). This record is verified before its push (the PR body).
  Before it: PASS ruff ok | 4568 passed, 23 warnings | schemas+smoke ok | scanners 3/3 · 2026-10-01 (local, the F1
  release record, PR #147).
  Before it: PASS ruff ok | 4568 passed, 23 warnings | schemas+smoke ok | scanners 3/3 · 2026-10-01 (local, the
  re-pin P 4ef8f14; the same count on the identity head and at M). This record is verified before its push
  (the PR body).
  Before it: PASS ruff ok | 4559 passed, 23 warnings | schemas+smoke ok | scanners 3/3 · 2026-10-01 (local, F1 at
  8f7923c, the review-2 repair).
  Before it: PASS ruff ok | 4496 passed, 23 warnings | schemas+smoke ok | scanners 3/3 · 2026-09-30 (local, F1
  merge readiness at d9df2371; the scanners are unmodified).
  - PR CI at d9df2371: the 0013 real-PG rehearsal succeeded (run 36747080987); the 0010 rehearsal succeeded.
  - This record (with the row-width guard and doc fixes): PASS 4498.
  Before it: PASS ruff ok | 4324 passed, 23 warnings | schemas+smoke ok | scanners 3/3 · 2026-09-30 (local, F1 at
  0bc11ff; the three scanners are unmodified).
  Before it: PASS ruff ok | 3999 passed, 23 warnings | schemas+smoke ok | scanners 3/3 · 2026-09-30 (local).
  - On P 24c66816, in a clean worktree: PASS 3999. The release record: PASS 3999. This W26-closure record: PASS 3999.
  - On the identity commit e7309c31, in a clean worktree; this record: PASS 3999.
  - Run on W26 be4b9939 (RC1 + W26 + the regenerated pin), in a clean worktree.
  - This STATE-only record: PASS 3673, in a clean worktree.
  - Earlier: PASS ruff ok | 3673 passed, 23 warnings | schemas+smoke ok | scanners 3/3 · 2026-09-29 (local).
  - Run on this STATE-only record, on main b11a8e53 (which carries both migration routes), in a clean worktree. The
    0012 record was re-verified the same way: PASS 3673.
  - Post-132: PASS ruff ok | 3673 passed, 23 warnings | schemas+smoke ok | scanners 3/3 · 2026-09-29 (local).
  - Run on feat/migration-0012-resolution-status 6ccf60eb (main 30b40662 + 0011 + 0012), in a clean worktree.
  - 0011 alone, at 500e5b83: PASS 3221.
  - This STATE-only record (T0) is re-verified on its own commit, in a clean worktree, before it is reported.
  - Post-129: PASS ruff ok | 2757 passed, 23 warnings | schemas+smoke ok | scanners 3/3 · 2026-09-29 (local).
  - Run on the RESOLVER_P1 tree (9de97e0d, identical to main 6fb3e8b4) in a clean detached worktree. This post-129
    STATE-only record (T0) is re-verified on its own commit in a clean worktree before it is reported.
  - Previous: PASS ruff ok | 2470 passed | schemas+smoke ok | scanners 3/3 · 2026-09-27 (local), run for the
    chore/state-post-127 record (main 9a1db2dd plus that STATE.md change; T0) in worktree lanes2/state127.
  - Earlier, the same result for the re-pin on release/prod-h2-hold, in worktree lanes2/repin:
    - on edc64df2; the 6 guard, baseline and build-info test files passed 113;
    - the guard, read-only against production with the new pin: HEALTHY, exit 0;
    - this STATE record (T0) was verified the same way before its commit.
  - Earlier, the same result for the release identity on prep/release-identity-h2-hold, in worktree lanes2/relid:
    - on 2b575abb; the targeted suites passed 111;
    - this STATE record (T0) was verified the same way before its commit.
  - H2's own checks, read-only: all thirteen H2 seal files verify.
  - Earlier, the same result for the H2 hold on feat/h2-failclosed-hold, in worktree lanes2/h2hold:
    - on e669e06f (the hold), again on ebfe2073 (the detail wording) and again on 4ea42593 (the headline); the
      targeted suites passed 167 each time;
    - this STATE record (T0) was verified the same way before its commit.
  - H2's own checks, read-only: all thirteen H2 seal files verify (the ten H2/Q5 seals and the three brief seals).
  - Earlier: PASS ruff ok | 2450 passed | schemas+smoke ok | scanners 3/3.
  - Run for the H2 Q5-adjudication record on chore/state-post-123 (main 597e5c95 plus that STATE.md change; T0), in
    its worktree.
  - H2's own checks, read-only: all eleven H2 seals verify, including H2_Q5 4/4, H2_Q5_FOLLOWUP 4/4 and
    H2_Q5_ADJUDICATION 4/4.
  - Earlier, for the H2-G2 record on chore/state-post-122 (main 83b099de plus that change; T0).
  - H2's own checks, read-only:
    - H2_PREP 15/15, H2_PREP_12A 10/10, H2_GUARD_VALIDATION 5/5, H2_V3_PREREG 4/4, H2_V3_RESULT 4/4,
      H2_G2_PREREG 4/4, H2_G2_RESULT 4/4;
    - H2_G2_CLOSURE_CHECK: all OK.
  - Earlier on this branch (2026-09-26), for the H2 v3-BLOCKED record: the same result.
  - H2's own checks, read-only:
    - H2_PREP 15/15, H2_PREP_12A 10/10, H2_GUARD_VALIDATION 5/5, H2_V3_PREREG 4/4, H2_V3_RESULT 4/4;
    - H2_V3_CLOSURE_CHECK: all OK.
  - Earlier on this branch (2026-09-26), for the H2 12(a) record: the same result.
  - H2's own checks, read-only: H2_PREP_12A.sha256 10/10; H2_PREP.sha256 15/15; H2_SKILL_GATE_BRIEF.v3.sha256, v2
    and v1 1/1 each; H2_SECOND_REVIEW_CHECK ALL PASS.
  - Earlier on this branch (2026-09-26), for the H2 rulings record: the same result.
  - Earlier on this branch (2026-09-25), for the H2 brief and its v3 repair: the same result each time.
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
CODEX_PENDING=NONE (2026-10-05). Codex remains unavailable (owner): Claude implemented, tested and reviewed the
  companion directly (MODEL SUBSTITUTION); no paid fallback.
  Before it: NONE. Codex's quota is EXHAUSTED (owner, 2026-10-04): no Codex, no delegate.sh, no wait, no paid
  fallback. Claude implements directly (MODEL SUBSTITUTION).
  Before it: NONE. Codex RESUMED by the owner (2026-10-04) for safe local T0/T1/T2 only. Tasks 901 (lane B) and 902
  (lane A) are DONE, both VERIFY=PASS; Claude read both diffs and corrected four of 901's labels.
  Before it: NONE. CODEX_PAUSED_BY_OWNER (owner ruling, 2026-10-01) until explicitly resumed; still in force
  after the F1 release (the owner, 2026-10-01).
  - Codex is not invoked; every pending retry was cancelled.
  - The merge gate is a CLAUDE_ADVERSARIAL_REVIEW (not independent) plus deterministic mutation evidence.
  - Review 3: never ran. Its first attempt failed on the usage limit (03:42Z, no report), and the
    retry was cancelled by the owner's ruling.
  Before it: F1 review3, the FINAL independent security and adversarial review on this head (a merge gate).
  - Task: .work/task-f1-review3.md in the worktree.
  - Review 2: DONE (NEEDS_DECISION; repaired in 8f7923c).
  Before it: F1 review2, the MANDATORY independent post-repair security and adversarial review, a merge gate.
  - Task: scratchpad/lanes12/f1/.work/task-f1-review2.md; the report goes to .work/f1-review2/REVIEW.md.
  - BLOCKED on the Codex usage limit until about 2026-09-30 19:35Z. The gate stays OPEN, and no PASS is substituted.
  - MODEL SUBSTITUTION (2026-09-30): Codex was unavailable, so Claude implemented F1 merge readiness: the registry,
    the apply route, the workflows, the tests and the docs.
  The owner directed that Claude owns critical reasoning and implementation, and that Codex is kept for bounded
  mechanical or adversarial verification.
  - F1 (2026-09-30):
    - D1 tests: DONE.
    - D2 review and audit: DONE (10 findings, all repaired).
    - D3 test updates: FAILED on the Codex usage limit, with no change made.
    - The delta review: NOT_RUN (quota).
    - MODEL SUBSTITUTION: Claude did D3's work and the delta review. The quota resets 2026-10-01 02:35 +07. An
      optional Codex delta review of 0bc11ff may run after that; it is not required.
  - Identity prep (2026-09-30): the bounded read-only review of e7309c31 plus this record: DONE (base a20a46c9):
    (1)-(5) PROVEN; findings NONE.
  - Post-W26 (2026-09-30): the bounded read-only review of be4b9939 PROVED (1)-(6), NONE. The release preparation was
    a read-only Plan lane.
  - Post-132 (2026-09-29): Codex did bounded read-only reviews only:
    - the rebuilt 0011, 20fbd542: delta PROVEN, NONE;
    - the rebuilt 0012, 6ccf60eb, together with the one-file 0011 delta to 500e5b83: both PROVEN, NONE.
  - Earlier today:
    - N1 646206fe: M1, repaired in 0208978d;
    - N2 87c01876: NONE;
    - 3433d306: NONE;
    - bc92e873: NONE.
  - Claude subagents implemented under Claude-written specs, and a read-only Plan lane mapped the integration. The
    task files are in the session scratchpad (p1/), not in .work/.
  - Post-129 (2026-09-29): this record used no Codex. The read-only Phase-1 prep used two read-only Claude lanes, the
    owner-permitted maximum.
  - RESOLVER_P1 (2026-09-29) used Codex for code and test edits under Claude-written specs; Claude owned the design,
    the dependency proofs and every diff review. 517887fc: 3 delegations (2 implementation, the first BLOCKED on a
    .work/ wording conflict in its spec; 1 read-only review). c7cb70f8 and fb765188 (unaccepted): 3 (implementation,
    read-only review, repair). 35545f4d (the authorized repair): 2 (implementation; read-only review, no findings).
    Task files and logs are in session-scratchpad worktrees, not in .work/. This STATE-only record used no Codex.
  - The smoke, its adjudication and this record used no Codex.
  - The re-pin used no Codex: the sanctioned deterministic tool, adapted in 3 recorded places (LOOP_STATE).
  - The release identity, a new change, used 1 of its 4 delegations: task-830, DONE. Files: .work/task-830.md,
    result-830.json and codex-830.log.
  - The H2 hold (T2) used Codex for its code and test edits: all 4 of its 4 delegations, so the change's budget is
    spent. The finalization's own words were "Use Codex for code/test edits per doctrine".
    - task-826: BLOCKED at the source-integrity guard test (the first causal failure, preserved);
    - task-827: DONE, the one targeted repair (the guard declaration);
    - task-828: DONE, the detail wording;
    - task-829: DONE, the headline.
    - Files: .work/task-826.md to task-829.md, result-826.json to result-829.json, and codex-826.log to
      codex-829.log.
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
OWNER_BOUNDARY=Nothing is pending from the A4C batch (2026-10-05). Ahead, each the owner's:
  - Lane R's publication (a new T3, when ready);
  - Lane P's publication, after the UOR qualification episode closes or on the owner's explicit authorization;
  - DP-D's export, structure only, a future owner action;
  - the writer JWT renewal, by 2026-10-30.
  Before it: ONE BATCHED OWNER ACTION (2026-10-05), T3: publish feat/a4-card04-companion @ 93ab50de (PR,
  required CI, merge commit), then this STATE record last. Running either A4 artifact against production stays a
  future owner decision at the UOR episode.
  Before it: Nothing is pending from the batch.
  - UOR side: the owner carries docs/automation/UOR_HANDOFF.md §14 (and the final values in this record) into UOR's
    governed session. UOR pins ARTIFACT_SHA256 2007fa28... read-only.
  - Running the A4 audit against production is a future owner decision at the qualification episode.
  Standing items: the writer JWT renewal by 2026-10-30 (WRITER_CUTOVER.md step 5); the H2 hold, UX-1 HELD, B5, D3, F3
  KEEP_UNSPENT; the Phase 7 rulings (P7-1 thresholds, custody, Q1/UX-1).
  Before it: ONE BATCHED OWNER ACTION (2026-10-04), T3: publish three local branches. That means push, PRs, CI and
  exact-head merges for:
  - chore/state-phase4-infeasible (cd4563c, plus this commit);
  - feat/t1-test-wallclock (ebbabe6);
  - docs/p8-tooling-inventory (953fe26).
  Auto refused `gh pr create` ([Data Exfiltration]). So the owner either switches this session to Manual, and Claude
  pushes, opens the PRs, reads CI and merges on each approval, or runs the steps. The Phase 4 verdict stands: no
  decision is pending.
  Standing items: the writer JWT renewal by 2026-10-30 (WRITER_CUTOVER.md step 5); the H2 hold, UX-1 HELD, B5, D3, F3
  KEEP_UNSPENT; the Phase 7 rulings (P7-1 thresholds, custody, Q1/UX-1).
  Before it: The Phase 4 verdict (2026-10-04; .work/roadmap/phase4/PHASE4_VERDICT_FINAL.md): INFEASIBLE under
  the rulings of 2026-10-04. No Phase 4 decision is pending.
  - Only the owner could change the verdict, and it would take both an F3 spend (ruling 3) and a scheduled-refit
    estimand (Option B). Neither is recommended.
  - Serving C1 as a labelled reference range (OD5) would be a new product decision.
  - Phase 7's remaining work waits on owner rulings: the P7-1 thresholds, the custody ruling, and Q1 with UX-1.
  Standing items: the writer JWT renewal by 2026-10-30; the H2 hold, UX-1 HELD, B5, D3, F3 KEEP_UNSPENT,
  CODEX_PAUSED_BY_OWNER.
  Before it: Phase 4's decisions (2026-10-04; .work/roadmap/phase4/PHASE4_VERDICT.md), all ruled by the
  owner on 2026-10-04 (OP-1 + OP-2 authorized and run; F3's derivation authorized and done; Option C; δ 0.03):
  1. D4 execution of OP-2 (the DEV hit-sequence H), with OP-1 (the C1 constants) optionally in the same
     session, preferably from a truncated DEV extract;
  2. F3's exact scope (a statement or an authorized derivation; plan §6.5);
  3. the staleness option: (a) train through the consumed folds, (b) a scheduled-refit estimand, or
     (c) an age cap;
  4. δ.
  Standing items: the writer JWT renewal by 2026-10-30; the H2 hold, UX-1 HELD, B5, D3, F3 KEEP_UNSPENT,
  CODEX_PAUSED_BY_OWNER.
  Before it: None immediate (2026-10-04). Phase 4's next owner boundaries:
  - D4 execution (any real-data refit or measurement);
  - the protocol freeze.
  Standing items: the writer JWT renewal by 2026-10-30; the H2 hold, UX-1 HELD, B5's DEGRADED half, D3, D4
  execution, F3 KEEP_UNSPENT, CODEX_PAUSED_BY_OWNER.
  Before it: The E2 consolidation (2026-10-04; the owner's Space secret steps): SUPABASE_DB_URL takes the
  narrow URL, then delete UCPE_SPACE_DB_URL and SUPABASE_SERVICE_ROLE_KEY. Standing items: the writer JWT
  renewal by 2026-10-30; the H2 hold, B5's DEGRADED half, D3, D4.
  Before it: The E2 cutover (2026-10-04, docs/runbooks/SPACE_DB_CUTOVER.md, steps 1-5):
  - the template and the helper's generate;
  - the login SQL;
  - the Space secret UCPE_SPACE_DB_URL.
  Standing items: the writer JWT renewal by 2026-10-30; the H2 hold, B5's DEGRADED half, D3, D4.
  Before it: The E2 release's T4 deploy (2026-10-04). Claude prepares all of it first: the identity PR
  merged, the guard HEALTHY, the preflight passed. Then the E2 cutover (docs/runbooks/SPACE_DB_CUTOVER.md):
  the login SQL and the Space secret UCPE_SPACE_DB_URL. Standing items: the writer JWT renewal by
  2026-10-30; the H2 hold, B5's DEGRADED half, D3, D4.
  Before it: Phase 3's remaining items are the owner's (2026-10-04):
  - E2 (DEFERRED: to un-defer or keep deferred);
  - design C1's hygiene step (delete SUPABASE_SERVICE_ROLE_KEY from the Space, T3 configuration);
  - the writer JWT renewal by 2026-10-30.
  Standing items: the H2 hold, B5's DEGRADED half, D3, D4.
  Before it: The read-only inventory with expect=after (2026-10-04): dispatch core-write-inventory.yml at this
  PR's merge commit (with the main guard) and approve it in production-db-owner. Then the optional hygiene of
  deleting SUPABASE_SERVICE_ROLE_KEY from the Space. Standing items: the H2 hold, B5's DEGRADED half, D3, D4, E2.
  Before it: A NEW T4, not a rerun (2026-10-04): dispatch apply-migration-0018.yml at this PR's merge commit
  (with the main guard), then approve it in production-db-owner. Run 37170407623 is consumed and never rerun.
  Before it: The one-shot T4 apply of migration 0018 (2026-10-03): dispatch apply-migration-0018.yml at
  this PR's merge commit (with the main guard), then approve it in production-db-owner. Standing items: the
  expect=after inventory (after the apply), the H2 hold, B5's DEGRADED half, D3, D4, E2.
  Before it: None now (2026-10-03). Next: the owner's T4 apply of 0018 (its one-shot route, approved in
  production-db-owner), once Claude's freeze package is merged. Standing items: the H2 hold, B5's DEGRADED half, D3,
  D4, E2.
  Before it: None now (2026-10-03): C4 is SET. The next owner steps come with D6, after E3's natural proof: authorize
  #212's merge, approve its run (expect=before) in production-db-owner; then 0018's freeze and its T4.
  Standing items: E3's natural proof (passive), the H2 hold, B5's DEGRADED half, D3, D4, E2.
  Before it: C4's Environment steps (2026-10-03; docs/runbooks/OWNER_URL_ENVIRONMENT.md): create production-db-owner
  (required reviewer: the owner; main only), add its SUPABASE_DB_URL secret, then delete the repository secret.
  The R1A deploy T4 is consumed. Standing items: E3's natural proof (passive), D6 (B: E3 proven + a clean production
  inventory), the H2 hold, B5's DEGRADED half, D3, D4, E2.
  Before it: None until G1's proof (2026-10-03). C4-PIN and D6 are ruled (verbatim in the header). Then, batched:
  - one Run action that merges this record's PR (G1 completed, C4 with C4-PIN), only after the G1 natural-run PASS;
  - later: C4's Environment steps (docs/runbooks/OWNER_URL_ENVIRONMENT.md); D6's freeze after the next release;
  - open: WB3's pinned crossing (one strict read method in persistence/repository.py) and the S8 option (1
    recommended).
  Before it: Two owner steps (2026-10-03), batched:
  - one Run action: merge #203 (this record) and #204 (G1), each on its exact head after its checks, then fast-forward
    the main checkout. Auto mode refused Claude's merge;
  - G1's secret steps (docs/runbooks/RESOLVER_CUTOVER.md): the login SQL in the SQL Editor (the T4: the role gets its
    login, holding only a SCRAM secret), then the GitHub secret UCPE_RESOLVER_DB_URL.
  Before it: None open now (2026-10-03). The switch is done ("SWITCHED"); its live proof is passive.
  - Owner reminders: renew SUPABASE_WRITER_JWT by 2026-10-30, before the 2026-11-02 expiry; keep
    SUPABASE_SERVICE_ROLE_KEY until D6.
  - Standing items: the H2 hold, B5's DEGRADED half, D3 (NO FOR NOW), D4 (HOLD), WB3 (with S8), E2 (deferred).
  Before it: E3's credential switch (2026-10-03): the owner's secret steps (docs/runbooks/WRITER_CUTOVER.md), by one
  owner card. E3-A YES and E3-B 30 days are ruled (verbatim in the header).
  Before it: E3's credential switch (2026-10-03):
  - E3-A: approve the plan;
  - E3-B: the token's lifetime, 30 days (recommended) or 90;
  - then the owner's secret steps (docs/runbooks/WRITER_CUTOVER.md).
  The WA deploy T4 is consumed (the owner's Run action, 10:49:56Z).
  Standing items: the H2 hold, B5's DEGRADED half, D3 (NO FOR NOW), D4 (HOLD), WB3 (with S8), E2 (deferred).
  Before it: None open now (2026-10-03). Both T4 applies are consumed (runs 37110330500 and 37110375659). The next
  boundary is the release T4, after the §2.6 package; later, E3's credential plan (after its executable proof).
  Before it: Two T4 applies (2026-10-03), in one Run action, in order:
  1. apply-migration-0016.yml (expected_sha = main at this record's merge; confirm APPLY-MIGRATION-0016-ONCE);
  2. only if 1 succeeded, apply-migration-0017.yml (the same expected_sha; confirm APPLY-MIGRATION-0017-ONCE).
  - Each is one-shot and never rerun. A refusal changes nothing, and its uploaded report names why.
  - Answered (2026-10-03, verbatim in the header): E1 YES W2; E2 DEFER; E3 YES in principle, after the proof; E4 YES,
    only repository.py + settings.py; WB1 YES after 0016; WB3 YES later, with S8.
  - Still open, for later batches: E3's credential plan (after its executable proof); E2 (deferred); WB3 (with S8);
    and the standing items: the H2 hold, B5's DEGRADED half, D3 (NO FOR NOW), D4 (HOLD).
  Before it: Phase 3 decisions (2026-10-03), batched:
  - E1: promote the rehearsed draft to migration 0016, W2 or INVOKER;
  - E2: the role behind the Space's DB_URL, OWNER or OTHER (never its value);
  - E3: the credential plan;
  - E4: the §2.6 crossing of repository.py and settings.py;
  - WB1: W-A, now rehearsed (promote draft 0017 to migration 0017, plus §2.6);
  - WB3: R-1 with S8;
  - and the standing items: the H2 hold, B5's DEGRADED half, D3, D4.
  - The RCPT T4 deploy is consumed (the owner's Run action, 2026-10-03T04:47:03Z).
  Before it: Reached once the release package passes preflight (2026-10-03). Batched:
  1. the T4 deploy of UCPE-PROD-RCPT-20261003-A: one Run action (a fresh preflight, then the deploy);
  2. E1-E4: the privilege design, now rehearsed (E1: promote the draft to migration 0016, W2 or INVOKER);
  3. WB1-WB3: the wider bundle (W-A as the end state, migration 0017 plus §2.6; R-1 with S8);
  4. the standing items: the H2 hold, B5's DEGRADED half, D3 (NO FOR NOW), D4 (HOLD).
  Before it: Not reached yet (2026-10-03). Expected, batched:
  - E1-E4 (the privilege design);
  - the receipts release (a T4);
  - the wider bundle's migration and §2.6 decisions;
  - the standing items: the H2 hold, B5's DEGRADED half, D3 (NO FOR NOW), D4 (HOLD).
  Before it: B9 is complete (2026-10-02). Both T4s are consumed: the 0015 apply (run 37033014490) and the deploy (D
  f046140b), each the owner's one Run action after Auto refused it.
  - Open for the owner, batched: the Phase 3 items above; the H2 items (the hold stays live); B5's DEGRADED half;
    D3 (NO FOR NOW); D4 (HOLD).
  Before it: The B9 release deploy (T4-2), when its frozen package is ready.
  - Auto stays the default. If the classifier blocks the exact frozen deploy, the owner gets one Run action.
  - Ruled 2026-10-02: RD-1 = R1 (verbatim excerpt in the header).
  - T4-1 (the 0015 apply) is consumed: the owner's Run action, run 37033014490.
  Before it: One owner decision (2026-10-02): RD-1 (B9_REST_DECISION.md).
  - R2a (recommended):
    - the owner runs the catalog-only privilege check (OD-DB-1 = D permits it, owner-run only);
    - D2 is re-issued for the Postgres variant;
    - after B9's release, the owner deletes SUPABASE_SERVICE_ROLE_KEY from the Space.
  - R1: §2.6 for the REST variant, plus migration 0015's T4 and a release T4.
  - The owner's instruction (2026-10-02), verbatim excerpt: "Do NOT ask the owner to run a normal analysis for
    M1 yet; that would be verification traffic and must not masquerade as USER_REQUESTED. Resolve M1 first by
    read-only Space configuration inspection using the existing local HF authentication. … If M1=REST, do not
    implement Postgres B9. Return the minimum REST-specific design/routing decision needed."
  Before it: One owner action (2026-10-02): run one analysis in the app (M1). Nothing else is asked.
  (WITHDRAWN by the owner.)
  - The owner's guidance on D1-D4 (2026-10-02), verbatim:
    "D1: first resolve M1 yourself read-only. Use existing local Hugging Face authentication only if already
    available; fetch bounded Space run logs and extract only the latest `persistence_receipt.repository` class.
    Never print/token-inspect credentials. If auth is unavailable or Auto blocks the read, stop with one minimal
    owner log-read action. Do not ask the owner to browse HF unless necessary.
    D2: owner approves the proposed minimum §2.6 B9 crossing ONLY IF D1 proves production uses
    `SupabasePersistenceRepository` (Postgres). Exact scope: `persistence/repository.py` gains
    `save_prediction_bundle` with one transaction and content-based identical-vs-conflict detection;
    `_persist_work_confirmed` consumes it; regenerate the exact evaluator pin and write the §2.6 record; red tests
    untouched. PERS-0 must make C1b and C3 PASS before publication/release. If D1=REST, do not implement this
    Postgres variant; return the REST-specific design.
    D3: NO FOR NOW. Keep UX-1 held. Do not regenerate F1/UOR handoff examples or analysis-hash goldens merely for
    the wording change.
    D4: HOLD. Before any real-data run, prepare a no-execution classification note proving the exact public
    source, dates, retrieval path and dataset are outside F3, §5A, protected/sealed spans and any consumed
    evidence lane. F3 stays KEEP_UNSPENT. If this cannot be proven from governing contracts, stop at the
    classification boundary.
    Before calling B9/Phase 3 complete, verify §23 against PERS-0 S8/circuit-open behavior. B9 may close C1b/C3
    only; do not silently defer a required acceptance criterion merely because durable reconciliation would need
    another table."
  Before it: Roadmap (2026-10-02). The SEC-1 deploy is consumed and is never rerun.
  - One batched question: may a change to the analysis payload regenerate the committed F1 radar_evidence.v1
    examples and the analysis_hash goldens? Schema and semantics are unchanged; only the example digests change.
    UX-1 needs this, and so will any payload change, such as a DecisionView.
  - Still open: M1; the H2 items (the hold stays live); B5's DEGRADED half deferred; a rollback is the owner's T4.
  Never authorized to Claude: UOR work, credential rotation or revocation, F3/§5A or protected access, H2
  execution, paid resources, any order capability, the OD-DB-1 data-row precheck.
  Before it: One Run action (2026-10-02): the SEC-1 deploy.
  - A single chained command: a fresh preflight of D 51a15fd0 with the reviewed delta digest, then `release.py
    deploy` (consumed once; never rerun).
  - Rule: AUTO is the default. A T4 that Auto blocks becomes one Run action; the owner is never asked to stay in
    Manual.
  - Still open: M1 (owner-run); the H2 items (the hold stays live); B5's DEGRADED half deferred; a rollback is the
    owner's T4.
  Never authorized to Claude: UOR work, credential rotation or revocation, F3/§5A or protected access, H2
  execution, paid resources, any order capability, the OD-DB-1 data-row precheck.
  Before it: Roadmap (2026-10-02). Both T4s are consumed and must never be rerun: the 0014 dispatch, run
  36952902214; the OBS-1 deploy, .work/release/CONSUMED_deploy_46a1de68….
  Still open:
  - M1 (owner-run): the writer transport, from the signed-in /v1/system_status.
  - H2: the items stay open, and the hold stays live.
  - B5's DEGRADED half stays deferred.
  - A rollback to D2 is an owner T4 (the command is in .work/release_obs1/rollback_check_post).
  Never authorized to Claude: UOR work, credential rotation or revocation, F3/§5A or protected access, H2
  execution, paid resources, any order capability, the OD-DB-1 data-row precheck.
  Before it: AT OWNER T4 (2026-10-01). Two frozen T4s, refused by the auto-mode classifier before execution:
  1. T4-0014: the one-shot production apply of migration 0014.
     - Dispatch apply-migration-0014.yml on main: expected_sha = main HEAD; confirm APPLY-MIGRATION-0014-ONCE.
     - Never rerun.
  2. T4-OBS1-DEPLOY:
     - a fresh preflight of D, then `scripts/release.py deploy D --authorize D --release-id
       UCPE-PROD-OBS1-20261001-A`;
     - never rerun;
     - then settle, the rollback-check, the re-pin (c82822e0) and the guard.
  Unblock: the owner switches this session to Manual permissions and resumes, or runs the commands themselves.
  Before it: Roadmap (2026-10-01). The OD-FINAL rulings (OD_FINAL), OD-DB-1 = D and the H2 rulings apply.
  1. Migration 0014's one-shot production apply and the OBS-1 release (T4s) are under the owner's standing
     authorization, conditional on: the exact package frozen on main; all deterministic and real-PG gates passing;
     H2 preserved. Any SHA mismatch or gate failure is a STOP, with no blind rerun.
  2. M1 (owner-run): the writer transport from the signed-in /v1/system_status.
  3. H2: the items stay open, and the hold stays live. B5's DEGRADED half stays deferred.
  Never authorized to Claude: UOR work, credential rotation or revocation, F3/§5A or protected access, H2
  execution, paid resources, any order capability, the OD-DB-1 data-row precheck.
  Before it: Roadmap (2026-10-01). The OD-FINAL rulings (OD_FINAL), OD-DB-1 = D and the H2 rulings apply.
  1. M1 (owner-run): the writer transport from the signed-in /v1/system_status.
     See .work/roadmap/writer_transport/MEASUREMENT_CONTRACT.md.
  2. Optional: the catalog-only DB precheck, .work/roadmap/db_precheck/01_catalog.sql, run in the Supabase SQL
     editor. The structural part stays unrun (OD-DB-1 = D).
  3. H2: the items stay open (the cutoff (e), §13.3, waiting versus architecture, the open points (b), (d) and
     (f)), and the hold stays live.
  4. B5 is deferred by the owner while the UOR handoff is active.
  5. Every push, merge and the next release stay owner T3/T4. The next release would carry B3's Dockerfile.
  Never authorized to Claude: UOR work, credential rotation or revocation, F3/§5A or protected access, H2
  execution, paid resources, a deploy, any order capability.
  Before it: Roadmap (2026-10-01). The OD-FINAL rulings (OD_FINAL) and the H2 rulings apply.
  1. B3: its acceptance proof runs in CI on its PR. Pushing B3 is a T3 for the owner.
  2. M1 (owner-run): the writer transport from the signed-in /v1/system_status.
     See .work/roadmap/writer_transport/MEASUREMENT_CONTRACT.md.
  3. H2: the items stay open (the cutoff (e), §13.3, waiting versus architecture, the open points (b), (d) and
     (f)), and the hold stays live.
  4. B5 is deferred by the owner while the UOR handoff is active.
  Never authorized to Claude: UOR work, credential rotation or revocation, F3/§5A or protected access, H2
  execution, paid resources, a deploy, any order capability.
  Before it: The UOR-side handoff and activation, in UOR's own governed sessions. UCPE never writes to UOR.
  - The owner hands docs/automation/UOR_HANDOFF.md (the governed package) to UOR. The token goes by NAME into
    UOR's secret store only.
  - Owner decisions in UOR's sessions: UOR's contract fixtures, its release allowlist (ACCEPTED_UPSTREAM_RELEASES),
    its registries and transport, and any UOR Cron re-enable.
  Not authorized to Claude: any UOR mutation, re-enabling UOR Cron, exposing the token, F3/§5A, any order
  capability. Codex stays paused (CODEX_PAUSED_BY_OWNER).
  Before it: The F1 credential issuance: a T4 and the owner's secret entry.
  - The procedure: CREDENTIAL_ROTATION.md, "Issue a credential"; ACTIVATION_CHAIN.md step 1, with its read-only
    pre- and post-check SQL.
  - The value never enters a chat, a file in the repository or a log.
  - Then the canary: one live request from the owner's own terminal (canary_f1.py), under its own authorization.
  - Then UOR: its own sessions build the registry and the transport. UCPE never writes to UOR.
  - Done by the owner: the enable (T3, 2026-10-01). G6 stays at the defaults (6 per 5 minutes, 120 per day).
  Not authorized to Claude: issuing a credential, running the canary with a token, mutating UOR or Cron, allowing
  UOR calls, F3/§5A, any order capability. Codex stays paused (CODEX_PAUSED_BY_OWNER).
  Before it: The F1 activation chain (docs/automation/F1_RELEASE_PLAN.md steps 4-8). Every step is the owner's:
  1. T4, a secret entry: issue the credential (CREDENTIAL_ROTATION.md, "Issue a credential"). The value never
     enters a chat, a file in the repository or a log; only its digest goes into the registry.
  2. G6 (T3, optional): the quota stays 6 per 5 minutes and 120 per day unless the owner lowers it.
  3. T3: set UCPE_AUTOMATION_ENABLED=1 on the Space (a restart), then the read-only post-enable check.
  4. The canary: one live request from the owner's machine, under its own authorization.
  5. UOR: its own sessions build the registry and the transport. UCPE never writes to UOR.
  Not authorized to Claude: issuing a credential, enabling the route, mutating UOR or Cron, allowing UOR
  calls, F3/§5A, any order capability. Codex stays paused (CODEX_PAUSED_BY_OWNER).
  Before it: The owner's standing authorization (2026-10-01) carries the deterministic T3/T4 continuation once
  each step's exact SHA, scope and preconditions are frozen:
  - the merge of PR #144 (exact head);
  - the 0013 one-shot apply (expected_sha = M);
  - the release identity, the deploy and the re-pin.
  STOP on any mismatch or failure, any secret entry, spend or product choice, protected evidence or F3, or
  any genuinely new risk.
  Never authorized: enabling automation, issuing credentials, mutating UOR or Cron, or allowing UOR calls
  before the governed activation chain proves them. The credential issuance (owner secret entry) is the
  standing boundary after the re-pin.
  Before it: The 0013 PRODUCTION APPLY (T4) after the merge: the owner authorizes the one dispatch, with
  expected_sha = M.
  - Authorized 2026-10-01 (standing): mark PR #144 ready and merge it with an exact-head merge commit, only if
    every gate passes.
  - Not authorized: the 0013 apply, a deploy, the enable, credentials, UOR mutation or Cron, F3/§5A, any order
    capability.
  Before it (2026-09-30): Do not merge, release or enable F1 (the owner).
  - Authorized and done: publishing PR #144 (draft) and using its CI.
  - Next owner boundary, after the Codex gate passes: the T3 merge of PR #144.
  - Then, in the order of docs/automation/F1_RELEASE_PLAN.md:
    - the 0013 apply (T4);
    - a release (T4) and the re-pin (T3);
    - credential issuance (T4);
    - the enable (T3);
    - the canary.
  - G2 is ACCEPTED as the local contract candidate. G6 is provisional (6/5min, 120/day).
  Before it (F1 local): NO ACTION IS AUTHORIZED. F1 is local and complete for its safe scope. Owner decisions (none
  taken):
  - G2: accept or modify the interface;
  - T3: publish feat/f1-governed-automation;
  - G6: the quota level;
  - T3: confirm SUPABASE_DB_URL on the Space;
  - build the 0013 apply route, then its T4 apply;
  - T4: the release, then the T3 re-pin;
  - credential issuance, the enable T3 and a controlled canary.
  Before it: W26_RELEASE_CLOSED; SAFE_MILESTONE_REACHED_FOR_AD_HOC_INTEGRATION. The next work needs a new owner
  instruction.
  Consumed on 2026-09-30:
  - the one-row DB read (pack §6): run once by the owner; PASS → PASS_PROVEN;
  - the publication and merge of this STATE record, under the standing authorization;
  - the real CONTROLLED_SMOKE (T4): run once by the owner, PASS_HTTP. It is never run again;
  - the standing authorization of the TC-v1 release chain: identity #141, the deploy T4 of D (PASS), re-pin #142, two
    guard dispatches, and the smoke-tools seal;
  - the owner's merge of #140 (86c9496f) and closure of #139 (unmerged);
  - the local-only release identity prep: e7309c31 plus its STATE record, then NOT_PUBLISHED (since merged as #141 → D);
  - the owner's merge of #138 (W26): main d790e0ff. It is not deployed;
  - the STATE repair direction: this record, superseding #139;
  - the owner's merges of #136 (RC1) and #137 (the STATE record): main e09dee01;
  - the W26 T3: reconciled to 79d43d38 with no semantic or pin drift, pushed with no force, PR #138 open (not
    merged), and this record pushed;
  - the T3 for RC1 (f1924495) and the STATE record (db8f229a): pushed with no force, and PRs #136 and #137 opened.
    Not merged;
  - the §2.6 authorization for W26: executed locally (be4b9939) and recorded here;
  - the release-preparation direction (read-only).
  Consumed since the post-132 record (853f1eb2):
  - the one-shot T3: 853f1eb2, 500e5b83 and 6ccf60eb pushed with no force, then merged by the owner (PRs #133,
    #134, #135; main b11a8e53);
  - the one-shot T4 APPLY-MIGRATION-0011-ONCE: run 36583531813, PASS. 0011 is live; never rerun it.
  - the one-shot T4 APPLY-MIGRATION-0012-ONCE: run 36586262979, PASS. 0012 is live; never rerun it.
  - the continuation direction: RC1 implemented locally (f1924495) and W26 prepared as patches, with nothing
    applied.
  Consumed since the post-129 record (7f59be5a):
  - T3-S129 (pushed 7f59be5a) and its merge by the owner (PR #130);
  - the one-shot T3 for N1 and N2 (pushed 0208978d and 87c01876) and their merges by the owner (PRs #131, #132);
  - the local-only authoring and rehearsal authorization for 0011, then 0012 (candidates 3433d306 and bc92e873,
    since superseded);
  - the post-132 continuous-mode direction: rebuild on fresh main (500e5b83, 6ccf60eb), the read-only integration
    map, bounded Codex reviews, no push.
  Consumed since the 9de97e0d record (post-129):
  - the RESOLVER_P1 publication T3 (branch pushed by Claude; PR #129 opened and merged by the owner; main 6fb3e8b4);
  - the direction for this local post-129 STATE-only record and the read-only Phase-1 prep.
  Consumed since the 2026-09-27 record (RESOLVER_P1):
  - the T3 for chore/state-post-127 (PR #128, main 6f5038d0);
  - the local P1-A authorization (517887fc);
  - the local P1-RESOLVER-ELIGIBILITY-B-REPAIR authorization (35545f4d), which also kept fb765188 only as an
    unaccepted candidate. c7cb70f8 and fb765188 consumed no authorization: they were local unaccepted execution
    without prior explicit owner authorization;
  - the direction for the 9de97e0d STATE-only record.
  Consumed in the 2026-09-27 record (LOOP_STATE):
  - the re-pin T3 (#127, merged);
  - the canonical guard dispatch (run 36310977790, HEALTHY);
  - the smoke execution (PASS_PROVEN) and its adjudication.
  Consumed in the record before (LOOP_STATE):
  - the release-identity T3 (#126, merged);
  - the first fresh T4 (FAILED_AUTH / NO_MUTATION);
  - dry-run 1 (not authenticated) and dry-run 2 (authenticated);
  - the deploy T4 (DEPLOYED 080f20a9);
  - the re-pin with the smoke contract.
  Consumed before them: the hold's T3 (#125, merged) and the release-identity preparation; the stopped T4 was not
  consumed. Earlier still: the Q5-adjudication STATE T3 (#124), the T2 hold authorization, the hold wording
  finalization and the headline polish (LOOP_STATE). Consumed before those: the H1 STATE T3 (#122), the H1 step (c)
  authorization, the H2 paper, bounded-repair, rulings, 12(a), guard-validation, v3 budget and H2-G2
  authorizations, the H2-G2 STATE T3 (#123), the Q5 read, the Q5 follow-up, and the Q5 adjudication ruling
  (LOOP_STATE). What remains, in order:
  1. OWNER DECISIONS, T3s AND T4s, in this order. Claude's `gh pr create` is refused by the auto-mode classifier, so
     the owner opens and merges each PR.
     STATUS after the 0011 T4:
     - a and b are CONSUMED (#133, #134, #135);
     - c is moot, because both routes are merged and each dispatch rehearses on a real PostgreSQL;
     - d's 0011 half is CONSUMED (PASS);
     - the 0012 half of d is CONSUMED too (PASS, run 36586262979);
     - Status 2026-09-30:
       - f, the resolver: RC1 is MERGED (#136 → 200e6ad6). It takes effect at the next scheduled resolver run, with no
         deploy.
       - e, the writer: W26 is MERGED (#138 → d790e0ff; its §2.6 execution was be4b9939). It is not deployed; main's
         guarded delta is [analysis_service.py]. Next:
         - DONE: the merge of #138. It did not deploy;
         - the release identity commit: PREPARED LOCALLY (e7309c31, T2 config/, with this STATE record). Its T3
           (push, PR, merge) is NOT_PUBLISHED;
         - then the deploy T4 of the exact merged SHA D (push to hf, once, never --force);
         - then the settle checks, the re-pin P, whose T3 is followed by one guard dispatch proving HEALTHY;
         - then a NEW sealed smoke, run once (T4), and the owner-authorized DB read of the smoke row.
         Pre-authorizing a conditional rollback T4 to 080f20a9 is an owner decision.
       - g, the methodology: RULED on 2026-09-30. Stamped USER_REQUESTED CROSS_PROVIDER outcomes enter normal
         evidence; no legacy reclassification; no H2 lift.
       - Tier note: CLAUDE.md lists "push to hf = deploy" under T3 but "release" under T4. The precedent runbook
         treats the deploy as T4, and this loop treats it as T4. Reconciling the doc is the owner's choice.
     a. T3: push chore/state-post-132 (this record, STATE.md only), then its PR.
     b. T3: push feat/migration-0011-provenance (500e5b83), then its PR and merge. Then the same for
        feat/migration-0012-resolution-status (6ccf60eb), which is stacked on it. Merging makes each dispatch-only
        workflow dispatchable, so each merge is also its enablement T3.
     c. Optional: a pull_request-triggered, no-secret rehearsal workflow for 0011 and 0012, like 0010's, so that the
        SQL runs on a real PostgreSQL before merge. It is excluded under the "dispatch-only" ruling.
     d. T4, one-shot each, never rerun:
        - dispatch apply-migration-0011 at the merged main SHA with APPLY-MIGRATION-0011-ONCE, then verify;
        - then apply-migration-0012 with APPLY-MIGRATION-0012-ONCE, then verify.
     e. The writer (TC-D), after 0011 is live. Decide the route:
        - Route B, recommended: a §2.6 change to the pinned `_insert_prediction` that names the four stamp columns
          only for stamped rows, with write_pin and a STATE record in the same PR;
        - or an unpinned extraction.
        Then:
        - a guarded analysis_service.py change that stamps after `_prediction_row`, with an injected clock;
        - a new release identity and CURRENT_DELTA_PATHS;
        - a deploy T4;
        - a smoke; proving storage needs one owner-authorized DB read;
        - the guard re-pin T3.
     f. The resolver (Route C, no pinned file), after 0011 and 0012 are live:
        - a new unpinned module with its own Postgres queries: the due scan widened to stamped CROSS_PROVIDER tc-v1
          rows, status reads, and one batched upsert per run under rq-v1;
        - a preflight with a visible fallback;
        - a new RESOLVER_VERSION;
        - any new reason key reviewed against 0012's pattern.
        It needs no deploy.
     g. Methodology acceptance:
        - resolved CROSS_PROVIDER outcomes enter the evidence base;
        - legacy stuck rows can be quarantined.
        Both change the evidence permanently. Unstamped legacy CROSS_PROVIDER rows stay unresolvable.
     The previous item 1 (the T3 for chore/state-post-129) is CONSUMED (PR #130).
     CONSUMED (post-129): the RESOLVER_P1 T3 (PR #129, main 6fb3e8b4). It published the candidate as merged history
     without squashing; c7cb70f8 and fb765188 remain unaccepted on main.
     Carried from the consumed chore/state-post-127 item (PR #128):
     - The deployed hold's verification is COMPLETE: the re-pin is merged, the guard is HEALTHY and the smoke returned
       PASS_PROVEN.
     - Rollback stays available only as a new T4: force-with-lease back to 00705c55, then a PR reverting the re-pin.
       (That was the rollback of the H2-hold deploy itself. For any later deploy the H2-preserving target is
       080f20a9; 00705c55 is retired: see the post-W26 record.)
     - Recorded for the owner: RELEASE_GATE's HF-secrets table documents REST persistence, but production runs the
       direct Postgres repository (the smoke proved that the skill-evidence refresh runs). Reconciling the table is a
       separate, docs-only decision.
  2. CURRENT LANE, H2 — **Q5 adjudication UNAVAILABLE. H2-G2 keeps its modeled PASS; its operating density is not
     confirmed.** It was ruled on 2026-09-26: Q1–Q8, point 12(a), the error budget, the H2-G2 selection, and the Q5
     rulings (LOOP_STATE).
     - The Q5 read is CONSUMED: provenance PASS (R2 corrected); density not yet validated; floor unmet everywhere
       (H2_Q5_ADJUDICATION.md).
     - The owner's next decisions:
       - the cutoff at (e), which fixes the envelope §13.3 validates;
       - whether and when to run §13.3, a no-database simulation at the recorded densities;
       - whether to wait for usage, or to reconsider the architecture (a new ruling);
       - the open points (b), (d) and (f). The hold itself is verified live (item c).
     - H2-G2 (α 0.001, g 0.07) passed all 36 binding scenarios (H2_G2_D3_PREREG.md, H2_G2_RESULT.md).
     - The v3 candidate (α 0.001, g 0.09) **FAILED** in S01 and stays on record, unreplaced (H2_D3_PREREG.v3.md,
       H2_V3_RESULT.md).
     - Sealed:
       - H2_PREP ea4bc8de… (v1);
       - H2_PREP_12A c795c177… (v2);
       - H2_GUARD_VALIDATION 745075ad… (v2's guard rejected);
       - H2_V3_PREREG cfcf773b… and H2_V3_RESULT 01839fd1… (v3, FAILED);
       - H2_G2_PREREG 06af15c7… and H2_G2_RESULT 070b6276… (H2-G2, PASSED pending Q5);
       - H2_Q5 dbc9987d…, H2_Q5_FOLLOWUP 37b87c28… and H2_Q5_ADJUDICATION d3e3dd01… (Q5: UNAVAILABLE).
     - The next owner boundaries each need their own authorization:
     0. CONSUMED 2026-09-26: after the v3 FAIL the owner selected (A) as a new generation, H2-G2 (g 0.07), which PASSED.
        The parameter search is closed.
     a. CONSUMED 2026-09-26: the count-only density read (Q1–Q3 and Q5; Q4 excluded), the follow-up, and the
        adjudication (UNAVAILABLE). The text below is kept as history. The read had been specified thus: the owner runs
        the five sealed statements of H2_COUNT_QUERY_PLAN.v2.md §3, each once, in the Supabase SQL editor, and returns
        the raw output (suggested wording in its §5). No write.
        - It returns no performance figures and no outcome-direction counts, so it cannot inform the frozen guard.
        - It yields the density envelope, the validation densities and the call mix.
     b. Confirm or change the open points (H2_G2_D3_PREREG.md §15). Each has a frozen default:
        - (b) no hardening beyond α_look 0.001, g 0.07 and the budget's reserve;
        - (d) the D3 replacement texts, now including DRIFT_GUARD and DENSITY_ENVELOPE (a Change-A wording change);
        - (e) the cutoff: (M) 2026-07-13T04:20:01Z (the default) or (I) 2026-08-19T08:31:57Z;
        - (f) NEW: the directional-call floor rule. The default is m ≥ 100 informative calls, and windows count
          only if they hold an informative call.
        - (a) is RULED (the drift guard). (c) is SETTLED: the call is sign(p_up − p_down), with exact ties NO_CALL.
     c. VERIFIED LIVE 2026-09-27: the CONTROLLED_SMOKE returned PASS_PROVEN, the re-pin is merged (#127) and the guard
        is HEALTHY (run 36310977790). The hold stays until the corrected D3 gate is implemented and validated (Q8). The
        text below is kept as history.
        DEPLOYED 2026-09-26T19:47:36Z (production 080f20a9 / UCPE-PROD-H2-HOLD-20260927-A). What remained then was
        item 1: the re-pin's publication and the CONTROLLED_SMOKE.
        MERGED 2026-09-26 (PR #125, main fa5c0da7); NOT DEPLOYED. Its T4 stopped before any mutation, and the
        release identity was prepared (LOOP_STATE). What remained then was item 1, a to e.
        IMPLEMENTED LOCALLY 2026-09-26: feat/h2-failclosed-hold, e669e06f + ebfe2073 + 4ea42593 (LOOP_STATE), with
        three recorded deviations from the design, each following the owner's words. What remains:
        - the T3 (item 1) and the merge;
        - then a separate deploy authorization (a push to hf is a deploy).
        Until it is deployed, the live gate behaves as today (Q8 NOT LIVE). The text below is kept as history.
        The T2 fail-closed hold (Q8), per H2_FAILCLOSED_T2_DESIGN.md (unchanged): implementation on a branch,
        ./verify.sh in a worktree and Claude's review of the diff; then a T3; then a separate deploy authorization.
        Until it is deployed, the live gate behaves as today.
     d. Optional: an independent review of the v2 records. Their fixes are checked mechanically only.
     e. Later, after the read: the §13 validation at the Q5 densities; the D3 implementation (T2); π_T's
        computation (from the archive through its load mask, or under a fetch authorization); then the owner's
        authorization to replace the hold, and a deploy.
     For reference, the brief's findings and questions (Q1–Q8 are now ruled; LOOP_STATE). Brief:
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
     Questions for the owner's ruling (RULED 2026-09-26; see LOOP_STATE):
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
NEXT_ACTION=Claude: Lane R and Lane P locally under DP-A to DP-F (tests, mutation, full gates, fresh reviews),
  then DP-D's local restore tooling and the owner export card. Return at the next genuine owner boundary with
  one batched action. The owner: carry UOR_HANDOFF §14 and §15 to UOR when ready.
  Before it: The owner: the T3 batch above. Claude after it: exact-head and file-set checks, CI reads (including
  the companion's rehearsal on PostgreSQL 17.6), the merge commit, then this record refreshed onto the resulting
  main with the merge and run ids, published last. The owner: carry UOR_HANDOFF §14 and §15 to UOR when ready.
  Before it: Claude: the remaining dependency-safe local lanes (each new pull request is a new owner T3 batch);
  passive reads only. The owner: carry the A4 handoff fields to UOR when ready.
  Before it: The owner: the batched T3 action above. Claude after it: CI reads, the exact-head merges, LAST_GREEN_SHA;
  then passive reads only (the receipt watch; the Phase 7 baseline once natural traffic exists) and the JWT renewal
  reminder (2026-10-30).
  Before it: The owner: read the Phase 4 verdict (INFEASIBLE) and choose what comes next (the Phase 7 rulings above,
  or another milestone). Claude meanwhile: passive reads only (the first natural receipt since the service-role
  key's deletion; the Phase 7 baseline once natural traffic exists) and the JWT renewal reminder (2026-10-30). No
  Codex, no GPT, no traffic.
  Before it: The owner: rule on the Phase 4 decisions. Claude, after an authorization: run OP-2 (and OP-1)
  write-once, with an audit hook; set H_c and L; finalize FEASIBLE or INFEASIBLE; then the protocol freeze
  package.
  Before it: Claude: Phase 4 (P4-1, P4-2), with no real-data refit:
  - C1's new identity: the spec, an unwired serving module and a fitting tool tested on synthetic data;
  - the D4 no-execution classification note;
  - the target-matched incumbent bridge;
  - the protocol draft with DEV-synthetic feasibility.
  Phase 7 (P7-1): passive measurement and design only. Return at a methodology, product, T3/T4,
  protected-evidence or secret boundary, or with the FEASIBLE/INFEASIBLE verdict.
  Before it: Claude: detect the consolidation passively (secret names plus the restarted Space's event; accept
  only SUPABASE_DB_URL, ucpe_space_db, DESIGNED), then the final Phase 3 exit re-audit and its record. Then
  Phase 4, with Phase 7's independent work alongside.
  Before it: The owner: the cutover steps, then say "switched". Claude: read the restarted Space's
  evidence_reader_identity event passively (accept only UCPE_SPACE_DB_URL, ucpe_space_db, DESIGNED), then
  hand over the consolidation (SUPABASE_DB_URL takes the narrow URL; delete UCPE_SPACE_DB_URL and
  SUPABASE_SERVICE_ROLE_KEY). Then the final exit re-audit.
  Before it: Claude: merge this record's PR after green CI. Then the E2 release chain (the identity PR,
  the guard on D, the preflight) and the owner's deploy card. After the deploy: settle, read the first
  evidence_reader_identity event (today's SUPABASE_DB_URL role), re-pin, the guard on R.
  Before it: The owner: rule on the Phase 3 items above. Claude: watch passively for the first post-D6 natural SAVED
  receipt (no traffic). If E2 is un-deferred: its own governed sequence (design C2), then an X3 re-audit.
  Before it: The owner: the expect=after inventory. Then Claude: adjudicate its raw report (verdict PASS, no
  surface), seal it, and record Phase 3's D6 as complete.
  Before it: The owner: the new T4 (docs/runbooks/MIGRATION_0018_APPLY.md). Then Claude: adjudicate the raw
  report, record 0018's applied_run (registry PR), and hand over the expect=after inventory.
  Before it: The owner: the T4 apply of 0018 (docs/runbooks/MIGRATION_0018_APPLY.md). Then Claude: adjudicate the
  raw apply report, record 0018's applied_run (registry PR), and hand over the expect=after inventory.
  Before it: Claude: freeze 0018 (migration, rollback, one-shot route, rehearsal and mutation gates), verify,
  PR, merge on its exact green head, then return with the exact T4 apply command. No production action meanwhile.
  Before it: Claude: read E3's first natural USER_REQUESTED SAVED receipt passively (no dispatch, no traffic); keep this
  route's DRAFT PR (#212) green; other safe Phase 3 prep. The owner: nothing until E3 is proven.
  Before it: The owner: C4's Environment steps. Claude, read passively with no dispatch: E3's first natural USER_REQUESTED
  SAVED receipt (and any persistence_reconciled event). Then D6's freeze package once E3 is proven: the production
  inventory route (read-only, in production-db-owner), the inventory with --expect before, then 0018's one-shot route.
  Before it: Claude, read passively, with no dispatch:
  - G1: the next natural scheduled resolver run on current main must show "resolver credential:
    UCPE_RESOLVER_DB_URL", "resolver_identity role=ucpe_resolver" and SUCCESS. Then mark this PR ready, for the owner's
    merge;
  - E3: the first natural USER_REQUESTED SAVED receipt.
  Before it: The owner: the Run action (merge #203 and #204), then G1's secret steps. Then Claude:
  - confirm G1 from the next hourly resolver run's log: "resolver credential: UCPE_RESOLVER_DB_URL" and
    "resolver_identity role=ucpe_resolver", with the run succeeding. Then a small PR removes the fallback;
  - confirm the first natural USER_REQUESTED persistence_receipt passively (bounded log reads only). SAVED makes the
    writer LIVE_PROVEN as ucpe_api_writer;
  Before it: Claude, in this order:
  - confirm the first natural USER_REQUESTED persistence_receipt passively (bounded log reads only). SAVED makes the
    writer LIVE_PROVEN as ucpe_api_writer;
  - meanwhile, the resolver cutover (G1), prepared only: no credential, no database write, no workflow switch;
  - never create verification traffic; never ask for, read or print a key or token.
  Before it: The owner: the credential switch (docs/runbooks/WRITER_CUTOVER.md; the owner card). E3-A and E3-B are ruled.
  - Then Claude: confirm passively that the next natural persistence_receipt is SAVED as ucpe_api_writer.
  - Every 30 days: the owner mints a new token (the runbook's step 5) and replaces SUPABASE_WRITER_JWT.
  - Throughout: never create verification traffic; never ask for, read or print a key or token.
  Before it: The owner: E3-A and E3-B, then the credential switch (docs/runbooks/WRITER_CUTOVER.md).
  - Then Claude: confirm passively that the next natural persistence_receipt is SAVED as ucpe_api_writer.
  - Later: D6, which removes the service-role key and narrows service_role's grants by a migration (a T4).
  - Throughout: never create verification traffic.
  Before it: Claude: the release package UCPE-PROD-WA-20261003-A, up to its T4.
  - It goes through the B4 chain from the main that carries this record.
  - Then the owner gets one Run action (a fresh preflight, then the deploy), with E3's credential plan to decide.
  - After the deploy: settle, rollback-check, the re-pin PR, the guard on R, and a STATE record.
  - Claude creates no credential value. Never create verification traffic.
  Before it: Claude, in this order:
  1. the §2.6 package (E4 plus the W-A client): the two headers, save_forecast_bundle and its routing, PERS-0 widened to
     the whole bundle, the evaluator pin regenerated, and the §2.6 record;
  2. E3's executable proof: ES256 + kid through a real PostgREST, with scratch keys only;
  3. the release package, up to its T4.
  - Claude creates no credential value. Throughout: never create verification traffic.
  Before it: The owner: the one Run action (0016, then 0017).
  - Then Claude:
    1. adjudicate both apply reports (raw first);
    2. the registry PR recording both applied runs;
    3. the §2.6 package (E4 + the W-A client): the two headers, save_forecast_bundle and its routing, PERS-0 widened to
       the whole bundle, the evaluator pin regenerated, and the §2.6 record;
    4. E3's executable proof: ES256 + kid through a real PostgREST, with scratch keys only;
    5. then the release package, up to its T4.
  - Claude creates no credential value. The writer JWT and the publishable key are the owner's, after the release.
  - Throughout: never create verification traffic.
  Before it: The owner: E1-E4, WB1 and WB3.
  - Then Claude, as answered: the migration-0016 route, that is the rehearsed draft promoted into
    migrations/0016, its one-shot apply route, rehearsal and registry entry, and its T4 apply card. Then W-A, if
    WB1 = yes, and the §2.6 package, if E4 = yes.
  - Throughout: observe passively the first natural persistence_receipt with the receipt fields; never create
    verification traffic.
  Before it: Claude: the release package UCPE-PROD-RCPT-20261003-A from the main that carries this record.
  - The identity PR is the next merge (D). Then push CI and B3, the guard on D, the rollback findings over D, the
    re-pin precomputed twice, and preflight review and accept.
  - Stop at the owner: one Run action (a fresh preflight, then the deploy) and the batched decisions.
  - After the owner's deploy: settle, rollback-check, the re-pin PR, the guard on R, and a STATE record.
  - If the owner defers the release instead, the package goes stale harmlessly. The next release supersedes its
    identity.
  - Throughout: watch passively for natural persistence_receipt events; never create verification traffic.
  Before it: Claude, in this order:
  1. P3-PRIV-R: rehearse design C1-C3 (W2) on scratch PostgreSQL with Supabase-like roles and an authenticator.
     - Prove each role can do exactly its list and is refused everything else, including through PostgREST-style
       role switching; and that anon and authenticated stay denied.
     - Run production's own F1 registry and ledger code, and the calibration query, under ucpe_space_db
       (Correction 01).
     - The draft SQL stays outside migrations/. Its PR is evidence for E1; it is not applied.
  2. The wider §8.1 bundle design (T0, sealed): run identity and the detail payload in the bundle, and the
     reconciliation of COMMIT_UNKNOWN.
  3. A STATE record, then the batched owner boundary.
  - Throughout: watch passively for natural persistence_receipt events; never create verification traffic.
  Before it: The owner: choose the next Phase 3 item (three-state receipts; the privilege and role design; the wider
  bundle; S8 recovery) or another roadmap lane.
  - Claude: watch, passively, for the first natural persistence_receipt after the release, without creating traffic.
  Before it: Claude: the B9 release (T4-2) through the B4 chain from the main that carries this registry record
  (check 5c requires it).
  - Release id UCPE-PROD-B9-<date>-A; rollback binding to the current production bc90e69b.
  - The deploy is a T4: one Run action if Auto refuses it.
  - After it: settle, rollback-check, the re-pin PR, the guard, and a STATE record.
  - The first natural USER_REQUESTED analysis after the release will log a persistence_receipt from
    SupabaseRestRepository. No verification traffic is created.
  Before it: The owner: RD-1. Then Claude:
  - R2a, after D2 is re-issued:
    - B9 per B9_DESIGN.md §A, with the pin and the §2.6 record;
    - its PR's PERS-0 rerun must show C1b and C3 PASS, and C1a, C2 and C4 still PASS;
    - then the release (T4, returned).
    - The owner's catalog check and the secret removal gate the switch, not the implementation.
  - R1: the RPC variant under its own §2.6, with the 0015 apply (T4) and a release (T4).
  - D4 stays HOLD, D3 stays NO, and UX-1 stays HOLD.
  Before it: The owner: one analysis in the app (M1). Then Claude continues automatically, by reading the logs:
  - M1 = SupabasePersistenceRepository:
    - B9 per D2's exact scope (B9_DESIGN.md §A), with the pin regenerated and the §2.6 record;
    - its PR's PERS-0 rerun must show C1b and C3 PASS, and C1a, C2 and C4 still PASS, before publication;
    - then a release (T4), returned to the owner as a live-release boundary.
  - M1 = SupabaseRestRepository: implement nothing; return the REST design (B9_DESIGN.md §B) for a ruling.
  - D4 stays HOLD (the run needs the owner's authorization). D3 stays NO.
  Before it: The owner: D1-D4. Then Claude:
  - after D1 (M1 = Postgres) and D2: implement B9 exactly as authorized, with the pin regenerated and PERS-0 rerun
    (C1b and C3 must flip to PASS); a release (T4);
  - after D3: UX-1, with the F1 examples and the analysis_hash goldens regenerated;
  - after D4: FEAS-1 on real DEV-admissible data.
  Before it: Claude: PERS-0, the plan §22 item 7 persistence crash/idempotency rehearsal of the current PG writer
  on scratch PostgreSQL in CI, against the §23 Persistence criteria. It measures and fixes nothing: B9 needs
  M1 and a §2.6 crossing. UX-1 waits on Q1.
  Before it: Claude:
  1. REL-1 (release tooling):
     - a changed frontend/app.js or styles.css must ship a new cache token, checked in preflight;
     - the asset-token test becomes conditional on a pending frontend delta.
  2. Then the next decision-free lane.
  - UX-1 waits on the owner's F1-artifact ruling.
  Before it: The owner runs the SEC-1 deploy (one Run action). Then Claude, automatically:
  1. settle D with the F1 probe; the full rollback-check of 46a1de68 against production D;
  2. publish the re-pin, which must equal 258b969c; the guard on it;
  3. rebase UX-1 onto it, set its guarded delta, verify, PR, merge; it then joins the next release train;
  4. merge this record, extended with the results.
  - FEAS-1 follow-ups need authorization: real DEV-admissible H for hit sequences and score differences (§22 item 5
    and item 8 with real data).
  Before it: The owner's next roadmap instruction. This envelope (OBS-1, DBI-1, the 0014 route and apply, the OBS-1
  release) is complete.
  - Claude, read-only, when next active: confirm that the resolver's next scheduled runs show error_save_* = 0 on
    the 0014-applied database, and that the scheduled guard stays HEALTHY at pin D.
  - On any regression: STOP and report. A rollback to D2 is the owner's T4.
  Before it: The owner, then Claude. Main stays at D 46a1de68 until step 3.
  1. T4-0014 (the owner, or Manual mode): dispatch once.
     - Claude downloads the report artifact and adjudicates the raw pre- and post-checks.
  2. T4-OBS1-DEPLOY (the owner, or Manual mode): a fresh preflight, then deploy once. Then Claude:
     - settles with the probe;
     - runs the full rollback-check of D2 against production D;
     - publishes the re-pin, which must equal c82822e0;
     - verifies the guard on it.
  3. Then this record merges, extended with both results: the registry's 0014 applied_run, and the unapplied-list
     test.
  On any SHA mismatch or refusal: STOP, with no rerun.
  Before it: Claude:
  1. The dedicated one-shot apply route for migration 0014, built from the merged bytes: the digest pin; a
     rehearsal with refusal of the second apply; security, RLS, trigger and schema fingerprints; refusal
     evidence; no bulk route.
  2. Then the single production apply (owner standing authorization, conditional).
  3. Then the OBS-1 release package (B4 tooling, the B3 gate).
  Before it: Claude: the next dependency-safe lanes from fresh main 52965cc2 (governing plan Phases 2-3; OD7 allows
  at most two proven-independent lanes). Each stops at its T3.
  - Observability (plan §10): bounded, sanitized structured events and the persistence receipt. The files are
    unpinned, and the guarded ones ride the deploy train.
  - The §8.2 DB-invariant groundwork: writer-compliance evidence, with constraints NOT VALID.
  Before it: Claude: B3 (reproducible build) on fresh main.
  - The hashed lock, the base-image digest, deterministic timestamps, and a two-runner build proof.
  - It stops at its T3: the push that runs the proof.
  Before it: OWNER: the UOR-side handoff (OWNER_BOUNDARY). Claude stops here.
  - The package: docs/automation/UOR_HANDOFF.md at main, and the local bundle .work/f1_release/uor_handoff_package/
    (every pinned file's exact bytes at main, with a manifest).
  - The credential stays ACTIVE. To stop at any time: revoke it (no restart), or clear UCPE_AUTOMATION_ENABLED.
  Before it: OWNER: issue the credential (OWNER_BOUNDARY), then run the canary. Claude stops here.
  - To stop the route at any time: revoke the credential (no restart), or clear UCPE_AUTOMATION_ENABLED (a
    restart).
  - Read-only re-checks Claude may run on request: post_enable_check_f1.sh and readonly_extra_checks_f1.sh.
  Before it: OWNER: the activation chain (OWNER_BOUNDARY), which starts with the credential issuance. Claude stops here.
  - The kit (local; nothing runs until the owner runs it): .work/f1_release/activation/ACTIVATION_CHAIN.md,
    the read-only post-enable check (post_enable_check_f1.sh), and the owner-run canary (canary_f1.py, with
    the token typed at a hidden prompt).
  - Any later guard dispatch: expect HEALTHY, delta [], pin = live = D2.
  Before it: Merge this identity PR with exact-head checks (D2).
  - Then one guard dispatch on D2: HEALTHY, delta [analysis_service, app, build_info], pin = live = 2096af6d.
  - Then the deploy precheck (.work/f1_release/deploy/) and one fast-forward push of D2 to hf/main.
  - Then the settle checks: RUNNING at D2; health; build-info F1; the static digests unchanged; the
    automation route answering 503 AUTOMATION_DISABLED.
  - Then the re-pin PR, merged, and one guard dispatch: HEALTHY, delta [].
  - STOP at the credential issuance.
  Before it: Verify this head, run the 0013 real-PG rehearsal and CI, then freeze it. Then Claude adversarial review
  round 2.
  - If clean: update the PR body, mark it ready, merge with --match-head-commit, and record M.
  - Then rebuild and reverify the 0013 package against M, precheck, and apply under the standing
    authorization.
  - Then the release identity, the deploy and the re-pin.
  - Stop at the credential issuance (owner).
  Before it: Run review 3 on this head: `./delegate.sh .work/task-f1-review3.md workspace-write xhigh`.
  - If clean, and every gate passes:
    - update the PR body, mark it ready, and merge with --match-head-commit;
    - record M;
    - rebuild and reverify the 0013 apply package against M;
    - prepare the T4 contract (.work/f1_release/ in the main checkout);
    - stop at the apply boundary.
  - If it finds a HIGH or MEDIUM: one consolidated repair, verify, CI, then the review again.
  Before it: After the Codex quota resets (about 19:35Z), run the mandatory review in the worktree:
  `./delegate.sh .work/task-f1-review2.md workspace-write xhigh`
  - If it finds a HIGH or MEDIUM: one consolidated repair, then ./verify.sh, a push without force, and CI.
  - If clean: record it, and report F1 MERGE_READY to the owner, whose T3 merge comes next.
  - If Codex stays unavailable: the gate stays OPEN, and the owner is told so.
  Before it (F1 local): WAIT for the owner's F1 decisions (OWNER_BOUNDARY): G2 on docs/automation/RADAR_EVIDENCE_V1.md and
  F1_NODE_CLASSIFICATION.md, and the T3 to publish feat/f1-governed-automation. Nothing F1 enables anything in
  production.
  Before it: WAIT for the owner (W26_RELEASE_CLOSED; SAFE_MILESTONE_REACHED_FOR_AD_HOC_INTEGRATION).
  - Nothing is pending in the W26 chain. The smoke and its DB read are consumed and never rerun.
  - DONE before it: the one-row DB read → PASS_PROVEN, adjudicated with
    `adjudicate_w26_stamp_smoke.py .work/w26_smoke/run_20260930T124617Z --db-read .work/w26_release/W26_DB_READ.csv`.
  DONE before it: the owner ran, once, `bash /Users/kha/Documents/Kha-app/UCPE/.work/w26_smoke/run_w26_stamp_smoke.sh`
  - They type the CONTROLLED_SMOKE code at the hidden prompt, and nothing else, then tell Claude.
  - Claude adjudicates the sealed run directory.
  - If PASS_HTTP, the owner runs DB_READ_FILLED.sql, from that run directory, in the Supabase SQL editor and saves the
    CSV. Claude adjudicates again with --db-read, and STATE records the result.
  Before it (identity prepared): WAIT for the owner. OWNER_BOUNDARY 1-2, in order:
  - item 1, remaining:
    - DONE:
      - the identity T3 (#141 → D 2096af6d);
      - the guard run on D (36714103648);
      - the deploy T4 of D (PASS) and the settle checks (PASS);
      - the re-pin T3 (#142 → 6becb100) and its guard run (36715108033, HEALTHY);
      - the smoke-tools seal.
      DONE later: the smoke T4 (PASS_HTTP) and the one-row DB read (PASS_PROVEN).
      Superseded plan text follows;
    - then a HEALTHY guard run on D (precondition 6: a scheduled run, or one authorized dispatch), the deploy T4 of
      the exact D (W26_RELEASE_PACK.md §3), the settle checks, the re-pin T3 and one guard run, the new smoke executor
      (to be sealed), the smoke T4 (once), and the one-row DB read. The commands are in .work/w26_release/deploy/
      RUNBOOK.md. #138 and #140 are merged, and #139 is closed;
    - the T4 APPLY-MIGRATION-0012-ONCE: CONSUMED, PASS (run 36586262979);
    - the writer route decision (§2.6, Route B recommended), now unblocked by 0011 being live, followed by its guarded
      change, deploy T4, smoke and re-pin;
    - the resolver (Route C), after 0012 is live;
    - the methodology acceptance in g;
    - this record's T3 (STATE.md only).
    Never dispatch apply-migration-0011 again: it is consumed, and the route refuses a second apply.
    Resolution stays idle meanwhile: under the exact-venue filters no normal row is due. No new USER_REQUESTED
    outcome accrues until the writer stamps reference_venue, which bears on H2's "waiting";
  - then H2's next decisions after the UNAVAILABLE adjudication: the cutoff (e), §13.3, waiting or architecture, and
    the open points. The hold stays in force meanwhile.
  Before any rollback or later deploy, re-read this record's LOOP_STATE (the deploy sequence, its checks and the
  rollback) and .work/816/l1/runbook.md §4-§6.
  Never run ./verify.sh in the main checkout: its secret scanner walks .work, sealed paths included. Verify only in a
  clean worktree. Read first:
  - the hold: git show e669e06f ebfe2073 4ea42593 (branch feat/h2-failclosed-hold) and .work/task-826.md to
    task-829.md with their results. Never re-run a consumed delegation;
  - .work/h2_skill_gate/H2_Q5_ADJUDICATION.md: the Q5 adjudication (UNAVAILABLE), and H2_Q5_RULING.md. Then
    H2_Q5_CHECK.md, the historical R2 stop, and H2_Q5_FOLLOWUP.md (6 | 5). Never query the database for H2 without
    the owner's authorization, and never re-run a consumed statement;
  - .work/h2_skill_gate/H2_G2_RESULT.md: the single H2-G2 acceptance run (36/36 PASS) and the budget accounting.
    Then H2_G2_RULING.md, H2_G2_ACCEPTANCE_PROTOCOL.md and H2_G2_D3_PREREG.md, the governing candidate, PASSED
    pending Q5. Never re-run H2_G2_ACCEPTANCE.py: its single run is consumed. No further parameter search;
  - .work/h2_skill_gate/H2_V3_RESULT.md: the single v3 acceptance run (FAIL in S01), the budget accounting and the
    owner's options. Then H2_RULING_V3.md, H2_V3_ACCEPTANCE_PROTOCOL.md and H2_D3_PREREG.v3.md, the failed candidate
    (on record, not governing), and H2_GUARD_VALIDATION.md, the rejection of v2's guard thresholds. Never re-run
    H2_V3_ACCEPTANCE.py for this candidate: its single run is consumed;
  - .work/h2_skill_gate/H2_RULING_12A.md: the 12(a) ruling, the second review's findings and their closure. Then
    the governing v2 records: H2_D3_PREREG.v2.md, H2_CUTOFF_DERIVATION.v2.md and H2_COUNT_QUERY_PLAN.v2.md (sealed
    by H2_PREP_12A.sha256). H2_FAILCLOSED_T2_DESIGN.md still governs the hold;
  - .work/h2_skill_gate/H2_RULINGS.md: the Q1–Q8 rulings, the first audit and its repair. It and the four v1
    documents are sealed by H2_PREP.sha256 and superseded where a v2 exists. Never edit a sealed file; make every
    change additively;
  - .work/h2_skill_gate/H2_SKILL_GATE_BRIEF.v3.md: the H2 brief (it governs; v2 and v1 are superseded, kept
    unchanged);
  - .work/research3/nextgen/ng1/NG1_CLOSURE.md: the closure, the preserved records and the governing wording;
  - pilot/STAGE1_AUDIT.attempt2.md and STAGE0_AUDIT.md (the governing Stage-1 and Stage-0 wording).
  The B lane's record is b_lane/B_LANE_CLOSURE_ADDENDUM.md.
  - H2: no database query except the five sealed statements of H2_COUNT_QUERY_PLAN.v2.md, each once, under the
    owner's authorization. No implementation of the hold or of D3 without its own authorization.
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
PRODUCTION=PROD-F1-AUTOMATION (D2 5a3ef022): the route ENABLED and serving one credential, uor-radar-2026-10
  (issued by the owner, ACTIVE; named by id only). F1_CANARY=PASS and LIVE_ISOLATION=PASS (2026-10-01).
  - Every other caller is refused: 401, and 403 for a human session cookie. G6: 6 per 5 minutes, 120 per day.
  - UOR's consumption waits for its own governed activation; UCPE has not touched UOR.
  Before the credential: PROD-F1-AUTOMATION (D2 5a3ef022), with the route ENABLED by the owner (restarted about 09:04Z on
  2026-10-01; RUNNING at D2).
  - No credential exists, so every call is refused: 401 CREDENTIAL_REQUIRED or CREDENTIAL_INVALID, and 403 for
    a human session cookie.
  - The post-enable check PASSED (ENABLE_CHECK 7/7, 09:05Z), and the extra read-only checks PASS 6/6 (09:16Z).
  - The Hugging Face edge answers CORS preflights and reflects origins (F1-ACT-1, LOW; RADAR_EVIDENCE_V1.md
    section 2). UCPE's own CORS policy is unchanged.
  Before the enable: PROD-F1-AUTOMATION, live since 2026-10-01T06:40Z (RUNNING at D2 at 06:40:54Z).
  - hf/main and the running commit are 5a3ef022 (D2), a fast-forward from 2096af6d. Build
    UCPE-PROD-F1-AUTOMATION-20261001-A; /healthcheck 200.
  - In it: F1, the governed automation route (#144), OFF (503 AUTOMATION_DISABLED); migration 0013 is applied;
    no credential exists. The human routes are unchanged (the non-regression suite).
  - Guard: HEALTHY on main 3ad53b87 after the re-pin merged (run 36828594390), delta [].
  - A rollback is a new owner T4. Its target is 2096af6d / UCPE-PROD-TC-V1-STAMP-20260930-A, never 00705c55
    or 080f20a9.
  Before it: PROD-TC-V1-STAMP (2096af6d, W26), pushed at 2026-09-30T12:24:01Z; guard HEALTHY after its re-pin
  (PR #142).
  Before it: PROD-H2-HOLD, live since 2026-09-26T19:47:36Z (RUNNING at 19:48:20Z).
  - hf/main and the running commit are 080f20a9, main's own commit (a fast-forward from 00705c55). Build
    UCPE-PROD-H2-HOLD-20260927-A; /healthcheck 200 (LOOP_STATE).
  - In it: the H2 fail-closed hold (#125), the release identity (#126), and the unwired v2 prep (#108, #109; nothing
    imports it).
  - Guard: HEALTHY on main 9a1db2dd after the re-pin merged (canonical dispatch, run 36310977790).
  - Functional: the CONTROLLED_SMOKE returned PASS_PROVEN (2026-09-27). The legacy 4H and 1H SKILL_DEMONSTRATED
    verdicts were held, and the runs are CONTROLLED_SMOKE, with no USER_REQUESTED contamination.
  - Production runs the direct Postgres repository: the skill-evidence refresh runs there.
  - Rollback is a new T4: git push --force-with-lease=refs/heads/main:080f20a9… hf 00705c55…:refs/heads/main.
    (That was the rollback of the H2-hold deploy. After any later deploy D, the target is 080f20a9:
    --force-with-lease=refs/heads/main:<D> hf 080f20a9…:refs/heads/main. 00705c55 lacks the H2 hold and is retired.)
  History: PROD-SAFE-3, live from 2026-09-17T03:39:17Z to 2026-09-26T19:47:36Z.
  - Re-read on 2026-09-26 UTC, after the T4 authorization of 17:44Z, public reads only:
    - hf/main 00705c55;
    - the Space API reports runtime.stage RUNNING and runtime.sha 00705c55;
    - /healthcheck 200;
    - /v1/build-info UCPE-PROD-SAFE-3-20260915-A.
  - The merged H2 hold (#125) and the prepared UCPE-PROD-H2-HOLD-20260927-A identity are NOT in production.
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
  - The H2 hold deploy: the single push at 2026-09-26T19:47:36Z (exit 0, 00705c55 → 080f20a9). Also consumed: the
    rejected push at 18:58:37Z (FAILED_AUTH / NO_MUTATION) and the dry-runs at 19:17:27Z and 19:36:37Z. A rollback or
    any later deploy needs a new T4.
  - The H2 hold CONTROLLED_SMOKE, run 2026-09-27T10:21:23Z (PASS_PROVEN). The executor refuses a second run
    (.work/h2_smoke/EXECUTED). Never delete or edit the run directory, the seals or the adjudication.
  - The canonical guard dispatch 36310977790.
  - W26:
    - the 0011 apply 36583531813 and the 0012 apply 36586262979;
    - the deploy of D 2096af6d, its single push at 2026-09-30T12:24:01Z;
    - the W26 CONTROLLED_SMOKE (PASS_HTTP) and its one-row DB proof (PASS_PROVEN).
  - F1:
    - the 0013 apply 36820986264 (APPLIED; the route refuses a second apply);
    - the deploy of D2, its single push at 2026-10-01T06:40Z (2096af6d → 5a3ef022), and its dry run at
      06:39:36Z;
    - the guard dispatches 36825556001 (D2) and 36828594390 (R);
    - the F1 canary, attempt_01 at 2026-10-01T10:25:15Z (HTTP_PASS, F1_CANARY=PASS). canary_f1.py refuses another
      attempt; never delete or edit its directory.
    A rollback or any later deploy needs a new T4.
  - B9 and RCPT (2026-10-02/03):
    - the 0015 apply 37033014490 (APPLIED; the route refuses a second apply);
    - the B9 deploy of D f046140b;
    - the RCPT deploy of D 17c9c053, its single push at 2026-10-03T04:47:03Z (f046140b → 17c9c053; the
      CONSUMED marker .work/release/CONSUMED_deploy_17c9c053d420…);
    - the guard dispatches 37062503316 (D) and 37098323783 (R).
    A rollback or any later deploy needs a new T4.
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
OD_FINAL=The owner's rulings on the governing plan's decision pack (§21), recorded verbatim (restated by the
  owner on 2026-10-01; previously ruled):
  - OD1: BTC/ETH + 1H setup + close-anchored ~6h terminal risk/range as next-gen primary design center only,
    existing timeframes retained.
  - OD2: YES.
  - OD3: YES with strict E2/E3/USER_REQUESTED separation, collector OFF, no F3/protected access.
  - OD4: Option B preferred only when an actual pinned diff requires the minimum named-file §2.6 crossing,
    extraction fallback if repeated crossings become too broad.
  - OD5: hide unaccepted challenger claim numbers in normal UI, descriptive/reference context allowed,
    authenticated debug may show EXPERIMENTAL.
  - OD6: DEFER pending measurements.
  - OD7: YES, max 2 proven-independent implementation lanes, shared/live surfaces serial.
  The H2 rulings and the live hold are preserved unchanged.
  OD-DB-1 (the owner, 2026-10-01): D. The structural/data-row DB precheck does not run yet. Only the catalog-only
  part may run, and only by the owner. No probability, label, return, §5A, F3 or protected material is read.
V2_STATUS=distributional-v2 is on main as an unwired module (#102). It is NOT frozen and NOT a methodology version.
  - Recipe: R2 arm CB, HAR log-variance plus a calendar profile, with empirical shape tables. BTC/USDT and
    ETH/USDT on 15m, 1H and 4H; TABLES_SHA256 f0689f29….
  - Evidence of record: docs/R2_FRONTIER_REPORT.md, docs/DISTRIBUTIONAL_V2_PREP.md and
    docs/R2_ZERO_DRIFT_GATE_AND_DISPLAY.md.
  - PRs #108 and #109 prepared everything that touches no evaluator-pinned file. It is still unwired.
  - Wiring needs §2.6 authorization.
  - Adopting the proper-score gate also needs per-row probabilities from persistence/repository.py, which is pinned.
  - Correction (lane C): with mu = 0, the up share is not 50/50. The shape tables fix it between 0.4794 and 0.5427.
RESOLVER_P1=Resolver exactness and eligibility. MERGED: PR #129, main 6fb3e8b4 (merged by the owner at
  2026-09-29T06:42:05Z; CI success). Its production effect begins with the first scheduled resolver run on 6fb3e8b4
  (NOT_YET_OBSERVED at the post-129 record). No deploy: the Space still runs 080f20a9, and only the resolver uses the
  due query. Merged history: main 6f5038d0 + 517887fc + c7cb70f8 + fb765188 + 35545f4d + 9de97e0d (merge 6fb3e8b4);
  feat/resolver-exactness-phase1a = 517887fc. Code files versus 6f5038d0 (5):
  scripts/resolve_outcomes.py, src/crypto_probability_engine/persistence/repository.py,
  ops/section_5a_evaluator_pin.json, tests/resolver/test_resolve_outcomes.py, tests/resolver/test_due_eligibility.py.
  - History (owner ruling, 2026-09-29; never re-grade it):
    - 517887fc (P1-A): owner-authorized local execution (resolver script and tests only, no pinned file). Its
      read-only closure audit returned LOCAL_MILESTONE_PASS.
    - c7cb70f8 and fb765188: LOCAL UNACCEPTED EXECUTION WITHOUT PRIOR EXPLICIT OWNER AUTHORIZATION. They are never
      to be marked authorized or PASS, retroactively or otherwise. Their commit messages call them "owner-authorized
      §2.6 change"; that label is wrong and must not be relied on.
    - The owner later authorized keeping fb765188 only as an unaccepted candidate, and prospectively authorized the
      repair that produced 35545f4d.
    - 35545f4d: the owner-authorized repair (P1-RESOLVER-ELIGIBILITY-B-REPAIR) and the only candidate for
      publication. Nothing on the branch is accepted before its T3.
    - Published by the T3 as merged history (6fb3e8b4) without squashing: c7cb70f8 and fb765188 remain unaccepted on
      main.
  - Owner authorizations, 2026-09-29, verbatim (session prefix omitted):
    - 517887fc: "Implement local-only `P1-RESOLVER-EXACTNESS-A` on `feat/resolver-exactness-phase1a`: only resolver
      script/tests; exact stored BINANCE_PUBLIC/OKX_PUBLIC only, ambiguous source=>0 provider calls/writes/resolved;
      same-venue bounded-history exact-target resolution; resolved only on save OK. No
      pinned/repo/migration/workflow/STATE/.work/DB/prod/F1/F2/F3; pinned need=>STOP. Synthetic tests +
      clean-worktree verify; local commit only; report SHA/diff/tests and F2 distinction."
    - 35545f4d: "On local `fb765188`, execute authorized `P1-RESOLVER-ELIGIBILITY-B-REPAIR`: add generic
      caller-supplied prediction-origin filtering before LIMIT in PG/REST/memory; scheduled resolver passes
      USER_REQUESTED plus existing exact-source/timeframe filters; set unpinned version
      `resolver-v2a-exact-eligibility`. Only repository.py, evaluator-pin manifest, resolver/tests; no
      STATE/prereg/DB/prod/workflow/F3/push. Preserve generic no-filter/OOS behavior; Codex read-only review, clean
      verify, local commit, report."
  - §2.6 RECORD. Pre-registration §2 item 6: a change to the evaluator after the first live readiness run resets the
    pin, requires explicit owner authorization that states what changed and why, and is recorded in STATE.md. Under
    §24 the evaluator is its import closure, which includes persistence/repository.py. The evaluator itself is
    consumed (SECTION_5A_RESULT) and is never rerun; its look-time pin stays reproducible from git history.
    - STATUS: CLOSED for publication (2026-09-29). The owner's T3 stated the final what and why, verbatim: "§2.6 what:
      pinned due-query gains explicit pre-LIMIT origin/source/timeframe eligibility and regenerated pin; why:
      non-resolvable rows must not starve resolvable rows. I accept the recorded carried risks."
    - What changed in the pinned closure (candidate 35545f4d versus main): persistence/repository.py only, and there
      only the due query: fetch_due_unresolved_predictions (protocol, in-memory, Postgres, REST),
      _execute_due_prediction_query, _fetch_due_prediction_rows and the helper _checked_due_filter. It gains
      keyword-only data_sources, timeframes and prediction_origins filters: exact match before ORDER BY and LIMIT;
      values validated before any query ([A-Za-z0-9_]+; origins must be supported; a bare string is refused); an
      empty filter returns [] with no query; None is unfiltered, with SQL and params byte-identical to main. Nothing
      else changed (AST-verified): OOS readers and writers, claim_section_5a_seal, writers, and the calibration and
      snapshot readers are untouched; no new module import; the pinned file list (69) is unchanged.
    - Why: under exact resolution, rows the resolver will not resolve (a data_source other than exactly
      BINANCE_PUBLIC or OKX_PUBLIC, including CROSS_PROVIDER, the label stored whenever both venues agree; any 1M
      row; any origin other than USER_REQUESTED) never get an outcome and never leave the oldest-first LIMIT due
      query, so about RESOLVER_LIMIT (50) of them would stop resolution for every row. CONTROLLED_SMOKE rows and
      SCHEDULED_SHADOW_EVIDENCE rows (the consumed §5A OOS population) are outside the resolver's population.
    - Pin closure_digest: main b9d94a7ddd085d93311a6899215ef1fcb4c32ffac98d0fd74fda632261cd8c00 (unchanged since
      4a0a908; the §5A look) -> candidate 35545f4d
      212ea63764663a4ed2830c0c12aa1035aab5ea05d572f55da1505e2d5a6014b8. The intermediate digests (95f42a10…,
      5740eea5…) belong to the unaccepted commits. Regenerated with evaluator_pin.write_pin();
      scripts/evaluate_section_5a.py was not run. Red tests, OOS freeze and runtime guard untouched.
    - No pre-registration addendum: §2 item 6 requires this STATE record, not an addendum, and no answer-bearing
      evaluator code changed. Precedent 4a0a908 wrote Addendum 10 because it changed consumption semantics.
  - Unpinned resolver in the candidate: one bounded request to the row's own venue (Binance startTime/endTime; OKX
    after, from candles or history-candles by target age), no cross-venue fallback; the terminal bar must close
    exactly at horizon_end_utc; 1M excluded; resolved only when the save returns "OK"; the due query asks for
    USER_REQUESTED, BINANCE_PUBLIC/OKX_PUBLIC and 15m/1D/1H/1W/4H; outcome rows carry resolver_version
    resolver-v2a-exact-eligibility (config/defaults.py keeps resolver-v1-wave4b2, untouched).
  - CODE PASS on 35545f4d (local): clean detached worktree VERIFY=PASS ruff ok | 2757 passed, 23 warnings |
    schemas+smoke ok | scanners 3/3 | 35545f4; Codex read-only review of the repair: no findings. This verifies the
    candidate's code only; it neither accepts nor authorizes the branch's history.
  - Carried risks, accepted by the owner in the publication T3: CROSS_PROVIDER USER_REQUESTED rows stay unresolved
    (recoverable later under an approved venue rule), so calibration and the held H2 gate would grow only from
    single-venue rows, pooling v1 with v2a outcomes; CONTROLLED_SMOKE and SCHEDULED_SHADOW_EVIDENCE rows would no
    longer be resolved (a future OOS collection must revisit the resolver's origin set; V1_QUANT_CONTRACT §5A.5
    describes the consumed frame); eligible rows whose terminal bar never appears are skipped every run (phase-B
    quarantine is the structural fix); a single-venue outage fails the hourly run until the venue returns; live
    Binance/OKX windowed-endpoint behaviour was not probed (every failure mode skips or fails; none writes).
  - Publication T3, CONSUMED (owner, 2026-09-29, verbatim): "I authorize one-shot T3 publication of
    `feat/resolver-eligibility-phase1b` only, candidate `9de97e0d8711f6c01c400af88ef5b526d628c34c`. First verify
    `origin/main` is still `6f5038d0491ff5fb64ae0759a5ad512daba16720`; mismatch => STOP. §2.6 what: pinned due-query
    gains explicit pre-LIMIT origin/source/timeframe eligibility and regenerated pin; why: non-resolvable rows must not
    starve resolvable rows. I accept the recorded carried risks. Push/PR/merge only; no workflow dispatch, DB action,
    HF deploy or F3 access." Executed: origin/main verified at 6f5038d0 (06:22:38Z); candidate tree 82ed6bad recorded;
    branch pushed at 9de97e0d; Claude's PR creation was refused by the auto-mode classifier; the owner opened PR #129
    and merged it (merge commit 6fb3e8b4, tree 82ed6bad). No deploy, migration, DB action or dispatch.
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
  - Releases run through scripts/release.py and docs/runbooks/RELEASE.md (since #151). A rollback goes only to a
    registered, H2-safe release (rollback-check; docs/runbooks/ROLLBACK.md), never to the pre-hold 00705c55.
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
- **In production (PROD-F1-AUTOMATION, since 2026-10-01; corrected here, it read PROD-H2-HOLD):** D2 5a3ef022.
  The H2 hold stays live. It also carries the W26 tc-v1 writer stamp and F1, the governed automation route
  (enabled, one credential; F1 is CLOSED and delegated to the UOR thread). The H2-HOLD content listed next is all
  still in it:
- **In PROD-H2-HOLD (from 2026-09-26, and in every release since):** the H2 fail-closed hold, its release identity
  and the unwired v2 prep, on top of PROD-SAFE-3's content:
  - Recent Analysis History and durable Detail;
  - session and auth hardening;
  - provider byte caps and deadlines;
  - strict candle adjacency;
  - the accumulated reviewed UI work.
- **Database:** migration 0010 is applied (2026-09-17), so the legacy tables' security is now codified in the
  migrations.
- **Deployed 2026-09-26 (PROD-H2-HOLD):** the unwired v2 prep (#108, #109), the H2 T2 fail-closed hold (Q8; PR #125)
  and the release identity UCPE-PROD-H2-HOLD-20260927-A (PR #126).
  - The hold is VERIFIED LIVE: the CONTROLLED_SMOKE returned PASS_PROVEN (2026-09-27).
  - The baseline re-pin is merged (PR #127), and the guard is HEALTHY.
- **Owner-gated, still open:** the v2 decisions (a) to (d); D-1 ruled (a) and (b) in principle, not implemented
  (OWNER_BOUNDARY, product decisions). The current next lane is H1 (OWNER_BOUNDARY 2).
  A v2 promotion needs its own freeze, T0, holdout and one look.
