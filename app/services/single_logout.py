"""Single-logout plumbing (Phase L3).

TrustSeal's SSO is federated (OIDC + SAML 2.0). This module gives
operators one place to end a user's entire presence:

* Revoke every :class:`RefreshTokenFamily` (TrustSeal's own JWT
  lifecycle).
* Revoke every :class:`UserSession` row so the account UI and the
  session-management endpoint reflect the logout.
* Emit a :class:`SecurityEvent` for the chained audit log.

The caller clears access/refresh cookies in the HTTP layer. For
SAML providers that advertise a SingleLogoutService endpoint the
service also returns a redirect URL the browser should visit
(``LogoutRequest``, HTTP-Redirect binding). The OIDC side omits
protocol-level logout here — RP-initiated logout is a redirect to
the IdP's ``end_session_endpoint``; the application returns the
URL when the OIDC provider carries one.
"""
from __future__ import annotations

import base64
import uuid
import zlib
from datetime import datetime
from typing import Optional
from urllib.parse import urlencode

from lxml import etree

from app.extensions import db
from app.models.event_delivery import SecurityEvent
from app.models.oidc_provider import OidcProvider
from app.models.saml_provider import SamlProvider
from app.models.user import User
from app.services import sessions as sessions_svc
from app.services.refresh_tokens import revoke_all_for_user


SAML_PROTOCOL_NS = "urn:oasis:names:tc:SAML:2.0:protocol"
SAML_ASSERTION_NS = "urn:oasis:names:tc:SAML:2.0:assertion"


class SingleLogoutError(RuntimeError):
    """Raised when a logout cannot be completed cleanly."""


def logout_user(
    user_id: int,
    *,
    reason: str = "user_initiated",
    saml_provider: Optional[SamlProvider] = None,
    oidc_provider: Optional[OidcProvider] = None,
) -> dict:
    """Terminate the user's TrustSeal session and return SSO redirects.

    Returns a dict with:

    * ``revoked_families`` — count of refresh-token families
      revoked.
    * ``saml_logout_url`` — IdP redirect for SAML Single Logout
      when a provider with a SingleLogoutService endpoint is passed.
    * ``oidc_logout_url`` — IdP redirect for OIDC RP-initiated
      logout when the provider advertises an
      ``end_session_endpoint``.
    """
    user = db.session.get(User, user_id)
    if user is None:
        raise SingleLogoutError("user_not_found")
    revoked = revoke_all_for_user(user.id, reason=f"sso_logout:{reason}")
    # Each ``revoke_all_for_user`` already revokes UserSession rows
    # via the sessions hook. Belt-and-braces: mark any that slipped.
    for session_row in sessions_svc.list_sessions(user.id):
        if session_row["active"]:
            sessions_svc.revoke(
                user.id, session_row["id"], reason=f"sso_logout:{reason}"
            )

    db.session.add(
        SecurityEvent(
            organization_id=user.organization_id,
            actor_id=user.id,
            action="sso.logout",
            resource_type="user",
            resource_id=user.id,
            outcome="ok",
            correlation_id=uuid.uuid4().hex,
        )
    )
    return {
        "revoked_families": revoked,
        "saml_logout_url": (
            build_saml_logout_url(saml_provider, user.email)
            if saml_provider is not None
            else None
        ),
        "oidc_logout_url": (
            build_oidc_logout_url(oidc_provider)
            if oidc_provider is not None
            else None
        ),
    }


# --------------------------------------------------- SAML LogoutRequest


def build_saml_logout_url(
    provider: SamlProvider, name_id: str
) -> Optional[str]:
    """Build an HTTP-Redirect LogoutRequest.

    Returns ``None`` when the provider has no configured SLO endpoint
    — some IdPs do not implement SAML SLO. The attribute is stored
    on ``SamlProvider.sso_url`` + optional
    ``single_logout_service_url`` once the operator adds it. For
    now we expect the SLO URL to live in
    ``provider.attribute_mapping["single_logout_service_url"]``.
    """
    mapping = provider.attribute_mapping or {}
    slo_url = mapping.get("single_logout_service_url")
    if not slo_url or not isinstance(slo_url, str):
        return None
    request_id = "_" + uuid.uuid4().hex
    issue_instant = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    root = etree.Element(
        "{%s}LogoutRequest" % SAML_PROTOCOL_NS,
        nsmap={
            "samlp": SAML_PROTOCOL_NS,
            "saml": SAML_ASSERTION_NS,
        },
        ID=request_id,
        Version="2.0",
        IssueInstant=issue_instant,
        Destination=slo_url,
    )
    issuer = etree.SubElement(root, "{%s}Issuer" % SAML_ASSERTION_NS)
    issuer.text = provider.audience
    name = etree.SubElement(root, "{%s}NameID" % SAML_ASSERTION_NS)
    name.text = name_id
    xml = etree.tostring(root, xml_declaration=False, encoding="utf-8")
    compressed = zlib.compress(xml)[2:-4]
    encoded = base64.b64encode(compressed).decode("ascii")
    separator = "&" if "?" in slo_url else "?"
    return f"{slo_url}{separator}{urlencode({'SAMLRequest': encoded})}"


# --------------------------------------------------- OIDC RP-initiated


def build_oidc_logout_url(provider: OidcProvider) -> Optional[str]:
    """Return the RP-initiated end-session URL when advertised."""
    end_session = getattr(provider, "end_session_endpoint", None)
    if not end_session or not isinstance(end_session, str):
        return None
    return end_session
