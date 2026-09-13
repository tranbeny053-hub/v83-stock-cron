# Section 5A evaluation — pre-registration of the evaluator

Written 2026-09-12, AFTER `T_close` (2026-09-12T04:00:00Z) but BEFORE any live read of the
holdout and BEFORE the evaluator existed. Governing contract: `V1_QUANT_CONTRACT.md` §5A,
which is unchanged and is not reinterpreted here. This document fixes the things §5A leaves
to implementation, so that they are fixed **before** anyone sees a number.

Standing: this document constrains the evaluator. It cannot widen §5A, cannot introduce a
margin, and cannot license any claim §5A withholds. Where the two disagree, §5A governs.

## 0. Why this document exists

The holdout is evaluated **exactly once**. A defective evaluator does not produce a wrong
answer that can be corrected — it consumes the holdout. §5A.9 forbids retuning against the
same holdout, so recovery would require a new candidate freeze, a new `T_freeze`, a new `T0`
and another 22 days of collection.

Every rule below exists to make the first execution the only execution needed.

## 1. Readiness and consumption are separate acts

The single most dangerous property of a one-look evaluation is that you cannot inspect the
evidence to check the tool without spending the look. This section removes that dilemma.

**READINESS mode** may be run any number of times against live data. It answers *is the
evidence adequate and is the pipeline sound* — never *did the candidate win*.

READINESS **may** compute and emit:

- Tier-1 pair counts and Tier-2 admitted pair counts, per timeframe and per cell
- Tier-2 rejection counts by cause: unresolved arm, `realized_label` disagreement
- `k_c` for `c` in `{1,2,4}` — usable window counts — and dropped-window counts
- missed-attempt counts; first and last `reference_close_utc`; the realised span
- the `realized_label` distribution and the four `quant_v2` feature diagnostics (§5A.10)
- provenance anomalies (see §4.3)
- an **attainability verdict** per timeframe: `ATTAINABLE` when `k_4 >= 5`, else
  `PASS_UNATTAINABLE`

READINESS may **never** compute or emit: any Brier value, any `d_i`, any window mean `d_bar`,
any `ECE`, any t-statistic, any sign-test count, any A/B/C verdict, or any
PASS / NOT PASS / FAIL determination.

**This prohibition is enforced structurally, not by comment.** In readiness mode the
paired-evidence projection **omits `p_up_frac`, `p_down_frac` and `p_timeout_frac`
entirely**. The probabilities are never loaded, so no score of any kind is computable from
what readiness holds in memory. A readiness run that could produce a Brier number is a bug by
construction, and a test asserts the projection's column set.

**Attainability may legitimately establish NOT PASS without consuming the look.** If
`k_4 < 5` for a timeframe, §5A.8 makes PASS arithmetically unreachable there. That conclusion
follows from the lattice and the sampling frame alone; it cannot depend on candidate
performance and cannot create a PASS. Learning it early is a saving, not a peek.

**CONSUMPTION mode** computes the §5A decision. It is the one look.

## 2. The freeze ordering — the property that makes readiness safe

Readiness is only safe if what readiness reveals cannot change the evaluator. The ordering is
therefore mandatory and is itself the safety mechanism:

1. The evaluator is built and proven on **synthetic fixtures with known answers only**.
2. Opus reviews the actual T2 diff.
3. The evaluator pin `ops/section_5a_evaluator_pin.json` is committed.
4. **Only then** may readiness run against live data.
5. Consumption re-verifies the pin before reading anything.
6. Any change to the evaluator **after** the first live readiness run resets the pin and
   requires explicit owner authorization that states what changed and why. The change is
   recorded in `STATE.md`. This makes retuning visible rather than merely discouraged.

The pin mirrors `oos/freeze_guard.py`: SHA-256 over canonical JSON of a sorted file list, then
per file a NUL-delimited path marker, the UTF-8 relative path, a NUL-delimited content marker
and the raw bytes; compared by exact equality against the committed pin, failing closed.

