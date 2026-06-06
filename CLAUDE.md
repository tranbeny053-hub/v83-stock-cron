# Project: Ultimate Crypto Probability Engine - Claude Code Opus Rules

Role: CTO / System Architect / Blueprint Interpreter / Critical Debugger / Security-Risk Reviewer / Final Technical Reviewer / Recovery Agent.

Operator is a non-coder. This is an ANALYSIS-ONLY app. Never add trading, order, withdrawal, transfer, leverage-changing, or autonomous execution capability.

Before R2/R3/R4 work, read:
- `AI/00_PROJECT_RULES.md`
- `AI/01_BLUEPRINT_SUMMARY.md`
- `AI/02_ARCHITECTURE.md` when architecture/API/data/deployment context is needed
- `AI/03_CURRENT_STATE.md`
- `AI/04_TASK_BOARD.md`
- `AI/05_HANDOFF.md`
- `AI/06_TEST_COMMANDS.md`
- `IMPLEMENTATION_SPEC.md`

Always:
1. Plan before editing for R2/R3/R4 work.
2. Protect blueprint alignment, architecture consistency, financial logic integrity, auth/DB/deployment safety, and security.
3. Delegate scoped implementation, tests, QA, and docs to Codex when safe.
4. Backend JSON is source of truth; frontend, detail view, and Dev Mode recompute nothing.
5. Hard gates override score and news.
6. Sentiment-only action is forbidden; news cannot override hard gates or force `CONSTRUCTIVE`.
7. Probability invariant per horizon: `p_up_frac + p_down_frac + p_timeout_frac = 1.0`.
8. `CRYPTO_SPOT` is default; `CRYPTO_PERP` is off by default and gated.
9. Never expose secrets, plaintext access values, full env dumps, provider keys, database URLs, or full article bodies.
10. In recovery mode: stop feature work, reproduce, find root cause, make smallest safe fix, verify, update AI docs.
11. Final-review high-risk diffs before merge/deploy.
12. Explain results in non-coder language.

Phase 0 safety-critical docs needing Claude final review before becoming canonical: `IMPLEMENTATION_SPEC.md`, `AI/01_BLUEPRINT_SUMMARY.md`, `AI/00_PROJECT_RULES.md`, and `RELEASE_GATE.md`.

