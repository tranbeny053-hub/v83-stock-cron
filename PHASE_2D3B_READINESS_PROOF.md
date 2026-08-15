# Phase 2D.3B Read-Only Readiness-Proof Packet

## 1. Status and authorization

```text
phase = 2D.3B
status = READ_ONLY_PROOF_PACKET_NOT_EXECUTED
runtime source base = a34aafa807a609e477d3fb8950c94567087046e3
scheduler = github-cron/main @ 676fafbe74235ba3d051e03c6165810ef78030df
HF = origin/main @ 30d4982903e6f44e063616bc3f03f334bd2544e2
```

Proof implementation is authorized. Proof execution, diagnostic dispatch, and production write
are not authorized. The locked write-confirmation value is omitted. A readiness `PASS` is evidence
only and does not authorize execution.

## 2. Candidate window

```text
reference close Vietnam = 2026-07-17 11:00 Asia/Ho_Chi_Minh
reference close UTC = 2026-07-17T04:00:00Z

admissible capture band Vietnam = 2026-07-17 11:05-11:20 Asia/Ho_Chi_Minh
admissible capture band UTC = 2026-07-17T04:05:00Z-04:20:00Z

provisional diagnostic dispatch Vietnam = 2026-07-17 11:05-11:08 Asia/Ho_Chi_Minh
provisional diagnostic dispatch UTC = 2026-07-17T04:05:00Z-04:08:00Z

provisional write dispatch band Vietnam = 2026-07-17 11:06-11:10 Asia/Ho_Chi_Minh
provisional write dispatch band UTC = 2026-07-17T04:06:00Z-04:10:00Z

hard write-dispatch stop Vietnam = 2026-07-17 11:12 Asia/Ho_Chi_Minh
hard write-dispatch stop UTC = 2026-07-17T04:12:00Z
```

All times are provisional and require a separately locked authorization predicate.

## 3. Identity-proof Terminal block

Run only from the Git toplevel after a later authorization packet supplies and locks
`EXPECTED_GOVERNANCE_HEAD`. This block is read-only.