The pinned set is **declared explicitly** rather than derived by import closure, because the
evaluator's transitive closure would sweep in most of the application and churn on unrelated
edits. The declared set is exactly what can change the answer: the evaluator's own modules
plus the reused definitions `calibration/metrics.py`, `calibration/schemas.py` and
`utils/invariants.py`.

## 3. Consumption guards

- **G1 pin** — `ops/section_5a_evaluator_pin.json` must match exactly, or refuse.
- **G2 one-shot seal** — refuse if any prior consumption artifact exists, mirroring
  `r2/sealed.py::refuse_existing`. A second run is structurally impossible, not merely
  discouraged.
- **G3 confirmation token** — an explicit CLI token, mirroring the collector's
  `--confirm-write`. Absent or wrong, the run is inert.
- **G4 raw before parsed** — the raw query result is written to the consumption artifact
  **before any statistic is computed** (doctrine rule 1), so a parser defect can never be a
  reason to re-read the holdout.
- **G5 `T_close` has passed** — asserted against the contract instant, not the wall clock's
  convenience.

## 4. Operationalizing §5A against the actual schema

These mappings were surveyed at `d52e9ae` before the evaluator existed.

### 4.1 There is no persisted `arm` column

`arm` is encoded **only** in `prediction_id` as `{run_id}:{timeframe}:{arm}`
(`api/analysis_service.py::_prediction_id`). The paired read therefore discriminates arms by
the `prediction_id` suffix, exactly as the existing `fetch_oos_t0` query already does with
`right(prediction_id, 9) = ':BASELINE'` and `right(prediction_id, 10) = ':CANDIDATE'`.

### 4.2 Tier-1 is defined exactly as `fetch_oos_t0` already defines it

`T0` is already committed to the contract as the minimum over pairs qualifying under
`fetch_oos_t0`. The paired-evidence read **must** use that same qualification, or the
population analysed would differ from the population that fixed `T0`:

    same run_id, normalized_symbol, timeframe, reference_close_utc
    exactly two rows
    exactly one ':BASELINE'  with methodology_version = 'heuristic-v1-wave4b0'
    exactly one ':CANDIDATE' with methodology_version = 'distributional-v1'
    namespace predicate run_id ~ '^oosb-[0-9a-f]{32}$'

### 4.3 `prediction_origin` is a reported anomaly, not a filter

None of the four existing OOS queries filters on `prediction_origin`; the `oosb-` namespace is
the discriminator, and it is what defined `T0`. Adding an origin predicate now would silently
change the population. So the evaluator keeps the namespace predicate **and separately counts
and reports** any `oosb-` row whose `prediction_origin` is not `SCHEDULED_SHADOW_EVIDENCE`.
A non-zero count is a provenance anomaly reported prominently in both modes; it does not
alter the analysed set.

### 4.4 One definition of Brier, not two

Per-row Brier is extracted from the existing inline expression in
`calibration/metrics.py::compute_calibration_metrics` into a public per-row function that the
aggregate then calls. This guarantees a single definition rather than a second private copy
that could drift. The refactor must be behaviour-preserving and the existing calibration tests
must pass **unchanged**.

Brier is the existing three-class sum of squared errors against one-hot on **internally
normalized** probabilities, over `OUTCOME_LABELS = ("UP", "DOWN", "TIMEOUT")`.

### 4.5 ECE reuses the unfiltered enumeration

`ECE = sum over ALL pre-fixed bins b of (count_b / total) * |calibration_gap_b|`, over the
seven `RELIABILITY_BUCKETS`, taken from `calibration/metrics.py`, which already returns every
pre-fixed bucket **including empty ones**. An empty bin has `bucket_count = 0` and
`calibration_gap = None` and contributes exactly `0.0` — excluded by arithmetic, never by
rule. A non-empty bin with a `None` gap is impossible; if one occurs the evaluator raises
rather than skipping it.

`shadow_validation/metrics.py::baseline_diagnostics` is **forbidden**: its `MIN_CELL_COUNT`
of 30 is post-hoc survivor selection. A test asserts the evaluator does not reach it.

