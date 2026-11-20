#!/usr/bin/env bash
#
# Owner step: allow the GitHub Actions deploy key to run ci-deploy.sh, and nothing else.
# Run on the server as root, with the PUBLIC key (one line, "ssh-ed25519 AAAA... mhrs-github-deploy"):
#
#   bash /srv/mhrs/infrastructure/vps/install-deploy-key.sh "ssh-ed25519 AAAA... mhrs-github-deploy"
#
# The key is added to /root/.ssh/authorized_keys with `restrict` (no shell, TTY, port/agent/X11
# forwarding) and a forced command, so even a leaked private key can only deploy a valid MHRS
# release archive. Remove it by deleting the line that ends in "mhrs-github-deploy".

set -euo pipefail
pub="${1:-}"
[[ $EUID -eq 0 ]] || { echo "Run as root." >&2; exit 1; }
[[ "$pub" =~ ^ssh-ed25519\ [A-Za-z0-9+/=]+(\ .*)?$ ]] || { echo "Give the ed25519 PUBLIC key line as the argument." >&2; exit 1; }
[[ -f /srv/mhrs/infrastructure/vps/ci-deploy.sh ]] || { echo "ci-deploy.sh is missing; deploy a current release first." >&2; exit 1; }

keyfile=/root/.ssh/authorized_keys
key_body="$(awk '{print $2}' <<<"$pub")"
if grep -qF "$key_body" "$keyfile" 2>/dev/null; then
    echo "This key is already installed."
    exit 0
fi
cp -p "$keyfile" "$keyfile.bak.$(date +%Y%m%d%H%M%S)"
printf 'restrict,command="/usr/bin/bash /srv/mhrs/infrastructure/vps/ci-deploy.sh" %s\n' "$pub" >> "$keyfile"
echo "Deploy key installed, restricted to ci-deploy.sh."
echo "Test from your computer (expect 'refused'):  ssh -i ~/.ssh/mhrs_github_deploy root@66.29.139.201 hello"
