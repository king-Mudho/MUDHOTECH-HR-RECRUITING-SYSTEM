#!/usr/bin/env bash
# Seed the STAGING environment with synthetic data (P11-T09). Refuses to run anywhere but staging.
#
#   infrastructure/deployment/seed-staging.sh            # demo organisations, staff, vacancies, candidates
#   infrastructure/deployment/seed-staging.sh --core     # + the core scenario: 100 applications to the demo
#                                                        #   Software Developer vacancy (processed by the workers)
#
# Every synthetic account shares DEMO_PASSWORD (SSM /mhrs/staging/DEMO_PASSWORD). Data is synthetic only
# (CLAUDE.md: never real CVs or personal data on staging). To start over, restore the staging database from
# the snapshot taken right after the first seed (docs/runbooks/restore-database.md) and rerun.
set -euo pipefail

APP_DIR="${MHRS_APP_DIR:-/opt/mhrs}"
cd "$APP_DIR"
env_name=$(tr -d '[:space:]' </etc/mhrs/environment 2>/dev/null || true)
[[ $env_name == staging ]] || { echo "seed-staging.sh: this host is '${env_name:-unknown}', not staging - refusing" >&2; exit 1; }
grep -q "^DEMO_PASSWORD=" .env || { echo "seed-staging.sh: set /mhrs/staging/DEMO_PASSWORD in SSM and redeploy" >&2; exit 1; }

DC=(docker compose -f docker-compose.prod.yml --env-file .env)
run() { "${DC[@]}" run --rm --no-deps -T backend python manage.py "$@"; }

echo "==> demo organisations, staff, vacancies and candidates"
run seed_demo --allow-non-debug
if [[ ${1:-} == --core ]]; then
  echo "==> core scenario: 100 synthetic applications (outcome emails delayed 1 minute, to Mailpit)"
  run seed_core_scenario --allow-non-debug --count 100 --delay-minutes 1
  echo "    processing takes a few minutes: watch ProcessingBacklogAgeSeconds or the HR applicants page"
fi
run check_human_decisions
echo "done - sign in at https://$(sed -n "s/^MHRS_DOMAIN=//p" .env | tr -d "'") with the demo accounts (docs/user-guides)"
