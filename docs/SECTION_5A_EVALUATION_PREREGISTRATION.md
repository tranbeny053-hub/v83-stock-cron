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

---

# Addendum 4, 2026-09-13 — owner rulings D1–D4 and the task-807 structural repairs

Codex task-807 returned NOT_VERIFIED with 40 of 40 mutations killed. The repair's mechanisms held;
fresh outside-in attacks found defects no earlier round reached, and three causal classes reached
the two-attempt repair bound. The owner ruled D1–D4. This addendum **supersedes §2's declared pin
set, §11's drift claim, and §21's authority policy**.

## 23. Scope is enforced at admission (V807-F1)

Scope was applied only at authorization, after A and B were computed, so an out-of-tranche asset
was pooled into both: losing BTC evidence alone was NOT_PASS, and adding favourable SOL/USDT
flipped A and B to true. That made PASS easier and is corrected, not reinterpreted: the tranche-1
scope (15m, 1H, 4H × BTC/USDT, ETH/USDT; §5A.1) has one definition and gates admission BEFORE any
statistic, attainability verdict, diagnostic or identity. Out-of-scope rows are counted globally
with a per-cell breakdown, and a row that reaches the decision out of scope fails closed.

## 24. The pin is derived mechanically (ruling D1; supersedes §2's declared set)

The pinned set is the full first-party import closure of the production entrypoint — module-level
and function-level imports, with every parent package `__init__` — plus declared non-imported
surfaces: `V1_QUANT_CONTRACT.md`, this document, migration 0009, the evaluation workflow, and
`requirements.txt`. A declared list was incomplete in three consecutive rounds; §2 had rejected
closure derivation expecting it to sweep in most of the application, and the measured closure is
bounded and does not reach the Hugging Face application surface. Because this document is now a
pinned surface, any later addendum changes the pin, which makes rule changes visible by
construction.

## 25. Fail closed unless authority and pin are positively verified (ruling D3; supersedes §21)

Consumption and seal recovery refuse an undeclared repository and have no switch to skip pin
verification. Every live CLI mode, readiness included, requires a positive durable Postgres
declaration. The red-test doubles now declare the durable authority, by owner amendment, so they
keep exercising claim-before-read under the fail-closed rule. Offline recomputation of a local
artifact keeps its pin flag: its rules are bound unconditionally to the RECORDED pin, which a
drifted evaluator cannot match.

## 26. Two identities with two purposes (ruling D4; corrects §11)

§11 claimed `evidence_snapshot_id` detects drift between readiness and consumption. **That claim
was false**: readiness hashes a probability-free projection and consumption hashes probabilities,
so the two never matched. It is withdrawn.

- `evidence_snapshot_id` authenticates everything a consumption captured. It is an integrity
  identity and is not comparable with anything readiness computes.
- `decision_population_id` is canonical and probability-free over exactly the population admission
  can admit — in scope and in the holdout — including outcome labels, and excluding post-close
  rows, other assets, feature rows and the anomaly count. Readiness and consumption compute it
  identically, so comparing them is a genuine drift check that cannot fire when no decision input
  changed.

## 27. The remaining structural repairs

- **V807-F3** — the entrypoint built `Settings()`, which ignores the environment, so with the
  database secret set it still produced an empty in-memory repository, and readiness would have
  reported zero evidence rather than refusing. Settings now come from the environment.
- **V807-R4** — the evaluation workflow gains `recompute`, since recovery from the durable seal
  needs the secret that exists only there.
- **V807-F6** — every tranche cell is materialized even when empty, per-scope counts are reported,
  and completeness is checked against a declared schema for populated and empty evidence in both
  modes.
- **V807-F8** — a statement-level trigger refuses `TRUNCATE`. Residual limit, stated: `DROP TABLE`
  or a superuser disabling triggers is outside what a table trigger can prevent.
- **V807-F10** — seal recovery cross-checks the seal's claimed contract instants.
- **V807-R2** — readiness raises `ReadinessRefused`, not a consumption error.

# Addendum 5, 2026-09-14 — the production entrypoint (owner rulings E1, E2=A, E3=A)