```bash
set -euo pipefail
export PATH="/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
export GIT_PAGER=cat
export PAGER=cat

: "${EXPECTED_GOVERNANCE_HEAD:?BLOCK: EXPECTED_GOVERNANCE_HEAD is required}"
case "${EXPECTED_GOVERNANCE_HEAD}" in
  [0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f]) ;;
  *) printf '%s\n' 'BLOCK: invalid EXPECTED_GOVERNANCE_HEAD' >&2; exit 1 ;;
esac

EXPECTED_TOPLEVEL='/Users/kha/Documents/New project'
PROJECT='v8-crypto-api-clean'
MERGE_BASE='7d2b1e49d4a7c13778791fda45762a72696414fb'
RUNTIME_BASE='a34aafa807a609e477d3fb8950c94567087046e3'
RUNTIME_TAG='wave-4d3-ops-2d2g-cadence-activation-t'
EXPECTED_SCHEDULER='676fafbe74235ba3d051e03c6165810ef78030df'
EXPECTED_HF='30d4982903e6f44e063616bc3f03f334bd2544e2'
WORKFLOW="${PROJECT}/.github/workflows/derivatives-evidence-cadence.yml"

actual_toplevel="$(git rev-parse --show-toplevel)"
test "${actual_toplevel}" = "${EXPECTED_TOPLEVEL}" || { printf '%s\n' 'BLOCK: toplevel'; exit 1; }
cd "${actual_toplevel}"

actual_branch="$(git branch --show-current)"
actual_head="$(git rev-parse HEAD)"
test "${actual_head}" = "${EXPECTED_GOVERNANCE_HEAD}" || {
  printf '%s\n' 'BLOCK: governance head'; exit 1;
}
git merge-base --is-ancestor "${MERGE_BASE}" "${actual_head}"

while IFS= read -r changed_path; do
  test -z "${changed_path}" && continue
  case "${changed_path}" in
    "${PROJECT}/PHASE_2D3B_READINESS_PROOF.md"|\
    "${PROJECT}/sql/phase_2d3b_readiness_proof.sql"|\
    "${PROJECT}/tests/docs/test_phase_2d3b_readiness_proof.py") ;;
    *) printf '%s\n' 'BLOCK: unapproved governance drift'; exit 1 ;;
  esac
done < <(git diff --name-only "${MERGE_BASE}..${actual_head}")

runtime_paths=(
  "${PROJECT}/src"
  "${PROJECT}/scripts"
  "${PROJECT}/.github/workflows"
  "${PROJECT}/migrations"
  "${PROJECT}/schemas"
  "${PROJECT}/ops"
  "${PROJECT}/frontend"
  "${PROJECT}/Dockerfile"
  "${PROJECT}/requirements.txt"
  "${PROJECT}/pyproject.toml"
)
git diff --quiet "${RUNTIME_BASE}..${actual_head}" -- "${runtime_paths[@]}"
test "$(git rev-parse "${RUNTIME_TAG}^{}")" = "${RUNTIME_BASE}" || {
  printf '%s\n' 'BLOCK: runtime tag'; exit 1;
}
test -z "$(git status --porcelain --untracked-files=all -- "${PROJECT}")" || {
  printf '%s\n' 'BLOCK: project subtree dirty'; exit 1;
}
test "$(git rev-parse "${RUNTIME_BASE}:${WORKFLOW}")" = \
  "$(git rev-parse "${actual_head}:${WORKFLOW}")" || {
  printf '%s\n' 'BLOCK: collector workflow drift'; exit 1;
}

WORKFLOW_PATH="${WORKFLOW}" python3 - <<'PY'
import os
from pathlib import Path

lines = Path(os.environ["WORKFLOW_PATH"]).read_text(encoding="utf-8").splitlines()
try:
    start = next(index for index, line in enumerate(lines) if line == "on:")
except StopIteration:
    raise SystemExit("BLOCK: workflow trigger block missing")
trigger_lines = []
for line in lines[start + 1 :]:
    if line and not line.startswith((" ", "\t")):
        break
    trigger_lines.append(line)
trigger_text = "\n".join(trigger_lines)
if "  workflow_dispatch:" not in trigger_text:
    raise SystemExit("BLOCK: workflow_dispatch missing")
if "  schedule:" in trigger_text or "cron:" in trigger_text:
    raise SystemExit("BLOCK: scheduled trigger present")
PY

scheduler_head="$(git ls-remote --heads github-cron main | awk '$2 == "refs/heads/main" {print $1}')"
hf_head="$(git ls-remote --heads origin main | awk '$2 == "refs/heads/main" {print $1}')"
test "${scheduler_head}" = "${EXPECTED_SCHEDULER}" || {
  printf '%s\n' 'BLOCK: scheduler SHA'; exit 1;
}
test "${hf_head}" = "${EXPECTED_HF}" || { printf '%s\n' 'BLOCK: HF SHA'; exit 1; }

printf 'branch=%s\n' "${actual_branch}"
printf 'governance_head=%s\n' "${actual_head}"
printf 'runtime_source_base=%s\n' "${RUNTIME_BASE}"
printf 'scheduler_main=%s\n' "${scheduler_head}"
printf 'hf_main=%s\n' "${hf_head}"
printf '%s\n' 'PASS_IDENTITY=PASS'
```

## 4. Database proof instructions

Only after separate proof-execution authorization, anh Kha runs
`sql/phase_2d3b_readiness_proof.sql` in Supabase SQL Editor and returns only its single sanitized
JSON result. No secret, connection string, or privileged credential may be pasted into chat.

Required JSON contract and blocking rules:

