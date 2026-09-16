# R2 — Future Quant Frontier: pre-registration and research map

Status: **research only, strictly isolated from §5A.** Opened 2026-09-04 while the
`distributional-v1` holdout runs (T_close = 2026-09-12T04:00:00Z). Nothing here is §5A
evidence, licenses no promotion, no freeze, no deploy, and no product claim.

## 1. Isolation envelope (binding)

- **Reads only** the candle cache retained at T_freeze:
  `.work/research/cache/datasets/*.pkl` (BTC/USDT, ETH/USDT × 15m/1H/4H; public Binance
  klines, OHLCV, closed bars). No database, no network, no holdout, no outcomes table, no
  `oos/`, no collector, no production or HF access.
- **Writes only** `.work/research2/**` (gitignored). Durable artifacts are documents under
  `docs/` and a `STATE.md` checkpoint on branch `research/r2-frontier` (T0). No product
  code, test, schema, workflow or dependency changes. `distributional-v1` stays frozen.
- **Information boundary.** A row is admitted iff `horizon_end_utc < R_admit`,
  `R_admit = 2026-08-12T00:00:00Z` (T_freeze − 8 d 11 h 36 m). Every feature uses only
  candles with `close_time <= predicted_at < R_admit`. Holdout outcomes begin at
  T0 = 2026-08-21T04:00:00Z, so no admitted row overlaps any holdout instant.
- No push, no PR, no T3/T4 boundary is crossed by this milestone.

## 2. Estimand

For cell (symbol, timeframe) and a row anchored at bar close `τ`:
`P(label | F_τ)`, `label ∈ {UP, DOWN, TIMEOUT}`, horizon `h = 6` bars, terminal simple return
`r = close_{τ+6}/close_τ − 1`, resolver semantics exactly (`UP` iff `r > b`, `DOWN` iff
`r < −b`, else `TIMEOUT`, equality → `TIMEOUT`). Primary band `b = 0.002` (production's
degraded no-book execution band); sensitivity bands `{0.00325, 0.0045, 0.007}`.

## 3. Protocol (fixed before any experiment runs)

- **Folds.** Per timeframe, `K = 8` expanding-origin folds; boundaries at equal-count
  quantiles of `predicted_at` over admitted rows, shared by both symbols of the timeframe
  (Phase R layout). Purge: training rows need `horizon_end < split`. Embargo: training rows
  need `predicted_at < split − 6 bars`.
- **DEV = folds 1–6; SEALED = folds 7–8.** All selection, tuning and composition happen on
  DEV. SEALED is evaluated **once**, for a shortlist of at most four arms (reference
  included) written to `.work/research2/SEALED_ATTESTATION.md` **before** the run. The
  runner refuses sealed folds without that file. No second look.
- **Scores.** Primary: mean three-class **log loss** (natural log, proper). Secondary:
  three-class **Brier** (sum of squared errors, the product and §5A definition).
  Calibration: `ECE_top` on the product's `RELIABILITY_BUCKETS` over the top-label
  probability, unfiltered bins (product definition, computed by the product function), plus
  decile reliability of `p_timeout`. Sharpness: mean predictive entropy. All reported per
  cell, per fold, and pooled over symbols per timeframe.
- **Paired statistics** vs the reference arm: per-fold mean difference, mean of fold means,
  t-statistic over folds, sign count. Ties count against the challenger.
- **Adoption rule (DEV, per timeframe, pooled over symbols).** A component is adopted iff
  its paired log-loss difference is `< 0` in **≥ 5 of 6** dev folds, the fold-mean
  t-statistic is `≤ −2.0`, no symbol's pooled Brier worsens by more than `0.002`, and
  `ECE_top` does not worsen by more than `0.01`.
- **Recommendation rule (SEALED, per timeframe).** A composed candidate is *recommended
  for a future freeze decision* iff both log loss and Brier improve on the reference in
  **both** sealed folds and `ECE_top` is not worse by more than `0.01`. Anything short is
  recorded as "not recommended" with its numbers.
- These rules rank research candidates only. They are **not** §5A acceptance and carry no
  error-rate claim.

## 4. Reference arms

- **B3-dev** — the Phase R selected method refit in-fold: EWMA close-to-close variance
  (decay grid `{0.85, 0.90, 0.94, 0.97, 0.99}`), `sigma_h = sigma_bar · 6^alpha`
  (alpha grid `{0.3, 0.4, 0.5, 0.6, 0.7}`), `mu = 0`, empirical 101-knot CDF `G` of
  standardized training returns, Weibull tail clamps. EWMA over the full history prefix
  (as Phase R computed it). **This is the reference for every paired comparison.**
