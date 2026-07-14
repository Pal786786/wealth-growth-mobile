# My Funding Bank — Known Limitations (v1.0 Beta)

_Tracked openly so support, sales, and product can align expectations._

---

## Platform

- **Single-node MongoDB** in the default compose stack. HA requires promoting to a 3-node replica set (see `PRODUCTION_DEPLOYMENT_GUIDE.md` § alt-deploy).
- **No Redis / cache layer** yet. Read scalability comes only from Mongo indexes and Gunicorn workers.
- **JWT tokens are long-lived** (7 days). Short-lived + refresh planned in Sprint 14.
- **No WAF / DDoS protection out of the box.** Nginx rate limits mitigate abuse but Cloudflare or AWS WAF is recommended for public launch.
- **Backups do not include KYC images stored outside Mongo.** Documents stored as base64 inside Mongo are backed up correctly.

---

## Third-party integrations

- **Cashfree Payouts** may fall back to demo mode if API keys unset. This is intentional — UI clearly labels demo status.
- **Razorpay** webhook retry policy assumes provider-side signature verification; local logs may lag by up to 15 s.
- **TwelveData** free tier limits us to ~800 requests/day. Rate limit is respected by the market data cache.
- **Emergent LLM key** consumption is bounded by the platform budget — monitor via profile page. If exhausted, AI features degrade gracefully with a user-visible message.

---

## Monitoring

- **Grafana ports bound to `127.0.0.1`** for security. External access requires SSH tunnel or Nginx vhost.
- **Prometheus retention: 30 days.** Longer retention requires remote-write to a long-term TSDB (VictoriaMetrics/Mimir).
- **`mfb_active_sessions` is approximate** — 5-min sliding window heuristic, not a hard count.

---

## Mobile

- **Expo Go cannot exercise `expo-camera` in background mode.** QR scanning works in foreground; background camera requires a dev build.
- **Push notifications** are gated by `EMERGENT_PUSH_KEY` and require an actual signed build (not Expo Go). Not enabled in beta.

---

## CI/CD

- **Trivy is non-blocking** in the initial launch to prevent false-positive-driven build failures. Elevate to blocking after 30 days of green runs.
- **Mobile builds** are done via Emergent Publish button, not GitHub Actions — the workflow only prebuilds an artifact for QA.

---

## Documentation

- Load-test harness (`tests/loadtest/*.js`) is a placeholder — populate before general availability.
- Alertmanager receivers are documented but not shipped (privacy of webhook URLs).

---

_Please open a GitHub issue with the `known-limitation` label when you encounter one that is not documented above._
