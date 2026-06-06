# Project: Ultimate Crypto Probability Engine - Codex Rules

Role: Implementation Engineer / Scoped Feature Builder / QA Engineer / Test Runner / Regression Checker / Codebase Explorer / Documentation-Handoff Maintainer / Parallel Executor.

Before coding or editing, read:
- `AGENTS.md`
- `AI/00_PROJECT_RULES.md`
- `AI/01_BLUEPRINT_SUMMARY.md`
- `AI/03_CURRENT_STATE.md`
- `AI/04_TASK_BOARD.md`
- `AI/05_HANDOFF.md`
- `AI/06_TEST_COMMANDS.md`
- `IMPLEMENTATION_SPEC.md` when product contract context is needed

Always:
1. Confirm task scope, risk level, allowed files, forbidden files, and verification commands.
2. Implement only the requested scoped task.
3. Do not invent architecture, endpoints, providers, formulas, weights, indicators, or deployment facts.
4. Do not change financial/scoring/probability/news-influence logic without Claude-approved spec.
5. Do not edit secrets, `.env`, API keys, production config, deployment config, dependencies, lockfiles, or DB schema without explicit approval.
6. Do not touch files assigned to another active agent; use isolated branches/worktrees for parallel work.
7. Keep frontend a thin renderer of backend JSON.
8. Run or attempt relevant lint/type/build/test/smoke checks and record results.
9. Update `AI/03_CURRENT_STATE.md` and `AI/05_HANDOFF.md` after meaningful work.
10. List files changed, files read but not changed, risks, and next steps.
11. Provide a short non-technical summary for the user.

This repo is analysis-only. Any executable trading, withdrawal, transfer, leverage-changing, or autonomous execution capability is forbidden.
