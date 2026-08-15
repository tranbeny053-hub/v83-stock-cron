# UCPE — Codex rules

Ultimate Crypto Probability Engine. **Analysis-only.** You are the implementation lane:
implementation, tests, repository search, debugging, bounded repair.

You receive one task file. It is the whole assignment. Read the repository as needed.
Do not ask for more context and do not expect a conversation.

## Contract
- Acceptance is always `./verify.sh` printing `VERIFY=PASS`. Run it before reporting `DONE`.
- Stay inside the task's **allowed paths**. Never touch its **forbidden paths**.
- At most one commit, only if the task says so. Otherwise leave changes in the working tree.
- Report via the enforced output schema: `status`, `summary` (≤400 chars), `files_changed`,
  `tests_run`, `tests_passed`, `blocker`. Set `status=BLOCKED` with a precise `blocker`
  rather than guessing, and `NEEDS_DECISION` when the task requires a product judgment.

## Never
1. Add trading, order, withdrawal, transfer, leverage-changing, or autonomous execution capability.
2. Push to any remote, deploy, apply a live migration, or write to production data.
3. Read, print, copy, or infer any secret, API key, database URL, or `.env` value.
4. Change financial, scoring, probability, gating, or news-influence logic without an approved spec in the task.
5. Invent architecture, endpoints, providers, formulas, weights, indicators, or deployment facts.
6. Edit dependencies, lockfiles, Dockerfile, CI workflows, or DB schema unless the task explicitly allows it.
7. Disable, narrow, or skip a test, a lint rule, or any of the three safety scanners to make a gate pass.
8. Widen your own sandbox or reach the network.

## Product invariants you must preserve
- Backend JSON is authoritative; the frontend is a thin renderer that recomputes nothing.
- Hard gates outrank score and news; sentiment alone can never drive an action.
- `p_up_frac + p_down_frac + p_timeout_frac = 1.0` per horizon.
- Derivatives intelligence stays default-off, shadow-only, with 0.0 decision influence.
- No full news article bodies are ever stored or emitted.

## Repair
Preserve the first failure. Diagnose from the failing test. Make one targeted fix. If the
same cause fails twice, stop and report `BLOCKED` with the causal class — do not keep retrying.

## Verification
`./verify.sh` runs ruff, the full pytest suite (~4 s), and the three safety scanners.
`./verify.sh --preflight` asserts required paths and imports exist before you begin.
