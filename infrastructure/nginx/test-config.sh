#!/usr/bin/env bash
# Validate the nginx site with the pinned production image (CI and local):
#   infrastructure/nginx/test-config.sh            -> nginx -t for staging and production renders
# Uses a throw-away self-signed certificate and maps the upstream hostnames to 127.0.0.1.
set -euo pipefail
cd "$(dirname "$0")"
IMAGE=$(grep -oE 'nginx:[0-9][^" ]+' ../../docker-compose.prod.yml | head -1)
WORK=$(mktemp -d "$PWD/.cfgtest.XXXXXX")
trap 'rm -rf "$WORK"' EXIT
# Git Bash on Windows: docker needs Windows paths; no MSYS path rewriting of /CN=... or /etc/...
host() { if command -v cygpath >/dev/null; then cygpath -w "$1"; else echo "$1"; fi; }
export MSYS_NO_PATHCONV=1
mkdir -p "$WORK/le/live/mhrs" "$WORK/local/upstreams" "$WORK/static" "$WORK/certbot" "$WORK/nginxlog"
echo 'server backend:8000 resolve max_fails=0;' >"$WORK/local/upstreams/backend.conf"
echo 'server frontend:3000 resolve max_fails=0;' >"$WORK/local/upstreams/frontend.conf"
openssl req -x509 -newkey rsa:2048 -nodes -days 1 -subj "/CN=mhrs.test" \
  -keyout "$(host "$WORK/le/live/mhrs/privkey.pem")" -out "$(host "$WORK/le/live/mhrs/fullchain.pem")" 2>/dev/null
cp "$WORK/le/live/mhrs/fullchain.pem" "$WORK/le/live/mhrs/chain.pem"
printf 'allow 127.0.0.1;\ndeny all;\n' >"$WORK/local/ops-allowlist.conf"
# shellcheck disable=SC2016  # a literal (dummy) htpasswd hash
printf 'ops:$apr1$test$000000000000000000000.\n' >"$WORK/local/flower.htpasswd"
chmod -R a+rX "$WORK"

for env in staging production; do
  docker run --rm \
    -e MHRS_DOMAIN=hr.mhrs.test -e MHRS_ENVIRONMENT="$env" -e NGINX_ENVSUBST_FILTER='^MHRS_' \
    --add-host frontend:127.0.0.1 --add-host backend:127.0.0.1 \
    -v "$(host "$PWD/templates"):/etc/nginx/templates:ro" -v "$(host "$PWD/snippets"):/etc/nginx/snippets:ro" \
    -v "$(host "$WORK/local"):/etc/nginx/local:ro" -v "$(host "$WORK/le"):/etc/letsencrypt:ro" \
    -v "$(host "$WORK/static"):/srv/static:ro" -v "$(host "$WORK/certbot"):/var/www/certbot:ro" \
    -v "$(host "$WORK/nginxlog"):/var/log/mhrs-nginx" \
    "$IMAGE" sh -c '
      set -e
      out=$(/docker-entrypoint.sh nginx -t 2>&1) || { echo "$out"; exit 1; }
      if echo "$out" | grep -q "\[warn\]"; then echo "$out" | grep "\[warn\]"; exit 1; fi
      conf=/etc/nginx/conf.d/default.conf
      grep -q "server_name hr.mhrs.test;" $conf      # rendered from the template (stock site replaced)
      grep -q "env-'"$env"'.conf" $conf
      grep -q "\$request_uri" $conf                    # nginx variables survive envsubst
      test "$(ls /etc/nginx/conf.d)" = "default.conf"'
  echo "nginx config OK ($env)"
done
