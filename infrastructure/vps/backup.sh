#!/usr/bin/env bash
#
# Back up the MHRS database and file storage to /srv/mhrs/backups (owner-only), keeping
# MHRS_BACKUP_RETENTION_DAYS (default 14) days. Run nightly by mhrs-backup.timer and by deploy.sh.
#
#   bash /srv/mhrs/infrastructure/vps/backup.sh

set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=site.conf
source "$HERE/site.conf"
[[ $EUID -eq 0 ]] || { echo "Run as root." >&2; exit 1; }

RETENTION_DAYS="${MHRS_BACKUP_RETENTION_DAYS:-14}"
STAMP="$(date +%Y%m%d-%H%M%S)"
mkdir -p "$BACKUP_DIR" && chmod 700 "$BACKUP_DIR"
umask 077

DB_FILE="$BACKUP_DIR/mhrs-db-$STAMP.dump"
# shellcheck disable=SC2024  # root (not postgres) writes the owner-only backup file
sudo -u postgres pg_dump --format=custom --no-owner "$DB_NAME" > "$DB_FILE"
[[ -s "$DB_FILE" ]] || { echo "Database backup is empty." >&2; exit 1; }
# verify the archive is readable before trusting it
pg_restore --list "$DB_FILE" >/dev/null

# File storage (CVs, documents): SeaweedFS data directory. Copied while running; the volume files
# are append-only, so a copy taken now restores to a consistent earlier point.
FILES_FILE="$BACKUP_DIR/mhrs-files-$STAMP.tar.gz"
tar -czf "$FILES_FILE" -C "$APP_DIR" s3-data run/s3.json 2>/dev/null || {
    rc=$?; (( rc == 1 )) || { echo "File storage backup failed ($rc)." >&2; exit 1; }
}
# keys needed to read encrypted fields; without them the database backup is unreadable
cp "$BACKEND/.env" "$BACKUP_DIR/mhrs-env-$STAMP"

find "$BACKUP_DIR" -maxdepth 1 -type f -name 'mhrs-*' -mtime +"$RETENTION_DAYS" -delete
echo "Backup written: $(basename "$DB_FILE") ($(du -h "$DB_FILE" | cut -f1)), $(basename "$FILES_FILE") ($(du -h "$FILES_FILE" | cut -f1))"
