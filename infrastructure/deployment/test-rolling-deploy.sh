#!/usr/bin/env bash
# Rehearsal of deploy.sh's rolling restart (EC-OPS-04), runnable in CI and locally:
#
#   infrastructure/deployment/test-rolling-deploy.sh
#
# Starts nginx with the real production template and small stand-in backend/frontend servers (release 1),
# keeps sending requests through nginx, rolls both services to release 2 with deploy.sh's
# roll_side_by_side, and fails if any request did not return 200 or if the old release still answers.
# shellcheck disable=SC2034  # variables set before sourcing deploy.sh are read there
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
NGINX_IMAGE=$(grep -oE 'nginx:[0-9][^" ]+' "$ROOT/docker-compose.prod.yml" | head -1)
PY_IMAGE=$(grep -oE 'python:3\.12\.[0-9]+-slim-[a-z]+' "$ROOT/backend/Dockerfile" | head -1)
PORT="${REHEARSAL_PORT:-18443}"
WORK=$(mktemp -d "$HERE/.rehearsal.XXXXXX")
# forward-slash Windows paths (D:/...) on Git Bash: valid for docker and inside YAML strings
host() { if command -v cygpath >/dev/null; then cygpath -m "$1"; else echo "$1"; fi; }
export MSYS_NO_PATHCONV=1 COMPOSE_PROJECT_NAME=mhrs-rehearsal

cleanup() {
  [[ -n ${LOAD_PID:-} ]] && kill "$LOAD_PID" 2>/dev/null || true
  docker compose -f "$(host "$WORK/compose.yml")" --env-file "$(host "$WORK/.env")" down -v --remove-orphans >/dev/null 2>&1 || true
  rm -rf "$WORK"
}
trap cleanup EXIT

mkdir -p "$WORK/le/live/mhrs" "$WORK/local/upstreams" "$WORK/static" "$WORK/certbot"
echo 'server backend:8000 resolve max_fails=0;' >"$WORK/local/upstreams/backend.conf"
echo 'server frontend:3000 resolve max_fails=0;' >"$WORK/local/upstreams/frontend.conf"
openssl req -x509 -newkey rsa:2048 -nodes -days 1 -subj "/CN=hr.mhrs.test" \
  -keyout "$(host "$WORK/le/live/mhrs/privkey.pem")" -out "$(host "$WORK/le/live/mhrs/fullchain.pem")" 2>/dev/null
printf 'deny all;\n' >"$WORK/local/ops-allowlist.conf"
: >"$WORK/local/flower.htpasswd"
chmod -R a+rX "$WORK"

# stand-in app server with gunicorn's shutdown semantics: answers every path with its release; on SIGTERM
# it closes the listening socket at once (new connections are refused, so nginx tries the other
# container), finishes in-flight requests, and drops idle keep-alive connections after 5 s
cat >"$WORK/server.py" <<'EOF'
import os, signal, sys, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

RELEASE = os.environ["RELEASE"]

class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    timeout = 5  # idle keep-alive, like gunicorn --keep-alive 5 / Node's default
    def do_GET(self):
        time.sleep(0.05)  # a little work, so requests are in flight during the switch
        body = f"release={RELEASE}\n".encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def log_message(self, *args):
        pass

server = ThreadingHTTPServer(("0.0.0.0", int(sys.argv[1])), Handler)
server.daemon_threads = False
server.block_on_close = True
def stop(*_):
    server.socket.close()  # refuse new connections immediately
    threading.Thread(target=server.shutdown).start()
signal.signal(signal.SIGTERM, stop)
server.serve_forever()
server.server_close()
EOF

cat >"$WORK/compose.yml" <<EOF
name: mhrs-rehearsal
x-app: &app
  image: $PY_IMAGE
  volumes: ["$(host "$WORK/server.py"):/srv/server.py:ro"]
  environment: { RELEASE: "\${RELEASE}" }
  stop_grace_period: 20s
