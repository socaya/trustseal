"""Tenant usage visibility (Phase F1).

Returns the current period's hit count for every known meter so the
account page can show "15 of 100 envelopes this month" without the
UI having to coordinate with the billing adapter.
"""
from __future__ import annotations

from flask import Blueprint, abort, jsonify, request
from flask_jwt_extended import jwt_required

from app.services import usage_ledger
from app.services.token_security import active_token_user

usage_api = Blueprint("usage_api", __name__, url_prefix="/api/usage")


@usage_api.route("/summary", methods=["GET"])
@jwt_required()
def summary():
    user = active_token_user()
    if user is None or not user.is_active or user.organization_id is None:
        abort(401)
    period = request.args.get("period", "month")
    try:
        summary = usage_ledger.summary(user.organization_id, period=period)
    except usage_ledger.UsageError as exc:
        abort(400, description=str(exc))
    return jsonify(period=period, meters=summary)
