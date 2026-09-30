-- Rehearsal assertion for migration 0013: every Supabase API role is refused every read and write
-- of both new tables. Each probe runs in its own sub-block as that role (SET LOCAL ROLE, which the
-- sub-block's end reverts) and must fail with insufficient_privilege. A probe that is not refused
-- raises out of the block, so the step fails and nothing persists.
-- Runs ONLY in a scratch local PostgreSQL on a CI runner, as that server's superuser, which alone
-- may SET ROLE to the NOLOGIN API roles. Never run it against a real database.
DO $$
DECLARE
  asked_role text;
  probe text;
  probes_run integer := 0;
BEGIN
  FOREACH asked_role IN ARRAY ARRAY['anon', 'authenticated', 'service_role'] LOOP
    FOREACH probe IN ARRAY ARRAY[
      'SELECT count(*) FROM public.automation_credential',
      'SELECT count(*) FROM public.automation_radar_ledger',
      'SELECT secret_sha256 FROM public.automation_credential',
      'INSERT INTO public.automation_credential (credential_id, secret_sha256, status)'
        || ' VALUES (''role-probe'', pg_catalog.repeat(''a'', 64), ''ACTIVE'')',
      'INSERT INTO public.automation_radar_ledger (credential_id, client_request_id,'
        || ' request_fingerprint, state, release_id, deadline_ms, received_at_utc)'
        || ' VALUES (''role-probe'', ''3f9d2c1e-8a4b-4c2d-9e6f-1a2b3c4d5e6f'','
        || ' ''sha256:'' || pg_catalog.repeat(''a'', 64), ''IN_PROGRESS'', ''UCPE-PROBE'','
        || ' 30000, pg_catalog.now())',
      'UPDATE public.automation_credential SET status = ''REVOKED''',
      'UPDATE public.automation_radar_ledger SET state = ''COMPLETED''',
      'DELETE FROM public.automation_credential',
      'DELETE FROM public.automation_radar_ledger',
      'TRUNCATE public.automation_credential',
      'TRUNCATE public.automation_radar_ledger'
    ] LOOP
      BEGIN
        EXECUTE pg_catalog.format('SET LOCAL ROLE %I', asked_role);
        EXECUTE probe;
        RAISE EXCEPTION 'the API role % was not refused: %', asked_role, probe;
      EXCEPTION
        WHEN insufficient_privilege THEN
          probes_run := probes_run + 1;
      END;
    END LOOP;
  END LOOP;
  IF current_user <> session_user THEN
    RAISE EXCEPTION 'the probes left the role % set', current_user;
  END IF;
  IF probes_run <> 33 THEN
    RAISE EXCEPTION '% of the 33 API-role probes were refused', probes_run;
  END IF;
  RAISE NOTICE 'migration 0013 rehearsal: all 33 API-role probes were refused';
END
$$;