Buckets are assigned by the normalized probability of the **top predicted label**, and
`calibration_gap = avg_predicted_max_prob - empirical_hit_rate`, both as already defined.

### 4.6 No new dependency

`scipy` is not a product dependency and must not become one. The Student-t lower-tail CDF is
implemented via the regularized incomplete beta function, and the binomial tail exactly via
`math.comb`. Both are proven against published known values to at least 1e-9.

## 5. Statistical definitions, with every edge case fixed in advance

Let `d_i = Brier_candidate(i) - Brier_baseline(i)`, negative favouring the candidate. The unit
of analysis is the **window mean** `d_bar_w`. Windows are half-open `[start, end)`, assigned by
`reference_close_utc`, per the §5A.6 lattice; gap rows are discarded; multiple occasions in one
window are averaged.

**A1 — one-sided t-test**, on `{d_bar_w}` at coarsening `c`, `k` windows:

- `k < 2` → **A1 does not hold** (no dispersion estimate).
- `s` = sample standard deviation, `ddof = 1`. If `s == 0` or is not finite → **A1 does not
  hold**: the statistic is undefined and a strict guard may only err toward NOT PASS.
- `t = mean / (s / sqrt(k))`; `p = P(T_{k-1} <= t)` (lower tail, since the alternative is
  `mean < 0`). A1 holds iff `p <= 0.05`.
- A non-negative mean yields `p >= 0.5`, so ties and reversals fail, as required.

**A2 — one-sided sign test**, ties counting against the candidate:

- `n_neg = #{w : d_bar_w < 0}`. Ties (`d_bar_w == 0`) are **non-negative** and **remain in
  `k`**.
- `p = sum_{i=n_neg}^{k} C(k, i) * 2^-k`. A2 holds iff `p <= 0.05`.
- This reproduces §5A.8 exactly: `k=5, n_neg=5` gives `0.03125` (holds); `k=4, n_neg=4` gives
  `0.0625` (fails). Both are known-answer tests.

**A(t) holds iff A1 and A2 both hold at all three coarsenings `c` in `{1,2,4}`.**

**B1** — `ECE_candidate <= ECE_baseline` computed over **all Tier-2 admitted pairs for that
timeframe**, both symbols, **not** restricted to the window lattice. The contrast with B2 is
deliberate in §5A.7 and is preserved here.

**B2** — at `c = 1`, on the **same usable-window set as A**. Per window and arm, ECE over that
window's pairs on the same complete pre-fixed bins, weighted by within-window bin counts.
`n_worse = #{w : ECE_cand(w) >= ECE_base(w)}` (ties **worse**),
`n_better = #{w : ECE_cand(w) < ECE_base(w)}`. B2 holds iff `n_worse <= n_better`.

**B(t) holds iff B1 and B2.** B is a strict comparison, never a test: no margin exists.

**C(s,t)** — at `c = 1`, over symbol `s`'s own pairs on the same shared lattice. A window is
usable for `s` iff it holds at least one admitted pair for `s`.
`n_worse(s) = #{w : d_bar(s,w) >= 0}` (ties worse), `n_better(s) = #{w : d_bar(s,w) < 0}`.
`C(s,t)` holds iff `n_worse(s) <= n_better(s)`. Zero usable windows → **NOT COVERED**.

**States.** `PASS(t) = A(t) and B(t) and not FAIL(t)`. NOT PASS is anything short of A and B.
`AUTHORIZED(s,t) = PASS(t) and s in {BTC/USDT, ETH/USDT} and COVERED(s,t) and C(s,t)`.

## 6. FAIL is reported by observability, not by assumption

§5A.7 defines FAIL as an invariant breach or a failure to gate when evidence is thin. Some of
that is visible in the persisted rows and some is not. The evaluator therefore emits a
**FAIL-check table**, each row one of:

    OBSERVABLE_PASS | OBSERVABLE_BREACH | NOT_OBSERVABLE_FROM_PERSISTED_STATE

