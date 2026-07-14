# Sprint 13 — Production Deployment & Beta Release

This directory contains the complete deployment package delivered by Sprint 13. All items are **infrastructure, monitoring, CI/CD and documentation** — zero business-feature changes were introduced.

---

## What was delivered

### `deploy/` — Runtime infrastructure
- `docker/` — Backend, Admin, Nginx Dockerfiles (multi-stage, non-root)
- `docker-compose.prod.yml` — Full stack: backend + admin + Mongo + nginx + certbot + backup
- `docker-compose.monitoring.yml` — Optional Prometheus + Grafana + node/mongo/cAdvisor exporters
- `nginx/` — Reverse proxy, TLS (Let's Encrypt), rate limits, security headers
- `supervisor/supervisord.prod.conf` — Bare-metal alternative
- `logrotate/mfb` — 30-day rotation for backend, nginx, mongodb, backup logs
- `mongo/mongod.conf` — Production Mongo config (SCRAM-SHA-256, WiredTiger tuning)
- `.env.prod.example` — Template with every required + optional variable
- `prometheus/` — Scrape config + 12 alerting rules
- `grafana/` — Auto-provisioned datasource + **7 dashboards**

### `scripts/deploy/` — Operational scripts
- `validate_env.py` — Refuses to boot with placeholder or missing secrets
- `ensure_indexes.py` — 43 idempotent indexes across 14 collections
- `mongo_backup.sh` — Encrypted (optional) + S3-compatible upload
- `mongo_restore.sh` — Local or S3 source, with `DROP_BEFORE_RESTORE` safety
- `crash_recovery.sh` — Guided incident recovery
- `smoke_test.sh` — 30-second post-deploy verification

### `backend/health_monitoring.py` — Backend module
- `/api/health/live`   — liveness (fastest)
- `/api/health/ready`  — readiness (Mongo ping, 503 on failure)
- `/api/health`        — deep JSON (Mongo/CPU/mem/disk + business counters)
- `/api/health/summary`— lightweight JSON dashboard payload (kept as requested)
- `/api/metrics`       — Prometheus exposition (12 base metrics + custom counters)

### `.github/workflows/` — CI/CD
- `ci.yml` — lint → unit → integration → full regression → security (Bandit, pip-audit, Gitleaks, Trivy)
- `deploy.yml` — build + push images → staging → **manual approval** → production → smoke test → **auto-rollback on failure** → release notes

### `docs/deployment/` — Guides & certificates
- `PRODUCTION_DEPLOYMENT_GUIDE.md` — Full first-time & rolling deploy runbook
- `BETA_RELEASE_CHECKLIST.md` — Gate before public beta
- `ROLLBACK_PROCEDURE.md` + `ROLLBACK_PLAN.md` — Tactical + strategic rollback
- `SECURITY_AUDIT.md` — 22-line control matrix + open follow-ups
- `PERFORMANCE_AUDIT.md` — Latency/throughput baseline + SLOs
- `MONITORING_SETUP.md` — Metrics catalogue + dashboards + alerting
- `BACKUP_RESTORE.md` — Manual/scheduled backups, S3, restore drill
- `DEPLOYMENT_CHECKLIST.md` — Every-release short checklist
- `KNOWN_LIMITATIONS.md` — Public disclosure list
- `FINAL_RELEASE_CERTIFICATION.md` — Sign-off form
- `FINAL_REGRESSION_REPORT.md` — 800 tests / 798 passing / 2 skipped

---

## Quick verification (in this pod)

```bash
# YAML/JSON validity
python -c "import yaml; yaml.safe_load(open('deploy/docker-compose.prod.yml'))"

# Health endpoints on the running backend
curl -s localhost:8001/api/health/live
curl -s localhost:8001/api/health/ready
curl -s localhost:8001/api/health/summary | jq
curl -s localhost:8001/api/metrics | head -20

# Env validator (warn-only against current pod env)
python scripts/deploy/validate_env.py --warn-only

# Full regression
cd backend && python -m pytest tests/ -q
# → 798 passed, 2 skipped in ~12 min
```

---

## Release certification

| Signal                              | Result   |
|-------------------------------------|----------|
| Full regression                     | ✅ 798/798 (100% executable) |
| Docker Compose validity              | ✅       |
| Prometheus/Grafana validity          | ✅       |
| Backend health + metrics live         | ✅       |
| Mongo indexes ensured (43)            | ✅       |
| Env validator runs                    | ✅       |

**Go / No-Go:** ✅ **GO for beta** – see `docs/deployment/FINAL_RELEASE_CERTIFICATION.md` for sign-off.
