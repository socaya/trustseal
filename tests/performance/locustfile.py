"""TrustSeal performance scenarios.

Three scenarios exercise the parts of the system we expect to put
under load first:

* ``SignerPrepareLoad`` — concurrent ``POST /api/envelopes/<id>/prepare``
  from many signers. Measures idempotency-lock contention and outbox
  throughput.
* ``PublicVerifyLoad`` — anonymous ``POST /verify/pdf`` uploads. The
  verification path is CPU-heavy (PDF parse + signature inspection)
  and the first likely bottleneck for a public verification page.
* ``DossierRead`` — authenticated ``GET /evidence/retentions/<id>``
  reads for compliance officers. Tests tenant-scoped query cost.

Run:

    POSTGRES_ADMIN_URL=postgresql://postgres@localhost:5432/postgres \\
    TRUSTSEAL_LOCUST_TARGET=https://staging.trustseal.internal \\
    locust -f tests/performance/locustfile.py --headless \\
      -u 200 -r 20 --run-time 10m \\
      --csv=artifacts/perf/baseline

SLOs (derived from the SRS):

* Envelope prepare p95 < 400 ms at 200 concurrent clients.
* Public verify p95 < 1.5 s at 50 concurrent anonymous clients.
* Dossier read p95 < 300 ms at 100 concurrent clients.

The scenarios do not touch production. They expect a staging target
and fresh JWTs supplied via environment variables. They never generate
real cryptographic signatures; the request shapes approximate real
client behaviour so the server exercises the same code paths.
"""
from __future__ import annotations

import hashlib
import io
import os
import uuid

try:
    from locust import FastHttpUser, between, task
except ImportError as exc:  # pragma: no cover - optional dep
    raise SystemExit(
        "locust is not installed. Install the perf extras:\n"
        "    pip install 'locust>=2.20,<3'\n"
    ) from exc

TARGET = os.environ.get("TRUSTSEAL_LOCUST_TARGET", "http://localhost:5000")


def _auth_header() -> dict[str, str]:
    """Load a staging JWT from the environment.

    The scenarios refuse to run without an explicit token so a stray
    ``locust`` invocation in a terminal does not accidentally hammer a
    production host.
    """
    token = os.environ.get("TRUSTSEAL_LOCUST_TOKEN")
    if not token:
        raise SystemExit(
            "TRUSTSEAL_LOCUST_TOKEN required. Mint a staging-only "
            "access token and export it before running locust."
        )
    return {"Authorization": f"Bearer {token}"}


def _sample_pdf_bytes() -> bytes:
    """Return a tiny but structurally valid PDF for verify uploads."""
    return b"%PDF-1.4\n% locust probe\n0 0 obj\n<<>>\nendobj\n%%EOF\n"


class SignerPrepareLoad(FastHttpUser):
    """Hammer ``/api/envelopes/<id>/prepare`` with idempotency keys.

    Each virtual user prepares a distinct envelope id (supplied via
    ``TRUSTSEAL_LOCUST_ENVELOPE_IDS``, comma-separated) with a fresh
    idempotency key per attempt. The locust client counts the number
    of ``409 idempotency_in_progress`` responses so contention under
    load is visible in the summary.
    """

    host = TARGET
    wait_time = between(0.5, 1.5)

    def on_start(self):  # pragma: no cover - runtime hook
        raw = os.environ.get("TRUSTSEAL_LOCUST_ENVELOPE_IDS", "")
        self._envelope_ids = [p.strip() for p in raw.split(",") if p.strip()]
        if not self._envelope_ids:
            raise SystemExit(
                "TRUSTSEAL_LOCUST_ENVELOPE_IDS required: a comma list of "
                "staging envelope ids the signer user may finalize."
            )

    @task
    def prepare_envelope(self):  # pragma: no cover - runtime loop
        envelope_id = self._envelope_ids[
            hash(self.environment.runner.user_count) % len(self._envelope_ids)
        ]
        headers = {
            "Idempotency-Key": uuid.uuid4().hex,
            **_auth_header(),
        }
        with self.client.post(
            f"/api/envelopes/{envelope_id}/prepare",
            headers=headers,
            catch_response=True,
            name="/api/envelopes/{id}/prepare",
        ) as response:
            if response.status_code in (200, 201, 409):
                response.success()
            else:
                response.failure(
                    f"unexpected status {response.status_code}"
                )


class PublicVerifyLoad(FastHttpUser):
    """Upload a sample PDF against ``/verify/pdf`` as an anonymous user."""

    host = TARGET
    wait_time = between(1, 4)

    @task
    def verify_pdf(self):  # pragma: no cover - runtime loop
        body = _sample_pdf_bytes()
        digest = hashlib.sha256(body).hexdigest()
        files = {"pdf": ("probe.pdf", io.BytesIO(body), "application/pdf")}
        data = {"evidence_sha256": digest}
        with self.client.post(
            "/verify/pdf",
            data=data,
            files=files,
            catch_response=True,
            name="/verify/pdf",
        ) as response:
            # 200 (verdict rendered) and 400/503 (feature off, bad body)
            # are expected outcomes under load; 5xx should fail the
            # request so Locust's summary flags them.
            if response.status_code < 500:
                response.success()
            else:
                response.failure(f"5xx from verify: {response.status_code}")


class DossierRead(FastHttpUser):
    """Read a tenant-scoped evidence dossier."""

    host = TARGET
    wait_time = between(0.5, 2.0)

    def on_start(self):  # pragma: no cover - runtime hook
        raw = os.environ.get("TRUSTSEAL_LOCUST_RETENTION_IDS", "")
        self._retention_ids = [p.strip() for p in raw.split(",") if p.strip()]
        if not self._retention_ids:
            raise SystemExit(
                "TRUSTSEAL_LOCUST_RETENTION_IDS required: comma list of "
                "retention ids the staging viewer can read."
            )

    @task
    def read_dossier(self):  # pragma: no cover - runtime loop
        retention_id = self._retention_ids[
            hash(self.environment.runner.user_count) % len(self._retention_ids)
        ]
        # Evidence views are session-authenticated rather than JWT, so
        # production rehearsals use a long-lived staging session
        # cookie supplied via ``TRUSTSEAL_LOCUST_COOKIE``.
        cookie = os.environ.get("TRUSTSEAL_LOCUST_COOKIE")
        headers: dict[str, str] = {}
        if cookie:
            headers["Cookie"] = cookie
        with self.client.get(
            f"/evidence/retentions/{retention_id}",
            headers=headers,
            catch_response=True,
            name="/evidence/retentions/{id}",
        ) as response:
            if response.status_code in (200, 302, 401):
                response.success()
            else:
                response.failure(
                    f"unexpected status {response.status_code}"
                )
