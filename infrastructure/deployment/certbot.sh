#!/usr/bin/env bash
# Let's Encrypt certificates for the MHRS nginx container (P11-T02, docs/10 §5).
#
#   sudo infrastructure/deployment/certbot.sh issue  <domain> <contact-email> [--staging]
#   sudo infrastructure/deployment/certbot.sh renew          # what the systemd timer runs
#   sudo infrastructure/deployment/certbot.sh status
#
# * certbot runs on the host (Ubuntu package, kept current by unattended-upgrades).
# * The certificate lineage is always named `mhrs` (/etc/letsencrypt/live/mhrs/), which the nginx
#   snippet infrastructure/nginx/snippets/tls.conf points at, whatever the domain.
# * First issuance uses --standalone with nginx stopped (nginx cannot start without a certificate);
#   renewals use the webroot /var/www/certbot served by nginx on port 80, then reload nginx.
# * Accepting the Let's Encrypt subscriber agreement is the owner's decision: `issue` passes
#   --agree-tos only because the owner runs it with their contact email.
set -euo pipefail

APP_DIR="${MHRS_APP_DIR:-/opt/mhrs}"
COMPOSE=(docker compose -f "$APP_DIR/docker-compose.prod.yml" --env-file "$APP_DIR/.env")
WEBROOT=/var/www/certbot
LINEAGE=mhrs

die() { echo "certbot.sh: $*" >&2; exit 1; }
need_root() { [[ $EUID -eq 0 ]] || die "run as root (sudo)"; }
nginx_running() { "${COMPOSE[@]}" ps --status running --services 2>/dev/null | grep -qx nginx; }
reload_nginx() {
  if nginx_running; then
    "${COMPOSE[@]}" exec -T nginx nginx -t -q && "${COMPOSE[@]}" exec -T nginx nginx -s reload
    echo "nginx reloaded"
  fi
}

install_renewal_hook() {
  # certbot runs deploy hooks after every successful renewal, including from certbot.timer
  local hook=/etc/letsencrypt/renewal-hooks/deploy/mhrs-reload-nginx.sh
  mkdir -p "$(dirname "$hook")"
  cat >"$hook" <<EOF
#!/bin/sh
# installed by infrastructure/deployment/certbot.sh
[ "\$RENEWED_LINEAGE" = "/etc/letsencrypt/live/$LINEAGE" ] || exit 0
docker compose -f "$APP_DIR/docker-compose.prod.yml" --env-file "$APP_DIR/.env" exec -T nginx nginx -s reload
EOF
  chmod 755 "$hook"
}

cmd_issue() {
  need_root
  local domain="${1:-}" email="${2:-}" staging="${3:-}"
  [[ -n $domain && -n $email ]] || die "usage: certbot.sh issue <domain> <contact-email> [--staging]"
  [[ $domain =~ ^[A-Za-z0-9.-]+\.[A-Za-z]{2,}$ ]] || die "invalid domain: $domain"
  command -v certbot >/dev/null || apt-get install -y certbot
  mkdir -p "$WEBROOT"

  local was_running=0
  if nginx_running; then was_running=1; "${COMPOSE[@]}" stop nginx; fi
  local args=(certonly --standalone --non-interactive --agree-tos --email "$email"
              --cert-name "$LINEAGE" -d "$domain" --key-type ecdsa --elliptic-curve secp384r1)
  [[ $staging == "--staging" ]] && args+=(--staging)
  certbot "${args[@]}" || { [[ $was_running == 1 ]] && "${COMPOSE[@]}" start nginx; die "issuance failed"; }

  # later renewals go through nginx (webroot), not standalone
  # (certbot >= 2.3; Ubuntu 24.04 ships 2.9). Needs nginx up to answer the dry-run challenge.
  "${COMPOSE[@]}" up -d nginx
  certbot reconfigure --cert-name "$LINEAGE" --webroot -w "$WEBROOT" --non-interactive \
    || die "could not switch renewals to webroot - check that nginx serves $WEBROOT on port 80"
  install_renewal_hook
  systemctl enable --now certbot.timer >/dev/null 2>&1 || true
  echo "certificate issued for $domain; renewals run from certbot.timer (twice a day)"
}

cmd_renew() {
  need_root
  certbot renew --quiet --webroot -w "$WEBROOT"
  reload_nginx
}

cmd_status() {
  certbot certificates --cert-name "$LINEAGE"
  systemctl list-timers certbot.timer --no-pager || true
}

case "${1:-}" in
  issue)  shift; cmd_issue "$@" ;;
  renew)  cmd_renew ;;
  status) cmd_status ;;
  *) die "usage: certbot.sh {issue <domain> <email> [--staging]|renew|status}" ;;
esac
