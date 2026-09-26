#!/bin/bash
# One-command production deployment on a fresh Ubuntu 22.04/24.04 server (x86_64 or ARM64,
# e.g. an Oracle Cloud Always-Free VM). Safe to re-run: it updates and restarts in place.
#
#   curl -fsSL https://raw.githubusercontent.com/<you>/<repo>/main/scripts/deploy-vm.sh | \
#     bash -s -- https://github.com/<you>/<repo>.git you@example.com
#
# Args: <git-repo-url> <email-for-lets-encrypt>
set -euo pipefail
REPO="${1:?git repo url required}"
EMAIL="${2:?e-mail for the HTTPS certificate required}"
DIR="$HOME/netra"

echo "==> Docker"
if ! command -v docker >/dev/null; then
  curl -fsSL https://get.docker.com | sudo sh
  sudo usermod -aG docker "$USER"
fi
sudo systemctl enable --now docker
DOCKER="sudo docker"

echo "==> Swap (protects against out-of-memory kills during image builds)"
if ! swapon --show | grep -q /swapfile; then
  sudo fallocate -l 4G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile && sudo swapon /swapfile
  echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab >/dev/null
fi

echo "==> Host firewall (Oracle Ubuntu images reject everything except SSH by default)"
for rule in "tcp 80" "tcp 443" "tcp 8189" "udp 8189"; do
  set -- $rule
  sudo iptables -C INPUT -p "$1" --dport "$2" -j ACCEPT 2>/dev/null || sudo iptables -I INPUT 5 -p "$1" --dport "$2" -j ACCEPT
done
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq iptables-persistent >/dev/null
sudo netfilter-persistent save >/dev/null

echo "==> Automatic security updates"
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq unattended-upgrades >/dev/null

echo "==> Code"
if [ -d "$DIR/.git" ]; then git -C "$DIR" pull --ff-only; else git clone "$REPO" "$DIR"; fi
cd "$DIR"

echo "==> Configuration"
PUBLIC_IP="$(curl -fsS https://api.ipify.org)"
SITE="$(echo "$PUBLIC_IP" | tr . -).sslip.io"   # free wildcard DNS: resolves to PUBLIC_IP
if [ ! -f .env ]; then ./scripts/gen-env.sh; fi
set_env() { grep -q "^$1=" .env && sed -i "s|^$1=.*|$1=$2|" .env || echo "$1=$2" >> .env; }
set_env SITE_ADDRESS "$SITE"
set_env TLS_MODE "$EMAIL"
set_env PUBLIC_IP "$PUBLIC_IP"
set_env ENVIRONMENT production
chmod 600 .env

echo "==> Start"
$DOCKER compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build --remove-orphans

echo "==> Nightly database backup + weekly image cleanup"
( crontab -l 2>/dev/null | grep -v netra-backup; \
  echo "30 2 * * * cd $DIR && ./scripts/backup.sh >> $HOME/netra-backup.log 2>&1 # netra-backup"; \
  echo "0 4 * * 0 sudo docker image prune -af >/dev/null 2>&1 # netra-backup" ) | crontab -

echo
echo "Netra is starting at https://$SITE  (first start builds images: allow ~10 minutes)"
echo "Accounts: admin / operator / viewer - passwords are in $DIR/.env"
echo "Point the Vercel console at it with:  scripts/configure-vercel.sh $SITE"
