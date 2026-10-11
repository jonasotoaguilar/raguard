#!/usr/bin/env bash
# Backup the raguard PostgreSQL database with pg_dump (custom format).
#
# Usage:
#   POSTGRES_USER=raguard POSTGRES_PASSWORD=secret POSTGRES_DB=raguard \
#     scripts/backup-postgres.sh [DEST_DIR]
#   scripts/backup-postgres.sh --help
#
# Env (required unless noted):
#   POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB (PGHOST/PGPORT optional,
#   default localhost/5432), DEST_DIR (or first arg, default ./backups).
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
PGHOST="${PGHOST:-localhost}"
PGPORT="${PGPORT:-5432}"
DEST_DIR="${1:-${DEST_DIR:-./backups}}"

command -v pg_dump >/dev/null || {
  echo "error: pg_dump not found in PATH" >&2
  exit 1
}

mkdir -p "$DEST_DIR"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT="$DEST_DIR/raguard-${POSTGRES_DB}-${STAMP}.dump"

export PGPASSWORD="$POSTGRES_PASSWORD"
pg_dump -h "$PGHOST" -p "$PGPORT" -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
  --format=custom --file="$OUT"

if [[ ! -s "$OUT" ]]; then
  echo "error: backup failed: $OUT is missing or empty" >&2
  exit 1
fi
echo "backup OK: $OUT ($(du -h "$OUT" | cut -f1))"
