# V1 quant contract — skill gating, then horizon-specific modelling

Status: **evidence-complete, awaiting ONE owner scope decision before implementation.**
Evidence: production calibration query, 806 valid samples, run 2026-08-16.
Cohort: single `model_version=phase1a-wave4b0`, `methodology_version=heuristic-v1-wave4b0`,
no version mix, no invalid rows, no derivatives contamination.

---

## 1. The exact problem

The engine presents six timeframes as peers. The evidence says they are not peers: two
have real skill, three do not, and one is **worse than a coin flip**.

Brier here is the sum of three squared errors versus one-hot, meaned, so the
no-information baseline is **0.6667** (uniform 1/3) and uniform log loss is **1.0986**.

| Timeframe | n | Brier | vs uniform | log loss | directional | n dir | z vs 50% | significant | majority-class baseline | vs majority |
|---|---:|---:|---:|---:|---:|---:|---:|:--:|---:|---:|
| **15m** | 172 | 0.6868 | **+0.0201 worse** | 1.1357 | 0.4909 | 110 | −0.19 | **no** | 0.5000 | −0.009 |
| **1H** | 165 | 0.6206 | −0.0461 | 1.0299 | 0.6197 | 142 | 2.85 | **yes** | 0.5915 | +0.028 |
| **4H** | 172 | 0.5999 | −0.0668 | 1.0084 | 0.6755 | 151 | 4.31 | **yes** | 0.6291 | +0.046 |
| **1D** | 163 | 0.6541 | −0.0126 | 1.0829 | 0.5217 | 161 | 0.55 | **no** | 0.8199 | **−0.298** |
| **1W** | 134 | 0.6216 | −0.0451 | 1.0528 | 0.4627 | 134 | −0.86 | **no** | 0.5299 | −0.067 |
| **1M** | 0 | — | — | — | — | 0 | — | no data | — | — |
| ALL | 806 | 0.6373 | −0.0294 | 1.0624 | 0.5587 | 698 | 3.10 | yes | 0.5330 | +0.026 |

### Four findings that drive this contract

**F1 — 15m has negative skill.** It is worse than uniform on Brier *and* log loss, and its
directional rate is below 50%. Its `0.00–0.40` bucket (n=126) states 0.3850 and observes
0.2460: a **+0.1390 overconfidence gap** on the largest single bucket in the dataset. 15m
is the shortest, most-used card, and it is actively misleading.

**F2 — Only 1H and 4H have demonstrated skill.** 4H is strongest (z=4.31, p<0.0001) and is
the only timeframe clearly beating its own majority-class baseline (+4.6pp). 1D and 1W are
statistically indistinguishable from chance. The aggregate `MEASURED` gate at 806 samples
is therefore **misleading as a product signal** — it is carried by 1H and 4H.

**F3 — 1D's confidence ordering is inverted.** Bucket `0.40–0.50` (n=81) states 0.4400 and
observes 0.7037 (gap −0.2637). Bucket `0.50–0.60` (n=65) states 0.5340 and observes 0.3077
(gap **+0.2263**). Higher stated confidence produced *lower* observed accuracy. That is a
ranking failure, not mere miscalibration — the confidence signal is anti-informative on 1D.

**F4 — The probability range is compressed and the high-confidence regime is untested.**
No sample anywhere exceeds a 0.60 top probability; the highest bucket mean observed is
0.5495. Four of seven reliability buckets are empty across every timeframe. The shared
directional split is over-damped, and any behaviour gated on high confidence has **never
executed in production**.

`1D`'s majority-class baseline of 0.8199 reflects one downtrend regime and must not be
treated as a stable benchmark. The chance-level findings (F2) do not depend on it.

---

## 2. Answer to the v1 question

**Are the stated probabilities honest enough to ship as v1? No — not as currently
presented.** The probabilities are not fraudulent; the aggregate has genuine, if small,
skill (z=3.10). But presenting six timeframes as equals asserts skill that three of them
do not have and that one contradicts. The defect is in **presentation and gating**, not in
the probability arithmetic.

Supported by evidence: 1H and 4H directional signal.
Not supported: 15m as an actionable card; any 1D confidence ordering; any claim about 1M.

---

## 3. Sequencing decision: gate first, model second

These must ship as **two separate bounded changes, hard-gating first.**