`FAIL(t)` is declared **only** on `OBSERVABLE_BREACH`. Every `NOT_OBSERVABLE` check is reported
prominently, so the absence of a detected breach is never read as proof there was none —
proven, reconstructed and inferred stay distinguished.

The probability-sum invariant is observable: every admitted row is checked with the existing
`utils/invariants.py::validate_probability_triplet` at its existing `1e-6` tolerance. Checks
that require runtime context absent from the ledger are marked `NOT_OBSERVABLE` rather than
approximated. **The evaluator must not invent a gate predicate**; where an existing predicate
can be reused it is reused, and where none exists the check is `NOT_OBSERVABLE`.

## 7. Reporting discipline

Per §5A.0: the `0.05` boundary is a **convention** and carries no probabilistic claim. Output
labels the quantity `boundary_statistic`, never "p-value as an error rate", and never uses
"statistically significant". No profitability claim, no per-asset superiority claim, no family
claim, and no claim beyond an authorized cell. Diagnostics are reported alongside **every**
outcome including NOT PASS and FAIL, and never gate anything.

A PASS is evidence **within the observed regime composition** and does not extrapolate.

## 8. Known frame limitation, recorded before the look

Collector cadence ran at roughly 13% of the scheduled rate, collapsing on 2026-08-27 from
21-40 runs/day to 2-9/day. An unrelated hourly workflow collapsed identically on the same
date, so the cause is GitHub Actions scheduled-workflow throttling, not the collector. The
`4H` cell drives `T_close` and has `k_4 = 5` exactly — no slack. Under §5A.5 heavy dropping is
evidence about the **frame**, not the candidate, and can never create a PASS. A NOT PASS on
attainability would be correct self-gating, and is recorded here as an anticipated and
acceptable outcome so that it cannot later be treated as a surprise requiring a remedy.

---

# Addendum, 2026-09-12 — four semantics pinned before implementation

Added after the §5A re-audit and before any of the implementation it governs. Each item below
resolves something §5A leaves undefined. **None of them is a new acceptance rule**, and each is
checked against one test: *can this choice ever make PASS easier to reach?* If it could, it
would be an amendment to the contract and would need the owner. Every resolution here is
neutral or strictly stricter, and §13 records that check per item.

## 9. `T_close` inclusion semantics

**Holdout membership is `T0 <= reference_close_utc < T_close`** — half-open, on
`reference_close_utc`, matching §5A.6's "rows are assigned by `reference_close_utc`" and the
half-open convention the lattice already uses. A row whose `reference_close_utc` is exactly
`T_close` is **excluded**.

This is load-bearing because the collector **kept running after `T_close`**: it fired at
05:55Z on 2026-09-12, nearly two hours past the close. Those rows are outside the holdout and
must not enter any statistic. Without an explicit rule they would silently enter B1, whose
population §5A.7 defines as "the whole holdout for that timeframe" rather than by the lattice.

For the lattice this rule is **already implied and changes nothing**: with
`j_max = floor((T_close - T0 - 2*E_t) / P_c)`, the last window ends at
`j_max*P_c + E_t <= T_close - E_t`, so no window ever reaches `T_close`. The rule therefore
binds only B1's wider population, which is exactly where it was missing.

**Resolution timing is deliberately NOT a membership criterion.** Membership is fixed by a
quantity known at prediction time. Bounding by `horizon_end_utc` or by resolution time instead
would let the analysed population depend on when the resolver happened to run — the sampling
frame would then be shaped by infrastructure timing rather than by the contract.

Because a row admitted under this rule may nonetheless have resolved after the declared close,
the evaluator **reports** the count of admitted pairs with `horizon_end_utc > T_close`, per
timeframe and per cell. It is a §5A.10-style diagnostic: reported always, gating never.

## 10. Zero and subset ECE behaviour

Both of these are review findings on already-committed code (see `0e4c8e8`), pinned here as
required behaviour rather than left to implementation taste.

- **`ece([])` raises.** It must never return `0.0`. On an empty input both arms would tie and
  B1 would read as "non-degradation satisfied" on no evidence at all.
