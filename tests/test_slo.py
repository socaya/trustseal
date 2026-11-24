"""SLO metrics + status endpoint (J5)."""
from __future__ import annotations

import pytest
from flask_jwt_extended import create_access_token


class TestClassify:
    def test_public_verify(self):
        from app.services.slo import classify_path

        assert classify_path("/verify") == "public_verify"
        assert classify_path("/verify/pdf") == "public_verify"

    def test_signer(self):
        from app.services.slo import classify_path

        assert classify_path("/sign/abc") == "signer"
        assert classify_path("/api/signer-intent/envelopes/1") == "signer"

    def test_admin_api_default(self):
        from app.services.slo import classify_path

        assert classify_path("/api/envelopes") == "admin_api"
        assert classify_path("/metrics") == "admin_api"
        assert classify_path("") == "admin_api"


class TestObservations:
    def _record(self, endpoint: str, status: str, latency_s: float) -> None:
        """Push a single sample into the existing Prometheus series."""
        from app.metrics import http_request_duration_seconds, http_requests_total

        http_requests_total.labels(
            method="GET", endpoint=endpoint, status=status
        ).inc()
        http_request_duration_seconds.labels(
            method="GET", endpoint=endpoint, status=status
        ).observe(latency_s)

    def test_observations_cover_every_class(self, pg_app):
        """Returned structure includes every default class."""
        from app.services import slo

        classes = {o.endpoint_class for o in slo.observations(pg_app.config)}
        assert classes == {"public_verify", "signer", "admin_api"}

    def test_errors_push_class_into_breach(self, pg_app):
        """Adding a burst of 5xx samples flips the admin_api status to breach.

        Delta-based so prior test traffic (which also lands in the
        global Prometheus registry) does not perturb the assertion.
        """
        from app.services import slo

        for _ in range(2000):
            # Lots of 5xx into a single endpoint so the ratio exceeds
            # the admin_api availability budget (0.5%) regardless of
            # whatever baseline the earlier tests pushed into the
            # registry.
            self._record("/api/envelopes", "5xx", 0.5)
        obs = {o.endpoint_class: o for o in slo.observations(pg_app.config)}
        admin = obs["admin_api"]
        assert admin.error_count >= 2000
        assert admin.availability_observed < admin.availability_target
        assert admin.status == "breach"
        assert admin.burn_rate > 1.0


class TestEndpoint:
    def test_requires_admin(self, pg_app):
        from app.extensions import db
        from app.models.organization import Organization
        from app.models.user import User

        org = Organization(name="SLO Tenant", type="company")
        db.session.add(org)
        db.session.flush()
        user = User(
            username="slo-user",
            email="slo-user@example.test",
            is_active=True,
            organization_id=org.id,
        )
        user.set_password("slopassword12345")
        db.session.add(user)
        db.session.commit()
        client = pg_app.test_client()
        token = create_access_token(identity=str(user.id))
        r = client.get(
            "/api/_internal/slo",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 403

    def test_admin_sees_overall_status(self, pg_app):
        from app.extensions import db
        from app.models.organization import Organization
        from app.models.system import Role, UserRole
        from app.models.user import User

        org = Organization(name="SLO Admin Tenant", type="company")
        db.session.add(org)
        db.session.flush()
        role = Role.query.filter_by(name="admin").one_or_none() or Role(
            name="admin", description="test"
        )
        db.session.add(role)
        db.session.flush()
        admin = User(
            username="slo-admin",
            email="slo-admin@example.test",
            is_active=True,
            organization_id=org.id,
        )
        admin.set_password("slopassword12345")
        db.session.add(admin)
        db.session.flush()
        db.session.add(UserRole(user_id=admin.id, role_id=role.id))
        db.session.commit()
        client = pg_app.test_client()
        token = create_access_token(identity=str(admin.id))
        r = client.get(
            "/api/_internal/slo",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        body = r.get_json()
        assert body["overall"] in {"ok", "at_risk", "breach"}
        assert {c["endpoint_class"] for c in body["classes"]} == {
            "public_verify",
            "signer",
            "admin_api",
        }


class TestRunbookAndAlertRules:
    def test_slo_runbook_and_prometheus_alerts_match_targets(self):
        from pathlib import Path
        import yaml
        from app.services.slo import DEFAULT_TARGETS

        root = Path(__file__).resolve().parent.parent
        runbook = (root / "docs" / "runbooks" / "SLOs.md").read_text(encoding="utf-8")
        alerts_raw = (root / "docs" / "runbooks" / "slo-alerts.prometheus.yml").read_text(
            encoding="utf-8"
        )
        parsed = yaml.safe_load(alerts_raw)
        groups = {g["name"]: g["rules"] for g in parsed["groups"]}
        assert "trustseal_slo_availability_burn_rate" in groups
        assert "trustseal_slo_latency" in groups

        burn_rules = groups["trustseal_slo_availability_burn_rate"]
        latency_rules = groups["trustseal_slo_latency"]
        for cls in DEFAULT_TARGETS:
            assert cls in runbook
            cls_burns = {
                r["labels"]["burn_window"]
                for r in burn_rules
                if r["labels"].get("endpoint_class") == cls
            }
            assert cls_burns == {"fast", "slow"}, f"Missing fast/slow burn alerts for {cls}"
            assert any(
                r["labels"].get("endpoint_class") == cls for r in latency_rules
            ), f"Missing p95 latency alert for {cls}"
