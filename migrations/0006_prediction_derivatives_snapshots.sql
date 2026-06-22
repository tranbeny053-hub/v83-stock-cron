-- Wave 4D.3 immutable prediction-linked derivatives evidence.
-- Additive, append-only data-plane storage.

CREATE TABLE IF NOT EXISTS public.prediction_derivatives_snapshots (
    prediction_id TEXT PRIMARY KEY
        CHECK (btrim(prediction_id) <> '')
        REFERENCES public.predictions(prediction_id)
        ON DELETE RESTRICT,
    run_id TEXT NOT NULL
        CHECK (btrim(run_id) <> ''),
    normalized_symbol TEXT NOT NULL
        CHECK (btrim(normalized_symbol) <> ''),
    derivatives_schema_version TEXT NOT NULL
        CHECK (btrim(derivatives_schema_version) <> ''),
    derivatives_methodology_version TEXT NOT NULL
        CHECK (btrim(derivatives_methodology_version) <> ''),
    influence_mode TEXT NOT NULL
        CHECK (influence_mode = 'SHADOW_ONLY'),
    decision_influence_frac NUMERIC NOT NULL
        CHECK (decision_influence_frac = 0),
    block_status TEXT NOT NULL
        CHECK (block_status IN ('ACTIVE', 'DEGRADED', 'UNAVAILABLE')),
    core_prediction_as_of_utc TIMESTAMPTZ NOT NULL,
    observation_as_of_utc TIMESTAMPTZ NOT NULL,
    snapshot_payload JSONB NOT NULL
        CHECK (jsonb_typeof(snapshot_payload) = 'object'),
    snapshot_hash TEXT NOT NULL
        CHECK (snapshot_hash ~ '^[0-9a-f]{64}$'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CHECK (observation_as_of_utc >= core_prediction_as_of_utc),
    CHECK (
        snapshot_payload ?& ARRAY[
            'schema_version',
            'methodology_version',
            'influence_mode',
            'decision_influence_frac',
            'normalized_symbol',
            'core_prediction_as_of_utc',
            'observation_as_of_utc',
            'block_status',
            'provider_summary',
            'metrics',
            'comparability',
            'disagreement',
            'warnings',
            'not_trade_command',
            'not_financial_advice'
        ]
    ),
    CHECK (
        jsonb_typeof(snapshot_payload->'schema_version') = 'string'
        AND snapshot_payload->>'schema_version' = derivatives_schema_version
    ),
    CHECK (
        jsonb_typeof(snapshot_payload->'methodology_version') = 'string'
        AND snapshot_payload->>'methodology_version' = derivatives_methodology_version
    ),
    CHECK (
        jsonb_typeof(snapshot_payload->'influence_mode') = 'string'
        AND snapshot_payload->>'influence_mode' = influence_mode
    ),
    CHECK (
        jsonb_typeof(snapshot_payload->'decision_influence_frac') = 'number'
        AND (snapshot_payload->>'decision_influence_frac')::NUMERIC
            = decision_influence_frac
    ),
    CHECK (
        jsonb_typeof(snapshot_payload->'normalized_symbol') = 'string'
        AND snapshot_payload->>'normalized_symbol' = normalized_symbol
    ),
    CHECK (
        jsonb_typeof(snapshot_payload->'block_status') = 'string'
        AND snapshot_payload->>'block_status' = block_status
    ),
    CHECK (
        jsonb_typeof(snapshot_payload->'core_prediction_as_of_utc') = 'string'
        AND (snapshot_payload->>'core_prediction_as_of_utc')::TIMESTAMPTZ
            = core_prediction_as_of_utc
    ),
    CHECK (
        jsonb_typeof(snapshot_payload->'observation_as_of_utc') = 'string'
        AND (snapshot_payload->>'observation_as_of_utc')::TIMESTAMPTZ
            = observation_as_of_utc
    ),
    CHECK (jsonb_typeof(snapshot_payload->'provider_summary') = 'array'),
    CHECK (jsonb_typeof(snapshot_payload->'metrics') = 'array'),
    CHECK (jsonb_typeof(snapshot_payload->'comparability') = 'array'),
    CHECK (jsonb_typeof(snapshot_payload->'disagreement') = 'array'),
    CHECK (jsonb_typeof(snapshot_payload->'warnings') = 'array'),
    CHECK (
        jsonb_typeof(snapshot_payload->'not_trade_command') = 'boolean'
        AND (snapshot_payload->>'not_trade_command')::BOOLEAN IS TRUE
    ),
    CHECK (
        jsonb_typeof(snapshot_payload->'not_financial_advice') = 'boolean'
        AND (snapshot_payload->>'not_financial_advice')::BOOLEAN IS TRUE
    )
);

CREATE INDEX IF NOT EXISTS idx_pds_methodology_symbol_observation
ON public.prediction_derivatives_snapshots (
    derivatives_methodology_version,
    normalized_symbol,
    observation_as_of_utc
);

ALTER TABLE public.prediction_derivatives_snapshots
ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE public.prediction_derivatives_snapshots
FROM PUBLIC, anon, authenticated, service_role;

GRANT SELECT, INSERT
ON TABLE public.prediction_derivatives_snapshots
TO service_role;

CREATE OR REPLACE FUNCTION public.reject_prediction_derivatives_snapshot_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'prediction derivatives snapshots are append-only';
END;
$$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger
        WHERE tgname = 'trg_pds_reject_update'
          AND tgrelid = 'public.prediction_derivatives_snapshots'::regclass
    ) THEN
        CREATE TRIGGER trg_pds_reject_update
        BEFORE UPDATE ON public.prediction_derivatives_snapshots
        FOR EACH ROW
        EXECUTE FUNCTION public.reject_prediction_derivatives_snapshot_mutation();
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger
        WHERE tgname = 'trg_pds_reject_delete'
          AND tgrelid = 'public.prediction_derivatives_snapshots'::regclass
    ) THEN
        CREATE TRIGGER trg_pds_reject_delete
        BEFORE DELETE ON public.prediction_derivatives_snapshots
        FOR EACH ROW
        EXECUTE FUNCTION public.reject_prediction_derivatives_snapshot_mutation();
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger
        WHERE tgname = 'trg_pds_reject_truncate'
          AND tgrelid = 'public.prediction_derivatives_snapshots'::regclass
    ) THEN
        CREATE TRIGGER trg_pds_reject_truncate
        BEFORE TRUNCATE ON public.prediction_derivatives_snapshots
        FOR EACH STATEMENT
        EXECUTE FUNCTION public.reject_prediction_derivatives_snapshot_mutation();
    END IF;
END;
$$;
