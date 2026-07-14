# My Funding Bank — Deployment Checklist (Every Release)

_A trimmed operational checklist for standard rolling releases. For the first-ever production launch, use `BETA_RELEASE_CHECKLIST.md` instead._

---

## Pre-deploy

- [ ] Release tag created (`git tag vX.Y.Z`)
- [ ] Change log reviewed in the PR merged into `main`
- [ ] Full CI pipeline green (`ci.yml`) on the tag
- [ ] Regression job green (`Full regression (799+)` in `ci.yml`)
- [ ] `scripts/deploy/validate_env.py` clean on staging
- [ ] Feature flags for risky changes set to OFF by default
- [ ] On-call engineer informed & Slack `#mfb-ops` channel notified

## Staging

- [ ] `deploy.yml` → `deploy_staging` completed
- [ ] Smoke test on staging passed
- [ ] Manual QA on 3 critical flows (login, wallet top-up, withdrawal request)
- [ ] Grafana “API Performance” panel shows no regressions vs previous baseline

## Production

- [ ] Pre-deploy backup taken (`mongo_backup.sh` inside `deploy_production` step)
- [ ] Manual approval given on the GitHub Environment gate
- [ ] `deploy_production` job green
- [ ] Post-deploy smoke test passed → `.last_good_tag` updated
- [ ] Grafana error-rate panel returns to baseline within 15 min

## Post-deploy (24 h window)

- [ ] No new critical alerts firing
- [ ] Reconciliation job succeeded overnight
- [ ] Support inbox reviewed for user-reported regressions
- [ ] Retro notes appended to release ticket