Codex task-808 returned NOT_VERIFIED. The evaluator's logic, the seal lifecycle, the mechanical
pin and the red-test amendment all held under attack; the production entrypoint did not. With
V807-F3 and V807-R4 before them, V808-F1, V808-R6 and V808-R5 are the second defeat of one
causal class: **a guarantee true in the library but false where the evaluation actually runs.**
The root cause is that the workflow was only ever checked as text, never executed the way GitHub
runs it, and the runtime it installed was unbound. This addendum **supersedes §24's claim that
pinning `requirements.txt` pins the runtime** and records the owner's rulings.

## 28. Dispatch inputs never reach shell source (V808-F1; ruling E1)

The workflow built its shell script as `--confirm '${{ inputs.confirm }}'`. GitHub substitutes an
expression into the script text before bash parses it, so a quote in the input ended the string
and the rest ran as commands — after the pin check had passed, in the step holding the database
secret. A dispatcher could have mutated the evaluator, re-pinned it, and consumed under rules
nobody reviewed.

Now no `${{ }}` appears in any `run:`. Inputs reach the shell only through `env:` and are expanded
in double quotes as `--option="$VALUE"`, where bash never re-parses them and a value beginning with
`-` stays bound to its option. The workflow's steps are EXECUTED in tests, as GitHub runs them,
against a stub interpreter with hostile inputs (quotes, `$( )`, backticks, `;`, newlines, globs),
and each must arrive as one inert argument. A negative control confirms the tests fail on the old
workflow, on an unquoted expansion, and on a piped step without pipefail.

## 29. A refusal can never show green (V808-R6; ruling E1)

The evaluation step piped into `tee` and declared no shell. GitHub runs an unspecified shell as
`bash -e`, without pipefail, so a refused or crashed readiness, consumption or recovery exited 0.
Every step now declares `shell: bash` (`bash --noprofile --norc -eo pipefail`). No step pipes. The
CLI writes its own `--report`: the outcome on success, and on refusal a record naming the refusal
while the process still exits non-zero. An unexpected error is reported by type only, because the
artifact is downloadable and a driver message can name a host.

## 30. Dispatch provenance and its residual (ruling E2=A)

Every live mode first ATTESTS the run, before any repository exists:

- `GITHUB_ACTIONS`, a manual `workflow_dispatch` of `.github/workflows/section-5a-evaluation.yml`
  on `refs/heads/main`;
- `expected_sha` — a required dispatch input the owner copies from the authorization — is a full
  lowercase commit SHA equal to the dispatched commit AND to the checked-out `HEAD`, with no
  tracked file modified;
- the runtime of §31.

A refusal names every failed check. The verified record is written into the durable claim, and
into the snapshot, so the run that spent the look is identified permanently: commit, workflow run
and attempt, runner image, interpreter, lock digest, installed versions and pin digest.

Enforcement is layered. The CLI attests every live mode. The durable Postgres repository refuses a
claim without a verified record before any statement executes, and migration 0009 refuses it in
SQL (`run_provenance JSONB NOT NULL`, a CHECK wrapped in `COALESCE(..., false)` because a CHECK
whose expression is NULL passes, and immutability with the other claim fields). Seal recovery
refuses a seal whose record does not verify, or whose snapshot names a different run. The library
verifies a record whenever one is given. As with the durable-authority declaration of §25,
declared test doubles may omit it, and a look taken that way can never be recovered.

**Residual, stated rather than hidden.** Every fact is observed by code in the dispatcher's own
tree. The single account with write access, or anything holding its credentials, can dispatch a
branch whose evaluator skips all of this, and the repository-level database secret is readable
from any branch that account pushes. These guards stop accidents, drift, mis-dispatch and the
public. They do not stop a compromised owner credential. An environment approval gate was
considered and rejected: on a one-account repository the approver is the dispatcher.

## 31. The exact runtime (ruling E3=A; supersedes §24's runtime claim)

`requirements.txt` specified ranges — `pydantic>=2,<3`, `psycopg[binary,pool]>=3,<4`, others
unconstrained — and the workflow, CI and local verification used Python 3.12, 3.11 and 3.13, so the
runtime that was verified was not the runtime that would execute. That matters concretely: G1 was
psycopg's NUMERIC adaptation, exactly what a minor release can change.

