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
