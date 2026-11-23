#!/usr/bin/env bash
# Restore a CineRank custom-format PostgreSQL backup.
# Run from the repository root. Prefer restoring into a separate database first.
set -euo pipefail

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
DB_USER="${POSTGRES_USER:-cinerank}"
TARGET_DB="${RESTORE_DB:-${POSTGRES_DB:-cinerank}}"

if [ "$#" -ne 1 ]; then
  echo "Usage: RESTORE_DB=<database> $0 <backup.dump>" >&2
  exit 2
fi

dump="$1"
if [ ! -f "$dump" ]; then
  echo "Backup not found: $dump" >&2
  exit 1
fi
if [ ! -f "$dump.sha256" ]; then
  echo "Missing checksum file: $dump.sha256" >&2
  exit 1
fi

sha256sum -c "$dump.sha256"

echo "This will restore into database '$TARGET_DB'."
echo "Existing objects with matching names may be dropped by pg_restore --clean."
read -r -p "Type RESTORE to continue: " confirmation
if [ "$confirmation" != "RESTORE" ]; then
  echo "aborted"
  exit 1
fi

docker compose -f "$COMPOSE_FILE" exec -T db \
  pg_restore -U "$DB_USER" -d "$TARGET_DB" \
  --clean --if-exists --no-owner --no-privileges < "$dump"

echo "restore_complete database=$TARGET_DB"
