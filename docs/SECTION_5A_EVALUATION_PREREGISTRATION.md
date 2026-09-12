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
