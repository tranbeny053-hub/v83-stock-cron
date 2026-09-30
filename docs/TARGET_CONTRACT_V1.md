# Target contract v1 (`tc-v1`)

Written 2026-09-29 under owner decision D1: dedicated provenance columns. Migration 0011 added
them (applied 2026-09-29). **The resolver reads the contract (Route C), and the writer stamps live
rows (§2.6 package W26).**

## Status

- **Code.** `src/crypto_probability_engine/targets/contract_v1.py`.
  - It is pure. It imports only the standard library and `config/defaults.py`
    (`TIMEFRAME_SECONDS`).
  - Tests: `tests/targets/test_target_contract_v1.py`.
- **The resolver and the writer import it:** `scripts/resolve_outcomes.py` and
  `resolution/status_store.py` (Route C), and `api/analysis_service.py` (W26). The §5A evaluator
  does not. The module is
  outside the evaluator pin closure. A test checks both facts.
- **Stored stamps.** Migration 0011's columns are live (2026-09-29, run 36583531813). The writer
  stamps only after W26 is deployed; until then every stored row is v0.

## Purpose

Today the event a stored probability forecasts is defined only by code. tc-v1 names that event,
versions it and makes it checkable per row. The aims:
- a stored probability can always be matched to the exact event it forecast;
- the resolver knows which venue to resolve on. That includes coherent two-venue rows, which
  today record no venue at all.

tc-v1 changes no estimand, probability, gate or label.

## The estimand: close-anchored

For a live row built by `api/analysis_service.py::_prediction_row`:

- **Reference.** The last closed candle of the snapshot: `reference_close_utc` is its close time,
  and `reference_price` is its close.
- **Horizon.** `horizon_bars` = 6 (`DEFAULT_PHASE1A.h_primary_bars`), and
  `horizon_end_utc = reference_close_utc + horizon_bars × TIMEFRAME_SECONDS[timeframe]`.
- **Close-anchored.** The horizon runs from the reference close, not from the moment of issue.
  The time left at issue is therefore shorter than the nominal six bars by the age of the
  reference close at issue. That age is up to 1.5 bars at `as_of` (the candle freshness budget),
  plus any candle-cache reuse (up to 300 s) and the compute time.
- **Band.** `decision_band_frac`, the round-trip cost (2 × taker fee + slippage), as a fraction of
  `reference_price`. When present, the writer's band is at least 2 × taker fee.
- **Label.** With `r = (terminal close − reference_price) / reference_price`: `UP` if
  `r > band`, `DOWN` if `r < −band`, otherwise `TIMEOUT`. `p_up_frac`, `p_down_frac` and
  `p_timeout_frac` forecast this label.
