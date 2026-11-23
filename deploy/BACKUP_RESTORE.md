# PostgreSQL Backup and Recovery

PostgreSQL is the source of truth. Redis persistence is not a backup and must not be treated as one.

## Scope

The scripts back up the database only. Avatar uploads and other media live in the `cinerank-media` volume and need a separate volume backup if they must be recoverable.

## Backup

Run from the repository root while the Compose stack is running:

```bash
BACKUP_DIR=/var/backups/cinerank RETENTION_DAYS=14 ./deploy/backup_postgres.sh
```

The script writes a compressed custom-format dump plus a SHA-256 checksum. The default retention is 14 days. Files are created owner-readable only. The script prints paths, never credentials.

Schedule it outside the container, for example:

```cron
0 2 * * * cd /srv/cinerank && BACKUP_DIR=/var/backups/cinerank ./deploy/backup_postgres.sh >> /var/log/cinerank-backup.log 2>&1
```

## Encryption and off-host storage

The scripts do not encrypt dumps themselves. Store the backup directory on an encrypted volume or encrypt each dump before copying it off host. Keep at least one copy outside the database host. Restrict access to the backup directory and checksum files.

## Restore drill

A backup is not proven until it restores. Restore into a separate database first:

```bash
docker compose exec -T db createdb -U cinerank cinerank_restore
RESTORE_DB=cinerank_restore ./deploy/restore_postgres.sh /var/backups/cinerank/cinerank-20260101T020000Z.dump
```

Then verify:

```bash
docker compose exec -T db psql -U cinerank -d cinerank_restore -c "select count(*) from movies;"
docker compose exec -T db psql -U cinerank -d cinerank_restore -c "select count(*) from users;"
docker compose exec -T db psql -U cinerank -d cinerank_restore -c "select version_num from alembic_version;"
```

Run a smoke test against the restored database before considering the backup valid. Drop the drill database afterward.

Restoring over the live database requires an explicit `RESTORE` confirmation and uses `pg_restore --clean --if-exists`. Stop API and worker traffic first, take a fresh backup, and expect a maintenance window.

## Targets and evidence

Record actual targets for the deployment instead of assuming the defaults:

- Recovery point objective: daily backups give an RPO of up to 24 hours. A shorter RPO requires more frequent dumps or continuous archiving.
- Recovery time objective: measure it during a restore drill with the real dump size and hardware. Do not publish an RTO that has not been measured.

Record the drill date, backup path, checksum result, restore duration, row counts and application smoke-test result in the operational log.
