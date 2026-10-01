-- Rehearsal assertion for migration 0013: every Supabase API role is refused every read and write
-- of both new tables.
-- NON-VACUOUS BY CONSTRUCTION:
-- - it refuses to run unless the session is a superuser connected over a local unix socket, the
--   only context in which SET ROLE to the NOLOGIN API roles is possible;
-- - SET LOCAL ROLE runs OUTSIDE the refusal handler, so a SET ROLE that fails aborts the script
--   instead of counting as a refusal, and the role is checked to have taken effect;
-- - only the table probe itself may raise insufficient_privilege. A probe that is not refused
--   raises out of the block, so the step fails and nothing persists;
-- - each probe ends by raising a private sentinel that unwinds its sub-block, which reverts the
--   role before the next probe.
-- Runs ONLY in a scratch local PostgreSQL on a CI runner, as that server's superuser.
-- Never run it against a real database.
DO $$
DECLARE
  asked_role text;
  probe text;
  probes_run integer := 0;
  refused boolean;
BEGIN
  IF pg_catalog.inet_server_addr() IS NOT NULL THEN
    RAISE EXCEPTION 'the role probes run only over a local unix socket';
  END IF;
  IF NOT (SELECT r.rolsuper FROM pg_catalog.pg_roles AS r WHERE r.rolname = session_user) THEN
    RAISE EXCEPTION 'the role probes run only as the scratch server''s superuser';
  END IF;
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
      refused := false;
      BEGIN
        EXECUTE pg_catalog.format('SET LOCAL ROLE %I', asked_role);
        IF current_user <> asked_role THEN
          RAISE EXCEPTION 'SET ROLE % did not take effect (current_user %)', asked_role, current_user;
        END IF;
        BEGIN
          EXECUTE probe;
        EXCEPTION
          WHEN insufficient_privilege THEN
            refused := true;
        END;
        IF NOT refused THEN
          RAISE EXCEPTION 'the API role % was not refused: %', asked_role, probe;
        END IF;
        RAISE EXCEPTION 'probe done' USING ERRCODE = 'UC013';
      EXCEPTION
        WHEN SQLSTATE 'UC013' THEN
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
