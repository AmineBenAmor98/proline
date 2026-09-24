#!/bin/bash
# Runs once, as root, on first boot. Everything here is true of any rebuild of
# this box: the OS packages, swap, Docker, and the directory the deploy expects.
#
# WHAT IS NOT HERE: /srv/proline/.env and /srv/proline/.env.backup, and the
# database password. User data is readable from the instance metadata endpoint by
# anything running on the box, and it is stored in plain text in the Pulumi
# stack. Secrets go in over SSH, once, by hand -- see infra/DEPLOY.md.
#
# Output lands in /var/log/cloud-init-output.log. If the deploy fails, read that
# before anything else.
set -euxo pipefail

export DEBIAN_FRONTEND=noninteractive

apt-get update
apt-get install -y ca-certificates curl gnupg unattended-upgrades

# 2 GB with no swap gets OOM-killed during the image build. This is the whole
# reason the $7 bundle is not enough and the $12 one is.
if [ ! -f /swapfile ]; then
	fallocate -l 2G /swapfile
	chmod 600 /swapfile
	mkswap /swapfile
	swapon /swapfile
	echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

# Docker from Docker's own repository. Ubuntu's packaged docker.io has no
# compose v2, and `docker compose` is what the deploy command uses.
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
	-o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
. /etc/os-release
cat > /etc/apt/sources.list.d/docker.list <<EOF
deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu ${VERSION_CODENAME} stable
EOF

apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
usermod -aG docker ubuntu

# Docker's default logging grows without bound, and this disk also holds the
# database. A full disk is the failure that takes both the site and the backup.
cat > /etc/docker/daemon.json <<'EOF'
{
  "log-driver": "json-file",
  "log-opts": { "max-size": "10m", "max-file": "3" }
}
EOF
systemctl restart docker

# Security updates apply themselves. Nobody logs into this box for months at a
# time, which is exactly when an unpatched OpenSSL matters.
cat > /etc/apt/apt.conf.d/20auto-upgrades <<'EOF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
EOF

install -d -o ubuntu -g ubuntu /srv/proline

echo "user-data finished at $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
