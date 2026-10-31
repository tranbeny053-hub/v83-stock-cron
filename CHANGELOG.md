# Changelog

All notable changes to this project are recorded here.

## 2026-10-30 - The C10 evaluation-row producer, synthetic only (on main, not released)

It records #307. Nothing in this entry is released.

Added:
- #307: `scripts/quant_ng_evalrows.py`, a dormant tool that schedules evaluation instants and
  labels exactly the resolvable ones for the C10 censoring tool. A row is labelled only when
  regular bars close exactly at its start and at its horizon end within the quarter, using the
  product's strict rule (up only above the band, down only below it, otherwise a timeout) in exact
  fractions. Every scheduled instant needs both arms' forecasts; one missing refuses the run. It
  writes the censoring tool's input, which never carries a price, and a record stamped synthetic.
  Its horizon, cadence and band are test-only settings, and three synthetic choices are named in
  the record: instants start at the quarter's first day, a missing forecast refuses the run, and
  one band applies to the whole run.

Notes:
- Classification, counting and score bounds stay in the C10 censoring tool, which is unchanged.
- Nothing in the product imports it, and no deployed file changes, so the running app is
  unaffected. No real-data path exists, and no scientific validity is claimed from synthetic
  tests.

## 2026-10-29 - C10 (A+) censoring accounting and G-1 (a′) trading at T, synthetic only (on main, not released)

It records #304. Nothing in this entry is released.

Added:
- #304: `scripts/quant_ng_censor.py`, a dormant accounting tool for the future evaluation-row
  stage, reading synthetic input only, with its horizon a test-only parameter. A row resolves only
  if the regular bar closing exactly at its horizon end exists. Every other row is counted with
  one reason, in this order: span end, halt, unknown, then confirmed delisting. Unknown is never
  pooled with delisting. Rows end by the quarter's end, and classification reads no bar closing
  after the earlier of the corpus end and the quarter end. Score bounds use exact fractions and
  one shared label per censored row for both arms. A claim holds only at the adverse end.

Changed:
- #304: the dormant universe builder, `scripts/quant_ng_corpus.py`, now admits a symbol at T only
  if its daily bar for the day before T exists with quote volume above zero. Otherwise the symbol
  is `not_admitted: not_trading_at_t`. The completeness rule and the universe rule file are
  unchanged.

Notes:
- Both follow the owner's 2026-10-29 rulings and are synthetic-only. They make no claim that
  real data is admissible; the provenance, availability and revision contracts are still unruled.
  Neither contains networking code.
- Nothing in the product imports either file, and no deployed file changes, so the running app is
  unaffected.

## 2026-10-29 - The parse layer for OD-NG-5(b) step (b1), MOCK fetch outputs only (on main, not released)

It records #301. Nothing in this entry is released.

Added:
- #301: `scripts/quant_ng_extract.py`, a dormant parser. It turns the archive kline files that
  the (b1) fetch tool verified into parsed daily bars and per-timeframe window counts at a
  UTC-midnight cutoff T. It reads only each row's open time, close time and quote-asset volume,
  never a price. Rows and files dated at or after T are discarded before any data check. Only
  files the manifest classes `ok` are parsed, each read once and re-hashed against the manifest.
  Off-grid bars fill no slot and add no volume; zero-volume regular bars count as present. Only
  a MOCK manifest is accepted, BTCUSDT and ETHUSDT are refused, and a refusal leaves nothing
  behind.

Notes:
- It writes no provenance record, so its output is not evidence the universe builder can use;
  the provenance contract is still unruled. It contains no networking code.
- Nothing in the product imports it, and it changes no deployed file, so the running app is
  unaffected.

## 2026-10-29 - Test pins for the dormant universe builder, and the model routing and worker rule in CLAUDE.md (on main, not released)

It records #297 and #298. Nothing in this entry is released.

Added:
- #297: four tests in `tests/scripts/test_quant_ng_corpus.py` pin refusals that the dormant
  universe builder already makes: a daily bar carrying any field but its open time and quote
  volume, a price included; a candidate carrying an unrecognised key, such as a delisting date; a
  coverage count above its history window, at 15m, 1H and 4H; and, with no freshness entry at all,
  every timeframe reported `unknown`, never fresh. The builder itself is unchanged.

Changed:
- #298: `CLAUDE.md` now carries the owner's model routing (the model and effort are chosen per
  milestone, from Opus Medium, High and XHIGH and Fable XHIGH and Max) and a worker rule. The rule
  allows at most two active safe lanes in total. Ordinary subagents may do bounded work but never
  count as a review the owner requires to be independent, which needs a separate, verified
  session. Codex execution through `./delegate.sh` is unchanged.

Notes:
- Neither change touches a deployed file, so the running app is unaffected.

## 2026-10-28 - The offline fetch executor for OD-NG-5(b) step (b1), mock archive only (on main, not released)

It records #294. Nothing in this entry is released.

Added:
- #294: `scripts/quant_ng_fetch.py`, a dormant executor that reads a plan's file list from a local
  mock archive folder, its only transport. Before reading any archive byte it validates the whole
  plan, refusing a path outside the archive's kline layout (a non-ASCII digit included), BTCUSDT or
  ETHUSDT, a refused base, a protected path fragment, and a plan over its request cap. Each file is
  classed ok, mismatch, checksum_malformed or missing against its official checksum; every byte
  string read is kept read-only under its digest, and a deterministic manifest (status `MOCK`) is
  written. Above the plan's unverified share it refuses, leaving nothing the run created.

Notes:
- It contains no networking code, under the owner's ruling F-RUN = (b1) only: offline, mocked and
  synthetic tooling. It does not fetch, parse klines or build evidence.
- Nothing in the product imports it, and it runs under the fit tool's write guard.
- It changes no deployed file, so the running app is unaffected.

## 2026-10-28 - The fit gate checks the universe snapshot's ruled identity (on main, not released)

It records #291. Nothing in this entry is released.

Changed:
- #291: `scripts/quant_ng_fit.py`, the dormant fit precondition gate, now refuses, before creating
  any output, a universe snapshot that is not a JSON object, or that lacks the ruled builder's id
  (`ucpe.universe.asof.v2`), status (`SYNTHETIC`), rule digest or F-C firewall. The ruled digest is
  pinned in the tool and tested equal to the builder's pin. The artifact records the snapshot's id,
  status and rule digest, and its tool and schema versions are now "2".

Notes:
- These are identity fields only: they do not prove the builder produced the file, and a row's
  symbol is not yet checked against the snapshot's membership.
- #291 is dormant and synthetic-only: nothing in the product imports it, and it has no network or
  fetch.
- It changes no deployed file, so the running app is unaffected.

## 2026-10-25 - The dormant as-of universe snapshot builder, synthetic-only (on main, not released)

It records #288. Nothing in this entry is released.