| Object | Required keys | Expected result | Block when |
|---|---|---|---|
| root | `schema_version`, `captured_at_utc`, `authority`, `transaction`, `rls`, `migration_contract`, `append_only_contract`, `role_privileges`, `candidate_contract`, `baseline_counts`, `clause_results`, `database_proof_result` | schema v1 and `database_proof_result=PASS` | any key is absent, null, unknown, or result is not `PASS` |
| `authority` | `current_user`, `session_user`, `current_role_is_superuser`, `current_role_bypasses_rls`, `authoritative_visibility` | identities present; authoritative visibility true | visibility is false or identity is absent |
| `transaction` | `txn_read_only`, `txn_isolation` | `on`; `repeatable read` | either value differs |
| `rls` | `predictions_owner`, `predictions_current_role_is_owner`, `predictions_rls_enabled`, `predictions_rls_forced`, `predictions_policy_count`, `pds_owner`, `pds_current_role_is_owner`, `pds_rls_enabled`, `pds_rls_forced`, `pds_policy_count` | bounded catalog facts consistent with authoritative visibility | table/owner visibility is missing or contradicts authority |
| `migration_contract` | `mig_0006_ok`, `mig_0007_ok`, `origin_contract_ok` | all true | any false or null |
| `append_only_contract` | three named trigger booleans and `pds_reject_triggers_enabled_count` | all true; count 3 | any trigger is absent/disabled or count differs |
| `role_privileges` | `service_role_exists`, `service_role_select`, `service_role_insert`, `service_role_update`, `service_role_delete`, `service_role_truncate` | true, true, true, false, false, false | role missing or any privilege differs |
| `candidate_contract` | `candidate_normalized_symbol`, `candidate_normalized_symbol_contract_source`, `candidate_reference_close_utc` | `BTC/USDT`; source trace present; `2026-07-17T04:00:00Z` | any value differs |
| `baseline_counts` | all eleven governed counts | `0,0,0,0,0,8,2,0,0,0,0` in documented key order | any measured count differs or is missing |
| `clause_results` | authority, transaction, migration, origin, append-only, privilege, v1-zero, candidate, v0, overlap, and v0-safety clauses | every value true | any value is false, null, missing, or unknown |

The governed baseline keys are `v1_snapshots`, `v1_distinct_predictions`,
`v1_scheduled_shadow_snapshots`, `v1_orphans`, `candidate_identity_occupied`, `v0_snapshots`,
`v0_scheduled_shadow_snapshots`, `v0v1_semantic_overlap`, `v0_non_shadow_influence`,
`v0_nonzero_or_unparseable_influence`, and `v0_duplicate_prediction_groups`.

## 5. Live OKX proof design

The existing reviewed diagnostic and manual-only workflow are the proof source. The intended,
still-unauthorized contract is:

```text
workflow UI name = Derivatives Cadence Readiness Diagnostic
visible workflow input names = none
symbol = BTC/USDT
timeframe = ALL
max cells = 2
expected runner identity = github-hosted-ubuntu
required selection flags = --symbol "BTC/USDT" --timeframe ALL --max-cells 2
existing identity flags = --source-commit-sha <locked SHA> --runner-identity-class github-hosted-ubuntu
```

The current workflow command supplies only the two identity flags and therefore defaults to
`symbol=ALL`, `timeframe=ALL`, and `max_cells=4`. It cannot represent the required two-cell
contract through visible inputs. Readiness must be `BLOCK` unless a separately reviewed,
authorization-locked mechanism supplies the exact selection flags without unreviewed source or
workflow drift. This packet gives no click or dispatch instruction.

The sanitized diagnostic evidence must prove both BTC cells and all of the following:

- Instrument `BTC-USDT-SWAP`, live SWAP, USDT-linear.
- Current funding and open interest with exactly:
  `okx.funding.current_estimate`, `okx.open_interest.current.contracts`,
  `okx.open_interest.current.base`, and `okx.open_interest.current.usd`.
