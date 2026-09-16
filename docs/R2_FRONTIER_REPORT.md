# R2 — Future Quant Frontier: report and recommended future candidate

Status: **research only — complete.** Opened and closed 2026-09-04 on branch
`research/r2-frontier`, while the `distributional-v1` holdout runs untouched
(T_close = 2026-09-12T04:00:00Z). Pre-registration: `docs/R2_FRONTIER_PREREGISTRATION.md`
(committed at `6ec047d` before any experiment ran). Evidence tables:
`docs/r2_evidence/REPORT_TABLES.md` (1,506 lines, every number below is traceable there),
`docs/r2_evidence/L1_SUMMARY.md`, and the sealed attestation
`docs/r2_evidence/SEALED_ATTESTATION.md`.

**This is not §5A evidence.** It licenses no promotion, no freeze, no deploy, no product
claim, and says nothing about the running holdout. It recommends a *future* candidate for a
*future* owner freeze decision, after the current holdout has been evaluated once at T_close.

## 1. What this means (owner summary)

- **The current candidate is sound but leaves the largest predictable ingredient on the
  table.** `distributional-v1` forecasts only *how volatile* the next six bars will be, using one
  exponentially-weighted average of past squared returns. It ignores that crypto volatility has a
  strong, stable daily and weekly rhythm, and it ignores the intrabar range and the longer-memory
  structure of volatility.
- **Adding those two things — a calendar volatility profile and a HAR-style variance
  regression — is the single most valuable next step on every timeframe.** It improved the
  primary proper score (log loss) out of sample on both symbols, on all three timeframes, at all
  four cost bands, in every calendar year and every volatility regime tested, and in every one of
  the eight walk-forward folds including the two sealed ones evaluated exactly once.
- **Direction is not predictable at this horizon.** Cross-asset lead–lag, own momentum and
  time-of-day all scored at chance (AUC ≈ 0.50); the candidate's zero-drift design is correct.
- **Nothing here changes what the running holdout will say.** The next decision is still the
  one-look §5A evaluation at T_close. Only after that should the owner consider freezing a
  `distributional-v2` candidate built from the recipe in §5, under a new pre-registered holdout.
- **Two product findings need an owner decision before any zero-drift successor ships**
  (§2, A6): the directional skill gate cannot measure a zero-drift model, and the user-facing
  directional split is 50/50 by construction under `distributional-v1` already.

Relative size of the gain, in log-loss skill against the uniform forecast (1.0986): on 15m the
candidate's skill rises from 3.7% to 4.9%, on 1H from 4.5% to 5.9%, on 4H from 15.1% to 15.8%
(sealed folds). Roughly a quarter to a third more skill on the two short timeframes; a small
but consistent gain on 4H, where volatility clustering already carried most of the value.

## 2. Architecture audit — the probability stack as it exists today

**Two methodologies coexist behind one selector** (`quant/pipeline.py`): the deployed
`heuristic-v1-wave4b0` and the frozen candidate `distributional-v1`. Both emit the same
triplet contract; both are scored by the same resolver label (six-bar terminal return against
a band). Everything downstream — score, gates, skill gate, detail view — consumes the triplet.

**A1. The deployed heuristic's timeout term is nearly constant.** `compute_timeout_probability`
scales per-bar realized volatility by a per-timeframe reference (0.02 for 15m, 0.035 for 1H,
0.06 for 4H). Actual per-bar volatility on the research corpus is about 0.0024 (15m), 0.0050
(1H) and 0.0123 (4H), so the volatility component contributes roughly 0.04–0.06 and the
timeout probability sits near 0.24–0.26 on every timeframe and in every regime. The realized
base rate of TIMEOUT at the production band is 42% (15m), 25% (1H) and 10% (4H). The heuristic
therefore under-states timeouts on 15m and over-states them on 4H, which is why Phase R found
it worse than a training-window climatology on every cell.

**A2. The heuristic's directional tilt is structurally compressed.** The six-bar momentum net
of cost is divided by `max(realized_vol, 0.02)`; the floor dominates on every timeframe, the
result is capped at ±2 and passed through `tanh(0.25·x)`, so the directional split can never
leave roughly 0.39–0.61 of the directional mass. This is contract finding F4 restated
mechanically, and X3 below shows there is no directional signal for a tilt to express anyway.

**A3. `distributional-v1` is a scale-only conditional model.** One EWMA of close-to-close
squared returns, a horizon exponent, a frozen unconditional empirical shape, and `mu = 0`. Its
strengths are real: the triplet is a difference of one CDF, so the invariant holds
analytically, and it beat the heuristic and climatology on every Phase R cell. Its blind spots
are exactly where this milestone found value: no intraday/weekly seasonality, one memory
length, close-to-close only (the intrabar range is discarded), and an unconditional shape.