Changing `methodology_version` resets the calibration cohort to `NO_SAMPLES` and forces
re-accumulation from zero. If horizon-specific modelling shipped first, it would destroy
the only evidence base the product has **while the product was still overclaiming**.
Gating first stops the overclaim immediately using evidence that already exists, and
preserves the cohort as the control against which new modelling is later measured.

---

## 4. Change A — skill gating (this contract; T2)

### Invariants (must not be weakened)
- Analysis-only. No trading, order, withdrawal, transfer, leverage, or execution capability.
- Backend JSON stays authoritative; the frontend renders and recomputes nothing.
- `p_up_frac + p_down_frac + p_timeout_frac = 1.0` per horizon — **unchanged**.
- Hard gates continue to outrank score and news.
- Derivatives stay default-off, shadow-only, 0.0 decision influence.
- No full article bodies; no secret exposure.
- **Probability values themselves are not altered by this change.** Gating changes
  disposition and labelling only.

### Required behaviour
1. A new **skill gate**, evaluated per timeframe, independent of the existing sample gate.
2. A timeframe whose directional performance is not demonstrably better than chance must
   not present a directional disposition as actionable; it is labelled as having no
   demonstrated skill.
3. The skill gate is a **hard gate** and therefore outranks score and news, consistent
   with existing gate seniority.
4. Skill status is computed from recorded outcomes, never hardcoded per timeframe — the
   thresholds are configuration, the verdict is data-derived, so it self-corrects as
   evidence accumulates.
5. `NO_SAMPLES` timeframes (1M today) report no skill verdict, not a false negative.
6. The aggregate gate must never be presented as a per-timeframe guarantee.

### Acceptance criteria
- Given the current production cohort, 15m/1D/1W resolve to no-demonstrated-skill and
  1H/4H resolve to skill-demonstrated.
- A timeframe with zero resolved outcomes resolves to insufficient-evidence, distinct from
  no-skill.
- The probability triplet returned for any input is **byte-identical** to today's output;
  only disposition/labelling fields change.
- Existing hard-gate precedence tests still pass unchanged.
- `./verify.sh` → `VERIFY=PASS` (754+ tests).

### Protected behaviour (must not change)
`quant/pipeline.py` probability computation · existing hard-gate composition semantics ·
auth · persistence · the calibration cohort filter · schema `response.schema.json`
backward compatibility for existing consumers.

### Allowed paths
`src/crypto_probability_engine/gates/` · `src/crypto_probability_engine/calibration/` ·
`src/crypto_probability_engine/api/` (response assembly and calibration endpoint only) ·
`src/crypto_probability_engine/config/defaults.py` (thresholds) · `schemas/` (additive
only) · `tests/` · `frontend/` (render new label only).
**Not** `quant/pipeline.py` internals, `migrations/`, `.github/`, `Dockerfile`.

### Deterministic tests required
- Skill verdict per timeframe from fixture outcome sets (skill / no-skill / insufficient).
- Probability triplet unchanged versus a frozen fixture — regression against silent drift.
- Skill gate outranks score and news.
- Invariant `p_up + p_down + p_timeout = 1.0` preserved.
- Zero-sample timeframe yields insufficient-evidence, not no-skill.
- Schema additive-only: existing consumers keep parsing.

### Backward compatibility
Additive fields only. No removal or retyping of any existing response field.

### Rollout
T2 local implementation → `./verify.sh` → Claude reviews the actual diff → T3 push + PR +
CI → separate T3 deploy decision. **No deploy is authorized by this contract.**

---

## 5. Change B — horizon-specific modelling (deferred, separate contract)

Justified by F4 and by the single shared `heuristic-v1-wave4b0` serving all six horizons
despite performance ranging 0.4909→0.6755. Not specified here. It requires a new
`methodology_version`, which resets calibration to `NO_SAMPLES`; the current 806-sample
cohort becomes its control. Must not begin until Change A has shipped and re-accumulated
evidence under gating.

**Entry clause satisfied.** Change A shipped (`9933615`, deployed) and re-accumulation under
gating is proven by the **21 post-Change-A resolved outcomes** from the partition run
(`831 = 806 frozen + 4 pre-A late + 21 post-A`, `post_a_inside_first806 = 0`). The clause is
qualitative and carries no numeric threshold; none is invented. The acceptance contract for the
first validation tranche is **section 5A**.

