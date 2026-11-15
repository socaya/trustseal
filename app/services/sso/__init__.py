"""Single sign-on adapters.

:mod:`oidc` provides a tenant-scoped OIDC authentication flow using
``authlib``'s OAuth2 client. SAML is deferred to a follow-up adapter.
"""
from .oidc import (
    OidcCallbackError,
    OidcError,
    build_authorization_url,
    discover_or_fail,
    encrypt_secret,
    exchange_and_authenticate,
    register_provider,
)

__all__ = [
    "OidcError",
    "OidcCallbackError",
    "build_authorization_url",
    "discover_or_fail",
    "encrypt_secret",
    "exchange_and_authenticate",
    "register_provider",
]