- **`ece(rows)` raises when its population is a strict subset of `rows`.** `compute_calibration_metrics`
  silently drops rows its normalizer rejects, so the bucket counts can total fewer than the
  input. Scoring a one-shot decision over a silently narrowed population is a change of
  estimand. The evaluator asserts the totals match and raises on any shortfall.
- **A timeframe with zero Tier-2 admitted pairs is an explicit NOT PASS**, decided and reported
  *before* A or B is attempted, with the reason stated.

## 11. Immutable evidence-snapshot identity

The consumption run computes `evidence_snapshot_id` — SHA-256 over a canonical, deterministically
sorted serialization of the **raw** evidence rows, taken before any statistic touches them.
The same identity is computed in readiness mode.

It does three things:

1. **Binds a result to its evidence.** A recorded verdict is meaningless without knowing exactly
   which rows produced it; the id makes that checkable rather than asserted.
2. **Detects drift between readiness and consumption.** The collector is still running, so the
   evidence can change under us. A differing id between a readiness run and the consumption run
   is surfaced loudly.
3. **Makes recomputation possible without a second look** (see §12).

## 12. One-shot failure states

**The look is consumed the moment the holdout's probabilities are read** — not when a result is
successfully produced. A crash after reading has still spent it, and pretending otherwise would
be the exact self-deception §5A exists to prevent. The seal is therefore armed immediately after
the raw capture and **before** any statistic runs.

States, each recorded in the artifact:

    NOT_STARTED           no consumption has begun
    SEALED_RAW_CAPTURED   raw evidence captured and sealed; the look IS consumed
    COMPLETE              statistics computed and the result written
    SEALED_NO_RESULT      raw captured and sealed, but the statistics failed

`SEALED_NO_RESULT` is recoverable **without a second look**, and this is the whole point of
doctrine rule 1 ("a parser failure must never be a reason to repeat a consequential action").
The evaluator provides a recompute path that reads the immutable snapshot from disk, performs
**no database access whatsoever**, and may be run any number of times. Fixing a statistics
defect therefore costs a recomputation, never the holdout.

A second *consumption* run is refused unconditionally while any snapshot exists.

## 13. Invented-nothing check, per item

| Pinned item | Could it make PASS easier? |
|---|---|
| Holdout `[T0, T_close)` | No — strictly narrows the population by excluding post-close rows |
| Lattice unchanged by §9 | No — the last window already ends at or before `T_close - E_t` |
| `horizon_end > T_close` count | No — reported only, gates nothing |
| `ece([])` raises | No — removes an outcome where B1 held on no evidence |
| `ece` subset raises | No — removes a silently narrowed, unrepresentative population |
| Zero admitted → NOT PASS | No — that is the stricter outcome |
| Snapshot identity | No — records evidence; computes no statistic |
| Seal before statistics | No — makes consumption harder to repeat, never easier |
| Recompute from snapshot | No — same evidence, same rules, no new read |

## 14. Authorship and pending independent verification

The implementation of the paired read, admission, decision, diagnostics, runner and guards was
**authored by Claude Opus**, not by Codex, because Codex quota was exhausted and the owner chose
not to wait. The owner preserved review independence by **reordering** rather than dropping it:
Codex will **independently verify** this work — adversarially, not as a rubber stamp — before
any live read, any T3, and the final consolidated review.

Until that verification completes, the work carries the marker
**`CLAUDE_AUTHORED_PENDING_CODEX_INDEPENDENT_VERIFICATION`**, and it is not eligible for a live
readiness run, a pin that authorizes one, a push, or a merge.

---

# Addendum 2, 2026-09-12 — owner rulings closing verification findings F1, F2, F9

Codex returned **NOT_VERIFIED** on the first implementation (report at
`.work/805/5a-verification.md`). All 20 named mutations were caught, so the test suite was
sound; nine findings addressed things no test covered. Three were owner decisions rather than
repairs, and the owner has ruled. These rulings **supersede** the affected parts of the
original pre-registration.

## 15. F1 — `PASS` is reserved; the honest state is named