Changed:
- #288: `scripts/quant_ng_corpus.py`, with tests, builds one read-only as-of universe snapshot from
  pinned synthetic evidence, under the owner's ruling of OD-NG-5(a). The ruled values are in
  `ops/quant_ng/UNIVERSE_RULE_v1.json`, pinned by digest. It refuses any evidence that is not
  marked synthetic, and refuses to run without a completeness threshold marked as a synthetic test
  value, because that threshold is still unruled. BTCUSDT and ETHUSDT are never candidates.

Notes:
- #288 is dormant: nothing in the product imports it, it has no network or fetch, and it has never
  read market data. Real use waits on two further owner decisions, OD-NG-5(b) and OD-NG-7.
- It changes no deployed file, so the running app is unaffected.

## 2026-10-25 - Vietnam time beside UTC in the UI, and the fit tool's precondition gate, dormant (on main, not released)

It records #283 and #285. Nothing in this entry is released.

Changed:
- #285: the web UI shows Vietnam time (Asia/Ho_Chi_Minh) beside the UTC values it derives from. "last
  refreshed at ..." and the Recent list now render Vietnam time explicitly, where they used to take
  both the time zone and the locale from the viewer's own computer, so one screen read differently on
  two machines. Detail, Saved and Batch each show a Vietnam row immediately before each UTC row; every
  UTC row keeps its label and the backend's verbatim value. A value the record does not hold reads
  "Not kept in saved history." on both rows, never an invented time.
- #283: `scripts/quant_ng_fit.py`, with tests, adds the next-generation fit tool's precondition gate:
  it checks a fit plan's inputs, spans and cutoff, and refuses a plan that breaks any of its rules.
  It has no estimator, no universe rule and no real-data mode, and nothing in the product imports it.

Notes:
- #285 is display only: no API field, stored record, hash, candle boundary or evidence changes, and
  nothing is recomputed. Its owner ruling amended the detail view's row order to add the Vietnam rows.
- #285 changes `frontend/app.js`, a deployed file, so the running app differs from main until the
  next release; this entry is not that release.
- #283 is dormant: nothing in the product imports it, it has never been run on market data, and
  it fits nothing, because the estimator is deliberately absent.

## 2026-10-24 - Clearing the clipboard after each writer-token renewal (on main, not released)

It records #280. Nothing in this entry is released.

Changed:
- #280: `docs/runbooks/WRITER_CUTOVER.md` adds one step to the 30-day renewal advice: after
  replacing the `SUPABASE_WRITER_JWT` secret with the new token, clear the clipboard (step 7). The
  renewal card already said so; the runbook's own paragraph did not.

Notes:
- Documentation only: no code, schema, migration, gate, threshold or runtime behaviour change.
- The advice itself is unchanged: replace the token, never delete it, and an expired token makes
  every save fail while analyses are still served.

## 2026-10-23 - Weekly bars for the daily reference variant, dormant, and the writer runbook's current advice (on main, not released)

It records #275 and #277. Nothing in this entry is released.

Changed:
- #275: `quant_ng/reference_v1d.py` and `ops/quant_ng/REFERENCE_SPEC_v1d.json`, with tests and an
  update to `docs/NG_SCALE_CONTRACTS.md`, add weekly bars (1W) to the single-type daily variant, as
  the owner ruled, for development only:
  - weeks open on Monday at 00:00 UTC;
  - the 3-week lattice is anchored at 2026-09-21T00:00Z and extended backward only, and a weekly
    candle, a reference close, or a supplied anchor that closes or ends after that instant is
    refused;
  - the memory is all available history, and the pseudo-count is the existing "3 days of lattice
    rows" rule computed exactly (1/7 of a row);
  - daily bars, `reference.py` and `windows.py` are unchanged.
- #277: `docs/runbooks/WRITER_CUTOVER.md` now says the switch to the least-privilege writer is
  done and the writer's token is its only credential: never delete it; renew it by minting a new
  token, replacing the secret's value and clearing the clipboard; ask before revoking any key.

Notes:
- #275 is a proposal: the next-generation plan is not adopted, and nothing outside `quant_ng`
  imports the module: no served number, gate, stored row or response changes.
- No migration, gate, threshold or runtime behaviour change. The next release's runtime delta will
  include the module's weekly bars.

## 2026-10-23 - The next-generation window, reference and candidate tiers, dormant (on main, not released)

It records #272. Nothing in this entry is released.

