# My Funding Bank — Production Deployment Guide

**Version:** 1.0 (Sprint 13)  
**Audience:** DevOps / SRE / Release Manager  
**Estimated deployment time:** 45–60 min (fresh install), 5–10 min (rolling update)

---

## 0. Overview

The MFB platform consists of:

| Component        | Technology         | Port (internal)    | Deployable Container |
|------------------|-------------------|--------------------|----------------------|
| Backend API      | FastAPI + Gunicorn (Uvicorn workers) | 8001 | `mfb/backend`        |
| Admin Panel      | Vite (static SPA)  | 80                 | `mfb/admin`          |
| Mobile           | Expo (SDK 54)      | – (built + shipped separately) | –         |
| Database         | MongoDB 7.0        | 27017              | `mongo:7.0`          |
| Reverse Proxy    | Nginx + certbot    | 80/443             | `mfb/nginx`          |
| Backups          | mongodump + cron   | –                  | `mfb_backup`         |
| Monitoring (opt) | Prometheus, Grafana, node/mongo exporters, cAdvisor | 9090/3001 | optional |

All services are orchestrated by **Docker Compose** (`deploy/docker-compose.prod.yml`). A **Supervisor** alternative exists for bare-metal VMs.

---

## 1. Prerequisites

### 1.1 Server sizing (recommended)

| Environment | CPU | RAM  | Disk (SSD) | Notes                          |
|-------------|-----|------|-----------|--------------------------------|
| Staging     | 2   | 4 GB | 40 GB      | Single node                     |
| Production  | 4   | 8 GB | 100 GB     | Enable weekly disk-usage report |
| DB (opt.)   | 2   | 8 GB | 200 GB     | Separate node for Mongo (HA)    |

### 1.2 Software

- Ubuntu 22.04 LTS (or any Docker-supported Linux)
- Docker Engine ≥ 24.0 and Docker Compose Plugin ≥ 2.20
- `git`, `curl`, `openssl`
- DNS records pointing to server IP for both `app.<domain>` and `admin.<domain>`
- Ports **80** and **443** open to the internet

### 1.3 Secrets you must prepare

| Secret | Where used | How to generate |
|--------|------------|-----------------|
| `JWT_SECRET`               | Backend token signing         | `openssl rand -hex 32` |
| `MONGO_ROOT_PASSWORD`      | MongoDB auth                  | `openssl rand -base64 24` |
| `GRAFANA_ADMIN_PASSWORD`   | Grafana login                 | `openssl rand -base64 18` |
| `BACKUP_ENCRYPT_PASSPHRASE` | GPG symmetric key (optional) | `openssl rand -base64 32` |
| Third-party keys           | Razorpay, Cashfree, TwelveData, Emergent LLM | From provider dashboards |

---

## 2. First-time deployment

### 2.1 Clone & prepare

```bash
ssh deploy@<your-server>
sudo mkdir -p /opt/mfb && sudo chown $USER: /opt/mfb
cd /opt/mfb
git clone <repo-url> .
cp deploy/.env.prod.example .env.prod
$EDITOR .env.prod                       # fill in real values
```

### 2.2 Validate configuration

```bash
python3 scripts/deploy/validate_env.py       # errors are fatal
```

### 2.3 Bootstrap TLS certificates (Let's Encrypt)

```bash
# Bring stack up on HTTP first so certbot can complete the ACME challenge
docker compose -f deploy/docker-compose.prod.yml --env-file .env.prod up -d nginx

docker compose -f deploy/docker-compose.prod.yml --env-file .env.prod \
  run --rm nginx /usr/local/bin/certbot-init.sh

# Then switch to full TLS-serving nginx (compose profile 'tls')
docker compose -f deploy/docker-compose.prod.yml --env-file .env.prod \
  --profile tls up -d
```

### 2.4 Start the full stack

```bash
docker compose -f deploy/docker-compose.prod.yml --env-file .env.prod up -d
docker compose -f deploy/docker-compose.prod.yml ps       # verify all healthy
```

### 2.5 Create indexes

```bash
docker compose -f deploy/docker-compose.prod.yml exec backend \
  python /app/scripts/deploy/ensure_indexes.py --report
```

### 2.6 Post-deploy smoke test

```bash
BASE_URL=https://app.<domain> bash scripts/deploy/smoke_test.sh
```