**SUPERSEDES §6.** The original resolution declared `FAIL(t)` only on `OBSERVABLE_BREACH` and
let A and B alone reach `PASS`. That treats *unknown* as *clean* and makes PASS easier to reach
than §5A.7 allows, which is precisely the class this document forbids.

**Ruling.** The contract token `PASS` is emitted **only** when A and B hold **and every** FAIL
predicate is **affirmatively established** clean. While any required predicate is unverified,
the terminal state is:

    A_AND_B_HELD_FAIL_UNVERIFIED      AUTHORIZED = false

It is not a lesser PASS. It authorizes nothing, and `AUTHORIZED(s,t)` continues to require the
contract `PASS`. The reason string names every unverified predicate.

**Consequence, stated plainly.** Three of the four FAIL predicates cannot be reconstructed from
the ledger today, so **with the current persisted data the best attainable outcome is
`A_AND_B_HELD_FAIL_UNVERIFIED` and no cell can be authorized.** That is the honest position, not
a defect: §5A's PASS was defined against a verifiability the ledger does not provide.

## 16. F2 — Postgres is the durable seal authority

**SUPERSEDES §3 G2.** The original seal checked the local filesystem. The evaluation workflow
runs on a **fresh GitHub runner per dispatch** and uploads its artifact only *after* the job, so
that seal is empty on every run and a second consumption simply succeeded. "Structurally
impossible" was true locally and false in the deployment.

**Ruling.** The durable cross-run authority is **Supabase/Postgres**. GitHub artifacts are
**secondary only** — convenience and audit trail, never the authority.

**Atomic durable capture.** `migrations/0009_section_5a_evaluation_seal.sql` (authored, **not
applied**) defines a singleton-constrained table whose row carries the raw snapshot. Claiming
the seal and capturing the evidence are therefore **one `INSERT ... ON CONFLICT DO NOTHING`**:
there is no interval in which the look is spent but unrecorded, and a race resolves in the
database rather than in application logic. An `UPDATE` trigger makes the captured evidence
immutable; only the state may advance. The REST fallback **refuses** to claim the seal, because
it cannot offer an atomic durable claim.

This also closes **F3**: the non-consequential reads now precede the probability read, so no
fallible call sits between consumption and the seal.

### Migration-ordering audit, as instructed

**The hazard is real.** `scripts/apply_migrations.py` has **no migration ledger**. It globs
every `*.sql`, sorts, and applies them **all** in one transaction, relying only on each file
being idempotent. There is no way to apply a subset — so authoring `0009` and running the
default path would **force the deliberately unapplied `0008_analysis_run_details.sql`**,
consuming a T4 that has never been authorized.

An additive `--only NAME` selection was added for exactly this reason. **Default behaviour is
unchanged**, and the script now prints what it will apply before applying it. Applying `0009`
must use `--only`; a test asserts that path never pulls in `0008`.

## 17. F9 — membership stays as pre-registered

**CONFIRMS §9, adds the limitation.** Membership remains `T0 <= reference_close_utc < T_close`,
unchanged for this tranche. It was fixed before any live read, and changing it now could move
the result either way — which is retuning, whatever the motive.

**The limitation, recorded rather than fixed.** This reading admits pairs whose
`horizon_end_utc` falls after `T_close`, and therefore can incorporate outcomes that were not
knowable at the close. A `horizon_end_utc <= T_close` population would exclude them. Both
readings are defensible from the contract text, which does not uniquely define B1's "whole
holdout". The count of admitted pairs resolving after the close is reported as a diagnostic, so
the exposure is visible in the output rather than buried. **No retrospective change is made.**

## 18. Repairs closing the remaining findings

- **F4** — `recompute_from_snapshot` now verifies the pin, recomputes the evidence digest from
  the stored rows and refuses a mismatch, and refuses when the recorded pin digest differs.
  "Same evidence, same rules" is enforced rather than asserted.
- **F5** — `evidence_snapshot_id` now covers the feature rows and the anomaly count, not just
  the scored rows. A separate `result_inputs_digest` binds the evidence to the pin digest, the
  contract instants and the timeframe set — kept separate so the evidence identity stays stable
  when the evaluator changes, which is what makes drift detectable by comparison.
