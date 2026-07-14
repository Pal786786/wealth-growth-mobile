# My Funding Bank — Rollback Procedure

_Applies to every production release. Print this and keep at reach during deploys._

---

## 1. When to roll back

Roll back **immediately** if any of the following occur within 60 minutes of a deploy:

1. Smoke test fails (`scripts/deploy/smoke_test.sh` non-zero)
2. 5xx error rate > 5% for > 5 minutes (Grafana “API Performance”)
3. Auth or payments succeed rate drops ≥ 15% below the 24-hour baseline
4. Mongo write failures or replica set replication stops
5. Critical finance alert (`mfb_finance_alerts{severity="critical"}`) newly firing after deploy

Otherwise, prefer a **forward fix** with a hotfix release (see § 5).

---

## 2. Fast rollback (image swap only)

Assumes DB schema is backwards-compatible (default for MFB).

```bash
cd /opt/mfb
LAST_GOOD=$(cat .last_good_tag)
echo "Rolling back to $LAST_GOOD"
IMAGE_TAG=$LAST_GOOD docker compose -f deploy/docker-compose.prod.yml \
                                    --env-file .env.prod up -d backend admin
BASE_URL=https://app.<domain> bash scripts/deploy/smoke_test.sh
```

**Expected duration:** 60–90 seconds.

The CI/CD deploy pipeline **automatically** triggers this on smoke-test failure (see `deploy.yml`, job `deploy_production` → `Rollback on failure`).

---

## 3. Full rollback with data restore

Only perform if the migration corrupted or destroyed data.

```bash
# 3.1 Stop write traffic
docker compose -f deploy/docker-compose.prod.yml stop backend admin

# 3.2 List available backups
ls -lh /var/lib/docker/volumes/mfb_mongo_backups/_data/

# 3.3 Restore
docker compose -f deploy/docker-compose.prod.yml run --rm backup \
   /usr/local/bin/mongo_restore.sh /backups/mfb_mfb_prod_<STAMP>.tar.gz
# add DROP_BEFORE_RESTORE=true env if you must overwrite

# 3.4 Swap image back to previous good tag
LAST_GOOD=$(cat .last_good_tag)
IMAGE_TAG=$LAST_GOOD docker compose -f deploy/docker-compose.prod.yml \
                                    --env-file .env.prod up -d backend admin

# 3.5 Smoke test + reconciliation
BASE_URL=https://app.<domain> bash scripts/deploy/smoke_test.sh
curl -s $BASE_URL/api/health | jq
```

**Expected duration:** 10–25 minutes depending on DB size.

---

## 4. Communication template

> **INCIDENT: Rollback in progress**
> • Release: `v1.x.y`  →  reverted to `v1.x.(y-1)`
> • Detected at: `<HH:MM UTC>`
> • Rolled back at: `<HH:MM UTC>`
> • Trigger: `<smoke test 500s / error-rate alert / manual>`
> • Impact: `<functionality / user count>`
> • Next update: `+30 min` on `#mfb-incident`

Post-mortem to be filed within 48 hours (Google Doc template in Confluence).

---

## 5. Forward fix (preferred)

1. `git checkout -b hotfix/<issue> v1.x.y`
2. Fix, add regression test, run `pytest`.
3. Tag `v1.x.(y+1)` and follow normal deploy pipeline.
4. Cherry-pick to `main`.

---

## 6. Verification after any rollback

- [ ] `docker compose ps` → every service `healthy`
- [ ] `/api/health` returns `"status": "healthy"`
- [ ] `/api/health/summary` → mongo_latency_ms < 20
- [ ] Grafana error-rate panel returns to baseline within 15 min
- [ ] Finance reconciliation returns clean on next scheduled run
- [ ] Support / on-call notified that traffic is normalised

---

## 7. Automation reference

The production deploy job (`deploy.yml`) writes `.last_good_tag` upon a successful smoke test. That file is the single source of truth for the fast-rollback command. Never delete it manually.
