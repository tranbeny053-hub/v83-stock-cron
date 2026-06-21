-- Wave 4C.2 immutable prediction-time Quant V2 feature evidence.
-- Additive only: no destructive action or existing-row mutation.

CREATE TABLE IF NOT EXISTS public.prediction_feature_snapshots (
    prediction_id TEXT PRIMARY KEY
        REFERENCES public.predictions(prediction_id)
        ON DELETE RESTRICT,

    run_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    normalized_symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,

    prediction_as_of_utc TIMESTAMPTZ NOT NULL,
    reference_close_utc TIMESTAMPTZ NOT NULL,

    quant_v2_schema_version TEXT NOT NULL,
    feature_methodology_version TEXT NOT NULL,

    influence_mode TEXT NOT NULL
        CHECK (influence_mode = 'SHADOW_ONLY'),

    no_lookahead_assertion BOOLEAN NOT NULL,

    block_status TEXT NOT NULL
        CHECK (block_status IN ('ACTIVE', 'DEGRADED', 'DISABLED')),

    feature_count INTEGER NOT NULL
        CHECK (feature_count >= 0),

    degraded_count INTEGER NOT NULL
        CHECK (
            degraded_count >= 0
            AND degraded_count <= feature_count
        ),

    provider_signature TEXT NOT NULL,

    snapshot_payload JSONB NOT NULL
        CHECK (jsonb_typeof(snapshot_payload) = 'object'),

    snapshot_hash TEXT NOT NULL,

    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_pfs_methodology_timeframe_asof
ON public.prediction_feature_snapshots (
    feature_methodology_version,
    timeframe,
    prediction_as_of_utc
);

CREATE INDEX IF NOT EXISTS idx_pfs_symbol_timeframe_asof
ON public.prediction_feature_snapshots (
    normalized_symbol,
    timeframe,
    prediction_as_of_utc
);

ALTER TABLE public.prediction_feature_snapshots
ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE public.prediction_feature_snapshots
FROM anon, authenticated;