- **Resolution** (since PR #129, `scripts/resolve_outcomes.py`). The terminal close is the close
  of the bar whose close time equals `horizon_end_utc` exactly, fetched from the same venue.

## Fields

### Target: `TargetContractV1`

| Field | Source | Stored |
|---|---|---|
| `target_version` | constant `tc-v1` | planned column |
| `normalized_symbol` | `symbol.display` | existing column |
| `timeframe` | request; tc-v1 admits `15m`, `1H`, `4H`, `1D`, `1W` | existing column |
| `reference_venue` | `VENUE_LABELS[snapshot.provider]`: the venue whose candles gave the reference close | planned column |
| `reference_close_utc` | close time of the last closed candle | existing column |
| `reference_price` | close of that candle | existing column |
| `horizon_bars` | 6 | existing column |
| `horizon_end_utc` | `reference_close_utc + horizon_bars × bar` | existing column |
| `band_frac` | the row's `decision_band_frac` | existing column |
| `band_units` | constant `FRACTION_OF_REFERENCE_PRICE` | derived, never stored |
| `label_rule` | constant `TERMINAL_CLOSE_VS_BAND_3STATE` | derived, never stored |
| `resolution_rule` | constant `EXACT_TERMINAL_BAR_SAME_VENUE` | derived, never stored |

`VENUE_LABELS` maps `binance` to `BINANCE_PUBLIC` and `okx` to `OKX_PUBLIC`. It equals
`adapters/provider_selection.py` `DATA_SOURCE_BY_PROVIDER`, which labels every live row's
`data_source`, and is the inverse of the resolver's `EXACT_SOURCE_PROVIDERS`. Tests check both.

### Timestamps: `ForecastTimestampsV1`

All of these are app-clock instants. The database's commit time (`created_at`, DB clock) is never
one of them and is never compared.

| Field | Meaning | Stored |
|---|---|---|
| `source_as_of_utc` | the row's `predicted_at_utc` | existing column |
| `candle_cutoff_utc` | the row's `reference_close_utc`: the last candle used | existing column |
| `overall_cutoff_utc` | the row's `predicted_at_utc` | existing column |
| `core_computed_at_utc` | when the quant core finished | planned column |
| `issued_at_utc` | when the response was produced | planned column |
| `remaining_duration_at_issue` | `horizon_end_utc − issued_at_utc` | derived, never stored |

- **`predicted_at_utc` is locked.** It is `snapshot.as_of_utc`, stamped with `utc_now()` after
  the candle and depth fetch. The 300 s candle cache can reuse an older snapshot, and with it an
  older `as_of_utc`.
  - The feature and derivatives snapshot builders and the §5A embargo depend on it.
  - tc-v1 never redefines, renames or overwrites it. It reads it as `source_as_of`.
- **Why the overall cutoff equals `predicted_at_utc`.** The core's other inputs are read at that
  instant: the order book, and the band and liquidity derived from it. The ticker and recent
  trades are fetched just after it, and neither reaches the quant core.
- **New names.** quant_v2's `computed_at_utc` actually means as_of. tc-v1 therefore introduces
  `core_computed_at_utc` and `issued_at_utc` rather than reusing that name.

### Columns: migration 0011 (applied 2026-09-29)

- **Columns.** `target_version`, `reference_venue`, `core_computed_at_utc` and `issued_at_utc`
  (`STAMP_FIELDS`, in that order). Types: text for the first two, and `TIMESTAMPTZ`, like the
  existing `*_utc` columns, for the two times.
- **Nullable, with no default.** NULL in all four means v0.
- **No backfill.**
- **Checks.**
  - `target_version` is NULL or `tc-v1`.
  - `reference_venue` is NULL or a venue label.
  - A row carries either none of the four or all four, and when it carries them,
    `core_computed_at_utc <= issued_at_utc`.
- **Applied once** (2026-09-29, run 36583531813). The file is
  `migrations/0011_prediction_target_provenance.sql`.
  - Its only route is `scripts/apply_migration_0011.py`.
  - The route is dispatched once, by `.github/workflows/apply-migration-0011.yml`, as a T4 action.

## Invariants

`validate_v1` returns violation codes. An empty result means a valid tc-v1 row. Every comparison
is exact.

| ID | Rule | Row-checkable |
|---|---|---|
| I1 | Chronology, app clock only: `reference_close_utc ≤ predicted_at_utc ≤ core_computed_at_utc ≤ issued_at_utc`. The DB commit time is never checked. | yes: `I1_*` |
| I2 | `horizon_end_utc = reference_close_utc + horizon_bars × TIMEFRAME_SECONDS[timeframe]`, exactly. | yes: `I2_HORIZON_END_MISMATCH` |
| I3 | `horizon_end_utc > issued_at_utc`: a positive remaining duration at issue. | yes: `I3_NO_REMAINING_DURATION` |
| I4 | Resolution rule: the bar whose close equals `horizon_end_utc` exactly, on `reference_venue`. There is no other venue and no nearest bar. The resolver enforces it with market data. | no |
| I5 | Each of `p_up_frac`, `p_down_frac`, `p_timeout_frac` is in [0, 1], and they sum to 1 within 1e-9. | yes: `I5_*` |
| I6 | Write-once: the stamp, and the evidence-class fields pending OD-FINAL-3, are written with the row and never updated. | no |
| I7 | NULL = v0: an unstamped row is v0; there is no backfill. | no (see `classify_row`) |
| I8 | `reference_venue` is `BINANCE_PUBLIC` or `OKX_PUBLIC`. A venue `data_source` must equal it. `CROSS_PROVIDER` requires `cross_provider_state = COHERENT`. Any other `data_source` fails. | yes: `I8_*` |
| I9 | `timeframe` is in `15m`, `1H`, `4H`, `1D`, `1W` (`1M` fails closed), and `1 ≤ horizon_bars ≤ 96`. | yes: `I9_*` |

`validate_v1` also requires all of the following:
- `target_version` is `tc-v1`;
- the row is not in the §5A OOS population. A `prediction_id` or `run_id` starting `oosb-` (which
  covers every arm id `oosb-<32 hex>:<tf>:(BASELINE|CANDIDATE)`) fails, and so does origin
  `SCHEDULED_SHADOW_EVIDENCE`;
- `normalized_symbol` is a non-empty string;
- `reference_price` is finite and > 0;
- `decision_band_frac` is finite and ≥ 0;
- `is_live_data` is `True`;
- every timestamp parses, whether an ISO-8601 string with `Z` or an offset, or a datetime. A naive
  value means UTC.

**Resolver band fallback.** When a stored band is missing or ≤ 0, the resolver substitutes
2 × `taker_fee_frac`. tc-v1 accepts a band of exactly 0, but the writer never produces one.

## Legacy (v0) mapping

- **What v0 is.** A row whose four stamp fields are all absent or NULL is v0
  (`classify_row` returns `v0-legacy`). Its estimand is the same close-anchored target. Only the
  provenance is missing.
- **v0 venue.** A v0 row's venue is its `data_source`, only when that is exactly `BINANCE_PUBLIC`
  or `OKX_PUBLIC`.
- **v0 `CROSS_PROVIDER` rows stay unresolvable** under the exact-source rule. The writer never
  stored which venue produced their reference candle, and tc-v1 does not guess it.
- **Earlier outcomes.** Outcomes written before PR #129 carry `resolver_version`
  `resolver-v1-wave4b2`. They followed that resolver's rule: the first candle closing at or after
  `horizon_end_utc`, possibly from the other venue.
- **`tc-v1-invalid`.** A row that carries any stamp but fails `validate_v1` gets this class and no
  resolution venue. That includes a partial stamp, a NULL `target_version` beside another stamp
  field, or any other `target_version`. It fails closed.

## API (`contract_v1.py`)

- **`stamp_v1(row, *, snapshot_provider, core_computed_at, issued_at)`.**
  - It returns a new dict: the row plus the four stamp fields, and only if the result passes
    `validate_v1`. Otherwise it returns an unchanged shallow copy.
  - The times are written as ISO-8601 UTC `Z` strings, the writer's `_iso_utc` format.
  - It never raises, never mutates its input and never changes an existing key.
  - A row that already has any stamp key, even NULL, is returned unchanged.
  - An unknown provider is never guessed. For example, `active_provider` `cross_provider` is not
    a snapshot provider.
- **`validate_v1(row)`** returns a tuple of violation codes.
- **`classify_row(row)`** returns `tc-v1`, `tc-v1-invalid` or `v0-legacy`.
- **`resolution_venue(row)`.**
  - Valid tc-v1: it returns `reference_venue`.
  - v0: it returns the exact venue `data_source`, or None.
  - Otherwise: None.
- **Row constructors.** `TargetContractV1.from_row(row)` and `ForecastTimestampsV1.from_row(row)`
  return None unless the row is valid tc-v1.

## Out of scope

- **Evidence-class fields.** Pending OD-FINAL-3.
- **Display of the contract or its timestamps.** Pending OD-FINAL-5.
- **`1M`.** Its bar is an approximate 30 days with no exact bar grid, so it fails closed.
- **The §5A OOS population.** It is consumed and is never stamped.
- **Any change to the estimand itself,** for example an issue-anchored horizon. That would be a
  new target version.

## Planned order

1. **Author migration 0011.** Done: the migration and its one-shot apply route. Four nullable
   columns; NULL = v0; no backfill.
2. **Apply 0011 live.** Done: the owner's one-shot T4 (2026-09-29, run 36583531813, PASS).
3. **Stamp in the writer.** W26, under §2.6. The writer calls `stamp_v1` with `snapshot.provider`,
   the core-finished instant and the response instant.
   - `api/analysis_service.py` (runtime-guarded, not pinned) takes both instants from an
     injectable app clock, `_stamp_clock`. It stamps after `_prediction_row` and after both
     snapshot builders, so the response, `analysis_hash`, the detail view and the snapshots are
     unchanged. It never stamps an OOS arm or a `SCHEDULED_SHADOW_EVIDENCE` row.
   - The REST writer posts the whole row, so stamping before 0011 is live would break its
     prediction writes.
   - The Postgres writer names its columns in the pinned `persistence/repository.py`. That
     column list changes only under §2.6, and only if actually required. It is required: the
     fixed 25-column INSERT drops the stamp. W26's pinned hunk names the four stamp columns
     only when all four are present and not None; for every other row the statement stays
     byte-identical. It came with the owner's §2.6 authorization, `evaluator_pin.write_pin()`
     and a STATE record.
4. **Resolver.** Implemented locally (RC1, branch `feat/resolver-route-c-rq-v1`; not merged or
   deployed). `scripts/resolve_outcomes.py` resolves every row on `resolution_venue(row)`. Route C
   (`crypto_probability_engine/resolution/`, unpinned) reads `reference_venue` and the other stamp
   columns on its own connection, so stamped `CROSS_PROVIDER` rows become due there; unstamped
   ones never are.
