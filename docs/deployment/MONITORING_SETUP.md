# My Funding Bank — Monitoring Setup Guide

---

## 1. Architecture

```
┌──────────────┐   scrape 15s   ┌────────────────┐   dashboards   ┌────────────┐
│  MFB backend ├──────────────▶│  Prometheus     ├──────────────▶│ Grafana    │
│  /api/metrics│                │  alerts.yml     │                └────────────┘
└──────────────┘                └──────┬─────────┘
                                        ▼
                                 (optional) Alertmanager
                                 → Slack / PagerDuty / email
```

---

## 2. Enabling the stack

```bash
docker compose -f deploy/docker-compose.prod.yml \
               -f deploy/docker-compose.monitoring.yml \
               --profile monitoring \
               --env-file .env.prod up -d
```

Services started:

- `mfb_prometheus`   (retention 30 days, TSDB path `/prometheus`)
- `mfb_grafana`      (auto-provisions datasource + 7 dashboards)
- `mfb_node_exporter` (host CPU/mem/disk/net)
- `mfb_mongo_exporter` (MongoDB internals)
- `mfb_cadvisor`     (per-container metrics)

### Ports

| Service     | Bind          | Access route                                   |
|-------------|---------------|-----------------------------------------------|
| Prometheus  | internal only | `docker compose exec prometheus wget -qO- http://localhost:9090/-/healthy` |
| Grafana     | `127.0.0.1:3001` | Expose behind Nginx + VPN, or `ssh -L 3001:127.0.0.1:3001 deploy@<host>` |

---

## 3. Backend metrics catalogue

| Metric                                | Type     | Labels                | Purpose                    |
|---------------------------------------|----------|-----------------------|----------------------------|
| `mfb_http_requests_total`              | counter  | method, path, status  | Traffic + error rate       |
| `mfb_http_request_duration_seconds`    | histogram| method, path          | Latency p50/p95/p99        |
| `mfb_http_in_flight_requests`          | gauge    | –                     | Backpressure indicator     |
| `mfb_mongo_ping_seconds`               | gauge    | –                     | DB latency                 |
| `mfb_wallet_transactions_total`        | counter  | type, status          | Business volume            |
| `mfb_payments_total`                   | counter  | provider, status      | Payment health             |
| `mfb_withdrawals_total`                | counter  | provider, status      | Payout health              |
| `mfb_provider_up`                      | gauge    | provider              | External provider status   |
| `mfb_finance_alerts`                   | gauge    | severity, status      | Reconciliation alerts      |
| `mfb_scheduler_jobs`                   | gauge    | state                 | APScheduler health         |
| `mfb_active_sessions`                  | gauge    | –                     | Active users (5-min window)|
| `mfb_build_info`                       | gauge    | version, env, host    | Static build info          |

Emit new counters from your modules via helpers in `health_monitoring.py`:

```python
import health_monitoring as hm
hm.record_payment("razorpay", "success")
hm.record_withdrawal("cashfree", "failed")
hm.set_provider_up("twelvedata", True)
```

---

## 4. Dashboards (auto-provisioned)

1. **System Health** — uptime, CPU, memory, disk, request rate
2. **API Performance** — p50/p95/p99, error rate, status codes
3. **Finance Overview** — alerts, wallet volumes
4. **Payments & Withdrawals** — provider breakdown + success %
5. **Providers** — external provider health matrix
6. **Database** — mongo latency, ops/sec, connections
7. **Scheduler & Alerts** — job counts, alert severity trend

Grafana admin credentials come from `GRAFANA_ADMIN_USER` / `GRAFANA_ADMIN_PASSWORD` in `.env.prod`.

---

## 5. Alerting rules

All rules live in `deploy/prometheus/alerts.yml` (loaded automatically). Highlights:

- `BackendDown` – critical, 1 min
- `HighAPILatencyP95` – warning, p95 > 1 s for 5 min
- `HighAPIErrorRate` – critical, 5xx > 5%
- `ProviderOffline` – per external provider
- `MongoUnreachable` / `MongoSlow`
- `DiskSpaceHigh` (80%) / `DiskSpaceCritical` (90%)
- `MemoryHigh` (85%) / `CPUHigh` (90%)
- `PaymentFailuresSurge` / `WithdrawalFailuresSurge`
- `FinanceCriticalAlerts`

### Wire an Alertmanager receiver

```yaml
# alertmanager.yml (not shipped, add to your infra separately)
receivers:
  - name: slack-critical
    slack_configs:
      - send_resolved: true
        api_url: <SLACK_WEBHOOK>
        channel: "#mfb-alerts"
route:
  receiver: slack-critical
  group_by: [alertname, severity]
```

Then point Prometheus at it by adding `alertmanager:9093` in `deploy/prometheus/prometheus.yml` → `alerting.static_configs.targets`.

---

## 6. Lightweight JSON dashboard

Even with monitoring stack disabled, the built-in JSON summary is always available:

```bash
curl -s https://app.<domain>/api/health/summary | jq
{
  "status": "healthy",
  "uptime_sec": 12943.5,
  "mongo_ok": true,
  "mongo_latency_ms": 0.6,
  "cpu_pct": 8.3,
  "memory_pct": 41.2,
  "disk_pct": 22.5,
  "version": "v1.0.0",
  "env": "production"
}
```

Use it inside the admin panel `AdminHealth` widget as a fallback when Grafana isn't available.

---

## 7. Disabling monitoring

Set `ENABLE_METRICS=false` in `.env.prod` to skip Prometheus registration inside the backend, and simply omit the `--profile monitoring` flag from your compose command to avoid launching Prometheus/Grafana. All feature endpoints keep working.