### 2.7 (Optional) Enable monitoring

```bash
docker compose -f deploy/docker-compose.prod.yml \
               -f deploy/docker-compose.monitoring.yml \
               --profile monitoring --env-file .env.prod up -d
```

Grafana is served on `http://127.0.0.1:3001` (bind it behind your VPN or add an Nginx vhost).

---

## 3. Rolling updates

```bash
cd /opt/mfb
git fetch --tags && git checkout v1.x.y
IMAGE_TAG=v1.x.y docker compose -f deploy/docker-compose.prod.yml --env-file .env.prod pull
scripts/deploy/mongo_backup.sh          # take a pre-deploy backup
IMAGE_TAG=v1.x.y docker compose -f deploy/docker-compose.prod.yml --env-file .env.prod up -d
BASE_URL=https://app.<domain> bash scripts/deploy/smoke_test.sh
```

Zero-downtime updates: Gunicorn (workers=4) allows one-worker-at-a-time reload via `docker compose kill -s HUP backend` when only code changes.

---

## 4. Alternative: Supervisor deployment (bare-metal VM)

1. Install Python 3.11, Nginx, MongoDB 7.0 on the host.
2. Copy `deploy/supervisor/supervisord.prod.conf` to `/etc/supervisor/conf.d/mfb.conf`.
3. Copy `deploy/nginx/nginx.conf` and `deploy/nginx/conf.d/mfb.conf` into `/etc/nginx/`.
4. Deploy code to `/opt/mfb/backend` and create the venv at `/opt/mfb/venv`.
5. `supervisorctl reread && supervisorctl update && supervisorctl status`.

---

## 5. Backups (see `BACKUP_RESTORE.md`)

- **Default:** encrypted (optional) local backups at `/backups`, retention 30 days.
- **S3-compatible upload:** set `BACKUP_STORAGE=s3` and populate S3 variables in `.env.prod`.
- **Manual backup:** `docker compose exec backup /usr/local/bin/mongo_backup.sh`.
- **Restore:** `docker compose exec backup /usr/local/bin/mongo_restore.sh <file>` (see doc).

---

## 6. Logging & log rotation

- All containers use JSON file driver with 20 MB rotation (7 files).
- Host-side rotation for bare-metal: copy `deploy/logrotate/mfb` to `/etc/logrotate.d/mfb`.
- Nginx access + backend gunicorn logs are STDOUT and captured by Docker.

---

## 7. Monitoring & alerting

See `MONITORING_SETUP.md`. Endpoints exposed by backend:

| Endpoint                    | Purpose                     |
|-----------------------------|-----------------------------|
| `GET /api/health/live`      | Liveness (fast)             |
| `GET /api/health/ready`     | Readiness (DB check)        |
| `GET /api/health`           | Full JSON snapshot          |
| `GET /api/health/summary`   | Lightweight dashboard JSON  |
| `GET /api/metrics`          | Prometheus scrape endpoint  |

---

## 8. Rollback

See `ROLLBACK_PROCEDURE.md` and `ROLLBACK_PLAN.md`. In brief:

```bash
cat .last_good_tag                            # previous known-good tag
IMAGE_TAG=<previous-tag> docker compose -f deploy/docker-compose.prod.yml \
                                     --env-file .env.prod up -d
```

---

## 9. Security (see `SECURITY_AUDIT.md`)

- Non-root containers (`mfb:10001`), read-only where possible.
- Strict TLS 1.2/1.3, HSTS, rate limits (30 req/s general, 5 req/s on auth).
- MongoDB `authorization: enabled` + SCRAM-SHA-256.
- Env variable validator refuses to start if placeholder secrets are present in production.
- Gitleaks + Trivy + Bandit + pip-audit in CI.

---

## 10. Post-deployment checklist

Use `BETA_RELEASE_CHECKLIST.md` — do not proceed to public launch without ticking every box.

---

## 11. Support runbook quick-reference

- Everything down? → `bash scripts/deploy/crash_recovery.sh`
- 5xx spike?      → Grafana “API Performance” dashboard + `docker compose logs --tail=200 backend`
- Slow DB?         → `mongo_ping_seconds` panel; check `/api/health`
- Disk full?       → `docker system prune -a`; verify `/backups` retention
