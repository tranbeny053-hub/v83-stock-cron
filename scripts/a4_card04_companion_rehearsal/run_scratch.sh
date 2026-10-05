#!/usr/bin/env bash
# One scratch PostgreSQL cluster for the ucpe.a4_card04_companion.v1 rehearsal, built from every
# applied migration. A local run and the CI workflow run this same script:
#   run_scratch.sh <postgres bin dir> <fresh work dir> <report path>
# It starts a private server listening on a socket only (no TCP), applies the Supabase-like role
# fixtures, every migration as a non-superuser owner and the probe roles, runs rehearse.py with
# ${PYTHON:-python}, and stops the server. It never reads a database URL from the environment and
# never contacts a remote.
set -euo pipefail
BIN="$1"
WORK="$2"
REPORT="$3"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
OWNER="$(id -un)"
DB=a4_companion_rehearsal
if [ -e "$WORK" ]; then
  echo "REFUSED: $WORK exists; give a fresh work directory" >&2
  exit 2
fi
mkdir -p "$WORK"
SOCKET="$(mktemp -d /tmp/a4c.XXXXXX)"  # a socket path must stay under about 100 bytes
cleanup() {
  "$BIN/pg_ctl" -D "$WORK/data" -m fast -w stop >/dev/null 2>&1 || true
  rm -rf "$SOCKET"
}
trap cleanup EXIT
"$BIN/initdb" -D "$WORK/data" -U postgres --auth=trust --encoding=UTF8 --locale=C \
  >"$WORK/initdb.log"
"$BIN/pg_ctl" -D "$WORK/data" -l "$WORK/server.log" -w start \
  -o "-c listen_addresses='' -c unix_socket_directories='$SOCKET' -c fsync=off" >/dev/null
as_super() { "$BIN/psql" -X -q -v ON_ERROR_STOP=1 -h "$SOCKET" -U postgres "$@"; }
as_owner() { "$BIN/psql" -X -q -v ON_ERROR_STOP=1 -h "$SOCKET" -U "$OWNER" "$@"; }
as_super -d postgres -c "CREATE ROLE \"$OWNER\" LOGIN"
as_super -d postgres -f "$ROOT/scripts/migration_0013_rehearsal/00_supabase_like_roles.sql"
as_super -d postgres -v owner="$OWNER" \
  -f "$ROOT/scripts/migration_0016_rehearsal/00_supabase_like_authenticator.sql"
as_super -d postgres -c "CREATE DATABASE $DB OWNER \"$OWNER\""
as_super -d "$DB" -v owner="$OWNER" \
  -f "$ROOT/scripts/migration_0013_rehearsal/01_supabase_like_grants.sql"
as_super -d "$DB" -v owner="$OWNER" \
  -f "$ROOT/scripts/migration_0015_rehearsal/00_supabase_like_function_grants.sql"
for migration in "$ROOT"/migrations/[0-9][0-9][0-9][0-9]_*.sql; do
  as_owner -d "$DB" -f "$migration"
done
as_super -d "$DB" -v owner="$OWNER" \
  -f "$ROOT/scripts/a4_card04_companion_rehearsal/00_probe_roles.sql"
A4C_REHEARSAL_URL="postgresql:///$DB?host=$SOCKET" "${PYTHON:-python}" \
  "$ROOT/scripts/a4_card04_companion_rehearsal/rehearse.py" --report="$REPORT"
