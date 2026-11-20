#!/usr/bin/env bash
#
# Build and (re)start MHRS on the shared VPS. Run for the first deploy and every update.
#
#   bash /srv/mhrs/infrastructure/vps/deploy.sh
#
#   1. back up the database and file storage (refuses to migrate without a restore point)
#   2. install locked Python dependencies (uv, --frozen) and the local embedding model
#   3. start the private S3 storage and ClamAV daemon; create the buckets
#   4. Django deploy checks, migrations (expand-only), taxonomy, skill vectors, templates, static
#   5. build the frontend with the private Node 24 and switch to the new release (last 3 kept)
#   6. install and restart the systemd units (worker gets a warm shutdown)
#   7. install the nginx site on the first deploy; afterwards only validate it
#   8. health checks against gunicorn, Node and nginx, with the real host name

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=site.conf
source "$HERE/site.conf"

KEEP_RELEASES=3
log()  { printf '\n\033[1;34m==>\033[0m %s\n' "$1"; }
warn() { printf '\033[1;33m[warn]\033[0m %s\n' "$1"; }
die()  { printf '\033[1;31m[error]\033[0m %s\n' "$1" >&2; exit 1; }

[[ $EUID -eq 0 ]] || die "Run this as root."
[[ "$HERE" == "$APP_DIR/infrastructure/vps" ]] || die "Run the copy at $APP_DIR/infrastructure/vps/deploy.sh."
[[ -f "$BACKEND/.env" && -f "$FRONTEND/.env" ]] || die "Run setup-server.sh first."
exec 9>"$RUN_DIR/deploy.lock"; flock -n 9 || die "Another deploy is running."

APP_HOME="/home/$APP_USER"
NODE_PATH_DIR="$NODE_DIR/bin"
as_app() { sudo -u "$APP_USER" env "HOME=$APP_HOME" "PATH=$NODE_PATH_DIR:/usr/local/bin:/usr/bin:/bin" "$@"; }
manage() {
    ( cd "$BACKEND" && sudo -u "$APP_USER" env "HOME=$APP_HOME" DJANGO_SETTINGS_MODULE=config.settings.prod \
        HF_HOME="$HF_HOME_DIR" bash -c 'set -a; source .env; set +a; exec .venv/bin/python manage.py "$@"' _ "$@" )
}
wait_port() {  # wait_port <port> <seconds> <name>
    for _ in $(seq 1 "$2"); do
        [[ -n "$(ss -ltnH "sport = :$1" 2>/dev/null)" ]] && return 0
        sleep 1
    done
    die "$3 did not start listening on 127.0.0.1:$1 (journalctl -u ... for details)."
}

log "Fixing ownership"
chown -R "$APP_USER:$APP_USER" "$APP_DIR"
chmod 600 "$BACKEND/.env" "$RUN_DIR/s3.json"
chmod 700 "$BACKUP_DIR" "$S3_DATA_DIR" "$RUN_DIR"

FIRST_DEPLOY=0
[[ -d "$BACKEND/.venv" ]] || FIRST_DEPLOY=1

# --------------------------------------------------------------------- backup
if [[ "${SKIP_BACKUP:-0}" == "1" ]]; then
    warn "SKIP_BACKUP=1: deploying with NO restore point."
elif (( FIRST_DEPLOY )); then
    warn "First deploy: nothing to back up yet."
else
    log "Backing up before migrating"
    bash "$HERE/backup.sh" || die "Backup FAILED; refusing to migrate. Fix it or re-run with SKIP_BACKUP=1."
fi

# -------------------------------------------------------------------- backend
log "Installing locked Python dependencies (uv --frozen, with the local embedding extra)"
( cd "$BACKEND" && as_app env UV_PROJECT_ENVIRONMENT="$BACKEND/.venv" UV_PYTHON="$PYTHON" \
    UV_PYTHON_DOWNLOADS=never UV_LINK_MODE=copy UV_CACHE_DIR="$APP_HOME/.cache/uv" \
    "$TOOLS_DIR/uv/bin/uv" sync --frozen --no-dev --no-install-project --extra ml --quiet )

SEMANTIC="$(grep -E '^SEMANTIC_SKILL_MATCHING=' "$BACKEND/.env" | cut -d= -f2 | tr '[:upper:]' '[:lower:]')"
if [[ "$SEMANTIC" == "false" ]]; then
    warn "Semantic skill matching is off (SEMANTIC_SKILL_MATCHING=false): no embedding model needed."
else
    log "Fetching the local embedding model ($EMBEDDING_MODEL) into $HF_HOME_DIR (once)"
    # run from a directory the app user can read: the library first looks for the model name as a path
    ( cd "$BACKEND" && as_app env HF_HOME="$HF_HOME_DIR" "$BACKEND/.venv/bin/python" -c \
        "from sentence_transformers import SentenceTransformer as S; S('$EMBEDDING_MODEL', device='cpu')" >/dev/null )