- **Interpreter:** CPython **3.13.14** exactly, the interpreter the verification ran under. The
  workflow installs that exact version on a pinned `ubuntu-24.04` image, and the attestation
  refuses any other interpreter.
- **Dependencies:** `ops/section_5a_evaluator_requirements.lock` pins the complete transitive set
  the evaluator and its in-job tests import — 19 distributions, the versions the full suite
  verified — with every published SHA-256 hash for each version (209, cross-checked against the
  package index). It is installed only with
  `pip install --require-hashes --no-deps --only-binary=:all:`. The attestation refuses a runtime
  whose installed versions differ from the lock, or that holds any distribution outside it except
  the installer (`pip`, `setuptools`, `wheel`).
- **Pin:** the lock replaces `requirements.txt` as the declared runtime surface, so any change to
  the runtime changes the pin digest. The interpreter version lives in the pinned closure.
- **Tests under that runtime, before exposure:** after attestation the job runs the evaluator's own
  suite under exactly this interpreter and lock, in a step with no secret. Only a green suite
  reaches the one step that receives the database secret.
- **Actions** are pinned to full commit SHAs, never to movable tags; the checkout keeps no
  credentials.

Residual: the runner image is refreshed by GitHub weekly, and the installer is not itself locked.
Neither can change an installed version without the attestation refusing.

## 32. Committed tests now pin what the campaign claimed (V808-R7)

Codex's "40 of 40 behavioural mutants killed" held only with tests it had just written. Against the
committed suite, seven survived, re-pinned so the pin could not be the killer:

- the naive-clock guard
- the existing-local-snapshot guard
- feature rows in `decision_population_id`
- per-scope counts replaced by global counts
- the closure skipping function-level imports
- exact ties counted for the candidate in B2 and in C

The last two contradict §5A.5, which counts ties as WORSE for both. The implementation was
correct, but nothing committed would have caught a regression. Codex's seven tests are adopted
unchanged, and future mutation campaigns credit kills by committed tests separately from kills by
tests written in the same round.

## 33. A correction to the record

The task-808 review reported the outcome resolver's workflow as sharing R6's false green. It does
not: its script begins with `set -euo pipefail`, which makes a failed resolver fail its pipeline
and its step. That was verified by executing the step against failing and succeeding stubs, not
asserted, and the resolver lane adds a regression test rather than a change.

# Addendum 6, 2026-09-14 — isolated start-up and code-origin attestation (rulings G1=A, G2)

Codex task-809 returned VERIFIED_WITH_FINDINGS: 15 of 15 mutants killed by committed tests, no
injection, no false green, no provenance bypass on a real path. Two findings remained.

- **V809-F1 (MEDIUM).** Opus found it independently, as O809-1, before Codex reported. Addendum 5
  §31 bound the runtime's package METADATA, not the code Python actually imports. A shadow
  `certifi.py` was imported under locked version numbers. A committed `scripts/platform.py` ran
  inside the evaluator while the pin still passed.
- **V809-F2 (LOW).** The workflow step reader silently dropped a workflow-level `env:`.

The owner ruled G1=A, strengthened, and G2. This addendum **narrows §31's claim to what is now
verified and supersedes §24's reach**: the pin binds the reviewed source, and this addendum binds
what actually loads.

## 34. Why the runtime identity was not the code identity

Four causes, each confirmed:
1. The CLI imported the evaluator, and with it psycopg, httpx and certifi, at module level, before
   anything was attested.
2. `python scripts/...` puts `scripts/` first on `sys.path`, and the workflow added
   `PYTHONPATH=src`, so either could shadow a standard-library or locked module.
3. The clean-tree check deliberately ignored untracked files.
4. Two copies of one distribution at one version collapsed into one inventory entry.

## 35. Isolated start-up: `python -I -S -B`

The evaluator — attestation and evaluation alike — only ever runs as `python -I -S -B`. It refuses
unless exactly those flags are in force:

- `-I` ignores `PYTHON*` variables, keeps the script directory off `sys.path` and disables user
  site-packages.
- `-S` is added because `-I` alone still runs `site`, which executes `.pth` files and
  `sitecustomize` BEFORE any evaluator code. Only with `-S` is refusing them a refusal rather than
  a detection after the fact.
- `-B` is added so nothing a run compiles can later stand in for a verified source.

