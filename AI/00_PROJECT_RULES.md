# Project Rules

Status: Phase 0 artifact extraction. This file needs CLAUDE FINAL REVIEW before it becomes canonical.

## Permanent Rules

- User is a non-coder approver/operator.
- Blueprint v1.2.2 is the highest product, architecture, security, quant, news, and deployment source of truth.
- Phase 0 is docs only. Do not build app code during Phase 0.
- Repo docs, tests, and Git are source of truth; chat history is not durable state.
- No "done", "fixed", or "working" claim without verification evidence.
- Keep changes small, scoped, reversible, and recorded in `AI/03_CURRENT_STATE.md` and `AI/05_HANDOFF.md`.

## Analysis-Only Boundary

The app provides deterministic crypto analysis and decision support only. It must not create any executable financial action.

Forbidden implementation-scope terms:

```text
place_order
create_order
submit_order
cancel_order
order_manager
order_router
execution_engine
autonomous_execution
auto_trade
withdraw
withdrawal
transfer_funds
internal_transfer
sapi_withdraw
enable_trading
trade_permission
margin_borrow
leverage_set
```

These terms may appear only in explicit documentation-only scope sections or isolated checker-test fixtures excluded from production scan.

## Hard Product Invariants

- Backend JSON is authoritative; frontend, detail view, and Dev Mode recompute nothing.
- `CRYPTO_SPOT` is default.
- `CRYPTO_PERP` is off by default and requires env flag plus per-request opt-in.
- `METRICS_ONLY` is default and must fetch no news.
- `NEWS_ADDON` is advisory and never overrides hard gates.
- Sentiment-only action is forbidden.
- News cannot force `CONSTRUCTIVE` or `CONSTRUCTIVE_CAUTIOUS`.
- Probability invariant per horizon: `p_up_frac + p_down_frac + p_timeout_frac = 1.0`.
- heat = signal intensity, not risk.
- No secrets, plaintext access codes, full env dumps, database URLs, provider keys, or full article bodies in repo, logs, frontend, Dev Mode, or exports.
- No backend LLM in score, probability, gate, or news-influence path.

## Gate Hierarchy

```text
DATA INTEGRITY (schema/coherence/freshness/quote-asset peg)
  > PROVIDER HEALTH + CROSS-PROVIDER CONFLICT
  > EPISTEMIC SUFFICIENCY
  > EXCHANGE / SYSTEM HEALTH (maintenance/halt/kill-switch/shelter)
  > LIQUIDITY / DEPTH / SPREAD VIABILITY
  > ABNORMAL VOLATILITY / TAIL RISK
  > DERIVATIVES RISK (only if CRYPTO_PERP)
  > EXECUTION REALISM
  > PORTFOLIO / RISK ASSUMPTIONS (if provided)
  > QUANT PROBABILITY + NEWS-MODULATED SCORE STACK
  > FINAL DISPOSITION
```

No score, probability, catalyst, news item, narrative, arbiter modifier, or display may override a failed hard gate.

## Source Verification

All provider/API/news/macro/source specifics remain `TO_VERIFY` until checked against current official documentation. If a source row is not verified, implementation may only be abstract, stubbed, fixture-backed, disabled, or shadow. No paid provider is mandatory for Phase 1A.

## Definition of Done

A task is done only when:
- requested behavior or artifact exists, or the blocker is clearly explained;
- changed files are listed;
- files read but not changed are listed when relevant;
- relevant checks were run or attempted;
- pass/fail/not-run results are recorded with reasons;
- risks, remaining unknowns, and rollback considerations are listed;
- `AI/03_CURRENT_STATE.md` is updated;
- `AI/05_HANDOFF.md` is updated;
- the user receives a short non-technical summary.

## Do Not Touch Without Explicit Approval

- secrets, `.env`, access codes, API keys, DB URLs;
- dependencies, lockfiles, deployment config, migrations;
- financial formulas, probability weights, scoring logic, news influence;
- auth, DB, deployment, persistence, or recovery logic;
- destructive Git or filesystem operations;
- provider/source implementations whose verification fields remain `TO_VERIFY`.

