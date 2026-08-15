# UCPE — Claude Code rules

Ultimate Crypto Probability Engine. **Analysis-only.** Operator is a non-coder.
Canonical doctrine: `docs/OPERATING_DOCTRINE.md` — read once per session; it is short.

## Role and context
Hold the loop: decompose tasks, delegate implementation to Codex via `./delegate.sh`, verify
with `./verify.sh`, review T2+ diffs, commit to a branch, update `STATE.md`. Do **not** do
ordinary implementation, test writing, repo search, hashing, or linting yourself.
Always-loaded context is `CLAUDE.md` · `AGENTS.md` · `STATE.md` and nothing else. Open
source, specs, `RELEASE_GATE.md`, and logs on demand. Pass paths, never file contents.

## Product invariants — never weaken these
1. Never add trading, order placement, withdrawal, transfer, leverage-changing, or autonomous execution capability.
2. Backend JSON is the source of truth. Frontend, detail view, and Dev Mode recompute nothing.
3. Hard gates outrank score and news. Sentiment-only action is forbidden; news can never override a hard gate or force `CONSTRUCTIVE`.
4. Probability invariant per horizon: `p_up_frac + p_down_frac + p_timeout_frac = 1.0`.
5. `CRYPTO_SPOT` is default. `CRYPTO_PERP` and derivatives intelligence are default-off, shadow-only, 0.0 decision influence.
6. Never expose secrets, plaintext access values, env dumps, provider keys, database URLs, or full article bodies.
7. Calibration honesty holds: no profitability claims; sample gates stay enforced.
8. The three safety scanners are mandatory in CI and must never be disabled or narrowed.

## Risk tiers — govern by irreversibility, not visibility
| Tier | Scope | Gate |
|---|---|---|
| T0 | docs, comments, `STATE.md` | `./verify.sh` |
| T1 | frontend, adapters, scripts, tests, refactors | `./verify.sh` + branch. No authorization, no model review. |
| T2 | `quant/` `gates/` `api/auth.py` `persistence/` `config/` `schemas/` `migrations/` (authored) | `./verify.sh` + new targeted test + **Claude reads the actual diff** |
| T3 | push to `origin`; **push to `hf` = deploy**; enable workflow; configure secret | **Owner authorizes, once per batch** |
| T4 | production DB writes; applying live migrations; release; key rotation | **Owner authorizes the specific action. One-shot, no rerun.** Raw capture before parsing. |

Never rerun a consumed T4 action. Never widen a task envelope from inside it.
Reject any diff touching paths outside the task's allowed set.

## Loop
```
STATE.md → ./verify.sh --preflight [required paths] → write .work/task-NNN.md
→ ./delegate.sh .work/task-NNN.md → read result JSON + `git diff --stat` only
→ ./verify.sh → review diff if T2+ → commit to branch → update STATE.md
```

## Budget per merged change
≤3 Opus turns · ≤4 Codex delegations · ≤1 owner interaction. If at risk, **stop and
re-partition** — do not spend more. Paid API cost target **$0**. Never silently
substitute a model; record any substitution in `STATE.md`.

## Failure handling
Preserve the first causal failure. Diagnose from the failing test, not the transcript. One
targeted repair. On a repeat of the same causal class: stop delegating, do root-cause →
sibling scan → downstream-consumer scan → regression test → one consolidated repair. Bound
at 2 attempts per causal class, then escalate. Never blind-retry.

## Escalate to owner only for
Product/scope decision · secret or credential · T3/T4 boundary · spending decision · causal
class unresolved after defect-class repair. Batch these. Never request a secret in chat or
in a file.

## Anti-regrowth
Six process artifacts maximum: `CLAUDE.md` `AGENTS.md` `STATE.md` `verify.sh` `delegate.sh`
`docs/OPERATING_DOCTRINE.md`. No orchestrator, no control plane, no agent team, no parallel
subagents, no recurring evidence machinery. If they exceed ten, **delete the excess — do
not refactor it.**
