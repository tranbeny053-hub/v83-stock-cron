-- Rehearsal assertion for migration 0010, run on a database REBUILT from migrations 0001-0010 with
-- Supabase's default privileges and no production state: the codified posture must hold on its own.
-- Raises on any departure. Runs ONLY in a scratch local PostgreSQL on a CI runner. It asks about
-- every table privilege the server has: MAINTAIN too on PostgreSQL 17 and later.
DO $$
DECLARE
  legacy_object text;
  api_role text;
  table_privilege text;
  table_privileges text[] := ARRAY[
    'SELECT', 'INSERT', 'UPDATE', 'DELETE', 'TRUNCATE', 'REFERENCES', 'TRIGGER'
  ];
BEGIN
  IF pg_catalog.current_setting('server_version_num')::integer >= 170000 THEN
    table_privileges := table_privileges || 'MAINTAIN'::text;
  END IF;
  FOREACH legacy_object IN ARRAY ARRAY[
    'analysis_runs',
    'analysis_timeframe_results',
    'app_events',
    'news_clusters',
    'news_evidence_links',
    'news_items',
    'prediction_outcomes',
    'predictions',
    'provider_observations',
    'watchlist'
  ]
  LOOP
    IF NOT (
      SELECT c.relrowsecurity
      FROM pg_catalog.pg_class AS c
      WHERE c.oid = pg_catalog.to_regclass('public.' || legacy_object)
    ) THEN
      RAISE EXCEPTION 'row-level security is off on %', legacy_object;
    END IF;
    FOREACH table_privilege IN ARRAY table_privileges
    LOOP
      FOREACH api_role IN ARRAY ARRAY['anon', 'authenticated']
      LOOP
        IF pg_catalog.has_table_privilege(api_role, 'public.' || legacy_object, table_privilege) THEN
          RAISE EXCEPTION '% still holds % on %', api_role, table_privilege, legacy_object;
        END IF;
      END LOOP;
      IF NOT pg_catalog.has_table_privilege(
        'service_role', 'public.' || legacy_object, table_privilege
      ) THEN
        RAISE EXCEPTION 'service_role lacks % on %', table_privilege, legacy_object;
      END IF;
    END LOOP;
  END LOOP;
  FOREACH legacy_object IN ARRAY ARRAY[
    'analysis_timeframe_results_id_seq',
    'app_events_id_seq',
    'provider_observations_id_seq'
  ]
  LOOP
    FOREACH api_role IN ARRAY ARRAY['anon', 'authenticated']
    LOOP
      IF pg_catalog.has_sequence_privilege(
        api_role, 'public.' || legacy_object, 'USAGE, SELECT, UPDATE'
      ) THEN
        RAISE EXCEPTION '% still holds a privilege on %', api_role, legacy_object;
      END IF;
    END LOOP;
    IF NOT pg_catalog.has_sequence_privilege('service_role', 'public.' || legacy_object, 'USAGE')
    THEN
      RAISE EXCEPTION 'service_role lacks USAGE on %', legacy_object;
    END IF;
  END LOOP;
END
$$;
