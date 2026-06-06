# Task Board

## P0 - Phase 0 Validation

- [x] Create Phase 0 docs-only operating artifacts
  - Owner: Codex
  - Risk: R1 docs-only, contains R4 safety content requiring Claude review
  - Allowed files: `IMPLEMENTATION_SPEC.md`, `CLAUDE.md`, `AGENTS.md`, `AI/`, `DEBUG_PACK_EXAMPLE.md`, `DEPLOYMENT_CHECKLIST.md`, `RELEASE_GATE.md`, `ROLLBACK_PLAN.md`, `DISASTER_RECOVERY_RUNBOOK.md`, `CHANGELOG.md`
  - Verification: required file existence checks, scoped Git status/diff, secret heuristic scan, forbidden-scope term review

- [ ] Claude final review of Phase 0 safety-critical docs
  - Owner: Claude
  - Risk: R4 review content, no code
  - Allowed files: review comments or targeted edits only after user/Claude instruction
  - Verification: confirm blueprint alignment, hard-gate hierarchy, probability invariant, news authority, role model, security boundaries

- [ ] User approval to proceed to Phase 1A planning
  - Owner: User
  - Risk: R2/R3/R4 depending on next task
  - Allowed files: no files until task packet exists
  - Verification: explicit approval/handoff recorded

## P1 - Phase 1A Skeleton, Not Started

- [ ] Claude Phase 1A architecture/safety task packet
  - Owner: Claude
  - Risk: R2/R3 because auth/API/schema/deployment skeleton boundaries are involved
  - Allowed files: to be specified by Claude; likely includes app skeleton paths only after approval
  - Verification: written plan, allowed/forbidden files, rollback notes, test commands

- [ ] FastAPI/static frontend skeleton
  - Owner: Codex after Claude plan
  - Risk: R2/R3
  - Allowed files: to be assigned in Phase 1A task packet; not allowed during Phase 0
  - Verification: `TBD - finalized in Phase 1A`, plus `/healthcheck`, schema stub, auth shell, mode echo, no secret leak

- [ ] Stable schema stub and disabled news blocks
  - Owner: Codex after Claude plan
  - Risk: R2/R4 review because schema carries financial/news safety contract
  - Allowed files: to be assigned in Phase 1A task packet
  - Verification: schema validation, invariant fixture, `METRICS_ONLY` no-news behavior, Claude final review

- [ ] UI login/menu/input/cards/detail shell
  - Owner: Codex after Claude plan
  - Risk: R1/R2, with backend-authority contract review
  - Allowed files: to be assigned in Phase 1A task packet
  - Verification: frontend recomputes nothing, card detail opens correct `run_id`, heat labeled as signal intensity not risk

## Sprint 2 Backlog

- [ ] Wire live public Binance/OKX adapters plus real `data_quality`
  - Owner: Claude plan, then Codex implementation
  - Risk: R3/R4 data correctness and provider verification
  - Allowed files: to be specified by Claude Sprint 2 task packet
  - Verification: official source verification, no private/authenticated calls, fail-closed validation, fixture/live parity tests, and `is_live_data=true` only when verified public data is actually used

- [ ] Full hard-gating for liquidity/tail/execution
  - Owner: Claude plan, then Codex implementation
  - Risk: R4 financial-safety logic
  - Allowed files: to be specified by Claude Sprint 2 task packet
  - Verification: module-specific hard-gate thresholds, hard-gate seniority tests, non-constructive output under every breached gate

- [ ] Horizon-specific probability modeling for `H_primary` and `H_extended`
  - Owner: Claude plan, then Codex implementation
  - Risk: R4 quant logic
  - Allowed files: to be specified by Claude Sprint 2 task packet
  - Verification: invariant holds per horizon, deterministic fixtures, calibration labels remain honest