**A4. The 15m decay of 0.90 is a seasonality artefact.** Once returns are deseasonalised, the
in-fold optimum moves to 0.97 on both 15m cells. The short memory was tracking the diurnal
volatility cycle rather than volatility persistence.

**A5. Train/serve skew from the 205-candle snapshot is real but immaterial.** The live
snapshot carries `min_history + 5 = 205` candles. At decay 0.99 the EWMA on that window differs
from the full-history EWMA by about 8% in sigma on average (1H, 4H), yet the log-loss effect is
at most 0.0025 and changes sign across timeframes (X0). On 15m (decay 0.90) the two are
identical. A separate consequence: any feature with a lookback above 205 bars — the weekly
realized variance at 15m needs 672 — cannot be served without widening the fetch, which is why
the recommendation is split into a deployable track and a longer-window track.

**A6. The directional skill gate cannot evaluate a `mu = 0` model.** With `p_up == p_down`
by construction, the product's top-label tie order always names `UP`, so the directional hit
rate under `distributional-v1` equals the realized UP share among non-timeouts — a measurement
of market drift, not of the model. The user-normalised split is 0.5/0.5 on every request. If
any zero-drift successor is promoted, the skill gate needs a proper-score definition (skill
versus climatology on log loss or Brier) and the directional display needs a product decision.
This is a finding for the owner, not something this milestone changed.

**A7. `regime_2state` is inert.** Its 0.05 per-bar threshold is never crossed on 15m, 1H or
4H (all 236,338 Phase R rows and all rows here are `NORMAL_VARIANCE`). It carries no
information into any consumer today.

**A8. What the label is, precisely.** `UP` iff terminal six-bar simple return exceeds the
band, `DOWN` iff below minus the band, otherwise `TIMEOUT`, equality inclusive. The band is
`2·taker_fee + spread/2`; with no order book it is exactly 0.002, and with a live BTC/ETH book
it is about 0.00205, so the research primary band is representative. The resolver takes the
first candle closing at or after the horizon end; on the gap-free research corpus that is the
same candle. One 1H bar and six 4H bars have non-standard durations (exchange maintenance) and
were kept.

**A9. Scoring.** The product's Brier (sum of squared errors, uniform 0.667) and `ECE_top` over
the fixed reliability buckets are reused unchanged via the product functions. Log loss is
added as the primary score because the North Star is the conditional probability itself and
log loss is the strictly proper local score for it (uniform 1.0986).

## 3. What was done (isolation, data, protocol)

- **Isolation.** Reads only the candle cache retained at T_freeze (public Binance klines,
  BTC/USDT and ETH/USDT × 15m/1H/4H). Rows admitted only if the six-bar horizon ends before
  `R_admit = 2026-08-12T00:00:00Z` (8.5 days before T_freeze; T0 of the holdout is
  2026-08-21T04:00:00Z, so no admitted outcome overlaps any holdout instant). No database, no
  network, no holdout or outcome inspection, no collector, no product code change; all working
  files under the gitignored `.work/research2/`. `./verify.sh` on the untouched tree:
  `VERIFY=PASS ruff ok | 1132 passed | schemas+smoke ok | scanners 3/3 | 6ec047d`.
- **Corpus.** 69,244 rows per 15m cell (2024-08-20 → 2026-08-11), 34,807 per 1H cell
  (2022-08-22 → 2026-08-11), 13,059 per 4H cell (2020-08-25 → 2026-08-10). TIMEOUT base rate at
  the 0.002 band: 42% / 25% / 10% (BTC) — the label mix differs sharply by timeframe.
- **Protocol.** Eight expanding-origin walk-forward folds per timeframe, shared by both
  symbols, purged (training horizon ends before the split) and embargoed (six bars). DEV = folds
  1–6 for all selection; SEALED = folds 7–8, evaluated once for an attested shortlist of three
  arms. Sealed spans: 15m 2026-03-04 → 2026-08-11; 1H 2025-09-23 → 2026-08-11; 4H
  2025-04-14 → 2026-08-11.
- **Scores.** Log loss (primary, strictly proper), three-class Brier (product/§5A
  definition), `ECE_top` computed by the product's own calibration function, decile reliability
  of `p_timeout`. Paired per-fold differences against the reference `B3Dev` — the Phase R
  method refit in-fold (decay, exponent and empirical shape chosen on training rows only).
