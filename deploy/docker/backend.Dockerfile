# ==============================================================================
# My Funding Bank — Backend (FastAPI) Production Dockerfile
# ==============================================================================
# Multi-stage build: small runtime image, non-root user, pre-compiled deps.
# ==============================================================================

FROM python:3.11-slim AS builder

WORKDIR /build
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_EXTRA_INDEX_URL=https://d33sy5i8bnduwe.cloudfront.net/simple/
# ^ `emergentintegrations` (used by the AI features) is NOT on PyPI; it is
#   published on Emergent's package index above.

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential gcc libffi-dev libssl-dev curl \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt ./
RUN pip wheel --wheel-dir /wheels -r requirements.txt gunicorn uvicorn[standard] prometheus-client

# ----- runtime -----
FROM python:3.11-slim AS runtime

ARG APP_UID=10001
ARG APP_GID=10001

RUN groupadd -g ${APP_GID} mfb && useradd -u ${APP_UID} -g ${APP_GID} -m -s /bin/bash mfb

RUN apt-get update && apt-get install -y --no-install-recommends \
        curl tini ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY --from=builder /wheels /wheels
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir --no-index --find-links=/wheels -r requirements.txt gunicorn uvicorn[standard] prometheus-client \
    && rm -rf /wheels

COPY --chown=mfb:mfb backend/ /app/backend/
COPY --chown=mfb:mfb scripts/deploy/ /app/scripts/deploy/

USER mfb
WORKDIR /app/backend

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/backend \
    WEB_CONCURRENCY=4 \
    GUNICORN_TIMEOUT=60 \
    PROMETHEUS_MULTIPROC_DIR=/tmp/prom_multiproc \
    LOG_LEVEL=info

EXPOSE 8001

HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -fsS http://localhost:8001/api/health/live || exit 1

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["sh", "-c", "mkdir -p $PROMETHEUS_MULTIPROC_DIR && gunicorn server:app \
    --workers ${WEB_CONCURRENCY:-4} \
    --worker-class uvicorn.workers.UvicornWorker \
    --bind 0.0.0.0:8001 \
    --timeout ${GUNICORN_TIMEOUT:-60} \
    --graceful-timeout 30 \
    --keep-alive 5 \
    --access-logfile - \
    --error-logfile - \
    --log-level ${LOG_LEVEL:-info}"]
