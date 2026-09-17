# Zero-drift skill gate and directional display — recommended defaults

Read-only design work, 2026-09-12. **No `distributional-v2` code, no freeze, no promotion.**
R2 evidence was read but not touched; no database or holdout was accessed.

> **Correction, 2026-09-17 (§7).** §1, §4 and §5 assume that `mu = 0` makes `p_up == p_down`. It
> does not. The empirical shape tables of distributional-v1 and distributional-v2 are skewed, so both
> models carry a fixed up/down split of about 48–54% up, set only by the band-to-scale ratio, the
> cell and (on 1H v2) the session. The recommendations stand, and §7 states what changes in the
> reasoning.

These are the two owner decisions R2 §7.2 batches as prerequisites for any future
`distributional-v2`. They are prerequisites *for* v2 rather than consequences *of* the §5A
result, so settling them now takes them off the critical path without committing to anything.

## 1. The problem, stated mechanically

R2 finding A6: **the directional skill gate cannot evaluate a `mu = 0` model.** Confirmed
against the code:

- `distributional-v1` and the recommended `distributional-v2` both set `mu = 0`, so
  `p_up == p_down` exactly.
- `calibration/metrics.py::top_prediction_label` uses `TOP_LABEL_TIE_ORDER` beginning at `UP`
  and replaces only on strict `>`. An exact tie therefore always names **UP**.
- So the observed "directional hit rate" equals the realized UP share among non-timeouts.

`calibration/skill.py::classify_directional_skill` then tests that rate against 0.5 with
`z = (2h - n)/sqrt(n)` at `z >= 1.96`, `n >= 100`. **Under a zero-drift model this measures
market drift, not model skill.** It is not merely uninformative — it is actively misleading,
because a drifting market would return `SKILL_DEMONSTRATED` for a model that makes no
directional claim at all, and a flat market would hard-gate a model that is behaving exactly
as designed.

This matters because `apply_skill_gate` is a **hard gate**: `NO_DEMONSTRATED_SKILL` forces
`NO_TRADE`, sets `score_ignored` and `news_ignored`, and forces
`ELEVATED_RISK_AVOID`.

## 2. Recommended default — a proper-score skill gate

**Skill is demonstrated when the model beats climatology on a strictly proper score.** This
keeps the gate's meaning ("is this model adding anything?") while removing its dependence on a
directional tilt the model does not claim to have.

| Element | Recommended default | Why this and not the alternative |
|---|---|---|
| Score | **Log loss AND Brier — both must clear** | Log loss is the strictly proper *local* score for the conditional probability, which is the North Star, and R2 §A9 already made it primary. But log loss is unbounded and its `EPS` clamp is exactly the pathology behind the known 27.631 diagnostic defect. Brier is bounded and also strictly proper. Requiring both makes the gate robust to either one's failure mode, mirroring §5A's A1∧A2 conjunction. |
| Reference forecast | **Trailing empirical climatology per `(normalized_symbol, timeframe)`** — the constant three-class base rate over the same evaluation window | R2 §A1 already used training-window climatology as the benchmark and found the deployed heuristic worse than it on every cell, so it is a validated and meaningful reference rather than a new invention. |
| Decision rule | **One-sided paired test on the per-row score difference `d_i = S_model(i) − S_clim(i)`, requiring the mean below zero**, at the existing `0.05` convention | Paired on the same rows, so it removes period difficulty. It reuses `oos/evaluation/stats_kernel.py` exactly as built for §5A — no new mathematics enters the product. |
| Sample floor | **100 resolved outcomes** — the same number as today | Continuity. But note the population changes (below). |
| Verdicts | **Unchanged**: `INSUFFICIENT_EVIDENCE`, `SKILL_DEMONSTRATED`, `NO_DEMONSTRATED_SKILL` | This is the important one. Keeping the enum means `apply_skill_gate`, hard-gate seniority, the detail view and the frontend are all **untouched**. Only the classifier changes. |
| Selection | **By `methodology_version`** — the directional classifier for `heuristic-v1-wave4b0`, the proper-score classifier for any zero-drift methodology | The two measure genuinely different things. A model with a directional tilt *should* be judged on direction; deleting that classifier while the heuristic is still deployed would be a regression. |