- **Adoption rule (DEV).** Log-loss improvement in ≥ 5 of 6 folds, fold-mean t ≤ −2, no
  symbol's Brier worse by > 0.002, `ECE_top` not worse by > 0.01. **Recommendation rule
  (SEALED).** Log loss and Brier both improve in both sealed folds, `ECE_top` not worse by
  > 0.01. Both are ranking conventions with no error-rate claim.
- **Self-tests** (all green before every run): exact resolver label boundaries; exact
  purge/embargo counts; a leakage guard that must *discriminate* (memorising probe fails with
  guards, succeeds without); feature causality under future perturbation; cross-asset alignment
  that cannot see a later candle; the EWMA identical to the product function on the exact
  205-candle slice; the reference arm identical to the Phase R implementation within 1e-9; the
  sealed guard refusing without attestation. Every arm's `predict` is called with targets
  replaced by NaN to prove it never reads them.

## 4. Level-1 results — one component at a time against B3Dev (DEV folds, log loss)

Δ = pooled log-loss difference versus B3Dev (negative is better); t over six folds; "neg" =
folds improved; ✓ = adopted under the rule. Uniform log loss is 1.0986.

| Component | 15m Δ (t, neg) | 1H Δ (t, neg) | 4H Δ (t, neg) |
|---|---|---|---|
| **X0** 205-candle window, refit (`B3Dev_w205`) | +0.0000 (+0.2, 3) | +0.0002 (+0.2, 3) | −0.0002 (−0.3, 3) |
| **X1** range-based EWMA, Parkinson (`S2_park`) | −0.0039 (−5.9, 6) ✓ | −0.0025 (−1.9, 4) | +0.0006 (+1.1, 2) |
| **X1** HAR log-variance regression (`S3_har`) | −0.0063 (−6.8, 6) ✓ | −0.0089 (−4.2, 6) ✓ | −0.0010 (−1.4, 4) |
| **X1** calendar seasonality (`S4_season`) | −0.0057 (−9.9, 6) ✓ | −0.0107 (−5.7, 6) ✓ | −0.0027 (−3.5, 6) ✓ |
| **X1** HAR + seasonality (`S6_har_season`) | **−0.0091 (−8.7, 6) ✓** | **−0.0138 (−4.0, 6) ✓** | **−0.0050 (−3.9, 6) ✓** |
| **X1** direct six-bar EWMA (`S5_direct6`) | +0.0164 (+6.0, 0) | +0.0005 (+0.5, 1) | +0.0014 (+2.3, 2) |
| **X2** Student-t shape (`G2_t`) | +0.0000 | −0.0009 (−1.3, 4) | −0.0024 (−0.9, 2) |
| **X2** regime-conditional shape (`G3_regime`) | −0.0015 (−3.4, 5) ✓ | +0.0004 | +0.0010 |
| **X2** session-conditional shape (`G4_session`) | −0.0017 (−4.2, 6) ✓ | −0.0020 (−2.3, 5) ✓ | +0.0004 |
| **X2** 1001-knot shape (`G5_emp1001`) | +0.0000 | +0.0000 | +0.0000 |
| **X3** location: cross-asset / own lags / hour / all | −0.0001 … +0.0005, AUC 0.50 | +0.0002 … +0.0009, AUC 0.48–0.51 | −0.0000 … +0.0006, AUC 0.50 |
| **X4** multinomial logistic on the same features (`D1`) | −0.0054 (−2.8, 5) ✓ | −0.0099 (−3.3, 6) ✓ | +0.0029 (+0.8, 3) |
| **X4** gradient boosting upper bound (`D2_hgb`) | −0.0011 (−0.4, 4) | −0.0042 (−2.3, 5) ✓ | +0.0065 (+1.8, 2) |
| **X5** temperature scaling (`C1_temp`) | −0.0015 (−3.4, 5) ✓ | −0.0009 (−0.8, 4) | +0.0007 |
| **X5** vector scaling (`C2_vector`) | −0.0003 | +0.0016 | +0.0035 |
| **X5** isotonic on `p_timeout` (`C3`) / plus direction (`C4`) | +0.018 / +1.16 | +0.100 / +2.36 | +0.021 / +1.47 |
| **X6** fitted linear pool over decays and range members (`E4_fitlin`) | −0.0055 (−10.0, 6) ✓ | −0.0047 (−4.2, 6) ✓ | −0.0010 (−1.2, 4) |

Readings that matter:

- **Scale dominates.** The variance-forecast error itself (level-calibrated QLIKE against the
  realized six-bar variance) falls from 0.683 to 0.498 (15m), 0.822 to 0.628 (1H) and 0.675 to
  0.559 (4H) under `S6`. The reference over-predicts TIMEOUT in its upper deciles on 15m
  (stated 0.55 vs observed 0.51; 0.75 vs 0.68); `S6` removes that (0.54 vs 0.56; 0.74 vs 0.75).
