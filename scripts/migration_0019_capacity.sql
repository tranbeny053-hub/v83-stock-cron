-- NG4 pilot capacity: AUTHORED, NOT APPLIED. Run only by scripts/apply_migration_0019.py, in the same transaction
-- as migrations/authored/0019_lattice_evidence.sql and right after it; never on its own and never twice.
--
-- The owner's values (2026-11-06, NG4-PILOT INPUTS): at most 1,200 rows plus missed instants, a warning at 600. The
-- 14-day lattice of SOL/USDT on 15m/1H/4H/1D has 592 or 593 slots (quant_ng.lattice.planned_slots), so the warning
-- fires only above plan and the stop at about twice the plan. The capacity row stops collection; it never deletes.
--
-- 0019 revoked the applying role's hand-off on ucpe_lattice_owner, so writing the row takes the same temporary
-- hand-off again: SET on the owner, the row inserted by the owner itself (its INSERT policy), the hand-off revoked.
-- Then 0019's own self-check runs again unchanged (a test keeps the copy below byte-identical), and the row is read
-- back. Any failure raises and rolls back the whole transaction, 0019 included.

GRANT ucpe_lattice_owner TO CURRENT_USER WITH INHERIT FALSE, SET TRUE;
SET ROLE ucpe_lattice_owner;
INSERT INTO ucpe_lattice.lattice_capacity (max_rows, warn_rows, note)
VALUES (1200, 600, 'NG4 TEST_ONLY pilot, SOL/USDT Binance 15m/1H/4H/1D, 14 days; owner 2026-11-06');
DO $$
BEGIN
    IF (SELECT count(*) FROM ucpe_lattice.lattice_capacity WHERE max_rows = 1200 AND warn_rows = 600) <> 1
       OR (SELECT count(*) FROM ucpe_lattice.lattice_capacity) <> 1 THEN
        RAISE EXCEPTION '0019 capacity: the capacity row is not exactly 1200/600' USING ERRCODE = 'UP019';
    END IF;
END;
$$;
RESET ROLE;
REVOKE ucpe_lattice_owner FROM CURRENT_USER;

-- Self-check: no role but the owner, the writer and superusers holds any privilege on the schema or its objects, the
-- writer holds no table privilege, and the hand-off grant is gone.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
          FROM (
                -- A NULL ACL means the default (for functions, EXECUTE to PUBLIC), so it is expanded first.
                SELECT coalesce(n.nspacl, pg_catalog.acldefault('n', n.nspowner)) AS acl
                  FROM pg_catalog.pg_namespace n WHERE n.nspname = 'ucpe_lattice'
                UNION ALL
                SELECT coalesce(c.relacl, pg_catalog.acldefault(
                           (CASE WHEN c.relkind = 'S' THEN 's' ELSE 'r' END)::"char", c.relowner))
                  FROM pg_catalog.pg_class c
                  JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
                 WHERE n.nspname = 'ucpe_lattice' AND c.relkind IN ('r', 'S', 'v', 'm', 'p', 'f')
                UNION ALL
                SELECT coalesce(p.proacl, pg_catalog.acldefault('f', p.proowner))
                  FROM pg_catalog.pg_proc p
                  JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace WHERE n.nspname = 'ucpe_lattice'
               ) o
          CROSS JOIN LATERAL pg_catalog.aclexplode(o.acl) a
          LEFT JOIN pg_catalog.pg_roles g ON g.oid = a.grantee
         WHERE (a.grantee = 0 OR (g.rolname NOT IN ('ucpe_lattice_owner', 'ucpe_lattice_writer') AND NOT g.rolsuper))
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