### The sample-floor subtlety, stated plainly
Today's `n` counts only **non-timeout** outcomes, because only those have a direction. A
proper-score `n` counts **all resolved outcomes**. On 15m, where R2 measured the realized
`TIMEOUT` base rate at 42%, that is roughly 1.7× more usable evidence for the same wall-clock
period. So keeping the floor at 100 makes the gate reachable *sooner* while making it
substantively *harder* — it now demands genuine probabilistic skill rather than a coin-flip
edge. That is the right direction of travel, but it is a real change in what the number means
and should not be adopted silently.

### Fail-closed behaviour is preserved exactly
`INSUFFICIENT_EVIDENCE` continues to activate the hard gate. A cell with no data stays
protected rather than guessed at.

## 3. The consequence the owner must weigh before promoting anything

**Promotion assigns a new `methodology_version`, which resets calibration to `NO_SAMPLES`.**
The skill gate then returns `INSUFFICIENT_EVIDENCE` for every cell, which activates the hard
gate. So immediately after any promotion — v1 or v2 — **the product will show `NO_TRADE` and
`ELEVATED_RISK_AVOID` on every affected cell until the new cohort reaches the sample floor.**

This is correct fail-closed behaviour, not a defect, and it is the same on the current gate
and the recommended one. It is stated here because it is the kind of thing that is obvious in
advance and alarming in production. The owner should decide beforehand whether that gated
window is acceptable, and how it is communicated.

## 4. Recommended default — directional display under a zero-drift model

Today the detail view emits `prob_up_pct` and `prob_down_pct`, and the frontend renders
"Directional edge", "Directional balance" and a "Direction context". Under `mu = 0` every one
of these is a fixed artefact of the constraint, not a measurement.

**Recommendation: stop presenting a directional split, and say why.**

Replace it with a single explicit statement that the methodology makes no directional claim,
citing the evidence: R2's X3 tested cross-asset, own-lag, hour-of-day and combined location
features and found AUC 0.48–0.51 — **no directional signal to express.**

The reasoning is the Quant North Star directly. A rendered "50% / 50%" reads as a computed
forecast that happened to land on even odds. It was not computed; it is what `mu = 0` means.
Showing it invites a confident misreading of a number the model never asserted, while the
genuine finding — that direction was tested for and not found — is both true and more useful.
"Distinguish proven from reconstructed from inferred" applies exactly here.

Two mechanical consequences follow:

- **Never derive a direction from the top-label tie order under a zero-drift methodology.**
  `TOP_LABEL_TIE_ORDER` naming `UP` is a determinism device for bucketing, not a directional
  claim, and it must not leak into the display or into `setup_direction`.
- What the model *does* claim stays, and becomes the headline: **P(move beyond the band)
  versus P(timeout)**. That is a real conditional statement, it is what the scale model
  actually estimates, and R2 shows it is where all the measured improvement lives.

## 5. A knock-on worth recording now, not discovering later

`ECE_top` buckets by the top label's probability and scores it against that label's hit rate.
Under a zero-drift model the top label is always `UP`, so `ECE_top` silently becomes "how well
calibrated is `p_up` as a forecast of UP among all outcomes" — a real statement, but not the
one a reader assumes, and degraded by the same tie mechanism that breaks the directional gate.

This matters beyond the display, because **§5A's criterion B is defined on exactly this
`ECE`**. Any future tranche validating a zero-drift candidate should re-examine whether
`ECE_top` is the right calibration measure for it, or whether a full three-class calibration
measure is needed. **This changes nothing about the current tranche** — §5A is fixed, `T_close`
has passed, and `distributional-v1` was validated under the rules as written.

## 6. Boundaries

Recommended defaults only. No code, no `distributional-v2`, no freeze, no promotion, and no
change to any gate in the product today. Adoption of §2 and §4 is an owner decision, and both
would land as ordinary reviewed T2 work under a future contract — not under §5A, which is
closed to amendment.

## 7. Correction, 2026-09-17: the shape tables are skewed, so the split is not 50/50

**What was wrong.** §1 says that under `mu = 0`, `p_up == p_down` exactly, and that the top label is
therefore always `UP` by tie order. `mu = 0` only removes a location term. The probabilities are
`p_down = F(-b/sigma)` and `p_up = 1 - F(b/sigma)`, where `F` is the cell's empirical CDF of
standardized six-bar returns. `F` is not symmetric about zero. So `p_up != p_down` whenever the band
`b` is positive, which is always.

- The product's own tests already relied on this: `test_epistemic_null_neutralizes_real_distributional_asymmetry`.
- What `mu = 0` does guarantee is sign invariance: flipping the sign of every input return changes
  nothing (`test_zero_location_has_no_return_sign_response`).

