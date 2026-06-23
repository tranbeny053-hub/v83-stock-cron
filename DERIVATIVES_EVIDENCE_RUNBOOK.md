# Derivatives Evidence Collector Runbook

## Boundary

Wave 4D.3-Ops Phase 2A is a manual-only evidence-collection foundation. The
workflow has no schedule or cron trigger, the collector is disabled by default,
and dry-run defaults to `true`. The normal Hugging Face runtime keeps
`UCPE_ENABLE_DERIVATIVES_INTEL=false`; the collector enables derivatives only
inside its short-lived process.

The fixed maximum is four cells, in this order:

1. `BTC/USDT` `1H`
2. `BTC/USDT` `4H`
3. `ETH/USDT` `1H`
4. `ETH/USDT` `4H`

One invocation can create no more than four predictions and four derivatives
snapshots. There is no range argument, historical backfill, or catch-up loop.
The existing adapters bound the full matrix to 58 logical public requests and
at most 98 HTTP attempts in the worst case. That ceiling allows a failed spot
registry read to be retried for each cell, allows every spot call its one
configured retry, and assumes the 60-second derivatives symbol cache expires
between slow cells. Derivatives registry and current-state resources do not retry.

## Zero-write dry run

Use `workflow_dispatch` and select:

```text
enable_collector = true
dry_run = true
matrix_scope = FULL_4_CELL, BTC_ONLY, or ETH_ONLY
confirm_write = empty
```

Dry-run may read public market data and calculate deterministic cadence
identities. It does not construct the production persistence repository, read
`SUPABASE_DB_URL`, or call the synchronous persistence service.

## Controlled one-shot write

Before a write, confirm the prediction-origin migration and immutable
derivatives-snapshot migration are already approved and applied, and that the
repository secret is configured in the GitHub scheduler repository. Then use:

```text
enable_collector = true
dry_run = false
matrix_scope = the reviewed scope
confirm_write = WRITE-EVIDENCE
```

Any other confirmation fails closed. The workflow passes the database URL only
to the collector step. The collector uses `analyze_request` with deterministic
identity and `SCHEDULED_SHADOW_EVIDENCE`, then delegates all writes to
`persist_analysis_now`; it never builds rows or executes SQL.

## Post-write verification

After a controlled write, use read-only production queries to verify:

* no more than the requested prediction rows were added;
* every new prediction has origin `SCHEDULED_SHADOW_EVIDENCE`;
* every new derivatives snapshot is linked to its prediction ID;
* influence remains `SHADOW_ONLY` and decision influence remains zero;
* duplicate reruns report identical evidence rather than overwrite it;
* calibration and Quant V2 validation continue excluding the scheduled origin.

Do not paste query results containing credentials, URLs, raw payloads, or other
sensitive material into logs or chat.

## Stop and kill procedure

Do not dispatch another run. If a run is waiting, let the non-cancelling
concurrency group finish unless incident response requires GitHub-side
cancellation. Keep `enable_collector=false` on subsequent manual dispatches.
No Hugging Face variable needs to be changed or restarted because this collector
does not modify the web runtime.

## Interpretation and reruns

`INSERTED` records first-write evidence. `ALREADY_EXISTS` is an idempotent retry.
Degraded provider evidence may be persisted and is reported separately from the
persistence outcome. Provider unavailability, partial persistence, a failed
safety invariant, or an unresolved cell failure makes the invocation non-zero.
Never treat unavailable or degraded evidence as healthy evidence.

Phase 2A does not perform Wave 4D.4 evaluation and does not open Wave 4D.5.
Collection must remain dormant until a separately reviewed GitHub-only
deployment and an explicitly authorized manual dispatch.

## Binance Registry Diagnostic

The Binance registry diagnostic is diagnosis only. It does not access a
database, does not create predictions, does not persist evidence, and does not
authorize a collector rerun by itself.

The manual workflow `UCPE Derivatives Registry Diagnostic` runs exactly three
public probes from the scheduler runner:

1. Binance USD-M `GET /fapi/v1/exchangeInfo` with a 3 second timeout.
2. Binance USD-M `GET /fapi/v1/exchangeInfo` with a 10 second timeout.
3. OKX SWAP `GET /api/v5/public/instruments?instType=SWAP` with a 10 second
   timeout.

Dispatch it manually from GitHub Actions when a reviewer asks for runner-side
registry evidence. The output is intentionally sanitized: endpoint paths,
timeouts, HTTP status, high-level error categories, elapsed milliseconds, and
symbol/data counts only. It never prints full URLs, response bodies, headers,
cookies, secrets, database values, or exception traces.

Interpret final classifications as follows:

* `BINANCE_OK`: both Binance registry probes returned a valid public symbols
  payload.
* `BINANCE_TIMEOUT_AT_3S_BUT_OK_AT_10S`: the 3 second probe timed out but the
  10 second probe succeeded.
* `BINANCE_ACCESS_RESTRICTED`: Binance returned access or legal restriction
  evidence such as 401, 403, or 451.
* `BINANCE_RATE_LIMITED`: Binance returned rate-limit evidence such as 418 or
  429.
* `BINANCE_SERVER_FAILURE`: Binance returned a 5xx failure.
* `BINANCE_NETWORK_OR_TLS_FAILURE`: both Binance probes failed before a usable
  HTTP status.
* `BINANCE_MALFORMED_RESPONSE`: Binance returned a response that did not match
  the expected registry JSON shape.
* `BINANCE_UNKNOWN_FAILURE`: the sanitized evidence did not fit a more specific
  diagnostic category.

OKX is a same-runner control probe only; it does not override the Binance final
classification. Do not claim a root cause until the diagnostic workflow has run
and the result has been reviewed. Cron scheduling and Wave 4D.4 evaluation
remain blocked until a separate review authorizes them.
