# Debug Pack Example

Purpose: sanitized copy/paste template for Claude/Codex debugging. Do not include secrets, plaintext access values, full environment, database URLs, provider keys, private headers, or full article bodies.

```text
# Debug Pack
run_id:
symbols:
timeframes:
analysis_mode:
asset_class:
app_version:
environment:
  APP_ACCESS_CODE_HASH: set (****)
  DEV_MODE_CODE_HASH: set (****)
  SESSION_SIGNING_KEY: set (****)
  SUPABASE: not configured
  BINANCE_KEY: not configured
  OKX_KEY: not configured
failed_step:
user_facing_error:
raw_error_summary:
active_provider:
provider_health:
  binance_status:
  okx_status:
  latency_ms:
  throttle_status:
candles_received:
validation_warnings:
feature_summary:
quant_compute_state:
probability_state:
risk_arbiter_state:
gate_result:
recent_logs:
  - sanitized only
sanitized_payload_hash:
steps_to_reproduce:
```

## News Add-on Pack

Use only for `NEWS_ADDON` runs.

```text
# News Add-on Pack
run_id:
analysis_mode: NEWS_ADDON
news_addon_state:
  status:
  sources_configured:
  sources_ok:
  sources_failed:
  latency_ms:
sources_queried:
  - name:
    tier:
    status:
    latency_ms:
    throttle:
item_counts:
  considered:
  after_dedup:
  dropped_low_confidence:
top_material_events:
  - category:
    title:
    source:
    tier:
    published_utc:
    materiality:
    url_hash:
event_horizon:
  immediate_count:
  next_24h_count:
  next_7d_count:
  next_30d_count:
  nearest_material_event:
source_confidence:
  tier_breakdown:
  weighted_confidence_frac:
news_influence:
  confidence_adj:
  timeout_adj:
  alpha_evidence:
  omega_pressure:
  sigma_pressure:
  clamp_status:
  reasons:
news_warnings:
notes: no full article bodies; no secrets; metadata and short snippets only
```

## Sanitization Rules

- Mask sensitive values as `set (****)`.
- Include hashes, statuses, counts, timestamps, and short summaries.
- Do not include full raw payloads from providers unless they are already sanitized and contain no secrets or full article bodies.
- Do not include full env dumps.
- Do not include copyrighted full article text.

