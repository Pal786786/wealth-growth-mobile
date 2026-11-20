#!/usr/bin/env bash
# ==============================================================================
# My Funding Bank — get real Let's Encrypt SSL certificates
# ==============================================================================
# Run from the repo root AFTER the stack is up and DNS for all three domains
# points to this server:
#     bash deploy/init-letsencrypt.sh            # real certificates
#     STAGING=1 bash deploy/init-letsencrypt.sh  # test certificates (no rate limit)
#
# On first boot nginx creates temporary self-signed certs (marked with .dummy).
# This script replaces only those; domains that already have a real
# certificate are skipped. Renewal is automatic (certbot container + nginx
# reloads every 6h).
# ==============================================================================
set -euo pipefail

cd "$(dirname "$0")/.."
ENV_FILE=".env.prod"
[ -f "$ENV_FILE" ] || { echo "ERROR: $ENV_FILE not found in $(pwd)"; exit 1; }
set -a; . "./$ENV_FILE"; set +a

DC="docker compose -f deploy/docker-compose.prod.yml --env-file $ENV_FILE"
STAGING_FLAG=""
[ "${STAGING:-0}" = "1" ] && STAGING_FLAG="--staging"

SERVER_IP="$(curl -fsS4 https://api.ipify.org || true)"

for DOMAIN in "$DOMAIN_NAME" "$ADMIN_DOMAIN" "$WEBSITE_DOMAIN"; do
    echo
    echo "==> $DOMAIN"

    DNS_IP="$(getent ahostsv4 "$DOMAIN" | awk 'NR==1{print $1}' || true)"
    if [ -n "$SERVER_IP" ] && [ "$DNS_IP" != "$SERVER_IP" ]; then
        echo "   SKIP: $DOMAIN points to '${DNS_IP:-nothing}', this server is $SERVER_IP."
        echo "   Fix the DNS A record, wait a few minutes, and run this script again."
        continue
    fi

    if ! $DC exec -T nginx test -f "/etc/letsencrypt/live/$DOMAIN/.dummy"; then
        echo "   already has a real certificate — skipping"
        continue
    fi

    echo "   removing temporary certificate"
    $DC run --rm --entrypoint sh certbot -c \
        "rm -rf /etc/letsencrypt/live/$DOMAIN /etc/letsencrypt/archive/$DOMAIN /etc/letsencrypt/renewal/$DOMAIN.conf"

    echo "   requesting Let's Encrypt certificate"
    if ! $DC run --rm --entrypoint certbot certbot certonly \
            --webroot -w /var/www/certbot \
            -d "$DOMAIN" \
            --email "$CERTBOT_EMAIL" \
            --agree-tos --no-eff-email --non-interactive \
            --rsa-key-size 4096 $STAGING_FLAG; then
        echo "   FAILED for $DOMAIN — restoring a temporary certificate so nginx keeps running"
        $DC restart nginx
        continue
    fi
done

echo
echo "==> reloading nginx"
$DC exec -T nginx nginx -s reload
echo "Done."
