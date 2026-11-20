#!/usr/bin/env bash
#
# Point MHRS outgoing email at a real SMTP mailbox (e.g. a Gmail or Workspace account with an
# app password, or your mail provider's SMTP). You type the password at the prompt; it goes
# straight into /srv/mhrs/backend/.env (owner-only) and is never printed.
#
#   ssh -t agribizframework "bash /srv/mhrs/infrastructure/vps/configure-email.sh"
#
# Until this runs, emails (including sign-up confirmations) are only written to the worker log.

set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=site.conf
source "$HERE/site.conf"
[[ $EUID -eq 0 ]] || { echo "Run as root." >&2; exit 1; }

read -r -p "SMTP server [smtp.gmail.com]: " host; host="${host:-smtp.gmail.com}"
read -r -p "Port (587 = STARTTLS, 465 = SSL) [587]: " port; port="${port:-587}"
read -r -p "Username (full email address): " user
read -r -s -p "Password or app password (not shown): " pass; echo
read -r -p "Sender name and address [MUDHOTECH HR RECRUITING SYSTEM <$user>]: " from
from="${from:-MUDHOTECH HR RECRUITING SYSTEM <$user>}"

scheme="smtp+tls"; [[ "$port" == "465" ]] && scheme="smtp+ssl"
url="$(python3 - "$scheme" "$user" "$pass" "$host" "$port" <<'PY'
import sys, urllib.parse as u
scheme, user, pw, host, port = sys.argv[1:6]
print(f"{scheme}://{u.quote(user, safe='')}:{u.quote(pw, safe='')}@{host}:{port}")
PY
)"

env_file="$BACKEND/.env"
cp "$env_file" "$env_file.bak.$(date +%Y%m%d%H%M%S)"
python3 - "$env_file" "$url" "$from" "$user" <<'PY'
import sys
path, url, sender, user = sys.argv[1:5]
lines = open(path).read().splitlines()
values = {"EMAIL_URL": url, "DEFAULT_FROM_EMAIL": f'"{sender}"', "SUPPORT_EMAIL": user}
out, seen = [], set()
for line in lines:
    key = line.split("=", 1)[0]
    if key in values:
        out.append(f"{key}={values[key]}"); seen.add(key)
    else:
        out.append(line)
out += [f"{k}={v}" for k, v in values.items() if k not in seen]
open(path, "w").write("\n".join(out) + "\n")
PY
chown "$APP_USER:$APP_USER" "$env_file" "$env_file".bak.* && chmod 600 "$env_file" "$env_file".bak.*
systemctl restart mhrs-backend mhrs-worker mhrs-beat

read -r -p "Send a test email to: " to
cd "$BACKEND"
sudo -u "$APP_USER" env DJANGO_SETTINGS_MODULE=config.settings.prod \
    bash -c 'set -a; source .env; set +a; exec .venv/bin/python manage.py send_test_email --to "$1"' _ "$to" \
    && echo "Sent. Check the inbox (and spam folder) of $to."