services:
  backend:
    <<: *app
    command: ["python", "/srv/server.py", "8000"]
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/healthz', timeout=2)"]
      interval: 2s
      timeout: 3s
      retries: 10
  frontend:
    <<: *app
    command: ["python", "/srv/server.py", "3000"]
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:3000/', timeout=2)"]
      interval: 2s
      timeout: 3s
      retries: 10
  nginx:
    image: $NGINX_IMAGE
    ports: ["127.0.0.1:$PORT:443"]
    environment: { MHRS_DOMAIN: hr.mhrs.test, MHRS_ENVIRONMENT: staging, NGINX_ENVSUBST_FILTER: "^MHRS_" }
    volumes:
      - "$(host "$ROOT/infrastructure/nginx/templates"):/etc/nginx/templates:ro"
      - "$(host "$ROOT/infrastructure/nginx/snippets"):/etc/nginx/snippets:ro"
      - "$(host "$WORK/local"):/etc/nginx/local:ro"
      - "$(host "$WORK/le"):/etc/letsencrypt:ro"
      - "$(host "$WORK/static"):/srv/static:ro"
      - "$(host "$WORK/certbot"):/var/www/certbot:ro"
    depends_on:
      backend: { condition: service_healthy }
      frontend: { condition: service_healthy }
EOF

echo "RELEASE=1" >"$WORK/.env"
docker compose -f "$(host "$WORK/compose.yml")" --env-file "$(host "$WORK/.env")" up -d --wait >/dev/null
URL="https://hr.mhrs.test:$PORT"
CURL=(curl -k -s --max-time 10 --resolve "hr.mhrs.test:$PORT:127.0.0.1" -o /dev/null -w '%{http_code}\n')
for _ in $(seq 1 30); do [[ $("${CURL[@]}" "$URL/api/v1/ping") == 200 ]] && break; sleep 1; done

# steady traffic through nginx (API + pages) while the release changes
: >"$WORK/codes"
(
  while :; do
    "${CURL[@]}" "$URL/api/v1/ping" >>"$WORK/codes" &
    "${CURL[@]}" "$URL/" >>"$WORK/codes" &
    sleep 0.1
  done
) &
LOAD_PID=$!
sleep 2

echo "RELEASE=2" >"$WORK/.env"
# shellcheck source=deploy.sh
# (plain assignments: a prefix on `source` would be undone after it returns, with deploy.sh's own defaults)
MHRS_APP_DIR="$WORK"
MHRS_LOG_DIR="$WORK"
UPSTREAM_DIR="$WORK/local/upstreams"
ROLL_HEALTH_TIMEOUT=60
source "$HERE/deploy.sh"
COMPOSE_FILE="$(host "$WORK/compose.yml")"
ENV_FILE="$(host "$WORK/.env")"
roll_side_by_side backend
roll_side_by_side frontend
sleep 3
kill "$LOAD_PID"
LOAD_PID=""
wait 2>/dev/null || true
sleep 1

total=$(wc -l <"$WORK/codes")
bad=$(grep -vc '^200$' "$WORK/codes" || true)
backend_count=$(dc ps -q backend | wc -l)
frontend_count=$(dc ps -q frontend | wc -l)
api_release=$(curl -k -s --resolve "hr.mhrs.test:$PORT:127.0.0.1" "$URL/api/v1/ping")
page_release=$(curl -k -s --resolve "hr.mhrs.test:$PORT:127.0.0.1" "$URL/")
echo "requests: $total, non-200: $bad, backend containers: $backend_count, frontend containers: $frontend_count"
echo "now serving: api $api_release / page $page_release"
[[ $total -gt 50 ]] || { echo "FAIL: too little traffic generated"; exit 1; }
if [[ $bad -ne 0 ]]; then
  echo "FAIL: non-200 responses during the roll:"
  sort "$WORK/codes" | uniq -c
  echo "nginx errors:"
  dc logs --no-color nginx 2>&1 | grep -E '\[(error|warn)\]' | sed -E 's/, (client|server|host|request|referrer): [^,]*//g' | tail -15
  exit 1
fi
[[ $backend_count -eq 1 && $frontend_count -eq 1 ]] || { echo "FAIL: expected one container per service"; exit 1; }
grep -q 'server backend:8000 resolve' "$WORK/local/upstreams/backend.conf" || { echo "FAIL: backend upstream not restored to the service name"; exit 1; }
[[ $api_release == "release=2" && $page_release == "release=2" ]] || { echo "FAIL: old release still answering"; exit 1; }
echo "rolling deploy rehearsal OK: zero failed requests"