- **The direct six-bar EWMA is clearly worse** than scaling one-bar volatility by `6^alpha`, so
  the horizon-scaling form of the candidate is right and only its inputs were incomplete.
- **Shape barely matters** once the scale is right: knot density is irrelevant, Student-t is
  neutral, and only the session-conditional shape survives on 1H in composition.
- **Post-hoc calibration cannot substitute for a better model**: temperature scaling helps only
  on 15m and only by a fifth of what the scale fix gives; unsmoothed isotonic regression is
  unsafe (it emits 0/1 plateaus on thin inner slices — an implementation property, reported as a
  failed probe, not evidence about calibration in general).
- **Discriminative models do not beat the generative frame.** The logistic model's own
  importance ranking points back to band-over-sigma, sigma, weekend and hour; the boosting
  upper bound adds nothing and overfits on 4H. The architecture question is settled in favour of
  the generative scale-first design.
- **X0 closes the train/serve question**: refitting on the 205-candle window changes nothing
  measurable; on 1H/4H the in-fold optimum on that window is decay 0.97 rather than 0.99.

## 5. Composition, robustness and the sealed look

Greedy composition on DEV in the pre-registered order (scale → shape → calibration →
location → pool), each step kept only under the adoption rule against the current composed
model, on two tracks: **A** (every feature lookback ≤ 205 candles, scored with every EWMA on the
trailing 205-candle window — production-faithful) and **B** (unrestricted).

| Timeframe | Track A recipe (deployable now) | Track B recipe |
|---|---|---|
| 15m | `S6_har_season205` (HAR without the 672-bar weekly term) as the core of a fitted linear pool with the six other scale arms; max lookback 97 bars | `S6_har_season` (needs 673 bars) |
| 1H | `S6_har_season` + session-conditional shape `G4_session`; max lookback 169 bars | identical to A |
| 4H | `S6_har_season`; max lookback 43 bars | identical to A |

Rejected in composition: every shape component on 15m and 4H, temperature scaling on top of
the composed scale (its DEV gain vanished once the scale was fixed), every location component
(the 4H `L3_hour` had passed the L1 rule at Δ = −0.00002 — the rule has no magnitude floor —
and failed against the composed model), and the pool on 1H and 4H.

**DEV (folds 1–6) pooled over both symbols, primary band 0.002**

| Timeframe | B3Dev log loss / Brier / ECE | Track A (windowed 205) | Track B |
|---|---|---|---|
| 15m | 1.0536 / 0.6356 / 0.018 | 1.0447 / 0.6301 / 0.005 | 1.0445 / 0.6300 / 0.005 |
| 1H | 1.0485 / 0.6374 / 0.011 | 1.0334 / 0.6284 / 0.014 | 1.0337 / 0.6286 / 0.014 |
| 4H | 0.9193 / 0.5752 / 0.035 | 0.9144 / 0.5737 / 0.036 | 0.9143 / 0.5737 / 0.036 |

**Robustness (DEV).** Log loss and Brier improve at every band in {0.002, 0.00325, 0.0045,
0.007}, for BTC and ETH separately, in every calendar year (15m 2024–2026, 1H 2023–2025, 4H
2021–2025), in every volatility tercile (largest gains in the quietest tercile: −0.015 on 15m,
−0.025 on 1H), and in every fold (worst fold still negative on every timeframe). `ECE_top`
improves on 15m, is within 0.003 on 1H at the primary band, and is slightly worse on 4H at the
widest bands (up to +0.013 at 0.007).

**SEALED (folds 7–8, one look, attested shortlist B3Dev / CA / CB), primary band 0.002**

| Timeframe | B3Dev log loss / Brier / ECE | CA (deployable) | CB | Per-fold Δ log loss CA |
|---|---|---|---|---|
| 15m | 1.0584 / 0.6375 / 0.032 | **1.0460 / 0.6296 / 0.011** | 1.0453 / 0.6291 / 0.008 | −0.0110, −0.0139 |
| 1H | 1.0488 / 0.6375 / 0.011 | **1.0334 / 0.6292 / 0.015** | 1.0335 / 0.6292 / 0.015 | −0.0183, −0.0126 |
| 4H | 0.9323 / 0.5778 / 0.006 | **0.9254 / 0.5758 / 0.007** | 0.9254 / 0.5758 / 0.007 | −0.0078, −0.0061 |

