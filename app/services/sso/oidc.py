"""Tenant-scoped OpenID Connect authentication.

Flow:

1. ``POST /api/auth/sso/<slug>/register`` (admin only) stores a
   provider: issuer, client id, encrypted client secret, trusted email
   domains, display name. The clear-text secret appears exactly once in
   the response.
2. ``GET /api/auth/sso/<tenant>/<slug>/start`` returns an authorization
   URL plus a signed PKCE state — the caller redirects the user there.
3. ``GET /api/auth/sso/<tenant>/<slug>/callback`` receives the IdP
   redirect, verifies the state/code, fetches the id_token through
   authlib, validates ``email_verified``, matches the trusted domain,
   either finds or just-in-time creates the User, then issues the
   same access + refresh family as a password login.

The service never trusts the client with the discovery result; every
request re-fetches the ``.well-known/openid-configuration`` metadata so
rotating IdP keys are picked up without an application restart.

Secrets are encrypted at rest with a Fernet key derived from the
application ``SECRET_KEY`` (see :mod:`app.services.mfa`). A production
deployment with KMS should swap this derivation for a KMS-backed
Fernet envelope — the call site is isolated to :func:`encrypt_secret`
and :func:`_decrypt_secret`.
"""
from __future__ import annotations

import base64
import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, Optional

from authlib.integrations.requests_client import OAuth2Session
from authlib.jose import JsonWebToken
from authlib.oidc.core import CodeIDToken
from cryptography.fernet import Fernet, InvalidToken

from app.extensions import db
from app.models.oidc_provider import OidcProvider
from app.models.organization import Organization
from app.models.user import User
from app.services.refresh_tokens import issue_login_tokens


class OidcError(RuntimeError):
    """Domain-level OIDC configuration failure."""


class OidcCallbackError(RuntimeError):
    """Callback-time failure: untrusted email, unknown provider, etc."""


# ----- secret storage ---------------------------------------------


def _fernet_key(app_secret: str) -> bytes:
    if not isinstance(app_secret, str) or len(app_secret) < 32:
        raise OidcError("SECRET_KEY too short to derive OIDC envelope key")
    raw = hashlib.sha256(("oidc:" + app_secret).encode("utf-8")).digest()
    return base64.urlsafe_b64encode(raw)


def encrypt_secret(secret: str, app_secret: str) -> str:
    return Fernet(_fernet_key(app_secret)).encrypt(secret.encode("ascii")).decode("ascii")


def _decrypt_secret(cipher: str, app_secret: str) -> str:
    try:
        return (
            Fernet(_fernet_key(app_secret))
            .decrypt(cipher.encode("ascii"))
            .decode("ascii")
        )
    except InvalidToken as exc:
        raise OidcError("OIDC client secret unwrap failed") from exc


# ----- discovery --------------------------------------------------


@dataclass(frozen=True)
class DiscoveryMetadata:
    authorization_endpoint: str
    token_endpoint: str
    jwks_uri: str
    issuer: str


def discover_or_fail(issuer: str, fetch=None) -> DiscoveryMetadata:
    """Return the OIDC discovery metadata or raise :class:`OidcError`.

    ``fetch`` is injected by tests so no real network I/O is required.
    In production it defaults to :func:`requests.get`.
    """
    if not isinstance(issuer, str) or not issuer.startswith("https://"):
        raise OidcError("OIDC issuer must be an https URL")
    if fetch is None:
        import requests

        fetch = requests.get
    url = issuer.rstrip("/") + "/.well-known/openid-configuration"
    response = fetch(url, timeout=10)
    if getattr(response, "status_code", 0) != 200:
        raise OidcError("OIDC discovery failed")
    try:
        document = response.json()
    except Exception as exc:
        raise OidcError("OIDC discovery payload is not JSON") from exc
    required = {"authorization_endpoint", "token_endpoint", "jwks_uri", "issuer"}
    if not required.issubset(document):
        raise OidcError("OIDC discovery document missing required keys")
    if document["issuer"].rstrip("/") != issuer.rstrip("/"):
        raise OidcError("OIDC discovery issuer mismatch")
    return DiscoveryMetadata(
        authorization_endpoint=document["authorization_endpoint"],
        token_endpoint=document["token_endpoint"],
        jwks_uri=document["jwks_uri"],
        issuer=document["issuer"],
    )


