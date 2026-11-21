#!/usr/bin/env bash
#
# One-time setup of encrypted off-server backups to Google Drive for MHRS (owner step).
# Run from YOUR computer, so the Google sign-in opens in your browser through an SSH tunnel:
#
#   ssh -t -L 53682:127.0.0.1:53682 agribizframework "bash /srv/mhrs/infrastructure/vps/configure-offsite-backup.sh"
#
#   1. Signs in to Google Drive with the narrowest scope rclone offers (drive.file: the server sees
#      only files it created). Open the printed link, choose the Google account, allow.
#   2. Creates an encryption layer (rclone crypt) over the Drive folder "MHRS-backups" with a random
#      password and salt, and writes a plain copy of both to /etc/mhrs/offsite-backup-key.txt so you
#      can store them OFF the server (password manager). Without them the Drive copies are useless.
#   3. Takes a fresh backup, uploads it, downloads it back, decrypts it and checks it restores.
#   4. Makes every successful nightly backup upload itself afterwards.
#
# Safe to re-run; pass --reset to start the Google sign-in again.

set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=site.conf
source "$HERE/site.conf"

CONF_DIR="/etc/mhrs"
RCLONE_CONFIG="$CONF_DIR/rclone.conf"
KEY_FILE="$CONF_DIR/offsite-backup-key.txt"
DRIVE_FOLDER="MHRS-backups"
log() { printf '\n\033[1;34m==>\033[0m %s\n' "$1"; }
die() { printf '\033[1;31m[error]\033[0m %s\n' "$1" >&2; exit 1; }

[[ $EUID -eq 0 ]] || die "Run this as root."
if [[ "${1:-}" == "--reset" && -f "$RCLONE_CONFIG" ]]; then
    mv "$RCLONE_CONFIG" "$RCLONE_CONFIG.old-$(date +%Y%m%d%H%M%S)"
fi
command -v rclone >/dev/null || { log "Installing rclone"; dnf install -y -q rclone >/dev/null; }
rclone version | head -1
install -d -m 700 "$CONF_DIR"
rc() { rclone --config "$RCLONE_CONFIG" "$@"; }

if ! rc listremotes 2>/dev/null | grep -q '^gdrive:$'; then
    log "Google Drive sign-in"
    cat <<'EOF'
    rclone starts a sign-in page on port 53682 and prints a link. Open it in the browser on YOUR
    computer (the ssh -L tunnel carries it here), choose the Google account that should hold the
    backups and allow access. Google may say rclone is not verified by Google: that is the standard
    open-source rclone client; continue.
EOF
    rc config create gdrive drive scope=drive.file config_is_local=true config_team_drive=false
    rc listremotes | grep -q '^gdrive:$' || die "Google Drive sign-in did not complete."
fi

if ! rc listremotes | grep -q '^mhrs-offsite:$'; then
    log "Creating the encryption layer"
    PASSWORD="$(openssl rand -base64 48 | tr -d '\n')"
    SALT="$(openssl rand -base64 48 | tr -d '\n')"
    rc config create mhrs-offsite crypt remote="gdrive:$DRIVE_FOLDER" \
        filename_encryption=standard directory_name_encryption=true \
        password="$PASSWORD" password2="$SALT" --obscure >/dev/null
    umask 077
    printf 'MHRS off-server backup key (rclone crypt)\ncreated %s\nremote gdrive:%s\npassword  %s\npassword2 %s\n' \
        "$(date -u +%FT%TZ)" "$DRIVE_FOLDER" "$PASSWORD" "$SALT" > "$KEY_FILE"
    unset PASSWORD SALT
fi
chmod 600 "$RCLONE_CONFIG" "$KEY_FILE" 2>/dev/null || true

log "Taking a fresh backup and uploading it"
bash "$HERE/backup.sh" >/dev/null
bash "$HERE/offsite-backup.sh"

log "Restore test: download, decrypt, verify"
DB_DUMP="$(find "$BACKUP_DIR" -maxdepth 1 -name 'mhrs-db-*.dump' -printf '%T@ %p\n' | sort -nr | head -1 | cut -d' ' -f2-)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
rc copyto "mhrs-offsite:$(basename "$DB_DUMP")" "$TMP/restore.dump"
cmp -s "$DB_DUMP" "$TMP/restore.dump" || die "the downloaded copy differs from the local backup"
TABLES="$(pg_restore --list "$TMP/restore.dump" | grep -c ' TABLE ')"
printf '    the Drive copy is identical and readable (%s tables)\n' "$TABLES"

log "Running it after every nightly backup"
install -d /etc/systemd/system/mhrs-backup.service.d
cat > /etc/systemd/system/mhrs-backup.service.d/offsite.conf <<'EOF'
[Unit]
OnSuccess=mhrs-offsite-backup.service
EOF
install -m 644 "$APP_DIR/infrastructure/vps/systemd/mhrs-offsite-backup.service" /etc/systemd/system/
systemctl daemon-reload

log "Google Drive only holds ciphertext:"
rc lsf "gdrive:$DRIVE_FOLDER" | head -3 | sed 's/^/    /'
cat <<EOF

$(printf '\033[1;32mOff-server backups are on.\033[0m')

NOW store the encryption key somewhere other than this server (a password manager), then delete
the plain copy:
    cat $KEY_FILE
    rm $KEY_FILE
Without that key, the Drive copies cannot be read.
EOF
