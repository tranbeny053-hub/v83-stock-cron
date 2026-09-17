# distributional-v2 — prepared, not frozen

Written 2026-09-15, under the owner ruling "R2-based v2; no new freeze/T0 or holdout tuning".

## Status, in one paragraph

A complete, tested implementation of the future candidate that R2 recommended is ready for a
freeze decision. **Nothing is decided by it:**
- it is wired to nothing (no methodology selector, no version constant);
- it is not frozen;
- it defines no T_freeze, T0 or holdout;
- no data from the §5A holdout window was read;
- §5A's consumed look is untouched.

It is evidence that the recipe can be served exactly. It is not evidence that the recipe is good in
production: only a new pre-registered holdout can show that (§5A.9).

## What it serves

R2 arm **CB** (`docs/R2_FRONTIER_REPORT.md` §5–6, `docs/r2_evidence/SEALED_ATTESTATION.md`), per
(symbol, timeframe), for **BTC/USDT and ETH/USDT only**:

| Timeframe | Scale | Shape | Closed candles required |
|---|---|---|---|
| 15m | HAR log-variance + calendar profile, incl. the one-week term | one 101-knot table | 673 |
| 1H | the same | one table per UTC session (00–07, 08–15, 16–23) | 169 |
| 4H | the same | one 101-knot table | 43 |

- **Code.** `src/crypto_probability_engine/quant/probability_distributional_v2.py`, pure Python, the
  `probability_distributional.py` contract: one empirical CDF at the live band, `mu = 0`, no
  runtime fitting.
- **Constants.** `src/crypto_probability_engine/quant/distributional_v2_tables.py`, with
  `TABLES_SHA256 = f0689f292047067b25610ee97e7d001901799d028aa71d5bb0315a666bd377b2`.
- **Any other symbol or timeframe, or any window that is not the full run of closed, adjacent,
  UTC-aligned, well-formed candles, fails closed.**
- **The 15m window exceeds the snapshot.** 673 is more than the 204 candles a market snapshot
  carries, so serving 15m needs the candle-history capability prepared separately
  (`adapters/candle_history.py`, branch `prep/l3-candle-width`). 1H and 4H fit inside the existing
  snapshot.

## Where the constants came from

- **Code.** R2's own research code path, verbatim: `r2.compose.build_model(rows, CB recipe)` on
  **all** admitted rows of each cell. The recipe was checked against `results/compose_*.json`
  `final_arms`.
- **No score chose anything.** The recipe is the attested one, and S6 has no hyperparameters. The
  seasonal HAR regression is a least-squares fit, and the shape is the empirical quantile table of
  r/sigma. Sealed folds 7–8 enter only as training rows; their one-look evaluation is not repeated.
- **Data.** The Binance klines cache retained at T_freeze.
  - The cache files were written 2026-08-20T09:16–09:19Z, before §5A T0 = 2026-08-21T04:00Z.
  - Rows are admitted only if their six-bar horizon ended before R_admit = 2026-08-12T00:00Z. The
    last admitted horizon ends at 2026-08-11T23:59:59.999Z.

| Cell | Admitted rows | With the full HAR history |
|---|---|---|
| each 15m | 69,244 | 68,596 |
| each 1H | 34,807 | 34,663 |
| each 4H | 13,059 | 13,041 |

- **Input digests** (SHA-256, first 16 hex): full values, with every research-code file digest, in
  the refit output that produced the constants.
  - candle cache:
    - BTCUSDT_15m `50d82e13fbaf3ccf`, 1H `2b0d48207f044db3`, 4H `45cc136f01f3244a`;
    - ETHUSDT_15m `54b6ebf8ae2f9b2c`, 1H `538189adab932b02`, 4H `c98b5059d55ff291`;
  - composition results: 15m `0748e6e5d95b1f9d`, 1H `78db01f173a31c80`, 4H `482a8a9c69616eda`;
  - sealed attestation: `5c1b6f0e8c18d80f`.