**The 806 cohort remains the historical control-of-record and is development-visible. It is
therefore NOT the clean out-of-sample set**, and no decision-grade evidence rests on a comparison
against it. A pooled non-inferiority criterion against that cohort was attempted, measured and
**rejected on evidence** (control-side `sigma^2*VIF/n0` exceeded the entire error budget at every
block width on the pre-registered grid, and the pooled margin proved unstable across the cohort's
own halves). It is not retuned.

---

## 5A. Change B tranche 1 — acceptance contract (ADOPTED)

Adopted by the owner. Governs the first validation tranche only. **`T_freeze` is deliberately
unset:** it is recorded here only when the exact candidate-freeze commit exists (§5A.2).

### 5A.0 Standing prohibitions

- **This is a pre-committed decision procedure, not a hypothesis test. It has no error rate.**
  The one-sided `0.05` boundary is a **convention** carrying no probabilistic claim.
- A PASS is **never** described as "statistically significant"; no p-value is reported as a
  probability or an error rate.
- **Pooled non-inferiority stays rejected.** No margin is defined anywhere in this contract.
- **Diagnostics never gate promotion** — `MEASURED >= 500`, `MIN_DIRECTIONAL_SAMPLES = 100`,
  `z = 1.96` and `LOW_BUCKET_SAMPLE` are reported only.
- **No family claim** ("Change B works") and **no claim beyond an authorized cell** (§5A.7).

### 5A.1 Scope

Tranche 1 is **`15m`, `1H`, `4H`** over **`BTC/USDT`** and **`ETH/USDT`** — six cells.
`1D`, `1W`, `1M` and every other asset stay on the current methodology, gated, until separately
validated.

    E_t (per-timeframe horizon, h_primary_bars = 6):  15m -> 90 min   1H -> 6 h   4H -> 24 h
    E_embargo (composition-wide longest horizon)   :  24 h

### 5A.2 `T_freeze` and `T0` — separate instants

    T_freeze = UTC commit timestamp of the commit freezing the candidate methodology_version.
               GOVERNS PURGE AND EMBARGO -- the candidate's information boundary.

               RECORDED. The candidate freeze commit exists:
                 commit                61e9796351b6a0bd224f441a7a2e3ef99dd4239c
                 T_freeze (UTC)        2026-08-20T11:35:56Z
                 methodology_version   distributional-v1
                 rooted at             origin/main 9b2eba5

               This commit is IMMUTABLE. It must not be cherry-picked, rebased, amended or
               recreated; its timestamp is the information boundary and any rewrite would move
               T_freeze after the fact.

    T0       = reference_close_utc of the FIRST construction-time-eligible paired-shadow
               occasion after activation (§5A.4). GOVERNS THE LATTICE ORIGIN AND T_close.
               OBSERVED, never chosen; committed to Git within the first sampling cycle.

               OBSERVED AND RECORDED. The T4 canary produced one qualifying pair:
                 T0                    2026-08-21T04:00:00Z
                 occasion              BTC/USDT, 15m, one oosb- run, BASELINE + CANDIDATE
                 T_freeze -> T0 gap    16h 24m 04s   (no leakage; the candidate was already frozen)

               T_close derives by formula, it is not chosen:
                 T_close = T0 + max_t(22 * E_t) = T0 + 528 h = T0 + 22 days
                         = 2026-09-12T04:00:00Z          (driven by 4H, E_t = 24 h)

               T0 IS IMMUTABLE ONCE SET. It is min(reference_close_utc) over qualifying pairs, and
               the collector refuses backfill, so every later occasion has a strictly greater
               reference_close_utc and the minimum cannot move. T_close may not be extended,
               shortened or re-declared.

`T_freeze <= T0`. Anchoring `T_close` to `T0` ensures activation delay cannot silently consume the
holdout. The `T0 - T_freeze` gap is recorded and reported: it creates **no leakage**, because the
candidate is already frozen, but a long delay is visibility-relevant. If no eligible occasion ever
occurs there is **no `T0` and no holdout** — a sampling-frame failure to fix, never a result.

**Purge and embargo, anchored at `T_freeze`:**

    purge   (per row, exact) : exclude from development any row with horizon_end_utc >= T_freeze
    embargo (blanket)        : additionally exclude predicted_at_utc >= T_freeze - E_embargo

`E_t` plays no part here; it governs analysis windows only.

### 5A.3 Provenance

