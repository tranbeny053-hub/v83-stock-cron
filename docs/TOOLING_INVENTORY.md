# Tooling inventory
ACTIVE_GATE: verification checks and push/PR workflows; ACTIVE_RELEASE: release and rollback machinery.
ACTIVE_JOB: scheduled or repeatable dispatch jobs; ACTIVE_OWNER_TOOL: local helpers and repeatable owner procedures.
ACTIVE_PIN: gate/test pins, locks and baselines; REHEARSAL: scratch-PostgreSQL support without production effect.
HISTORICAL_CONSUMED: completed one-shot actions, NEVER rerun; STATE.md governs.
HISTORICAL_REFERENCE: reproduction/audit material outside current loops; UNVERIFIED: class not established.
Touches records the strongest supported target, including guarded modes; a pin itself is local.
Consumed production routes retain offline helpers and scratch rehearsal modes without authorizing a production rerun.
tests/docs/test_tooling_inventory.py keeps the tables complete and checks classes, evidence and workflow triggers.


## Scripts

| Path | Class | Trigger | Touches | Evidence |
| --- | --- | --- | --- | --- |
| `scripts/a4_card04_companion_rehearsal/` | REHEARSAL | a4-card04-companion-rehearsal.yml | scratch PG | Scratch PostgreSQL 17.6 build, probe roles and rehearsal invoked by .github/workflows/a4-card04-companion-rehearsal.yml; a local run uses the same scripts. |
| `scripts/a4_ledger_audit_rehearsal/` | REHEARSAL | a4-ledger-audit-rehearsal.yml | scratch PG | Scratch probe role and rehearsal invoked by .github/workflows/a4-ledger-audit-rehearsal.yml. |
| `scripts/apply_migration_0008.py` | HISTORICAL_CONSUMED | none (production apply consumed; scratch rehearse only where supported) | production DB | STATE.md: '0008 was applied once, 2026-09-16 (run 35164080476).' (never rerun). |
| `scripts/apply_migration_0010.py` | HISTORICAL_CONSUMED | none (production apply consumed; scratch rehearse only where supported) | production DB | STATE.md: 'The owner-authorized 0010 T4 is CONSUMED and VERIFIED: run 35190794876 (BATCH_0010).' (never rerun). |
| `scripts/apply_migration_0011.py` | HISTORICAL_CONSUMED | none (production apply consumed; scratch rehearse only where supported) | production DB | STATE.md: 'APPLY-MIGRATION-0011-ONCE is CONSUMED and PASSED: run 36583531813 on main b11a8e53, committed.' (never rerun). |
| `scripts/apply_migration_0012.py` | HISTORICAL_CONSUMED | none (production apply consumed; scratch rehearse only where supported) | production DB | STATE.md: 'APPLY-MIGRATION-0012-ONCE is CONSUMED and PASSED: run 36586262979 on main b11a8e53, committed.' (never rerun). |
| `scripts/apply_migration_0013.py` | HISTORICAL_CONSUMED | none (production apply consumed; scratch rehearse only where supported) | production DB | STATE.md: 'Migration 0013 is APPLIED (T4, CONSUMED, PASS; run 36820986264).' (never rerun). |
| `scripts/apply_migration_0014.py` | HISTORICAL_CONSUMED | none (production apply consumed; scratch rehearse only where supported) | production DB | STATE.md: 'run 36952902214 (workflow_dispatch on main at 46a1de68, attempt 1). It is consumed: never rerun.' (never rerun). |
| `scripts/apply_migration_0015.py` | HISTORICAL_CONSUMED | none (production apply consumed; scratch rehearse only where supported) | production DB | STATE.md: '**T4-1, the 0015 apply, is CONSUMED.**' (never rerun). |
| `scripts/apply_migration_0016.py` | HISTORICAL_CONSUMED | none (production apply consumed; scratch rehearse only where supported) | production DB | STATE.md: '**0016: run 37110330500**, APPLIED and committed,' (never rerun). |
| `scripts/apply_migration_0017.py` | HISTORICAL_CONSUMED | none (production apply consumed; scratch rehearse only where supported) | production DB | STATE.md: '**0017: run 37110375659**, APPLIED and committed.' (never rerun). |
| `scripts/apply_migration_0018.py` | HISTORICAL_CONSUMED | none (production apply consumed; scratch rehearse only where supported) | production DB | STATE.md: '**D6: COMPLETE.** 0018 is APPLIED (run 37172530166,' (never rerun). |
| `scripts/apply_migrations.py` | HISTORICAL_REFERENCE | tests only | production DB | docs/automation/F1_NODE_CLASSIFICATION.md excludes this ledgerless bulk runner from current apply routes. |
| `scripts/apply_section_5a_seal.py` | HISTORICAL_CONSUMED | none (production route consumed; offline support remains) | production DB | STATE.md: 'The 0009 route: 34851608514 (refused before any DB contact) and 34861816985 (applied). Never dispatch it again.' (never rerun). |
| `scripts/audit_rehearsal/` | REHEARSAL | audit-table-privileges-rehearsal.yml | scratch PG | Scratch fixtures/probes invoked by .github/workflows/audit-table-privileges-rehearsal.yml. |
| `scripts/audit_table_privileges.py` | HISTORICAL_REFERENCE | audit-table-privileges.yml (owner dispatch) | production DB | A read-only catalog audit, not a write: STATE.md records the older-table audit, run 35120616278; no current loop runs it. |
| `scripts/calibration_report.py` | HISTORICAL_REFERENCE | owner-local | production DB | Reads production predictions, probabilities included (build_operator_repository); that touches the protected §5A window and H2's production rows, so a run is an owner decision. |
| `scripts/check_build_info.py` | ACTIVE_GATE | verify.sh (pytest) | local | Invoked by tests/scripts/test_check_build_info.py under verify.sh. |
| `scripts/check_no_forbidden_scope.py` | ACTIVE_GATE | verify.sh | local | Invoked by verify.sh as an offline acceptance gate. |
| `scripts/check_no_full_article_body.py` | ACTIVE_GATE | verify.sh | local | Invoked by verify.sh as an offline acceptance gate. |
| `scripts/check_no_secrets.py` | ACTIVE_GATE | verify.sh | local | Invoked by verify.sh as an offline acceptance gate. |
| `scripts/collect_derivatives_evidence.py` | ACTIVE_JOB | derivatives-evidence-cadence.yml | production DB | Invoked by .github/workflows/derivatives-evidence-cadence.yml. |
| `scripts/collect_oos_pair_evidence.py` | HISTORICAL_REFERENCE | none (closed window; owner decision to re-enable) | production DB | .github/workflows/oos-pair-evidence.yml records the closed holdout and disabled schedule. |
| `scripts/core_write_inventory.py` | ACTIVE_JOB | core-write-inventory.yml | production DB | Invoked by .github/workflows/core-write-inventory.yml. |
| `scripts/core_write_inventory_rehearsal/` | REHEARSAL | core-write-inventory-rehearsal.yml | scratch PG | Scratch fixtures/probes invoked by .github/workflows/core-write-inventory-rehearsal.yml. |
| `scripts/diagnose_binance_registry.py` | ACTIVE_JOB | derivatives-registry-diagnostic.yml | external read-only | Invoked by .github/workflows/derivatives-registry-diagnostic.yml. |
| `scripts/evaluate_section_5a.py` | HISTORICAL_CONSUMED | none (production route consumed; offline support remains) | production DB | STATE.md: 'The §5A ONE LOOK, consume run 34919367341 (1d8f933, population f83c31f7…).' (never rerun). |
| `scripts/live_smoke.py` | ACTIVE_OWNER_TOOL | owner-local | external read-only | scripts/live_smoke.py documents or exercises this opt-in owner CLI. |
| `scripts/make_access_hash.py` | ACTIVE_OWNER_TOOL | owner-local | local | scripts/make_access_hash.py documents or exercises this opt-in owner CLI. |
| `scripts/manual_smoke.py` | ACTIVE_GATE | verify.sh | local | Invoked by verify.sh as an offline acceptance gate. |
| `scripts/measure_okx_cadence_readiness.py` | ACTIVE_JOB | derivatives-cadence-readiness-diagnostic.yml | external read-only | Invoked by .github/workflows/derivatives-cadence-readiness-diagnostic.yml. |
| `scripts/migration_0010_rehearsal/` | REHEARSAL | apply-migration-0010-rehearsal.yml | scratch PG | Scratch fixtures/probes invoked by .github/workflows/apply-migration-0010-rehearsal.yml. |
| `scripts/migration_0011_rehearsal/` | REHEARSAL | apply-migration-0011.yml | scratch PG | Scratch fixtures/probes invoked by .github/workflows/apply-migration-0011.yml. |
| `scripts/migration_0012_rehearsal/` | REHEARSAL | apply-migration-0012.yml | scratch PG | Scratch fixtures/probes invoked by .github/workflows/apply-migration-0012.yml. |
| `scripts/migration_0013_rehearsal/` | REHEARSAL | migration-0015-rehearsal.yml | scratch PG | Scratch fixtures/probes invoked by .github/workflows/migration-0015-rehearsal.yml. |
| `scripts/migration_0014_rehearsal/` | REHEARSAL | migration-0014-rehearsal.yml | scratch PG | Scratch fixtures/probes invoked by .github/workflows/migration-0014-rehearsal.yml. |
| `scripts/migration_0015_rehearsal/` | REHEARSAL | migration-0015-rehearsal.yml | scratch PG | Scratch fixtures/probes invoked by .github/workflows/migration-0015-rehearsal.yml. |
| `scripts/migration_0016_rehearsal/` | REHEARSAL | migration-0016-rehearsal.yml | scratch PG | Scratch fixtures/probes invoked by .github/workflows/migration-0016-rehearsal.yml. |
| `scripts/migration_0017_rehearsal/` | REHEARSAL | migration-0018-rehearsal.yml | scratch PG | Scratch fixtures/probes invoked by .github/workflows/migration-0018-rehearsal.yml. |
| `scripts/migration_0018_rehearsal/` | REHEARSAL | migration-0018-rehearsal.yml | scratch PG | Scratch fixtures/probes invoked by .github/workflows/migration-0018-rehearsal.yml. |
| `scripts/news_live_smoke.py` | ACTIVE_OWNER_TOOL | owner-local | external read-only | scripts/news_live_smoke.py documents or exercises this opt-in owner CLI. |
| `scripts/persistence_rehearsal/` | REHEARSAL | persistence-rehearsal.yml | scratch PG | Scratch fixtures/probes invoked by .github/workflows/persistence-rehearsal.yml. |
| `scripts/privilege_rehearsal/` | REHEARSAL | privilege-rehearsal.yml | scratch PG | Scratch fixtures/probes invoked by .github/workflows/privilege-rehearsal.yml. |
| `scripts/production_smoke.py` | ACTIVE_OWNER_TOOL | owner-local | HF Space | scripts/production_smoke.py documents or exercises this opt-in owner CLI. |
| `scripts/quant_v2_validation_report.py` | HISTORICAL_REFERENCE | owner-local | production DB | Reads production predictions, probabilities included (build_operator_repository); that touches the protected §5A window and H2's production rows, so a run is an owner decision. |
| `scripts/release.py` | ACTIVE_RELEASE | owner-local | HF Space | docs/runbooks/RELEASE.md and docs/runbooks/ROLLBACK.md invoke the guarded release chain. |
| `scripts/reproducible_build.sh` | ACTIVE_GATE | reproducible-build.yml | CI only | Invoked by .github/workflows/reproducible-build.yml for two clean builds and fixture smoke. |
| `scripts/restore_proof/` | REHEARSAL | restore-proof-rehearsal.yml | scratch PG | DP-D structure-first restore proof: export gate, catalog fingerprint, private socket-only scratch clusters; prove.py checks the owner's export (docs/runbooks/RESTORE_PROOF_EXPORT.md) and rehearse.py is invoked by .github/workflows/restore-proof-rehearsal.yml; a local run uses the same scripts. |
| `scripts/resolve_outcomes.py` | ACTIVE_JOB | resolve-outcomes.yml | production DB | Invoked by .github/workflows/resolve-outcomes.yml. |
| `scripts/resolver_credential.py` | ACTIVE_OWNER_TOOL | owner-local | local | docs/runbooks/RESOLVER_CUTOVER.md documents or exercises this opt-in owner CLI. |
| `scripts/source_integrity_guard.py` | ACTIVE_JOB | source-integrity-guard.yml | HF Space | Invoked by .github/workflows/source-integrity-guard.yml. |
| `scripts/space_db_credential.py` | ACTIVE_OWNER_TOOL | owner-local | local | docs/runbooks/SPACE_DB_CUTOVER.md documents or exercises this opt-in owner CLI. |
| `scripts/validate_schemas.py` | ACTIVE_GATE | verify.sh | local | Invoked by verify.sh as an offline acceptance gate. |
| `scripts/writer_signing_key.py` | ACTIVE_OWNER_TOOL | owner-local | local | docs/runbooks/WRITER_CUTOVER.md documents or exercises this opt-in owner CLI. |

