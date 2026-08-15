-- UCPE calibration cohort status — READ ONLY.
-- Safe to run in the Supabase SQL editor. SELECT statements only: no INSERT, UPDATE,
-- DELETE, ALTER, CREATE, DROP, or GRANT. Exposes no secret.
--
-- Purpose: reproduce EXACTLY the filter the application uses to build a calibration
-- report, so we can state the real sample_gate instead of guessing from row totals.
--
-- The application's filter (repository.py::_execute_calibration_query) is:
--     p.is_live_data = true
--     AND o.is_live_data = true
--     AND o.realized_label IN ('UP','DOWN','TIMEOUT')
--     AND coalesce(p.prediction_origin,'USER_REQUESTED') = 'USER_REQUESTED'
--
-- Sample gates (calibration/service.py::sample_gate_for) on the resulting valid_count:
--     0 -> NO_SAMPLES | <100 -> INSUFFICIENT_SAMPLE | <300 -> WARMING_UP
--     <500 -> PRELIMINARY_MEASURED | >=500 -> MEASURED

-- 1) THE ANSWER: how many rows the default unscoped calibration report actually sees,
--    and therefore which gate it reports.
SELECT
  count(*) AS calibration_cohort_rows,
  CASE
    WHEN count(*) <= 0   THEN 'NO_SAMPLES'
    WHEN count(*) < 100  THEN 'INSUFFICIENT_SAMPLE'
    WHEN count(*) < 300  THEN 'WARMING_UP'
    WHEN count(*) < 500  THEN 'PRELIMINARY_MEASURED'
    ELSE 'MEASURED'
  END AS expected_sample_gate
FROM public.predictions p
JOIN public.prediction_outcomes o ON o.prediction_id = p.prediction_id
WHERE p.is_live_data = true
  AND o.is_live_data = true
  AND o.realized_label IN ('UP','DOWN','TIMEOUT')
  AND coalesce(p.prediction_origin,'USER_REQUESTED') = 'USER_REQUESTED';

-- 2) WHERE THE ROWS GO: which filter clause excludes what. Explains any gap between
--    the 813 total outcomes and the cohort count above.
SELECT
  count(*)                                                          AS joined_rows_total,
  count(*) FILTER (WHERE p.is_live_data IS NOT TRUE)                AS excluded_prediction_not_live,
  count(*) FILTER (WHERE o.is_live_data IS NOT TRUE)                AS excluded_outcome_not_live,
  count(*) FILTER (WHERE coalesce(p.prediction_origin,'USER_REQUESTED') <> 'USER_REQUESTED')
                                                                    AS excluded_non_user_origin,
  count(*) FILTER (WHERE o.realized_label NOT IN ('UP','DOWN','TIMEOUT'))
                                                                    AS excluded_bad_label
FROM public.predictions p
JOIN public.prediction_outcomes o ON o.prediction_id = p.prediction_id;

-- 3) PARTITIONING by origin and live-data flags.
SELECT
  coalesce(p.prediction_origin,'(null)') AS prediction_origin,
  p.is_live_data AS prediction_live,
  o.is_live_data AS outcome_live,
  count(*) AS n
FROM public.predictions p
JOIN public.prediction_outcomes o ON o.prediction_id = p.prediction_id
GROUP BY 1,2,3
ORDER BY n DESC;

-- 4) PARTITIONING within the usable cohort, by timeframe and version. A version mix
--    raises VERSION_MIX_WARNING; per-timeframe counts are what per-scope reports see.
SELECT
  p.timeframe,
  p.model_version,
  p.methodology_version,
  count(*) AS n
FROM public.predictions p
JOIN public.prediction_outcomes o ON o.prediction_id = p.prediction_id
WHERE p.is_live_data = true
  AND o.is_live_data = true
  AND o.realized_label IN ('UP','DOWN','TIMEOUT')
  AND coalesce(p.prediction_origin,'USER_REQUESTED') = 'USER_REQUESTED'
GROUP BY 1,2,3
ORDER BY n DESC;

-- 5) The six historical derivatives smoke rows the release gate says should be
--    reclassified CONTROLLED_SMOKE. If these are still USER_REQUESTED they are
--    contaminating the cohort above.
SELECT p.prediction_id, p.symbol, p.timeframe, p.predicted_at_utc,
       p.prediction_origin, p.methodology_version
FROM public.predictions p
WHERE p.methodology_version IS NOT NULL
  AND p.methodology_version <> ''
  AND p.prediction_origin = 'USER_REQUESTED'
  AND EXISTS (
    SELECT 1 FROM public.prediction_derivatives_snapshots d
    WHERE d.prediction_id = p.prediction_id
  )
ORDER BY p.predicted_at_utc;