Both arms write `SCHEDULED_SHADOW_EVIDENCE` with `run_id` matching `^oosb-[0-9a-f]{32}$` — disjoint
from the derivatives `^cadence-` namespace — and `prediction_id = f"{run_id}:{timeframe}:{arm}"`,
`arm` in `{BASELINE, CANDIDATE}`, both at **0.0 decision influence**. Pairing is constructed at
runtime by `oos/pair_context.py`: one shared `MarketSnapshot` object, skill state resolved once,
target derived once, one information cutoff, and candidate-only features admitted only on positive
evidence of being at or before that cutoff — after it, missing, unparseable or timezone-naive
**invalidate the pair**.

### 5A.4 Two tiers of pair eligibility

**Tier 1 — construction-time eligible** (knowable immediately; **defines `T0`**): both arms
persisted a row for the same `(normalized_symbol, timeframe, reference_close_utc)` within one
`oosb-` run, and the pair was not invalidated by cutoff enforcement.

**Tier 2 — analysis-time admitted** (knowable only at `T_close`; **defines every statistic**):
Tier 1, **plus** both arms resolved to an outcome, **plus** the two arms' `realized_label` agree.

The split is required: `T0` must be fixable prospectively, but outcome resolution is knowable only
later, so defining `T0` on Tier 2 would make `T_close` retrospective. Unpaired rows are discarded.
`Brier` is the existing three-class sum-of-squared-errors definition against one-hot on normalized
probabilities, unchanged.

### 5A.5 Sampling frame

**Scheduled-attempt cadence `period_t = E_t / 2`** — two scheduled attempts per window, so a single
missed run cannot empty one: **45 min / 3 h / 12 h** for `15m` / `1H` / `4H`, i.e. **42 scheduled
attempts per symbol per day**, 84 per day across the two symbols.

**Resource preflight — stated as what it is.** These are **scheduled prediction occasions and
`MarketSnapshot` constructions**, *not* a proven raw HTTP request count: actual upstream request
volume depends on provider selection, retries, multi-endpoint composition and caching, none of
which is measured here.

    2 symbols   84 prediction occasions/day  ->  168 prediction rows + 168 feature snapshots/day
                over 22 days: 3696 prediction rows + 3696 snapshots
                outcome resolution 7.0/hour against the hourly resolver's 50-per-run cap
                storage on the order of 15 MB against the 500 MB tier

**One `MarketSnapshot` is constructed per occasion and shared by both arms**, so snapshot
construction is per *occasion*, not per arm. The repository is public, so GitHub Actions minutes
are unlimited. The frame clears free-resource discipline.

**Empty-window rule.** A window is **usable** iff it holds at least one Tier-2 admitted pair. Empty
windows are dropped; survivors remain at least a gap apart, so the spacing guarantee is preserved.
**Dropped-window and missed-attempt counts are reported** — heavy dropping is evidence about the
*frame*, not the candidate. Dropping only reduces `k` and **can never create a PASS**.

**No backfill.** A missed occasion may **not** be re-run later to fill a window.

### 5A.6 Window lattice and scheduler semantics

For timeframe `t` and coarsening `c` in `{1, 2, 4}`, window width `W = E_t` **fixed**, gap
`G = c * E_t`:

    P_c      = (1 + c) * E_t
    window j = [ T0 + j*P_c ,  T0 + j*P_c + E_t )        HALF-OPEN: left-closed, right-open
    gap    j = [ T0 + j*P_c + E_t ,  T0 + (j+1)*P_c )    rows here are discarded
    j_max    = floor( ( T_close - T0 - 2*E_t ) / P_c )   the second E_t lets the last window resolve
    k_c      = j_max + 1                                  before empty-window dropping

**Rows are assigned by `reference_close_utc`**, which both arms share by construction, so assignment
is deterministic and identical across arms.

**Only the gap scales with `c`; the window does not.** Every coarsening therefore analyses the
**same unit** and varies only the *separation*, so **the estimand is invariant across
coarsenings** — the requirement for a robustness check to mean anything. A layout scaling both
would make the `c = 4` window mean a four-times-coarser aggregate, so the conjunction would span
three different estimands; that layout is rejected. `c = 1` is the **minimum sufficient** spacing:
with `G = E_t`, a row at a window's end has its horizon end exactly at the next window's start, so
horizon overlap is removed by construction. `c = 2` and `c = 4` are deliberate over-spacing.