- Finite valid values, fresh and ordered timestamps, no-lookahead, and provider `ACTIVE`.
- Canonical close exactly `2026-07-17T04:00:00Z` and completion offset from 300 through 1200
  seconds, inclusive; the 1H bound controls the shared window.
- Funding interval derived from live `fundingTime` and `nextFundingTime` fields. Any settlement or
  unsafe funding boundary in the protected interval yields `UNSAFE_FUNDING_BOUNDARY`.
- Exact two-cell budget: three derivatives requests, two candle requests, one server-time
  request, six logical requests total, six HTTP attempts maximum, and zero Binance requests.
- Closed allowlisted output only. Unknown, missing, contradictory, or extra evidence blocks.

This implementation performs no provider request.

## 6. Timing sequence

1. Claude locks the exact governance HEAD, database expected baseline, and mechanical reducer
   before the candidate window.
2. Identity proof passes.
3. Authoritative database proof passes.
4. A separately authorized write-free GitHub diagnostic captures representative live OKX
   evidence.
5. The mechanical reducer evaluates the evidence.
6. A quick authoritative v1-zero reconfirmation occurs.
7. Production write is considered only if every predicate passes, exact execution authorization
   already exists, and current time is before the hard stop.

A fresh Claude review cannot safely fit between live capture and the hard stop. Any future
execution therefore requires a pre-authorized, fully enumerated fail-closed predicate.

## 7. Combined evidence contract

The combined evidence object has exactly these top-level keys:

```text
schema_version
capture_started_utc
capture_completed_utc
candidate_reference_close_utc
governance_head
runtime_source_base
identity_proof
database_proof
okx_proof
window_compliance
operator_ready
locked_confirmation_present
explicit_non_actions
readiness
```

The mechanical reducer sets `readiness = PASS` only when identity, database, OKX, and window
proofs all pass; operator readiness is true; locked-confirmation presence is false; the exact key
set matches; and no value is missing, null, unknown, extra, or contradictory. Every other input
sets `readiness = BLOCK`. A `PASS` remains evidence and never implies execution authorization.

## 8. Blocking classifications

```text
IDENTITY_MISMATCH
UNEXPECTED_SOURCE_DRIFT
SCHEDULER_SHA_MISMATCH
HF_SHA_MISMATCH
WORKFLOW_NOT_MANUAL_ONLY
NON_AUTHORITATIVE_DB_VISIBILITY
DB_TRANSACTION_CONTRACT_FAILED
MIGRATION_CONTRACT_FAILED
APPEND_ONLY_CONTRACT_FAILED
ROLE_PRIVILEGE_CONTRACT_FAILED
V1_BASELINE_NOT_ZERO
V0_BASELINE_CHANGED
SEMANTIC_OVERLAP
CANDIDATE_IDENTITY_OCCUPIED
PROVIDER_UNAVAILABLE
PROVIDER_DEGRADED
INSTRUMENT_MISMATCH
MISSING_METRIC
NONFINITE_METRIC
TIMESTAMP_INVALID
NO_LOOKAHEAD_FAILED
UNSAFE_FUNDING_BOUNDARY
REQUEST_BUDGET_EXCEEDED
UNEXPECTED_PROVIDER
OUTSIDE_CAPTURE_WINDOW
OPERATOR_NOT_READY
LOCKED_CONFIRMATION_PRESENT
UNKNOWN_OR_MISSING_FIELD
```

## 9. Authorization matrix

```text
local documentation/SQL/test implementation = YES
local feature-branch commit = YES

proof execution = NO
SQL execution = NO
live OKX request = NO
diagnostic workflow dispatch/rerun = NO
local merge = NO
tag = NO
push/deploy = NO
production write = NO
DB mutation/migration = NO
HF mutation = NO
Decision influence = NO
```

## 10. Next gate

```text
Claude HIGH read-only review of the exact committed Phase 2D.3B packet
to lock the fail-closed predicate.

No proof execution, diagnostic dispatch or production write.
```
