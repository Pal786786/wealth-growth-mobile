#!/usr/bin/env bash
# ==============================================================================
# My Funding Bank — one-time VPS setup (Ubuntu 22.04 / 24.04, run as root)
# ==============================================================================
# What it does:
#   1. Installs Docker, git, firewall (ports 22, 80, 443 only)
#   2. Adds 2 GB swap if the server has less than 4 GB RAM and no swap
#   3. Creates .env.prod with strong random secrets + your domains
#   4. Builds and starts everything (MongoDB, backend, admin, website, nginx)
#   5. Gets free SSL certificates from Let's Encrypt
#
# Usage (from inside the cloned repo, e.g. /opt/mfb):
#     sudo bash deploy/setup-vps.sh
# Safe to run again: it never overwrites an existing .env.prod.
# ==============================================================================
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then echo "Run as root: sudo bash deploy/setup-vps.sh"; exit 1; fi
cd "$(dirname "$0")/.."
REPO_DIR="$(pwd)"
ENV_FILE=".env.prod"
DC="docker compose -f deploy/docker-compose.prod.yml --env-file $ENV_FILE"

step() { echo; echo "================ $* ================"; }

# ---------------------------------------------------------------- 1. packages
step "1/5 Installing Docker + basics"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq ca-certificates curl git ufw openssl python3 >/dev/null
if ! command -v docker >/dev/null 2>&1; then
    curl -fsSL https://get.docker.com | sh
fi
systemctl enable --now docker
docker compose version

# Port 80/443 must be free for our nginx container
for svc in nginx apache2 httpd caddy; do
    if systemctl is-active --quiet "$svc" 2>/dev/null; then
        echo "WARNING: '$svc' is running on this server and uses port 80/443."
        read -rp "Stop and disable $svc? [y/N] " ans
        if [[ "$ans" =~ ^[Yy]$ ]]; then systemctl disable --now "$svc"; else echo "Cannot continue while $svc holds port 80/443."; exit 1; fi
    fi
done

ufw allow OpenSSH >/dev/null
ufw allow 80/tcp >/dev/null
ufw allow 443/tcp >/dev/null
ufw --force enable >/dev/null
echo "Firewall: only SSH, 80, 443 open."

# ---------------------------------------------------------------- 2. swap
step "2/5 Memory check"
MEM_MB=$(awk '/MemTotal/{print int($2/1024)}' /proc/meminfo)
echo "RAM: ${MEM_MB} MB"
if [ "$MEM_MB" -lt 4000 ] && [ "$(swapon --show | wc -l)" -eq 0 ]; then
    echo "Adding 2 GB swap (needed to build the website/admin on small servers)"
    fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile >/dev/null && swapon /swapfile
    grep -q '/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

# ---------------------------------------------------------------- 3. env
step "3/5 Configuration (.env.prod)"
if [ -f "$ENV_FILE" ]; then
    echo "$ENV_FILE already exists — keeping it."
else
    cp .env.prod.example "$ENV_FILE"
    read -rp "API domain (mobile app uses this), e.g. api.myfundingbank.in : " D_API
    read -rp "Admin panel domain, e.g. admin.myfundingbank.in            : " D_ADMIN
    read -rp "Website domain, e.g. myfundingbank.in                       : " D_WEB
    read -rp "Email for SSL notices                                       : " D_EMAIL

    JWT=$(openssl rand -hex 32)
    MONGO_PW=$(openssl rand -hex 20)
    KYC_KEY=$(python3 -c 'import base64,os;print(base64.urlsafe_b64encode(os.urandom(32)).decode())')

    setv() { # setv KEY VALUE  — replace KEY=... line in .env.prod
        python3 - "$ENV_FILE" "$1" "$2" <<'PY'
import sys,re
f,k,v=sys.argv[1:]
s=open(f).read()
s=re.sub(rf'^{k}=.*$', f'{k}={v}', s, flags=re.M)
open(f,'w').write(s)
PY
    }
    setv DOMAIN_NAME "$D_API"
    setv ADMIN_DOMAIN "$D_ADMIN"
    setv WEBSITE_DOMAIN "$D_WEB"
    setv CERTBOT_EMAIL "$D_EMAIL"
    setv FRONTEND_ORIGIN "https://$D_WEB"
    setv APP_URL "https://$D_WEB"
    setv REFERRAL_BASE_URL "https://$D_WEB"
    setv JWT_SECRET "$JWT"
    setv MONGO_ROOT_PASSWORD "$MONGO_PW"
    setv KYC_ENCRYPTION_KEY "$KYC_KEY"
    chmod 600 "$ENV_FILE"
    echo "Created $ENV_FILE with random secrets."
    echo "Add API keys (Razorpay, MSG91, EMERGENT_LLM_KEY, ...) later with:  nano $REPO_DIR/$ENV_FILE"
    echo "IMPORTANT: back up $ENV_FILE somewhere safe (KYC_ENCRYPTION_KEY cannot be recovered)."
fi

# ---------------------------------------------------------------- 4. start
step "4/5 Building and starting containers (first build takes 5-15 min)"
$DC up -d --build
echo "Waiting for backend to become healthy..."
for i in $(seq 1 40); do
    status=$(docker inspect -f '{{.State.Health.Status}}' mfb_backend 2>/dev/null || echo starting)
    [ "$status" = "healthy" ] && break
    sleep 5
done
$DC ps

# ---------------------------------------------------------------- 5. ssl
step "5/5 SSL certificates"
bash deploy/init-letsencrypt.sh || true

set -a; . "./$ENV_FILE"; set +a
echo
echo "============================================================"
echo " Setup finished."
echo "   API      : https://$DOMAIN_NAME/api/health/live"
echo "   Admin    : https://$ADMIN_DOMAIN"
echo "   Website  : https://$WEBSITE_DOMAIN"
echo
echo " NEXT: log into admin and CHANGE the default admin password"
echo "       (default seeded user: admin@mfb.in)."
echo " Future updates:  bash deploy/update.sh"
echo "============================================================"
