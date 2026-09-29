-- Rehearsal assertion for migration 0012. It runs on the rehearsal database after the rehearse-mode
-- apply, and on a database rebuilt from migrations 0001-0010 and 0012 alone, without 0011: the
-- resolution-status table must be exactly the reviewed one on both. One DO block that raises on any
-- departure. Every probe row is inserted in its own sub-block, which always ends in an exception and
-- so rolls back: nothing persists.
-- Runs ONLY in a scratch local PostgreSQL on a CI runner, as the tables' owner.
-- Never run it against a real database.
DO $$
DECLARE
  expected_column record;
  expected_constraint record;
  expected_index record;
  probe record;
  asked_role name;
  asked_privilege text;
  asked_privileges text[] := ARRAY[
    'SELECT', 'INSERT', 'UPDATE', 'DELETE', 'TRUNCATE', 'REFERENCES', 'TRIGGER'
  ];
  counted bigint;
  failed_state text;
  failed_message text;
  failed_constraint text;
  failed_column text;
  failed_name text;
  probes_run integer := 0;
  at_1 timestamptz := '2026-09-29 12:00:01+00';
  at_2 timestamptz := '2026-09-29 12:00:02+00';
  at_3 timestamptz := '2026-09-29 12:00:03+00';
  probe_id text := 'rehearsal-probe';
  resolver text := 'resolver-v2a';
  a_skip text := 'skip_not_due';
  an_error text := 'error_candle_invalid';
  reason_64 text := 'error_' || pg_catalog.repeat('x', 58);
  reason_65 text := 'error_' || pg_catalog.repeat('x', 59);
