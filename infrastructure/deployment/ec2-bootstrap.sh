#!/usr/bin/env bash
# MUDHOTECH HR RECRUITING SYSTEM - one-time (re-runnable) host setup for an EC2 Ubuntu 24.04 LTS instance
# (P11-T03, docs/10 §3). Run as root on a fresh instance, e.g. from EC2 user data or over SSM:
#
#   sudo SSH_ALLOW_CIDR=203.0.113.10/32 DEPLOY_SSH_KEY="ssh-ed25519 AAAA... ops" \
#        MHRS_ENVIRONMENT=staging bash infrastructure/deployment/ec2-bootstrap.sh
#
# Variables (all optional except where noted):
#   MHRS_ENVIRONMENT  staging | production (default production) - tags logs and the CloudWatch namespace
#   SSH_ALLOW_CIDR    CIDR allowed to reach port 22. Empty = port 22 closed (use SSM Session Manager).
#   DEPLOY_SSH_KEY    public key for the `mhrs` deploy user (CI deploys over SSH); empty = SSM only
#   SWAP_SIZE_GB      swap file size (default 4)
#   OPS_ALLOW_IPS     space-separated operator IPs/CIDRs for /django-admin, API docs, flower (default none)
#   APP_DIR           application checkout (default /opt/mhrs)
#
# What it does: OS updates + unattended security upgrades, Docker Engine + compose plugin (Docker's apt
# repository), chrony (Amazon Time Sync), ufw (80/443, 22 restricted), fail2ban, SSH hardening, swap,
# Docker log rotation, CloudWatch agent (memory/disk/swap metrics + logs), AWS CLI, certbot, the `mhrs`
# deploy user and the host-specific nginx files in /etc/mhrs/nginx. Safe to run again.
set -euo pipefail

MHRS_ENVIRONMENT="${MHRS_ENVIRONMENT:-production}"
SSH_ALLOW_CIDR="${SSH_ALLOW_CIDR:-}"
DEPLOY_SSH_KEY="${DEPLOY_SSH_KEY:-}"
SWAP_SIZE_GB="${SWAP_SIZE_GB:-4}"
OPS_ALLOW_IPS="${OPS_ALLOW_IPS:-}"
APP_DIR="${APP_DIR:-/opt/mhrs}"
DEPLOY_USER=mhrs
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
export DEBIAN_FRONTEND=noninteractive NEEDRESTART_MODE=a

log() { printf '\n==> %s\n' "$*"; }
die() { echo "ec2-bootstrap: $*" >&2; exit 1; }

[[ $EUID -eq 0 ]] || die "run as root"
# shellcheck source=/dev/null
. /etc/os-release
[[ ${ID:-} == ubuntu && ${VERSION_ID:-} == 24.04 ]] || die "expected Ubuntu 24.04 (found ${PRETTY_NAME:-unknown})"
[[ $MHRS_ENVIRONMENT =~ ^(staging|production)$ ]] || die "MHRS_ENVIRONMENT must be staging or production"
[[ $SWAP_SIZE_GB =~ ^[0-9]+$ ]] || die "SWAP_SIZE_GB must be a number"
ARCH=$(dpkg --print-architecture)   # amd64 (t3) or arm64 (t4g)

log "OS packages and unattended security upgrades"
apt-get update -q
apt-get -y -q -o Dpkg::Options::=--force-confold upgrade
apt-get install -y -q --no-install-recommends \
  ca-certificates curl gnupg jq unzip git chrony ufw fail2ban unattended-upgrades \
  apt-listchanges needrestart logrotate certbot apache2-utils postgresql-client-16
cat >/etc/apt/apt.conf.d/20auto-upgrades <<'EOF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
APT::Periodic::AutocleanInterval "7";
EOF
cat >/etc/apt/apt.conf.d/52mhrs-unattended-upgrades <<'EOF'
// security updates only; Docker Engine is upgraded deliberately (deploy window), not unattended
Unattended-Upgrade::Allowed-Origins {
  "${distro_id}:${distro_codename}-security";
  "${distro_id}ESMApps:${distro_codename}-apps-security";
  "${distro_id}ESM:${distro_codename}-infra-security";
};
Unattended-Upgrade::Remove-Unused-Dependencies "true";
Unattended-Upgrade::Automatic-Reboot "true";
Unattended-Upgrade::Automatic-Reboot-Time "03:30";
EOF
systemctl enable --now unattended-upgrades

log "Time: chrony with the Amazon Time Sync Service (EC-OPS-06)"
if ! grep -q '169.254.169.123' /etc/chrony/chrony.conf; then
  sed -i '1i server 169.254.169.123 prefer iburst minpoll 4 maxpoll 4' /etc/chrony/chrony.conf
