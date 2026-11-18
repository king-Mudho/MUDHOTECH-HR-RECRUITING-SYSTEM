#!/usr/bin/env bash
# Weekly logical backup of the MHRS database to S3 (P11-T06, docs/10 §3 "Backups").
# RDS automated backups + point-in-time recovery are the primary recovery path (RPO ~5 min); this
# pg_dump is the independent second copy (survives an RDS-level mistake, restorable anywhere).
#
#   infrastructure/deployment/backup.sh                 # dump -> verify -> upload to s3://<S3_BUCKET_BACKUPS>/postgres/
#   infrastructure/deployment/backup.sh --local DIR     # dump -> verify -> keep in DIR (drills, ad-hoc copies)
#
# Reads DATABASE_URL (and S3_BUCKET_BACKUPS, MHRS_ENVIRONMENT) from the environment or /opt/mhrs/.env.
# Installed as a weekly systemd timer by `backup.sh --install-timer` (Sunday 01:30 UTC, after the RDS window).
set -euo pipefail

APP_DIR="${MHRS_APP_DIR:-/opt/mhrs}"
ENV_FILE="${ENV_FILE:-$APP_DIR/.env}"
LOG_DIR="${MHRS_LOG_DIR:-/var/log/mhrs}"
[[ -w $LOG_DIR ]] || LOG_DIR="${TMPDIR:-/tmp}"

log() { printf '%s [backup] %s\n' "$(date -u +%FT%TZ)" "$*" | tee -a "$LOG_DIR/backup.log" >&2; }
die() { log "ERROR: $*"; metric 0; exit 1; }
env_get() {
  local v="${!1:-}"
  [[ -z $v && -r $ENV_FILE ]] && v=$(sed -n "s/^$1=//p" "$ENV_FILE" | tail -1 | sed "s/^'\(.*\)'\$/\1/")
  printf '%s' "$v"
}
metric() {
  # BackupSucceeded 1/0 -> CloudWatch alarm when no successful backup for 8 days (P11-T07)
  [[ ${MODE:-} == upload ]] && command -v aws >/dev/null || return 0
  aws cloudwatch put-metric-data --namespace "MHRS/${ENVIRONMENT:-unknown}" --metric-name BackupSucceeded \
    --value "$1" --unit Count >/dev/null 2>&1 || true
}

install_timer() {
  [[ $EUID -eq 0 ]] || { echo "run --install-timer as root" >&2; exit 1; }
  cat >/etc/systemd/system/mhrs-backup.service <<EOF
[Unit]
Description=MHRS weekly logical database backup to S3
After=docker.service network-online.target

[Service]
Type=oneshot
User=mhrs
ExecStart=$APP_DIR/infrastructure/deployment/backup.sh
Nice=10
IOSchedulingClass=idle
EOF
  cat >/etc/systemd/system/mhrs-backup.timer <<'EOF'
[Unit]
Description=Weekly MHRS database backup

[Timer]
OnCalendar=Sun *-*-* 01:30:00 UTC
Persistent=true
RandomizedDelaySec=10min

[Install]
WantedBy=timers.target
EOF
  systemctl daemon-reload
  systemctl enable --now mhrs-backup.timer
  systemctl list-timers mhrs-backup.timer --no-pager
}

MODE=upload
OUT_DIR=""
case "${1:-}" in
  --install-timer) install_timer; exit 0 ;;
  --local) MODE=local; OUT_DIR="${2:?usage: backup.sh --local DIR}" ;;
  "") ;;
  *) echo "usage: backup.sh [--local DIR | --install-timer]" >&2; exit 2 ;;
esac

ENVIRONMENT=$(env_get MHRS_ENVIRONMENT)
[[ -z $ENVIRONMENT && -r /etc/mhrs/environment ]] && ENVIRONMENT=$(tr -d '[:space:]' </etc/mhrs/environment)
ENVIRONMENT="${ENVIRONMENT:-local}"
DATABASE_URL=$(env_get DATABASE_URL)
[[ -n $DATABASE_URL ]] || die "DATABASE_URL is not set (environment or $ENV_FILE)"
command -v pg_dump >/dev/null || die "pg_dump not found (postgresql-client-16; ec2-bootstrap.sh installs it)"

stamp=$(date -u +%Y%m%dT%H%M%SZ)
work="${OUT_DIR:-$(mktemp -d)}"
mkdir -p "$work"
file="$work/mhrs-$ENVIRONMENT-$stamp.dump"
[[ $MODE == upload ]] && trap 'rm -rf "$work"' EXIT

started=$SECONDS
log "dumping $ENVIRONMENT database"
# --enable-row-security: the app role is subject to the FORCEd tenant policies (ADR-012). Without it pg_dump
# refuses to run ("query would be affected by row-level security policy"); with app.current_org unset the
# policy admits every row, so the dump is complete.
pg_dump --dbname="$DATABASE_URL" --format=custom --compress=6 --no-owner --no-privileges \
  --enable-row-security --file="$file" || die "pg_dump failed"
dump_seconds=$((SECONDS - started))

# integrity: the archive's table of contents must be readable and contain table data
entries=$(pg_restore --list "$file" | grep -c 'TABLE DATA' || true)
[[ $entries -gt 0 ]] || die "dump has no table data entries"
sha256sum "$file" | sed "s#  .*/#  #" >"$file.sha256"
size=$(du -h "$file" | cut -f1)
log "dump ok: $(basename "$file") ($size, $entries tables with data, ${dump_seconds}s)"

if [[ $MODE == upload ]]; then
  bucket=$(env_get S3_BUCKET_BACKUPS)
  bucket="${bucket:-mhrs-$ENVIRONMENT-backups}"
  dest="s3://$bucket/postgres/$(date -u +%Y/%m)/"
  aws s3 cp --only-show-errors --sse AES256 "$file" "$dest" || die "upload to $dest failed"
  aws s3 cp --only-show-errors --sse AES256 "$file.sha256" "$dest" || die "checksum upload failed"
  log "uploaded to $dest$(basename "$file") (lifecycle: 35 days)"
fi
metric 1
# read by infrastructure/monitoring/host-checks.sh -> BackupAgeHours (alarm after 8 days without success)
[[ $MODE == upload ]] && date +%s >"$LOG_DIR/last-backup-success"
log "backup finished in $((SECONDS - started))s"
echo "$file"