The CLI imports ONLY the standard library at module level. The first import beyond it is
`crypto_probability_engine.runtime_isolation`, a standard-library-only module under the package's
empty `__init__`. A real isolated process proves that nothing else has loaded when it refuses.

## 36. The controlled import path and the pre-import audit

With the path still limited to the interpreter's own library, `runtime_isolation.enter` refuses
unless:

- **The start-up path** is exactly the interpreter's zip, stdlib and lib-dynload: no current
  directory, no script directory, no site-packages.
- **site-packages is exactly the lock:**
  - every locked distribution at its locked version;
  - nothing else except the installer (`pip`, `setuptools`, `wheel`);
  - no distribution present twice, whatever the version;
  - no `.pth`, no `sitecustomize` or `usercustomize`, no egg metadata.
- **Every file in site-packages is owned** by a distribution's RECORD, apart from CPython's own
  `README.txt`.
- **Every locked file matches its recorded SHA-256 and size.** Locked distributions carry no
  bytecode, because the workflow installs with `--no-compile`.
- **The checkout** holds:
  - no untracked or ignored `.py`, `.pyc`, `.pyo`, `.pyd`, `.so`, `.dylib` or `.pth` file;
  - no `__pycache__`;
  - no tracked compiled or path-configuration file;
  - nothing in `src/` except `crypto_probability_engine`.

Only then is `sys.path` set: the interpreter's library, then the verified site-packages, then
`src/`. First-party files come last, so they can never shadow a verified module.

## 37. Code-origin attestation, and what the record carries

Every module in `sys.modules` must come from one of:
- the interpreter's standard library (site-packages below the stdlib root does NOT count);
- a hash-verified locked file;
- a file of the reviewed pin, the entrypoint included.

Built-in and frozen modules are part of the interpreter itself. Any other origin, or no verifiable
origin, refuses. The check runs three times, the last immediately before the claim:
1. after the evaluator's imports;
2. after the repository is built;
3. after the reads that precede the claim, which may import driver code.

A refusal at any point spends nothing.

The run provenance gains two fields:
- `interpreter_flags`, which must equal the isolated flag set;
- `installed_files_sha256`, a digest of the exact bytes of every locked file.

Migration 0009's CHECK requires both. The in-job test and attestation steps use `-B`, and pip
uses `--no-compile`, so no step leaves bytecode in the checkout or site-packages. The separate
non-isolated pin step is removed: the isolated attestation verifies the pin.

## 38. The workflow reader refuses what it does not model (ruling G2)

`tests/workflows/_workflow_steps.py` now refuses a workflow-level `env:`, as it already refused
workflow-level `defaults:`. Both change every step. The change is identical in all three lanes
that carry the reader.

## 39. Residuals, stated rather than hidden

- **The standard library** is trusted as installed by actions/setup-python.
- **The installer** is inventoried, and must own its files, but is not hash-verified. It is never
  a permitted module origin.
- **`git`** is trusted to list tracked files.
- **A compromised owner credential** remains out of reach (§30).
- **The positive path** is proven locally with a toolcache-shaped interpreter. Its first proof on
  GitHub's runner image is the readiness dispatch, which is T4. An unexpected file in the image's
  site-packages refuses safely there, before any database access.

# Addendum 7, 2026-09-14 — the closed trust boundary (ruling J1=B)

Codex task-810 killed 5 of 5 mutants but returned NOT_VERIFIED. Four bypasses remained:

- **V810-F1 (CRITICAL).** Installed code was checked against the RECORD written beside it. A
  tampered file with a rewritten RECORD passed; Opus reproduced it.
- **V810-F2 (HIGH).** Files were hashed at audit and loaded later by path.
- **V810-F3 (HIGH).** A symlinked package directory escaped both audits; Opus reproduced it.
- **V810-F4 (HIGH).** Module origins were read from mutable attributes.

The root cause was two things. The checks authenticated mutable installed metadata instead of the
pinned hashes. And the job executed one piece of unverified code: the floating pip that
setup-python reinstalls from the package index, which the install step ran. The owner ruled J1=B.
This addendum **supersedes Addendum 6 §36's site-packages rule and §39's installer residual**.

## 40. The trusted computing base