BEGIN
  -- (a) The thirteen columns, in order, exactly typed, with their nullability and the one default,
  -- and no identity, generation or column grant.
  SELECT count(*) INTO counted
  FROM pg_catalog.pg_attribute AS a
  WHERE a.attrelid = 'public.prediction_resolution_status'::regclass
    AND a.attnum > 0
    AND NOT a.attisdropped;
  IF counted <> 13 THEN
    RAISE EXCEPTION 'prediction_resolution_status has % columns, not 13', counted;
  END IF;
  FOR expected_column IN
    SELECT *
    FROM (
      VALUES
        (1, 'prediction_id', 'text', true, NULL),
        (2, 'resolution_status', 'text', true, NULL),
        (3, 'attempt_count', 'integer', true, NULL),
        (4, 'first_attempt_utc', 'timestamp with time zone', true, NULL),
        (5, 'last_attempt_utc', 'timestamp with time zone', true, NULL),
        (6, 'first_reason', 'text', true, NULL),
        (7, 'last_reason', 'text', true, NULL),
        (8, 'next_eligible_utc', 'timestamp with time zone', false, NULL),
        (9, 'quarantined_at_utc', 'timestamp with time zone', false, NULL),
        (10, 'resolved_at_utc', 'timestamp with time zone', false, NULL),
        (11, 'policy_version', 'text', true, NULL),
        (12, 'resolver_version', 'text', true, NULL),
        (13, 'updated_at_utc', 'timestamp with time zone', true, 'now()')
    ) AS v(column_position, column_name, type_name, not_null, default_expression)
  LOOP
    IF NOT EXISTS (
      SELECT 1
      FROM pg_catalog.pg_attribute AS a
      LEFT JOIN pg_catalog.pg_attrdef AS d ON d.adrelid = a.attrelid AND d.adnum = a.attnum
      WHERE a.attrelid = 'public.prediction_resolution_status'::regclass
        AND a.attnum = expected_column.column_position
        AND a.attname = expected_column.column_name
        AND NOT a.attisdropped
        AND pg_catalog.format_type(a.atttypid, a.atttypmod) = expected_column.type_name
        AND a.attnotnull = expected_column.not_null
        AND pg_catalog.pg_get_expr(d.adbin, d.adrelid)
          IS NOT DISTINCT FROM expected_column.default_expression
        AND a.attidentity = ''
        AND a.attgenerated = ''
        AND a.attacl IS NULL
    ) THEN
      RAISE EXCEPTION 'column % of prediction_resolution_status is not % % (NOT NULL %, default %)',
        expected_column.column_position, expected_column.column_name, expected_column.type_name,
        expected_column.not_null, COALESCE(expected_column.default_expression, 'none');
    END IF;
  END LOOP;

  -- (b) The nine constraints, each validated and of its type, and no other but NOT NULL, which
  -- PostgreSQL 18 records with contype 'n'; then the two indexes, exactly.
  FOR expected_constraint IN
    SELECT *
    FROM (
      VALUES
        ('prediction_resolution_status_pkey', 'p'),
        ('prs_prediction_id_nonblank', 'c'),
        ('prs_status_valid', 'c'),
        ('prs_attempt_count_positive', 'c'),
        ('prs_attempt_chronology', 'c'),
        ('prs_reason_format', 'c'),
        ('prs_policy_version_format', 'c'),
        ('prs_resolver_version_nonblank', 'c'),
        ('prs_state_shape', 'c')
    ) AS v(constraint_name, constraint_type)
  LOOP
    IF NOT EXISTS (
      SELECT 1
      FROM pg_catalog.pg_constraint AS c
      WHERE c.conrelid = 'public.prediction_resolution_status'::regclass
        AND c.conname = expected_constraint.constraint_name
        AND c.contype::text = expected_constraint.constraint_type
        AND c.convalidated
    ) THEN
      RAISE EXCEPTION '% is not a validated constraint of type % on prediction_resolution_status',
        expected_constraint.constraint_name, expected_constraint.constraint_type;
    END IF;
  END LOOP;
  SELECT count(*) INTO counted
  FROM pg_catalog.pg_constraint AS c
  WHERE c.conrelid = 'public.prediction_resolution_status'::regclass
    AND c.contype <> 'n';
  IF counted <> 9 THEN
    RAISE EXCEPTION 'prediction_resolution_status has % constraints, not 9', counted;
  END IF;
  FOR expected_index IN
    SELECT *
    FROM (
      VALUES
        ('prediction_resolution_status_pkey', true, ARRAY['prediction_id'], NULL),
        (
          'prediction_resolution_status_retry_idx', false,
          ARRAY['next_eligible_utc', 'prediction_id'], '(resolution_status = ''RETRYABLE''::text)'
        )
    ) AS v(index_name, is_unique, key_columns, predicate)
  LOOP
    IF NOT EXISTS (
      SELECT 1
      FROM pg_catalog.pg_index AS x
      JOIN pg_catalog.pg_class AS i ON i.oid = x.indexrelid
      WHERE x.indrelid = 'public.prediction_resolution_status'::regclass
        AND i.relname = expected_index.index_name
        AND x.indisunique = expected_index.is_unique
        AND ARRAY(
          SELECT a.attname::text
          FROM pg_catalog.unnest(x.indkey) WITH ORDINALITY AS k(attnum, n)
          LEFT JOIN pg_catalog.pg_attribute AS a
            ON a.attrelid = x.indrelid AND a.attnum = k.attnum
          ORDER BY k.n
        ) = expected_index.key_columns
        AND pg_catalog.pg_get_expr(x.indpred, x.indrelid)
          IS NOT DISTINCT FROM expected_index.predicate
    ) THEN
      RAISE EXCEPTION '% is not the reviewed index on prediction_resolution_status',
        expected_index.index_name;
    END IF;
  END LOOP;
  SELECT count(*) INTO counted
  FROM pg_catalog.pg_index AS x
  WHERE x.indrelid = 'public.prediction_resolution_status'::regclass;
  IF counted <> 2 THEN
    RAISE EXCEPTION 'prediction_resolution_status has % indexes, not 2', counted;
  END IF;

  -- (c) An ordinary table with row-level security on and not forced, and no policy.
  IF NOT EXISTS (
    SELECT 1
    FROM pg_catalog.pg_class AS c
    WHERE c.oid = 'public.prediction_resolution_status'::regclass
      AND c.relkind = 'r'
      AND c.relrowsecurity
      AND NOT c.relforcerowsecurity
  ) THEN
    RAISE EXCEPTION 'prediction_resolution_status does not have row-level security on and not forced';
  END IF;
  IF EXISTS (
    SELECT 1
    FROM pg_catalog.pg_policy AS p
    WHERE p.polrelid = 'public.prediction_resolution_status'::regclass
  ) THEN
    RAISE EXCEPTION 'prediction_resolution_status has a policy';
  END IF;

  -- (d) No table privilege at all for PUBLIC or the three API roles, to whom the default privileges
  -- granted everything when the table was created: every privilege the server has, MAINTAIN from
  -- PostgreSQL 17 on.
  IF pg_catalog.current_setting('server_version_num')::integer >= 170000 THEN
    asked_privileges := asked_privileges || 'MAINTAIN'::text;
  END IF;
  FOREACH asked_role IN ARRAY ARRAY['public', 'anon', 'authenticated', 'service_role'] LOOP
    FOREACH asked_privilege IN ARRAY asked_privileges LOOP
      IF pg_catalog.has_table_privilege(
        asked_role, 'public.prediction_resolution_status', asked_privilege
      ) THEN
        RAISE EXCEPTION '% holds % on prediction_resolution_status', asked_role, asked_privilege;
      END IF;
    END LOOP;
  END LOOP;

  -- (e) No row.
  SELECT count(*) INTO counted FROM public.prediction_resolution_status;
  IF counted <> 0 THEN
    RAISE EXCEPTION 'prediction_resolution_status holds % rows, not none', counted;
  END IF;

  -- (f) Behavioural probes. Each inserts a full row, copies times, then raises the sentinel, so the
  -- sub-block always rolls back. An accepted probe must reach the sentinel. A rejected probe must
  -- fail with exactly its SQLSTATE, from exactly what it names: the constraint for 23514 and 23505,
  -- the column for 23502. PostgreSQL tests CHECK constraints in name order, and prs_state_shape
  -- implies prs_status_valid and sorts before it, so a status outside the three names
  -- prs_state_shape. Anything else fails the rehearsal.
  FOR probe IN
    SELECT *
    FROM (
      VALUES
        ('retryable', 'accepted', NULL, 1,
         probe_id, 'RETRYABLE', 1, at_1, at_2, a_skip, an_error, at_3, NULL, NULL, 'rq-v1', resolver),
        ('quarantined', 'accepted', NULL, 1,
         probe_id, 'QUARANTINED', 5, at_1, at_2, a_skip, an_error, NULL, at_3, NULL, 'rq-v1', resolver),
        ('resolved', 'accepted', NULL, 1,
         probe_id, 'RESOLVED', 2, at_1, at_2, a_skip, an_error, NULL, NULL, at_3, 'rq-v1', resolver),
        ('first-equals-last-attempt', 'accepted', NULL, 1,
         probe_id, 'RETRYABLE', 1, at_2, at_2, a_skip, an_error, at_3, NULL, NULL, 'rq-v1', resolver),
        ('reason-64-characters', 'accepted', NULL, 1,
         probe_id, 'RETRYABLE', 1, at_1, at_2, reason_64, reason_64, at_3, NULL, NULL, 'rq-v1', resolver),
        ('policy-rq-v1', 'accepted', NULL, 1,
         probe_id, 'RETRYABLE', 1, at_1, at_2, a_skip, an_error, at_3, NULL, NULL, 'rq-v1', resolver),
        ('policy-rq-v12', 'accepted', NULL, 1,
         probe_id, 'RETRYABLE', 1, at_1, at_2, a_skip, an_error, at_3, NULL, NULL, 'rq-v12', resolver),
        ('retryable-without-next-eligible', '23514', 'prs_state_shape', 1,
         probe_id, 'RETRYABLE', 1, at_1, at_2, a_skip, an_error, NULL, NULL, NULL, 'rq-v1', resolver),
        ('retryable-with-quarantined-at', '23514', 'prs_state_shape', 1,
         probe_id, 'RETRYABLE', 1, at_1, at_2, a_skip, an_error, at_3, at_3, NULL, 'rq-v1', resolver),
        ('retryable-with-resolved-at', '23514', 'prs_state_shape', 1,
         probe_id, 'RETRYABLE', 1, at_1, at_2, a_skip, an_error, at_3, NULL, at_3, 'rq-v1', resolver),
        ('quarantined-without-quarantined-at', '23514', 'prs_state_shape', 1,
         probe_id, 'QUARANTINED', 5, at_1, at_2, a_skip, an_error, NULL, NULL, NULL, 'rq-v1', resolver),
        ('quarantined-with-next-eligible', '23514', 'prs_state_shape', 1,
         probe_id, 'QUARANTINED', 5, at_1, at_2, a_skip, an_error, at_3, at_3, NULL, 'rq-v1', resolver),
        ('quarantined-with-resolved-at', '23514', 'prs_state_shape', 1,
         probe_id, 'QUARANTINED', 5, at_1, at_2, a_skip, an_error, NULL, at_3, at_3, 'rq-v1', resolver),
        ('resolved-without-resolved-at', '23514', 'prs_state_shape', 1,
         probe_id, 'RESOLVED', 2, at_1, at_2, a_skip, an_error, NULL, NULL, NULL, 'rq-v1', resolver),
        ('resolved-with-next-eligible', '23514', 'prs_state_shape', 1,
         probe_id, 'RESOLVED', 2, at_1, at_2, a_skip, an_error, at_3, NULL, at_3, 'rq-v1', resolver),
        ('resolved-with-quarantined-at', '23514', 'prs_state_shape', 1,
         probe_id, 'RESOLVED', 2, at_1, at_2, a_skip, an_error, NULL, at_3, at_3, 'rq-v1', resolver),
        ('status-pending', '23514', 'prs_state_shape', 1,
         probe_id, 'PENDING', 1, at_1, at_2, a_skip, an_error, at_3, NULL, NULL, 'rq-v1', resolver),
        ('attempt-count-zero', '23514', 'prs_attempt_count_positive', 1,
         probe_id, 'RETRYABLE', 0, at_1, at_2, a_skip, an_error, at_3, NULL, NULL, 'rq-v1', resolver),
        ('last-attempt-before-first', '23514', 'prs_attempt_chronology', 1,
         probe_id, 'RETRYABLE', 1, at_2, at_1, a_skip, an_error, at_3, NULL, NULL, 'rq-v1', resolver),
        ('reason-failed-prefix', '23514', 'prs_reason_format', 1,
         probe_id, 'RETRYABLE', 1, at_1, at_2, 'failed_x', an_error, at_3, NULL, NULL, 'rq-v1', resolver),
        ('reason-bare-skip-prefix', '23514', 'prs_reason_format', 1,
         probe_id, 'RETRYABLE', 1, at_1, at_2, a_skip, 'skip_', at_3, NULL, NULL, 'rq-v1', resolver),
        ('reason-uppercase', '23514', 'prs_reason_format', 1,
         probe_id, 'RETRYABLE', 1, at_1, at_2, 'SKIP_X', an_error, at_3, NULL, NULL, 'rq-v1', resolver),
        ('reason-hyphen', '23514', 'prs_reason_format', 1,
         probe_id, 'RETRYABLE', 1, at_1, at_2, a_skip, 'error_x-y', at_3, NULL, NULL, 'rq-v1', resolver),
        ('reason-65-characters', '23514', 'prs_reason_format', 1,
         probe_id, 'RETRYABLE', 1, at_1, at_2, reason_65, an_error, at_3, NULL, NULL, 'rq-v1', resolver),
        ('policy-rq-v0', '23514', 'prs_policy_version_format', 1,
         probe_id, 'RETRYABLE', 1, at_1, at_2, a_skip, an_error, at_3, NULL, NULL, 'rq-v0', resolver),
        ('policy-rq-1', '23514', 'prs_policy_version_format', 1,
         probe_id, 'RETRYABLE', 1, at_1, at_2, a_skip, an_error, at_3, NULL, NULL, 'rq-1', resolver),
        ('policy-rq-v01', '23514', 'prs_policy_version_format', 1,
         probe_id, 'RETRYABLE', 1, at_1, at_2, a_skip, an_error, at_3, NULL, NULL, 'rq-v01', resolver),
        ('resolver-version-blank', '23514', 'prs_resolver_version_nonblank', 1,
         probe_id, 'RETRYABLE', 1, at_1, at_2, a_skip, an_error, at_3, NULL, NULL, 'rq-v1', '  '),
        ('prediction-id-blank', '23514', 'prs_prediction_id_nonblank', 1,
         ' ', 'RETRYABLE', 1, at_1, at_2, a_skip, an_error, at_3, NULL, NULL, 'rq-v1', resolver),
        ('first-reason-null', '23502', 'first_reason', 1,
         probe_id, 'RETRYABLE', 1, at_1, at_2, NULL, an_error, at_3, NULL, NULL, 'rq-v1', resolver),
        ('prediction-id-twice', '23505', 'prediction_resolution_status_pkey', 2,
         probe_id, 'RETRYABLE', 1, at_1, at_2, a_skip, an_error, at_3, NULL, NULL, 'rq-v1', resolver)
    ) AS v(
      probe_name, expected, rejected_by, copies,
      prediction_id, resolution_status, attempt_count, first_attempt_utc, last_attempt_utc,
      first_reason, last_reason, next_eligible_utc, quarantined_at_utc, resolved_at_utc,
      policy_version, resolver_version
    )
  LOOP
    probes_run := probes_run + 1;
    BEGIN
      INSERT INTO public.prediction_resolution_status (
        prediction_id, resolution_status, attempt_count, first_attempt_utc, last_attempt_utc,
        first_reason, last_reason, next_eligible_utc, quarantined_at_utc, resolved_at_utc,
        policy_version, resolver_version
      )
      SELECT
        probe.prediction_id, probe.resolution_status, probe.attempt_count,
        probe.first_attempt_utc, probe.last_attempt_utc, probe.first_reason, probe.last_reason,
        probe.next_eligible_utc, probe.quarantined_at_utc, probe.resolved_at_utc,
        probe.policy_version, probe.resolver_version
      FROM pg_catalog.generate_series(1, probe.copies);
      RAISE EXCEPTION 'migration 0012 rehearsal probe accepted';
    EXCEPTION
      WHEN OTHERS THEN
        GET STACKED DIAGNOSTICS
          failed_state = RETURNED_SQLSTATE,
          failed_message = MESSAGE_TEXT,
          failed_constraint = CONSTRAINT_NAME,
          failed_column = COLUMN_NAME;
        -- A not-null violation names its column; a check or unique violation, its constraint.
        failed_name := CASE WHEN failed_state = '23502' THEN failed_column ELSE failed_constraint END;
        IF probe.expected = 'accepted' THEN
          IF failed_state <> 'P0001' OR failed_message <> 'migration 0012 rehearsal probe accepted' THEN
            RAISE EXCEPTION 'probe % must be accepted, but failed with %: %',
              probe.probe_name, failed_state, failed_message;
          END IF;
        ELSIF failed_state <> probe.expected THEN
          RAISE EXCEPTION 'probe % failed with % (%), not with %, which % must raise',
            probe.probe_name, failed_state, failed_message, probe.expected, probe.rejected_by;
        ELSIF failed_name IS DISTINCT FROM probe.rejected_by THEN
          RAISE EXCEPTION 'probe % was rejected by %, not by %',
            probe.probe_name, failed_name, probe.rejected_by;
        END IF;
    END;
  END LOOP;

  IF probes_run <> 31 THEN
    RAISE EXCEPTION 'ran % probes, not 31', probes_run;
  END IF;
  SELECT count(*) INTO counted FROM public.prediction_resolution_status;
  IF counted <> 0 THEN
    RAISE EXCEPTION 'a rehearsal probe row persisted';
  END IF;
END
$$;
