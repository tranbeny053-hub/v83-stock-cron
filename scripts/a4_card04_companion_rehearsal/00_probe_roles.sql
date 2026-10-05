-- Rehearsal fixture for ucpe.a4_card04_companion.v1: three readers of exactly the companion's eleven
-- columns. Runs ONLY in the scratch local PostgreSQL that run_scratch.sh builds from every applied
-- migration, as that server's superuser. Never run it against a real database.
--
-- a4c_probe: the least privilege the companion needs. SELECT on the ten ledger columns and on
-- predictions.run_id, and BYPASSRLS, because the companion runs with row security off and so must
-- never read through a policy. The rehearsal runs the sealed audit as this role (SET ROLE): a read of
-- any other column or table would fail with a privilege error instead of passing.
CREATE ROLE a4c_probe NOLOGIN NOINHERIT BYPASSRLS;
GRANT USAGE ON SCHEMA public TO a4c_probe;
GRANT SELECT (credential_id, client_request_id, evidence_origin, state, outcome_code, http_status,
              run_id, analysis_hash, deadline_ms, received_at_utc)
    ON TABLE public.automation_radar_ledger TO a4c_probe;
GRANT SELECT (run_id) ON TABLE public.predictions TO a4c_probe;
GRANT a4c_probe TO :"owner";

-- a4c_policy_reader: the same columns, no BYPASSRLS, and permissive policies on both tables. It could
-- see every row, but only through a policy, so the companion must refuse it.
CREATE ROLE a4c_policy_reader NOLOGIN NOINHERIT;
GRANT USAGE ON SCHEMA public TO a4c_policy_reader;
GRANT SELECT (credential_id, client_request_id, evidence_origin, state, outcome_code, http_status,
              run_id, analysis_hash, deadline_ms, received_at_utc)
    ON TABLE public.automation_radar_ledger TO a4c_policy_reader;
GRANT SELECT (run_id) ON TABLE public.predictions TO a4c_policy_reader;
CREATE POLICY a4c_policy_reader_ledger ON public.automation_radar_ledger
    FOR SELECT TO a4c_policy_reader USING (true);
CREATE POLICY a4c_policy_reader_predictions ON public.predictions
    FOR SELECT TO a4c_policy_reader USING (true);
GRANT a4c_policy_reader TO :"owner";

-- a4c_hidden_reader: the same columns, no BYPASSRLS and no policy. Row security hides every row from
-- it, so without row security off both counts would silently read zero.
CREATE ROLE a4c_hidden_reader NOLOGIN NOINHERIT;
GRANT USAGE ON SCHEMA public TO a4c_hidden_reader;
GRANT SELECT (credential_id, client_request_id, evidence_origin, state, outcome_code, http_status,
              run_id, analysis_hash, deadline_ms, received_at_utc)
    ON TABLE public.automation_radar_ledger TO a4c_hidden_reader;
GRANT SELECT (run_id) ON TABLE public.predictions TO a4c_hidden_reader;
GRANT a4c_hidden_reader TO :"owner";
