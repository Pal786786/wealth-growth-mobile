#!/bin/sh
# ==============================================================================
# My Funding Bank — Nginx container entrypoint
# ==============================================================================
# 1. Renders /etc/nginx/templates/*.template → /etc/nginx/conf.d/ using the
#    domain variables from .env.prod (only these vars are replaced).
# 2. If a Let's Encrypt certificate does not exist yet for a domain, creates a
#    temporary self-signed one so nginx can boot. deploy/init-letsencrypt.sh
#    then swaps it for a real certificate (marker file: .dummy).
# 3. Reloads nginx every 6 hours so renewed certificates are picked up.
# ==============================================================================
set -eu

: "${DOMAIN_NAME:?DOMAIN_NAME required}"
: "${ADMIN_DOMAIN:?ADMIN_DOMAIN required}"
: "${WEBSITE_DOMAIN:?WEBSITE_DOMAIN required}"

mkdir -p /etc/nginx/conf.d /var/www/certbot
rm -f /etc/nginx/conf.d/default.conf
for tpl in /etc/nginx/templates/*.template; do
    out="/etc/nginx/conf.d/$(basename "$tpl" .template)"
    envsubst '${DOMAIN_NAME} ${ADMIN_DOMAIN} ${WEBSITE_DOMAIN}' < "$tpl" > "$out"
    echo "[entrypoint] rendered $out"
done

for d in "$DOMAIN_NAME" "$ADMIN_DOMAIN" "$WEBSITE_DOMAIN"; do
    live="/etc/letsencrypt/live/$d"
    if [ ! -f "$live/fullchain.pem" ]; then
        echo "[entrypoint] no certificate for $d yet — creating temporary self-signed cert"
        mkdir -p "$live"
        openssl req -x509 -nodes -newkey rsa:2048 -days 7 \
            -keyout "$live/privkey.pem" -out "$live/fullchain.pem" \
            -subj "/CN=$d" >/dev/null 2>&1
        touch "$live/.dummy"
    fi
done

# Pick up renewed certificates
( while :; do sleep 21600; nginx -s reload 2>/dev/null || true; done ) &

nginx -t
exec nginx -g 'daemon off;'
