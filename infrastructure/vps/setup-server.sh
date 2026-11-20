#!/usr/bin/env bash
#
# One-time preparation of the shared VPS for MHRS (hr.agribizframework.com).
#
#   sudo bash /srv/mhrs/infrastructure/vps/setup-server.sh
#
# Assumes the sibling apps' setup already installed nginx, PostgreSQL 16, Redis, Python 3.12,
# certbot, firewalld and the swap file. Adds only what MHRS needs, never touching the others:
#   - packages: pgvector (PostgreSQL extension), clamd, tesseract, poppler-utils
#   - its own Node 24 under /srv/mhrs/tools (the system Node 20 stays for the other apps)
#   - uv and the SeaweedFS binary under /srv/mhrs/tools
#   - the mhrs system user, directories, database role (no superuser, no BYPASSRLS) and database
#   - .env files with generated secrets (never printed), S3 credentials and clamd config
#
# Idempotent: safe to re-run. Existing .env files and credentials are never overwritten.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=site.conf
source "$HERE/site.conf"

log()  { printf '\n\033[1;34m==>\033[0m %s\n' "$1"; }
warn() { printf '\033[1;33m[warn]\033[0m %s\n' "$1"; }
die()  { printf '\033[1;31m[error]\033[0m %s\n' "$1" >&2; exit 1; }

[[ $EUID -eq 0 ]] || die "Run this as root."
[[ -d "$BACKEND" && -d "$FRONTEND" ]] || die "Unpack the release into $APP_DIR first (see README.md)."

# ------------------------------------------------------------ prerequisites
log "Checking what the sibling apps' setup already installed"
for tool in nginx psql "$PYTHON" openssl curl tar redis-cli certbot; do
    command -v "$tool" >/dev/null 2>&1 || die "'$tool' is not installed; this script expects the shared agribizframework server."
done
systemctl is-active --quiet postgresql || die "PostgreSQL is not running."
systemctl is-active --quiet redis || die "Redis is not running."

log "Checking that MHRS's ports are free"
for pair in "$BACKEND_PORT:mhrs-backend" "$FRONTEND_PORT:mhrs-frontend" "$S3_PORT:mhrs-s3" "$CLAMD_PORT:mhrs-clamd" \
            "9533:mhrs-s3" "8580:mhrs-s3" "8588:mhrs-s3"; do
    port="${pair%%:*}"; service="${pair##*:}"
    if [[ -n "$(ss -ltnH "sport = :$port" 2>/dev/null)" ]] && ! systemctl is-active --quiet "$service"; then
        die "Port $port is used by another application. Choose other ports in site.conf and the companion files."
    fi
done

# ----------------------------------------------------------------- packages
log "Installing pgvector, clamd, tesseract and poppler (additive; nothing else changes)"
dnf install -y -q pgvector clamd tesseract tesseract-langpack-eng poppler-utils file-libs >/dev/null
systemctl list-unit-files clamav-freshclam.service >/dev/null 2>&1 && systemctl enable --now clamav-freshclam >/dev/null 2>&1 || true

# --------------------------------------------------------------------- user
log "Creating the $APP_USER system user (no login shell, no password)"
id "$APP_USER" >/dev/null 2>&1 || useradd --system --create-home --home-dir "/home/$APP_USER" --shell /usr/sbin/nologin "$APP_USER"
mkdir -p "/home/$APP_USER" && chown "$APP_USER:$APP_USER" "/home/$APP_USER" && chmod 700 "/home/$APP_USER"

log "Creating $APP_DIR directories"
mkdir -p "$FRONTEND/releases" "$APP_DIR/logs" "$BACKUP_DIR" "$S3_DATA_DIR" "$HF_HOME_DIR" "$TOOLS_DIR" "$RUN_DIR" "$BACKEND/staticfiles"
chown -R "$APP_USER:$APP_USER" "$APP_DIR"
chmod 700 "$BACKUP_DIR" "$S3_DATA_DIR" "$RUN_DIR"

# -------------------------------------------------------------------- tools
ARCH="$(uname -m)"; [[ "$ARCH" == "x86_64" ]] || die "Only x86_64 is supported (found $ARCH)."

