# My Funding Bank — Beta Release Checklist

_A gate that MUST be passed before enabling public beta signups._

---

## 🔐 Security

- [ ] `.env.prod` created with production-grade secrets (no placeholders)
- [ ] `validate_env.py` returns exit code 0
- [ ] All third-party keys rotated at least once and stored in a secure secret manager
- [ ] MongoDB `security.authorization: enabled`
- [ ] JWT secret ≥ 32 chars, generated via `openssl rand -hex 32`
- [ ] TLS certificates issued for `app.<domain>` and `admin.<domain>`; HSTS enabled
- [ ] `docker compose logs nginx` shows TLS 1.2/1.3 handshakes only
- [ ] Rate limits verified (Postman/hey) — abusive traffic returns 429
- [ ] Gitleaks scan passes on `main`
- [ ] Trivy image scan: 0 CRITICAL, 0 HIGH (or documented waivers)
- [ ] Bandit SAST report reviewed
- [ ] Password reset and OTP flows tested end-to-end

## 🧪 Quality

- [ ] Full pytest regression suite (799+ tests) passing on the release commit
- [ ] Admin panel smoke: login → dashboard → finance → KYC screens load
- [ ] Mobile smoke on Android + iOS (login, wallet, KYC, payment, withdrawal, gold, MF)
- [ ] Load test: 100 rps for 5 minutes with < 1% error rate
- [ ] p95 latency for critical endpoints < 500 ms

## 📊 Data & Backups

- [ ] Indexes created (`ensure_indexes.py --report` shows 0 errors)
- [ ] First backup taken and verified via `mongo_restore.sh` into a scratch DB
- [ ] Backup cron enabled (default 02:00 UTC daily)
- [ ] Retention policy set (`BACKUP_RETENTION_DAYS=30` recommended)
- [ ] S3 backup destination configured (or explicitly documented as “local only”)
- [ ] Encrypted backup passphrase stored in secret manager (if `BACKUP_ENCRYPT=true`)

## 🛠️ Ops & Monitoring

- [ ] Prometheus + Grafana deployed OR JSON `/api/health/summary` dashboard bookmarked
- [ ] All 7 Grafana dashboards render data
- [ ] Prometheus rules loaded (`amtool check-rules` clean)
- [ ] Alertmanager receiver (email/Slack/PagerDuty) configured for CRITICAL alerts
- [ ] `docker compose ps` shows every service `healthy`
- [ ] Log rotation enabled (`docker system df` shows sane log sizes)
- [ ] Automatic restart on crash verified (`docker kill mfb_backend` → restarts)

## 🔄 CI/CD

- [ ] `.github/workflows/ci.yml` green on main
- [ ] `.github/workflows/deploy.yml` production environment requires manual approval (repo setting)
- [ ] All GitHub Secrets set: `STAGING_HOST`, `STAGING_SSH_KEY`, `PROD_HOST`, `PROD_SSH_KEY`
- [ ] Release tag `v1.0.0-beta.1` created

## 📚 Documentation

- [ ] Production Deployment Guide reviewed by 2 engineers
- [ ] Rollback Procedure dry-run performed on staging
- [ ] Security Audit + Performance Audit signed off
- [ ] Known Limitations document published to internal wiki
- [ ] On-call rotation defined and pager tested

## 🎉 Beta launch actions

- [ ] Feature flag `PUBLIC_SIGNUPS_ENABLED=true`
- [ ] Support inbox (`support@myfundingbank.in`) monitored
- [ ] Incident channel created (Slack `#mfb-incident`)
- [ ] Communications draft ready for beta users (whitelist / invitation email)
- [ ] Analytics baseline snapshot taken (users, wallet balance, KYC completion)

---

**Approval signatures**

| Role                | Name | Date | Signature |
|---------------------|------|------|-----------|
| Engineering Lead    |      |      |           |
| DevOps / SRE        |      |      |           |
| Security Reviewer   |      |      |           |
| Product Owner       |      |      |           |
