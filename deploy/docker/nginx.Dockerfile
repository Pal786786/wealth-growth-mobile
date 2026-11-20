# ==============================================================================
# My Funding Bank — Nginx reverse proxy + marketing website
# ==============================================================================
# Stage 1 builds the Next.js marketing website (static export → /build/out).
# Stage 2 is nginx: API + admin proxy, website static files, TLS.
# ==============================================================================

FROM node:20-alpine AS website
WORKDIR /build
COPY website/package.json website/package-lock.json* ./
RUN if [ -f package-lock.json ]; then npm ci --no-audit --no-fund; else npm install --no-audit --no-fund; fi
COPY website/ ./
RUN rm -rf out .next && npm run build

FROM nginx:1.27-alpine
RUN apk add --no-cache curl tini openssl gettext
COPY deploy/nginx/nginx.conf /etc/nginx/nginx.conf
COPY deploy/nginx/snippets/ /etc/nginx/snippets/
COPY deploy/nginx/templates/ /etc/nginx/templates/
COPY deploy/nginx/entrypoint.sh /usr/local/bin/mfb-nginx-entrypoint.sh
COPY --from=website /build/out /usr/share/nginx/website
RUN chmod +x /usr/local/bin/mfb-nginx-entrypoint.sh && rm -f /etc/nginx/conf.d/default.conf
EXPOSE 80 443
ENTRYPOINT ["/sbin/tini", "--"]
CMD ["/usr/local/bin/mfb-nginx-entrypoint.sh"]
