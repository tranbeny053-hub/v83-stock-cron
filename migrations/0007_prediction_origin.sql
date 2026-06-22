-- Wave 4D.3-Ops Phase 1 prediction-origin cohort separation.
-- Additive only; existing rows receive the explicit USER_REQUESTED default.

ALTER TABLE public.predictions
    ADD COLUMN IF NOT EXISTS prediction_origin TEXT
    NOT NULL
    DEFAULT 'USER_REQUESTED';

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'predictions_prediction_origin_chk'
          AND conrelid = 'public.predictions'::regclass
    ) THEN
        ALTER TABLE public.predictions
            ADD CONSTRAINT predictions_prediction_origin_chk
            CHECK (
                prediction_origin IN (
                    'USER_REQUESTED',
                    'CONTROLLED_SMOKE',
                    'SCHEDULED_SHADOW_EVIDENCE'
                )
            );
    END IF;
END;
$$;

CREATE INDEX IF NOT EXISTS idx_predictions_origin_methodology_tf
ON public.predictions (
    prediction_origin,
    methodology_version,
    timeframe
);
