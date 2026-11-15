"""Session-scoped tenant propagation for PostgreSQL row-level security.

The migration ``h8e206f1c0a7`` enables RLS on trust-critical tables
and gates each row by a Postgres session variable
(``trustseal.current_tenant_id``). This module keeps that variable in
sync with the active caller:

* ``set_tenant(tenant_id)`` issues ``SET LOCAL
  trustseal.current_tenant_id = ...`` on the current session. "LOCAL"
  scopes the setting to the enclosing transaction so a pooled
  connection never inherits a prior request's tenant.
* ``clear_tenant()`` resets the variable to the empty string, which
  the ``trustseal_current_tenant()`` SQL function treats as NULL. A
  session with no tenant sees zero rows — fail-closed.
* The Flask ``before_request`` hook sets the variable from the JWT
  identity (or leaves it clear when the caller is anonymous).

The hook must run *after* ``flask_jwt_extended`` has decoded the
token but *before* any request handler queries the DB. In practice
we attach it inside a dedicated ``@app.before_request`` handler that
tolerates missing / invalid JWTs (returning without raising so
public verification and signer landing paths still work).

RLS is defence in depth, not a replacement for the application-layer
``TenantScopedRepository``. It catches bugs that forget to filter on
``organization_id``; application code is still expected to be
correct.
"""
from __future__ import annotations

from typing import Optional

from flask import Flask, g, request
from sqlalchemy import text

from app.extensions import db


def set_tenant(tenant_id: int | None) -> None:
    """Propagate the active tenant id to the Postgres session.

    ``tenant_id`` is coerced to ``int`` to avoid SQL injection via a
    string-valued claim.
    """
    if tenant_id is None:
        db.session.execute(
            text("SELECT set_config('trustseal.current_tenant_id', '', true)")
        )
        return
    coerced = int(tenant_id)
    db.session.execute(
        text(
            "SELECT set_config('trustseal.current_tenant_id', :value, true)"
        ),
        {"value": str(coerced)},
    )


def clear_tenant() -> None:
    set_tenant(None)


def active_tenant() -> Optional[int]:
    """Read the current session variable (useful in tests)."""
    row = db.session.execute(
        text("SELECT current_setting('trustseal.current_tenant_id', true)")
    ).scalar()
    if row is None or row == "":
        return None
    try:
        return int(row)
    except (TypeError, ValueError):
        return None


def _resolve_tenant_from_request() -> Optional[int]:
    """Return the caller's tenant id for the active request.

    The hook runs after the app's authentication ``before_request``
    chain, so ``current_user`` is already loaded for session-cookie
    callers and ``get_jwt()`` for API callers. Both sources avoid
    issuing their own DB query from this hook — the lookup is already
    cached on the request.

    Anonymous callers return ``None`` so RLS sees no rows.
    """
    try:
        from flask_login import current_user

        if (
            current_user is not None
            and getattr(current_user, "is_authenticated", False)
            and getattr(current_user, "organization_id", None) is not None
        ):
            return int(current_user.organization_id)
    except Exception:
        pass
    try:
        from flask_jwt_extended import get_jwt

        claims = get_jwt()
        tenant = claims.get("organization_id") or claims.get("tenant_id")
        if tenant is not None:
            return int(tenant)
    except Exception:
        pass
    return None


_HOOK_INSTALLED = False


def register_rls_hook(app: Flask) -> None:
    """Install the per-request tenant propagation hook.

    Idempotent — repeated factory calls keep a single hook.
    """
    global _HOOK_INSTALLED
    if _HOOK_INSTALLED:
        return

    @app.before_request
    def _propagate_tenant() -> None:
        # Skip for static assets so server-side rendering avoids a
        # redundant DB round trip.
        if request.endpoint == "static":
            return
        tenant_id = _resolve_tenant_from_request()
        g._trustseal_rls_tenant = tenant_id
        try:
            set_tenant(tenant_id)
        except Exception:
            # A failed set_config must not break request handling for
            # public endpoints. The RLS policy is still fail-closed so
            # callers hit "no rows" rather than seeing another tenant.
            try:
                clear_tenant()
            except Exception:
                pass

    @app.teardown_request
    def _reset_tenant(_exc=None) -> None:
        try:
            clear_tenant()
        except Exception:
            pass

    _HOOK_INSTALLED = True
