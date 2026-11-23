#!/usr/bin/env bash
# Create a compressed, checksummed PostgreSQL backup from the Compose database.
# Run from the repository root. Requires the Compose stack to be running.
set -euo pipefail

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
BACKUP_DIR="${BACKUP_DIR:-./backups}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"
DB_USER="${POSTGRES_USER:-cinerank}"
DB_NAME="${POSTGRES_DB:-cinerank}"

if [ ! -f "$COMPOSE_FILE" ]; then
  echo "Compose file not found: $COMPOSE_FILE" >&2
  exit 1
fi

command -v docker >/dev/null 2>&1 || {
  echo "docker is required" >&2
  exit 1
}

umask 077
mkdir -p "$BACKUP_DIR"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
dump="$BACKUP_DIR/cinerank-$stamp.dump"

docker compose -f "$COMPOSE_FILE" exec -T db \
  pg_dump -U "$DB_USER" -d "$DB_NAME" \
  --format=custom --no-owner --no-privileges > "$dump"

sha256sum "$dump" > "$dump.sha256"

# Never print credentials. The dump and checksum stay owner-readable only.
echo "backup=$dump"
echo "checksum=$dump.sha256"

find "$BACKUP_DIR" -type f -name 'cinerank-*.dump*' -mtime "+$RETENTION_DAYS" -delete
echo "retention_days=$RETENTION_DAYS"
