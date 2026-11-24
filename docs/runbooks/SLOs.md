# Enterprise SLOs, Error Budgets & Burn-Rate Alerting

**Owner:** SRE / Platform Engineering
**Code Reference:** `app/services/slo.py`, `GET /api/_internal/slo`, `app/metrics.py`
**Alert Rules:** `docs/runbooks/slo-alerts.prometheus.yml`

---

## 1. Service Level Indicators (SLIs) & Targets

TrustSeal classifies HTTP traffic into three endpoint families (`app.services.slo.classify_path`) and measures availability and latency directly from Prometheus metrics (`http_requests_total` and `http_request_duration_seconds`).

| Endpoint Class | Route Prefix(es) | Availability SLO (30d) | 30d Error Budget | Latency p95 Target | Latency p99 Target |
| --- | --- | --- | --- | --- | --- |
| `public_verify` | `/verify`, `/verify/pdf` | **99.9%** (`status != "5xx"`) | 0.1% (~43.2 min) | **500 ms** | **1,000 ms** |
| `signer` | `/sign/*`, `/api/signer-intent/*` | **99.9%** (`status != "5xx"`) | 0.1% (~43.2 min) | **1,000 ms** | **2,000 ms** |
| `admin_api` | All other `/api/*` endpoints | **99.5%** (`status != "5xx"`) | 0.5% (~3.6 hrs) | **2,000 ms** | **4,000 ms** |

Operator overrides are supported via `app.config["SLO_TARGETS"]`. Live computed status and burn rates are exposed to tenant/platform administrators at `GET /api/_internal/slo`.

---

## 2. Multi-Window, Multi-Burn-Rate Alerting Policy

Following the Google SRE Workbook multi-window burn-rate model, AlertManager evaluates both **fast burn** (page immediately) and **slow burn** (ticket/warn) windows for each endpoint class in `docs/runbooks/slo-alerts.prometheus.yml`:

| Severity | Burn Rate | Short / Long Windows | 30d Budget Consumed | AlertManager Action |
| --- | --- | --- | --- | --- |
| **Page (`critical`)** | **14.4×** | 5m & 1h | 2% in 1 hour | Page primary on-call (`pagerduty-sre`) |
| **Page (`critical`)** | **6×** | 30m & 6h | 5% in 6 hours | Page primary on-call (`pagerduty-sre`) |
| **Ticket (`warning`)** | **1×** | 6h & 3d | 10% in 3 days | Create SRE ticket (`slack-sre-alerts`) |
| **Latency (`warning`)** | p95 breach | 15m sustained | N/A | Notify SRE channel (`slack-sre-alerts`) |

---

## 3. Error Budget Policy

- **> 50% budget remaining:** Normal feature velocity and release cadence.
- **20% – 50% budget remaining:** Review recent deployments and error contributors in `GET /api/_internal/slo` and Prometheus dashboards; prioritize reliability fixes.
- **< 20% budget remaining (or active `breach`):** Freeze non-emergency feature rollouts for the affected endpoint class until error rate returns below target and post-incident actions are scheduled.

---

## 4. Operator Runbook — Responding to a Burn-Rate Alert

1. **Inspect live SLO snapshot:** Query `GET /api/_internal/slo` (requires admin JWT) and check `overall_status`, per-class `burn_rate`, `error_count`, and `latency_p95_observed_ms`.
2. **Isolate failing routes:** Filter `http_requests_total{status="5xx"}` by `endpoint` and correlate `X-Request-Id` / OpenTelemetry trace IDs (`app/tracing.py`).
3. **Check database & dependency health:** Verify `/health/ready` (PostgreSQL connectivity, outbox lag, KMS/TSA reachability).
4. **Mitigate:** Roll back the latest release, shed abusive traffic via durable rate limits (`app/services/rate_limiting.py`), or fail over to standby per `docs/runbooks/disaster-recovery.md`.
5. **Post-incident:** Record root cause, error budget impact, and preventive regression test before lifting any release freeze.
