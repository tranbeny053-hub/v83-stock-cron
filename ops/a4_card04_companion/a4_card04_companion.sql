-- ucpe.a4_card04_companion.v1: the sealed, read-only companion of ucpe.a4_ledger_audit.v1 for UOR Card 04.
--
-- PURPOSE, and only this: during one owner-authorized UOR qualification episode, beside the accepted A4
-- audit of the same request, prove the four durable facts Card 04 still needs, as scalars:
-- 1. deadline_ms: the request's own deadline, from its ledger row (migration 0013). The route writes it
--    once, when it reserves the row, from the validated request; it is part of the request fingerprint.
-- 2. analysis_hash: that successful run's analysis identity, from the same row. It is written with the
--    200 body it equals.
-- 3. predictions_rows_for_run_id: how many public.predictions rows (migration 0003) carry the bound run_id.
--    Isolation evidence only: the cohort writer and the isolated route draw run ids from one generator,
--    and the route never writes a prediction.
-- 4. credential_ledger_rows_since_activation: how many ledger rows the bound credential has whose
--    received_at_utc is at or after qualification_activation_utc.
-- It reads ten ledger columns and predictions.run_id, and nothing else: no other column of either
-- table, no other table, never the stored response body. The pg_catalog reads are the schema proof.
--
-- SEALED. ops/a4_card04_companion/a4_card04_companion.py pins this file's sha256 and runs it, and nothing
-- else, inside a READ ONLY transaction with row security off (a row-level policy that would hide a row
-- raises an error instead, so neither count can be silently filtered), always rolled back. A changed
-- byte is a new artifact version.
--
-- BINDING. The ledger's primary key (credential_id, client_request_id) and the response's run_id. The
-- request's deadline_ms and the response's analysis_hash are compared with the row, never trusted.
--
-- SCHEMA PROOF. Both relations are ordinary tables in public with no inheritance child (a child's rows
-- would join every read); every column read has migration 0013's or 0003's type and nullability; the
-- ledger's primary key is the pair. Anything else is SCHEMA_DRIFT. A column the companion does not
-- read is not its concern, and a missing table is a database error.
--
-- OUTPUT. Exactly one row of scalars, whatever the database holds. reason is the FIRST failing check, in
-- this order: SCHEMA_DRIFT, NO_ROW, AMBIGUOUS, WRONG_ORIGIN, NOT_COMPLETED, NOT_SUCCEEDED, RUN_MISMATCH,
-- DEADLINE_MISMATCH, ANALYSIS_HASH_MISMATCH, ACTIVATION_AFTER_REQUEST; else OK. verdict is PASS only for
-- OK. The two counts are reported, never judged: UOR Card 04 adjudicates them. Every comparison is
-- NULL-safe, so a missing fact fails closed.
WITH binding AS (
    SELECT CAST(%(credential_id)s AS text) AS credential_id,
           CAST(%(client_request_id)s AS uuid) AS client_request_id,
           CAST(%(expected_run_id)s AS text) AS expected_run_id,
           CAST(%(expected_deadline_ms)s AS integer) AS expected_deadline_ms,
           CAST(%(expected_analysis_hash)s AS text) AS expected_analysis_hash,
           CAST(%(qualification_activation_utc)s AS timestamptz) AS activation_utc
),
relations AS (
    SELECT c.oid,
           c.relname::text AS relname
      FROM pg_catalog.pg_class AS c
      JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace
     WHERE n.nspname = 'public'
       AND c.relname IN ('automation_radar_ledger', 'predictions')
       AND c.relkind = 'r'
),
expected_columns (relname, column_name, column_type, column_not_null) AS (
    VALUES ('automation_radar_ledger', 'credential_id', 'text', true),
           ('automation_radar_ledger', 'client_request_id', 'uuid', true),
           ('automation_radar_ledger', 'evidence_origin', 'text', true),
           ('automation_radar_ledger', 'state', 'text', true),
           ('automation_radar_ledger', 'outcome_code', 'text', false),
           ('automation_radar_ledger', 'http_status', 'integer', false),
           ('automation_radar_ledger', 'run_id', 'text', false),
           ('automation_radar_ledger', 'analysis_hash', 'text', false),
           ('automation_radar_ledger', 'deadline_ms', 'integer', true),
           ('automation_radar_ledger', 'received_at_utc', 'timestamp with time zone', true),
           ('predictions', 'run_id', 'text', true)
),
live_columns AS (
    SELECT r.relname,
           a.attname::text AS column_name,
           pg_catalog.format_type(a.atttypid, a.atttypmod) AS column_type,
           a.attnotnull AS column_not_null
      FROM pg_catalog.pg_attribute AS a
      JOIN relations AS r ON r.oid = a.attrelid
     WHERE a.attnum > 0
       AND NOT a.attisdropped
),
ledger_key AS (
    SELECT con.conrelid,
           con.conkey
      FROM pg_catalog.pg_constraint AS con
      JOIN relations AS r ON r.oid = con.conrelid
     WHERE r.relname = 'automation_radar_ledger'
       AND con.contype = 'p'
),
schema_check AS (
    SELECT ((SELECT count(*) FROM relations) = 2
            AND NOT EXISTS (SELECT 1
                              FROM pg_catalog.pg_inherits AS i
                              JOIN relations AS h ON h.oid = i.inhparent)
            AND NOT EXISTS (SELECT relname, column_name, column_type, column_not_null
                              FROM expected_columns
                            EXCEPT
                            SELECT relname, column_name, column_type, column_not_null
                              FROM live_columns)
            AND (SELECT count(*) FROM ledger_key) = 1
            AND (SELECT array_agg(a.attname::text ORDER BY a.attname::text)
                   FROM pg_catalog.pg_attribute AS a
                   JOIN ledger_key AS pk
                     ON a.attrelid = pk.conrelid
                    AND a.attnum = ANY (pk.conkey))
                = ARRAY['client_request_id', 'credential_id']) AS schema_ok
),
target AS (
    SELECT l.evidence_origin,
           l.state,
           l.outcome_code,
           l.http_status,
           l.run_id,
           l.analysis_hash,
           l.deadline_ms,
           l.received_at_utc
      FROM public.automation_radar_ledger AS l
      JOIN binding AS b
        ON l.credential_id = b.credential_id
       AND l.client_request_id = b.client_request_id
),
target_facts AS (
    SELECT count(*) AS matched_rows,
           CASE WHEN count(*) = 1 THEN min(t.evidence_origin) END AS evidence_origin,
           CASE WHEN count(*) = 1 THEN min(t.state) END AS state,
           CASE WHEN count(*) = 1 THEN min(t.outcome_code) END AS outcome_code,
           CASE WHEN count(*) = 1 THEN min(t.http_status) END AS http_status,
           CASE WHEN count(*) = 1 THEN min(t.run_id) END AS run_id,
           CASE WHEN count(*) = 1 THEN min(t.analysis_hash) END AS analysis_hash,
           CASE WHEN count(*) = 1 THEN min(t.deadline_ms) END AS deadline_ms,
           CASE WHEN count(*) = 1 THEN min(t.received_at_utc) END AS received_at_utc
      FROM target AS t
),
run_predictions AS (
    SELECT count(*) AS predictions_rows_for_run_id
      FROM public.predictions AS p
      JOIN binding AS b
        ON p.run_id = b.expected_run_id
),
credential_rows AS (
    SELECT count(*) AS credential_ledger_rows_since_activation
      FROM public.automation_radar_ledger AS w
      JOIN binding AS b
        ON w.credential_id = b.credential_id
       AND w.received_at_utc >= b.activation_utc
),
checks AS (
    SELECT b.credential_id AS bound_credential_id,
           b.client_request_id::text AS bound_client_request_id,
           b.expected_run_id AS bound_run_id,
           (s.schema_ok IS TRUE) AS schema_ok,
           f.matched_rows,
           f.evidence_origin,
           f.state,
           f.outcome_code,
           f.http_status,
           (f.run_id IS NOT DISTINCT FROM b.expected_run_id) AS run_id_matches,
           f.deadline_ms,
           (f.deadline_ms IS NOT DISTINCT FROM b.expected_deadline_ms) AS deadline_ms_matches,
           f.analysis_hash,
           (f.analysis_hash IS NOT DISTINCT FROM b.expected_analysis_hash) AS analysis_hash_matches,
           (f.received_at_utc >= b.activation_utc) AS activation_not_after_request,
           rp.predictions_rows_for_run_id,
           cr.credential_ledger_rows_since_activation
      FROM binding AS b
     CROSS JOIN schema_check AS s
     CROSS JOIN target_facts AS f
     CROSS JOIN run_predictions AS rp
     CROSS JOIN credential_rows AS cr
),
decision AS (
    SELECT k.*,
           CASE
               WHEN k.schema_ok IS NOT TRUE THEN 'SCHEMA_DRIFT'
               WHEN k.matched_rows = 0 THEN 'NO_ROW'
               WHEN k.matched_rows <> 1 THEN 'AMBIGUOUS'
               WHEN k.evidence_origin IS DISTINCT FROM 'AUTOMATED_RADAR' THEN 'WRONG_ORIGIN'
               WHEN k.state IS DISTINCT FROM 'COMPLETED' THEN 'NOT_COMPLETED'
               WHEN k.outcome_code IS DISTINCT FROM 'SUCCEEDED'
                    OR k.http_status IS DISTINCT FROM 200 THEN 'NOT_SUCCEEDED'
               WHEN k.run_id_matches IS NOT TRUE THEN 'RUN_MISMATCH'
               WHEN k.deadline_ms_matches IS NOT TRUE THEN 'DEADLINE_MISMATCH'
               WHEN k.analysis_hash_matches IS NOT TRUE THEN 'ANALYSIS_HASH_MISMATCH'
               WHEN k.activation_not_after_request IS NOT TRUE THEN 'ACTIVATION_AFTER_REQUEST'
               ELSE 'OK'
           END AS reason
      FROM checks AS k
)
SELECT 'ucpe.a4_card04_companion.v1' AS artifact,
       CASE WHEN d.reason = 'OK' THEN 'PASS' ELSE 'FAIL' END AS verdict,
       d.reason,
       d.bound_credential_id,
       d.bound_client_request_id,
       d.bound_run_id,
       d.schema_ok,
       d.deadline_ms,
       d.deadline_ms_matches,
       d.analysis_hash,
       d.analysis_hash_matches,
       d.predictions_rows_for_run_id,
       d.credential_ledger_rows_since_activation
  FROM decision AS d