## Workflows

| Path | Class | Trigger | Touches | Evidence |
| --- | --- | --- | --- | --- |
| `.github/workflows/a4-card04-companion-rehearsal.yml` | ACTIVE_GATE | pull_request | scratch PG | .github/workflows/a4-card04-companion-rehearsal.yml runs the sealed Card-04 companion's scratch-PostgreSQL 17.6 rehearsal on pull_request. |
| `.github/workflows/a4-ledger-audit-rehearsal.yml` | ACTIVE_GATE | pull_request | scratch PG | .github/workflows/a4-ledger-audit-rehearsal.yml runs the sealed A4 audit's scratch-PostgreSQL rehearsal on pull_request. |
| `.github/workflows/apply-migration-0008.yml` | HISTORICAL_CONSUMED | workflow_dispatch | production DB | STATE.md: '0008 was applied once, 2026-09-16 (run 35164080476).' (never rerun). |
| `.github/workflows/apply-migration-0010-rehearsal.yml` | ACTIVE_GATE | pull_request | scratch PG | .github/workflows/apply-migration-0010-rehearsal.yml runs its checks on pull_request. |
| `.github/workflows/apply-migration-0010.yml` | HISTORICAL_CONSUMED | workflow_dispatch | production DB | STATE.md: 'The owner-authorized 0010 T4 is CONSUMED and VERIFIED: run 35190794876 (BATCH_0010).' (never rerun). |
| `.github/workflows/apply-migration-0011.yml` | HISTORICAL_CONSUMED | workflow_dispatch | production DB | STATE.md: 'APPLY-MIGRATION-0011-ONCE is CONSUMED and PASSED: run 36583531813 on main b11a8e53, committed.' (never rerun). |
| `.github/workflows/apply-migration-0012.yml` | HISTORICAL_CONSUMED | workflow_dispatch | production DB | STATE.md: 'APPLY-MIGRATION-0012-ONCE is CONSUMED and PASSED: run 36586262979 on main b11a8e53, committed.' (never rerun). |
| `.github/workflows/apply-migration-0013-rehearsal.yml` | ACTIVE_GATE | pull_request | scratch PG | .github/workflows/apply-migration-0013-rehearsal.yml runs its checks on pull_request. |
| `.github/workflows/apply-migration-0013.yml` | HISTORICAL_CONSUMED | workflow_dispatch | production DB | STATE.md: 'Migration 0013 is APPLIED (T4, CONSUMED, PASS; run 36820986264).' (never rerun). |
| `.github/workflows/apply-migration-0014.yml` | HISTORICAL_CONSUMED | workflow_dispatch | production DB | STATE.md: 'run 36952902214 (workflow_dispatch on main at 46a1de68, attempt 1). It is consumed: never rerun.' (never rerun). |
| `.github/workflows/apply-migration-0015.yml` | HISTORICAL_CONSUMED | workflow_dispatch | production DB | STATE.md: '**T4-1, the 0015 apply, is CONSUMED.**' (never rerun). |
| `.github/workflows/apply-migration-0016.yml` | HISTORICAL_CONSUMED | workflow_dispatch | production DB | STATE.md: '**0016: run 37110330500**, APPLIED and committed,' (never rerun). |
| `.github/workflows/apply-migration-0017.yml` | HISTORICAL_CONSUMED | workflow_dispatch | production DB | STATE.md: '**0017: run 37110375659**, APPLIED and committed.' (never rerun). |
| `.github/workflows/apply-migration-0018.yml` | HISTORICAL_CONSUMED | workflow_dispatch | production DB | STATE.md: '**D6: COMPLETE.** 0018 is APPLIED (run 37172530166,' (never rerun). |
| `.github/workflows/audit-table-privileges-rehearsal.yml` | ACTIVE_GATE | pull_request | scratch PG | .github/workflows/audit-table-privileges-rehearsal.yml runs its checks on pull_request. |
| `.github/workflows/audit-table-privileges.yml` | HISTORICAL_REFERENCE | workflow_dispatch | production DB | A read-only catalog audit, not a write: STATE.md records the older-table audit, run 35120616278; no current loop runs it. |
| `.github/workflows/ci.yml` | ACTIVE_GATE | push, pull_request | CI only | .github/workflows/ci.yml runs its checks on push, pull_request. |
| `.github/workflows/core-write-inventory-rehearsal.yml` | ACTIVE_GATE | pull_request | scratch PG | .github/workflows/core-write-inventory-rehearsal.yml runs its checks on pull_request. |
| `.github/workflows/core-write-inventory.yml` | ACTIVE_JOB | workflow_dispatch | production DB | .github/workflows/core-write-inventory.yml defines the repeatable manual diagnostic/collection job. |
| `.github/workflows/derivatives-cadence-readiness-diagnostic.yml` | ACTIVE_JOB | workflow_dispatch | external read-only | .github/workflows/derivatives-cadence-readiness-diagnostic.yml defines the repeatable manual diagnostic/collection job. |
| `.github/workflows/derivatives-evidence-cadence.yml` | ACTIVE_JOB | workflow_dispatch | production DB | .github/workflows/derivatives-evidence-cadence.yml defines the repeatable manual diagnostic/collection job. |
| `.github/workflows/derivatives-registry-diagnostic.yml` | ACTIVE_JOB | workflow_dispatch | external read-only | .github/workflows/derivatives-registry-diagnostic.yml defines the repeatable manual diagnostic/collection job. |
| `.github/workflows/keepalive.yml` | ACTIVE_JOB | schedule, workflow_dispatch | HF Space | .github/workflows/keepalive.yml defines the repeatable scheduled job. |
| `.github/workflows/migration-0014-rehearsal.yml` | ACTIVE_GATE | pull_request | scratch PG | .github/workflows/migration-0014-rehearsal.yml runs its checks on pull_request. |
| `.github/workflows/migration-0015-rehearsal.yml` | ACTIVE_GATE | pull_request | scratch PG | .github/workflows/migration-0015-rehearsal.yml runs its checks on pull_request. |
| `.github/workflows/migration-0016-rehearsal.yml` | ACTIVE_GATE | pull_request | scratch PG | .github/workflows/migration-0016-rehearsal.yml runs its checks on pull_request. |
| `.github/workflows/migration-0017-rehearsal.yml` | ACTIVE_GATE | pull_request | scratch PG | .github/workflows/migration-0017-rehearsal.yml runs its checks on pull_request. |
| `.github/workflows/migration-0018-rehearsal.yml` | ACTIVE_GATE | pull_request | scratch PG | .github/workflows/migration-0018-rehearsal.yml runs its checks on pull_request. |
| `.github/workflows/oos-pair-evidence.yml` | HISTORICAL_REFERENCE | workflow_dispatch | production DB | .github/workflows/oos-pair-evidence.yml says the holdout closed and re-enabling collection is an owner decision. |
| `.github/workflows/persistence-rehearsal.yml` | ACTIVE_GATE | pull_request | scratch PG | .github/workflows/persistence-rehearsal.yml runs its checks on pull_request. |
| `.github/workflows/privilege-rehearsal.yml` | ACTIVE_GATE | pull_request | scratch PG | .github/workflows/privilege-rehearsal.yml runs its checks on pull_request. |
| `.github/workflows/reproducible-build.yml` | ACTIVE_GATE | pull_request, push | CI only | .github/workflows/reproducible-build.yml runs its checks on pull_request, push. |
| `.github/workflows/restore-proof-rehearsal.yml` | ACTIVE_GATE | pull_request | scratch PG | .github/workflows/restore-proof-rehearsal.yml runs the DP-D restore proof's scratch-PostgreSQL 17.6 rehearsal on pull_request. |
| `.github/workflows/resolve-outcomes.yml` | ACTIVE_JOB | schedule, workflow_dispatch | production DB | .github/workflows/resolve-outcomes.yml defines the repeatable scheduled job. |
| `.github/workflows/section-5a-apply-seal-migration.yml` | HISTORICAL_CONSUMED | workflow_dispatch | production DB | STATE.md: 'The 0009 route: 34851608514 (refused before any DB contact) and 34861816985 (applied). Never dispatch it again.' (never rerun). |
| `.github/workflows/section-5a-evaluation.yml` | HISTORICAL_CONSUMED | workflow_dispatch | production DB | STATE.md: 'The §5A ONE LOOK, consume run 34919367341 (1d8f933, population f83c31f7…).' (never rerun). |
| `.github/workflows/source-integrity-guard.yml` | ACTIVE_JOB | schedule, workflow_dispatch | HF Space | .github/workflows/source-integrity-guard.yml defines the repeatable scheduled job. |

