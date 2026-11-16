"""SAML 2.0 Service Provider endpoints.

Routes:

* ``GET /saml/<provider_id>/metadata`` — publish SP metadata for the
  IdP administrator to upload.
* ``GET /saml/<provider_id>/login`` — build an AuthnRequest and
  redirect the browser to the IdP. ``RelayState`` carries the
  ``next`` URL through the round trip.
* ``POST /saml/<provider_id>/acs`` — Assertion Consumer Service.
  Validates the signed response, JIT-provisions the user, issues
  JWT access + refresh tokens, and redirects back to
  ``RelayState`` or ``/`` on success.

JIT provisioning policy: the email attribute (configured per
provider in ``attribute_mapping``) maps to the ``User.email``. A
matching active user is reused; a missing user is created in the
provider's organization with ``email_verified=True`` (the IdP
vouched for the address).
"""
from __future__ import annotations

from datetime import datetime
from urllib.parse import urlparse, urljoin

from flask import (
    Blueprint,
    abort,
    current_app,
    jsonify,
    redirect,
    request,
    url_for,
)

from app.extensions import db
from app.models.saml_provider import SamlProvider
from app.models.user import User
from app.services import saml as saml_service
from app.services.refresh_tokens import issue_login_tokens

saml_views = Blueprint("saml_views", __name__, url_prefix="/saml")


def _provider_or_404(provider_id: int) -> SamlProvider:
    row = db.session.get(SamlProvider, provider_id)
    if row is None or not row.is_active:
        abort(404)
    return row


def _acs_url(provider_id: int) -> str:
    base = (current_app.config.get("PUBLIC_BASE_URL") or "").rstrip("/")
    return f"{base}/saml/{provider_id}/acs"


def _safe_relay_state(candidate: str | None) -> str:
    """Only relay states that stay inside the deployment base URL are honored.

    Open-redirect avoidance: an attacker who seeds RelayState in a
    phishing email must not be able to bounce the authenticated
    browser to an external host after ACS.
    """
    if not candidate:
        return "/"
    base = urlparse(current_app.config.get("PUBLIC_BASE_URL") or "")
    target = urlparse(urljoin(f"{base.scheme}://{base.netloc}", candidate))
    if target.netloc and target.netloc != base.netloc:
        return "/"
    # Always return the path + query of the candidate.
    rebuilt = target.path or "/"
    if target.query:
        rebuilt = f"{rebuilt}?{target.query}"
    return rebuilt


@saml_views.route("/<int:provider_id>/metadata", methods=["GET"])
def metadata(provider_id: int):
    provider = _provider_or_404(provider_id)
    xml = saml_service.build_sp_metadata(
        provider.audience,
        acs_url=_acs_url(provider.id),
        sp_signing_cert_pem=provider.sp_signing_cert_pem,
    )
    return (xml, 200, {"Content-Type": "application/samlmetadata+xml"})


@saml_views.route("/<int:provider_id>/login", methods=["GET"])
def login(provider_id: int):
    provider = _provider_or_404(provider_id)
    relay = _safe_relay_state(request.args.get("next"))
    redirect_url, request_id = saml_service.build_authn_request(
        provider,
        acs_url=_acs_url(provider.id),
        relay_state=relay,
    )
    response = redirect(redirect_url)
    # Record the AuthnRequest ID in a short-lived HttpOnly cookie so
    # the ACS can enforce InResponseTo and resist cross-tab attacks.
    response.set_cookie(
        f"ts_saml_req_{provider.id}",
        request_id,
        httponly=True,
        secure=request.is_secure,
        samesite="Lax",
        max_age=600,
        path=f"/saml/{provider.id}/acs",
    )
    return response


@saml_views.route("/<int:provider_id>/acs", methods=["POST"])
def acs(provider_id: int):
    provider = _provider_or_404(provider_id)
    saml_response = request.form.get("SAMLResponse")
    if not saml_response:
        abort(400, description="saml_response_missing")
    expected = request.cookies.get(f"ts_saml_req_{provider.id}")
    try:
        assertion = saml_service.consume_response(
            provider,
            saml_response_b64=saml_response,
            acs_url=_acs_url(provider.id),
            expected_in_response_to=expected,
        )
    except saml_service.SamlError as exc:
        db.session.rollback()
        return jsonify(error=str(exc)), 401

    user = _resolve_or_create_user(provider, assertion)
    if user is None:
        db.session.rollback()
        return jsonify(error="user_attribute_missing"), 401
    access, refresh = issue_login_tokens(user.id)
    db.session.commit()
    relay = _safe_relay_state(request.form.get("RelayState"))
    response = redirect(relay)
    response.set_cookie(
        "access_token",
        access,
        httponly=True,
        secure=request.is_secure,
        samesite="Lax",
    )
    response.set_cookie(
        "refresh_token",
        refresh,
        httponly=True,
        secure=request.is_secure,
        samesite="Lax",
    )
    # Clear the request-id cookie once the ACS has consumed it.
    response.delete_cookie(
        f"ts_saml_req_{provider.id}", path=f"/saml/{provider.id}/acs"
    )
    return response


def _resolve_or_create_user(provider, assertion):
    """Map the SAML assertion to a local User, JIT-provisioning if absent."""
    email_attr = provider.attribute_mapping.get("email")
    first_name_attr = provider.attribute_mapping.get("first_name")
    last_name_attr = provider.attribute_mapping.get("last_name")
    email = None
    if email_attr and assertion.attributes.get(email_attr):
        email = assertion.attributes[email_attr][0].strip().lower()
    elif "@" in assertion.name_id:
        email = assertion.name_id.strip().lower()
    if not email:
        return None
    user = User.query.filter_by(email=email).first()
    if user is None:
        user = User(
            username=email,
            email=email,
            is_active=True,
            organization_id=provider.organization_id,
            email_verified=True,
            email_verified_at=datetime.utcnow(),
        )
        if first_name_attr and assertion.attributes.get(first_name_attr):
            user.first_name = assertion.attributes[first_name_attr][0]
        if last_name_attr and assertion.attributes.get(last_name_attr):
            user.last_name = assertion.attributes[last_name_attr][0]
        # SAML-provisioned users do not get a usable password; set a
        # random one so the hash column is well-formed.
        import secrets

        user.set_password(secrets.token_urlsafe(32))
        db.session.add(user)
        db.session.flush()
    else:
        if not user.is_active:
            return None
        if not user.email_verified:
            user.email_verified = True
            user.email_verified_at = datetime.utcnow()
    return user