All six arm × timeframe comparisons meet the pre-registered recommendation rule: log loss and
Brier improve in both sealed folds, for both symbols in both folds, at all four bands, with
`ECE_top` within tolerance (15m markedly better; 1H +0.005; 4H +0.001). The sealed gains are
at least as large as the DEV gains, so the DEV selection did not overfit.

## 6. Recommended future-candidate architecture (`distributional-v2`, not frozen)

Keep the `distributional-v1` contract exactly — a difference of one standardized CDF at the
live band, `mu = 0`, frozen constants, no runtime fitting, numpy only — and replace its scale:

1. **Calendar volatility profile.** A multiplicative table of mean squared return by
   (UTC hour × weekday/weekend) on 15m and 1H (48 cells) and by (bar-of-day × weekday) on 4H
   (42 cells), shrunk toward 1 with a pseudo-count of 50; frozen per timeframe.
2. **HAR log-variance regression.** `sigma_h^2 = exp(b0 + Σ b_k · log RV_k + b_s · log M)`
   with `RV_k` the trailing mean squared return over 1, 6, 24, one day and one week of bars,
   plus the trailing 6- and 24-bar Parkinson range variance, and `M` the mean profile over the
   next six calendar slots. Nine frozen coefficients per timeframe. **Deployable within the
   current 205-candle snapshot on 1H and 4H; on 15m the weekly term must be dropped
   (`S6_har_season205`, 97-bar lookback) unless the owner widens the candle fetch to ≥ 700
   bars** — Track B shows the weekly term is worth about 0.0007 log loss on 15m alone, and the
   Track A pool recovers that without it.
3. **Empirical shape** as today (101 knots, Weibull clamps); on 1H, one shape per UTC session
   (Asia / Europe / US).
4. **Optional, 15m only:** the fitted linear pool over the seven scale arms (weights frozen);
   worth −0.001 log loss on DEV; heavier to serve, and the simplest deployable core
   (`S6_har_season205` alone) already captures 87% of the Track B gain.

**Not recommended** (evidence-backed): any directional term; any discriminative classifier;
isotonic post-hoc calibration; changing the horizon-scaling form; finer shape knots.

## 7. Sequencing and boundaries before any of this can ship

1. **T_close first.** The running §5A evaluation at 2026-09-12T04:00:00Z is untouched by this
   work and must be run once, as scheduled, before any new candidate is considered.
2. **Owner decisions** (batched, none taken here): (a) redefine the skill gate for zero-drift
   models (§2 A6); (b) what the directional display should show under a zero-drift model;
   (c) whether to widen the candle fetch beyond 205 bars (unlocks Track B on 15m and longer
   memories generally); (d) whether a `distributional-v2` freeze should follow the T_close
   result, which resets the calibration cohort again (contract §3).
3. **A new pre-registered holdout** (new candidate freeze, new T_freeze, T0 and T_close) is the
   only acceptance path. The sealed folds here are research evidence on retained klines, not the
   live paired shadow evidence §5A requires.
4. **Implementation shape** if authorised: one new module mirroring
   `probability_distributional.py` with frozen tables, a T2 task with the same fail-closed
   selector and coherence tests, no new dependency (the research used scipy/scikit-learn only for
   fitting; every recommended component is closed-form or table-driven at serve time).

## 8. Research map — what remains open

Dependency-ordered, none started here: **(a)** finer-bar realized variance for the 1H and 4H
cells (needs same-row comparison because the finer caches start later); **(b)** cross-asset
*volatility* spillover (BTC variance into the ETH HAR); **(c)** a GARCH-family and
realized-GARCH comparison against HAR on the same folds; **(d)** band-augmented training so a
discriminative or calibrated layer can serve arbitrary live bands; **(e)** 1D/1W cells built by
aggregating the 4H cache (six years, thin); **(f)** periodic refit policy and drift monitoring for
the frozen seasonal profile under a governed methodology version; **(g)** a per-timeframe
proper-score skill gate design (A6) with its own evidence requirements; **(h)** order-book and
funding features, which need a live collector and are out of reach offline.

## 9. Limitations, stated plainly

Two symbols, one venue, two to six years. Selection happened on DEV and was confirmed once on
SEALED; the sealed window is the most recent five to sixteen months and does not extrapolate to
unobserved regimes. The adoption rule has no magnitude floor (one 2e-5 "adoption" slipped
through at L1 and was correctly rejected in composition). `ECE_top` is slightly worse on 1H and
on 4H at wide bands. The 4H gain is small in absolute terms. Nothing here is a profitability,
per-asset superiority, or product-quality claim, and nothing here inspected or altered the
running holdout, its collector, `distributional-v1`, production or Hugging Face.
