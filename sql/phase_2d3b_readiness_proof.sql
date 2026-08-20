BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;

WITH
parameters AS (
    SELECT
        'BTC/USDT'::text AS candidate_normalized_symbol,
        '2026-07-17T04:00:00Z'::timestamptz AS candidate_close_utc,
        'deriv-intel-okx-shadow-v1'::text AS v1_methodology,
        'deriv-intel-shadow-v0'::text AS v0_methodology,
        'SCHEDULED_SHADOW_EVIDENCE'::text AS scheduled_origin
),
relation_catalog AS (
    SELECT
        c.oid,
        n.nspname AS schema_name,
        c.relname,
        owner_role.rolname AS owner_name,
        c.relrowsecurity AS rls_enabled,
        c.relforcerowsecurity AS rls_forced
    FROM pg_catalog.pg_class AS c
    JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace
    JOIN pg_catalog.pg_roles AS owner_role ON owner_role.oid = c.relowner
    WHERE n.nspname = 'public'
      AND c.relname IN ('predictions', 'prediction_derivatives_snapshots')
      AND c.relkind IN ('r', 'p')
),
relation_state AS (
    SELECT
        (max(oid::bigint) FILTER (WHERE relname = 'predictions'))::oid AS predictions_oid,
        max(owner_name) FILTER (WHERE relname = 'predictions') AS predictions_owner,
        coalesce(bool_or(rls_enabled) FILTER (WHERE relname = 'predictions'), false)
            AS predictions_rls_enabled,
        coalesce(bool_or(rls_forced) FILTER (WHERE relname = 'predictions'), false)
            AS predictions_rls_forced,
        (max(oid::bigint) FILTER (
            WHERE relname = 'prediction_derivatives_snapshots'
        ))::oid AS pds_oid,
        max(owner_name) FILTER (WHERE relname = 'prediction_derivatives_snapshots')
            AS pds_owner,
        coalesce(
            bool_or(rls_enabled) FILTER (
                WHERE relname = 'prediction_derivatives_snapshots'
            ),
            false
        ) AS pds_rls_enabled,
        coalesce(
            bool_or(rls_forced) FILTER (
                WHERE relname = 'prediction_derivatives_snapshots'
            ),
            false
        ) AS pds_rls_forced
    FROM relation_catalog
),
current_role_state AS (
    SELECT
        current_user::text AS current_user_name,
        session_user::text AS session_user_name,
        coalesce(r.rolsuper, false) AS current_role_is_superuser,
        coalesce(r.rolbypassrls, false) AS current_role_bypasses_rls
    FROM (SELECT current_user::text AS role_name) AS active
    LEFT JOIN pg_catalog.pg_roles AS r ON r.rolname = active.role_name
),
authority_state AS (
    SELECT
        cr.current_user_name,
        cr.session_user_name,
        cr.current_role_is_superuser,
        cr.current_role_bypasses_rls,
        rs.predictions_owner,
        rs.predictions_owner = cr.current_user_name AS predictions_current_role_is_owner,
        rs.predictions_rls_enabled,
        rs.predictions_rls_forced,
        (
            SELECT count(*)::integer
            FROM pg_catalog.pg_policies
            WHERE schemaname = 'public' AND tablename = 'predictions'
        ) AS predictions_policy_count,
        rs.pds_owner,
        rs.pds_owner = cr.current_user_name AS pds_current_role_is_owner,
        rs.pds_rls_enabled,
        rs.pds_rls_forced,
        (
            SELECT count(*)::integer
            FROM pg_catalog.pg_policies
            WHERE schemaname = 'public'
              AND tablename = 'prediction_derivatives_snapshots'
        ) AS pds_policy_count,
        (
            cr.current_role_is_superuser
            OR cr.current_role_bypasses_rls
            OR (
                rs.predictions_owner = cr.current_user_name
                AND rs.pds_owner = cr.current_user_name
                AND NOT rs.predictions_rls_forced
                AND NOT rs.pds_rls_forced
            )
        ) AS authoritative_visibility
    FROM current_role_state AS cr
    CROSS JOIN relation_state AS rs
),
transaction_state AS (
    SELECT
        current_setting('transaction_read_only') AS txn_read_only,
        current_setting('transaction_isolation') AS txn_isolation,
        current_setting('transaction_read_only') = 'on'
            AND current_setting('transaction_isolation') = 'repeatable read'
            AS transaction_contract_ok
),
pds_columns AS (
    SELECT
        a.attname AS column_name,
        pg_catalog.format_type(a.atttypid, a.atttypmod) AS data_type,
        a.attnotnull AS not_null,
        pg_catalog.pg_get_expr(ad.adbin, ad.adrelid) AS default_expression
    FROM pg_catalog.pg_attribute AS a
    LEFT JOIN pg_catalog.pg_attrdef AS ad
      ON ad.adrelid = a.attrelid AND ad.adnum = a.attnum
    WHERE a.attrelid = 'public.prediction_derivatives_snapshots'::regclass
      AND a.attnum > 0
      AND NOT a.attisdropped
),
pds_column_contract AS (
    SELECT
        count(*) = 13
        AND count(*) FILTER (WHERE column_name = 'prediction_id' AND data_type = 'text'
            AND not_null) = 1
        AND count(*) FILTER (WHERE column_name = 'run_id' AND data_type = 'text'
            AND not_null) = 1
        AND count(*) FILTER (WHERE column_name = 'normalized_symbol' AND data_type = 'text'
            AND not_null) = 1
        AND count(*) FILTER (WHERE column_name = 'derivatives_schema_version'
            AND data_type = 'text' AND not_null) = 1
        AND count(*) FILTER (WHERE column_name = 'derivatives_methodology_version'
            AND data_type = 'text' AND not_null) = 1
        AND count(*) FILTER (WHERE column_name = 'influence_mode' AND data_type = 'text'
            AND not_null) = 1
        AND count(*) FILTER (WHERE column_name = 'decision_influence_frac'
            AND data_type = 'numeric' AND not_null) = 1
        AND count(*) FILTER (WHERE column_name = 'block_status' AND data_type = 'text'
            AND not_null) = 1
        AND count(*) FILTER (WHERE column_name = 'core_prediction_as_of_utc'
            AND data_type = 'timestamp with time zone' AND not_null) = 1
        AND count(*) FILTER (WHERE column_name = 'observation_as_of_utc'
            AND data_type = 'timestamp with time zone' AND not_null) = 1
        AND count(*) FILTER (WHERE column_name = 'snapshot_payload' AND data_type = 'jsonb'
            AND not_null) = 1
        AND count(*) FILTER (WHERE column_name = 'snapshot_hash' AND data_type = 'text'
            AND not_null) = 1
        AND count(*) FILTER (WHERE column_name = 'created_at'
            AND data_type = 'timestamp with time zone' AND not_null
            AND default_expression IS NOT NULL) = 1
        AS columns_ok
    FROM pds_columns
),
pds_constraint_catalog AS (
    SELECT
        con.conname,
        con.contype,
        con.confdeltype,
        lower(pg_catalog.pg_get_constraintdef(con.oid, true)) AS definition
    FROM pg_catalog.pg_constraint AS con
    WHERE con.conrelid = 'public.prediction_derivatives_snapshots'::regclass
),
pds_constraint_contract AS (
    SELECT
        count(*) FILTER (
            WHERE conname = 'prediction_derivatives_snapshots_pkey'
              AND contype = 'p'
              AND definition = 'primary key (prediction_id)'
        ) = 1 AS primary_key_ok,
        count(*) FILTER (
            WHERE contype = 'f'
              AND confdeltype = 'r'
              AND definition LIKE 'foreign key (prediction_id) references predictions(prediction_id)%'
        ) = 1 AS foreign_key_ok,
        count(*) FILTER (WHERE contype = 'c') = 27 AS check_count_ok,
        bool_or(contype = 'c' AND definition LIKE '%influence_mode%shadow_only%')
            AND bool_or(contype = 'c' AND definition LIKE '%decision_influence_frac%0%')
            AND bool_or(contype = 'c' AND definition LIKE '%observation_as_of_utc%core_prediction_as_of_utc%')
            AND bool_or(contype = 'c' AND definition LIKE '%snapshot_hash%[0-9a-f]%64%')
            AND bool_or(contype = 'c' AND definition LIKE '%snapshot_payload%normalized_symbol%')
            AND bool_or(contype = 'c' AND definition LIKE '%snapshot_payload%methodology_version%')
            AND bool_or(contype = 'c' AND definition LIKE '%snapshot_payload%provider_summary%')
            AND bool_or(contype = 'c' AND definition LIKE '%snapshot_payload%metrics%')
            AND bool_or(contype = 'c' AND definition LIKE '%not_trade_command%true%')
            AND bool_or(contype = 'c' AND definition LIKE '%not_financial_advice%true%')
            AS required_checks_ok
    FROM pds_constraint_catalog
),
pds_index_contract AS (
    SELECT count(*) = 1 AS index_ok
    FROM pg_catalog.pg_indexes
    WHERE schemaname = 'public'
      AND tablename = 'prediction_derivatives_snapshots'
      AND indexname = 'idx_pds_methodology_symbol_observation'
      AND lower(indexdef) LIKE '%(derivatives_methodology_version, normalized_symbol, observation_as_of_utc)%'
),
origin_column_contract AS (
    SELECT
        count(*) = 1
        AND bool_and(pg_catalog.format_type(a.atttypid, a.atttypmod) = 'text')
        AND bool_and(a.attnotnull)
        AND bool_and(pg_catalog.pg_get_expr(ad.adbin, ad.adrelid) = '''USER_REQUESTED''::text')
        AS column_ok
    FROM pg_catalog.pg_attribute AS a
    LEFT JOIN pg_catalog.pg_attrdef AS ad
      ON ad.adrelid = a.attrelid AND ad.adnum = a.attnum
    WHERE a.attrelid = 'public.predictions'::regclass
      AND a.attname = 'prediction_origin'
      AND a.attnum > 0
      AND NOT a.attisdropped
),
origin_constraint_contract AS (
    SELECT count(*) = 1
        AND bool_and(lower(pg_catalog.pg_get_constraintdef(con.oid, true))
            LIKE '%user_requested%controlled_smoke%scheduled_shadow_evidence%')
        AS constraint_ok
    FROM pg_catalog.pg_constraint AS con
    WHERE con.conrelid = 'public.predictions'::regclass
      AND con.conname = 'predictions_prediction_origin_chk'
      AND con.contype = 'c'
),
origin_index_contract AS (
    SELECT count(*) = 1 AS index_ok
    FROM pg_catalog.pg_indexes
    WHERE schemaname = 'public'
      AND tablename = 'predictions'
      AND indexname = 'idx_predictions_origin_methodology_tf'
      AND lower(indexdef) LIKE '%(prediction_origin, methodology_version, timeframe)%'
),
migration_contract AS (
    SELECT
        (
            to_regclass('public.prediction_derivatives_snapshots') IS NOT NULL
            AND cc.columns_ok
            AND pc.primary_key_ok
            AND pc.foreign_key_ok
            AND pc.check_count_ok
            AND pc.required_checks_ok
            AND pi.index_ok
        ) AS mig_0006_ok,
        (oc.column_ok AND ox.constraint_ok AND oi.index_ok) AS mig_0007_ok,
        (oc.column_ok AND ox.constraint_ok) AS origin_contract_ok
    FROM pds_column_contract AS cc
    CROSS JOIN pds_constraint_contract AS pc
    CROSS JOIN pds_index_contract AS pi
    CROSS JOIN origin_column_contract AS oc
    CROSS JOIN origin_constraint_contract AS ox
    CROSS JOIN origin_index_contract AS oi
),
trigger_contract AS (
    SELECT
        count(*) FILTER (
            WHERE t.tgname = 'trg_pds_reject_update' AND t.tgenabled IN ('O', 'A')
        ) = 1 AS pds_reject_update_trigger_enabled,
        count(*) FILTER (
            WHERE t.tgname = 'trg_pds_reject_delete' AND t.tgenabled IN ('O', 'A')
        ) = 1 AS pds_reject_delete_trigger_enabled,
        count(*) FILTER (
            WHERE t.tgname = 'trg_pds_reject_truncate' AND t.tgenabled IN ('O', 'A')
        ) = 1 AS pds_reject_truncate_trigger_enabled,
        count(*) FILTER (
            WHERE t.tgname IN (
                'trg_pds_reject_update',
                'trg_pds_reject_delete',
                'trg_pds_reject_truncate'
            )
              AND t.tgenabled IN ('O', 'A')
        )::integer AS pds_reject_triggers_enabled_count
    FROM pg_catalog.pg_trigger AS t
    JOIN pg_catalog.pg_proc AS p ON p.oid = t.tgfoid
    JOIN pg_catalog.pg_namespace AS n ON n.oid = p.pronamespace
    WHERE t.tgrelid = 'public.prediction_derivatives_snapshots'::regclass
      AND NOT t.tgisinternal
      AND n.nspname = 'public'
      AND p.proname = 'reject_prediction_derivatives_snapshot_mutation'
),
service_role_state AS (
    SELECT max(oid::bigint)::oid AS service_role_oid
    FROM pg_catalog.pg_roles
    WHERE rolname = 'service_role'
),
role_privilege_contract AS (
    SELECT
        sr.service_role_oid IS NOT NULL AS service_role_exists,
        coalesce(pg_catalog.has_table_privilege(sr.service_role_oid, rs.pds_oid, 'SELECT'), false)
            AS service_role_select,
        coalesce(pg_catalog.has_table_privilege(sr.service_role_oid, rs.pds_oid, 'INSERT'), false)
            AS service_role_insert,
        coalesce(pg_catalog.has_table_privilege(sr.service_role_oid, rs.pds_oid, 'UPDATE'), false)
            AS service_role_update,
        coalesce(pg_catalog.has_table_privilege(sr.service_role_oid, rs.pds_oid, 'DELETE'), false)
            AS service_role_delete,
        coalesce(pg_catalog.has_table_privilege(sr.service_role_oid, rs.pds_oid, 'TRUNCATE'), false)
            AS service_role_truncate
    FROM service_role_state AS sr
    CROSS JOIN relation_state AS rs
),
baseline_counts AS (
    SELECT
        count(*) FILTER (WHERE d.derivatives_methodology_version = p.v1_methodology)::bigint
            AS v1_snapshots,
        count(DISTINCT d.prediction_id) FILTER (
            WHERE d.derivatives_methodology_version = p.v1_methodology
        )::bigint AS v1_distinct_predictions,
        count(*) FILTER (
            WHERE d.derivatives_methodology_version = p.v1_methodology
              AND pred.prediction_origin = p.scheduled_origin
              AND pred.run_id !~ '^oosb-[0-9a-f]{32}$'
        )::bigint AS v1_scheduled_shadow_snapshots,
        count(*) FILTER (
            WHERE d.derivatives_methodology_version = p.v1_methodology
              AND pred.prediction_id IS NULL
        )::bigint AS v1_orphans,
        count(*) FILTER (WHERE d.derivatives_methodology_version = p.v0_methodology)::bigint
            AS v0_snapshots,
        count(*) FILTER (
            WHERE d.derivatives_methodology_version = p.v0_methodology
              AND pred.prediction_origin = p.scheduled_origin
              AND pred.run_id !~ '^oosb-[0-9a-f]{32}$'
        )::bigint AS v0_scheduled_shadow_snapshots,
        count(*) FILTER (
            WHERE d.derivatives_methodology_version = p.v0_methodology
              AND d.influence_mode <> 'SHADOW_ONLY'
        )::bigint AS v0_non_shadow_influence,
        count(*) FILTER (
            WHERE d.derivatives_methodology_version = p.v0_methodology
              AND CASE
                  WHEN jsonb_typeof(d.snapshot_payload->'decision_influence_frac') = 'number'
                   AND (d.snapshot_payload->>'decision_influence_frac')
                       ~ '^-?[0-9]+([.][0-9]+)?$'
                  THEN (d.snapshot_payload->>'decision_influence_frac')::numeric <> 0
                  ELSE true
              END
        )::bigint AS v0_nonzero_or_unparseable_influence
    FROM public.prediction_derivatives_snapshots AS d
    LEFT JOIN public.predictions AS pred ON pred.prediction_id = d.prediction_id
    CROSS JOIN parameters AS p
),
candidate_count AS (
    SELECT count(*)::bigint AS candidate_identity_occupied
    FROM public.predictions AS pred
    CROSS JOIN parameters AS p
    WHERE pred.normalized_symbol = p.candidate_normalized_symbol
      AND pred.timeframe IN ('1H', '4H')
      AND pred.reference_close_utc = p.candidate_close_utc
),
semantic_overlap_count AS (
    SELECT count(*)::bigint AS v0v1_semantic_overlap
    FROM public.prediction_derivatives_snapshots AS d0
    JOIN public.predictions AS p0 ON p0.prediction_id = d0.prediction_id
    JOIN public.prediction_derivatives_snapshots AS d1
      ON d1.derivatives_methodology_version = 'deriv-intel-okx-shadow-v1'
    JOIN public.predictions AS p1 ON p1.prediction_id = d1.prediction_id
    WHERE d0.derivatives_methodology_version = 'deriv-intel-shadow-v0'
      AND p0.normalized_symbol = p1.normalized_symbol
      AND p0.timeframe = p1.timeframe
      AND p0.reference_close_utc = p1.reference_close_utc
),
duplicate_group_count AS (
    SELECT count(*)::bigint AS v0_duplicate_prediction_groups
    FROM (
        SELECT d.prediction_id
        FROM public.prediction_derivatives_snapshots AS d
        WHERE d.derivatives_methodology_version = 'deriv-intel-shadow-v0'
        GROUP BY d.prediction_id
        HAVING count(*) > 1
    ) AS duplicate_groups
),
measured_counts AS (
    SELECT
        b.v1_snapshots,
        b.v1_distinct_predictions,
        b.v1_scheduled_shadow_snapshots,
        b.v1_orphans,
        c.candidate_identity_occupied,
        b.v0_snapshots,
        b.v0_scheduled_shadow_snapshots,
        s.v0v1_semantic_overlap,
        b.v0_non_shadow_influence,
        b.v0_nonzero_or_unparseable_influence,
        d.v0_duplicate_prediction_groups
    FROM baseline_counts AS b
    CROSS JOIN candidate_count AS c
    CROSS JOIN semantic_overlap_count AS s
    CROSS JOIN duplicate_group_count AS d
),
clause_results AS (
    SELECT jsonb_build_object(
        'authoritative_visibility', a.authoritative_visibility,
        'transaction_contract_ok', t.transaction_contract_ok,
        'mig_0006_ok', m.mig_0006_ok,
        'mig_0007_ok', m.mig_0007_ok,
        'origin_contract_ok', m.origin_contract_ok,
        'append_only_contract_ok',
            tr.pds_reject_update_trigger_enabled
            AND tr.pds_reject_delete_trigger_enabled
            AND tr.pds_reject_truncate_trigger_enabled
            AND tr.pds_reject_triggers_enabled_count = 3,
        'role_privilege_contract_ok',
            rp.service_role_exists
            AND rp.service_role_select
            AND rp.service_role_insert
            AND NOT rp.service_role_update
            AND NOT rp.service_role_delete
            AND NOT rp.service_role_truncate,
        'v1_baseline_zero',
            mc.v1_snapshots = 0
            AND mc.v1_distinct_predictions = 0
            AND mc.v1_scheduled_shadow_snapshots = 0
            AND mc.v1_orphans = 0,
        'candidate_identity_unoccupied', mc.candidate_identity_occupied = 0,
        'v0_baseline_expected',
            mc.v0_snapshots = 8
            AND mc.v0_scheduled_shadow_snapshots = 2,
        'semantic_overlap_zero', mc.v0v1_semantic_overlap = 0,
        'v0_safety_contract_ok',
            mc.v0_non_shadow_influence = 0
            AND mc.v0_nonzero_or_unparseable_influence = 0
            AND mc.v0_duplicate_prediction_groups = 0
    ) AS clauses
    FROM authority_state AS a
    CROSS JOIN transaction_state AS t
    CROSS JOIN migration_contract AS m
    CROSS JOIN trigger_contract AS tr
    CROSS JOIN role_privilege_contract AS rp
    CROSS JOIN measured_counts AS mc
),
proof_result AS (
    SELECT
        clauses,
        CASE
            WHEN jsonb_typeof(clauses) = 'object'
             AND NOT EXISTS (
                SELECT 1
                FROM jsonb_each(clauses) AS item
                WHERE item.value IS DISTINCT FROM 'true'::jsonb
             )
            THEN 'PASS'
            ELSE 'BLOCK'
        END AS database_proof_result
    FROM clause_results
)
SELECT jsonb_build_object(
    'schema_version', 'ucpe.phase-2d3b-db-readiness.v1',
    'captured_at_utc', to_char(clock_timestamp() AT TIME ZONE 'UTC',
        'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"'),
    'authority', jsonb_build_object(
        'current_user', a.current_user_name,
        'session_user', a.session_user_name,
        'current_role_is_superuser', a.current_role_is_superuser,
        'current_role_bypasses_rls', a.current_role_bypasses_rls,
        'authoritative_visibility', a.authoritative_visibility
    ),
    'transaction', jsonb_build_object(
        'txn_read_only', t.txn_read_only,
        'txn_isolation', t.txn_isolation
    ),
    'rls', jsonb_build_object(
        'predictions_owner', a.predictions_owner,
        'predictions_current_role_is_owner', a.predictions_current_role_is_owner,
        'predictions_rls_enabled', a.predictions_rls_enabled,
        'predictions_rls_forced', a.predictions_rls_forced,
        'predictions_policy_count', a.predictions_policy_count,
        'pds_owner', a.pds_owner,
        'pds_current_role_is_owner', a.pds_current_role_is_owner,
        'pds_rls_enabled', a.pds_rls_enabled,
        'pds_rls_forced', a.pds_rls_forced,
        'pds_policy_count', a.pds_policy_count
    ),
    'migration_contract', jsonb_build_object(
        'mig_0006_ok', m.mig_0006_ok,
        'mig_0007_ok', m.mig_0007_ok,
        'origin_contract_ok', m.origin_contract_ok
    ),
    'append_only_contract', jsonb_build_object(
        'pds_reject_update_trigger_enabled', tr.pds_reject_update_trigger_enabled,
        'pds_reject_delete_trigger_enabled', tr.pds_reject_delete_trigger_enabled,
        'pds_reject_truncate_trigger_enabled', tr.pds_reject_truncate_trigger_enabled,
        'pds_reject_triggers_enabled_count', tr.pds_reject_triggers_enabled_count
    ),
    'role_privileges', jsonb_build_object(
        'service_role_exists', rp.service_role_exists,
        'service_role_select', rp.service_role_select,
        'service_role_insert', rp.service_role_insert,
        'service_role_update', rp.service_role_update,
        'service_role_delete', rp.service_role_delete,
        'service_role_truncate', rp.service_role_truncate
    ),
    'candidate_contract', jsonb_build_object(
        'candidate_normalized_symbol', p.candidate_normalized_symbol,
        'candidate_normalized_symbol_contract_source',
            'normalize_symbol.display -> prediction_row.normalized_symbol -> derivatives snapshot',
        'candidate_reference_close_utc', to_char(p.candidate_close_utc AT TIME ZONE 'UTC',
            'YYYY-MM-DD"T"HH24:MI:SS"Z"')
    ),
    'baseline_counts', to_jsonb(mc),
    'clause_results', pr.clauses,
    'database_proof_result', pr.database_proof_result
)
FROM authority_state AS a
CROSS JOIN transaction_state AS t
CROSS JOIN migration_contract AS m
CROSS JOIN trigger_contract AS tr
CROSS JOIN role_privilege_contract AS rp
CROSS JOIN parameters AS p
CROSS JOIN measured_counts AS mc
CROSS JOIN proof_result AS pr;

ROLLBACK;