Trusted, and nothing else:
1. the exact CPython 3.13.14 installed by the pinned `actions/setup-python`;
2. the pinned Actions (checkout, setup-python, upload-artifact, each a full commit SHA);
3. the pip wheel CPython itself bundles in `ensurepip/_bundled`.

Everything the evaluator imports beyond that base is authenticated, not inventoried.

## 41. No unverified code runs

- **The floating pip.** It is deleted from site-packages without ever being executed, and its
  presence, or any other installer's, is refused thereafter.
- **Installation.** CPython's bundled pip, running as `python -I -S -B`:
  1. downloads the locked wheels with `--require-hashes` into a wheelhouse outside the checkout;
  2. installs from those wheels alone, with `--no-index --no-compile --require-hashes --no-deps`.
- **After attestation.**
  - The in-job tests run authenticated and first-party code only, with `-s -B` and
    `PYTHONNOUSERSITE` and `PYTHONDONTWRITEBYTECODE` inherited by every subprocess.
  - The evaluation runs as `python -I -S -B` and re-audits everything itself.

## 42. What is authenticated, and against what

- **Wheels.** Each wheel's SHA-256 must be one the hash lock pins for that exact version: exactly one
  wheel per locked pin, nothing else in the wheelhouse, no symlink.
- **Installed importable bytes.** Every file an authenticated wheel declares must be installed as a
  regular file whose SHA-256 and size equal the digest recorded INSIDE that wheel's own RECORD.
  - `.data/purelib` and `.data/platlib` map to the site root.
  - Scripts, headers and data never enter site-packages.
  - The RECORD pip writes beside installed files is never an authority (V810-F1).
- **`installed_files_sha256`** is now a deterministic function of the authenticated wheels alone.
- **site-packages** holds exactly those files, pip's installer metadata (`INSTALLER`, `REQUESTED`,
  `RECORD`, `direct_url.json`) and CPython's `README.txt`. Refused:
  - any other file, directory or distribution;
  - any duplicate, symlink, `.pth`, `sitecustomize`, `usercustomize` or egg;
  - a split purelib/platlib layout.
- **The checkout** must equal its commit. Refused:
  - tracked modifications, tracked or untracked symlinks (V810-F3);
  - untracked or ignored code, bytecode caches;
  - tracked compiled or path files, and anything in `src/` but the package.

## 43. Residual trusted base, stated rather than hidden

- **The base itself.** Its integrity is assumed, not verified. So is the runner image beneath the
  interpreter: kernel, filesystem, bash, coreutils and git.
- **V810-F2 and F4.** No unverified code runs after attestation, so a file swapped between audit and
  load, or a module origin rewritten in memory, requires code from inside that base. They are
  residual, not closed. The same holds for bundled shared libraries and package data files, which
  are verified at attestation and are not modules.
- **The verify-at-load import hook** was considered and, by owner ruling, not adopted.
- **The owner credential.** Code supplied by a compromised owner credential remains out of reach
  (Addendum 5 §30).
- **The first real proof on GitHub's runner image** is the readiness dispatch, which is T4. An
  unexpected file there refuses safely, before any database access.

# Addendum 8, 2026-09-14 — the seal is locked down before it exists, and applied once (rulings K1=A, K2=A)

A read-only review of migration 0009, made before its first application, found three gaps:

- **F-0009-A (HIGH).** The seal table got neither row-level security nor revoked grants, unlike
  0005 and 0006. On Supabase, tables in `public` inherit grants for the PostgREST roles. An anon-key
  `INSERT` could therefore squat the singleton seal with forgeable provenance. The real consumption
  would then refuse, and the guards would keep the forged row. That is a denial of service against
  the one look.
- **F-0009-B (MEDIUM).** No approved route applied it: database access is GitHub Actions only, and
  no workflow ran a migration.
- **F-0009-C (MEDIUM).** There is no migration ledger, so `CREATE TABLE IF NOT EXISTS` would keep
  any stale table. The default migration runner would also drag in the unapplied 0008.

The owner ruled K1=A and K2=A. **No evaluation rule changes. The evaluator's behaviour is
unchanged.** What changes is the seal's DDL before its first application, and the one route that
applies it.

## 44. The seal is locked down (F-0009-A)

