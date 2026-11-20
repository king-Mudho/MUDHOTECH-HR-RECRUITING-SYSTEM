#!/usr/bin/env bash
#
# External check of the live MHRS site, using the real host name throughout.
#
#   bash infrastructure/vps/check-production.sh            (from anywhere with internet access)

set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=site.conf
source "$HERE/site.conf"
BASE="https://$SITE_DOMAIN"
failed=0
check() {  # check <name> <expected> <url> [curl args]
    local name="$1" expected="$2" url="$3"; shift 3
    local code
    code="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 20 "$@" "$url" 2>/dev/null || echo 000)"
    if [[ "$code" == "$expected" ]]; then printf '  ok    %-36s %s\n' "$name" "$code"
    else printf '  FAIL  %-36s got %s, expected %s\n' "$name" "$code" "$expected"; failed=1; fi
}
echo "MHRS production check: $BASE"
resolved="$(getent hosts "$SITE_DOMAIN" 2>/dev/null | awk '{print $1}' | head -1)"
[[ -z "$resolved" ]] && resolved="$(nslookup "$SITE_DOMAIN" 2>/dev/null | awk '/^Address: /{print $2}' | tail -1)"
[[ "$resolved" == "$SERVER_IP" ]] && echo "  ok    DNS                                  $resolved" \
    || { echo "  FAIL  DNS resolves to '${resolved:-nothing}', expected $SERVER_IP"; failed=1; }
check "HTTP redirects to HTTPS" 301 "http://$SITE_DOMAIN/"
check "home page" 200 "$BASE/"
check "job board" 200 "$BASE/jobs"
check "login page" 200 "$BASE/login"
check "health" 200 "$BASE/healthz"
check "readiness (db, redis, storage)" 200 "$BASE/readyz"
check "public jobs API" 200 "$BASE/api/v1/jobs/"
check "unsigned storage access refused" 403 "$BASE/mhrs-documents/x"
check "django admin not exposed" 404 "$BASE/django-admin/"
expiry="$(echo | openssl s_client -servername "$SITE_DOMAIN" -connect "$SITE_DOMAIN:443" 2>/dev/null | openssl x509 -noout -enddate 2>/dev/null | cut -d= -f2)"
[[ -n "$expiry" ]] && echo "  ok    certificate valid until              $expiry" || { echo "  FAIL  no certificate"; failed=1; }
hsts="$(curl -sSI --max-time 15 "$BASE/" | grep -i '^strict-transport-security' | tr -d '\r')"
[[ -n "$hsts" ]] && echo "  ok    $hsts" || { echo "  FAIL  no HSTS header"; failed=1; }
if command -v systemctl >/dev/null && systemctl list-unit-files mhrs-backend.service >/dev/null 2>&1; then
    for s in "${SERVICES[@]}"; do printf '  %-5s %-36s %s\n' "$(systemctl is-active --quiet "$s" && echo ok || echo FAIL)" "$s" "$(systemctl is-active "$s")"; done
fi
exit $failed