**This removes one identified dependence channel; it does not prove independence.** Common latent
regime beyond `E_t`, shared model state and cross-symbol factors survive.

**Scheduler semantics.** The lattice is anchored to `T0` and is **independent of the scheduler**;
it is **never re-phased** to align with run times. Jitter needs no correction, because the bar's
`reference_close_utc` determines assignment. A missed attempt yields no pair and may leave a window
empty, which is dropped and counted. Multiple occasions inside one window are expected at
`E_t / 2` and are averaged into that window's mean.

Per-row statistic `d_i = Brier_candidate(i) - Brier_baseline(i)`, negative favouring the candidate.
**The unit of analysis is the window mean of `d`.**

### 5A.7 Requirements and cell-level authorization

**A — predictive robustness** (per timeframe, pooled over the two symbols). At each `c` in
`{1,2,4}`, on window means of `d`:

    A1  one-sided t-test     the MEAN of window means is < 0     (magnitude-sensitive)
    A2  one-sided sign test  the MEDIAN / majority is < 0        (distribution-free)

both at the one-sided `0.05` convention. **A holds only if A1 and A2 hold at ALL THREE
coarsenings.** The conjunction requires improvement to be **material in aggregate AND broadly
distributed across time**, excluding a candidate that wins in one regime and loses elsewhere.
**No margin exists to invent**: the null is "no better", so a merely-equal candidate does not pass.
**Ties count against the candidate.**

**B — calibration non-degradation** (per timeframe). `ECE` is computed over the **complete
pre-fixed** `RELIABILITY_BUCKETS` (`calibration/schemas.py`) taken from the **unfiltered**
`calibration/metrics.py` enumeration — never the `shadow_validation/metrics.py` view, whose
`MIN_CELL_COUNT` filter is post-hoc survivor selection. **Empty bins carry zero weight and are
excluded by arithmetic, never by rule.**

    ECE = sum over ALL pre-fixed bins b of ( count_b / total ) * | calibration_gap_b |

    B1  ECE_candidate <= ECE_baseline over the whole holdout for that timeframe
    B2  at c = 1, on the SAME usable-window set as A. Per window and arm, ECE is computed over that
        window's pairs on the same complete pre-fixed bins, weighted by within-window bin counts.
          n_worse  = #{ w : ECE_cand(w) >= ECE_base(w) }    ties count as WORSE
          n_better = #{ w : ECE_cand(w) <  ECE_base(w) }
        B2 holds iff n_worse <= n_better.

**B is a strict comparison, not a test**, because any non-degradation test needs a **margin** and
inventing one is forbidden; a strict guard can only err toward NOT PASS.

**C — per-cell degradation guard.** A pools symbols, so A alone could hide an asset that degrades.
For each symbol `s`, at `c = 1`, over that symbol's own pairs:

    n_worse(s)  = #{ usable windows w : d_bar(s,w) >= 0 }    ties count as WORSE
    n_better(s) = #{ usable windows w : d_bar(s,w) <  0 }
    C(s,t) holds iff n_worse(s) <= n_better(s).
    A symbol with zero usable windows in that timeframe is NOT COVERED.

Windows are time-based and shared, so per-symbol analysis reuses the same lattice; only the pair
subset changes.

**Authorization is per cell, because the asset universe is dynamic:**

    PASS(t)          requires  A(t) AND B(t) AND no FAIL(t)
    AUTHORIZED(s,t)  requires  PASS(t) AND s in {BTC/USDT, ETH/USDT}
                               AND s COVERED AND C(s,t)

**Every cell outside that set stays on the current methodology — including every asset not listed
and every asset first observed after `T0`.** A newly-appearing USDT asset inherits nothing. Under
cell-level authorization an under-sampled asset is simply not promoted, so under-sampling gains
nothing.

**States, per timeframe.** **FAIL** — an invariant breach (`p_up + p_down + p_timeout != 1.0` per
horizon; a hard gate overridden by score or news; sentiment-only action) or failure to gate when
evidence is thin. **NOT PASS** — anything short of A and B. **PASS** — A and B hold with no FAIL.

### 5A.8 Evidence adequacy — derived, not invented

