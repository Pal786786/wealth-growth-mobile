#!/usr/bin/env bash
# ==============================================================================
# Initial Let's Encrypt certificate acquisition.
# Run ONCE after DNS records point to this server.
#
# Usage:
#   DOMAIN_NAME=app.myfundingbank.in \
#   ADMIN_DOMAIN=admin.myfundingbank.in \
#   CERTBOT_EMAIL=ops@myfundingbank.in \
#   bash certbot-init.sh
# ==============================================================================
set -euo pipefail

: "${DOMAIN_NAME:?DOMAIN_NAME required}"
: "${ADMIN_DOMAIN:?ADMIN_DOMAIN required}"
: "${CERTBOT_EMAIL:?CERTBOT_EMAIL required}"

mkdir -p /var/www/certbot

for DOMAIN in "$DOMAIN_NAME" "$ADMIN_DOMAIN"; do
    echo "[certbot-init] Requesting cert for $DOMAIN ..."
    certbot certonly \
        --webroot -w /var/www/certbot \
        --email "$CERTBOT_EMAIL" \
        --agree-tos --no-eff-email \
        --keep-until-expiring \
        -d "$DOMAIN"
done

echo "[certbot-init] All certificates acquired. Reloading nginx..."
nginx -s reload || true