## Ops

| Path | Class | Trigger | Touches | Evidence |
| --- | --- | --- | --- | --- |
| `ops/a4_card04_companion/CARD.md` | ACTIVE_OWNER_TOOL | owner-local, one UOR qualification episode only | production DB | The owner card for ucpe.a4_card04_companion.v1; prepared, never run against production (docs/automation/UOR_HANDOFF.md section 15). |
| `ops/a4_card04_companion/MANIFEST.json` | ACTIVE_PIN | a4_card04_companion.py; tests | local | The package seal: the runner checks every sealed file against it before any contact, and tests/automation/test_a4_card04_companion.py rebuilds it; its sha256 is ARTIFACT_SHA256 in docs/automation/UOR_HANDOFF.md section 15. |
| `ops/a4_card04_companion/a4_card04_companion.py` | ACTIVE_OWNER_TOOL | owner-local, one UOR qualification episode only | production DB | The read-only runner of ucpe.a4_card04_companion.v1, documented by ops/a4_card04_companion/CARD.md; never run against production yet. |
| `ops/a4_card04_companion/a4_card04_companion.sql` | ACTIVE_PIN | a4_card04_companion.py | local | The sealed SELECT, pinned by sha256 in ops/a4_card04_companion/a4_card04_companion.py. |
| `ops/a4_card04_companion/build_manifest.py` | ACTIVE_OWNER_TOOL | owner-local | local | Regenerates ops/a4_card04_companion/MANIFEST.json, checked by tests/automation/test_a4_card04_companion.py. |
| `ops/a4_ledger_audit/CARD.md` | ACTIVE_OWNER_TOOL | owner-local, one UOR qualification episode only | production DB | The owner card for ucpe.a4_ledger_audit.v1; prepared, never run against production (docs/automation/UOR_HANDOFF.md section 14). |
| `ops/a4_ledger_audit/MANIFEST.json` | ACTIVE_PIN | tests only | local | The package seal, read by tests/automation/test_a4_ledger_audit.py; its sha256 is ARTIFACT_SHA256 in docs/automation/UOR_HANDOFF.md section 14. |
| `ops/a4_ledger_audit/a4_ledger_audit.py` | ACTIVE_OWNER_TOOL | owner-local, one UOR qualification episode only | production DB | The read-only runner of ucpe.a4_ledger_audit.v1, documented by ops/a4_ledger_audit/CARD.md; never run against production yet. |
| `ops/a4_ledger_audit/a4_ledger_audit.sql` | ACTIVE_PIN | a4_ledger_audit.py | local | The sealed SELECT, pinned by sha256 in ops/a4_ledger_audit/a4_ledger_audit.py. |
| `ops/a4_ledger_audit/build_manifest.py` | ACTIVE_OWNER_TOOL | owner-local | local | Regenerates ops/a4_ledger_audit/MANIFEST.json, checked by tests/automation/test_a4_ledger_audit.py. |
| `ops/hf_runtime_baseline.json` | ACTIVE_PIN | source-integrity-guard.yml | local | Read by scripts/source_integrity_guard.py. |
| `ops/oos_candidate_freeze.json` | ACTIVE_PIN | tests only; collector freeze guard | local | Read by tests/oos/test_freeze_guard.py. |
| `ops/release/config.json` | ACTIVE_RELEASE | owner-local (release.py) | local | Read by scripts/release.py for release and rollback checks. |
| `ops/release/releases.json` | ACTIVE_RELEASE | owner-local (release.py) | local | Read by scripts/release.py for release and rollback checks. |
| `ops/section_5a_evaluator_pin.json` | ACTIVE_PIN | tests only; isolated route attestation | local | Read by tests/workflows/test_owner_url_environment.py. |
| `ops/section_5a_evaluator_requirements.lock` | ACTIVE_PIN | core-write-inventory.yml; isolated route bootstrap | local | Read by .github/workflows/core-write-inventory.yml. |
| `ops/section_5a_red_tests_pin.json` | ACTIVE_PIN | tests only | local | Read by tests/oos/evaluation/test_red_tests_are_unedited.py. |

