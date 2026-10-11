#!/usr/bin/env bash
# Restore the raguard PostgreSQL database from a pg_dump custom-format file.
#
# WARNING: this OVERWRITES data in the target database. There is no undo
# beyond taking a fresh backup first (see scripts/backup-postgres.sh).
#
# Usage:
#   CONFIRM_RESTORE=yes POSTGRES_USER=raguard POSTGRES_PASSWORD=secret \
#     POSTGRES_DB=raguard scripts/restore-postgres.sh <DUMP_FILE>
#   scripts/restore-postgres.sh --help
#
# Env (required unless noted):
#   CONFIRM_RESTORE=yes (explicit confirmation, no default),
#   POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB (PGHOST/PGPORT optional,
#   default localhost/5432).
set -euo pipefail

usage() {
  sed -n '2,/^set /p' "$0" | sed 's/^# \?//'
}

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  usage
  exit 0
fi

: "${POSTGRES_USER:?POSTGRES_USER is required}"
: "${POSTGRES_PASSWORD:?POSTGRES_PASSWORD is required}"
: "${POSTGRES_DB:?POSTGRES_DB is required}"
if [[ "${CONFIRM_RESTORE:-}" != "yes" ]]; then
  echo "error: refusing to restore without explicit confirmation." >&2
  echo "Set CONFIRM_RESTORE=yes. WARNING: this OVERWRITES all data in database '$POSTGRES_DB'." >&2
  exit 1
fi
DUMP_FILE="${1:?usage: scripts/restore-postgres.sh <DUMP_FILE>}"
if [[ ! -s "$DUMP_FILE" ]]; then
  echo "error: dump file '$DUMP_FILE' is missing or empty" >&2
  exit 1
fi
PGHOST="${PGHOST:-localhost}"
PGPORT="${PGPORT:-5432}"

command -v pg_restore >/dev/null || {
  echo "error: pg_restore not found in PATH" >&2
  exit 1
}

echo "WARNING: restoring '$DUMP_FILE' will OVERWRITE all data in database '$POSTGRES_DB' on $PGHOST:$PGPORT." >&2
export PGPASSWORD="$POSTGRES_PASSWORD"
pg_restore --clean --if-exists -h "$PGHOST" -p "$PGPORT" -U "$POSTGRES_USER" \
  -d "$POSTGRES_DB" "$DUMP_FILE"
echo "restore OK from $DUMP_FILE"
