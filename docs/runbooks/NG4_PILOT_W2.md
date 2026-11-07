# NG4 pilot W2 owner runbook

After the single 0019 + capacity + 0020 apply T4 succeeds, the owner issues the login credential. This remains an owner action; authoring the helper issues nothing.

1. On the owner's Mac, run `python -m scripts.lattice_space_credential generate`. The helper writes owner-only files under `~/ucpe-keys` and prints no secret.
2. Run `python -m scripts.lattice_space_credential copy-sql`; paste the clipboard into the SQL Editor as the applying role. This enables `ucpe_lattice_space` login.
3. Run `python -m scripts.lattice_space_credential copy-url`; paste into the Space secret `UCPE_LATTICE_DB_URL`.
4. VALID UNTIL is an owner option at credential time; the start instant is unruled.
5. Read the T4 post-checks, including the Space's next `evidence_reader_identity` event DESIGNED for `ucpe_space_db` and the preflight's `ucpe_lattice_space_exists`.

## Disable after the end

After the runner's `lattice_pilot_state` ENDED or CAPACITY_STOP event, execute as an authorized database role:

```sql
ALTER ROLE ucpe_lattice_space NOLOGIN PASSWORD NULL;
```

Delete the Space secret. Terminate the role's backends. If the applier lacks `pg_signal_backend` (see preflight `applier_signal_backend`), stop the Space, delete the secret and wait for the pooler to reap its sessions. Verify zero sessions and re-read role configuration:

```sql
SELECT count(*) FROM pg_stat_activity WHERE usename = 'ucpe_lattice_space';
SELECT rolname, rolconfig FROM pg_roles WHERE rolname = 'ucpe_lattice_space';
```

## Rollback (separate T4)

First perform the same disable, secret deletion, backend termination and verification. Then execute:

```sql
REVOKE ucpe_lattice_writer FROM ucpe_lattice_space;
DROP ROLE ucpe_lattice_space;
```

Role settings are session defaults, not limits; a session can change them. `CONNECTION LIMIT 3` is a bound. Pooler behaviour cannot be rehearsed. There is no production precedent for these role features; a platform refusal rolls the T4 back atomically, and the T4 is consumed.

## Credential inventory
`UCPE_LATTICE_DB_URL` (a Space secret) is created only by the owner's credential step after the 0019 + 0020 apply, and
deleted at the disable step. `docs/automation/CREDENTIAL_ROTATION.md` is not edited in this change: it feeds the UOR
handoff manifest, so its entry is added with the switch-ON change, when the secret first exists.
