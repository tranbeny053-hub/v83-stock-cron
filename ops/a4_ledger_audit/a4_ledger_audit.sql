-- ucpe.a4_ledger_audit.v1: the sealed, read-only A4 per-request audit of the AUTOMATED_RADAR ledger.
--
-- PURPOSE, and only this: during one owner-authorized UOR qualification episode, prove the one row of
-- public.automation_radar_ledger (migration 0013) that records one qualification request, so UOR can
-- adjudicate A4. It reads no other application table: no cohort, prediction, registry or section 5A
-- table is evidence here.
--
-- SEALED. ops/a4_ledger_audit/a4_ledger_audit.py pins this file's sha256 and runs it, and nothing else,
-- inside a READ ONLY transaction that is always rolled back. A changed byte is a new artifact version.
--
-- BINDING. The ledger's primary key (credential_id, client_request_id): a client_request_id alone is
-- not unique across credentials. run_id, release_id and evidence_hash, copied from the received 200
-- response, are cross-checked against the row.
--
-- OUTPUT. Exactly one row of scalar facts, whatever the ledger holds. Never the stored response body:
-- only five identity keys are read from it, for the consistency check. reason is the FIRST failing
-- check, in this order: SCHEMA_DRIFT, NO_ROW, AMBIGUOUS, WRONG_ORIGIN, NOT_COMPLETED, NOT_SUCCEEDED,
-- BODY_IDENTITY_MISMATCH, RUN_MISMATCH, RELEASE_MISMATCH, EVIDENCE_MISMATCH; else OK. verdict is PASS
-- only for OK. Every comparison is NULL-safe, so a missing fact fails closed.
WITH binding AS (
    SELECT CAST(%(credential_id)s AS text) AS credential_id,
           CAST(%(client_request_id)s AS uuid) AS client_request_id,
           CAST(%(expected_run_id)s AS text) AS expected_run_id,
           CAST(%(expected_release_id)s AS text) AS expected_release_id,
           CAST(%(expected_evidence_hash)s AS text) AS expected_evidence_hash
),
ledger_table AS (
    SELECT c.oid
      FROM pg_catalog.pg_class AS c
      JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace
     WHERE n.nspname = 'public'
       AND c.relname = 'automation_radar_ledger'
       AND c.relkind = 'r'
),
expected_columns (column_name, column_type, column_not_null) AS (
    VALUES ('credential_id', 'text', true),
           ('client_request_id', 'uuid', true),
           ('request_fingerprint', 'text', true),
           ('evidence_origin', 'text', true),
           ('state', 'text', true),
           ('outcome_code', 'text', false),
           ('http_status', 'integer', false),
           ('response_body', 'jsonb', false),
           ('run_id', 'text', false),
           ('analysis_hash', 'text', false),
           ('evidence_hash', 'text', false),
           ('release_id', 'text', true),
           ('deadline_ms', 'integer', true),
           ('received_at_utc', 'timestamp with time zone', true),
           ('completed_at_utc', 'timestamp with time zone', false)
),
live_columns AS (
    SELECT a.attname::text AS column_name,
           pg_catalog.format_type(a.atttypid, a.atttypmod) AS column_type,
           a.attnotnull AS column_not_null
      FROM pg_catalog.pg_attribute AS a
      JOIN ledger_table AS t ON t.oid = a.attrelid
     WHERE a.attnum > 0
       AND NOT a.attisdropped
),
primary_key AS (
    SELECT con.conkey
      FROM pg_catalog.pg_constraint AS con
      JOIN ledger_table AS t ON t.oid = con.conrelid
     WHERE con.contype = 'p'
),
schema_check AS (
    SELECT ((SELECT count(*) FROM ledger_table) = 1
            AND (SELECT count(*) FROM live_columns) = (SELECT count(*) FROM expected_columns)
            AND NOT EXISTS (SELECT column_name, column_type, column_not_null FROM expected_columns
                            EXCEPT
                            SELECT column_name, column_type, column_not_null FROM live_columns)
            AND (SELECT count(*) FROM primary_key) = 1
            AND (SELECT array_agg(a.attname::text ORDER BY a.attname::text)
                   FROM pg_catalog.pg_attribute AS a
                   JOIN ledger_table AS t ON t.oid = a.attrelid
                   JOIN primary_key AS k ON a.attnum = ANY (k.conkey))
                = ARRAY['client_request_id', 'credential_id']) AS schema_ok
),
hits AS (
    SELECT l.evidence_origin,
           l.state,
           l.outcome_code,
           l.http_status,
           l.run_id,
           l.release_id,
           l.evidence_hash,
           l.response_body ->> 'schema_version' AS body_schema_version,
           l.response_body ->> 'evidence_origin' AS body_evidence_origin,
           l.response_body ->> 'client_request_id' AS body_client_request_id,
           l.response_body ->> 'run_id' AS body_run_id,
           l.response_body ->> 'evidence_hash' AS body_evidence_hash,
           l.response_body -> 'build_info' ->> 'release_id' AS body_release_id
      FROM public.automation_radar_ledger AS l
      JOIN binding AS b
        ON l.credential_id = b.credential_id
       AND l.client_request_id = b.client_request_id
),
row_facts AS (
    SELECT count(*) AS matched_rows,
           CASE WHEN count(*) = 1 THEN min(h.evidence_origin) END AS evidence_origin,
           CASE WHEN count(*) = 1 THEN min(h.state) END AS state,
           CASE WHEN count(*) = 1 THEN min(h.outcome_code) END AS outcome_code,
           CASE WHEN count(*) = 1 THEN min(h.http_status) END AS http_status,
           CASE WHEN count(*) = 1 THEN min(h.run_id) END AS run_id,
           CASE WHEN count(*) = 1 THEN min(h.release_id) END AS release_id,
           CASE WHEN count(*) = 1 THEN min(h.evidence_hash) END AS evidence_hash,
           CASE WHEN count(*) = 1 THEN min(h.body_schema_version) END AS body_schema_version,
           CASE WHEN count(*) = 1 THEN min(h.body_evidence_origin) END AS body_evidence_origin,
           CASE WHEN count(*) = 1 THEN min(h.body_client_request_id) END AS body_client_request_id,
           CASE WHEN count(*) = 1 THEN min(h.body_run_id) END AS body_run_id,
           CASE WHEN count(*) = 1 THEN min(h.body_evidence_hash) END AS body_evidence_hash,
           CASE WHEN count(*) = 1 THEN min(h.body_release_id) END AS body_release_id
      FROM hits AS h
),
checks AS (
    SELECT b.credential_id AS bound_credential_id,
           b.client_request_id::text AS bound_client_request_id,
           (s.schema_ok IS TRUE) AS schema_ok,
           r.matched_rows,
           r.evidence_origin,
           (r.evidence_origin IS NOT DISTINCT FROM 'AUTOMATED_RADAR'
            AND r.body_evidence_origin IS NOT DISTINCT FROM 'AUTOMATED_RADAR')
               AS origin_automated_radar,
           r.state,
           r.outcome_code,
           r.http_status,
           r.run_id,
           (r.run_id IS NOT DISTINCT FROM b.expected_run_id) AS run_id_matches,
           r.release_id,
           (r.release_id IS NOT DISTINCT FROM b.expected_release_id) AS release_id_matches,
           r.evidence_hash,
           (r.evidence_hash IS NOT DISTINCT FROM b.expected_evidence_hash) AS evidence_hash_matches,
           (r.body_schema_version IS NOT DISTINCT FROM 'radar_evidence.v1'
            AND r.body_client_request_id IS NOT DISTINCT FROM b.client_request_id::text
            AND r.body_run_id IS NOT DISTINCT FROM r.run_id
            AND r.body_evidence_hash IS NOT DISTINCT FROM r.evidence_hash
            AND r.body_release_id IS NOT DISTINCT FROM r.release_id) AS body_identity_consistent
      FROM binding AS b
     CROSS JOIN schema_check AS s
     CROSS JOIN row_facts AS r
),
decision AS (
    SELECT k.*,
           CASE
               WHEN k.schema_ok IS NOT TRUE THEN 'SCHEMA_DRIFT'
               WHEN k.matched_rows = 0 THEN 'NO_ROW'
               WHEN k.matched_rows <> 1 THEN 'AMBIGUOUS'
               WHEN k.origin_automated_radar IS NOT TRUE THEN 'WRONG_ORIGIN'
               WHEN k.state IS DISTINCT FROM 'COMPLETED' THEN 'NOT_COMPLETED'
               WHEN k.outcome_code IS DISTINCT FROM 'SUCCEEDED'
                    OR k.http_status IS DISTINCT FROM 200 THEN 'NOT_SUCCEEDED'
               WHEN k.body_identity_consistent IS NOT TRUE THEN 'BODY_IDENTITY_MISMATCH'
               WHEN k.run_id_matches IS NOT TRUE THEN 'RUN_MISMATCH'
               WHEN k.release_id_matches IS NOT TRUE THEN 'RELEASE_MISMATCH'
               WHEN k.evidence_hash_matches IS NOT TRUE THEN 'EVIDENCE_MISMATCH'
               ELSE 'OK'
           END AS reason
      FROM checks AS k
)
SELECT 'ucpe.a4_ledger_audit.v1' AS audit,
       CASE WHEN d.reason = 'OK' THEN 'PASS' ELSE 'FAIL' END AS verdict,
       d.reason,
       d.bound_credential_id,
       d.bound_client_request_id,
       d.schema_ok,
       d.matched_rows,
       d.evidence_origin,
       d.origin_automated_radar,
       d.state,
       d.outcome_code,
       d.http_status,
       d.run_id,
       d.run_id_matches,
       d.release_id,
       d.release_id_matches,
       d.evidence_hash,
       d.evidence_hash_matches,
       d.body_identity_consistent
  FROM decision AS d