- **F6** — the pin now includes `persistence/repository.py`, where the Tier-1 rule, the SQL, the
  projection and the origin handling live. Omitting it left the code that **selects every
  analysed row** outside the pin, which defeated the pin's purpose. Readiness now verifies the
  pin itself, so the CLI path enforces the freeze ordering rather than relying on the workflow.
- **F7** — dropped-window counts and the full per-cell diagnostic block are reported, and
  `missed_attempts` is reported as **`UNMEASURED`** with its basis rather than as `0`. No
  attempt ledger exists in the database; zero would have been a fabricated number.
- **F8** — `per_row_d` normalizes both arms before scoring. §5A.4 defines Brier on normalized
  probabilities and the ECE path normalizes internally, so scoring raw values treated a
  tolerance-admitted row inconsistently between the two statistics.

---

# Addendum 3, 2026-09-13 — repair of G1–G11 against the Codex-authored red tests

The failing tests were authored by Codex against the frozen implementation `2b31832` **before**
any repair, and pinned by SHA-256
`efe36649582ecbfe3a9835d159bd3ea1bd54befe4a55269dd165084d265f07df` in their own commit ahead of
the repair. They were not edited to obtain green. This addendum **supersedes §16's claim design**.

## 19. The one look is claimed before any probability is exposed

**SUPERSEDES the atomic claim-with-snapshot of §16.** That design put the evidence in the claim,
which required reading the probabilities first. Two concurrent consumers could therefore both
read before one lost the singleton insert (G3), and a serialization failure between read and
claim spent the look with no seal (G1, G9).

The order is now fixed as: every guard → a **durable, atomic CLAIM** carrying no evidence → the
probability read → capture of the snapshot and its digests. Only the claimant may read. A failure
after the claim leaves the look durably recorded as spent (`CAPTURE_FAILED`); a failure before it
spends nothing.

On Postgres the probability read is itself **capture-before-exposure**: one transaction locks the
seal, requires it `CLAIMED` and uncaptured, reads, writes the rows verbatim into `raw_evidence`,
and only then returns. Probabilities never leave the database except as rows already durably
captured. Migration 0009 enforces the lifecycle in the database — a `CLAIMED` row cannot carry
evidence, a captured state requires the raw capture, claim fields are immutable, captured
evidence is write-once, transitions are restricted, and the seal cannot be deleted.

## 20. One lossless canonical serializer

Every evidence digest and every seal column uses `utils/canonical_json.py`. It is total over the
types the driver returns, lossless in value (a `Decimal` is formatted exactly, never through
`normalize()`, whose 28-digit context would round), driver-independent (`Decimal("0.6")` and
`0.6` are one value), timezone-independent, and round-trip stable, so a snapshot read back from
disk digests exactly as captured. Rows and feature rows are hashed as multisets, so driver order
cannot change an identity.

## 21. Seal authority

A repository declares its seal authority. The consumption library refuses any declaration other
than `POSTGRES_DURABLE`. The production entrypoint additionally requires a **positive**
declaration, because `build_operator_repository` silently falls back to an in-memory repository
when no database is configured — a missing secret must refuse, not seal process-locally. Both the
CLI and the canonical serializer are inside the evaluator pin.

## 22. A contradiction in the pinned red tests, recorded rather than resolved

**G3.4 is unsatisfiable under its own test double, and remains RED.** The double's probability
read waits on a two-party `threading.Barrier` with a 5-second timeout. G3.1 requires at most one
read; G3.4 requires exactly one read **and** a successful consumption. A lone reader raises
`BrokenBarrierError` after 5.0 s — proven empirically before the repair, independent of any
design. Under the repair every G3.4 assertion that can hold does hold: one consumer is refused
before reading, exactly one read occurs, and the durable seal records the spent look. Only "one
success" is blocked, by the barrier. The test was not edited and was not gamed; amending it is for
the owner and Codex.
