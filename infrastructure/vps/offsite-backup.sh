#!/usr/bin/env bash
#
# Copy the newest MHRS backup set (database dump, file storage, keys) to Google Drive, encrypted
# before it leaves the server. Runs automatically after every successful mhrs-backup.service once
# configure-offsite-backup.sh has been run; also fine to run by hand:
#
#   bash /srv/mhrs/infrastructure/vps/offsite-backup.sh
#
# Same approach as the sibling AMA and DRP apps on this server (rclone crypt over a drive.file
# scope), with MHRS's own folder, key and configuration. Google Drive holds only ciphertext with
# scrambled names; without the key kept off this server, the Drive copies cannot be decrypted.

set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=site.conf
source "$HERE/site.conf"

RCLONE_CONFIG="${MHRS_RCLONE_CONFIG:-/etc/mhrs/rclone.conf}"
REMOTE="mhrs-offsite:"
REMOTE_RETENTION_DAYS="${MHRS_OFFSITE_RETENTION_DAYS:-90}"
STAMP_FILE="$RUN_DIR/offsite-last-success"

log() { printf '\n\033[1;34m==>\033[0m %s\n' "$1"; }
die() { printf '\033[1;31m[error]\033[0m %s\n' "$1" >&2; exit 1; }

if [[ ! -f "$RCLONE_CONFIG" ]]; then
    # not configured yet is a state, not a failure: the local backup already succeeded
    echo "Off-server backup not configured (no $RCLONE_CONFIG). Run configure-offsite-backup.sh."
    exit 0
fi
command -v rclone >/dev/null || die "rclone is not installed."
rc() { rclone --config "$RCLONE_CONFIG" "$@"; }

newest() { find "$BACKUP_DIR" -maxdepth 1 -name "$1" -printf '%T@ %p\n' | sort -nr | head -1 | cut -d' ' -f2-; }
DB_DUMP="$(newest 'mhrs-db-*.dump')"
FILES_TAR="$(newest 'mhrs-files-*.tar.gz')"
ENV_COPY="$(newest 'mhrs-env-*')"
[[ -n "$DB_DUMP" && -n "$FILES_TAR" && -n "$ENV_COPY" ]] || die "No complete backup set in $BACKUP_DIR."

log "Uploading to Google Drive (encrypted)"
for f in "$DB_DUMP" "$FILES_TAR" "$ENV_COPY"; do
    rc copyto "$f" "$REMOTE$(basename "$f")" --retries 5 --low-level-retries 10 || die "upload failed: $f"
    local_size="$(stat -c %s "$f")"
    remote_size="$(rc size --json "$REMOTE$(basename "$f")" | python3 -c 'import json,sys; print(json.load(sys.stdin)["bytes"])')"
    [[ "$local_size" == "$remote_size" ]] || die "size mismatch for $(basename "$f"): local $local_size, Drive $remote_size"
    printf '    %s (%s bytes) verified\n' "$(basename "$f")" "$local_size"
done

log "Removing Drive copies older than $REMOTE_RETENTION_DAYS days"
rc delete "$REMOTE" --min-age "${REMOTE_RETENTION_DAYS}d" --include 'mhrs-*' 2>&1 | grep -i deleted || echo "    nothing to remove"

date +%s > "$STAMP_FILE"
chown "$APP_USER:$APP_USER" "$STAMP_FILE"
log "Off-server copies (newest)"
rc lsl "$REMOTE" | sort -k2,3 | tail -3
