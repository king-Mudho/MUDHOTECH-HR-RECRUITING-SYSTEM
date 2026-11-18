#!/usr/bin/env bash
# Fault injection (P10-T07, EC-OPS-01..04): while 60 synthetic applications are submitted and
# processed by the real workers, Redis is stopped, a worker container is killed and PostgreSQL is
# restarted. Pass = every application accounted for, nothing waiting, no duplicate evaluation or
# status move (run_pilot_benchmark exits 1 otherwise). Run from the repository root after
# `docker compose up` + `seed_demo` (see .github/workflows/load.yml, job "resilience").
set -uo pipefail
DC="docker compose ${COMPOSE_FILES:-}"
note() { echo "::notice title=Resilience::$*"; echo "[$(date +%T)] $*"; }

$DC exec -T -d backend sh -c \
  'python manage.py run_pilot_benchmark --count 60 --timeout 2100 --out /tmp/RESILIENCE.md > /tmp/pilot.log 2>&1; echo $? > /tmp/pilot.exit'
note "pilot started (60 applications, workers process them)"

sleep 8
note "EC-OPS-01: stopping Redis during submissions"
$DC stop redis
sleep 25
$DC start redis
note "Redis back"

sleep 20
note "EC-OPS-04: killing the document worker container mid-task"
$DC kill worker-documents
sleep 20
$DC start worker-documents
note "document worker back"

sleep 30
note "EC-OPS-03: restarting PostgreSQL during processing"
$DC restart postgres
note "PostgreSQL back"

for i in $(seq 1 240); do
  if $DC exec -T backend test -f /tmp/pilot.exit; then break; fi
  sleep 10
done
code=$($DC exec -T backend cat /tmp/pilot.exit 2>/dev/null || echo "timeout")
$DC cp backend:/tmp/RESILIENCE.md RESILIENCE.md 2>/dev/null || true
$DC exec -T backend tail -n 40 /tmp/pilot.log || true
grep -E "records found|Still waiting|Duplicate|accounted for|median / max|^- Submitting" RESILIENCE.md 2>/dev/null \
  | sed 's/^/::notice title=Resilience result::/' || true
note "pilot exit code: $code"
[ "$code" = "0" ]
