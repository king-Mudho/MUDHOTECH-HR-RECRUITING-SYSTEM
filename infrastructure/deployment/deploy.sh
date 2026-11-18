#!/usr/bin/env bash
# MUDHOTECH HR RECRUITING SYSTEM - deploy a release on this host (P11-T05, docs/10 §4).
# Runs as the `mhrs` deploy user (docker group) in the checkout at /opt/mhrs:
#
#   infrastructure/deployment/deploy.sh <tag>      # e.g. v1.0.0 (production) or sha-<commit> (staging)
#   infrastructure/deployment/deploy.sh rollback   # redeploy the previous release (no migrations)
#   infrastructure/deployment/deploy.sh status
#
# Steps: lock -> render .env from SSM (/mhrs/<env>/) -> check out the release -> pull images -> migrate
# (expand-only, one-off container) + taxonomy -> rolling restart (backend, frontend side by side with the
# old container until healthy; workers warm-shutdown; beat last; nginx graceful reload) -> smoke tests ->
# record the release. A failed smoke test rolls back to the previous release automatically (the schema is
# backward compatible: expand/contract, EC-OPS-05), so no database rollback is needed.
#
# Test hooks (CI / local rehearsal only): SKIP_SSM=1 (use the existing .env), SKIP_GIT=1 (deploy the
# current checkout), SKIP_PULL=1 (images already present), SMOKE_URL=http://... (instead of https://<domain>).
set -euo pipefail

APP_DIR="${MHRS_APP_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
[[ ${BASH_SOURCE[0]} == "$0" ]] && cd "$APP_DIR"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
RELEASES="$APP_DIR/releases"
LOG_DIR="${MHRS_LOG_DIR:-/var/log/mhrs}"
ENV_FILE="$APP_DIR/.env"
ROLL_HEALTH_TIMEOUT="${ROLL_HEALTH_TIMEOUT:-240}"
NGINX_DRAIN_WAIT="${NGINX_DRAIN_WAIT:-3}"
UPSTREAM_DIR="${UPSTREAM_DIR:-/etc/mhrs/nginx/upstreams}"   # mounted at /etc/nginx/local/upstreams
mkdir -p "$RELEASES"
[[ -w $LOG_DIR ]] || LOG_DIR="$RELEASES"

log() { printf '%s [deploy] %s\n' "$(date -u +%FT%TZ)" "$*" | tee -a "$LOG_DIR/deploy.log" >&2; }
die() { log "ERROR: $*"; exit 1; }
dc() { docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" "$@"; }
# a value from the rendered .env (values may be single-quoted)
env_get() { sed -n "s/^$1=//p" "$ENV_FILE" | tail -1 | sed "s/^'\(.*\)'\$/\1/"; }

environment() {
  local e="${MHRS_ENVIRONMENT:-}"
  [[ -z $e && -r /etc/mhrs/environment ]] && e=$(tr -d '[:space:]' </etc/mhrs/environment)
  [[ $e =~ ^(staging|production)$ ]] || die "MHRS_ENVIRONMENT must be staging or production (or set /etc/mhrs/environment)"
  echo "$e"
}

valid_tag() { [[ $1 =~ ^(v[0-9]+\.[0-9]+\.[0-9]+(-[0-9A-Za-z.]+)?|sha-[0-9a-f]{7,40})$ ]]; }

# --- 1. configuration from SSM Parameter Store -------------------------------------------------------
render_env() {
  local env="$1" tag="$2" tmp
  if [[ ${SKIP_SSM:-0} == 1 ]]; then
    [[ -f $ENV_FILE ]] || die "SKIP_SSM=1 but $ENV_FILE does not exist"
  else
    command -v aws >/dev/null || die "aws CLI not found (ec2-bootstrap.sh installs it)"
    tmp=$(mktemp "$APP_DIR/.env.XXXXXX")
    chmod 600 "$tmp"
    # parameter name == variable name; GHCR_READ_TOKEN is for this script only, never for containers
    aws ssm get-parameters-by-path --path "/mhrs/$env/" --recursive --with-decryption --output json \
      | python3 -c '
import json, re, sys
params = json.load(sys.stdin)["Parameters"]
for p in sorted(params, key=lambda p: p["Name"]):
    name = p["Name"].rsplit("/", 1)[-1]
    value = p["Value"]
    if name == "GHCR_READ_TOKEN":
        continue
    if not re.fullmatch(r"[A-Z][A-Z0-9_]*", name) or "\n" in value or "\x27" in value:
        sys.exit(f"refusing parameter {name}: invalid name, multi-line value or single quote")
    # single-quoted: docker compose takes the value literally (no ${...} interpolation of secrets)
    print(f"{name}=\x27{value}\x27")
' >"$tmp" || { rm -f "$tmp"; die "could not read /mhrs/$env/ from SSM"; }
    grep -q '^SECRET_KEY=' "$tmp" || { rm -f "$tmp"; die "SSM /mhrs/$env/ has no SECRET_KEY - see docs/deployment/AWS_SETUP.md §6"; }
    mv "$tmp" "$ENV_FILE"
  fi
  # the release tag and image names are deploy facts, not configuration
  sed -i '/^MHRS_TAG=/d;/^MHRS_BACKEND_IMAGE=/d;/^MHRS_WORKER_IMAGE=/d;/^MHRS_FRONTEND_IMAGE=/d' "$ENV_FILE"
  local prefix="${MHRS_IMAGE_PREFIX:-$(env_get MHRS_IMAGE_PREFIX)}"
  prefix="${prefix:-ghcr.io/king-mudho}"
  {
    echo "MHRS_TAG=$tag"
    echo "MHRS_BACKEND_IMAGE=$prefix/mhrs-backend"
    echo "MHRS_WORKER_IMAGE=$prefix/mhrs-worker"
    echo "MHRS_FRONTEND_IMAGE=$prefix/mhrs-frontend"
  } >>"$ENV_FILE"
  chmod 600 "$ENV_FILE"
}

registry_login() {
  [[ ${SKIP_PULL:-0} == 1 || ${SKIP_SSM:-0} == 1 ]] && return 0
  local env="$1" token
  token=$(aws ssm get-parameter --name "/mhrs/$env/GHCR_READ_TOKEN" --with-decryption \
            --query Parameter.Value --output text 2>/dev/null || true)
  [[ -n $token && $token != None ]] || { log "no GHCR_READ_TOKEN: assuming public images"; return 0; }
  printf '%s' "$token" | docker login ghcr.io -u mhrs-deploy --password-stdin >/dev/null
}

# --- 2. code (compose file, nginx templates, scripts) at the release ---------------------------------
checkout() {
  local tag="$1"
  [[ ${SKIP_GIT:-0} == 1 ]] && return 0
  git fetch --quiet --tags origin
  local ref="$tag"
  [[ $tag == sha-* ]] && ref="${tag#sha-}"
  git -c advice.detachedHead=false checkout --quiet --detach "$ref" || die "release $tag not found in git"
}

# --- 3. rolling restart helpers ----------------------------------------------------------------------
health_of() { docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$1" 2>/dev/null || echo missing; }

wait_healthy() {
  local id="$1" deadline=$((SECONDS + ROLL_HEALTH_TIMEOUT)) status
  while ((SECONDS < deadline)); do
    status=$(health_of "$id")
    case $status in
      healthy) return 0 ;;
      unhealthy | exited | dead | missing) break ;;
    esac
    sleep 3
  done
  log "container ${id:0:12} did not become healthy (status: $(health_of "$id"))"
  docker logs --tail 60 "$id" 2>&1 | sed 's/^/    /' >&2 || true
  return 1
}

