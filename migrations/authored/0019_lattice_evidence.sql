-- NG4: the dormant lattice's separate, append-only evidence store (Route S; owner NG4-D1/D2/D3, 2026-11-05).
--
-- AUTHORED, NOT APPLIED. No apply route exists. Applying it is a future owner-authorized T4 through a one-shot route
-- still to be written, which runs it in one transaction, as the tables' owner holding CREATEROLE. It lives in
-- migrations/authored/ on purpose: every tool that globs migrations reads only migrations/*.sql or
-- migrations/[0-9]...*.sql, so none builds, compares or applies it, and scripts/apply_migrations.py refuses it by name.
-- The future route moves it to migrations/ when it applies it; until then the number 0019 is reserved.
--
-- WHAT IT IS. Schema ucpe_lattice, not public: PostgREST serves only its configured schemas, and Supabase's public
-- default privileges never apply here. Four tables, all append-only (UPDATE, DELETE and TRUNCATE refused by triggers,
-- as 0014 does for the core evidence), with row-level security enabled and forced and policies for the owner only.
-- Three SECURITY DEFINER functions are the only way in; the writer may execute them and has no table privilege.
-- Rows are TEST_ONLY reference rows of the E1_OPERATIONAL population (Addendum 5 S-E1): no claim admits them, nothing
-- reads them, and no E3 row can be written until a later migration admits one (7.4, the commit delay, S-E3).
-- Nothing here touches public.predictions or any existing table, role or grant.
--
-- COMMIT TIME (Addendum 5 S-C1; owner NG4 invariant). capture_commit_receipts records PostgreSQL's own commit
-- timestamp, pg_xact_commit_timestamp(xmin), which exists only while the server runs with track_commit_timestamp = on.
-- Otherwise every receipt is COMMIT_UNKNOWN, which is final. No insert time, statement time or transaction start is
-- ever recorded as a commit time. HOLD-1: whether production runs with the setting on is unknown.
--
-- TRUSTED ADMINS. On PostgreSQL 16+ the CREATEROLE runner keeps the ADMIN OPTION it gets on each role it creates, and
-- the owner can disable a trigger or a policy. Append-only therefore rests on who can reach ucpe_lattice_owner: the
-- runner and superusers, the same principals that own public.predictions and 0014's triggers today.
--
-- ROLLBACK. A separate T4, never automatic: DROP SCHEMA ucpe_lattice CASCADE; DROP ROLE ucpe_lattice_writer;
-- DROP ROLE ucpe_lattice_owner.

DO $$
BEGIN
    IF current_setting('server_version_num')::int < 160000 THEN
        RAISE EXCEPTION '0019: PostgreSQL 16 or later is required' USING ERRCODE = 'UP019';
    END IF;
    IF EXISTS (SELECT 1 FROM pg_catalog.pg_namespace WHERE nspname = 'ucpe_lattice') THEN
        RAISE EXCEPTION '0019: schema ucpe_lattice exists; a second application is refused' USING ERRCODE = 'UP019';
    END IF;
    IF EXISTS (
        SELECT 1 FROM pg_catalog.pg_roles WHERE rolname IN ('ucpe_lattice_owner', 'ucpe_lattice_writer')
    ) THEN
        RAISE EXCEPTION '0019: a lattice role exists; a second application is refused' USING ERRCODE = 'UP019';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = current_user AND (rolcreaterole OR rolsuper)
    ) THEN
        RAISE EXCEPTION '0019: the applying role needs CREATEROLE' USING ERRCODE = 'UP019';
    END IF;
    -- Isolation preconditions: no role but superusers and the runner may bypass row-level security while holding
    -- the predefined read-all or write-all data roles, and no publication may publish every table.
    IF EXISTS (
        SELECT 1 FROM pg_catalog.pg_roles r
         WHERE r.rolbypassrls AND NOT r.rolsuper AND r.rolname <> current_user
           AND (pg_catalog.pg_has_role(r.oid, 'pg_read_all_data', 'MEMBER')
                OR pg_catalog.pg_has_role(r.oid, 'pg_write_all_data', 'MEMBER'))
    ) THEN
        RAISE EXCEPTION '0019: a non-superuser role bypasses RLS and holds pg_read_all_data or pg_write_all_data'
            USING ERRCODE = 'UP019';
    END IF;
    IF EXISTS (SELECT 1 FROM pg_catalog.pg_publication WHERE puballtables) THEN
        RAISE EXCEPTION '0019: a FOR ALL TABLES publication exists' USING ERRCODE = 'UP019';
    END IF;
END;
$$;

CREATE ROLE ucpe_lattice_owner NOLOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
CREATE ROLE ucpe_lattice_writer NOLOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;

-- The temporary hand-off, as 0016 and 0018: SET on the owner, revoked at the end of this file.
GRANT ucpe_lattice_owner TO CURRENT_USER WITH INHERIT FALSE, SET TRUE;

CREATE SCHEMA ucpe_lattice AUTHORIZATION ucpe_lattice_owner;

-- Every object below is created by the owner itself, so no other creator's default privileges apply.
SET ROLE ucpe_lattice_owner;

CREATE TABLE ucpe_lattice.lattice_rows (
    lattice_row_id text PRIMARY KEY
        CHECK (lattice_row_id ~ '^e3l-[0-9a-f]{32}:(15m|1H|4H|1D):REF$'),
    lattice_run_id text NOT NULL
        CHECK (lattice_run_id ~ '^e3l-[0-9a-f]{32}$'),
    lattice_instant_utc timestamptz NOT NULL,
    reference_close_utc timestamptz NOT NULL,
    horizon_end_utc timestamptz NOT NULL,
    predicted_at_utc timestamptz NOT NULL,
    core_computed_at_utc timestamptz NOT NULL,
    issued_at_utc timestamptz NOT NULL,
    protocol_version text NOT NULL CHECK (protocol_version = 'E3_LATTICE_V1'),
    evaluation_population text NOT NULL CHECK (evaluation_population = 'E1_OPERATIONAL'),
    timing_class text NOT NULL CHECK (timing_class = 'NOT_APPLICABLE'),
    evidence_use text NOT NULL CHECK (evidence_use = 'TEST_ONLY'),
    arm text NOT NULL CHECK (arm = 'REF'),
    artifact_id text CHECK (artifact_id IS NULL),
    recipe_id text NOT NULL CHECK (length(recipe_id) BETWEEN 1 AND 128),
    methodology_version text NOT NULL CHECK (length(methodology_version) BETWEEN 1 AND 128),
    reference_prior_id text NOT NULL CHECK (length(reference_prior_id) BETWEEN 1 AND 128),
    normalized_symbol text NOT NULL CHECK (length(normalized_symbol) BETWEEN 1 AND 64),
    reference_venue text NOT NULL CHECK (length(reference_venue) BETWEEN 1 AND 64),
    data_source text NOT NULL CHECK (length(data_source) BETWEEN 1 AND 64),
    provider text NOT NULL CHECK (length(provider) BETWEEN 1 AND 64),
    timeframe text NOT NULL CHECK (timeframe IN ('15m', '1H', '4H', '1D')),
    horizon_bars integer NOT NULL CHECK (horizon_bars BETWEEN 1 AND 96),
    target_version text NOT NULL CHECK (target_version = 'tc-v1'),
    is_live_data boolean NOT NULL CHECK (is_live_data),
    reference_price numeric NOT NULL CHECK (reference_price > 0),
    decision_band_frac numeric NOT NULL CHECK (decision_band_frac >= 0),
    p_up_frac double precision NOT NULL CHECK (p_up_frac BETWEEN 0 AND 1),
    p_down_frac double precision NOT NULL CHECK (p_down_frac BETWEEN 0 AND 1),
    p_timeout_frac double precision NOT NULL CHECK (p_timeout_frac BETWEEN 0 AND 1),
    db_insert_clock_utc timestamptz NOT NULL DEFAULT pg_catalog.clock_timestamp(),
    CONSTRAINT lattice_rows_run_prefix CHECK (lattice_run_id = split_part(lattice_row_id, ':', 1)),
    CONSTRAINT lattice_rows_timeframe_suffix CHECK (split_part(lattice_row_id, ':', 2) = timeframe),
    CONSTRAINT lattice_rows_source_not_before_instant CHECK (predicted_at_utc >= lattice_instant_utc),
    -- tc-v1's I1 clock order and I8 venue rule, mirrored here (contract_v1.validate_v1).
    CONSTRAINT lattice_rows_close_before_source CHECK (reference_close_utc <= predicted_at_utc),
    CONSTRAINT lattice_rows_source_before_computed CHECK (predicted_at_utc <= core_computed_at_utc),
    CONSTRAINT lattice_rows_computed_before_issue CHECK (core_computed_at_utc <= issued_at_utc),
    CONSTRAINT lattice_rows_close_is_the_instant CHECK (reference_close_utc = lattice_instant_utc),
    CONSTRAINT lattice_rows_one_venue CHECK (data_source = reference_venue),
    CONSTRAINT lattice_rows_horizon_after_issue CHECK (horizon_end_utc > issued_at_utc),
    CONSTRAINT lattice_rows_horizon_after_close CHECK (horizon_end_utc > reference_close_utc),
    CONSTRAINT lattice_rows_triplet_sums_to_one
        CHECK (abs(p_up_frac + p_down_frac + p_timeout_frac - 1) <= 1e-9)
);
COMMENT ON COLUMN ucpe_lattice.lattice_rows.db_insert_clock_utc IS
    'insert-time DB clock (clock_timestamp at insert); NOT the commit time';

CREATE TABLE ucpe_lattice.lattice_commit_receipts (
    lattice_row_id text PRIMARY KEY REFERENCES ucpe_lattice.lattice_rows (lattice_row_id),
    commit_state text NOT NULL CHECK (commit_state IN ('COMMITTED', 'COMMIT_UNKNOWN')),
    commit_ts_utc timestamptz,
    commit_ts_source text NOT NULL CHECK (commit_ts_source = 'pg_xact_commit_timestamp'),
    captured_at_db_clock timestamptz NOT NULL DEFAULT pg_catalog.clock_timestamp(),
    CONSTRAINT lattice_commit_receipts_state_time
        CHECK ((commit_state = 'COMMITTED') = (commit_ts_utc IS NOT NULL))
);
COMMENT ON COLUMN ucpe_lattice.lattice_commit_receipts.captured_at_db_clock IS
    'when the receipt was captured; NOT the commit time';

CREATE TABLE ucpe_lattice.lattice_missed_instants (
    lattice_run_id text NOT NULL CHECK (lattice_run_id ~ '^e3l-[0-9a-f]{32}$'),
    timeframe text NOT NULL CHECK (timeframe IN ('15m', '1H', '4H', '1D')),
    normalized_symbol text NOT NULL CHECK (length(normalized_symbol) BETWEEN 1 AND 64),
    reference_venue text NOT NULL CHECK (length(reference_venue) BETWEEN 1 AND 64),
    lattice_instant_utc timestamptz NOT NULL,
    reason text NOT NULL CHECK (reason IN (
        'STALE_SNAPSHOT', 'FETCH_FAILED', 'WINDOW_UNAVAILABLE', 'REFERENCE_UNAVAILABLE', 'NOT_ISSUED', 'CAPACITY_STOP'
    )),
    protocol_version text NOT NULL CHECK (protocol_version = 'E3_LATTICE_V1'),
    evidence_use text NOT NULL CHECK (evidence_use = 'TEST_ONLY'),
    logged_at_db_clock timestamptz NOT NULL DEFAULT pg_catalog.clock_timestamp(),
    PRIMARY KEY (lattice_run_id, timeframe)
);

CREATE TABLE ucpe_lattice.lattice_capacity (
    id boolean PRIMARY KEY DEFAULT true CHECK (id),
    max_rows integer NOT NULL CHECK (max_rows > 0),
    warn_rows integer NOT NULL CHECK (warn_rows > 0 AND warn_rows < max_rows),
    note text NOT NULL CHECK (length(note) BETWEEN 1 AND 500)
);

CREATE FUNCTION ucpe_lattice.reject_mutation() RETURNS trigger
LANGUAGE plpgsql
SET search_path = ''
AS $$
BEGIN
    RAISE EXCEPTION 'the lattice store is append-only: % on % is refused', TG_OP, TG_TABLE_NAME;
END;
$$;
REVOKE ALL ON FUNCTION ucpe_lattice.reject_mutation() FROM PUBLIC;

DO $$
DECLARE
    t text;
BEGIN
    FOREACH t IN ARRAY ARRAY['lattice_rows', 'lattice_commit_receipts', 'lattice_missed_instants', 'lattice_capacity']
    LOOP
        EXECUTE format(
            'CREATE TRIGGER %I BEFORE UPDATE OR DELETE ON ucpe_lattice.%I FOR EACH ROW '
            'EXECUTE FUNCTION ucpe_lattice.reject_mutation()', t || '_append_only', t);
        EXECUTE format(
            'CREATE TRIGGER %I BEFORE TRUNCATE ON ucpe_lattice.%I FOR EACH STATEMENT '
            'EXECUTE FUNCTION ucpe_lattice.reject_mutation()', t || '_no_truncate', t);
        EXECUTE format('ALTER TABLE ucpe_lattice.%I ENABLE ROW LEVEL SECURITY', t);
        EXECUTE format('ALTER TABLE ucpe_lattice.%I FORCE ROW LEVEL SECURITY', t);
        EXECUTE format('CREATE POLICY owner_select ON ucpe_lattice.%I FOR SELECT TO ucpe_lattice_owner USING (true)', t);
        EXECUTE format(
            'CREATE POLICY owner_insert ON ucpe_lattice.%I FOR INSERT TO ucpe_lattice_owner WITH CHECK (true)', t);
    END LOOP;
END;
$$;

-- Rows plus missed instants count against the capacity (receipts are at most one per row). No capacity row: refused.
CREATE FUNCTION ucpe_lattice.capacity_status() RETURNS text
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_max integer;
    v_warn integer;
    v_used bigint;
BEGIN
    SELECT max_rows, warn_rows INTO v_max, v_warn FROM ucpe_lattice.lattice_capacity WHERE id;
    IF NOT FOUND THEN
        RETURN 'CAPACITY_UNSET';
    END IF;
    SELECT (SELECT count(*) FROM ucpe_lattice.lattice_rows)
         + (SELECT count(*) FROM ucpe_lattice.lattice_missed_instants)
      INTO v_used;
    IF v_used >= v_max THEN
        RETURN 'CAPACITY_STOP';
    ELSIF v_used + 1 >= v_warn THEN
        RETURN 'WARN';
    END IF;
    RETURN 'OK';
END;
$$;
REVOKE ALL ON FUNCTION ucpe_lattice.capacity_status() FROM PUBLIC;

CREATE FUNCTION ucpe_lattice.record_lattice_row(p_row jsonb) RETURNS text
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_keys text[] := ARRAY[
        'lattice_row_id', 'lattice_run_id', 'lattice_instant_utc', 'reference_close_utc', 'horizon_end_utc',
        'predicted_at_utc', 'core_computed_at_utc', 'issued_at_utc', 'protocol_version', 'evaluation_population',
        'timing_class', 'evidence_use', 'arm', 'artifact_id', 'recipe_id', 'methodology_version',
        'reference_prior_id', 'normalized_symbol', 'reference_venue', 'data_source', 'provider',
        'timeframe', 'horizon_bars', 'target_version', 'is_live_data', 'reference_price', 'decision_band_frac',
        'p_up_frac', 'p_down_frac', 'p_timeout_frac'
    ];
    v_capacity text;
    v_r ucpe_lattice.lattice_rows;
BEGIN
    IF p_row IS NULL OR pg_catalog.jsonb_typeof(p_row) <> 'object'
       OR (SELECT pg_catalog.array_agg(k ORDER BY k) FROM pg_catalog.jsonb_object_keys(p_row) AS k)
          IS DISTINCT FROM (SELECT pg_catalog.array_agg(k ORDER BY k) FROM pg_catalog.unnest(v_keys) AS k) THEN
        RAISE EXCEPTION 'record_lattice_row: the row must carry exactly the lattice columns' USING ERRCODE = '22023';
    END IF;
    PERFORM pg_catalog.pg_advisory_xact_lock(190019, 1);
    v_capacity := ucpe_lattice.capacity_status();
    IF v_capacity IN ('CAPACITY_UNSET', 'CAPACITY_STOP') THEN
        RETURN v_capacity;
    END IF;
    v_r := pg_catalog.jsonb_populate_record(NULL::ucpe_lattice.lattice_rows, p_row);
    INSERT INTO ucpe_lattice.lattice_rows (
        lattice_row_id, lattice_run_id, lattice_instant_utc, reference_close_utc, horizon_end_utc, predicted_at_utc,
        core_computed_at_utc, issued_at_utc, protocol_version, evaluation_population, timing_class, evidence_use,
        arm, artifact_id, recipe_id, methodology_version, reference_prior_id, normalized_symbol, reference_venue,
        data_source, provider, timeframe, horizon_bars, target_version, is_live_data, reference_price,
        decision_band_frac, p_up_frac, p_down_frac, p_timeout_frac
    ) VALUES (
        v_r.lattice_row_id, v_r.lattice_run_id, v_r.lattice_instant_utc, v_r.reference_close_utc,
        v_r.horizon_end_utc, v_r.predicted_at_utc, v_r.core_computed_at_utc, v_r.issued_at_utc,
        v_r.protocol_version, v_r.evaluation_population, v_r.timing_class, v_r.evidence_use, v_r.arm,
        v_r.artifact_id, v_r.recipe_id, v_r.methodology_version, v_r.reference_prior_id, v_r.normalized_symbol,
        v_r.reference_venue, v_r.data_source, v_r.provider, v_r.timeframe, v_r.horizon_bars,
        v_r.target_version, v_r.is_live_data, v_r.reference_price, v_r.decision_band_frac, v_r.p_up_frac,
        v_r.p_down_frac,
        v_r.p_timeout_frac
    ) ON CONFLICT (lattice_row_id) DO NOTHING;
    IF NOT FOUND THEN
        RETURN 'DUPLICATE';
    END IF;
    RETURN CASE WHEN v_capacity = 'WARN' THEN 'INSERTED_WARN' ELSE 'INSERTED' END;
END;
$$;

CREATE FUNCTION ucpe_lattice.record_missed_instant(p_entry jsonb) RETURNS text
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_keys text[] := ARRAY[
        'lattice_run_id', 'timeframe', 'normalized_symbol', 'reference_venue', 'lattice_instant_utc', 'reason',
        'protocol_version', 'evidence_use'
    ];
    v_capacity text;
    v_m ucpe_lattice.lattice_missed_instants;
BEGIN
    IF p_entry IS NULL OR pg_catalog.jsonb_typeof(p_entry) <> 'object'
       OR (SELECT pg_catalog.array_agg(k ORDER BY k) FROM pg_catalog.jsonb_object_keys(p_entry) AS k)
          IS DISTINCT FROM (SELECT pg_catalog.array_agg(k ORDER BY k) FROM pg_catalog.unnest(v_keys) AS k) THEN
        RAISE EXCEPTION 'record_missed_instant: the entry must carry exactly the missed-instant columns'
            USING ERRCODE = '22023';
    END IF;
    PERFORM pg_catalog.pg_advisory_xact_lock(190019, 1);
    v_capacity := ucpe_lattice.capacity_status();
    IF v_capacity IN ('CAPACITY_UNSET', 'CAPACITY_STOP') THEN
        RETURN v_capacity;
    END IF;
    v_m := pg_catalog.jsonb_populate_record(NULL::ucpe_lattice.lattice_missed_instants, p_entry);
    INSERT INTO ucpe_lattice.lattice_missed_instants (
        lattice_run_id, timeframe, normalized_symbol, reference_venue, lattice_instant_utc, reason,
        protocol_version, evidence_use
    ) VALUES (
        v_m.lattice_run_id, v_m.timeframe, v_m.normalized_symbol, v_m.reference_venue, v_m.lattice_instant_utc,
        v_m.reason, v_m.protocol_version, v_m.evidence_use
    ) ON CONFLICT (lattice_run_id, timeframe) DO NOTHING;
    IF NOT FOUND THEN
        RETURN 'DUPLICATE';
    END IF;
    RETURN 'LOGGED';
END;
$$;

-- Runs in a fresh transaction only: a row this transaction wrote has no commit timestamp yet. It tests the setting
-- before the call, which raises when track_commit_timestamp is off. A receipt is written once and never replaced.
CREATE FUNCTION ucpe_lattice.capture_commit_receipts(p_limit integer) RETURNS integer
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_row record;
    v_ts timestamptz;
    v_state text;
    v_added integer;
    v_count integer := 0;
BEGIN
    IF pg_catalog.pg_current_xact_id_if_assigned() IS NOT NULL THEN
        RAISE EXCEPTION 'capture_commit_receipts must run in a fresh transaction' USING ERRCODE = '25000';
    END IF;
    IF p_limit IS NULL OR p_limit < 1 OR p_limit > 1000 THEN
        RAISE EXCEPTION 'capture_commit_receipts: p_limit must be 1 to 1000' USING ERRCODE = '22023';
    END IF;
    PERFORM pg_catalog.pg_advisory_xact_lock(190019, 2);
    FOR v_row IN
        SELECT r.lattice_row_id, r.xmin AS row_xmin
          FROM ucpe_lattice.lattice_rows r
         WHERE NOT EXISTS (
               SELECT 1 FROM ucpe_lattice.lattice_commit_receipts c WHERE c.lattice_row_id = r.lattice_row_id)
         ORDER BY r.db_insert_clock_utc, r.lattice_row_id
         LIMIT p_limit
    LOOP
        v_ts := NULL;
        v_state := 'COMMIT_UNKNOWN';
        IF pg_catalog.current_setting('track_commit_timestamp') = 'on' THEN
            v_ts := pg_catalog.pg_xact_commit_timestamp(v_row.row_xmin);
            IF v_ts IS NOT NULL THEN
                v_state := 'COMMITTED';
            END IF;
        END IF;
        INSERT INTO ucpe_lattice.lattice_commit_receipts (lattice_row_id, commit_state, commit_ts_utc, commit_ts_source)
        VALUES (v_row.lattice_row_id, v_state, v_ts, 'pg_xact_commit_timestamp')
        ON CONFLICT (lattice_row_id) DO NOTHING;
        GET DIAGNOSTICS v_added = ROW_COUNT;
        v_count := v_count + v_added;
    END LOOP;
    RETURN v_count;
END;
$$;

REVOKE ALL ON SCHEMA ucpe_lattice FROM PUBLIC;
ALTER DEFAULT PRIVILEGES FOR ROLE ucpe_lattice_owner IN SCHEMA ucpe_lattice REVOKE ALL ON TABLES FROM PUBLIC;
ALTER DEFAULT PRIVILEGES FOR ROLE ucpe_lattice_owner IN SCHEMA ucpe_lattice REVOKE ALL ON SEQUENCES FROM PUBLIC;
ALTER DEFAULT PRIVILEGES FOR ROLE ucpe_lattice_owner IN SCHEMA ucpe_lattice REVOKE ALL ON FUNCTIONS FROM PUBLIC;
REVOKE ALL ON ALL TABLES IN SCHEMA ucpe_lattice FROM PUBLIC;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA ucpe_lattice FROM PUBLIC;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA ucpe_lattice FROM PUBLIC;

DO $$
DECLARE
    r text;
BEGIN
    FOREACH r IN ARRAY ARRAY[
        'anon', 'authenticated', 'service_role', 'authenticator',
        'ucpe_api_writer', 'ucpe_bundle_owner', 'ucpe_space_db', 'ucpe_resolver'
    ]
    LOOP
        IF EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = r) THEN
            EXECUTE format('REVOKE ALL ON SCHEMA ucpe_lattice FROM %I', r);
            EXECUTE format('REVOKE ALL ON ALL TABLES IN SCHEMA ucpe_lattice FROM %I', r);
            EXECUTE format('REVOKE ALL ON ALL SEQUENCES IN SCHEMA ucpe_lattice FROM %I', r);
            EXECUTE format('REVOKE ALL ON ALL FUNCTIONS IN SCHEMA ucpe_lattice FROM %I', r);
        END IF;
    END LOOP;
END;
$$;

GRANT USAGE ON SCHEMA ucpe_lattice TO ucpe_lattice_writer;
GRANT EXECUTE ON FUNCTION
    ucpe_lattice.record_lattice_row(jsonb),
    ucpe_lattice.record_missed_instant(jsonb),
    ucpe_lattice.capture_commit_receipts(integer)
TO ucpe_lattice_writer;

RESET ROLE;
REVOKE ucpe_lattice_owner FROM CURRENT_USER;

-- Self-check: no role but the owner, the writer and superusers holds any privilege on the schema or its objects, the
-- writer holds no table privilege, and the hand-off grant is gone.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
          FROM (
                SELECT n.nspacl AS acl FROM pg_catalog.pg_namespace n WHERE n.nspname = 'ucpe_lattice'
                UNION ALL
                SELECT c.relacl FROM pg_catalog.pg_class c
                  JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname = 'ucpe_lattice'
                UNION ALL
                SELECT p.proacl FROM pg_catalog.pg_proc p
                  JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace WHERE n.nspname = 'ucpe_lattice'
               ) o
          CROSS JOIN LATERAL pg_catalog.aclexplode(o.acl) a
          LEFT JOIN pg_catalog.pg_roles g ON g.oid = a.grantee
         WHERE o.acl IS NOT NULL
           AND (a.grantee = 0 OR (g.rolname NOT IN ('ucpe_lattice_owner', 'ucpe_lattice_writer') AND NOT g.rolsuper))
    ) THEN
        RAISE EXCEPTION '0019 self-check: an unexpected privilege on ucpe_lattice' USING ERRCODE = 'UP019';
    END IF;
    IF EXISTS (
        SELECT 1 FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
         WHERE n.nspname = 'ucpe_lattice'
           AND c.relkind = 'r'
           AND (pg_catalog.has_table_privilege('ucpe_lattice_writer', c.oid, 'SELECT,INSERT,UPDATE,DELETE,TRUNCATE')
                OR pg_catalog.has_table_privilege('ucpe_lattice_writer', c.oid, 'REFERENCES,TRIGGER'))
    ) THEN
        RAISE EXCEPTION '0019 self-check: the writer holds a table privilege' USING ERRCODE = 'UP019';
    END IF;
    IF EXISTS (
        SELECT 1 FROM pg_catalog.pg_auth_members m
          JOIN pg_catalog.pg_roles r ON r.oid = m.roleid
          JOIN pg_catalog.pg_roles u ON u.oid = m.member
         WHERE r.rolname = 'ucpe_lattice_owner' AND u.rolname = current_user AND m.set_option
    ) THEN
        RAISE EXCEPTION '0019 self-check: the temporary SET grant on the owner remains' USING ERRCODE = 'UP019';
    END IF;
END;
$$;