if [[ ! -x "$NODE_DIR/bin/node" ]] || [[ "$("$NODE_DIR/bin/node" --version)" != "v$NODE_VERSION" ]]; then
    log "Installing Node $NODE_VERSION privately for MHRS (system Node stays as it is)"
    tmp="$(mktemp -d)"
    base="https://nodejs.org/dist/v$NODE_VERSION"
    curl -fsSL "$base/node-v$NODE_VERSION-linux-x64.tar.xz" -o "$tmp/node.tar.xz"
    curl -fsSL "$base/SHASUMS256.txt" -o "$tmp/SHASUMS256.txt"
    ( cd "$tmp" && grep " node-v$NODE_VERSION-linux-x64.tar.xz\$" SHASUMS256.txt | sed "s| node-v.*| node.tar.xz|" | sha256sum -c - ) \
        || die "Node download failed its checksum."
    rm -rf "$NODE_DIR" && mkdir -p "$NODE_DIR"
    tar -xJf "$tmp/node.tar.xz" -C "$NODE_DIR" --strip-components=1
    rm -rf "$tmp"
fi
echo "    node $("$NODE_DIR/bin/node" --version)"

if [[ ! -x "$TOOLS_DIR/uv/bin/uv" ]]; then
    log "Installing uv $UV_VERSION (locked Python dependency installs)"
    "$PYTHON" -m venv "$TOOLS_DIR/uv"
    "$TOOLS_DIR/uv/bin/pip" install --quiet "uv==$UV_VERSION"
fi

if [[ ! -x "$TOOLS_DIR/weed" ]]; then
    log "Installing SeaweedFS $SEAWEEDFS_VERSION (private S3 storage on loopback)"
    tmp="$(mktemp -d)"
    base="https://github.com/seaweedfs/seaweedfs/releases/download/$SEAWEEDFS_VERSION"
    curl -fsSL "$base/linux_amd64.tar.gz" -o "$tmp/weed.tar.gz"
    if curl -fsSL "$base/linux_amd64.tar.gz.md5" -o "$tmp/weed.md5" 2>/dev/null; then
        expected="$(awk '{print $1}' "$tmp/weed.md5")"
        actual="$(md5sum "$tmp/weed.tar.gz" | awk '{print $1}')"
        [[ "$expected" == "$actual" ]] || die "SeaweedFS download failed its checksum."
    else
        warn "No published checksum for SeaweedFS $SEAWEEDFS_VERSION; continuing with the HTTPS download."
    fi
    tar -xzf "$tmp/weed.tar.gz" -C "$TOOLS_DIR" weed
    rm -rf "$tmp"
fi
chown -R "$APP_USER:$APP_USER" "$TOOLS_DIR"

# ----------------------------------------------------------------- database
log "Creating the $DB_USER role (NOSUPERUSER NOBYPASSRLS, so row-level security applies) and $DB_NAME"
DB_PASSWORD=""
if sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='$DB_USER'" | grep -q 1; then
    if [[ -f "$BACKEND/.env" ]]; then
        echo "    Role and backend/.env both exist -- leaving the password unchanged."
    else
        warn "Role '$DB_USER' exists but backend/.env does not -- issuing a new password."
        DB_PASSWORD="$(openssl rand -hex 24)"
        sudo -u postgres psql -q -c "ALTER ROLE $DB_USER WITH LOGIN NOSUPERUSER NOBYPASSRLS PASSWORD '$DB_PASSWORD';"
    fi
else
    [[ ! -f "$BACKEND/.env" ]] || die "backend/.env exists but role '$DB_USER' does not. Remove the stale .env first."
    DB_PASSWORD="$(openssl rand -hex 24)"
    sudo -u postgres psql -q -c "CREATE ROLE $DB_USER WITH LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEROLE PASSWORD '$DB_PASSWORD';"
fi
if ! sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='$DB_NAME'" | grep -q 1; then
    sudo -u postgres createdb -O "$DB_USER" "$DB_NAME"
fi
# Extensions need a superuser; created here so the app role never needs that privilege.
sudo -u postgres psql -q -d "$DB_NAME" -c "CREATE EXTENSION IF NOT EXISTS vector; CREATE EXTENSION IF NOT EXISTS pg_trgm;"
echo "    database $DB_NAME ready (vector, pg_trgm)"

# Local connections from 127.0.0.1 must accept password auth for the app role.
if ! PGPASSWORD="${DB_PASSWORD:-x}" psql -h 127.0.0.1 -U "$DB_USER" -d "$DB_NAME" -tAc "select 1" >/dev/null 2>&1 && [[ -n "$DB_PASSWORD" ]]; then
    warn "Password login for $DB_USER on 127.0.0.1 failed; check pg_hba.conf allows scram/md5 on host 127.0.0.1/32."
fi