The smallest attainable one-sided sign-test value on `k` windows is `2^-k`. Since
`2^-4 = 0.0625 > 0.05` and `2^-5 = 0.03125 <= 0.05`, **A2 can never reach the boundary with
`k <= 4`**; A1 needs `k >= 2` for a dispersion estimate. A must hold at all three coarsenings and
`k_4 <= k_2 <= k_1`, therefore:

    PASS is UNATTAINABLE unless k_4 >= 5.

**This is ATTAINABILITY ONLY — a consequence of the rule, not an adequacy threshold and not a
guarantee of sufficiency.** It is why no `>= 100`-style constant is required: thin evidence cannot
clear a boundary it cannot reach. Reaching `k_4 >= 5` establishes nothing on its own.

### 5A.9 One-look holdout and `T_close`

Evaluated **exactly once**, at `T_close`. **No interim looks** — `d`, `ECE`, per-symbol tallies and
window counts are not computed or inspected before `T_close`. A NOT PASS or FAIL **may not be
retuned against the same holdout**; a second attempt requires a **new candidate freeze, new
`T_freeze`, new `T0` and a new holdout**. `T_close` is fixed once `T0` is observed and **may not be
extended, shortened or re-declared thereafter**.

    multiplier = k + c(k-1) + 1  at k = 5, c = 4  =  5 + 16 + 1 = 22
    span_t = 22 * E_t     15m -> 33 h      1H -> 132 h      4H -> 528 h (22.0 d)
    T_close = T0 + max_t( 22 * E_t ) = T0 + 528 h = T0 + 22 days     (driven by 4H)

At that span the `4H` lattice yields `k_1 = 11`, `k_2 = 7`, `k_4 = 5`. **This is an attainability
floor, not an adequacy guarantee:** sparse traffic or dropped windows yield `k_4 < 5` and therefore
**NOT PASS**, which is correct self-gating.

### 5A.10 Mandatory pre-declared regime and state diagnostics

Declared here so the list cannot be chosen after seeing results. Reported per timeframe **and** per
cell, alongside **every** outcome including NOT PASS and FAIL:

- admitted pair count; `k_c` for `c` in `{1,2,4}`; **dropped-window count**; **missed-attempt count**
- `realized_label` distribution (`UP` / `DOWN` / `TIMEOUT`) — a `TIMEOUT`-heavy period changes what
  a Brier difference means
- **`regime`** distribution, **`realized_vol`** summary (median and IQR), **`trend_mtf`**
  distribution and **`volume_anomaly`** summary — the four persisted `quant_v2` features
- first and last `reference_close_utc`, and the realised span
- `T_freeze`, `T0`, and the `T0 - T_freeze` activation gap

**These never create or block a PASS.** Standing limitation: **a PASS is evidence WITHIN the
observed regime composition and does not extrapolate to unobserved regimes.**

### 5A.11 What a PASS licenses

A PASS authorizes **only the cells in `AUTHORIZED(s,t)`**. Promotion assigns the new
`methodology_version`, which resets calibration to `NO_SAMPLES` — so **promotion is not a
calibration claim**. **No profitability claim is licensed at any sample size, ever**, and **no
per-asset superiority claim**: C establishes only the absence of *detected* degradation.

### 5A.12 Recorded before `T0`

`T_freeze` (when it exists) · `T0` on observation · `T_close` · the six cells · `E_embargo` and
each `E_t` · the lattice formula and coarsening set · the `0.05` convention · A1/A2/B1/B2/C · both
eligibility tiers · the cadence · the no-backfill rule · the §5A.10 diagnostic list · the `oosb-`
namespace · and this contract's approval commit.

---

## 6. Known defect in the diagnostic query (not product code)

`sql/calibration_quality_readonly.sql` reports spurious values for **empty** scopes:
`log_loss` 27.6310 and `top_label_hit_rate` 0.0000 for 1M, and `observed_frequency`
0.0000 for empty buckets. Cause: `greatest(NULL, 1e-12)` returns `1e-12` in Postgres
(`GREATEST` ignores NULLs), so `-ln()` yields 27.631; and `avg(CASE WHEN … ELSE 0.0 END)`
counts the LEFT-JOINed NULL row as 0.0. Rows with `bucket_n = 0` or `valid_count = 0` must
be read as *no data*. Fix by filtering on `prediction_id IS NOT NULL`. Affects no timeframe
that has data, and no product code.

---

## 7. Owner scope decision required before implementation

Gating changes what users see. That is a product-value call, not a technical one.
See `.work/OWNER_ACTION.md`.