Added:
- #272: five modules in `crypto_probability_engine/quant_ng`, with their specs and tests, and an
  update to `docs/NG_SCALE_CONTRACTS.md`:
  - `windows.py`: one validated, fail-closed candle window;
  - `reference.py`, with `ops/quant_ng/REFERENCE_SPEC_v1.json`: the day-type base-rate reference
    (spec v1, the research programme's frozen generation-2 reference), and `reference_v1d.py`,
    with `ops/quant_ng/REFERENCE_SPEC_v1d.json`: a single-type variant for daily bars (1D only),
    for development only;
  - `candidate.py`: the R4-C1 candidate behind an eligible artifact manifest, with a sigma guard
    and a named central range;
  - `availability.py`: monthly targets and the extended horizon reported as unavailable.

Notes:
- These are proposals: the next-generation plan is not adopted, and the sigma guard is a proposed
  reading of its guard.
- Nothing outside `quant_ng` imports the new modules: no served number, gate, stored row or response
  changes. The candle-history caller guard admits `quant_ng/windows.py` as a dormant caller.
- No model constant or prior value is in the repository: a manifest supplies the candidate's
  constants and the caller the priors; spec v1's values are the research programme's frozen
  reference spec, and v1d's are the next-generation plan's daily variant of it.
- A one-time parity run on development data, authorized by the owner, found spec v1's reference
  (`reference.py`) equal to the research code's, bit for bit, in 108 of 108 cells. That is
  implementation parity, not a forecast-quality claim.
- No migration, gate, threshold or runtime behaviour change. The next release's runtime delta will
  include the package's new modules.

## 2026-10-22 - Next-generation groundwork, the release tool's re-pin fix and the gate's lint message (on main, not released)

It records #268, #269 and #270. Nothing in this entry is released.

Added:
- #268: `docs/NG_SCALE_EXP00_DEPENDENCY_AUDIT.md`, a read-only trace of the forecast probabilities
  from the pipeline to their consumers, storage and response, and a new package,
  `crypto_probability_engine/quant_ng`, with `docs/NG_SCALE_CONTRACTS.md`:
  - the governing plan's evidence-population, forecast-clock and replay-custody safeguards as pure
    functions;
  - a strict artifact manifest.

Fixed:
- #269: `scripts/release.py repin` now moves the guard test's asserted asset tokens, and `identity`
  and `repin` wrap each note so that no comment line is longer than 100 columns. Both were repaired
  by hand at the P7P release.
- #270: `verify.sh` names the first ruff finding when lint fails; with ruff's default output format
  it printed an empty detail.

Notes:
- Nothing imports the new package: no served number, gate, stored row or response changes.
- No migration, gate, threshold or runtime behaviour change. The next release's runtime delta will
  include the unwired package's files.
- The next-generation plan these support (NGA) is proposed, not adopted; its decisions are the
  owner's.

## 2026-10-17 - Release UCPE-PROD-P7P-20261017-A

Released to production on 2026-10-17: `UCPE-PROD-P7P-20261017-A`, commit `27edbcad` (#264), over
`UCPE-PROD-E2-20261004-A` (`1caa8b08`). It carries the three entries below. The runtime baseline was
re-pinned to it (#265), and the source-integrity guard reads it healthy.

Notes:
- The wording was frozen on 2026-10-17, and the owner's UX comprehension check passed (54 of 54).
- The owner accepted the movement of `analysis_hash` and `evidence_hash` from E2 to this release, and
  only that: no forecast-quality claim and no directional permission is accepted; both registries are
  empty.
- No migration, gate or threshold change. In `quant/`, only the R4-C1 candidate identity was added,
  and no analysis uses it. The H2 hold is unchanged.
- The A4 audit seals stay as sealed against `UCPE-PROD-E2-20261004-A`: no reseal.

## 2026-10-16 - The calibration card's sample gate and the Evidence row's singular (released in UCPE-PROD-P7P-20261017-A)

It records #261 and F-7 (#262), released in `UCPE-PROD-P7P-20261017-A` on 2026-10-17.

Changed:
- #261: each calibration card's row that shows its timeframe's sample gate reads "Sample gate"; it
  read "Reliability status", the label of the "Current status" card's row for the analysis's fixed
  calibration baseline. Its value is unchanged.
- F-7: the Decision view's Evidence row reads "1 resolved outcome" for one; "0 resolved outcomes"
  and "N resolved outcomes" are unchanged.

Notes:
- Frontend copy only: no payload, `analysis_hash`, governed pin, UOR or contract change.
- The wording was frozen, and the owner's UX check passed, on 2026-10-17, before the release.
- The baseline residual stays open: the summary's fixed "INSUFFICIENT_SAMPLE".

## 2026-10-15 - Wording freeze: F-1, F-4, F-6 and the Model Quality copy (released in UCPE-PROD-P7P-20261017-A)

It records #260, released in `UCPE-PROD-P7P-20261017-A` on 2026-10-17.

Changed:
- F-1: the evidence gate's sentence for a timeframe with no demonstrated skill names the accuracy
  observed on these outcomes, where there is a rate ("The accuracy observed on these outcomes was
  44.0%."), and says the true accuracy is unknown ("The true directional accuracy is unknown: this
  is not a finding that it is at or below 50%."). The verdict and its threshold are unchanged.
- F-4: the fold that shows a list the backend gives names a list of one in the singular: "0 items",
  "1 item", "2 items". An object's fold reads "View", as before.
- F-6: the readiness sentence (`model_readiness_label`, the "Evidence level" row of a screen
  without an accepted claim) is now "Model readiness: Heuristic (uncalibrated) — not validated."
  It said that accuracy was "not yet measured", which a screen showing an observed accuracy
  contradicted.
- S1/S2: two lines of the Model Quality section no longer state a measurement status that the
  same section contradicts. The "Current status" card without a calibration metric reads "This
  summary lists no calibration metric: measured calibration begins once the sample gate is met."
  (it read "Resolved-sample metrics are not surfaced in this view yet."). A calibration card at
  INSUFFICIENT_SAMPLE reads "Early diagnostic — too few resolved samples to establish
  reliability." (it read "Early diagnostic — not measured yet.").

Notes:
- `analysis_hash` moves for every analysis, human and automation, because F-6's sentence is in
  the payload (`frontend_display` and `timeframes`); on a timeframe with no demonstrated skill,
  F-1's sentence moves it as well. The governed pins moved, with their prior values recorded
  beside them (`tests/api/test_cadence_runtime_primitives.py`). F-4 and S1/S2 are frontend copy
  only: they move no payload.
- The UOR synthetic examples were regenerated (`docs/automation/UOR_HANDOFF.md`, revision
  2026-10-15): in each success example only `analysis_hash` and `evidence_hash` changed. The
  schemas, the contract, the error example and the live canary example are unchanged.
- No gate, block code, disposition token, threshold or quant change.
- The UX comprehension card was regenerated for F-1 and F-6. The wording was frozen, and the
  owner's UX check passed, on 2026-10-17, before the release.
- F-7, the Decision view's Evidence row reading "1 resolved outcomes" for one, was fixed by #262
  (the entry above).

## 2026-10-12 - Decision View, Gate Kinds and Save Receipt (released in UCPE-PROD-P7P-20261017-A)

What the release `UCPE-PROD-P7P-20261017-A` (2026-10-17) carries since `UCPE-PROD-E2-20261004-A`, as
merged up to the release-prep change that added this entry.

Changed:
- Added the Decision view (`decision_view.v2`), the one authoritative block of an analysis: its
  state, its sentence, its range and cost, its evidence and its gates. It leads the Single card,
  the Batch card and the Detail panel.
- Added the gate view (`gate_view.v1`), carried in the Decision view: the backend says which kind
  each active hard gate is (a risk gate with a measured finding, a system or data gate, the
  evidence gate), lists each with its sentence, and gives one summary and one framing. The
  frontend displays these and words none of its own.
- Added the saved-run view (`saved_run_view.v1`): a reopened run's block is built by the backend
  from what the run stores when it is read back, and a value the record does not hold says so.
- Added the save receipt (`save_receipt.v1`, `GET /v1/analyze/receipt/{run_id}`): whether one
  analysis was saved, asked after its response and shown in its Storage row.
- Changed the storage wording: the badge reads "Storage, last checked: ...", the Overview row reads
  "Storage when requested", and neither stands for the save receipt of one analysis.
- Added a lock to the in-memory run store, so a run added while the store is listed no longer
  makes a request fail.
- Retired the older decision sections from the default screen (the decision card, the gate
  brief, the scenario plan, the advisor explanation and the permission rows). Their fields remain
  in the response and in Raw JSON.
- Added a caveat where a round-trip cost is fees only because no slippage could be estimated.
- Changed how a gate result is styled: by the gate kinds the backend names (neutral for the
  evidence gate alone, the risk style for a measured risk gate, a distinct style for a system or
  data gate), with a layout for the Decision view's own lines.
- Added the owner's UX comprehension card (`docs/runbooks/UX_COMPREHENSION_CHECK.md`), generated
  from the product's own screens.
- Changed the frontend asset token to `p7p-20261012-a`.
- Renamed the third outcome from "Timeout" to "In band" on the screens (UX-1, 85462e4): it is the
  close at the horizon inside the decision band, not a clock timeout. The analysis payload's
  `probability_explanation` text changed with it. The data keys stay `p_timeout` and `TIMEOUT`.
- Added one provider connection pool for the process, one exchange for identical in-flight
  provider requests, passive per-analysis provider measurement, and an observe-only analysis
  budget that counts analysis requests and refuses none (#232: 7e39fd3, 948edf7 and 5bcd71c;
  follow-up #236).
- Added the R4-C1 candidate identity, `quant/candidate_r4_c1.py`, which no analysis uses (#225,
  429f1df).

Notes:
- Analysis only. No trading, order, transfer or execution capability is added.
- The hard gates are unchanged: every gate action, block code, disposition token and threshold
  is what it was. What changed is how a gate result is described and shown.
- `analysis_hash` moves for every human analysis, because the response carries new fields. The
  automation analysis carries no Decision view, but its `analysis_hash` and `evidence_hash` also
  moved since production: UX-1 changed its explanation text, and its sentences now say which kind
  of hard gate is active (the UOR handoff revisions of 2026-10-05 and 2026-10-10).
- The owner's UX comprehension check passed (54 of 54) and the wording was frozen, both on
  2026-10-17, before the release.
- No forecast-quality claim and no directional permission is accepted; both registries are empty.
- Releases between 2026-06-22 and this entry were not recorded in this file. They are recorded in
  `ops/release/releases.json` and `STATE.md`.

## 2026-06-22 - Wave 4D.2 Derivatives Intelligence Shadow Runtime

Changed:
- Added a default-OFF, strict `derivatives_intelligence` response block with separate core
  prediction and derivatives observation timestamps.
- Added bounded current-state public acquisition for Binance USD-M and OKX SWAP funding and
  open-interest evidence using raw-only LRU caches and fixed process-local lock stripes.
- Added provider availability summaries and comparability diagnostics without averaging or
  magnitude thresholds.
- Hardened non-funding quantity/notional parsing so negative values are invalid rather than
  silently accepted.
- Updated the source-controlled runtime fingerprint for the Wave 4D.2 release.

Notes:
- The block remains `SHADOW_ONLY` with zero decision influence and no persistence.
- The nine-second budget stops new calls; with a three-second request timeout, cold completion
  may approach twelve seconds.
- Future validation must retain both observation timestamps and must not backdate derivatives
  evidence to the core snapshot timestamp.

## 2026-06-15 - Wave 4B.3 Read-Only Calibration Metrics

Changed:
- Added a read-only calibration package with Brier score, multiclass log loss, top-label hit rate, reliability buckets, outcome distribution, directional-subset hit rate, and terminal-return diagnostics.
- Added sample gates for resolved prediction/outcome counts: `NO_SAMPLES`, `INSUFFICIENT_SAMPLE`, `WARMING_UP`, `PRELIMINARY_MEASURED`, and `MEASURED`.
- Added a SELECT-only repository method to join immutable `predictions` with immutable `prediction_outcomes` for calibration diagnostics.
- Added `scripts/calibration_report.py` for CLI-first JSON/text reports.
- Added offline tests for metrics, sample gates, version-mix warnings, repository filters, SELECT-only SQL, and CLI behavior.
- Added targeted review fix so calibration reporting uses direct Postgres first when `SUPABASE_DB_URL` exists, even if Supabase REST secrets also exist.
- Changed reliability-bucket `calibration_gap` to signed `avg_predicted_max_prob - empirical_hit_rate`.

Notes:
- Calibration diagnostics do not mutate predictions or outcomes and do not write back `calibration_status`, `reliability_status`, or `profitability_claim`.
- No API, UI, migration, quant/probability/score/gate/news, resolver-labeling, deploy, merge, or Hugging Face push was performed.

## 2026-06-15 - Wave 4B.2A GitHub Resolver Cron

Changed:
- Added `.github/workflows/resolve-outcomes.yml` to run the standalone outcome resolver hourly at minute 17 UTC and by manual dispatch.
- Added manual `limit` input and optional repository variable `RESOLVER_LIMIT`, defaulting to `50`.
- Required the GitHub repository secret `SUPABASE_DB_URL` and kept the workflow from printing it.
- Changed `scripts/resolve_outcomes.py` to exit non-zero when any prediction resolution fails.
- Added resolver tests for zero-failure and nonzero-failure script exit behavior.

Notes:
- This workflow runs only `scripts/resolve_outcomes.py`; it does not run migrations or deploy anything.
- The app remains analysis-only; no API, frontend, quant/probability/score/gate/news, calibration, or trading capability changes were made.

## 2026-06-15 - Wave 4B.2 Postgres Timeout Bind and Outcome Write Fix

Changed:
- Replaced bound `SET LOCAL statement_timeout = %s` calls with an internal integer literal in the shared Postgres wrapper and resolver due-fetch path.
- Changed `SupabasePersistenceRepository.save_prediction_outcome` to use a pool-free direct psycopg path with `ON CONFLICT (prediction_id) DO NOTHING`.
- Added sanitized phase-labelled error messages for Postgres due-fetch and outcome-write failures.
- Added regression tests proving `SET LOCAL` is executed without bind parameters and outcome writes do not depend on `psycopg_pool`.

Notes:
- Root cause: Supabase/Postgres accepted the verified due SELECT, but rejected bound parameters for `SET LOCAL statement_timeout` before the SELECT could run.
- No migrations, API, frontend, quant/probability/score/gate/news, calibration, deploy, merge, or Hugging Face push was performed.

## 2026-06-15 - Wave 4B.2 Direct Postgres Due-Fetch Wrapper Bugfix

Changed:
- Changed `SupabasePersistenceRepository.fetch_due_unresolved_predictions` to use a direct psycopg connection for operator due-fetch instead of the pooled `_run_db` wrapper.
- Kept the verified unresolved-row SQL and explicit `fetchall()` behavior.
- Kept tuple and mapping row conversion support.
- Added regression tests proving the due fetch does not depend on the pool wrapper and that `_run_db` still returns callback rows for other DB paths.

Notes:
- Root cause: the standalone psycopg query worked, but the repository due fetch still depended on the `psycopg_pool` wrapper; when that wrapper was unavailable/failing, due fetch never reached the verified SQL.
- No migrations, API, frontend, quant/probability/score/gate/news, calibration, deploy, merge, or Hugging Face push was performed.

## 2026-06-15 - Wave 4B.2 Postgres Due-Query Bugfix

Changed:
- Reworked `SupabasePersistenceRepository.fetch_due_unresolved_predictions` to use the verified `public.predictions` to `public.prediction_outcomes` unresolved-row join.
- Added mapping-row handling for Postgres due prediction rows while preserving tuple-row handling.
- Changed Postgres due-query failures from silent empty fallback to sanitized operator-visible failure.
- Added resolver CLI failure output so DB due-query errors return nonzero and do not print fake `due=0` success.
- Added tests for Postgres due-query SQL shape, tuple/mapping row conversion, and sanitized failure behavior.

Notes:
- No migrations, API, frontend, quant/probability/score/gate/news, calibration, deploy, merge, or Hugging Face push was performed.

## 2026-06-15 - Wave 4B.2 Resolver Operator Wiring Bugfix

Changed:
- Added a resolver-specific repository builder so `scripts/resolve_outcomes.py` prefers `SUPABASE_DB_URL` / direct Postgres when both direct DB and Supabase REST settings are present.
- Kept generic app persistence selection unchanged; runtime API can still prefer Supabase REST.
- Added safe resolver summary diagnostics: `repository=...`, `limit=...`, `due=...`, `resolved=...`, `skipped=...`, `failed=...`.
- Added tests for DB-first resolver selection, REST fallback, in-memory fallback, and sanitized output.

Notes:
- Root cause: the operator resolver used the generic app builder, which is REST-first and could query a different/empty path than the operator's direct Postgres due-query.
- No migrations, API, frontend, quant/probability/score/gate/news, calibration, deploy, merge, or Hugging Face push was performed.

## 2026-06-14 - Wave 4B.2 Outcome Resolver

Changed:
- Added idempotent `migrations/0004_prediction_outcomes.sql` for immutable prediction outcome rows.
- Added explicit `RESOLVER_VERSION`.
- Added due-prediction fetch and immutable outcome-save methods to in-memory, Supabase Postgres, and Supabase REST persistence adapters.
- Added standalone `scripts/resolve_outcomes.py` for offline no-lookahead outcome resolution.
- Added a stale-window overshoot guard so missing true horizon candles are skipped rather than mislabeled.
- Added tests for migration safety, due-query filtering, no-lookahead behavior, unfinished-horizon skip, UP/DOWN/TIMEOUT labeling, repository idempotency/immutability, REST/Postgres non-overwrite semantics, failure isolation, and API isolation.

Notes:
- Resolver never runs inside `/v1/analyze` and is not imported by `api/**`.
- Predictions are never updated, deleted, or relabeled.
- Bounded historical candle fetching is deferred; the resolver currently protects old predictions with the stale-window skip guard.
- No calibration metrics, UI, endpoint, response schema, quant/probability/score/gate/news, frontend, provider, auth, dependency, merge, deploy, or Hugging Face push was performed.
- `calibration_status` remains `DEFAULT_PHASE1A`, `reliability_status` remains `INSUFFICIENT_SAMPLE`, `profitability_claim` remains `false`, and `news_influence_frac` remains `0.0`.
- Migration was created but not run by Codex.

## 2026-06-14 - Wave 4B.1 Prediction Ledger Foundation

Changed:
- Added idempotent `migrations/0003_prediction_ledger.sql` for immutable prediction rows.
- Added explicit `MODEL_VERSION` and `METHODOLOGY_VERSION` constants.
- Added `save_prediction(row)` to in-memory, Supabase Postgres, and Supabase REST persistence adapters.
- Wired live analysis to enqueue a compact prediction ledger row through the existing best-effort background persistence path.
- Added tests for migration safety, repository idempotency/immutability, live ledger row content, non-live skip, missing-anchor skip, and persistence failure isolation.

Notes:
- No resolver, calibration metrics, UI, endpoint, response schema, quant/probability/score/gate/news, frontend, provider, auth, dependency, merge, deploy, or Hugging Face push was performed.
- Prediction rows are written only for live data with a valid closed-candle reference time and reference price.
- `calibration_status` remains `DEFAULT_PHASE1A`, `reliability_status` remains `INSUFFICIENT_SAMPLE`, `profitability_claim` remains `false`, and `news_influence_frac` remains `0.0`.
- Migration was created but not run by Codex.

## 2026-06-14 - Wave 4B0 Long-Timeframe Methodology Patch

Changed:
- Replaced sample-count-scaled realized volatility with per-bar log-return volatility.
- Changed three-state directional probability to use bounded volatility-normalized signal input.
- Made timeout volatility contribution timeframe-aware.
- Made tail CVaR breach threshold scale from the 4H baseline by timeframe duration.
- Marked monthly runs below 60 bars as `LOW_SAMPLE` while retaining the 24-bar minimum run threshold.
- Added golden tests for direction desaturation, probability invariant, short-timeframe stability, volatility duplication invariance, timeout, tail gate, and monthly low-sample sufficiency.

Notes:
- This is an R4 methodology patch and needs Claude review before merge/deploy.
- `calibration_status` remains `DEFAULT_PHASE1A`, `reliability_status` remains `INSUFFICIENT_SAMPLE`, and `profitability_claim` remains `false`.
- `news_influence_frac` remains `0.0`; no frontend, provider, auth, news, migration, dependency, deployment, or trading capability changes were made.

## 2026-06-14 - Wave 4A.2 Frontend Deploy Cache Bust

Changed:
- Added version query strings to `styles.css` and `app.js` references in `frontend/index.html`.
- Added harmless frontend build marker `UCPE_FRONTEND_BUILD = "wave4a2-cachebust"`.
- Strengthened frontend static tests to require versioned assets and restored card probability markers.
- Strengthened `scripts/manual_smoke.py` to fetch served `/` HTML, follow the served `app.js` URL including query string, and reject stale hidden-probability bundle text.

Notes:
- Root cause: live Hugging Face/browser/CDN was serving stale frontend assets after the card probability restore.
- Live verification after deploy should use hard refresh/incognito and confirm overview cards show `Up`, `Down`, and `Timeout`.
- No quant, probability, score, gates, features, news, config defaults, schemas, migrations, dependencies, merge, deploy, or Hugging Face push were performed.

## 2026-06-14 - Wave 4A.2 Restore Card Probability Display

Changed:
- Restored overview-card Up/Down/Timeout percentage rows from backend `frontend_display` values.
- Removed the qualitative replacement rows from Wave 4A.1.
- Kept the repeated per-card yellow explanatory note removed.
- Kept one global uncalibrated legend and preserved Detail percentages, Decision Brief, and Download JSON.

Notes:
- Frontend/display-layer correction only.
- No quant, probability, score, gates, features, news, config defaults, schemas, migrations, dependencies, merge, deploy, or Hugging Face push were performed.

## 2026-06-14 - Wave 4A.1 Frontend Honesty Declutter Hotfix

Changed:
- Removed the repeated per-card yellow Up/Down/Timeout explanatory note.
- Replaced precise overview-card Up/Down/Timeout percentages with qualitative uncalibrated card text.
- Kept full Up/Down/Timeout percentages in the structured Detail panel.
- Kept Download JSON and Decision Brief rendering intact.

Notes:
- Frontend/display-layer hotfix only.
- No quant, probability, score, gates, tail risk, volatility/trend, config defaults, or news logic changed.
- Deferred to later reviewed work: tanh gain saturation, timeout cap behavior, realized-volatility scaling, broad tail CVaR breach behavior, and score ceiling/collapse artifacts.
- No migrations, dependencies, deploy, merge, or Hugging Face push were performed.

## 2026-06-14 - Wave 4A Honesty and Decision Clarity

Changed:
- Added horizon-explicit timeframe labels such as `4H setup / ~24H horizon` to backend responses and frontend cards.
- Added persistent uncalibrated-heuristic copy and Up/Down/Timeout explanation in the main analysis UI.
- Added backend-built `decision_brief` with constrained actions: `NO_TRADE`, `WATCHLIST`, and `SPOT_WATCH`.
- Added structured Detail rendering for `decision_brief` and relabeled placeholder confidence as model readiness instead of true confidence.
- Added a frontend `Download JSON` button that exports the current in-memory analysis payload.
- Extended response/detail schemas and regression tests for the new presentation-only honesty fields.

Notes:
- No scoring, probability, gates, execution realism, global risk, or news-influence math changed.
- `news_influence_frac` remains `0.0`; news remains advisory-only.
- No migrations, dependencies, deploy, merge, or Hugging Face push were performed.

## 2026-06-06 - Blueprint v1.2.2 Phase 0 Artifact Extraction

Blueprint version: `v1.2.2`
schema_version: `TBD`
app_version: `TBD`

Phase: Phase 0 docs-only operating artifacts.

Added draft artifacts:
- `IMPLEMENTATION_SPEC.md`
- `IMPLEMENTATION_DECISIONS.md`
- `CLAUDE.md`
- `AGENTS.md`
- `.gitignore`
- `AI/00_PROJECT_RULES.md`
- `AI/01_BLUEPRINT_SUMMARY.md`
- `AI/02_ARCHITECTURE.md`
- `AI/03_CURRENT_STATE.md`
- `AI/04_TASK_BOARD.md`
- `AI/05_HANDOFF.md`
- `AI/06_TEST_COMMANDS.md`
- `AI/07_DECISION_LOG.md`
- `DEBUG_PACK_EXAMPLE.md`
- `DEPLOYMENT_CHECKLIST.md`
- `RELEASE_GATE.md`
- `ROLLBACK_PLAN.md`
- `DISASTER_RECOVERY_RUNBOOK.md`
- `CHANGELOG.md`

Notes:
- No app code was implemented.
- No deployment config, schema, CI, provider adapter, backend API, frontend implementation, dependency file, secret, or README update was created.
- Provider/API/news/macro/source details remain `TO_VERIFY`.
- `IMPLEMENTATION_SPEC.md`, `AI/01_BLUEPRINT_SUMMARY.md`, `AI/00_PROJECT_RULES.md`, and `RELEASE_GATE.md` need Claude final review before becoming canonical.

## 2026-06-06 - Phase 0 Claude Review Fix Pass

Changed:
- Replaced home-directory source references with filename-only source references in committed docs.
- Added `UNSUPPORTED_ASSET_CLASS` to `IMPLEMENTATION_SPEC.md`.
- Added `IMPLEMENTATION_DECISIONS.md` for Blueprint section 2.2 defaults.
- Restored the full Codex role wording in `AGENTS.md`.
- Added timeframe and metric-group summary to `AI/01_BLUEPRINT_SUMMARY.md`.
- Added `.gitignore` with `.DS_Store`.
- Updated `AI/03_CURRENT_STATE.md` and `AI/05_HANDOFF.md` with fix-pass verification.

Notes:
- No app code was implemented.
- `IMPLEMENTATION_SPEC.md` still carries R4 financial-safety content and remains flagged for Claude review.

## 2026-06-06 - Production Build Sprint 1

Blueprint version: `v1.2.2`
schema_version: `1.1-crypto-probability`
app_version: `0.1.0`

Added:
- FastAPI app factory, auth/session endpoints, health/status endpoints, analysis/detail/debug endpoints.
- Stable JSON Schemas and Pydantic response/request models.
- Public-only fixture-backed market-data boundary, symbol normalization, validation, and provider failover/quarantine state.
- Deterministic `DEFAULT_PHASE1A` quant baseline with invariant validation, hard gates, score stack, tail CVaR, and calibration/reliability labels.
- News contract stubs with `METRICS_ONLY` no-fetch behavior, `NEWS_ADDON` unavailable fallback, and no-op influence.
- Static cyberpunk frontend thin renderer.
- In-memory recent-run store, sanitized debug export, best-effort telemetry sink.
- Dockerfile for Hugging Face Docker Space target on port `7860`.
- Checkers for forbidden capability strings, secret-like assignments, full article bodies, and schema validation.
- Optional GitHub Actions CI workflow.

Verification:
- `PYTHONPATH=src python3 -m pytest`: PASS, 53 passed, 3 warnings.
- `ruff check src tests scripts`: PASS.
- Safety/schema/manual-smoke scripts: PASS.
- Local uvicorn/curl smoke: PASS after elevated local bind permission; `/healthcheck`, `/v1/system_status`, `METRICS_ONLY`, and `NEWS_ADDON` verified.

Notes:
- No deploy and no merge performed.
- Live Binance/OKX/news provider source details remain `TO_VERIFY`; runtime analysis uses deterministic fixture data in Sprint 1.
- WP2 auth/security, WP4 quant/financial logic, WP5 news authority, and WP8 Docker/deployment/checkers require Claude final review before merge/deploy.

## 2026-06-06 - Claude Final Review Fix Pass

Changed:
- Replaced the non-blueprint score disposition with `ELEVATED_RISK_AVOID`.
- Added deterministic guardrails so bad liquidity, tail breach, or excessive execution cost force non-constructive output.
- Moved probability, timeout, score, and risk-guard constants into visible `DEFAULT_PHASE1A` config.
- Added `.dockerignore` and expanded `.gitignore` for env/key/secret-like files.
- Added secure-cookie runtime setting with secure default.
- Added PBKDF2-HMAC-SHA256 access-code hashing with configurable iterations and salt.
- Marked Sprint 1 responses and frontend with `FIXTURE_DEMO` / non-live data labeling.
- Documented Sprint 1 limitations for H-primary/H-extended split simplification and incomplete full hard-gating.

Notes:
- No deploy and no merge performed.
- Sprint 2 first task is live public Binance/OKX adapters plus real `data_quality`.
- Claude re-review is required before merge/deploy.

## 2026-06-07 - Sprint 2 Live Public Market Data

Blueprint version: `v1.2.2`
schema_version: `1.1-crypto-probability`
app_version: `0.1.0`

Added:
- `docs/source_verification_matrix.md` with Binance/OKX spot public endpoint rows marked `VERIFIED_PUBLIC`.
- Env-driven live data config: `UCPE_DATA_MODE`, provider priority, timeout, retries, rate limit, candle cache TTL, cross-provider requirement, and live-smoke gate.
- Safe public HTTP client with host allow-list, bounded timeout/retries, local throttle, and typed provider errors.
- Binance and OKX public spot adapters for candles and books using keyless endpoints only.
- Provider selection layer with cross-provider coherence, single-source warning, `DATA_CONFLICT` fail-closed behavior, all-provider `UNAVAILABLE`, explicit fixture mode, and no silent live-to-fixture fallback.
- Analysis-service data-quality wiring and frontend data-source honesty banner.
- `scripts/live_smoke.py`, gated by `UCPE_LIVE_SMOKE_ENABLED=true`.
- Pytest socket guard blocking real network in unit tests.

Verification:
- Full pytest with socket guard: PASS, 76 passed, 3 warnings.
- Ruff: PASS after package fixes.

Notes:
- No deploy and no merge performed.
- No Binance/OKX API keys or private/authenticated exchange calls were added.
- Live smoke was not run because `UCPE_LIVE_SMOKE_ENABLED` was not enabled.
- Claude final review is required for provider integration, data honesty, no-network tests, HF env table, and release gate.

## 2026-06-07 - Sprint 2 Targeted Fix Pass

Blueprint version: `v1.2.2`
schema_version: `1.1-crypto-probability`
app_version: `0.1.0`

Changed:
- Renamed signed fields from `_frac` names to `primary_return`, `extended_return`, `alpha_signal`, `net_signal`, and `directional_edge`.
- Added down-market fixture and regression tests for negative signed fields, schema validation, and probability invariant.
- Added `scripts/make_access_hash.py` for PBKDF2-HMAC-SHA256 access-code hash generation with local `UCPE_ACCESS_CODE_SALT`.
- Added Binance/OKX candle fetch margin before closed-candle validation.
- Updated live smoke to test BTC and ETH in both `METRICS_ONLY` and `NEWS_ADDON`.
- Updated deployment docs, release gate, test commands, memory, current state, handoff, and decision log.

Verification:
- Full pytest: PASS, 80 passed, 3 warnings.
- Ruff: PASS.
- Safety/schema/manual smoke scripts: PASS.
- Live smoke with `UCPE_LIVE_SMOKE_ENABLED=true`: PASS for BTC/ETH in both modes, all `CROSS_PROVIDER`.

Notes:
- No deploy and no merge performed.
- No Binance/OKX API keys, private exchange calls, live news fetching, or trading capability were added.
- Claude re-review is required before merge/deploy.

## 2026-06-07 - Sprint 2 Final `_frac` Defect-Class Fix

Blueprint version: `v1.2.2`
schema_version: `1.1-crypto-probability`
app_version: `0.1.0`

Changed:
- Renamed unbounded magnitude fields from `realized_vol_frac`, `risk_pressure_frac`, and `cvar_loss_frac` to `realized_vol`, `risk_pressure`, and `cvar_loss`.
- Kept `_frac` sentinel validation strict and unchanged.
- Added high-volatility offline fixture coverage proving unbounded magnitudes can exceed `1.0` without schema failure.
- Added recursive full-response test that every emitted `_frac` field is numeric and within `[0,1]`.
- Extended live smoke to support `UCPE_LIVE_SMOKE_SYMBOLS`.
- Documented the systematic `_frac` field audit in `IMPLEMENTATION_DECISIONS.md`.

Notes:
- No deploy and no merge performed.
- No Binance/OKX API keys, private exchange calls, live news fetching, or trading capability were added.

## 2026-06-07 - Sprint 3 UI and 1M Timeframe Polish

Blueprint version: `v1.2.2`
schema_version: `1.1-crypto-probability`
app_version: `0.1.0`

Changed:
- Added `1M` monthly timeframe support with Binance `1M` and OKX `1Mutc` public candle mappings.
- Added timeframe-aware minimum history: `1M` requires `24` candles while sub-monthly timeframes keep the `200`-bar default.
- Updated live public adapter fetch limits to request the timeframe-specific minimum plus a small closed-candle margin.
- Replaced Single Analysis timeframe dropdown with six progressive timeframe cards: `15m`, `1H`, `4H`, `1D`, `1W`, and `1M`.
- Added red-to-grey signal heat styling and preserved the required `Signal heat — not risk` label.
- Replaced raw JSON as the primary detail experience with structured Overview, Probability, Risk/Gates, Market Data Quality, Provider State, Quant Signals, News Add-on, and collapsed Debug/Raw JSON sections.
- Added frontend static checks plus backend validation/API/quant tests for `1M`.

Notes:
- No deploy and no merge performed.
- No auth/security, Docker, provider HTTP client internals, scoring/gate/probability/news math, private exchange calls, live news fetching, or trading capability were added.

## 2026-06-07 - Deployed Frontend Polish Hotfix

Changed:
- Replaced continuous red/grey card heat styling with six discrete backend-score heat bands.
- Fixed Batch Analysis cards so Detail opens the same structured Detail Analysis renderer used by Single Analysis.
- Added a site-wide footer signature: `Copyright © 2026 by Kha`.
- Added frontend static tests for heat bands, batch detail wiring, collapsed raw JSON, no-recompute boundary, and signature visibility.

Notes:
- Frontend-only hotfix.
- No backend quant/scoring/gates/news/auth/deploy/provider logic was changed.
- No deploy or Hugging Face push was performed.

## 2026-06-07 - Wave 1 Supabase Persistence and Watchlist Foundation

Changed:
- Added optional Supabase Postgres persistence foundation with idempotent `migrations/0001_init.sql`.
- Added `scripts/apply_migrations.py` for local, URL-safe migration application.
- Added backend persistence repository layer with stateless in-memory fallback and Supabase adapter.
- Added best-effort compact persistence for analysis runs, timeframe results, and provider observations.
- Added `persistence_status` to debug-safe response data.
- Added session-gated watchlist backend endpoints and a frontend Watchlist tab with browser storage fallback.
- Added `psycopg[binary]>=3,<4` to backend requirements.
- Added tests for stateless analysis, persistence outage degradation, watchlist CRUD, migration safety, and frontend watchlist hooks.

Notes:
- No backend quant/scoring/gates/news math was changed.
- No provider adapter behavior, Binance/OKX keys, private exchange calls, live news fetching, or trading capability was added.
- No deploy or Hugging Face push was performed.

## 2026-06-07 - Wave 1 Targeted Persistence Fixes

Changed:
- Moved analysis persistence writes out of the HTTP response path.
- Added FastAPI background scheduling that submits compact persistence work to a bounded worker pool.
- Added Supabase repository circuit breaker with cooldown and fast skip while unavailable.
- Replaced connect-per-operation behavior with a small `psycopg_pool.ConnectionPool`.
- Added defensive persistence wrapper behavior for unexpected repository exceptions.
- Added tests for non-blocking analyze response, raising repository failure path, circuit breaker transitions, and degraded watchlist behavior.
- Updated requirements to `psycopg[binary,pool]>=3,<4`.

Notes:
- No quant/scoring/probability/gates/news math changed.
- No Binance/OKX provider logic, private exchange calls, live news fetching, or trading capability was added.
- No deploy, merge, or Hugging Face push was performed.

## 2026-06-07 - Wave 1.1 Stabilization Hotfix

Changed:
- Mapped OKX daily and weekly public candles to UTC intervals: `1Dutc` and `1Wutc`.
- Changed cross-provider coherence to compare the latest common closed candle bucket instead of each provider's latest row.
- Preserved the existing cross-provider tolerance while allowing explicit single public-provider live fallback when `UCPE_CROSS_PROVIDER_REQUIRED=false`.
- Added provider-state details for cross-provider state, disagreement basis, fallback flag, and fallback reason.
- Added a visible app-shell `Re-analyze` control with cooldown and last-refreshed timestamp.
- Added app-shell persistence status visibility and surfaced persistence status in Detail/System status.
- Clarified Dev Mode disabled/configuration UX without changing security semantics.
- Added regression tests for 1D/1W alignment, open-candle exclusion, optional/required cross-provider conflict behavior, refresh/static UI hooks, persistence status, and Dev Mode disabled copy.

Notes:
- Cross-provider tolerance was not loosened.
- Live mode still never falls back to fixture data.
- No quant/scoring/probability/gates/news math, private provider endpoints, secrets, deployment logic, or trading capability changed.
- No deploy, merge, or Hugging Face push was performed.

## 2026-06-08 - Wave 1.2 Supabase REST Runtime Hotfix

Changed:
- Added backend-only `SupabaseRestRepository` using Supabase PostgREST over HTTPS for Hugging Face runtime persistence.
- Runtime repository priority is now `SUPABASE_REST` when `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` exist, then `SUPABASE_POSTGRES` via `SUPABASE_DB_URL`, then `IN_MEMORY`.
- Kept direct Postgres support for local migrations/direct DB or non-Hugging-Face runtimes.
- Added REST persistence support for compact run, timeframe, provider-observation, recent-run, get-run, and watchlist methods.
- Added mocked `httpx` tests for REST writes, watchlist CRUD, circuit breaker failure, runtime selection priority, status diagnostics, and analysis continuing under REST outage.
- Updated deployment docs to clarify that Hugging Face should use REST secrets and that Postgres ports `5432`/`6543` may be blocked.

Notes:
- No quant/scoring/probability/gates/news math changed.
- No market-data provider behavior, private exchange calls, live news fetching, or trading capability was added.
- No Supabase values are exposed to frontend/status/debug; only secret names are documented.
- No deploy, merge, or Hugging Face push was performed.

## 2026-06-08 - Wave 2A Symbol Universe and Market Data v2

Changed:
- Added public symbol-universe resolution from Binance `exchangeInfo` and OKX `public/instruments` for spot USDT pairs.
- Relaxed static symbol normalization so valid `BASE/USDT`, `BASE-USDT`, and `BASEUSDT` aliases can be resolved by provider universe instead of a hardcoded base list.
- Expanded Binance public REST collection to include ticker and recent trades alongside existing klines/depth.
- Expanded OKX public REST collection to include ticker and recent trades alongside existing candles/books.
- Added compact provider resource observability: candles/depth/ticker/trades availability, latency, freshness, and warnings.
- Added advisory derived market metrics from real public data only: spread bps, mid price, depth imbalance, shallow slippage estimate, recent trade pressure, freshness, and cross-provider disagreement.
- Added `Market Data v2 / Provider Observability` to structured Detail Analysis.
- Added tests for symbol aliases/universe availability, provider-only fallback/blocking, unsupported symbols, universe cache, resource parsers, derived metrics, detail payload, and frontend render hooks.

Notes:
- Derived market metrics are formulaic metadata only and do not affect scoring, probability, gates, or news influence.
- No WebSocket, News Authority Engine, calibration, private/signed exchange endpoints, Binance/OKX API keys, deployment, or trading capability was added.
- No deploy, merge, or Hugging Face push was performed.

## 2026-06-08 - Wave 3A Advisory News Authority Foundation

Changed:
- Added metadata-only advisory news adapters for GDELT DOC 2.0, FRED macro observations, and optional NewsAPI.
- Added fixed host allow-list coverage for `api.gdeltproject.org`, `api.stlouisfed.org`, and `newsapi.org`.
- Added deterministic news item normalization, title/url hashing, conservative entity relevance, source authority scoring, freshness scoring, and simple clustering.
- Added `news_evidence`, provider status, macro observations, and `influence_mode=ADVISORY_DISPLAY_ONLY` to `NEWS_ADDON` responses.
- Kept `news_influence_frac=0.0`; advisory news does not change score, probability, gates, or disposition.
- Added `migrations/0002_news.sql` for compact news metadata persistence: `news_items`, `news_clusters`, and `news_evidence_links`.
- Extended persistence adapters with best-effort news metadata writes through existing non-blocking persistence path.
- Added `News Authority / Macro & Micro Context` to structured Detail Analysis.
- Added optional gated `scripts/news_live_smoke.py`; it skips unless `UCPE_NEWS_LIVE_SMOKE_ENABLED=true`.
- Added offline tests for provider normalization, provider failure, no-fetch `METRICS_ONLY`, advisory-only invariants, entity relevance, clustering, persistence rows, frontend rendering, and no secret/frontend exposure.

Notes:
- No full article text is stored, rendered, exported, scraped, or fetched from article URLs.
- GDELT requires no key. `FRED_API_KEY` and `NEWSAPI_KEY` are optional backend-only Hugging Face Secrets.
- No calibration, WebSocket, News Authority scoring influence, private exchange endpoints, exchange API keys, deployment, merge, or Hugging Face push was performed.

## 2026-06-08 - Wave 3A News Provider Hotfix

Changed:
- Added provider-level GDELT throttling with `UCPE_GDELT_MIN_INTERVAL_SECONDS=6` default.
- Added in-process advisory-news metadata cache with `UCPE_NEWS_CACHE_TTL_SECONDS=180` default.
- Added GDELT 429 diagnostics with `last_failure_http_status=429`, `last_failure_error_code=RATE_LIMITED`, retry/cooldown metadata, and cached-headline fallback when available.
- Added NewsAPI 401/429/400 diagnostics for invalid key, rate limit, and bad parameter cases without exposing keys or headers.
- Added sanitized provider-status fields for configured, healthy, status, item counts, macro observation counts, failure code/type/operation/time, retry, cache status, and latency.
- Updated gated news live smoke output to print sanitized provider statuses only.
- Added regression tests for GDELT cache/throttle/rate limit, NewsAPI invalid-key/rate-limit/unconfigured behavior, and FRED-OK mixed-provider degraded analysis.

Notes:
- `news_influence_frac` remains `0.0` and `influence_mode` remains `ADVISORY_DISPLAY_ONLY`.
- No scoring/probability/gates/disposition logic, full article body fetch/storage, scraping, trading capability, deploy, merge, or Hugging Face push was added.