# ----------------------------------------------------------------- secrets
S3_CONF="$RUN_DIR/s3.json"
if [[ ! -f "$BACKEND/.env" ]]; then
    log "Writing $BACKEND/.env with generated secrets"
    SECRET_KEY="$(openssl rand -hex 40)"
    FERNET_KEY="$("$PYTHON" -c 'import base64,os;print(base64.urlsafe_b64encode(os.urandom(32)).decode())')"
    S3_ACCESS_KEY="mhrs$(openssl rand -hex 8)"
    S3_SECRET_KEY="$(openssl rand -hex 24)"
    sed -e "s|__SITE_DOMAIN__|$SITE_DOMAIN|g" \
        -e "s|__SECRET_KEY__|$SECRET_KEY|" -e "s|__FERNET_KEY__|$FERNET_KEY|" \
        -e "s|__DB_USER__|$DB_USER|; s|__DB_PASSWORD__|$DB_PASSWORD|; s|__DB_NAME__|$DB_NAME|" \
        -e "s|__REDIS_QUEUE_DB__|$REDIS_QUEUE_DB|g; s|__REDIS_CACHE_DB__|$REDIS_CACHE_DB|g" \
        -e "s|__S3_PORT__|$S3_PORT|; s|__S3_ACCESS_KEY__|$S3_ACCESS_KEY|; s|__S3_SECRET_KEY__|$S3_SECRET_KEY|" \
        -e "s|__CLAMD_PORT__|$CLAMD_PORT|; s|__EMBEDDING_MODEL__|$EMBEDDING_MODEL|; s|__HF_HOME__|$HF_HOME_DIR|" \
        "$HERE/env-templates/backend.env.production" > "$BACKEND/.env"
    chown "$APP_USER:$APP_USER" "$BACKEND/.env" && chmod 600 "$BACKEND/.env"
    # SeaweedFS identity with the same generated key pair
    "$PYTHON" - "$S3_CONF" "$S3_ACCESS_KEY" "$S3_SECRET_KEY" <<'PY'
import json, sys
path, key, secret = sys.argv[1:4]
json.dump({"identities": [{"name": "mhrs", "credentials": [{"accessKey": key, "secretKey": secret}],
                           "actions": ["Admin", "Read", "Write", "List", "Tagging"]}]}, open(path, "w"))
PY
    chown "$APP_USER:$APP_USER" "$S3_CONF" && chmod 600 "$S3_CONF"
else
    echo "    $BACKEND/.env already exists -- not overwriting."
    [[ -f "$S3_CONF" ]] || die "$S3_CONF is missing while backend/.env exists; restore it from a backup."
fi

if [[ ! -f "$FRONTEND/.env" ]]; then
    log "Writing $FRONTEND/.env"
    sed -e "s|__SITE_DOMAIN__|$SITE_DOMAIN|g" -e "s|__BACKEND_PORT__|$BACKEND_PORT|g" \
        "$HERE/env-templates/frontend.env.production" > "$FRONTEND/.env"
    chown "$APP_USER:$APP_USER" "$FRONTEND/.env" && chmod 640 "$FRONTEND/.env"
fi

log "Writing the ClamAV daemon config (loopback TCP $CLAMD_PORT, shared signature database)"
cat > "$RUN_DIR/clamd.conf" <<EOF
Foreground yes
TCPSocket $CLAMD_PORT
TCPAddr 127.0.0.1
DatabaseDirectory /var/lib/clamav
LogSyslog yes
LogTime yes
MaxThreads 4
StreamMaxLength 30M
MaxFileSize 30M
MaxScanSize 60M
# one copy of the signatures in memory during reloads: this server hosts five stacks
ConcurrentDatabaseReload no
EOF
chown "$APP_USER:$APP_USER" "$RUN_DIR/clamd.conf"

# ------------------------------------------------------------------ network
if command -v getenforce >/dev/null 2>&1 && [[ "$(getenforce)" != "Disabled" ]]; then
    setsebool -P httpd_can_network_connect 1
fi

log "Memory"
free -h | sed 's/^/    /'

cat <<EOF

$(printf '\033[1;32m==> Setup complete\033[0m')

  Site address   https://$SITE_DOMAIN
  DNS            $(getent hosts "$SITE_DOMAIN" | awk '{print $1}' | head -1 || echo "NOT RESOLVING: add A record $SITE_DOMAIN -> $SERVER_IP")

Next:
  1. bash $APP_DIR/infrastructure/vps/deploy.sh
  2. certbot --nginx -d $SITE_DOMAIN --redirect
  3. bash $APP_DIR/infrastructure/vps/create-admin.sh      (you type the password)
  4. bash $APP_DIR/infrastructure/vps/configure-email.sh   (outgoing mailbox)
EOF
