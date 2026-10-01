-- Core-evidence invariants for new rows (governing plan §8.2; bundle DBI-1).
--
-- AUTHORED, NOT APPLIED. Applying this is a T4 action requiring owner authorization, through a
-- dedicated apply route that does not exist yet (a later bundle, the 0011-0013 pattern). The default
-- scripts/apply_migrations.py applies EVERY migration and must never be used for it.
--
-- EVERY CONSTRAINT IS NOT VALID. It binds every row written after the apply and scans no existing row:
-- - no holdout probability is read: under the §5A preregistration, reading the holdout's
--   probabilities is the look;
-- - no existing evidence is rejected or repaired (§8.2: "do not silently repair existing evidence");
-- - so no data precheck is needed (owner ruling OD-DB-1 = D).
-- Validating the old rows later (VALIDATE CONSTRAINT) reads every row and needs its own owner ruling.
--
-- THE CHECKS restate what the writer already guarantees (tests/persistence/test_writer_db_contract.py):
-- - predictions_probability_simplex_chk: each probability in [0, 1], and the three sum to 1 within the
--   pipeline's own tolerance, utils/invariants.PROBABILITY_TOLERANCE = 1e-6 (never stricter). NaN
--   fails, because PostgreSQL orders NaN above every number.
-- - predictions_reference_price_chk and prediction_outcomes_reference_price_chk: positive and below
--   'Infinity', which also excludes NaN.
-- - predictions_horizon_chronology_chk: a positive horizon that ends after the reference close, and a
--   reference close no later than the prediction.
--
-- APPEND-ONLY CORE EVIDENCE: predictions, prediction_outcomes and prediction_feature_snapshots refuse
-- UPDATE, DELETE and TRUNCATE, as 0006 already does for prediction_derivatives_snapshots. Both writers
-- only ever insert them (Postgres: ON CONFLICT DO NOTHING; REST: resolution=ignore-duplicates).
-- Corrections are additive records, never edits (§8.2).
--
-- LOCKS: each ADD CONSTRAINT ... NOT VALID takes a brief ACCESS EXCLUSIVE lock and each CREATE TRIGGER
-- a brief SHARE ROW EXCLUSIVE lock, with no scan. No foreign key is added, 0012's precedent.
-- The trigger function has a fixed search_path and no EXECUTE for PUBLIC or the API roles (§8.2).

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_catalog.pg_constraint
        WHERE conname = 'predictions_probability_simplex_chk'
          AND conrelid = 'public.predictions'::regclass
    ) THEN
        ALTER TABLE public.predictions
            ADD CONSTRAINT predictions_probability_simplex_chk
            CHECK (
                p_up_frac >= 0 AND p_up_frac <= 1
                AND p_down_frac >= 0 AND p_down_frac <= 1
                AND p_timeout_frac >= 0 AND p_timeout_frac <= 1
                AND abs(p_up_frac + p_down_frac + p_timeout_frac - 1) <= 0.000001
            )
            NOT VALID;
    END IF;
    IF NOT EXISTS (
        SELECT 1
        FROM pg_catalog.pg_constraint
        WHERE conname = 'predictions_reference_price_chk'
          AND conrelid = 'public.predictions'::regclass
    ) THEN
        ALTER TABLE public.predictions
            ADD CONSTRAINT predictions_reference_price_chk
            CHECK (reference_price > 0 AND reference_price < 'Infinity'::numeric)
            NOT VALID;
    END IF;
    IF NOT EXISTS (
        SELECT 1
        FROM pg_catalog.pg_constraint
        WHERE conname = 'predictions_horizon_chronology_chk'
          AND conrelid = 'public.predictions'::regclass
    ) THEN
        ALTER TABLE public.predictions
            ADD CONSTRAINT predictions_horizon_chronology_chk
            CHECK (
                horizon_bars > 0
                AND horizon_end_utc > reference_close_utc
                AND reference_close_utc <= predicted_at_utc
            )
            NOT VALID;
    END IF;
    IF NOT EXISTS (
        SELECT 1
        FROM pg_catalog.pg_constraint
        WHERE conname = 'prediction_outcomes_reference_price_chk'
          AND conrelid = 'public.prediction_outcomes'::regclass
    ) THEN
        ALTER TABLE public.prediction_outcomes
            ADD CONSTRAINT prediction_outcomes_reference_price_chk
            CHECK (outcome_reference_price > 0 AND outcome_reference_price < 'Infinity'::numeric)
            NOT VALID;
    END IF;
END;
$$;

CREATE OR REPLACE FUNCTION public.reject_core_evidence_mutation()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, pg_temp
AS $$
BEGIN
    RAISE EXCEPTION 'core prediction evidence is append-only: % on % is refused', TG_OP, TG_TABLE_NAME;
END;
$$;

REVOKE ALL ON FUNCTION public.reject_core_evidence_mutation()
FROM PUBLIC, anon, authenticated, service_role;

DO $$
DECLARE
    target TEXT;
    short TEXT;
BEGIN
    FOREACH target IN ARRAY ARRAY['predictions', 'prediction_outcomes', 'prediction_feature_snapshots']
    LOOP
        short := CASE target
            WHEN 'predictions' THEN 'pred'
            WHEN 'prediction_outcomes' THEN 'pout'
            ELSE 'pfs'
        END;
        IF NOT EXISTS (
            SELECT 1 FROM pg_catalog.pg_trigger
            WHERE tgname = 'trg_' || short || '_reject_update'
              AND tgrelid = pg_catalog.format('public.%I', target)::regclass
        ) THEN
            EXECUTE pg_catalog.format(
                'CREATE TRIGGER %I BEFORE UPDATE ON public.%I FOR EACH ROW '
                'EXECUTE FUNCTION public.reject_core_evidence_mutation()',
                'trg_' || short || '_reject_update', target);
        END IF;
        IF NOT EXISTS (
            SELECT 1 FROM pg_catalog.pg_trigger
            WHERE tgname = 'trg_' || short || '_reject_delete'
              AND tgrelid = pg_catalog.format('public.%I', target)::regclass
        ) THEN
            EXECUTE pg_catalog.format(
                'CREATE TRIGGER %I BEFORE DELETE ON public.%I FOR EACH ROW '
                'EXECUTE FUNCTION public.reject_core_evidence_mutation()',
                'trg_' || short || '_reject_delete', target);
        END IF;
        IF NOT EXISTS (
            SELECT 1 FROM pg_catalog.pg_trigger
            WHERE tgname = 'trg_' || short || '_reject_truncate'
              AND tgrelid = pg_catalog.format('public.%I', target)::regclass
        ) THEN
            EXECUTE pg_catalog.format(
                'CREATE TRIGGER %I BEFORE TRUNCATE ON public.%I FOR EACH STATEMENT '
                'EXECUTE FUNCTION public.reject_core_evidence_mutation()',
                'trg_' || short || '_reject_truncate', target);
        END IF;
    END LOOP;
END;
$$;