fi
timedatectl set-timezone UTC          # servers run in UTC; the app displays Africa/Harare
systemctl enable --now chrony
systemctl restart chrony

log "Docker Engine + compose plugin (Docker's apt repository)"
install -m 0755 -d /etc/apt/keyrings
if [[ ! -s /etc/apt/keyrings/docker.asc ]]; then
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
fi
echo "deb [arch=$ARCH signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu ${VERSION_CODENAME} stable" \
  >/etc/apt/sources.list.d/docker.list
apt-get update -q
apt-get install -y -q docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
mkdir -p /etc/docker
cat >/etc/docker/daemon.json <<'EOF'
{
  "log-driver": "json-file",
  "log-opts": { "max-size": "20m", "max-file": "5" },
  "live-restore": true,
  "no-new-privileges": true,
  "userland-proxy": false
}
EOF
systemctl enable docker
systemctl restart docker

log "Swap (${SWAP_SIZE_GB} GB) and kernel settings"
if [[ $SWAP_SIZE_GB -gt 0 && ! -f /swapfile ]]; then
  fallocate -l "${SWAP_SIZE_GB}G" /swapfile
  chmod 600 /swapfile
  mkswap /swapfile >/dev/null
  swapon /swapfile
  grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >>/etc/fstab
fi
cat >/etc/sysctl.d/90-mhrs.conf <<'EOF'
vm.swappiness = 10
vm.overcommit_memory = 1
net.core.somaxconn = 1024
net.ipv4.tcp_syncookies = 1
net.ipv4.conf.all.rp_filter = 1
net.ipv4.conf.all.accept_redirects = 0
net.ipv4.conf.all.send_redirects = 0
net.ipv6.conf.all.accept_redirects = 0
kernel.kptr_restrict = 2
EOF
sysctl --system >/dev/null

log "Deploy user ($DEPLOY_USER) and application directory ($APP_DIR)"
id "$DEPLOY_USER" >/dev/null 2>&1 || useradd --create-home --shell /bin/bash "$DEPLOY_USER"
usermod -aG docker "$DEPLOY_USER"
install -d -o "$DEPLOY_USER" -g "$DEPLOY_USER" -m 0750 "$APP_DIR" "$APP_DIR/releases"
if [[ -n $DEPLOY_SSH_KEY ]]; then
  [[ $DEPLOY_SSH_KEY =~ ^(ssh-ed25519|ecdsa-sha2-nistp256|ssh-rsa)\  ]] || die "DEPLOY_SSH_KEY is not an OpenSSH public key"
  install -d -o "$DEPLOY_USER" -g "$DEPLOY_USER" -m 0700 "/home/$DEPLOY_USER/.ssh"
  touch "/home/$DEPLOY_USER/.ssh/authorized_keys"
  grep -qxF "$DEPLOY_SSH_KEY" "/home/$DEPLOY_USER/.ssh/authorized_keys" \
    || echo "$DEPLOY_SSH_KEY" >>"/home/$DEPLOY_USER/.ssh/authorized_keys"
  chown "$DEPLOY_USER:$DEPLOY_USER" "/home/$DEPLOY_USER/.ssh/authorized_keys"
  chmod 600 "/home/$DEPLOY_USER/.ssh/authorized_keys"
fi
# ACME webroot (served by nginx on port 80) and host-side logs (deploy.sh, backup.sh)
install -d -m 0755 /var/www/certbot /var/log/mhrs

log "Host-specific nginx files (/etc/mhrs/nginx)"
install -d -m 0755 /etc/mhrs /etc/mhrs/nginx
{
  echo "# operator allow-list for /django-admin/, /api/docs/, /api/schema/, /readyz, /flower/"
  echo "# managed by ec2-bootstrap.sh (OPS_ALLOW_IPS); edit and run: docker compose exec nginx nginx -s reload"
  for ip in $OPS_ALLOW_IPS; do
    [[ $ip =~ ^[0-9a-fA-F:.]+(/[0-9]{1,3})?$ ]] || die "invalid OPS_ALLOW_IPS entry: $ip"
    echo "allow $ip;"
  done
  echo "deny all;"
} >/etc/mhrs/nginx/ops-allowlist.conf
# flower basic auth: empty until the owner adds a user (htpasswd -B /etc/mhrs/nginx/flower.htpasswd ops)
[[ -f /etc/mhrs/nginx/flower.htpasswd ]] || install -m 0644 /dev/null /etc/mhrs/nginx/flower.htpasswd
# nginx upstreams: deploy.sh (as the deploy user) switches them during rolling deploys
install -d -o "$DEPLOY_USER" -g "$DEPLOY_USER" -m 0755 /etc/mhrs/nginx/upstreams
for svc in backend:8000 frontend:3000; do
  f="/etc/mhrs/nginx/upstreams/${svc%%:*}.conf"
  [[ -f $f ]] || printf '# managed by deploy.sh
