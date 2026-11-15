# Performance test overview

The Locust scenarios in `tests/performance/locustfile.py` are designed
to exercise the parts of TrustSeal that we expect to put under load
first:

| Scenario              | Endpoint                                 | Why it matters                         |
|-----------------------|------------------------------------------|----------------------------------------|
| `SignerPrepareLoad`   | `POST /api/envelopes/<id>/prepare`       | Lock + idempotency contention path     |
| `PublicVerifyLoad`    | `POST /verify/pdf`                       | CPU-heavy PDF parse / signature check  |
| `DossierRead`         | `GET /evidence/retentions/<id>`          | Tenant-scoped multi-join compliance UI |

## Required environment

The scenarios refuse to run without explicit targeting so a stray
`locust` invocation never hits production:

```sh
export TRUSTSEAL_LOCUST_TARGET=https://staging.trustseal.internal
export TRUSTSEAL_LOCUST_TOKEN=<staging-only JWT access token>
export TRUSTSEAL_LOCUST_ENVELOPE_IDS=101,102,103
export TRUSTSEAL_LOCUST_RETENTION_IDS=201,202,203
# Optional: a staging session cookie for the evidence view.
export TRUSTSEAL_LOCUST_COOKIE="session=..."
```

## Running a baseline

```sh
pip install 'locust>=2.20,<3'
locust -f tests/performance/locustfile.py --headless \
  --users 200 --spawn-rate 20 --run-time 10m \
  --csv=artifacts/perf/baseline
```

Keep the `artifacts/perf/baseline-stats.csv` output under version
control so future runs can be compared.

## SLO thresholds

| Scenario            | p95     | Max error rate |
|---------------------|---------|----------------|
| envelope prepare    | 400 ms  | 0.1 %          |
| public verify       | 1.5 s   | 0.5 %          |
| dossier read        | 300 ms  | 0.1 %          |

A run that breaches any threshold is a Sev-3 incident until explained
or mitigated.

## What these tests do NOT do

- They do **not** attempt a full browser rendering. Accessibility and
  responsiveness tests live under `tests/accessibility/`.
- They do **not** validate the sealed PDFs that result. Correctness is
  covered by the integration suite under `tests/integration/`.
- They are **not** a substitute for soak testing: a 10-minute run
  reveals latency distributions but will not catch slow memory leaks.
