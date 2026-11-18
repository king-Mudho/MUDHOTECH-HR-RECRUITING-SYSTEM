#!/usr/bin/env bash
# Restore a logical MHRS backup into a NEW database and verify it (P11-T06,
# docs/runbooks/restore-database.md). It never drops or overwrites an existing database: switching the
# application to the restored database is a separate, deliberate step in the runbook.
#
#   ADMIN_DATABASE_URL=postgres://mhrs_admin:...@<host>:5432/postgres \
#   infrastructure/deployment/restore.sh <s3://bucket/key.dump | /path/file.dump> <target_db> [owner_role]
#
#   ADMIN_DATABASE_URL  a role that may CREATE DATABASE and extensions (RDS master user; never stored in SSM
#                       for the app). The restored objects are owned by owner_role (default mhrs_app).
#   RESTORE_JOBS        parallel pg_restore jobs (default 2)
set -euo pipefail

SRC="${1:?usage: restore.sh <s3-uri|file> <target_db> [owner_role]}"
TARGET="${2:?usage: restore.sh <s3-uri|file> <target_db> [owner_role]}"
OWNER="${3:-mhrs_app}"
ADMIN_URL="${ADMIN_DATABASE_URL:?set ADMIN_DATABASE_URL (a role allowed to create databases)}"
JOBS="${RESTORE_JOBS:-2}"
LOG_DIR="${MHRS_LOG_DIR:-/var/log/mhrs}"
[[ -w $LOG_DIR ]] || LOG_DIR="${TMPDIR:-/tmp}"

log() { printf '%s [restore] %s\n' "$(date -u +%FT%TZ)" "$*" | tee -a "$LOG_DIR/restore.log" >&2; }
die() { log "ERROR: $*"; exit 1; }
[[ $TARGET =~ ^[a-z_][a-z0-9_]{0,62}$ ]] || die "target database name must be a lowercase identifier"
[[ $OWNER =~ ^[a-z_][a-z0-9_]{0,62}$ ]] || die "owner role must be a lowercase identifier"
for tool in psql pg_restore; do command -v "$tool" >/dev/null || die "$tool not found (postgresql-client-16)"; done

# the URL of the same server, pointing at another database
url_for() { python3 -c 'import sys, urllib.parse as u; p = u.urlsplit(sys.argv[1]); print(u.urlunsplit(p._replace(path="/" + sys.argv[2])))' "$ADMIN_URL" "$1"; }
psql_admin() { psql "$ADMIN_URL" -v ON_ERROR_STOP=1 -Atq "$@"; }

started=$SECONDS
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