fi

log "Installing systemd units"
for unit in "$APP_DIR"/infrastructure/vps/systemd/*.service "$APP_DIR"/infrastructure/vps/systemd/*.timer; do
    install -m 644 "$unit" /etc/systemd/system/
done
systemctl daemon-reload
systemctl enable "${SERVICES[@]}" mhrs-backup.timer mhrs-monitor.timer >/dev/null 2>&1
systemctl start mhrs-backup.timer mhrs-monitor.timer

log "Starting private storage and the virus scanner"
systemctl restart mhrs-s3
systemctl start mhrs-clamd
wait_port "$S3_PORT" 60 "S3 storage"

log "Creating the storage buckets (idempotent)"
( cd "$BACKEND" && sudo -u "$APP_USER" bash -c 'set -a; source .env; set +a; exec .venv/bin/python -' <<'PY'
import os, time
import boto3
from botocore.config import Config
s3 = boto3.client("s3", endpoint_url=os.environ["S3_ENDPOINT_URL"], region_name=os.environ.get("S3_REGION"),
                  aws_access_key_id=os.environ["S3_ACCESS_KEY"], aws_secret_access_key=os.environ["S3_SECRET_KEY"],
                  config=Config(s3={"addressing_style": "path"}))
for attempt in range(30):
    try:
        existing = {b["Name"] for b in s3.list_buckets().get("Buckets", [])}
        break
    except Exception:
        time.sleep(2)
else:
    raise SystemExit("S3 storage is not answering")
for name in ("S3_BUCKET_QUARANTINE", "S3_BUCKET_DOCUMENTS", "S3_BUCKET_EXPORTS", "S3_BUCKET_PUBLIC"):
    bucket = os.environ[name]
    if bucket not in existing:
        s3.create_bucket(Bucket=bucket)
        print(f"    created {bucket}")
print("    buckets ready")
PY
)

log "Django deploy checks"
manage check --deploy --fail-level ERROR

log "Database migrations (expand-only)"
manage migrate --noinput
manage migrate --check

log "Skills taxonomy, skill vectors and notification templates (repeat-safe)"
manage load_taxonomy
if [[ "$SEMANTIC" != "false" ]]; then
    ( cd "$BACKEND" && sudo -u "$APP_USER" env "HOME=$APP_HOME" DJANGO_SETTINGS_MODULE=config.settings.prod \
        HF_HOME="$HF_HOME_DIR" HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
        bash -c 'set -a; source .env; set +a; exec .venv/bin/python manage.py embed_skills' )
fi
manage sync_notification_templates

log "Collecting static files"
manage collectstatic --noinput --clear >/dev/null

# ------------------------------------------------------------------- frontend
log "Installing Node dependencies (Node $("$NODE_DIR/bin/node" --version))"
( cd "$FRONTEND" && as_app npm ci --no-audit --no-fund --loglevel=error )

log "Building the frontend"
( cd "$FRONTEND" && as_app env NODE_OPTIONS=--max-old-space-size=2048 NEXT_TELEMETRY_DISABLED=1 npm run build >/dev/null ) \
    || die "Frontend build failed (re-run: cd $FRONTEND && sudo -u $APP_USER env PATH=$NODE_PATH_DIR:\$PATH npm run build)."
[[ -f "$FRONTEND/.next/standalone/server.js" ]] || die "The build did not produce .next/standalone/server.js."

log "Assembling the frontend release"
RELEASE_ID="$(date +%Y%m%d%H%M%S)"
RELEASE_DIR="$FRONTEND/releases/$RELEASE_ID"
mkdir -p "$RELEASE_DIR/.next"
cp -r "$FRONTEND/.next/standalone/." "$RELEASE_DIR/"
cp -r "$FRONTEND/.next/static" "$RELEASE_DIR/.next/static"
[[ -d "$FRONTEND/public" ]] && cp -r "$FRONTEND/public" "$RELEASE_DIR/public"
cp "$FRONTEND/.env" "$RELEASE_DIR/.env"
chown -R "$APP_USER:$APP_USER" "$RELEASE_DIR"
PREVIOUS="$(readlink -f "$FRONTEND/current" 2>/dev/null || true)"
ln -sfn "$RELEASE_DIR" "$FRONTEND/current"
chown -h "$APP_USER:$APP_USER" "$FRONTEND/current"
[[ -n "$PREVIOUS" && "$PREVIOUS" != "$RELEASE_DIR" ]] && echo "$PREVIOUS" > "$RUN_DIR/previous-frontend"
mapfile -t old < <(ls -1 "$FRONTEND/releases" | sort -r | tail -n +$((KEEP_RELEASES + 1)))
for o in "${old[@]:-}"; do [[ -n "$o" ]] && rm -rf "${FRONTEND:?}/releases/$o"; done

# ------------------------------------------------------------------- services
log "Restarting MHRS services"
systemctl restart mhrs-backend
systemctl restart mhrs-worker      # warm shutdown: running tasks finish first (TimeoutStopSec=120)
systemctl restart mhrs-beat
systemctl restart mhrs-frontend

# ---------------------------------------------------------------------- nginx
if [[ -f "$NGINX_CONF" ]] && grep -q "managed by Certbot" "$NGINX_CONF"; then
    log "nginx site is certbot-managed: validating in place"
    nginx -t 2>&1 | tail -1
    systemctl reload nginx
else
    log "Installing the nginx site for $SITE_DOMAIN (HTTP only until certbot runs)"
    sed -e "s|__SITE_DOMAIN__|$SITE_DOMAIN|g" -e "s|__APP_DIR__|$APP_DIR|g" \
        "$APP_DIR/infrastructure/vps/nginx/mhrs.conf.template" > "$NGINX_CONF.new"
    mv "$NGINX_CONF.new" "$NGINX_CONF" && chmod 644 "$NGINX_CONF"
    if ! nginx -t >/dev/null 2>&1; then
        mv "$NGINX_CONF" "$NGINX_CONF.rejected"
        nginx -t || true
        die "nginx rejected the MHRS site; moved to $NGINX_CONF.rejected so the other sites keep working."
    fi
    systemctl reload nginx
fi

# --------------------------------------------------------------------- verify
log "Verifying"
wait_port "$BACKEND_PORT" 60 "gunicorn"
wait_port "$FRONTEND_PORT" 60 "Next.js"
failed=0
check() {  # check <name> <expected> <curl args...>
    local name="$1" expected="$2"; shift 2
    local code
    code="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 20 "$@" 2>/dev/null || echo 000)"
    if [[ "$code" == "$expected" ]]; then printf '    \033[1;32mok\033[0m   %-34s %s\n' "$name" "$code"
    else printf '    \033[1;31mFAIL\033[0m %-34s got %s, expected %s\n' "$name" "$code" "$expected"; failed=1; fi
}
sleep 3
check "backend ready (db, redis, storage)" 200 -H "Host: $SITE_DOMAIN" -H "X-Forwarded-Proto: https" "http://127.0.0.1:$BACKEND_PORT/readyz"
check "public jobs API" 200 -H "Host: $SITE_DOMAIN" -H "X-Forwarded-Proto: https" "http://127.0.0.1:$BACKEND_PORT/api/v1/jobs/"
check "frontend (node)" 200 "http://127.0.0.1:$FRONTEND_PORT/"
if grep -q "managed by Certbot" "$NGINX_CONF"; then
    check "home page through nginx (https)" 200 --resolve "$SITE_DOMAIN:443:127.0.0.1" "https://$SITE_DOMAIN/"
    check "login page through nginx" 200 --resolve "$SITE_DOMAIN:443:127.0.0.1" "https://$SITE_DOMAIN/login"
    check "API through nginx" 200 --resolve "$SITE_DOMAIN:443:127.0.0.1" "https://$SITE_DOMAIN/api/v1/jobs/"
    check "unsigned storage access refused" 403 --resolve "$SITE_DOMAIN:443:127.0.0.1" "https://$SITE_DOMAIN/mhrs-documents/x"
else
    check "home page through nginx (http)" 200 -H "Host: $SITE_DOMAIN" "http://127.0.0.1/"
fi
for s in "${SERVICES[@]}"; do
    systemctl is-active --quiet "$s" && printf '    \033[1;32mok\033[0m   %-34s active\n' "$s" \
        || { printf '    \033[1;31mFAIL\033[0m %-34s %s\n' "$s" "$(systemctl is-active "$s")"; failed=1; }
done

if (( failed )); then
    cat <<EOF

Something is not answering. Logs:
    journalctl -u mhrs-backend -u mhrs-worker -u mhrs-frontend -n 80 --no-pager
    tail -n 50 /var/log/nginx/mhrs-error.log
Roll back the frontend: bash $APP_DIR/infrastructure/vps/rollback.sh
EOF
    exit 1
fi
echo "$RELEASE_ID" > "$RUN_DIR/current-release"
log "$(printf '\033[1;32mDeploy complete\033[0m') (frontend release $RELEASE_ID)"
free -m | sed 's/^/    /'
if (( FIRST_DEPLOY )) || ! grep -q "managed by Certbot" "$NGINX_CONF"; then
    cat <<EOF

Still to do on a first deploy:
  certbot --nginx -d $SITE_DOMAIN --redirect
  bash $APP_DIR/infrastructure/vps/create-admin.sh
  bash $APP_DIR/infrastructure/vps/configure-email.sh
EOF
fi
