-- UCPE migration + calibration status — READ ONLY.
-- Safe to run in the Supabase SQL editor. Contains no INSERT, UPDATE, DELETE, ALTER,
-- CREATE, DROP, or GRANT. It only reads catalog metadata and row counts.
-- Purpose: determine which migrations are actually applied and whether the prediction
-- ledger is accumulating resolvable outcomes, without exposing any secret.

-- 1) Which migrations are applied, inferred from the objects each one creates.
SELECT
  m.migration,
  m.expected_object,
  CASE WHEN to_regclass(m.expected_object) IS NOT NULL
       THEN 'APPLIED' ELSE 'NOT_APPLIED' END AS status
FROM (VALUES
  ('0001_init',                        'public.analysis_runs'),
  ('0001_init',                        'public.analysis_timeframe_results'),
  ('0001_init',                        'public.app_events'),
  ('0001_init',                        'public.provider_observations'),
  ('0001_init',                        'public.watchlist'),
  ('0002_news',                        'public.news_items'),
  ('0002_news',                        'public.news_clusters'),
  ('0002_news',                        'public.news_evidence_links'),
  ('0003_prediction_ledger',           'public.predictions'),
  ('0004_prediction_outcomes',         'public.prediction_outcomes'),
  ('0005_feature_snapshots',           'public.prediction_feature_snapshots'),
  ('0006_derivatives_snapshots',       'public.prediction_derivatives_snapshots')
) AS m(migration, expected_object)
ORDER BY m.migration, m.expected_object;

-- 2) Migration 0007 adds a column and an index rather than a table.
SELECT
  '0007_prediction_origin' AS migration,
  CASE WHEN EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'predictions'
      AND column_name = 'prediction_origin'
  ) THEN 'APPLIED' ELSE 'NOT_APPLIED' END AS column_status,
  CASE WHEN EXISTS (
    SELECT 1 FROM pg_indexes
    WHERE schemaname = 'public'
      AND indexname = 'idx_predictions_origin_methodology_tf'
  ) THEN 'APPLIED' ELSE 'NOT_APPLIED' END AS index_status;

-- 3) Is the prediction ledger accumulating, and are outcomes being resolved?
--    This is what governs whether calibration can ever leave INSUFFICIENT_SAMPLE.
SELECT
  (SELECT count(*) FROM public.predictions)                                   AS predictions_total,
  (SELECT count(*) FROM public.prediction_outcomes)                           AS outcomes_total,
  (SELECT count(*) FROM public.predictions  WHERE created_at > now() - interval '7 days')
                                                                              AS predictions_last_7d,
  (SELECT max(created_at) FROM public.predictions)                            AS newest_prediction,
  (SELECT max(created_at) FROM public.prediction_outcomes)                    AS newest_outcome;

-- 4) Resolved-outcome breakdown. A healthy calibration path needs a growing count of
--    resolved outcomes across all three labels, not only TIMEOUT.
SELECT realized_label, count(*) AS n
FROM public.prediction_outcomes
GROUP BY realized_label
ORDER BY n DESC;
