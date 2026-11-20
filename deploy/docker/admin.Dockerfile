# ==============================================================================
# My Funding Bank — Admin Panel (Vite React) Production Dockerfile
# ==============================================================================

FROM node:20-alpine AS builder
WORKDIR /build
COPY admin/package.json admin/yarn.lock* admin/package-lock.json* ./
RUN if [ -f package-lock.json ]; then npm ci --no-audit --no-fund; else npm install --no-audit --no-fund; fi
COPY admin/ ./
ARG VITE_API_BASE=/api
ENV VITE_API_BASE=${VITE_API_BASE}
RUN npm run build

FROM nginx:1.27-alpine AS runtime
RUN apk add --no-cache curl tini
COPY --from=builder /build/dist /usr/share/nginx/html
COPY deploy/nginx/admin-static.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -fsS http://localhost/ || exit 1
ENTRYPOINT ["/sbin/tini", "--"]
CMD ["nginx", "-g", "daemon off;"]