**The measured split.** The up share `p_up / (p_up + p_down)` is below, at four band-to-scale ratios
`z = b / sigma`. A test recomputes every figure from the committed tables
(`tests/quant/test_zero_drift_directional_split.py`).

| Model | Cell | Table | z=0.25 | z=0.5 | z=1.0 | z=2.0 |
|---|---|---|---:|---:|---:|---:|
| distributional-v2 | BTC/USDT 15m | one table | 0.5077 | 0.5075 | 0.5033 | 0.4794 |
| distributional-v2 | BTC/USDT 1H | session 00-07 UTC | 0.5109 | 0.5144 | 0.5188 | 0.5108 |
| distributional-v2 | BTC/USDT 1H | session 08-15 UTC | 0.5070 | 0.5047 | 0.4971 | 0.5171 |
| distributional-v2 | BTC/USDT 1H | session 16-23 UTC | 0.5255 | 0.5297 | 0.5382 | 0.5381 |
| distributional-v2 | BTC/USDT 4H | one table | 0.5221 | 0.5264 | 0.5303 | 0.5369 |
| distributional-v2 | ETH/USDT 15m | one table | 0.5094 | 0.5080 | 0.4975 | 0.4830 |
| distributional-v2 | ETH/USDT 1H | session 00-07 UTC | 0.5109 | 0.5147 | 0.5175 | 0.5174 |
| distributional-v2 | ETH/USDT 1H | session 08-15 UTC | 0.4876 | 0.4890 | 0.4861 | 0.4832 |
| distributional-v2 | ETH/USDT 1H | session 16-23 UTC | 0.5277 | 0.5343 | 0.5427 | 0.5382 |
| distributional-v2 | ETH/USDT 4H | one table | 0.5192 | 0.5212 | 0.5277 | 0.5275 |
| distributional-v1 | every symbol 15m | one table | 0.5091 | 0.5051 | 0.4879 | 0.4825 |
| distributional-v1 | every symbol 1H | one table | 0.5118 | 0.5158 | 0.5131 | 0.5121 |
| distributional-v1 | every symbol 4H | one table | 0.5205 | 0.5240 | 0.5384 | 0.5400 |

**What it means.**
- **The split is static.** It is a property of the historical sample the tables were fitted on, which
  drifted up over most of it. It responds to nothing in the current market except the ratio of the
  live band to the model's scale and, on 1H v2, the session. It is not a conditional directional
  forecast.
- **§1 still holds, by a different mechanism.** The top label is not a tie. It is whichever side the
  table's skew favours at that ratio, usually `UP`. At the four tabulated ratios, `DOWN` appears in
  exactly these cells:
  - 15m at z = 1.0 and 2.0 (for BTC under v2, only at 2.0);
  - ETH 1H in the 08-15 session, at every ratio;
  - BTC 1H in that session, at z = 1.0.

  A test pins that list. On a finer grid up to z = 4 the boundaries move. BTC 15m under v2 leans
  `DOWN` from z ≈ 1.09, and six further 1H and 4H tables lean `DOWN` only somewhere above z ≈ 2.4.
  The directional classifier therefore scores a fixed skew against realized
  direction. That measures market drift against a constant, not model skill, so the finding and the
  hard-gate hazard are unchanged.
- **§2 is unaffected.** The proper-score gate scores the whole triplet, skew included, against the
  base rate of the same rows. A static skew cannot beat that base rate: under a strictly proper
  score, the in-sample base rate is the best constant forecast. The prepared gate also counts
  differences within floating-point noise as none, so an exact echo of the base rate cannot pass
  either.
  - It is now prepared, dormant, as `calibration/proper_score_skill.py`, with a test reproducing
    finding A6: a static skew on an up-drifting market passes the directional gate and fails the
    proper-score gate.
- **§4 holds, more strongly.** The displayed split is not a visible 50/50 artefact. It is a
  plausible-looking 52/48 that no current market state drives, so it reads as a forecast even more
  easily. The recommendation (show P(move beyond the band) against P(timeout), and state that no
  directional claim is made) is unchanged. The mechanical rule generalizes: **never derive a
  direction from the static skew**, not only from the tie order.
- **§5 holds.** `ECE_top` buckets by whichever label the skew makes top. The knock-on for any future
  calibration criterion on a zero-location candidate is unchanged.
- **Nothing in the product changes.** The deployed default is `heuristic-v1-wave4b0`, whose
  direction comes from its own signal. Neither distributional methodology is selected for users.

