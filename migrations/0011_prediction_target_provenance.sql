-- Target contract v1 (tc-v1): the four provenance columns on public.predictions.
--
-- AUTHORED, NOT APPLIED. Applying this is a T4 action requiring owner authorization. It is applied
-- ONCE, and only by the dispatch-only workflow .github/workflows/apply-migration-0011.yml
-- (scripts/apply_migration_0011.py). That route executes exactly this file in ONE transaction,
-- between read-only pre-checks and post-checks, and rolls back on any surprise. The default
-- scripts/apply_migrations.py applies EVERY migration and must never be used for it.
--
-- WHY (owner decisions D1 = B and D2 = provenance first, 2026-09-29). Since PR #129 the resolver
-- resolves a row only on the venue whose candles gave its reference close. Normal rows store
-- data_source CROSS_PROVIDER, and the writer never stored that venue, so they cannot resolve. These
-- columns let the writer record the target explicitly (docs/TARGET_CONTRACT_V1.md, STAMP_FIELDS):
-- - target_version        'tc-v1', the target contract the row was issued under;
-- - reference_venue       BINANCE_PUBLIC or OKX_PUBLIC, the venue of the reference close;
-- - core_computed_at_utc  when the quant core finished (app clock);
-- - issued_at_utc         when the response was produced (app clock).
--
-- WHAT THIS DOES:
-- 1. Adds the four columns, nullable, with no default. NULL in all four means a v0 row. Every
--    existing row stays v0: nothing is backfilled or updated.
-- 2. Adds three CHECK constraints, each only if absent (the 0007 pattern):
--    - target_version is NULL or exactly 'tc-v1';
--    - reference_venue is NULL or a venue label;
--    - a row is either unstamped (all four NULL) or fully stamped, with
--      core_computed_at_utc <= issued_at_utc.
--
-- Nothing else changes: no existing column (predicted_at_utc keeps its meaning), no index, no
-- grant, no policy, no trigger, no other table. Adding a nullable column without a default rewrites
-- no row; each constraint reads the existing rows once. The transaction holds the table's ACCESS
-- EXCLUSIVE lock until it ends, so every read and write of predictions waits for this short
-- transaction; while it waits to take the lock, at most the route's lock_timeout, later reads and
-- writes queue behind it. The existing table-level grants cover the new columns, so who can read
-- or write the table is unchanged.

ALTER TABLE public.predictions
    ADD COLUMN IF NOT EXISTS target_version TEXT,
    ADD COLUMN IF NOT EXISTS reference_venue TEXT,
    ADD COLUMN IF NOT EXISTS core_computed_at_utc TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS issued_at_utc TIMESTAMPTZ;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_catalog.pg_constraint
        WHERE conname = 'predictions_target_version_chk'
          AND conrelid = 'public.predictions'::regclass
    ) THEN
        ALTER TABLE public.predictions
            ADD CONSTRAINT predictions_target_version_chk
            CHECK (target_version IS NULL OR target_version = 'tc-v1');
    END IF;
    IF NOT EXISTS (
        SELECT 1
        FROM pg_catalog.pg_constraint
        WHERE conname = 'predictions_reference_venue_chk'
          AND conrelid = 'public.predictions'::regclass
    ) THEN
        ALTER TABLE public.predictions
            ADD CONSTRAINT predictions_reference_venue_chk
            CHECK (reference_venue IS NULL OR reference_venue IN ('BINANCE_PUBLIC', 'OKX_PUBLIC'));
    END IF;
    IF NOT EXISTS (
        SELECT 1
        FROM pg_catalog.pg_constraint
        WHERE conname = 'predictions_target_stamp_chk'
          AND conrelid = 'public.predictions'::regclass
    ) THEN
        ALTER TABLE public.predictions
            ADD CONSTRAINT predictions_target_stamp_chk
            CHECK (
                (
                    target_version IS NULL
                    AND reference_venue IS NULL
                    AND core_computed_at_utc IS NULL
                    AND issued_at_utc IS NULL
                )
                OR (
                    target_version IS NOT NULL
                    AND reference_venue IS NOT NULL
                    AND core_computed_at_utc IS NOT NULL
                    AND issued_at_utc IS NOT NULL
                    AND core_computed_at_utc <= issued_at_utc
                )
            );
    END IF;
END;
$$;