- **Schema-qualified.** Every object 0009 creates is qualified as `public.`: the table, both guard
  functions and both triggers. The repository already reads `public.section_5a_evaluation_seal`, so
  a search path can no longer split the two.
- **Row-level security** is enabled on the table, and **every privilege is revoked** from
  `PUBLIC, anon, authenticated, service_role`. Nothing is granted.
- **Row-level security is not forced.** The evaluator connects as the table's owner, and an owner is
  not restricted by row-level security that is not forced. The REST repository refuses every seal
  operation, so no API role needs any access.
- **The lock-down follows the table and both guards**, in the same file, so the table never exists
  without it.

## 45. One route applies it, once (F-0009-B, F-0009-C)

- **The route.** `.github/workflows/section-5a-apply-seal-migration.yml` is manual dispatch only,
  with two required inputs, `expected_sha` and `confirm` (exactly
  `APPLY-SECTION-5A-SEAL-MIGRATION-ONCE`). It shares the evaluation's concurrency group, so it
  never runs beside a readiness, consumption or recovery run.
- **The runtime is the evaluation's**, with its install step verbatim and the same pinned Actions,
  interpreter and image. `scripts/apply_section_5a_seal.py` runs as `python -I -S -B` and enters the
  isolated runtime before anything third-party can load.
- **The attestation is the evaluation's, bound to this workflow.**
  `provenance.attest(..., workflow=SEAL_MIGRATION_WORKFLOW)` verifies a manual dispatch of THIS
  workflow on `main`, at exactly `expected_sha`, on a clean checkout, under the pinned runtime and
  pin. Only the two workflows in `ATTESTABLE_WORKFLOWS` can be named.
- **A record from this route can never claim or recover the look.** Three separate checks accept
  only the evaluation workflow: `require_verified_provenance`, the durable authority, and 0009's own
  CHECK.
- **The apply script is bound by the reviewed commit, not by the evaluator pin.** The pin stays
  exactly what the evaluation executes. The script is added only to the set of files whose loaded
  modules count as verified.
- **One transaction.** It runs under `lock_timeout`, `statement_timeout` and an advisory lock:
  1. **Pre-checks**, read-only. Refuse unless no seal table, guard function or guard trigger exists
     in any schema. Record whether 0008's table exists.
  2. **The migration.** Execute exactly the pinned bytes of 0009, with no parameters.
  3. **Post-checks**, read-only. Refuse unless the table has exactly the reviewed columns, all three
     named CHECK constraints, one primary key and exactly both guard triggers, and unless:
     - row-level security is on and not forced;
     - neither PUBLIC nor any API role holds any privilege;
     - the applying role owns the table;
     - it holds zero rows;
     - 0008's table is unchanged.
  4. **Commit** only if everything passed. Any refusal or error rolls the whole transaction back,
     so nothing is applied.
- **One shot.** A second dispatch refuses at the pre-check, so the one-shot property is enforced by
  the database, not by memory.
- **Evidence.** Every raw result is captured before it is judged, and written to the uploaded
  report on success and on refusal. The report and logs never contain the database URL. An
  unexpected failure is reported by type only, because driver messages can name the host.
- **The default runner stays forbidden for 0009.** `scripts/apply_migrations.py` without `--only`
  would apply 0008 too.

## 46. Residuals, stated rather than hidden

- **0009 has never executed on a real Postgres.** No local database exists, and none was
  downloaded. A SQL error at application rolls the single transaction back and changes nothing.
  That failure costs a fresh T4 authorization after diagnosis, never a partial schema.
- **The role names are Supabase's.** If `anon`, `authenticated` or `service_role` did not exist,
  the REVOKE, or the post-check's privilege test, would error, and the transaction would roll back.
- **Outside this route.** A database owner or superuser can still alter the table or disable its
  triggers. The residual stated in §27 (V807-F8) stands.
- **The trusted base is Addendum 7's**, and the owner-credential residual is Addendum 5 §30's.

# Addendum 9, 2026-09-14 — the driver's dynamic helpers, and a correction (rulings L1=A strengthened, L1b, L2, L3)

**The owner-authorized, one-shot apply of 0009 refused before touching the database** (run
`34851608514`, main `3dc545c`).
- Install, attestation and the in-job tests all passed on GitHub's real image.
- The apply step then refused at the loaded-module attestation it makes after importing the driver
  and before connecting:

  > module _cython_3_2_4 has no verifiable origin; module cython_runtime has no verifiable origin

