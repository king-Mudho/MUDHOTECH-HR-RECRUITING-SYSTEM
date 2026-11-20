#!/usr/bin/env bash
#
# Forced command for the GitHub Actions deploy key (deploy-prod.yml). The key can run nothing else:
# authorized_keys pins it to this script with no shell, no port forwarding and no TTY. Usage, as sent
# by the workflow:
#
#   ssh -i deploy_key root@66.29.139.201 "deploy v1.2.0" < mhrs-release.tar.gz
#
# The release archive arrives on stdin (git archive of the tagged commit). It is checked, unpacked
# into /srv/mhrs and deployed with deploy.sh (backup first, migrations, build, restart, checks).

set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=site.conf
source "$HERE/site.conf"

refuse() { echo "refused: $1" >&2; exit 2; }

read -r verb tag extra <<<"${SSH_ORIGINAL_COMMAND:-}"
[[ "${verb:-}" == "deploy" && -z "${extra:-}" ]] || refuse "only 'deploy <tag>' is allowed"
[[ "${tag:-}" =~ ^v[0-9]+\.[0-9]+\.[0-9]+(-[0-9A-Za-z.]+)?$ ]] || refuse "not a release tag: ${tag:-}"

tmp="$(mktemp /tmp/mhrs-release-XXXXXX.tar.gz)"
trap 'rm -f "$tmp"' EXIT
head -c 209715200 > "$tmp"                      # at most 200 MB from stdin
gzip -t "$tmp" 2>/dev/null || refuse "not a gzip archive"
listing="$(tar -tzf "$tmp")"
grep -qx 'infrastructure/vps/deploy.sh' <<<"$listing" || refuse "not an MHRS release archive"
! grep -Eq '(^/|(^|/)\.\.(/|$))' <<<"$listing" || refuse "archive contains unsafe paths"
! grep -Eq '(^|/)\.env$' <<<"$listing" || refuse "archive contains an .env file"

echo "==> Unpacking release $tag into $APP_DIR"
tar -xzf "$tmp" -C "$APP_DIR"
echo "$tag" > "$RUN_DIR/release-tag"
echo "==> Deploying $tag"
exec bash "$APP_DIR/infrastructure/vps/deploy.sh"
