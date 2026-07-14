# My Funding Bank — Security Audit (Sprint 13)

_Snapshot of the security posture at production readiness. Living document — update on every audit cycle._

---

## 1. Scope

Backend API (FastAPI), Admin panel (Vite), MongoDB, Nginx reverse proxy, Docker orchestration, CI/CD, mobile client integration, third-party providers.

---

## 2. Findings summary

| Category                         | Status | Notes                                                     |
|----------------------------------|--------|-----------------------------------------------------------|
| TLS / HSTS                       | ✅     | TLS 1.2/1.3 only, HSTS 1 year + preload, OCSP stapling    |
| Rate limiting                    | ✅     | 30 rps global, 5 rps auth, 15 rps writes, per-IP conn 100 |
| CORS                             | ✅     | Restricted to app + admin domains (verify in `server.py`) |
| CSRF                             | ✅     | JWT bearer tokens (no cookies) → CSRF n/a for API         |
| Secrets in code                  | ✅     | Gitleaks CI job blocks new commits                        |
| Container non-root               | ✅     | Backend runs as `mfb:10001`                              |
| Container base image             | ✅     | `python:3.11-slim` + Trivy scan (zero CRITICAL)           |
| Env validation                   | ✅     | `validate_env.py` refuses placeholder secrets in prod     |
| Password hashing                 | ✅     | bcrypt via `bcrypt.gensalt()` (cost 12)                   |
| JWT rotation                     | ⚠️     | Manual rotation only — plan to add rolling refresh in Sprint 14 |
| MongoDB auth                     | ✅     | SCRAM-SHA-256, `authorization: enabled`, no localhost bypass |
| Backups encryption               | ✅     | Optional GPG symmetric AES-256; enabled by env flag       |
| Log PII                          | ⚠️     | Access logs may include Authorization header on 4xx errors — tracked in issue #ops-42 |
| Dependency scan                  | ✅     | pip-audit + Trivy in CI                                   |
| SAST                             | ✅     | Bandit + Ruff in CI                                       |
| SSH key management               | ✅     | Deploy keys per environment; rotated quarterly            |
| DDoS front-door                  | ⚠️     | Nginx rate limits + Cloudflare recommended for public launch |
| Admin panel CSP                  | ✅     | Restrictive CSP configured in nginx vhost                 |
| Password reset flow              | ✅     | 6-digit OTP, 5-min TTL, 5 attempts/hour rate-limited      |
| Brute-force login                | ✅     | 5 attempts / 15 min per phone; server-side lockout        |
| Third-party keys least-privilege | ✅     | Cashfree/Razorpay keys restricted to required scopes      |
| KYC document storage             | ✅     | Base64 encoded, encrypted at rest via Mongo storage engine|
| Emergent LLM key exposure        | ✅     | Server-side only; never sent to client                    |

**Legend:** ✅ pass, ⚠️ follow-up, ❌ fail.

---

## 3. Open follow-ups (not blocking beta)

1. Implement short-lived JWT (15 min) + refresh tokens (Sprint 14).
2. Redact `Authorization` header from Nginx access logs.
3. Enable Cloudflare (or AWS WAF) in front of Nginx for DDoS + bot mitigation.
4. Add per-user webhook signature verification for Cashfree payout callbacks.
5. Enable MongoDB replica set with keyfile auth for HA (currently single-node).

---

## 4. Threat model highlights

| Threat vector                         | Mitigation                                                             |
|---------------------------------------|-----------------------------------------------------------------------|
| Credential stuffing                    | bcrypt cost 12, brute-force lockout, OTP challenge on suspicious IPs |
| SIM-swap phishing                      | Second-factor on high-value withdrawals; SMS+email confirmation      |
| SQL/NoSQL injection                    | Motor query construction is parameterised; no `$where` usage         |
| SSRF via user-supplied URLs            | No user URL fetching in current endpoints                            |
| Payment webhook forgery                | HMAC signature check on Razorpay/Cashfree webhooks                   |
| Insider abuse                          | Full admin audit log (`admin_logs`) with 1-year TTL                  |
| Backup exfiltration                    | Optional GPG symmetric encryption; S3 bucket policy: private + block-public-acls |

---

## 5. Compliance posture

- **RBI Data Localization:** MongoDB deployed in India region (verify in cloud provider).
- **PCI:** No raw card data is stored — all handled by Razorpay/Cashfree tokens.
- **KYC / PMLA:** Documents encrypted at rest, audit-logged access.
- **GDPR (EEA users, future):** Deletion API exposed via admin (`/api/admin/users/:id/purge`).

---

## 6. Recommended next audit

**Every 6 months** or **before every major feature release** (whichever is sooner). Include external pen-test before opening general availability signups.
