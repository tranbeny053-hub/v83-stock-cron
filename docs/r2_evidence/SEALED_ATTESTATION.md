# SEALED attestation — R2 Future Quant Frontier

Written 2026-09-04 BEFORE any sealed fold (7, 8) was evaluated. Pre-registration:
docs/R2_FRONTIER_PREREGISTRATION.md, committed at 6ec047d on branch research/r2-frontier.

Shortlist (at most four arms, reference mandatory; names resolve per timeframe to the recipes
recorded in results/compose_{15m,1H,4H}.json, final_arms):

- ARM: B3Dev
- ARM: CA
- ARM: CB

CA = TRACK_A deployable composition (all feature lookbacks <= 205 candles; scored with every
EWMA computed on the trailing 205-candle window, production-faithful).
CB = TRACK_B unrestricted composition.

Recorded DEV recipes (folds 1-6, from the greedy pre-registered composition):
- 15m: CA = fitted linear pool over {S6_har_season205, S3_har205, S4_season, S2_park, S2_gk,
  S2_hybrid, S2_rs}; CB = S6_har_season (needs rv_week, 673-bar lookback).
- 1H:  CA = CB = S6_har_season + G4_session shape (max lookback 169 bars).
- 4H:  CA = CB = S6_har_season (max lookback 43 bars).

Recommendation rule (pre-registered, applied mechanically by r2/sealed.py): per timeframe,
pooled over symbols, log loss AND Brier improve on B3Dev in BOTH sealed folds and ECE_top is not
worse by more than 0.01. This is the single look. No second run; no retuning against these folds.