- **Research-code-path detail, reproduced for fidelity.**
  - The shape tables include the few leading rows that lack a full one-week history: 648 per 15m
    cell, 144 per 1H, 18 per 4H.
  - The research code standardizes those rows with its EWMA fallback.
  - In serving, such a row cannot occur, because it fails closed.

## Proof that the module computes exactly that recipe

| Check | Rows | Largest probability difference |
|---|---|---|
| Real corpus, research predictions as computed by R2's code | 11,980 sampled rows × 3 bands (20 more were skipped, 10 per 1H cell, because their windows touch exchange-maintenance bars) | 2.3e-9 |
| The same rows, R2's feature store rebuilt with per-window sums | 11,980 × 3 | **8.9e-16** |
| Committed golden test: 18 synthetic windows (every cell, weekday and weekend, all three 1H sessions) × 3 bands | 54 | 3.9e-16 (test tolerance 1e-12) |

**The 2.3e-9 is attributed, not tolerated.**
- R2's rolling means difference a cumulative sum over the whole corpus, which loses about 1e-16 of
  absolute precision.
- `log(v + 1e-10)` then magnifies that loss for a near-zero return.
- Replacing only that arithmetic brings agreement to machine precision.

## Declared differences from the research code

None of these changes the method. The first is a serving rule; the others are numerical.

1. **No fallback.** An incomplete, irregular or malformed window refuses. The research code
   substituted its EWMA scale.
2. **Timeout.** It is `cdf_hi − cdf_lo`, v1's construction. The research code used
   `1 − p_up − p_down`.
   - The two agree to about 1e-16.
   - At a zero band, R2's form rounds below zero, and **R2's own triplet assertion fails there**
     (found by the golden oracle).
   - v1's form gives exactly zero, and it can never go negative. The live band is always positive.
3. **One triplet construction for all shapes.** R2 used `probabilities_from_cdf` for the session
   shape, which is algebraically identical.
4. **Rolling means use exact window sums (`math.fsum`).**

**A numerical note.**
- On 1H the one-day term equals the 24-bar term; on 4H it equals the 6-bar term.
- Least squares splits their weight equally between the identical columns, so the prediction is
  unaffected.

## Not done, and the decisions that remain the owner's

- **(a) Skill gate.** The directional skill gate cannot evaluate a zero-drift model. The recommended
  proper-score gate is in `docs/R2_ZERO_DRIFT_GATE_AND_DISPLAY.md` §2.
  - It is prepared, dormant, as `calibration/proper_score_skill.py`.
  - Adopting it also needs per-row probabilities from the repository, and the repository is pinned.
- **(b) Display.** The directional split is not 50/50. The skewed shape tables fix it at about 48–54%
  up, per cell and ratio, with no current market state behind it (the correction in
  `docs/R2_ZERO_DRIFT_GATE_AND_DISPLAY.md` §7). The recommended display is in the same document, §4.
- **(c) Wiring.**
  - A methodology selector branch and a version constant are needed.
  - What the branch would call after computing the probabilities is prepared, and not wired:
    `quant/distributional_v2_state.py` builds v1's exact `probability_state` and
    `horizon_timeout_state` shapes from a v2 triplet. A test compares them field by field.
  - Both live in files pinned by the §5A evaluator (`quant/pipeline.py`, `config/defaults.py`), so
    wiring needs the owner's §2.6 authorization.
  - The 15m wiring also consumes the candle-history capability.
- **(d) Freeze.**
  - Whether to freeze these exact constants, or refit on data up to a new T_freeze. Either way
    there is no tuning against the consumed §5A holdout.
  - A new pre-registration: T_freeze, T0, T_close and decision rules.
  - Archiving the research code in the repository, so an auditor can regenerate the tables.
  - A freeze assigns a new `methodology_version`. That resets calibration to `NO_SAMPLES`, so every
    affected cell shows the fail-closed gated state until the new cohort reaches the sample floor.
- **Scope.**
  - Constants exist for BTC/USDT and ETH/USDT only, because a fit pooled across symbols would be new
    research.
  - The constants come from Binance klines; production candles may come from OKX or Binance, as for
    distributional-v1.
