#!/usr/bin/env bash
#
# Create (or promote) the MHRS platform administrator. You type the password at the prompt;
# it is passed to Django through the environment only, never shown or stored in shell history.
#
#   ssh -t agribizframework "bash /srv/mhrs/infrastructure/vps/create-admin.sh"

set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=site.conf
source "$HERE/site.conf"
[[ $EUID -eq 0 ]] || { echo "Run as root." >&2; exit 1; }

read -r -p "Platform admin email: " email
read -r -s -p "Password (min. 12 characters, not shown): " password; echo
read -r -s -p "Repeat the password: " again; echo
[[ "$password" == "$again" ]] || { echo "The passwords differ." >&2; exit 1; }

cd "$BACKEND"
sudo -u "$APP_USER" env DJANGO_SETTINGS_MODULE=config.settings.prod \
    PLATFORM_ADMIN_EMAIL="$email" PLATFORM_ADMIN_PASSWORD="$password" \
    bash -c 'set -a; source .env; set +a; exec .venv/bin/python manage.py create_platform_admin'
echo "Sign in at https://$SITE_DOMAIN/login. Two-factor authentication becomes mandatory after 7 days."
