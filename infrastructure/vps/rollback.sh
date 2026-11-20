#!/usr/bin/env bash
#
# Roll MHRS back.
#
#   bash rollback.sh                       switch the frontend to the previous release
#   bash rollback.sh --release <archive>   also unpack an earlier release archive (git archive of a
#                                          previous commit, uploaded to /tmp) and redeploy it without
#                                          migrations; schema changes are expand-only, so the older
#                                          code runs against the newer schema
#   bash rollback.sh --restore-db <dump>   restore a database backup (destructive; asks to confirm)

set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=site.conf
source "$HERE/site.conf"
[[ $EUID -eq 0 ]] || { echo "Run as root." >&2; exit 1; }

case "${1:-}" in
  "")
    prev="$(cat "$RUN_DIR/previous-frontend" 2>/dev/null || true)"
    [[ -n "$prev" && -d "$prev" ]] || { echo "No previous frontend release recorded." >&2; exit 1; }
    ln -sfn "$prev" "$FRONTEND/current"
    systemctl restart mhrs-frontend
    echo "Frontend switched back to $(basename "$prev")."
    ;;
  --release)
    archive="${2:?give the release archive path}"
    [[ -f "$archive" ]] || { echo "$archive not found." >&2; exit 1; }
    tar -xzf "$archive" -C "$APP_DIR"
    SKIP_BACKUP=0 bash "$APP_DIR/infrastructure/vps/deploy.sh"
    ;;
  --restore-db)
    dump="${2:?give the backup file}"
    [[ -f "$dump" ]] || { echo "$dump not found." >&2; exit 1; }
    echo "This replaces the live database '$DB_NAME' with $(basename "$dump")."
    echo "Every change since that backup is lost. Type the database name to continue:"
    read -r answer
    [[ "$answer" == "$DB_NAME" ]] || { echo "Cancelled."; exit 1; }
    bash "$HERE/backup.sh"
    systemctl stop mhrs-beat mhrs-worker mhrs-backend
    sudo -u postgres pg_restore --clean --if-exists --no-owner --role="$DB_USER" -d "$DB_NAME" < "$dump"
    systemctl start mhrs-backend mhrs-worker mhrs-beat
    echo "Database restored from $(basename "$dump")."
    ;;
  *) echo "Unknown option $1" >&2; exit 2 ;;
esac