## Runbooks

| Path | Class | Trigger | Touches | Evidence |
| --- | --- | --- | --- | --- |
| `docs/runbooks/CORE_WRITE_INVENTORY.md` | ACTIVE_OWNER_TOOL | owner-local | production DB | Documents .github/workflows/core-write-inventory.yml before/after catalog checks. |
| `docs/runbooks/MIGRATION_0018_APPLY.md` | HISTORICAL_CONSUMED | none | production DB | STATE.md: '**D6: COMPLETE.** 0018 is APPLIED (run 37172530166,' (never rerun). |
| `docs/runbooks/OWNER_URL_ENVIRONMENT.md` | HISTORICAL_REFERENCE | none (C4 setup complete) | local | STATE.md records 'C4: SET, verified by NAME only' for this GitHub configuration procedure. |
| `docs/runbooks/RELEASE.md` | ACTIVE_RELEASE | owner-local | HF Space | Drives scripts/release.py release procedures. |
| `docs/runbooks/RESOLVER_CUTOVER.md` | HISTORICAL_REFERENCE | none (G1 cutover proven) | production DB | STATE.md records 'G1: LIVE_PROVEN' and run 37139970258 after this credential cutover. |
| `docs/runbooks/RESTORE_PROOF_EXPORT.md` | ACTIVE_OWNER_TOOL | owner-local | production DB | The owner's one-time schema-only and roles-only export for the DP-D restore proof (catalog reads, no row, no password); RUN ONCE by the owner on 2026-10-07 (the digests and the proof's outcome are in STATE.md). |
| `docs/runbooks/ROLLBACK.md` | ACTIVE_RELEASE | owner-local | HF Space | Drives scripts/release.py rollback procedures. |
| `docs/runbooks/SPACE_DB_CUTOVER.md` | ACTIVE_OWNER_TOOL | owner-local | production DB | Documents scripts/space_db_credential.py and the owner SQL/Space credential switch. |
| `docs/runbooks/WRITER_CUTOVER.md` | ACTIVE_OWNER_TOOL | owner-local | Supabase API | Documents scripts/writer_signing_key.py and recurring 30-day writer-token replacement. |