- The report shows no statement ran (`captured: {}`, `committed: false`). The authorization is
  consumed, and the run is never repeated.

**No evaluation rule changes.**

## 47. Cause, and a correction to the record

**The cause.**
- Importing the locked `psycopg` loads its Cython-compiled extensions, `psycopg_binary._psycopg` and
  `psycopg_binary.pq`, which are authenticated files.
- Cython's runtime then creates two modules in memory, with no spec, loader, file or path:
  - `_cython_3_2_4` holds exactly three C-level types;
  - `cython_runtime` is empty.
- The attestation refused every module without an origin.
- A scan of everything either route loads found these two as the only such modules. It covered the
  pinned first-party closure, `psycopg`, `psycopg_pool`, failed direct and pool connections, and
  both entrypoints. They reproduce on macOS too.

**The correction.** The J1=B end-to-end record said the origin checks passed with the driver loaded.
**That was wrong.** The evaluator imports the driver lazily, at its first connection, after both of
those checks. No test or run had attested loaded modules after the real driver was imported. So
consumption's check immediately before the claim would also have refused on the real runner: safely
before the claim, but blocking the look.

## 48. What the attestation now accepts

A module without an origin is accepted ONLY IF all of these hold:
1. its name is exactly `_cython_3_2_4` or `cython_runtime`;
2. both compiled extensions of the locked Postgres driver are loaded, each from an
   **authenticated locked file** with an extension-module suffix;
3. it is a plain module (`type(module) is types.ModuleType`) whose namespace has no spec, no loader,
   no `__file__` and no `__path__`, and whose `__name__` is the name it is loaded under;
4. its namespace matches an **exact pinned structural fingerprint**
   (`DYNAMIC_HELPER_FINGERPRINTS`).
   - The fingerprint is a SHA-256 over canonical JSON of the module's type and every namespace
     entry.
   - Strings are kept verbatim.
   - Each type is described by its metatype, name, qualified name, bases and the kind of each of its
     own attributes, so any Python function or class in it changes the fingerprint.

**Any other file-less module, or any other shape, refuses.** A refusal names the fingerprint it saw
and the pinned one.

**The fingerprints were computed with the real locked driver** on the pinned CPython 3.13.14, both
isolated and unisolated, and they agree. A driver rebuilt with another Cython changes these names or
fingerprints, and refuses until reviewed again.

## 49. The gap that hid it is closed (L1b)

- **Readiness now repeats the loaded-module attestation after its reads**, with the driver loaded.
  A readiness dispatch therefore rehearses consumption's pre-claim check faithfully.
- **Both entrypoints' `attest` mode now loads the locked driver WITHOUT connecting**, then attests
  loaded modules again, and records the fingerprints of the helpers it saw.
  - `scripts/evaluate_section_5a.py` loads `psycopg` and `psycopg_pool`.
  - `scripts/apply_section_5a_seal.py` loads the same two.
  - The attest step runs on the real runner BEFORE the test step and before any step that holds the
    secret, in both workflows. So the post-driver check is proven where it matters before a
    connection, or the claim, ever depends on it. Neither workflow file changes.
- **Why a step, not an in-job test.** The ruling proposed an in-job test. The repository bans every
  skipped test (`tests/test_no_silent_skips.py`), and a test that can run only inside the job would
  have to skip everywhere else. The attest step achieves the same purpose, one step earlier, and the
  ban stays intact.
- **Committed tests** (never skipped):
  - the accept/refuse matrix for synthetic helpers;
  - the real installed driver judged by the pinned rule in a fresh process, with exact equality on
    the pinned interpreter and locked build;
  - a driver import that opens no socket;
  - the new call orders of attest and readiness.

## 50. Residuals, stated rather than hidden

- **The fingerprints were computed on macOS arm64.** Linux x86_64 builds of the same driver release
  against the same CPython are expected to be identical, but this is **not yet proven on Linux**.
  The attest step proves or refutes it, before the tests and the secret. A mismatch stops that job
  there, and names both fingerprints.
