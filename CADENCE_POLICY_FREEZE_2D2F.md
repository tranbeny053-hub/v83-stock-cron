# Phase 2D.2F OKX Cadence Policy Freeze

## 1. Decision status

Phase 2D.2F ratifies the four current cadence-window values unchanged. This is a governed
decision-record freeze, not a runtime or source mutation. No deployment or production mutation
occurred in 2D.2F.

## 2. Scope of the freeze

The freeze covers only the existing OKX v1 cadence policy ID, the 1H and 4H admission windows,
and the existing fail-closed activation sentinel. Activation and cutover remain a separate Phase
2D.2G authorization.

## 3. Frozen policy values

- Policy ID: `cadence-cutover-okx-v1`
- 1H `post_close_delay_seconds`: `300`
- 1H `max_lateness_seconds`: `1200`
- 4H `post_close_delay_seconds`: `300`
- 4H `max_lateness_seconds`: `1800`
- Activation sentinel: `CUTOVER_CLOSE_UTC = 2100-01-01T00:00:00Z`

The sentinel remains an intentional fail-closed activation lock. No calendar cutover time is
selected by this decision.

## 4. Evidence cohort

All six write-free scheduler samples used source
`da5bb7f17de085f50fc254ee571bf77ef156630c`, methodology
`deriv-intel-okx-shadow-v1`, provider policy `deriv-provider-policy-okx-only-v1`, required
provider `OKX_SWAP`, and the BTC/USDT and ETH/USDT 1H/4H matrix. Influence remained
`SHADOW_ONLY`.

| Sample | Approximate 1H completion offset | Approximate 4H completion offset | Runner clock offset |
|---|---:|---:|---:|
| 1 | +3072..+3074 s | +3072..+3074 s | 105 ms |
| 2 | +89..+91 s | +3690..+3691 s | 60 ms |
| 3 | +334..+336 s | +3935..+3936 s | 57 ms |
| 4 | +1186..+1188 s | +4787..+4788 s | 84 ms |
| 5 | +3339..+3341 s | +6940..+6941 s | 119 ms |
| 6, second UTC date | +365..+367 s | +11166..+11167 s | 53 ms |

Every sample was `AVAILABLE_COMPLETE` for all four cells. Each cell was `ACTIVE`, contained all
four required valid metrics, and passed `candle_confirmed`, `no_lookahead_pass`, and
`provider_available`. Each sample used 10 logical requests, 10 HTTP attempts, and zero Binance
requests.

Required metric IDs were:

- `okx.funding.current_estimate`
- `okx.open_interest.current.contracts`
- `okx.open_interest.current.base`
- `okx.open_interest.current.usd`

The samples performed no database or Supabase access, HF mutation, collector invocation,
evidence write, or production mutation.

## 5. Evidence interpretation

The 1H lower edge is supported by complete evidence before window opening at approximately +90
seconds. Complete results near +335 and +366 seconds across two UTC dates support retaining the
300-second lower bound. Complete evidence near +1187 seconds supports the existing 1200-second
upper edge. The +90-second result does not authorize reducing the delay. This cohort describes
observed availability, not worst-case tail latency.

The directly observed 4H completion offsets show complete evidence remained available well beyond
the existing 1800-second maximum-lateness bound. They are not observations of the 4H early edge.

## 6. 4H assumption and limitation

No sample directly measured a 4H close at approximately +300 to +400 seconds. The 4H 300-second
lower bound is inferred rather than directly measured.

The inference rests on these bounded facts:

- 4H closes are a subset of 1H closes on the same OKX candle infrastructure.
- 1H completeness was directly observed as early as approximately +90 seconds.
- Funding and open-interest resources are current-value endpoints, not candle-indexed endpoints.
- All 4H cells were `AVAILABLE_COMPLETE` in all six samples.

Residual risk remains fail-safe: too-early requests are rejected outside the admissible cadence
window or return incomplete evidence, the lane remains non-writing, and production evidence cannot
be silently corrupted. The cohort must not be used to reduce the 4H delay below 300 seconds.

## 7. What this decision does not authorize

This decision does not replace the sentinel, activate cutover or collection, select a calendar
cutover, authorize a collector run or production write, deploy scheduler or HF source, change a
workflow or cron, open Wave 4D.4/4D.5, or permit derivatives influence on probability, score,
hard gates, Decision, or Scenario Plan.

## 8. Future tightening requirements

Any future attempt to tighten a bound requires a separately authorized campaign with, at minimum:

- direct 4H-close early-edge measurements;
- multiple observations per boundary;
- multiple UTC dates;
- weekday and weekend coverage;
- latency-distribution and tail analysis;
- provider-degradation or incident observations;
- separate methodology and production-safety review.

No future value is selected by this decision.

## 9. Next gate

The next gate is separate Phase 2D.2G activation/cutover authorization, preceded by Claude
High/Max merge-readiness review of the exact 2D.2F commit.
