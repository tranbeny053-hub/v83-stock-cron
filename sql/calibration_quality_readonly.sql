/*
Calibration quality, matching the application's default /v1/calibration read.

This one result set answers two questions for each of 15m, 1H, 4H, 1D, 1W,
1M, plus ALL: (1) how many fetched rows are usable and how honest their
three-outcome probabilities are; and (2) within each confidence bucket, how
mean top-label confidence compares with the observed top-label hit frequency.
Scope-level values repeat on that scope's seven bucket rows. The result is
therefore bounded at exactly 7 scopes x 7 buckets = 49 rows, including empty
buckets and empty scopes; it never emits prediction-level rows.

The endpoint performs six separate timeframe-scoped reads, not one unscoped
read. Its default limit is 5,000 rows per timeframe, ordered by outcome close
time ascending. endpoint_parameters mirrors that default; ALL combines those
six fetched cohorts because the endpoint itself does not emit an ALL item.

The cohort is the repository filter: both joined rows are live, the outcome is
UP/DOWN/TIMEOUT, and a missing prediction origin is treated as USER_REQUESTED.
A fetched row is invalid if its label is outside those three values; any of its
three probabilities is absent, non-numeric/non-finite after conversion, or
outside [0,1]; or their sum is non-finite or <= 0. Database probability columns
are numeric, so the range and positive-sum predicates reject their non-finite
numeric values before safe conversion to double precision. Valid probabilities
are divided by their sum, exactly as in _normalize_row.

Brier is not a binary or averaged-per-class score. Per valid row it is the SUM
of the three squared errors between normalized UP/DOWN/TIMEOUT probabilities
and the realized one-hot outcome; brier_score is the mean of those row sums.
Top-label ties resolve UP, then DOWN, then TIMEOUT. Top-label hit rate is the
fraction of valid rows whose tie-broken top label equals the realized label.
Log loss is the mean negative natural log of the normalized probability for
the realized label, floored at 1e-12. Directional hit rate is the top-label hit
rate over the directional subset only; that subset excludes TIMEOUT outcomes.
Directional subset count is the number of valid UP/DOWN outcomes.
Bucket edges are [0.00,0.40), [0.40,0.50), [0.50,0.60), [0.60,0.70),
[0.70,0.80), [0.80,0.90), and [0.90,1.00], so probability 1.00 is in the last.
Outcome counts likewise use valid rows only. Versions use all fetched rows;
empty values are omitted, and VERSION_MIX_WARNING means either version list has
more than one distinct value. The application separately summarizes finite,
parseable terminal returns with count/mean/median/min/max; that diagnostic is
outside the requested result columns and is not used as a quality metric here.
*/
WITH
endpoint_parameters(limit_rows) AS (
  VALUES (5000::bigint)
),
endpoint_timeframes(timeframe, timeframe_sort) AS (
  VALUES
    ('15m'::text, 1),
    ('1H'::text, 2),
    ('4H'::text, 3),
    ('1D'::text, 4),
    ('1W'::text, 5),
    ('1M'::text, 6)
),
ranked_cohort AS (
  SELECT
    p.prediction_id,
    p.timeframe,
    p.p_up_frac,
    p.p_down_frac,
    p.p_timeout_frac,
    p.model_version,
    p.methodology_version,
    o.realized_label,
    row_number() OVER (
      PARTITION BY p.timeframe
      ORDER BY o.outcome_close_utc ASC
    ) AS row_in_timeframe
  FROM public.predictions AS p
  JOIN public.prediction_outcomes AS o
    ON o.prediction_id = p.prediction_id
  JOIN endpoint_timeframes AS tf
    ON tf.timeframe = p.timeframe
  WHERE p.is_live_data = true
    AND o.is_live_data = true
    AND o.realized_label IN ('UP', 'DOWN', 'TIMEOUT')
    AND coalesce(p.prediction_origin, 'USER_REQUESTED') = 'USER_REQUESTED'
),
cohort AS (
  SELECT r.*
  FROM ranked_cohort AS r
  CROSS JOIN endpoint_parameters AS ep
  WHERE r.row_in_timeframe <= ep.limit_rows
),
classified_rows AS (
  SELECT
    c.*,
    coalesce(
      c.realized_label IN ('UP', 'DOWN', 'TIMEOUT')
        AND c.p_up_frac >= 0.0 AND c.p_up_frac <= 1.0
        AND c.p_down_frac >= 0.0 AND c.p_down_frac <= 1.0
        AND c.p_timeout_frac >= 0.0 AND c.p_timeout_frac <= 1.0
        AND c.p_up_frac + c.p_down_frac + c.p_timeout_frac > 0.0,
      false
    ) AS is_valid
  FROM cohort AS c
),
valid_float_rows AS (
  SELECT
    c.*,
    c.p_up_frac::double precision AS raw_up,
    c.p_down_frac::double precision AS raw_down,
    c.p_timeout_frac::double precision AS raw_timeout,
    c.p_up_frac::double precision
      + c.p_down_frac::double precision
      + c.p_timeout_frac::double precision AS probability_sum
  FROM classified_rows AS c
  WHERE c.is_valid
),
normalized_rows AS (
  SELECT
    v.*,
    v.raw_up / v.probability_sum AS p_up,
    v.raw_down / v.probability_sum AS p_down,
    v.raw_timeout / v.probability_sum AS p_timeout
  FROM valid_float_rows AS v
),
scored_rows AS (
  SELECT
    n.*,
    CASE
      WHEN n.p_up >= n.p_down AND n.p_up >= n.p_timeout THEN 'UP'
      WHEN n.p_down >= n.p_timeout THEN 'DOWN'
      ELSE 'TIMEOUT'
    END AS top_label,
    greatest(n.p_up, n.p_down, n.p_timeout) AS top_probability,
    power(n.p_up - CASE WHEN n.realized_label = 'UP' THEN 1.0 ELSE 0.0 END, 2)
      + power(n.p_down - CASE WHEN n.realized_label = 'DOWN' THEN 1.0 ELSE 0.0 END, 2)
      + power(
          n.p_timeout - CASE WHEN n.realized_label = 'TIMEOUT' THEN 1.0 ELSE 0.0 END,
          2
        ) AS brier_value
  FROM normalized_rows AS n
),
bucketed_rows AS (
  SELECT
    s.*,
    CASE
      WHEN s.top_probability < 0.40 THEN '0.00-0.40'
      WHEN s.top_probability < 0.50 THEN '0.40-0.50'
      WHEN s.top_probability < 0.60 THEN '0.50-0.60'
      WHEN s.top_probability < 0.70 THEN '0.60-0.70'
      WHEN s.top_probability < 0.80 THEN '0.70-0.80'
      WHEN s.top_probability < 0.90 THEN '0.80-0.90'
      ELSE '0.90-1.00'
    END AS bucket
  FROM scored_rows AS s
),
scopes(scope_name, scope_sort, timeframe_filter) AS (
  SELECT tf.timeframe, tf.timeframe_sort, tf.timeframe
  FROM endpoint_timeframes AS tf
  UNION ALL
  SELECT 'ALL'::text, 7, NULL::text
),
bucket_edges(bucket, bucket_sort) AS (
  VALUES
    ('0.00-0.40'::text, 1),
    ('0.40-0.50'::text, 2),
    ('0.50-0.60'::text, 3),
    ('0.60-0.70'::text, 4),
    ('0.70-0.80'::text, 5),
    ('0.80-0.90'::text, 6),
    ('0.90-1.00'::text, 7)
),
scope_counts_and_versions AS (
  SELECT
    s.scope_name,
    s.scope_sort,
    count(c.prediction_id)::bigint AS sample_count,
    count(c.prediction_id) FILTER (WHERE c.is_valid)::bigint AS valid_count,
    count(c.prediction_id) FILTER (WHERE NOT c.is_valid)::bigint AS invalid_row_count,
    coalesce(
      array_agg(DISTINCT c.model_version ORDER BY c.model_version)
        FILTER (WHERE coalesce(c.model_version, '') <> ''),
      ARRAY[]::text[]
    ) AS model_versions,
    coalesce(
      array_agg(DISTINCT c.methodology_version ORDER BY c.methodology_version)
        FILTER (WHERE coalesce(c.methodology_version, '') <> ''),
      ARRAY[]::text[]
    ) AS methodology_versions,
    (
      count(DISTINCT c.model_version)
        FILTER (WHERE coalesce(c.model_version, '') <> '') > 1
      OR count(DISTINCT c.methodology_version)
        FILTER (WHERE coalesce(c.methodology_version, '') <> '') > 1
    ) AS version_mix_warning
  FROM scopes AS s
  LEFT JOIN classified_rows AS c
    ON s.timeframe_filter IS NULL OR c.timeframe = s.timeframe_filter
  GROUP BY s.scope_name, s.scope_sort
),
scope_metrics AS (
  SELECT
    s.scope_name,
    avg(v.brier_value) AS brier_score,
    avg(CASE WHEN v.top_label = v.realized_label THEN 1.0 ELSE 0.0 END)
      AS top_label_hit_rate,
    avg(
      -ln(
        greatest(
          CASE v.realized_label
            WHEN 'UP' THEN v.p_up
            WHEN 'DOWN' THEN v.p_down
            WHEN 'TIMEOUT' THEN v.p_timeout
          END,
          1e-12
        )
      )
    ) AS log_loss,
    avg(CASE WHEN v.top_label = v.realized_label THEN 1.0 ELSE 0.0 END)
      FILTER (WHERE v.realized_label IN ('UP', 'DOWN')) AS directional_hit_rate,
    count(v.prediction_id) FILTER (WHERE v.realized_label IN ('UP', 'DOWN'))::bigint
      AS directional_subset_count,
    count(v.prediction_id) FILTER (WHERE v.realized_label = 'UP')::bigint AS outcome_up,
    count(v.prediction_id) FILTER (WHERE v.realized_label = 'DOWN')::bigint AS outcome_down,
    count(v.prediction_id) FILTER (WHERE v.realized_label = 'TIMEOUT')::bigint
      AS outcome_timeout
  FROM scopes AS s
  LEFT JOIN bucketed_rows AS v
    ON s.timeframe_filter IS NULL OR v.timeframe = s.timeframe_filter
  GROUP BY s.scope_name
),
scope_summary AS (
  SELECT
    cv.*,
    CASE
      WHEN cv.valid_count <= 0 THEN 'NO_SAMPLES'
      WHEN cv.valid_count < 100 THEN 'INSUFFICIENT_SAMPLE'
      WHEN cv.valid_count < 300 THEN 'WARMING_UP'
      WHEN cv.valid_count < 500 THEN 'PRELIMINARY_MEASURED'
      ELSE 'MEASURED'
    END AS sample_gate,
    m.brier_score,
    m.top_label_hit_rate,
    m.log_loss,
    m.directional_hit_rate,
    m.directional_subset_count,
    m.outcome_up,
    m.outcome_down,
    m.outcome_timeout
  FROM scope_counts_and_versions AS cv
  JOIN scope_metrics AS m
    ON m.scope_name = cv.scope_name
),
reliability AS (
  SELECT
    s.scope_name,
    s.scope_sort,
    b.bucket,
    b.bucket_sort,
    count(v.prediction_id)::bigint AS bucket_n,
    avg(v.top_probability) AS mean_predicted_probability,
    avg(CASE WHEN v.top_label = v.realized_label THEN 1.0 ELSE 0.0 END)
      AS observed_frequency
  FROM scopes AS s
  CROSS JOIN bucket_edges AS b
  LEFT JOIN bucketed_rows AS v
    ON (s.timeframe_filter IS NULL OR v.timeframe = s.timeframe_filter)
   AND v.bucket = b.bucket
  GROUP BY s.scope_name, s.scope_sort, b.bucket, b.bucket_sort
)
SELECT
  ss.scope_name AS timeframe,
  ss.sample_count,
  ss.valid_count,
  ss.invalid_row_count,
  ss.sample_gate,
  round(ss.brier_score::numeric, 4) AS brier_score,
  round(ss.top_label_hit_rate::numeric, 4) AS top_label_hit_rate,
  round(ss.log_loss::numeric, 4) AS log_loss,
  round(ss.directional_hit_rate::numeric, 4) AS directional_hit_rate,
  ss.directional_subset_count,
  ss.outcome_up,
  ss.outcome_down,
  ss.outcome_timeout,
  ss.model_versions,
  ss.methodology_versions,
  ss.version_mix_warning,
  CASE WHEN ss.version_mix_warning THEN 'VERSION_MIX_WARNING' END AS version_warning,
  r.bucket,
  r.bucket_n,
  round(r.mean_predicted_probability::numeric, 4) AS mean_predicted_probability,
  round(r.observed_frequency::numeric, 4) AS observed_frequency,
  round(
    (r.mean_predicted_probability - r.observed_frequency)::numeric,
    4
  ) AS calibration_gap,
  CASE WHEN r.bucket_n < 30 THEN 'LOW_BUCKET_SAMPLE' ELSE 'OK' END
    AS bucket_sample_status
FROM scope_summary AS ss
JOIN reliability AS r
  ON r.scope_name = ss.scope_name
ORDER BY ss.scope_sort, r.bucket_sort;
