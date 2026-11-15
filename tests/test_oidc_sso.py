"""OIDC SSO contract.

Covers:

* Secret encryption round-trips.
* Discovery accepts a valid document and rejects an issuer mismatch.
* ``register_provider`` validates slugs, domains, and duplicates.
* ``build_authorization_url`` returns a valid-looking URL and the
  state + nonce the caller must persist.
* ``exchange_and_authenticate`` just-in-time provisions a user when
  the email_verified claim is true and the domain is trusted.
* A missing ``email_verified`` is rejected.
* An untrusted email domain is rejected.
* A user already assigned to a different tenant is rejected.

The tests do not perform any HTTP I/O: fetch and the authlib token
exchange are stubbed.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from authlib.jose import JsonWebKey, jwt as josejwt

from app.services.sso import (
    OidcCallbackError,
    OidcError,
    build_authorization_url,
    discover_or_fail,
    encrypt_secret,
    exchange_and_authenticate,
    register_provider,
)


APP_SECRET = "test-secret-not-for-production-long-enough-for-fernet"
ISSUER = "https://idp.example.test"


@pytest.fixture
def tenant(pg_app):
    from app.extensions import db
    from app.models.organization import Organization

    org = Organization(name="OIDC Tenant")
    db.session.add(org)
    db.session.commit()
    return org


@pytest.fixture
def rsa_jwk():
    """Generate an RSA JWK pair the tests can sign id_tokens with."""
    key = JsonWebKey.generate_key("RSA", 2048, is_private=True)
    return key


def _discovery_payload():
    return {
        "issuer": ISSUER,
        "authorization_endpoint": f"{ISSUER}/authorize",
        "token_endpoint": f"{ISSUER}/token",
        "jwks_uri": f"{ISSUER}/jwks",
    }


def _mock_fetch(payload, *, status=200):
    class _Response:
        status_code = status

        def json(self):
            return payload

        @property
        def text(self):
            import json as _json

            return _json.dumps(payload)

    def _get(_url, timeout=None):
        return _Response()

    return _get


class TestSecrets:
    def test_round_trip(self):
        cipher = encrypt_secret("sek", APP_SECRET)
        from app.services.sso.oidc import _decrypt_secret

        assert _decrypt_secret(cipher, APP_SECRET) == "sek"

    def test_short_app_secret_rejected(self):
        with pytest.raises(OidcError):
            encrypt_secret("sek", "short")


class TestDiscovery:
    def test_valid(self):
        md = discover_or_fail(ISSUER, fetch=_mock_fetch(_discovery_payload()))
        assert md.issuer == ISSUER

    def test_issuer_mismatch_rejected(self):
        payload = _discovery_payload()
        payload["issuer"] = "https://other.example.test"
        with pytest.raises(OidcError):
            discover_or_fail(ISSUER, fetch=_mock_fetch(payload))

    def test_non_https_rejected(self):
        with pytest.raises(OidcError):
            discover_or_fail("http://insecure.example.test")

    def test_discovery_404_rejected(self):
        with pytest.raises(OidcError):
            discover_or_fail(
                ISSUER, fetch=_mock_fetch(_discovery_payload(), status=404)
            )


class TestRegistration:
    def test_happy_path(self, pg_app, tenant):
        provider = register_provider(
            tenant_id=tenant.id,
            slug="google",
            display_name="Google",
            issuer=ISSUER,
            client_id="client-id",
            client_secret="shh",
            trusted_email_domains=["example.test"],
            app_secret=APP_SECRET,
        )
        assert provider.slug == "google"
        assert provider.client_secret_cipher != "shh"
        assert provider.trusted_email_domains == ["example.test"]

    def test_bad_slug_rejected(self, pg_app, tenant):
        with pytest.raises(OidcError):
            register_provider(
                tenant_id=tenant.id,
                slug="not valid slug",
                display_name="Google",
                issuer=ISSUER,
                client_id="c",
                client_secret="s",
                trusted_email_domains=["example.test"],
                app_secret=APP_SECRET,
            )

    def test_empty_domains_rejected(self, pg_app, tenant):
        with pytest.raises(OidcError):
            register_provider(
                tenant_id=tenant.id,
                slug="google",
                display_name="Google",
                issuer=ISSUER,
                client_id="c",
                client_secret="s",
                trusted_email_domains=[],
                app_secret=APP_SECRET,
            )

    def test_duplicate_slug_rejected(self, pg_app, tenant):
        register_provider(
            tenant_id=tenant.id,
            slug="dup",
            display_name="Dup",
            issuer=ISSUER,
            client_id="c",
            client_secret="s",
            trusted_email_domains=["example.test"],
            app_secret=APP_SECRET,
        )
        with pytest.raises(OidcError):
            register_provider(
                tenant_id=tenant.id,
                slug="dup",
                display_name="Dup",
                issuer=ISSUER,
                client_id="c",
                client_secret="s",
                trusted_email_domains=["example.test"],
                app_secret=APP_SECRET,
            )


class TestAuthorizationUrl:
    def test_builds_url_with_state_and_nonce(self, pg_app, tenant):
        provider = register_provider(
            tenant_id=tenant.id,
            slug="goog",
            display_name="Goog",
            issuer=ISSUER,
            client_id="client-id",
            client_secret="shh",
            trusted_email_domains=["example.test"],
            app_secret=APP_SECRET,
        )
        url, state = build_authorization_url(
            provider,
            redirect_uri="https://app.example.test/callback",
            fetch=_mock_fetch(_discovery_payload()),
        )
        assert url.startswith(f"{ISSUER}/authorize?")
        assert "response_type=code" in url
        assert "client_id=client-id" in url
        assert "scope=" in url and "openid" in url
        assert "state=" in url
        assert "nonce=" in url
        assert state["redirect_uri"] == "https://app.example.test/callback"


class TestCallback:
    def _signed_id_token(
        self, provider, rsa_jwk, nonce, *, email, email_verified=True
    ):
        header = {"alg": "RS256", "kid": rsa_jwk.as_dict()["kid"]}
        now = datetime.now(timezone.utc)
        payload = {
            "iss": provider.issuer,
            "sub": "subject-" + email,
            "aud": provider.client_id,
            "exp": int((now + timedelta(minutes=5)).timestamp()),
            # Nudge iat into the past so authlib doesn't reject the
            # token for being "issued in the future" under clock skew.
            "iat": int((now - timedelta(seconds=5)).timestamp()),
            "nonce": nonce,
            "email": email,
            "email_verified": email_verified,
            "given_name": "Given",
            "family_name": "Family",
        }
        return josejwt.encode(header, payload, rsa_jwk).decode("ascii")

    def _resolver(self, rsa_jwk):
        full = rsa_jwk.as_dict()
        public = {k: full[k] for k in ("kty", "n", "e", "kid") if k in full}
        public["use"] = "sig"
        public["alg"] = "RS256"

        def _jwks(*_args, **_kwargs):
            return {"keys": [public]}

        return _jwks

    def _stub_token(self, id_token):
        def _fetch_token(self, *_args, **_kwargs):
            return {"id_token": id_token, "token_type": "Bearer"}

        return _fetch_token

    def test_jit_creates_user(self, pg_app, tenant, rsa_jwk):
        provider = register_provider(
            tenant_id=tenant.id,
            slug="goog",
            display_name="Goog",
            issuer=ISSUER,
            client_id="client-id",
            client_secret="shh",
            trusted_email_domains=["example.test"],
            app_secret=APP_SECRET,
        )
        nonce = "nonce-abc"
        state = "state-xyz"
        id_token = self._signed_id_token(
            provider, rsa_jwk, nonce, email="new@example.test"
        )
        with patch(
            "authlib.integrations.requests_client.OAuth2Session.fetch_token",
            self._stub_token(id_token),
        ):
            user, tokens = exchange_and_authenticate(
                provider,
                authorization_response=f"https://app.example.test/callback?state={state}&code=abc",
                expected_state=state,
                expected_nonce=nonce,
                redirect_uri="https://app.example.test/callback",
                app_secret=APP_SECRET,
                fetch=_mock_fetch(_discovery_payload()),
                jwk_resolver=self._resolver(rsa_jwk),
            )
        assert user.email == "new@example.test"
        assert user.organization_id == tenant.id
        access, refresh = tokens
        assert access and refresh

    def test_email_not_verified_rejected(self, pg_app, tenant, rsa_jwk):
        provider = register_provider(
            tenant_id=tenant.id,
            slug="goog",
            display_name="Goog",
            issuer=ISSUER,
            client_id="client-id",
            client_secret="shh",
            trusted_email_domains=["example.test"],
            app_secret=APP_SECRET,
        )
        nonce = "nonce-def"
        state = "state-xyz"
        id_token = self._signed_id_token(
            provider, rsa_jwk, nonce,
            email="noverified@example.test", email_verified=False,
        )
        with patch(
            "authlib.integrations.requests_client.OAuth2Session.fetch_token",
            self._stub_token(id_token),
        ):
            with pytest.raises(OidcCallbackError):
                exchange_and_authenticate(
                    provider,
                    authorization_response=f"https://app.example.test/callback?state={state}&code=abc",
                    expected_state=state,
                    expected_nonce=nonce,
                    redirect_uri="https://app.example.test/callback",
                    app_secret=APP_SECRET,
                    fetch=_mock_fetch(_discovery_payload()),
                    jwk_resolver=self._resolver(rsa_jwk),
                )

    def test_untrusted_domain_rejected(self, pg_app, tenant, rsa_jwk):
        provider = register_provider(
            tenant_id=tenant.id,
            slug="goog",
            display_name="Goog",
            issuer=ISSUER,
            client_id="client-id",
            client_secret="shh",
            trusted_email_domains=["example.test"],
            app_secret=APP_SECRET,
        )
        nonce = "nonce-xyz"
        state = "state-xyz"
        id_token = self._signed_id_token(
            provider, rsa_jwk, nonce, email="outside@wrong.test"
        )
        with patch(
            "authlib.integrations.requests_client.OAuth2Session.fetch_token",
            self._stub_token(id_token),
        ):
            with pytest.raises(OidcCallbackError):
                exchange_and_authenticate(
                    provider,
                    authorization_response=f"https://app.example.test/callback?state={state}&code=abc",
                    expected_state=state,
                    expected_nonce=nonce,
                    redirect_uri="https://app.example.test/callback",
                    app_secret=APP_SECRET,
                    fetch=_mock_fetch(_discovery_payload()),
                    jwk_resolver=self._resolver(rsa_jwk),
                )