- **The fingerprint is a structural cross-check, not a defence against code already running
  in-process.** Such code could build a matching module; that residual is Addendum 7 §43's. No
  unverified code runs after attestation.

## 51. Recovery repeats the same check (task-813 Finding 1; ruling M1=A)

- **The gap.** Codex's bounded check found one live path where the driver loads and a durable write
  can follow with no later loaded-module attestation. `recompute` reads the seal, which loads the
  driver, and may then advance it to COMPLETE.
- **The fix.** `runner.recompute_from_seal` takes the same `runtime_guard` consumption uses before
  its claim. It runs after the seal is read, and before any result is computed or the seal is
  advanced. The CLI passes `attest_loaded_modules`.
- **The paths now.** Every live path loads the driver only to be attested again before it acts:
  - attest attests after loading;
  - readiness attests after its reads;
  - consumption attests before its claim;
  - recovery attests before its result or write;
  - the seal migration attests before connecting.

# Addendum 10, 2026-09-14 — consumption names its readiness population (owner-authorized §2.6 safety change)

**Pre-registration §2.6 requires this addendum.** The evaluator has run live readiness once
(run `34863318042`, at main `4b0a522`). Any change after that resets the pin and needs explicit owner
authorization stating what changed and why. The owner authorized this change on 2026-09-14
(rulings N1=A, N2, N3).

## 52. Why

**The owner made the one look conditional on a guard.** The frozen consume path had to enforce that
the population about to be evaluated equals the readiness `decision_population_id`, BEFORE the
durable claim or any probability exposure.

**A read-only inspection of main `4b0a522` showed it did not:**
- the only pre-claim reads were the anomaly count and the feature diagnostics;
- the claim preceded the first paired-evidence read;
- the population identity was computed only in the result, and never compared.

§26 had already made `decision_population_id` a genuine drift check. This addendum makes that
check enforced, and places it before anything can be spent. The consume authorization was not
exercised, and nothing was dispatched.

## 53. What changed

- **Consumption takes the FULL readiness identity.**
  - The evaluation workflow gains the input `expected_population_id`, required for consume and
    passed only through `env:`.
  - The CLI gains `--expected-population-id`.
  - `runner.run_consumption` takes `expected_population_id`.
  - A **verified consumption**, one carrying run provenance, **must** name it. That is the only
    kind the durable Postgres authority and migration 0009's CHECK accept. Without it the run
    refuses before any read, and so does any value that is not exactly 64 lowercase hex characters.
- **Before the claim**, and before the loaded-module guard:
  1. the population is computed exactly as readiness computes it, from the probability-free
     projection `fetch_oos_paired_evidence(include_probabilities=False)`, by the same
     `decision_population_id`;
  2. a probability column in that projection refuses;
  3. **a mismatch raises `ReadinessPopulationMismatch` and STOPS UNCONSUMED**: nothing is claimed,
     no probability is read, and no artifact is written.
- **After the claim**, the population of the rows actually read is re-checked before any snapshot
  or statistic.
  - **Drift raises `ConsumedPopulationDrift`.**
  - The seal records `CAPTURE_FAILED`, and no statistic is computed.
  - Recovery refuses a seal without a snapshot, because recovering it is an owner decision.
- **The result states** `expected_decision_population_id` and `population_matches_readiness`.
- **No decision rule, statistic, threshold, lattice or admission rule changes.**
- **The pinned red tests are untouched and still pass.** Their doubles carry no provenance, so the
  library keeps accepting consumptions from undeclared test doubles without the identity, exactly as
  it accepts their absent provenance (ruling D3). The durable authority never does.

## 54. The sequence (ruling N3)

1. The change merges under its own T3.
2. A NEW, separately authorized readiness runs on the new pin.
3. Consumption may then run **only with that readiness run's `decision_population_id`**.

## 55. Residual, stated rather than hidden

- **A race after the claim can still spend the look.** A population change in the seconds between
  the pre-claim read and the post-claim read spends the look with no statistic computed
  (`CAPTURE_FAILED`, then an owner decision). The earlier readiness run showed 0 unresolved arms and
  0 label disagreements, and the collector is stopped.
- **The atomic alternative was not adopted.** It would make the claim, the read and the check one
  transaction (ruling N1=B), and would change the verified claim-before-read protocol.