# 1. fetch + checksum
if [[ $SRC == s3://* ]]; then
  command -v aws >/dev/null || die "aws CLI needed for s3:// sources"
  aws s3 cp --only-show-errors "$SRC" "$work/backup.dump"
  aws s3 cp --only-show-errors "$SRC.sha256" "$work/backup.dump.sha256" 2>/dev/null || true
  dump="$work/backup.dump"
else
  [[ -r $SRC ]] || die "cannot read $SRC"
  dump="$SRC"
  [[ -r $SRC.sha256 ]] && cp "$SRC.sha256" "$work/backup.dump.sha256"
fi
if [[ -s $work/backup.dump.sha256 ]]; then
  expected=$(cut -d' ' -f1 "$work/backup.dump.sha256")
  actual=$(sha256sum "$dump" | cut -d' ' -f1)
  [[ $expected == "$actual" ]] || die "checksum mismatch: the backup is corrupt or was modified"
  log "checksum ok"
else
  log "WARNING: no .sha256 next to the backup - integrity not verified"
fi
fetch_seconds=$((SECONDS - started))

# 2. new, empty database (refuse to touch an existing one)
exists=$(psql_admin -c "SELECT 1 FROM pg_database WHERE datname = '$TARGET'")
[[ -z $exists ]] || die "database $TARGET already exists - choose a new name (restores never overwrite)"
# PostgreSQL 16: creating a database for, and restoring as, another role needs membership in it (on RDS the
# master user created mhrs_app, so it holds ADMIN OPTION and may grant this to itself)
psql_admin -c "GRANT $OWNER TO CURRENT_USER" 2>/dev/null || true
psql_admin -c "CREATE DATABASE $TARGET OWNER $OWNER"
target_admin_url=$(url_for "$TARGET")

# extensions (vector, pg_trgm, unaccent, citext, ...) are created here as the admin, exactly as listed in the
# dump; their TOC entries are then left out, because the owner role may not create or comment on them
pg_restore --list "$dump" >"$work/toc.all"
mapfile -t extensions < <(awk '$4 == "EXTENSION" && $5 == "-" {print $6}' "$work/toc.all")
for ext in "${extensions[@]}"; do
  [[ $ext =~ ^[a-z0-9_]+$ ]] || die "unexpected extension name in the dump: $ext"
  psql "$target_admin_url" -v ON_ERROR_STOP=1 -q -c "CREATE EXTENSION IF NOT EXISTS \"$ext\""
done
awk '!(($4 == "EXTENSION" && $5 == "-") || ($4 == "COMMENT" && $5 == "-" && $6 == "EXTENSION"))' \
  "$work/toc.all" >"$work/toc.restore"
psql "$target_admin_url" -v ON_ERROR_STOP=1 -q -c "GRANT USAGE, CREATE ON SCHEMA public TO $OWNER;"
log "created database $TARGET (owner $OWNER; extensions: ${extensions[*]:-none})"

# 3. restore as the owner role (objects owned by it, so the FORCEd RLS policies keep applying - ADR-012)
restore_start=$SECONDS
pg_restore --dbname="$target_admin_url" --role="$OWNER" --no-owner --no-privileges --exit-on-error \
  --enable-row-security --jobs="$JOBS" --use-list="$work/toc.restore" "$dump" \
  || die "pg_restore failed - $TARGET is incomplete; drop it after investigating"
restore_seconds=$((SECONDS - restore_start))

# 4. verification queries (docs/runbooks/restore-database.md §Verify)
psql "$target_admin_url" -v ON_ERROR_STOP=1 -At <<'SQL' >"$work/verify.txt"
SELECT 'migrations|' || count(*) FROM django_migrations;
SELECT 'organisations|' || count(*) FROM organisations_organisation;
SELECT 'users|' || count(*) FROM accounts_user;
SELECT 'jobs|' || count(*) FROM jobs_job;
SELECT 'applications|' || count(*) FROM applications_application;
SELECT 'documents|' || count(*) FROM documents_document;
SELECT 'audit_events|' || count(*) FROM audit_auditevent;
SELECT 'latest_audit_event|' || coalesce(max(created_at)::text, 'none') FROM audit_auditevent;
SELECT 'rls_forced_tables|' || count(*) FROM pg_class WHERE relforcerowsecurity;
SELECT 'owner_is_superuser|' || bool_or(r.rolsuper) FROM pg_class c JOIN pg_roles r ON r.oid = c.relowner
  WHERE c.relnamespace = 'public'::regnamespace AND c.relkind = 'r';
SQL
sed 's/|/: /' "$work/verify.txt" | sed 's/^/  /' >&2
grep -q '^migrations|0$' "$work/verify.txt" && die "restored database has no migrations table rows"
grep -q '^rls_forced_tables|0$' "$work/verify.txt" && die "row-level security is not forced on any table after restore"

total=$((SECONDS - started))
log "restore of $(basename "$SRC") into $TARGET: fetch ${fetch_seconds}s, restore ${restore_seconds}s, total ${total}s"
cat >&2 <<EOF
Next (docs/runbooks/restore-database.md):
  * verify the audit hash chain against $TARGET:
      docker compose -f docker-compose.prod.yml run --rm -e DATABASE_URL=<url of $TARGET as $OWNER> backend python manage.py verify_audit_chain
  * to recover: put the application in maintenance, point DATABASE_URL (SSM) at $TARGET, redeploy.
EOF
