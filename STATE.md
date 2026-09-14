# STATE

Updated: 2026-09-14 (T3 BATCH #92-#94 MERGED — §5A evaluator ON MAIN 5940557, tree 249e6499 as authorized; lane D (0009 hardening + apply route, K1=A K2=A) in progress; nothing deployed; one look NOT consumed)

## Recovery block — read this first on resume
```
LOOP_STATE=POST-T_close. T_close PASSED 2026-09-12T04:00:00Z. THE §5A ONE LOOK IS NOT CONSUMED:
  no live DB read, no readiness run, no evaluation, no holdout row inspected.
  T3 BATCH #92-#94 MERGED 2026-09-14. The owner authorized it; it ran with scripted raw capture
  (.work/811/t3-batch/, SHA-256 manifest). Three INDEPENDENT PRs, merged in order. Each had exact-head
  CI green, a --match-head-commit merge, parents verified as (previous main, lane head), a merged
  tree bit-identical to the local merge-tree, and exact-main CI green. It was armed to stop on the
  first mismatch, and none occurred. All six CI runs were Python 3.11 on Linux, all green.
    #92 feat/5a-evaluator-on-main          e199969 -> 99e5499
    #93 test/resolver-pipefail-regression  8ce93c4 -> 86a5ed1
    #94 fix/oos-workflow-input-transport   8d6e26e -> 5940557
  The final main tree 249e64995e10fc840409ddac2fcf8e97f047c13c EQUALS the owner-authorized tree:
  the gated local composition, identical in either order.
  hf/main = a89b45e, unchanged. Zero open PRs.
  One pre-flight abort, disclosed to the owner: the first lane A invocation passed a mistyped full
  expected SHA. The script refused at step 0, before any push; nothing reached origin. It was
  rerun with every SHA read from the verified manifest.
  Previous batch, for provenance. That checkpoint corrected a stale recovery block
  (origin/main = 200d822 recorded when main was d52e9ae):
  T3 BATCH #84-#90 MERGED 2026-09-13, owner-authorized, seven INDEPENDENT PRs, each with
  exact-head CI green, a --match-head-commit merge, parents verified (previous main, lane
  head), the merged tree proven bit-identical to a local composition, and exact-main CI green
  after every merge; the batch was armed to stop on the first mismatch and none occurred:
    #84 docs/post-one-look-dependency-map     9a7fe7b -> 7c24989
    #85 docs/r2-zero-drift-gate-and-display   aeb7133 -> 0fca908
    #86 docs/g1-g7-acceptance-matrix          f471695 -> 4c2aa4d
    #87 chore/delegate-fresh-result-identity  a6fa2de -> d11bee6
    #88 ops/stop-post-tclose-collector        7ffc6f2 -> 651c63e
    #89 fix/r202-provider-http-bounds         ce2dc44 -> 068900d
    #90 fix/a203-candle-boundaries            27e81e2 -> 68b4c8e
  The final main tree e1042da is BIT-IDENTICAL to the composition of the seven reviewed heads
  computed in a different merge order, so what shipped is exactly what was reviewed,
  independent of order. Test arithmetic reconciles: 1150 = 1132 + 5 + 4 + 5 + 4.
  Historical standby narrative from 2026-08-28 is retained below for provenance:
LOOP_STATE_PRIOR=IDLE — STANDBY. No lane open, no candidate open. The product board is CLEAR:
  the owner closed the last two open candidates (see OWNER_PRODUCT_DECISIONS) and put the loop
  on standby until a NEW genuine product issue arrives or the governed section 5A T_close
  boundary is reached. Fifteen product PRs are SHIPPED to main. PR #56 (in-process
  Recent Analysis History) merged 2026-08-27T05:32:03Z, PR #57 (durable history) merged
  2026-08-27T06:12:00Z. Batches 1-10 remain closed and the pre-T_close audit returned BOARD
  CLEAR. PROD-SAFE-2 remains the deployed build and NOTHING was deployed by either merge. The
  section 5A envelope is UNCHANGED and still frozen: the holdout, its evaluation, the candidate
  freeze, the collector, outcome and holdout inspection, T_close itself, and any change to what
  the collector computes or persists. Ordinary safe work outside that envelope continues under
  normal risk tiers, with owner authorization for T3/T4.
CURRENT_MILESTONE=§5A EVALUATION — collection CLOSED at T_close. The evaluator is ON MAIN (5940557,
  PR #92) and has NEVER RUN. The work in progress is lane D, owner rulings K1=A and K2=A:
  - harden migration 0009 with row-level security, REVOKE from PUBLIC/anon/authenticated/service_role,
    and public.-qualified names;
  - add a dedicated one-shot apply workflow. In ONE transaction it runs the read-only pre-checks
    (no stale table: F-0009-C), applies exactly 0009, and runs the post-checks; any failure rolls back.
  Design: .work/812/lane-d-design.md. Then come three separate T4s: apply 0009 once, readiness, consume.
  HISTORY (below): the evaluator lived on feat/5a-evaluator, local, and its implementation was once
  FROZEN at 2b31832 (branch ref cb6edf7 carries STATE-only commits above it; the src/ tree hash is
  identical).
  VERIFICATION HISTORY. task-805 run 1 returned NOT_VERIFIED with nine findings F1-F9; the
  owner ruled on F1, F2 and F9 and Opus repaired F3-F8. task-805 run 2 exhausted Codex quota
  before reporting but its probes established seven sibling findings G1-G7, the worst being G1:
  Postgres NUMERIC arrives as Decimal, the serializer handled only datetime, and the digest ran
  after the probability read and before the seal claim, so on real data the FIRST consumption
  would have read the holdout and crashed with no seal. After two repair rounds on the same
  causal class were each defeated by siblings, the owner accepted the escalation and INVERTED
  THE LOOP: the verifier authors failing tests first, against the frozen implementation.
  task-806 RED TEAM RETURNED 2026-09-13 (result verified fresh; production code untouched):
  17 properties RED, 4 REFUTED with evidence (G3.2, G3.3, G4.2, G5.1), plus four NEW sibling
  findings, all RED — G8 the runner accepts a process-local in-memory repository as a seal
  authority; G9 the Postgres seal claim uses plain json.dumps and raises on datetime, a SECOND
  independent route to reading the holdout without sealing it, even once G1 is fixed; G10
  recompute treats deleted feature_rows and origin_anomalies as empty/zero; G11 an empty
  population reports a measured-looking zero-second span. Evidence at .work/806/.
  REPAIR LANDED 2026-09-13 at 0bbcdd5, against the task-806 red tests pinned by SHA-256 efe36649...
  in their own commit 80a95f6 BEFORE the repair and never edited. 20 of 21 pass. G3.4 stays RED:
  it is UNSATISFIABLE under its own double — its probability read waits on a two-party Barrier with
  a 5 s timeout, so the lone reader G3.1 requires raises BrokenBarrierError. Proven empirically
  before the repair; left for the owner and Codex to amend, neither edited nor gamed.
  THE DESIGN CHANGED: the one look is now CLAIMED, durably and atomically, BEFORE any probability
  is exposed, and on Postgres the read itself captures raw evidence into the claimed seal inside
  one transaction before returning. One lossless canonical serializer backs every digest and seal
  column. Migration 0009 enforces the lifecycle in the database. Addendum 3 of the pre-registration
  records it.
  RECOMPOSED onto main 5f36126 as branch feat/5a-evaluator-on-main; STATE.md was the only file
  changed on both sides and the only conflict.
  CURRENT IMPLEMENTATION: fd8239a on feat/5a-evaluator-on-main. It carries the owner rulings D1-D4
  and every task-807 structural repair, on top of the red-test amendment c44e416. This branch is
  LOCAL and NOT PUSHED; task-808 returned NOT_VERIFIED against it (see CODEX_VERIFICATION_808).
  Product work outside §5A continues in parallel; it never touches the envelope.
CURRENT_BRANCH=feat/5a-0009-hardening-apply-route (LOCAL, NOT PUSHED), branched from main 5940557.
  Its first commit is this post-batch STATE checkpoint. The lanes A, B and C are MERGED (#92-#94).
  main = origin/main = 5940557.
LAST_GREEN_SHA=5940557 (main). Exact-main CI passed on Python 3.11/Linux, run 34824354602. The local
  gate was 1739 on the identical tree (composition b58d334).
LAST_VERIFY_BATCH=Exact-head CI green on e199969, 8ce93c4 and 8d6e26e. Exact-main CI green on 99e5499,
  86a5ed1 and 5940557. Links are in .work/811/t3-batch/raw/*/ci_*_url.txt.
LAST_VERIFY=PASS ruff ok | 1739 passed | schemas+smoke ok | scanners 3/3 · composition 02d5844 ·
  2026-09-14 (local, and Codex task-811 before and after its mutants).
  CI portability: CI runs the suite on Python 3.11 on Linux, but every local gate ran 3.13.14 on macOS.
  - ruff reports no 3.12-only syntax; a probe proves ruff 0.16.3 would flag it.
  - The 45 changed Python files use no stdlib API newer than 3.11.
  - The full composition suite passed 1739 with builtins.sum replaced by 3.11's naive float
    summation; 2379 of 36594 calls really differed.
  - The libm-dependent t-CDF is asserted only within tolerances, and recompute binds evidence and
    rule digests, never float results.
  - The first real 3.11/Linux run is the PR's exact-head CI.
  End-to-end on a toolcache-shaped CPython 3.13.14, using the workflow's own step text:
  - install removed the floating pip unrun and installed 19 authenticated wheels with CPython's
    bundled pip;
  - attest PASSED; 7 negative refusals, including the V810-F1 and F3 reproductions;
  - 553 in-job tests passed, leaving no bytecode;
  - readiness reached the authority refusal, and with the driver loaded both origin checks passed.
MAIN_STATE=main = origin/main = 5940557, tree 249e6499, zero open PRs. It is the merge of PR #94 onto
  #93 (86a5ed1), onto #92 (99e5499), onto 5f36126 (PR #91, the #84-#90 STATE checkpoint).
  Scratch worktrees remain under the session scratchpad; the repository checkout itself is single.
MAIN_STATE_PRIOR=main = origin/main = 200d822, clean, single worktree, zero open PRs. 200d822 is the
  merge of the PR #82 STATE checkpoint onto 0f9fe93; no product code moved with it.
  0f9fe93 itself was the head of a TWO-LANE BATCH merged in order: PR #80 (d790569,
  exact-main CI #147, tree byte-identical to the reviewed head b91b318) then PR #81
  (0f9fe93, exact-main CI #149). Before merging the second
  lane its reviewed head, tree and diff were re-verified unchanged, and the tree that resulted
  from merging it onto the NEW main was proven BIT-IDENTICAL to the composition preflight tree
  eefb993e228e11ca7147ea0363b03bcc09ac9b79, so what shipped is exactly what was reviewed
  together. Test arithmetic reconciles exactly: 1125 base + 3 + 4 = 1132.
  b4333ee was the PR #79 STATE checkpoint, which recorded 7ab92ab (PR #78, CI #143).
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
  PR #65 (3eeeef6): each watchlist symbol now shows its last analysis — when, primary
    timeframe, and the same conservative source indicator — plus an "Open latest analysis"
    action gated on detail_available. Joined in the browser from /v1/runs on NORMALIZED_SYMBOL,
    not symbol: the watchlist stores symbol.display while a run row's symbol is the raw request
    text, so joining on symbol would silently report analyzed symbols as never analyzed.
    NAVIGATION ONLY: no score, disposition or probability, and the watchlist is never
    reordered, ranked or badged. A symbol with no match reads "No recent analysis found." —
    NOT "not analyzed yet" — because /v1/runs is BOUNDED recent history and absence there is
    evidence about the window, not about the symbol. The watchlist renders symbols first and
    enriches after, so a failing /v1/runs never empties it.
  PR #67 (17ca9e1): /v1/analyze_batch now returns an "items" list — one entry per request, in
    ORIGINAL REQUEST ORDER, carrying index, the RAW requested symbol, and status OK|ERROR, with
    run_id for OK and the same detail object for ERROR. Each errors entry also gains symbol.
    results is unchanged and every existing errors key keeps its value, so a consumer reading
    only those sees no difference; the analysis payload and analysis_hash do not move. Exactly
    one analysis attempt per item: nothing is retried and nothing extra is analyzed to recover
    identity. The raw request text is used deliberately — when the failure is a
    symbol-normalization rejection there is no normalized symbol, so it is the only honest
    identifier. The frontend renders in request order and falls back to successes-then-errors
    when items is absent.
  PR #69 (18e987a): the persistence status line now states its CONSEQUENCE instead of naming a
    state. STATELESS and UNAVAILABLE each say that the analysis is not retained and will not
    appear in Recent Analysis history; OK says storage is available and deliberately does NOT
    say "saved", because the write is best-effort and fire-and-forget, so claiming a completed
    save at render time would be a claim the frontend cannot support. Wording only: the status
    values, the API and the persistence path are unchanged.
  PR #70 (9923f33): the SAME wording now serves both places. The Detail "Persistence" row was
    carrying its own second copy of the status text, so PR #69 moved the header badge and left
    Detail behind; persistenceStatusText is now extracted once and used by both, and an
    executable test pins them equal for all four statuses. Also reverts a regression this lane
    introduced in its first commit: Detail's "Live data" row had been changed to a raw boolean,
    which made a missing value render blank instead of "n/a", capitalised only that one row,
    and disagreed with the second "Live data" row that still went through formatValue. It is
    restored to main's behaviour — formatValue already renders null/undefined as "n/a",
    booleans as "yes"/"no", and arrays as joined or "none".
  PR #72 (b8f5ff6): the global refresh control now actually refreshes Recent Analysis.
    refreshCurrentView branched on the active tab for single, watchlist and batch and then
    FELL THROUGH to loadSystemStatus() + markRefreshed(). The Recent tab (data-tab="recent")
    had no branch, so clicking the control there pinged /v1/system_status, never called
    loadRecentRuns(), and still stamped "last refreshed at ..." — the list stayed stale while
    the UI claimed a refresh. Recent now reloads /v1/runs and NOTHING else: no analysis, no
    write, no POST, no new endpoint, and the existing analysis-active and cooldown guard is
    untouched. Three supporting changes keep the wording honest rather than moving the lie one
    level down: loadRecentRuns swallows its own error, so it now REPORTS success and the stamp
    is written only when the reload actually happened, while a failure still arms the cooldown
    so the control cannot be hammered; markRefreshed takes an optional label and delegates the
    cooldown to startRefreshCooldown, with the default reproducing the previous text exactly so
    all four pre-existing call sites are unchanged; and the button reads "Refresh" on Recent
    instead of "Re-analyze", still "Re-analyzing..." on every tab while an analysis genuinely
    runs, with showPanel refreshing the label on a tab switch. The dev tab uses the same
    fallback and has the same untruthful label; it was DELIBERATELY LEFT ALONE rather than
    widening the task, and remains an open adjacent candidate. The new test executes the real
    functions in node against a fake DOM, and was not taken at face value: each of the three
    guards was reverted in turn and the test confirmed to fail.
  PR #74 (4af3bfd): the Dev tab refresh now says what it actually refreshes — the adjacent
    candidate PR #72 deliberately left open. The Dev tab used the same fallback, but unlike
    Recent its ACTION was already legitimate and is unchanged: /v1/system_status is a
    read-only GET, and on success api() feeds updateStatusFromPayload, which refreshes the
    persistence badge and Dev Mode availability. Only the wording lied. The button now reads
    "Refresh status" instead of "Re-analyze", and loadSystemStatus — which catches its own
    error and degrades the badge to UNKNOWN — now REPORTS success, so a failed refresh is no
    longer stamped "last refreshed at ...". A failure still arms the cooldown and still
    degrades the badge. The trailing fallback for an unrecognised tab got the same treatment
    and keeps the generic wording. NO AUTH-SEMANTIC CHANGE: zero diff lines touch
    updateDevModeUx, #devModeStatus, #devCode, #devForm, /v1/auth/dev, #loadRuns or
    /v1/debug/*, and no refresh message is ever written into the Dev Mode status line.
    MUTATION TESTING FOUND A REAL HOLE, now closed: the behaviour test STUBS loadSystemStatus
    and loadRecentRuns, so their real bodies never ran, and making loadSystemStatus's catch
    return true instead of false left the whole suite GREEN while silently restoring the very
    bug being fixed. That one-line contract — resolve true on success, false in the catch —
    carries every honesty guarantee in both refresh lanes. A second test now executes the real
    functions with api stubbed and pins all four outcomes plus the UNKNOWN degradation. The
    loadRecentRuns half shipped in PR #72 with the same hole and is closed here too.
  PR #76 (b7d4657): OPERATOR LOGOUT — the first T2 lane in this run. There was no way to end
    a session: the operator could only wait for the cookie to expire, and an elevated Dev Mode
    cookie outlived any intent to stop working. POST /v1/auth/logout is authenticated by the
    existing app session and deletes BOTH cookies with the exact attributes they were set with
    (path=/, HttpOnly, SameSite=lax, Secure when configured) so the browser actually matches
    and drops them. It clears the Dev cookie UNCONDITIONALLY — a logout that leaves an elevated
    session behind is the bug the route exists to prevent. No DB, no write, no analysis, no run.
    POST ONLY, deliberately, and NO MIDDLEWARE: a GET reaches the StaticFiles mount and 404s,
    so logout is unreachable by navigation, and SameSite=lax means a cross-site POST carries no
    cookie and fails the session check. An earlier revision added a global http middleware that
    ran on EVERY request just to turn that 404 into a 405; it was removed in review, because the
    status code was a test preference and 404 already satisfies the security requirement. Do not
    reintroduce it — the test now pins the real property, that a GET does not end the session.
  TTL MISMATCH FIXED (proven, not speculative): create_session_token has always expired the
    token at now + settings.session_ttl_seconds, from the operator-settable
    UCPE_SESSION_TTL_SECONDS, while set_session_cookie hardcoded max_age=3600. They agreed ONLY
    at the default. Above 3600 the browser dropped a still-valid cookie and logged the operator
    out early; below it the browser kept a cookie the server already rejected, so the UI looked
    signed in while every call returned 401. The cookie lifetime now follows the configured TTL,
    and a regression test asserts the real numbers (900 and 7200), not 3600.
    The UI's Log out control returns to a freshly-loaded state. The cookies are HttpOnly, so the
    browser cannot clear them itself: a FAILED request does NOT show a logged-out state, it says
    the operator is still signed in. A 401 is the exception and counts as logged out.
    clearOperatorData runs on LOGIN as well as logout, so a response still in flight when logout
    is clicked cannot leave the previous session's results in the DOM for the next login.
    Exactly one line was removed from auth.py (max_age=3600); app.py is purely additive; no
    existing auth check, limiter or comparison was touched. api/auth.py is NOT a guarded source
    path; app.py, index.html and app.js are, but all three were already in CURRENT_DELTA_PATHS,
    so the guard's delta set is unchanged.
  PR #78 (7ab92ab): SESSION EXPIRY RECOVERY. A normal authenticated request that 401s because
    the session is no longer valid used to leave the UI claiming to be signed in, with every
    later action failing under its own local error message. It now returns the UI to the
    locked/login state and clears operator data.
  THE CLASSIFICATION IS THE WHOLE POINT — DO NOT BLANKET ALL 401s. Recovery is OPT-IN through
    a sessionApi wrapper; api() itself is unchanged. Classification follows the endpoint's
    BACKEND GUARD, never the 401 message text, because verify_session_token emits three
    different messages ("Session expired.", "Valid session is required.", "Dev Mode re-auth is
    required.") and none is a stable contract. TEN sites guarded by require_app_session
    recover: /v1/system_status, /v1/analyze, /v1/analyze/detail/{id}, /v1/runs twice
    (loadRecentRuns and the watchlist enrichment), /v1/calibration, /v1/analyze_batch, and GET,
    POST and DELETE on /v1/watchlist. FIVE are excluded and MUST STAY EXCLUDED: POST
    /v1/auth/login and POST /v1/auth/dev are PUBLIC routes where a 401 means the code typed was
    wrong, not that a session ended; GET /v1/debug/runs and GET /v1/debug/export/{id} are
    guarded by require_app_dev_session, which reads ONLY the dev cookie, so a 401 there means
    Dev re-auth is needed while the normal session is perfectly valid; POST /v1/auth/logout
    handles its own 401. The URL namespace mirrors the guard boundary exactly, which is what
    makes the map stable. Opt-in is the safe default: a future normal-session call that forgets
    the wrapper merely misses the recovery, while a future dev call inheriting a global rule
    would destroy a valid session.
    The wrapper recovers BEFORE rethrowing, because three of the ten sites swallow their own
    errors, and rethrowing keeps existing finally blocks such as setAnalysisActive(false)
    running. A sessionGeneration counter, incremented ONLY on successful login, stops a 401 from
    an old session locking a session that has since been signed back in; handleSessionExpired
    also returns early when the workspace is already hidden, so concurrent 401s — routine, since
    loadWatchlist fires two requests in parallel — recover exactly once. An earlier revision
    incremented that counter inside resetToLoggedOut, which was both unnecessary and destructive
    to three existing tests; resetToLoggedOut is byte-identical to what preceded it.
    Eight mutations were confirmed to break the suite, including the three forbidden ones: the
    dev debug route recovering, dev login recovering, and an invalid access code logging the
    operator out. The test file also carries a COVERAGE GUARD that extracts every call site from
    app.js and asserts each is in the RECOVER or the EXCLUDE set, so a new unclassified call
    site fails the build instead of silently inheriting a default.
    src/, schemas/, migrations/, frontend/index.html and frontend/styles.css are byte-identical
    to the previous main: no backend change, no auth weakening, no retries, no writes.
  PR #80 (d790569): SESSION RESTORE ON LOAD. The session cookie is HttpOnly, so the page
    cannot read it, and nothing asked the server whether it was still valid. Every reload
    showed the login panel and made the operator retype the access code even when the cookie
    was good — and it is good for the full configured UCPE_SESSION_TTL_SECONDS since PR #76
    aligned the cookie lifetime to the token TTL. Boot now probes with loadSystemStatus, which
    already performs a read-only GET on the session-guarded route and already reports success.
    REUSING IT ADDS NO CALL SITE, which is why the PR #78 401-classification coverage guard
    stays green and untouched; do not replace this with a new api() call without classifying
    it there. A 401 at boot routes to handleSessionExpired, which returns immediately because
    the workspace is still hidden, so nothing is reset and no expiry message appears. Success
    mirrors the login path exactly, including the sessionGeneration bump and clearOperatorData
    before unhiding. A FAILED PROBE SAYS NOTHING: not being signed in is the default state, and
    announcing a failed session check on every first visit would be noise and wrong.
  PR #81 (0f9fe93): DEV MODE REPORTS WHAT ACTUALLY FAILED. Two defects. A failed Dev auth
    rendered devModeStatus.textContent — the AVAILABILITY line owned by updateDevModeUx, which
    reads "Dev Mode is available. Re-auth to load debug tools." Being truthy it always won, so
    a wrong Dev code, a rate limit and Dev Mode being disabled all produced that same sentence;
    typing the wrong code looked like nothing had happened. The backend distinguishes all three
    (401 "Invalid Dev Mode code.", 429 with retry_after_seconds 60, 403 "Dev Mode is disabled.")
    and every one was discarded. loginFailureMessage already handled them, including the retry
    hint, so the handler now uses it; devModeStatus keeps its own job and is never overwritten.
    Separately, Load Runs and the per-run Export buttons had NO error handling at all, so a
    failure — most often an expired Dev session — became an unhandled promise rejection and the
    operator saw nothing happen. Both now report, naming which action failed, and a 401 says Dev
    re-auth is needed WHILE STATING THE NORMAL SESSION REMAINS ACTIVE, which is true because
    those routes are guarded by require_app_dev_session and read only the dev cookie. No retry
    and no automatic re-auth. The three Dev and debug call sites DELIBERATELY keep plain api
    rather than sessionApi, so a Dev 401 still cannot end the normal session.
  SWEEP RESULT, so it is not redone blindly: /v1/system_status returns shelter_mode,
    kill_switch, circuit_state, repository_type, provider_mode, store_status,
    news_sources_status and last_calibration_utc that the UI drops. All are CONSTANTS today, so
    surfacing them would be speculative UI rather than user value — rejected, same call as the
    news influence_mode wording. Single-analysis per-timeframe failure, watchlist failure
    states and the build fingerprint were audited and are already correct.
  MERGED IS NOT DEPLOYED: none of this is in front of users.
ACTIVE_LANE=feat/5a-evaluator-on-main (LOCAL, NOT PUSHED) — the repaired §5A evaluator recomposed onto
  main. Implementation 0bbcdd5; fresh full Codex adversarial verification task-807 in progress.
OWNER_PRODUCT_DECISIONS=Two candidates are CLOSED BY OWNER RULING, 2026-08-28. They are not
  defects and must NOT be re-proposed by a future whole-product gap sweep. Both surfaced
  repeatedly as the only remaining candidates once the board was otherwise clear, so they are
  written here to stop that loop.
  1. RECENT HISTORY STAYS FIXED AND BOUNDED FOR v1. Do NOT add an operator-adjustable
     /v1/runs limit. What "recent" should mean is a product question the owner has answered,
     not an implementation gap. /v1/runs remains bounded recent history, which is also why the
     watchlist says "No recent analysis found." rather than claiming a symbol was never
     analyzed — absence there is evidence about the window, not about the symbol.
  2. CONSTANT system_status FIELDS STAY HIDDEN absent a real operator use case. The UI
     deliberately drops shelter_mode, kill_switch, circuit_state, repository_type,
     provider_mode, store_status, news_sources_status and last_calibration_utc. Every one is a
     CONSTANT in the current build, so rendering them would be speculative UI rather than user
     value. Surface one only if the owner raises a concrete operator need, or if that field
     actually starts to vary.
SUPERSEDED_FROZEN_LANES=The T_close freeze on the three lanes below LAPSED BY ITS OWN TERMS when
  T_close passed. fix/r202-01 (2c35ab2) and fix/a203-01 (b5310dc) were 63 commits stale; they were
  REPLAYED onto exact main d52e9ae in fresh worktrees, revalidated independently, and shipped as
  #89 and #90. The originals are SUPERSEDED and kept only for provenance. integration/b11-combined
  (1b10587) was deliberately NOT used as a release candidate and is superseded too.
  OPERATIONAL NOTE ON #90: A203 makes candle validation STRICTLY STRICTER — exact adjacency and
  rejection of a future latest close — so provider data previously tolerated with small gaps now
  fails analysis rather than proceeding. It is merged, NOT deployed.
FROZEN_POST_T_CLOSE_PRIOR=Three branches are LOCAL-ONLY and frozen until after T_close. None is
  pushed, none is on any remote, none is on main. Do not open a PR, merge, or deploy any of
  them before T_close:
    fix/r202-01              2c35ab2  provider HTTP byte cap + wall-clock deadline (R202-01)
    fix/a203-01              b5310dc  candle ordering/future boundaries fail closed (A203-01)
    integration/b11-combined 1b10587  the two above merged, for integration evidence only
  Re-verified at this pre-T_close checkpoint: still absent from origin, still unreachable
  from main, still frozen.
COLLECTOR=STOPPED on main as of #88 (651c63e): the schedule trigger is removed, workflow_dispatch
  retained, and WHAT the collector writes is unchanged. The §5A.5 pre-registered cadence
  assertion was INVERTED rather than deleted, so restoring a schedule fails the build. The
  OUTCOME RESOLVER IS STILL SCHEDULED (resolve-outcomes.yml, cron "17 * * * *"), which matters:
  outstanding predictions still need outcomes.
DELEGATE_HAZARD=CLOSED by #87. delegate.sh rotates any existing result and log to .prev-<ts> and
  refuses a result older than the invocation, so a stale verdict can no longer satisfy
  completion. That exact failure happened once and was nearly reported as a fresh verdict.
CODEX_VERIFICATION_807=COMPLETE, verdict NOT_VERIFIED. Fresh (result 14:28:56Z; Opus's independent
  review was written earlier at 13:47:32Z). 40 of 40 mutations KILLED, so the repair's mechanisms
  hold; G3.4 unsatisfiability independently CONFIRMED. Evidence and the consolidated MAX review are
  at .work/807/.
  CRITICAL F1 — out-of-tranche symbols are pooled into A and B. Verified by Opus: losing BTC alone
  is NOT_PASS (A=F, B=F); adding SOL/USDT flips it to A=T, B=T. Scope was enforced at authorization,
  never at admission. This makes PASS easier and has existed since the original decision layer.
  HIGH F3 — the CLI builds Settings(), which ignores the environment, so in Actions readiness would
  report an EMPTY in-memory store: a false "frame failed". Verified by Opus. Every other script uses
  Settings.from_env().
  HIGH R4 (Opus) — the workflow offers readiness and consume only, so seal recovery is unreachable
  where the secret lives. HIGH F4/F5 — the library accepts an undeclared authority and
  verify_pin=False. HIGH F2 — readiness and consumption identities are incomparable. MEDIUM F6-F9,
  LOW F10, R2.
CODEX_PENDING=NONE. task-811 COMPLETE. It is fresh: fired 06:44:29Z, delegate exit 06:53:47Z, base
  02d5844, tree f75fd138, no tracked change, and every restored file matches its committed blob.
CODEX_VERIFICATION_811=VERIFIED. Committed suite: 5 KILLED, 0 SURVIVED. The gate passed at 1739 both
  before and after the mutants.
  - M1: the wheel-digest check in audit_site_packages was disabled (the V810-F1 regression). Killed
    by test_a_tampered_file_with_a_rewritten_installed_record_refuses.
  - M2: the site-packages symlink refusal was disabled (the V810-F3 regression). Killed by
    test_a_symlinked_package_directory_refuses.
  - M3: lock-hash membership was disabled. Killed by test_a_wheel_the_lock_does_not_authenticate_refuses.
  - M4: pip, setuptools and wheel were allowed beside the lock. Killed by
    test_not_even_the_installer_may_sit_beside_the_lock.
  - M5: the install ran the floating `python -B -m pip`. Three workflow-boundary tests killed it.
  Opus cross-check: the raw pytest output has exactly 7 FAILED lines, which are the credited tests
  (3777 run - 3770 passed). Each mutant disabled a single guard, and every sibling test passed.
  Evidence: .work/811/codex/, with a SHA-256 manifest in .work/811/evidence.sha256.
  Final MAX review: .work/811/final-max-review.md.
CODEX_VERIFICATION_810=NOT_VERIFIED. 5 of 5 mutants KILLED by committed tests. Bypass hunt:
  - CRITICAL V810-F1: the installed RECORD is trusted. A file tampered together with its RECORD
    passes; Opus REPRODUCED it on the toolcache-shaped interpreter.
  - HIGH V810-F3: symlinked directories evade the walks; Opus REPRODUCED it.
  - HIGH V810-F2: time of check to time of use — hashed once, loaded later by path.
  - HIGH V810-F4: module origins are read from mutable attributes.
  Root cause (Opus): the checks authenticate against mutable installed metadata, not the pinned
  hashes; and the job runs one unverified piece of code, the floating pip that setup-python
  force-reinstalls from PyPI and the install step executes. The runtime-identity class is at the
  bound (E3 -> V809-F1 -> G1 -> V810). NO unilateral repair.
  Final MAX review: .work/810/final-max-review.md. Evidence: .work/810/.
CODEX_VERIFICATION_809=VERIFIED_WITH_FINDINGS on composition faaed6d (tree 993fc5dd). Committed suite:
  15/15 mutants KILLED, 0 SURVIVED, no new tests. Gate 1652. Red tests (c7e5d4c6...) and the adopted
  808 tests (b88f1838...) intact. Migration 0009 REVIEWED BUT UNEXECUTED: NULL, precedence and key
  spelling verified. The library provenance=None allowance is not permission on any real path.
  The resolver claim (§33) was proven by execution.
  MEDIUM F809-1, found independently by Opus as O809-1 15 minutes before Codex's report: the runtime
  identity binds distribution METADATA, not import ORIGINS. Codex's shadow certifi.py was imported
  under locked metadata; Opus's committed scripts/platform.py executed while the pin passed.
  Causes: module-level imports run before attestation; scripts/ is sys.path[0]; PYTHONPATH=src;
  untracked files are ignored; same-version duplicate distributions collapse. Not reachable through
  dispatch input.
  LOW F809-2: the workflow step reader silently drops workflow-level env.
  Consolidated MAX review: .work/809/consolidated-max-review.md. Evidence: .work/809/.
CODEX_VERIFICATION_808=NOT_VERIFIED. Consolidated MAX review: .work/808/consolidated-max-review.md.
  Evidence: .work/808/codex/ and .work/808/opus/.
  CRITICAL V808-F1 (Codex; Opus reproduced it harmlessly with a stub): the evaluation workflow puts
  `--confirm '${{ inputs.confirm }}'` into shell source AFTER the pin-check step, with
  SUPABASE_DB_URL in the step env. A dispatcher can mutate the evaluator, re-pin, and consume under
  altered rules. Needs write access: PUBLIC repo, exactly 1 push-capable account, 0 environments.
  Not live — the workflow exists only on this unpushed lane.
  HIGH R6 (Opus, new): the run step pipes into `| tee` under GitHub's default `bash -e` with no
  pipefail (confirmed in GitHub docs; reproduced), so a refused or crashed readiness, consume or
  recovery shows GREEN.
  MEDIUM R7 (Opus, new): Codex's 40/0 holds only with its uncommitted test_adversarial_808.py.
  Against the COMMITTED suite, mutants re-pinned: R01, R07, D08, D10, D12, S07 and S08 SURVIVE
  (1476 passed). S07 and S08 count exact ties for the candidate in B2 and C, contrary to §5A's
  "ties count as WORSE" — the implementation is correct, but nothing committed catches a regression.
  MEDIUM R5 (Opus, pre-result; Codex silent): requirements ranges plus interpreter drift, so the
  verified runtime is not the executed runtime.
  HOLDING: amendment c44e416 faithful; guard order and D3; F1 scope; D4 identity; D1 closure; 0009
  lifecycle (REVIEWED BUT UNEXECUTED); gates 1476 committed / 1483 with Codex's tests.
  CLASS AT BOUND: V808-F1, R6 and R5 are the second defeat of the entrypoint class (a guarantee
  true in the library, false at the production entrypoint; first defeat F3/R4). Root cause: the
  workflow is only ever checked as text and never executed, and its runtime is unbound. NO
  unilateral repair was made.
  Out-of-lane, not acted on: resolve-outcomes.yml:64 has the same tee masking; oos-pair-evidence.yml
  interpolates typed inputs into run (LOW).
OWNER_RULINGS_D1_D4=Applied 2026-09-13. D1 pin derived from the entrypoint's full first-party import
  closure plus declared rule/runtime surfaces (67 files; does not reach the HF app surface). D2 G3.4
  amended — barrier moved pre-claim, separate single-reader proof — in its own commit c44e416 with the
  amendment chained from the Codex original hash. D3 fail closed unless durable authority AND pin are
  positively verified; verify_pin removed from consumption and seal recovery. D4
  decision_population_id, probability-free, distinct from evidence_snapshot_id.
REPAIR_808_BASE=fd8239a. ./verify.sh PASS 1476. All 807 structural repairs applied: F1 scope at
  admission (CRITICAL), F3 Settings.from_env, R4 workflow recompute, F6 materialized cells + declared
  schema, F8 TRUNCATE guard, F10 contract-instants cross-check, R2 ReadinessRefused. Behavioural
  mutations with the mutant re-pinned: all four new critical guarantees KILLED.
ESCALATION_807=RESOLVED by owner rulings D1-D4 (see OWNER_RULINGS_D1_D4). As originally escalated:
  three causal classes have now been defeated twice each and are AT CLAUDE.md's
  two-attempt bound: pin scope (F6 -> G4 -> F7), diagnostics completeness (F7 -> G6 -> F6), authority
  surface (F2 -> G8 -> F4). No repair was started. Root cause for pin scope is measured: the CLI's
  first-party import closure is 23 files and 8 are unpinned, including config/settings.py, which
  undercuts the pre-registration's reason for rejecting closure-based pinning.
GPT_REQUEST_ID=NONE
GPT_THREAD_URL=NONE
GPT_REQUEST_STATE=NONE
OWNER_BOUNDARY=NONE OPEN. The T3 batch #92-#94 is CONSUMED; the owner authorized it on 2026-09-14,
  and it was executed exactly. K1=A and K2=A were ruled with it.
  Lane D needs its OWN T3 once it is built and verified. Applying 0009, readiness and consumption
  are each a SEPARATE T4.
OWNER_BOUNDARY_CONSUMED_T3_92_94=The request as it was made (.work/811/final-max-review.md):
  - The batch: push the three branches to origin (NEVER hf), open three independent PRs, and merge
    in order A, B, C. Each merge needs exact-head CI green, a --match-head-commit merge, parents
    verified and exact-main CI green. The merged main tree must equal the gated local composition.
    Stop on the first mismatch.
  - Merging runs only ci.yml, which uses no secrets. The evaluation workflow is dispatch-only, and
    no dispatch is authorized.
  - K1 (F-0009-A HIGH, no RLS or REVOKE on the seal table). A (recommended): amend in a follow-up
    lane D before any apply. B: fold into lane A before the push.
  - K2 (F-0009-B, no apply route). A (recommended): a dedicated manual-dispatch workflow for 0009
    alone, with the F-0009-C pre-checks. B: an apply mode in the evaluation workflow.
  Runbook: .work/811/0009-apply-only-runbook.md. Every T4 stays separate.
OWNER_RULINGS_J1_J3=Ruled 2026-09-14, now APPLIED and VERIFIED:
  - J1=B, with a closed trust base: exact CPython 3.13.14, pinned Actions, CPython's bundled pip;
    wheels authenticated against the lock; installed bytes against the wheel's own RECORD;
    symlinks and unexpected import surfaces refused; no unverified code after attestation;
    Addendum 7; no import hook.
  - J2=A: Codex ran one mechanical spot-check of 5 mutants, all killed.
  - J3: after 5/5 killed and a green composition, return ONE T3 batch for A, B and C.
  In parallel: the READ-ONLY proof and runbook that 0009 applies with --only, without 0008 (done).
  The T3 batch #84-#90 of 2026-09-13 is CONSUMED as well.
OWNER_BOUNDARY_PRIOR=Fourteen T3 origin batches are CONSUMED and must not be reused: the
  PR #56, PR #57, PR #59, PR #61, PR #63, PR #65, PR #67, PR #69, PR #70, PR #72, PR #74,
  PR #76 and PR #78 batches, plus the two-lane PR #80 + PR #81 batch. Each authorized exactly
  its own push, PR and merge, and no deploy. No T4 has been authorized or consumed for
  migration 0008. The PROD-SAFE-2 T3/T4 authorization remains CONSUMED. Standing prohibition while the
  holdout runs: no holdout or outcome inspection, no collector dispatch, no deploy, no model
  change, no re-freeze.
DEPLOY_PROHIBITED=HELD BY OWNER RULING until the §5A one-look result is captured and checkpointed.
  The original wording below was scoped "through T_close" and would have lapsed silently when
  T_close passed; the owner extended it instead. Production stays at hf/main = a89b45e
  (PROD-SAFE-2), re-confirmed unchanged after the batch. No workflow deploys to Hugging Face, so
  no merge can deploy. Original wording:
DEPLOY_PROHIBITED_PRIOR=NO HUGGING FACE DEPLOY OF ANY KIND WHILE THE HOLDOUT RUNS, through
  T_close = 2026-09-12T04:00:00Z. This binds every lane in this file, including work already
  merged to main. A push to origin is a separate, lesser action and never implies a deploy;
  only a push to the hf remote deploys. Production stays at hf/main = a89b45e (PROD-SAFE-2),
  confirmed unchanged immediately after every merge.
NEXT_ACTION=Build lane D on feat/5a-0009-hardening-apply-route, following .work/812/lane-d-design.md:
  - D1: amend 0009, add text tests, re-pin, and a pre-registration addendum;
  - D2: a one-transaction apply script with pre- and post-checks and a fake-driver suite;
  - D3: a dispatch-only workflow, with contract and executed-boundary tests.
  Then ./verify.sh, a fake-driver end-to-end run, ONE Codex spot-check of at most 5 mutants, and an
  Opus diff review; then request lane D's T3.
  DO NOT run readiness, consumption or recompute; dispatch any workflow; apply 0008 or 0009; push
  to hf; or deploy.
NEXT_ACTION_PRIOR=SECTION 5A ONLY, scheduled: WAIT until T_close = 2026-09-12T04:00:00Z, then run the
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