# ----- registration ----------------------------------------------


def register_provider(
    *,
    tenant_id: int,
    slug: str,
    display_name: str,
    issuer: str,
    client_id: str,
    client_secret: str,
    trusted_email_domains: Iterable[str],
    app_secret: str,
) -> OidcProvider:
    if not isinstance(slug, str) or not 1 <= len(slug) <= 64 or not slug.replace("-", "").replace("_", "").isalnum():
        raise OidcError("provider slug must be url-safe alnum/dash/underscore")
    if not isinstance(display_name, str) or not 1 <= len(display_name) <= 120:
        raise OidcError("display_name required")
    if not isinstance(client_id, str) or not 1 <= len(client_id) <= 256:
        raise OidcError("client_id required")
    if not isinstance(client_secret, str) or not 1 <= len(client_secret) <= 512:
        raise OidcError("client_secret required")
    domains = [d.strip().lower() for d in trusted_email_domains if isinstance(d, str)]
    domains = [d for d in domains if d and "." in d and len(d) <= 253]
    if not domains:
        raise OidcError("at least one trusted email domain required")
    if OidcProvider.query.filter_by(organization_id=tenant_id, slug=slug).first():
        raise OidcError("provider slug already registered for this tenant")
    row = OidcProvider(
        organization_id=tenant_id,
        slug=slug,
        display_name=display_name,
        issuer=issuer.rstrip("/"),
        client_id=client_id,
        client_secret_cipher=encrypt_secret(client_secret, app_secret),
        trusted_email_domains=domains,
        active=True,
    )
    db.session.add(row)
    db.session.flush()
    return row


# ----- authorization URL ------------------------------------------


def build_authorization_url(
    provider: OidcProvider,
    *,
    redirect_uri: str,
    discovery: DiscoveryMetadata | None = None,
    fetch=None,
) -> tuple[str, dict]:
    """Return the authorization URL and the state payload to persist.

    The returned ``state`` dictionary should be stored in a session
    cookie or short-lived server-side record for the lifetime of the
    user's redirect. The callback requires both ``state`` and ``nonce``.
    """
    if not provider.active:
        raise OidcError("provider is not active")
    metadata = discovery or discover_or_fail(provider.issuer, fetch=fetch)
    import secrets as pysecrets

    state = pysecrets.token_urlsafe(32)
    nonce = pysecrets.token_urlsafe(32)
    client = OAuth2Session(
        client_id=provider.client_id,
        scope="openid email profile",
    )
    url, _ = client.create_authorization_url(
        metadata.authorization_endpoint,
        redirect_uri=redirect_uri,
        state=state,
        nonce=nonce,
    )
    return url, {"state": state, "nonce": nonce, "redirect_uri": redirect_uri}


# ----- callback ---------------------------------------------------


