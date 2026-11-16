"""Single-logout HTTP surface (Phase L3).

``POST /api/auth/sso/logout`` ends the caller's TrustSeal session
and returns any SSO IdP redirect URLs the browser should visit to
complete logout on the identity provider side.
"""
from __future__ import annotations

from flask import Blueprint, abort, jsonify, make_response, request
from flask_jwt_extended import jwt_required

from app.extensions import db
from app.models.oidc_provider import OidcProvider
from app.models.saml_provider import SamlProvider
from app.services import single_logout
from app.services.token_security import active_token_user

sso_logout_api = Blueprint(
    "sso_logout_api", __name__, url_prefix="/api/auth/sso"
)


@sso_logout_api.route("/logout", methods=["POST"])
@jwt_required()
def logout():
    user = active_token_user()
    if user is None or not user.is_active:
        abort(401)
    data = request.get_json(silent=True) or {}
    saml_provider_id = data.get("saml_provider_id")
    oidc_provider_id = data.get("oidc_provider_id")
    saml_provider = (
        db.session.get(SamlProvider, int(saml_provider_id))
        if isinstance(saml_provider_id, int)
        else None
    )
    oidc_provider = (
        db.session.get(OidcProvider, int(oidc_provider_id))
        if isinstance(oidc_provider_id, int)
        else None
    )
    # Guard cross-tenant provider references.
    if saml_provider and saml_provider.organization_id != user.organization_id:
        saml_provider = None
    if oidc_provider and getattr(oidc_provider, "organization_id", None) != user.organization_id:
        oidc_provider = None
    try:
        outcome = single_logout.logout_user(
            user.id,
            saml_provider=saml_provider,
            oidc_provider=oidc_provider,
        )
    except single_logout.SingleLogoutError as exc:
        db.session.rollback()
        abort(400, description=str(exc))
    db.session.commit()
    response = make_response(jsonify(outcome))
    # Clear any Flask-Login + JWT cookies the browser is carrying.
    response.delete_cookie("access_token")
    response.delete_cookie("refresh_token")
    response.delete_cookie("session")
    return response
