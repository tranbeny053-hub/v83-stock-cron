# Zero-drift skill gate and directional display — recommended defaults

Read-only design work, 2026-09-12. **No `distributional-v2` code, no freeze, no promotion.**
R2 evidence was read but not touched; no database or holdout was accessed.

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
