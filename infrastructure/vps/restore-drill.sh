#!/usr/bin/env bash
#
# Restore drill: prove the latest backup can be restored, without touching the live database.
# Takes a fresh backup, restores it into a scratch database, compares row counts of key tables
# with the live database, reports the timings (RPO/RTO evidence) and drops the scratch copy.
#
#   bash /srv/mhrs/infrastructure/vps/restore-drill.sh

set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=site.conf
source "$HERE/site.conf"
[[ $EUID -eq 0 ]] || { echo "Run as root." >&2; exit 1; }

SCRATCH="mhrs_restore_drill"
TABLES=(accounts_user organisations_organisation jobs_job applications_application
        taxonomy_skill notifications_notificationtemplate audit_auditevent django_migrations)
count() { sudo -u postgres psql -tAq -d "$1" -c "SELECT count(*) FROM $2" 2>/dev/null || echo "missing"; }

t0=$(date +%s)
bash "$HERE/backup.sh" >/dev/null
DUMP="$(ls -1t "$BACKUP_DIR"/mhrs-db-*.dump | head -1)"
t1=$(date +%s)

sudo -u postgres dropdb --if-exists "$SCRATCH"
sudo -u postgres createdb "$SCRATCH"
sudo -u postgres psql -q -d "$SCRATCH" -c "CREATE EXTENSION IF NOT EXISTS vector; CREATE EXTENSION IF NOT EXISTS pg_trgm;"
sudo -u postgres pg_restore --no-owner --exit-on-error -d "$SCRATCH" < "$DUMP" 2>/dev/null \
  || sudo -u postgres pg_restore --no-owner -d "$SCRATCH" < "$DUMP"
t2=$(date +%s)

printf '%-40s %10s %10s\n' "table" "live" "restored"
mismatch=0
for t in "${TABLES[@]}"; do
    live="$(count "$DB_NAME" "$t")"; restored="$(count "$SCRATCH" "$t")"
    flag=""; [[ "$live" == "$restored" ]] || { flag="  <-- differs"; mismatch=1; }
    printf '%-40s %10s %10s%s\n' "$t" "$live" "$restored" "$flag"
done
sudo -u postgres dropdb "$SCRATCH"

echo
echo "Backup file      $(basename "$DUMP") ($(du -h "$DUMP" | cut -f1))"
echo "Backup took      $((t1 - t0)) s   (RPO: nightly 01:45 + before every deploy)"
echo "Restore took     $((t2 - t1)) s   (database only; RTO incl. service restart is a few minutes)"
if (( mismatch )); then
    echo "RESULT: FAILED - row counts differ (writes during the drill can cause small differences; re-run at a quiet time)."
    exit 1
fi
echo "RESULT: OK - the backup restores and matches the live database."
