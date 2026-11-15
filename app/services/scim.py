"""SCIM 2.0 helpers: token minting, bearer-token authentication, and
user serialization.

Covers the subset Okta and Azure AD need to run a basic provisioning
job:

* ``mint_token(tenant_id, …)`` issues a SCIM bearer. The raw token is
  returned once; only its hash is persisted.
* ``authenticate(request)`` validates the ``Authorization`` header and
  returns the matching :class:`ScimServiceAccount`, or ``None``.
* ``user_to_scim(user)`` renders a :class:`User` as SCIM resource
  JSON.
* ``apply_create(payload, tenant_id)`` validates a SCIM user POST
  body and returns the User instance.
* ``apply_patch(user, payload)`` understands ``replace`` operations
  for ``active``, ``name.givenName``, ``name.familyName``, and
  ``emails[primary eq true].value``.

Pagination follows SCIM's ``startIndex`` / ``count`` convention.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime
from typing import Iterable

from flask import request

from app.extensions import db
from app.models.scim import ScimServiceAccount
from app.models.user import User

SCIM_USER_SCHEMA = "urn:ietf:params:scim:schemas:core:2.0:User"
SCIM_LIST_SCHEMA = "urn:ietf:params:scim:api:messages:2.0:ListResponse"
SCIM_ERROR_SCHEMA = "urn:ietf:params:scim:api:messages:2.0:Error"
SCIM_PATCH_SCHEMA = "urn:ietf:params:scim:api:messages:2.0:PatchOp"
TOKEN_SALT = b"trustseal/scim/token"


class ScimError(RuntimeError):
    """Domain-level SCIM failure with an HTTP status hint."""

    def __init__(self, message: str, *, status: int = 400):
        super().__init__(message)
        self.status = status


def _token_hash(token: str) -> str:
    return hashlib.sha256(TOKEN_SALT + token.encode("ascii")).hexdigest()


def mint_token(
    *,
    tenant_id: int,
    created_by_id: int,
    display_name: str,
) -> tuple[ScimServiceAccount, str]:
    if not isinstance(display_name, str) or not 1 <= len(display_name) <= 120:
        raise ScimError("display_name required")
    token = "scim_" + secrets.token_urlsafe(32)
    account = ScimServiceAccount(
        organization_id=tenant_id,
        created_by_id=created_by_id,
        display_name=display_name,
        token_hash=_token_hash(token),
        active=True,
    )
    db.session.add(account)
    db.session.flush()
    return account, token


def authenticate() -> ScimServiceAccount | None:
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        return None
    token = header[len("Bearer ") :].strip()
    if not token:
        return None
    digest = _token_hash(token)
    account = ScimServiceAccount.query.filter_by(
        token_hash=digest, active=True
    ).first()
    if account is None:
        return None
    # Record last-used for observability — not security.
    account.last_used_at = datetime.utcnow()
    db.session.flush()
    return account


def user_to_scim(user: User) -> dict:
    primary_email = (user.email or "").strip()
    return {
        "schemas": [SCIM_USER_SCHEMA],
        "id": str(user.id),
        "externalId": str(user.id),
        "userName": user.username,
        "name": {
            "givenName": user.first_name or "",
            "familyName": user.last_name or "",
        },
        "emails": [{"value": primary_email, "primary": True, "type": "work"}]
        if primary_email
        else [],
        "active": bool(user.is_active),
        "meta": {
            "resourceType": "User",
            "created": user.created_at.isoformat() if user.created_at else None,
        },
    }


def apply_create(payload: dict, tenant_id: int) -> User:
    if not isinstance(payload, dict):
        raise ScimError("payload must be a JSON object")
    if SCIM_USER_SCHEMA not in (payload.get("schemas") or []):
        raise ScimError("Users resource must declare the core User schema")
    username = str(payload.get("userName") or "").strip()
    if not username or len(username) > 64:
        raise ScimError("userName required")
    emails = payload.get("emails") or []
    primary_email = _primary_email(emails)
    if not primary_email:
        raise ScimError("primary emails[].value required")
    if User.query.filter(
        (User.username == username) | (User.email == primary_email)
    ).first():
        raise ScimError("conflict", status=409)
    name = payload.get("name") or {}
    user = User(
        username=username,
        email=primary_email,
        first_name=(name.get("givenName") or None),
        last_name=(name.get("familyName") or None),
        is_active=bool(payload.get("active", True)),
        organization_id=tenant_id,
    )
    user.set_password(secrets.token_urlsafe(48))
    db.session.add(user)
    db.session.flush()
    return user


def apply_patch(user: User, payload: dict) -> User:
    if (
        not isinstance(payload, dict)
        or SCIM_PATCH_SCHEMA not in (payload.get("schemas") or [])
    ):
        raise ScimError("PatchOp schema required")
    operations = payload.get("Operations") or []
    if not isinstance(operations, list) or not operations:
        raise ScimError("At least one PatchOp operation required")
    for op in operations:
        if not isinstance(op, dict):
            raise ScimError("operation must be a JSON object")
        verb = (op.get("op") or "").lower()
        path = op.get("path")
        value = op.get("value")
        if verb == "replace":
            _apply_replace(user, path, value)
        elif verb == "remove":
            _apply_remove(user, path)
        elif verb == "add":
            _apply_replace(user, path, value)
        else:
            raise ScimError(f"Unsupported patch verb {verb!r}")
    db.session.flush()
    return user


def _apply_replace(user: User, path, value) -> None:
    if path in (None, ""):
        if isinstance(value, dict):
            for inner_path, inner_value in value.items():
                _apply_replace(user, inner_path, inner_value)
            return
        raise ScimError("replace without path requires an object value")
    if path == "active":
        if not isinstance(value, bool):
            raise ScimError("active must be a boolean")
        user.is_active = value
        return
    if path == "name.givenName":
        user.first_name = str(value or "") or None
        return
    if path == "name.familyName":
        user.last_name = str(value or "") or None
        return
    if path == "emails[primary eq true].value":
        if not isinstance(value, str) or "@" not in value:
            raise ScimError("emails[primary eq true].value must be an email string")
        user.email = value.strip().lower()
        return
    raise ScimError(f"Unsupported path {path!r}")


def _apply_remove(user: User, path) -> None:
    if path == "name.givenName":
        user.first_name = None
        return
    if path == "name.familyName":
        user.last_name = None
        return
    raise ScimError(f"Unsupported remove path {path!r}")


def _primary_email(emails: Iterable) -> str | None:
    for entry in emails:
        if (
            isinstance(entry, dict)
            and entry.get("primary") is True
            and isinstance(entry.get("value"), str)
            and "@" in entry["value"]
        ):
            return entry["value"].strip().lower()
    # Fall back to the first well-formed email with a value.
    for entry in emails:
        if (
            isinstance(entry, dict)
            and isinstance(entry.get("value"), str)
            and "@" in entry["value"]
        ):
            return entry["value"].strip().lower()
    return None


def constant_time_equals(a: str, b: str) -> bool:
    return hmac.compare_digest(a, b)