port_of() { case $1 in backend) echo 8000 ;; frontend) echo 3000 ;; *) die "no upstream port for $1" ;; esac; }

# nginx upstream for a service: the compose service name normally, one container's name during a roll
set_upstream() {
  local svc="$1" target="$2" file="$UPSTREAM_DIR/$1.conf"
  mkdir -p "$UPSTREAM_DIR"
  printf '# managed by deploy.sh\nserver %s:%s resolve max_fails=0;\n' "$target" "$(port_of "$svc")" >"$file.tmp"
  mv "$file.tmp" "$file"
}

nginx_reload_only() {
  [[ -n $(dc ps -q nginx) ]] || return 0
  dc exec -T nginx sh -c 'nginx -t -q && nginx -s reload 2>/dev/null' || die "nginx rejected the upstream change"
  sleep "$NGINX_DRAIN_WAIT"   # old nginx workers finish their in-flight requests
}

# Start the new container next to the old one and wait until it is healthy; point nginx at it (graceful
# reload), stop the old one (it finishes in-flight requests), then point nginx back at the service name.
# If the new container never becomes healthy it is removed and the old one keeps serving.
roll_side_by_side() {
  local svc="$1" old new name
  old=$(dc ps -q "$svc" | tr '\n' ' ')
  if [[ -z ${old// /} ]]; then
    set_upstream "$svc" "$svc"
    dc up -d --no-deps "$svc"
    new=$(dc ps -q "$svc")
    wait_healthy "$new" || die "$svc did not start"
    return 0
  fi
  dc up -d --no-deps --no-recreate --scale "$svc=2" "$svc"
  new=$(dc ps -q "$svc" | grep -v -F -x -f <(tr ' ' '\n' <<<"$old" | sed '/^$/d') || true)
  [[ -n $new ]] || die "$svc: no new container was created"
  if ! wait_healthy "$new"; then
    docker rm -f "$new" >/dev/null
    die "$svc: new release unhealthy - old container still serving"
  fi
  name=$(docker inspect -f '{{.Name}}' "$new")
  set_upstream "$svc" "${name#/}"
  nginx_reload_only
  for id in $old; do
    docker stop -t 40 "$id" >/dev/null   # gunicorn / next finish in-flight requests
    docker rm "$id" >/dev/null
  done
  dc up -d --no-deps --no-recreate --scale "$svc=1" "$svc" >/dev/null
  set_upstream "$svc" "$svc"
  nginx_reload_only
  log "$svc rolled to $(docker inspect -f '{{.Config.Image}}' "$new")"
}

restart_in_place() {
  # workers: SIGTERM = warm shutdown (stop_grace_period 120 s); unacked tasks are redelivered (acks_late)
  dc up -d --no-deps "$@"
}

reload_nginx() {
  if [[ -z $(dc ps -q nginx) ]]; then
    dc up -d --no-deps nginx
  else
    dc up -d --no-deps nginx   # recreates only if its compose definition changed
    # re-render the template (it may have changed with the release) and reload without dropping connections
    dc exec -T nginx sh -c '/docker-entrypoint.d/20-envsubst-on-templates.sh >/dev/null && nginx -t -q && nginx -s reload'
  fi
}

# --- 4. smoke tests ----------------------------------------------------------------------------------
smoke() {
  local domain base
  domain=$(env_get MHRS_DOMAIN)
  base="${SMOKE_URL:-https://$domain}"
  local -a curl_opts=(-fsS --max-time 15 -o /dev/null)
  [[ -z ${SMOKE_URL:-} ]] && curl_opts+=(--resolve "$domain:443:127.0.0.1")
  dc exec -T backend curl -fsS --max-time 10 http://localhost:8000/readyz >/dev/null || { log "smoke: /readyz failed"; return 1; }
  for path in /healthz /jobs /login /api/v1/jobs/; do
    curl "${curl_opts[@]}" "$base$path" || { log "smoke: $base$path failed"; return 1; }
  done
  log "smoke tests passed ($base)"
}

# --- main --------------------------------------------------------------------------------------------
deploy() {
  local tag="$1" skip_migrate="${2:-}"
  valid_tag "$tag" || die "invalid release tag: $tag (expected vX.Y.Z or sha-<commit>)"
  local env previous
  env=$(environment)
  previous=$(cat "$RELEASES/current" 2>/dev/null || true)
  log "deploying $tag to $env (previous: ${previous:-none})"

  render_env "$env" "$tag"
  registry_login "$env"
  checkout "$tag"
  [[ ${SKIP_PULL:-0} == 1 ]] || dc pull --quiet backend worker-default worker-documents worker-ai beat frontend nginx redis clamav

  # nginx upstreams default to the compose service names (rolls switch them temporarily)
  [[ -f $UPSTREAM_DIR/backend.conf ]] || set_upstream backend backend
  [[ -f $UPSTREAM_DIR/frontend.conf ]] || set_upstream frontend frontend

  # infrastructure services first (no-op when unchanged)
  dc up -d --no-deps redis clamav

  if [[ $skip_migrate != --skip-migrate ]]; then
    log "migrations (expand-only) and reference data"
    dc run --rm --no-deps -T backend python manage.py migrate --noinput
    dc run --rm --no-deps -T backend python manage.py load_taxonomy
    dc run --rm --no-deps -T worker-ai python manage.py embed_skills
    dc run --rm --no-deps -T backend python manage.py check --deploy --fail-level ERROR
  fi

  roll_side_by_side backend
  roll_side_by_side frontend
  restart_in_place worker-default worker-documents worker-ai
  restart_in_place beat
  reload_nginx

  if ! smoke; then
    if [[ -n $previous && $previous != "$tag" && ${NO_AUTO_ROLLBACK:-0} != 1 ]]; then
      log "smoke tests failed - rolling back to $previous"
      NO_AUTO_ROLLBACK=1 deploy "$previous" --skip-migrate
      die "release $tag failed its smoke tests; $previous restored"
    fi
    die "release $tag failed its smoke tests"
  fi

  [[ -n $previous && $previous != "$tag" ]] && echo "$previous" >"$RELEASES/previous"
  echo "$tag" >"$RELEASES/current"
  echo "$(date -u +%FT%TZ) $tag $env $(git rev-parse --short HEAD 2>/dev/null || echo -)" >>"$RELEASES/history"
  docker image prune -f --filter "until=168h" >/dev/null || true   # EC-OPS-08
  log "release $tag is live on $env"
}

main() {
  exec 9>"$RELEASES/.deploy.lock"
  flock -n 9 || die "another deploy is running"
  case "${1:-}" in
    status)
      echo "current:  $(cat "$RELEASES/current" 2>/dev/null || echo none)"
      echo "previous: $(cat "$RELEASES/previous" 2>/dev/null || echo none)"
      dc ps --format 'table {{.Service}}\t{{.Image}}\t{{.Status}}'
      ;;
    rollback)
      local prev
      prev=$(cat "$RELEASES/previous" 2>/dev/null) || die "no previous release recorded"
      NO_AUTO_ROLLBACK=1 deploy "$prev" --skip-migrate
      ;;
    "" | -h | --help)
      sed -n '2,16p' "$0"
      ;;
    *)
      deploy "$1"
      ;;
  esac
}

# sourcing (rehearsal test) only defines the functions
if [[ ${BASH_SOURCE[0]} == "$0" ]]; then
  main "$@"
fi
