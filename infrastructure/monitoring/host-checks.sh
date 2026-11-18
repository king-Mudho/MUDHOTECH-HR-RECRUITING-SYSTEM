#!/usr/bin/env bash
# Host-level checks the containers cannot see, published to CloudWatch every 15 minutes (P11-T07):
#   CertDaysLeft         days until the TLS certificate expires (alarm < 14, docs/10 §8)
#   UnhealthyContainers  containers whose healthcheck reports unhealthy, or that are restarting
#   ContainersRunning    running containers of the mhrs compose project
#
#   infrastructure/monitoring/host-checks.sh               # run once (prints the values)
#   sudo infrastructure/monitoring/host-checks.sh --install-timer
set -euo pipefail

CERT="${MHRS_CERT:-/etc/letsencrypt/live/mhrs/fullchain.pem}"
ENVIRONMENT="${MHRS_ENVIRONMENT:-$(tr -d '[:space:]' </etc/mhrs/environment 2>/dev/null || echo unknown)}"
NAMESPACE="MHRS/$ENVIRONMENT"
SCRIPT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$(basename "${BASH_SOURCE[0]}")"

if [[ ${1:-} == --install-timer ]]; then
  [[ $EUID -eq 0 ]] || { echo "run --install-timer as root" >&2; exit 1; }
  cat >/etc/systemd/system/mhrs-host-checks.service <<EOF
[Unit]
Description=MHRS host checks (certificate expiry, container health) to CloudWatch

[Service]
Type=oneshot
ExecStart=$SCRIPT
EOF
  cat >/etc/systemd/system/mhrs-host-checks.timer <<'EOF'
[Unit]
Description=MHRS host checks every 15 minutes

[Timer]
OnBootSec=2min
OnUnitActiveSec=15min

[Install]
WantedBy=timers.target
EOF
  systemctl daemon-reload
  systemctl enable --now mhrs-host-checks.timer
  exit 0
fi

cert_days=-1
if [[ -r $CERT ]]; then
  end=$(openssl x509 -enddate -noout -in "$CERT" | cut -d= -f2)
  cert_days=$(( ($(date -d "$end" +%s) - $(date +%s)) / 86400 ))
fi
unhealthy=$(docker ps --filter label=com.docker.compose.project=mhrs --format '{{.Status}}' \
  | grep -c -E '\(unhealthy\)|Restarting' || true)
running=$(docker ps --filter label=com.docker.compose.project=mhrs --filter status=running -q | wc -l)
# backup.sh writes the epoch of its last success; no file yet = no backup ever (large age, alarm fires)
last_backup=$(cat "${MHRS_LOG_DIR:-/var/log/mhrs}/last-backup-success" 2>/dev/null || echo 0)
backup_age_hours=$(( ($(date +%s) - last_backup) / 3600 ))

echo "CertDaysLeft=$cert_days UnhealthyContainers=$unhealthy ContainersRunning=$running BackupAgeHours=$backup_age_hours ($NAMESPACE)"
if command -v aws >/dev/null && [[ $ENVIRONMENT != unknown ]]; then
  aws cloudwatch put-metric-data --namespace "$NAMESPACE" --metric-data \
    "MetricName=CertDaysLeft,Value=$cert_days,Unit=Count" \
    "MetricName=UnhealthyContainers,Value=$unhealthy,Unit=Count" \
    "MetricName=ContainersRunning,Value=$running,Unit=Count" \
    "MetricName=BackupAgeHours,Value=$backup_age_hours,Unit=Count"
fi