- **B3-prod** — the frozen production constants (`probability_distributional.py`) with
  the EWMA computed on the **trailing 205-bar window**, which is what the live snapshot
  actually carries (`min_history_for + 5`). Used in X0 only; its constants were fitted on
  data overlapping the dev folds, so it is a train/serve-skew probe, not a fair challenger.

## 5. Research map (dependency-aware)

```
L0  foundation: corpus (admitted rows) → causal feature store → protocol → scoring → selftest
      │
L1  independent experiments (parallel; each isolates one component against B3-dev)
      ├─ X0 production faithfulness   (205-bar window, EWMA initialisation)
      ├─ X1 scale / volatility forecast (range-based, HAR, seasonality, direct h-bar)
      ├─ X2 shape of standardized returns (Student-t, regime-conditional, knot density)
      ├─ X3 location / direction       (cross-asset lead-lag, lagged returns, time-of-day)
      ├─ X4 direct discriminative      (softmax on the generative features; GBM upper bound)
      ├─ X5 post-hoc calibration       (temperature, vector scaling, isotonic on p_timeout)
      └─ X6 ensembling                 (log-linear / linear pools over scale variants)
      │
L2  composition on DEV: greedy, ordered scale → shape → calibration → location → pool,
    each step kept only under the adoption rule; ≤ 3 composed candidates:
      C-A deployable now (≤ 205 bars, numpy-only)   C-B needs a longer candle window
      C-C discriminative upper bound (dependency decision required)
      │
L3  SEALED one-look evaluation of the attested shortlist; robustness (band grid,
    per-symbol, per-year, vol-tercile regime); failure analysis; recommendation.
```

Every feature records its **minimum lookback in bars**; an arm is flagged
`FEASIBLE_205` only if every feature it uses needs ≤ 205 bars, because that is the
production snapshot today.

## 6. Experiment specifications

**X0 — production faithfulness.** B3 with EWMA on (a) full prefix, (b) trailing 205 bars
initialised at the window's first squared return (production code path, asserted by
identity against `probability_distributional._ewma_sigma`), (c) trailing 205 bars
initialised at the window's mean squared return, (d) the frozen production constants on
(b). Each in-fold refit where applicable. Measures the skew between what was validated and
what runs.

**X1 — scale.** Shape held at the in-fold empirical CDF; only `sigma_h` varies.
S1 EWMA close-to-close (= B3-dev). S2 range-based EWMA on Parkinson, Garman–Klass,
Rogers–Satchell variances, and a close/range hybrid. S3 HAR-style OLS of
`log RV6_future` on log trailing realized variances over `{1, 6, 24, 1 day, 1 week}` bars
(with log-bias correction). S4 deterministic intraday/weekly seasonality multiplier
(hour × weekday/weekend profile, pseudo-count shrinkage 50, fitted on training rows only)
applied to deseasonalised EWMA and reseasonalised over the next six bars. S5 direct EWMA of
overlapping 6-bar squared returns. S6 = S3 + S4. Hyper-parameters chosen in-fold by the same
Gaussian quasi-likelihood B3 uses. Also reported: QLIKE against realized 6-bar variance.

**X2 — shape.** Scale held at B3-dev. G1 empirical 101 knots (= B3-dev). G2 Student-t with
in-fold MLE degrees of freedom. G3 empirical CDF conditional on in-fold `sigma_h` terciles.
G4 empirical CDF conditional on session (Asia / Europe / US by UTC hour) for 15m and 1H.
G5 empirical 1001 knots.

**X3 — location.** Within the generative frame: `mu` from in-fold ridge on the standardized
target using (a) other-symbol lagged returns 1/3/6 bars, (b) own lagged returns 1/3/6/24,
(c) hour-of-day means; shrinkage chosen on an inner temporal split. Coefficient stability
across folds reported. Expected to be near-null; the estimand is whether any directional
information exists at this horizon.

**X4 — direct discriminative.** Multinomial logistic regression on `log(b/sigma_h)` and the
X1/X3 features, L2 chosen on an inner temporal split; plus a histogram gradient-boosting
classifier with early stopping on the same inner split as an **upper-bound probe**
(not deployable without a dependency decision).

**X5 — post-hoc calibration** of B3-dev outputs: temperature scaling, vector (3×3 affine)
scaling with L2, isotonic regression on `p_timeout` with the directional split preserved.
Calibrators are fitted on an inner held-out slice of the training fold (purged), never on
the fitting slice.

**X6 — ensembling.** Equal-weight log-linear and linear pools over the decay grid and the
close/range estimators; in-fold fitted weights on an inner split.

## 7. What this milestone may and may not conclude

May: rank modelling components by out-of-sample proper-score improvement over B3-dev;
recommend a *future* candidate architecture for a *future* owner freeze decision; record
production train/serve skew as an engineering finding.
May not: touch the running holdout; alter `distributional-v1`; claim profitability,
per-asset superiority, or anything about the §5A result; promote, freeze, push or deploy.