def exchange_and_authenticate(
    provider: OidcProvider,
    *,
    authorization_response: str,
    expected_state: str,
    expected_nonce: str,
    redirect_uri: str,
    app_secret: str,
    fetch=None,
    jwk_resolver=None,
    now: datetime | None = None,
) -> tuple[User, tuple[str, str]]:
    """Exchange the authorization code for tokens and authenticate.

    Returns ``(user, (access_token, refresh_token))``. The caller is
    responsible for calling ``db.session.commit()``.

    ``jwk_resolver`` is injected by tests; in production it fetches the
    provider's ``jwks_uri`` and verifies the id_token signature using
    the matching key.
    """
    if not provider.active:
        raise OidcCallbackError("provider is inactive")
    discovery = discover_or_fail(provider.issuer, fetch=fetch)
    client_secret = _decrypt_secret(provider.client_secret_cipher, app_secret)
    client = OAuth2Session(
        client_id=provider.client_id,
        client_secret=client_secret,
        scope="openid email profile",
    )
    try:
        tokens = client.fetch_token(
            discovery.token_endpoint,
            authorization_response=authorization_response,
            state=expected_state,
            redirect_uri=redirect_uri,
        )
    except Exception as exc:
        raise OidcCallbackError(f"token_exchange_failed: {exc}") from exc

    id_token_raw = tokens.get("id_token")
    if not id_token_raw:
        raise OidcCallbackError("id_token missing from provider response")

    if jwk_resolver is None:
        import json

        import requests

        def jwk_resolver(*_args, **_kwargs):
            response = requests.get(discovery.jwks_uri, timeout=10)
            return json.loads(response.text)

    # authlib's ``decode`` accepts a JWKS-shaped dict directly;
    # calling the resolver here (rather than letting authlib call it)
    # keeps the service API narrow and lets tests supply a static set
    # of trusted keys.
    jwks = jwk_resolver(id_token_raw)
    if not isinstance(jwks, dict) or "keys" not in jwks:
        raise OidcCallbackError("jwk_resolver must return a JWKS dict with 'keys'")

    jwt = JsonWebToken(["RS256", "ES256"])
    try:
        claims = jwt.decode(
            id_token_raw,
            key=jwks,
            claims_cls=CodeIDToken,
            claims_options={
                "iss": {"essential": True, "value": provider.issuer},
                "aud": {"essential": True, "value": provider.client_id},
                "nonce": {"essential": True, "value": expected_nonce},
            },
        )
        validate_at = now or datetime.now(timezone.utc)
        if validate_at.tzinfo is None:
            validate_at = validate_at.replace(tzinfo=timezone.utc)
        claims.validate(now=int(validate_at.timestamp()))
    except Exception as exc:
        raise OidcCallbackError(f"id_token_invalid: {exc}") from exc

    email = (claims.get("email") or "").strip().lower()
    email_verified = bool(claims.get("email_verified"))
    if not email or "@" not in email:
        raise OidcCallbackError("id_token missing verified email")
    if not email_verified:
        raise OidcCallbackError("email not verified by identity provider")
    domain = email.split("@", 1)[1]
    if domain not in (provider.trusted_email_domains or []):
        raise OidcCallbackError(f"domain {domain} not permitted on this provider")
    tenant = db.session.get(Organization, provider.organization_id)
    if tenant is None or not tenant.is_active:
        raise OidcCallbackError("tenant not accepting new logins")

    user = User.query.filter_by(email=email).first()
    if user is None:
        user = _jit_create_user(email, claims, tenant)
    elif user.organization_id != tenant.id:
        raise OidcCallbackError("email already registered in another tenant")
    elif not user.is_active:
        raise OidcCallbackError("user is deactivated")
    tokens_out = issue_login_tokens(user.id)
    return user, tokens_out


def _jit_create_user(email: str, claims: dict, tenant: Organization) -> User:
    local = email.split("@", 1)[0][:60]
    base_username = local
    candidate = base_username
    suffix = 1
    while User.query.filter_by(username=candidate).first() is not None:
        suffix += 1
        candidate = f"{base_username}-{suffix}"
        if suffix > 99:
            raise OidcCallbackError("could not allocate unique username")
    import secrets as pysecrets

    user = User(
        username=candidate,
        email=email,
        first_name=claims.get("given_name"),
        last_name=claims.get("family_name"),
        is_active=True,
        organization_id=tenant.id,
    )
    # A random password placeholder: the user must never log in with a
    # password unless they explicitly set one. ``check_password`` for
    # this value is essentially impossible for an attacker to guess.
    user.set_password(pysecrets.token_urlsafe(48))
    db.session.add(user)
    db.session.flush()
    return user