server %s resolve max_fails=0;
' "$svc" >"$f"
  chown "$DEPLOY_USER:$DEPLOY_USER" "$f"
done
echo "$MHRS_ENVIRONMENT" >/etc/mhrs/environment

log "SSH hardening + firewall (ufw) + fail2ban"
cat >/etc/ssh/sshd_config.d/90-mhrs.conf <<'EOF'
PermitRootLogin no
PasswordAuthentication no
KbdInteractiveAuthentication no
PubkeyAuthentication yes
X11Forwarding no
AllowAgentForwarding no
MaxAuthTries 3
LoginGraceTime 30
ClientAliveInterval 300
ClientAliveCountMax 2
EOF
sshd -t
systemctl try-reload-or-restart ssh
ufw --force reset >/dev/null
ufw default deny incoming
ufw default allow outgoing
ufw allow 80/tcp comment 'http (ACME + redirect)'
ufw allow 443/tcp comment 'https'
if [[ -n $SSH_ALLOW_CIDR ]]; then
  [[ $SSH_ALLOW_CIDR =~ ^[0-9a-fA-F:.]+/[0-9]{1,3}$ ]] || die "SSH_ALLOW_CIDR must be a CIDR, e.g. 203.0.113.10/32"
  ufw allow from "$SSH_ALLOW_CIDR" to any port 22 proto tcp comment 'ssh (restricted)'
else
  echo "port 22 stays closed: use AWS SSM Session Manager"
fi
ufw --force enable
# Docker publishes 80/443 itself (iptables DOCKER chain); ufw covers everything else, and the EC2
# security group is the outer boundary (docs/deployment/AWS_SETUP.md).
cat >/etc/fail2ban/jail.d/mhrs.local <<'EOF'
[DEFAULT]
bantime = 1h
findtime = 10m
maxretry = 5
backend = systemd

[sshd]
enabled = true
EOF
systemctl enable fail2ban
systemctl restart fail2ban

log "AWS CLI v2 (SSM parameters for deploy.sh, S3 backups)"
if ! command -v aws >/dev/null; then
  snap install aws-cli --classic
fi

log "CloudWatch agent (metrics: memory, disk, swap; logs: system + containers)"
if ! dpkg -s amazon-cloudwatch-agent >/dev/null 2>&1; then
  tmp=$(mktemp -d)
  curl -fsSL -o "$tmp/cwagent.deb" "https://amazoncloudwatch-agent.s3.amazonaws.com/ubuntu/${ARCH}/latest/amazon-cloudwatch-agent.deb"
  dpkg -i "$tmp/cwagent.deb"
  rm -rf "$tmp"
fi
CW_CONFIG=/opt/aws/amazon-cloudwatch-agent/etc/mhrs.json
sed "s/__ENV__/${MHRS_ENVIRONMENT}/g" "$REPO_DIR/infrastructure/monitoring/cloudwatch-agent.json" >"$CW_CONFIG"
/opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl -a fetch-config -m ec2 -s -c "file:$CW_CONFIG"

log "Log rotation for host-side MHRS logs (deploy, backups)"
cat >/etc/logrotate.d/mhrs <<'EOF'
/var/log/mhrs/*.log {
  weekly
  rotate 8
  compress
  delaycompress
  missingok
  notifempty
  create 0640 mhrs mhrs
}
EOF
chown "$DEPLOY_USER:$DEPLOY_USER" /var/log/mhrs

log "Done"
cat <<EOF
Host ready for MHRS ($MHRS_ENVIRONMENT).
  docker:   $(docker --version) / $(docker compose version --short)
  time:     $(chronyc -n tracking | awk '/Reference ID/ {print $4, $5}')
  swap:     $(swapon --show=SIZE --noheadings | head -1)
  firewall: $(ufw status | head -1)
Next steps (docs/deployment/AWS_SETUP.md):
  1. Clone the repository into $APP_DIR as $DEPLOY_USER (or let deploy.sh do it).
  2. sudo infrastructure/deployment/certbot.sh issue <domain> <contact-email>
  3. sudo -u $DEPLOY_USER $APP_DIR/infrastructure/deployment/deploy.sh <tag>
EOF
