#!/usr/bin/env bash
#
# Run the MHRS production monitor (monitor.py) as the mhrs user with the backend environment.
# Started every 5 minutes by mhrs-monitor.timer. Manual use:
#
#   bash /srv/mhrs/infrastructure/vps/monitor.sh           # run the checks now
#   bash /srv/mhrs/infrastructure/vps/monitor.sh --test    # send a test alert email

set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=site.conf
source "$HERE/site.conf"

states=""
for s in "${SERVICES[@]}"; do states+="$s=$(systemctl is-active "$s") "; done

cd "$BACKEND" || exit 1
exec sudo -u "$APP_USER" env DJANGO_SETTINGS_MODULE=config.settings.prod SITE_DOMAIN="$SITE_DOMAIN" \
    SERVICE_STATES="$states" PYTHONPATH="$BACKEND" \
    bash -c 'set -a; source .env; set +a; exec .venv/bin/python "$0" "$@"' "$HERE/monitor.py" "$@"
