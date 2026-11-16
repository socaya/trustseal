"""Operator-facing SLO status endpoint (J5).

``GET /api/_internal/slo`` returns the current observations per
endpoint class. Admin-only — exposing the burn-rate to tenants
would leak cross-tenant performance data.
"""
from __future__ import annotations

from flask import Blueprint, abort, jsonify
from flask_jwt_extended import jwt_required

from app.policies.api_access import is_admin
from app.services import slo
from app.services.token_security import active_token_user

slo_api = Blueprint("slo_api", __name__, url_prefix="/api/_internal")


@slo_api.route("/slo", methods=["GET"])
@jwt_required()
def slo_status():
    user = active_token_user()
    if user is None or not user.is_active:
        abort(401)
    if not is_admin(user.id):
        abort(403, description="admin_required")
    observations = slo.observations()
    overall = "ok"
    for obs in observations:
        if obs.status == "breach":
            overall = "breach"
            break
        if obs.status == "at_risk" and overall != "breach":
            overall = "at_risk"
    return jsonify(
        overall=overall,
        classes=[
            {
                "endpoint_class": o.endpoint_class,
                "status": o.status,
                "request_count": o.request_count,
                "error_count": o.error_count,
                "availability": {
                    "observed": o.availability_observed,
                    "target": o.availability_target,
                },
                "latency_p95_ms": {
                    "observed": o.latency_p95_observed_ms,
                    "target": o.latency_p95_target_ms,
                },
                "burn_rate": o.burn_rate,
            }
            for o in observations
        ],
    )
