"""SCIM 2.0 Users endpoint.

The surface is intentionally narrow. It implements the subset that
Okta, Azure AD, and OneLogin need to run a user-provisioning
connector:

* ``GET /scim/v2/Users`` — list (paginated).
* ``POST /scim/v2/Users`` — create (JIT-provisioned local user).
* ``GET /scim/v2/Users/<id>`` — fetch a single user.
* ``PATCH /scim/v2/Users/<id>`` — ``replace``/``remove``/``add`` on
  ``active``, ``name.*``, and primary email.
* ``DELETE /scim/v2/Users/<id>`` — soft-delete by deactivating.

Every request requires a tenant-scoped SCIM bearer token minted
through :func:`app.services.scim.mint_token`. Cross-tenant access is
impossible because the authenticated :class:`ScimServiceAccount`
carries the tenant id that every query is scoped to.
"""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from app.extensions import db
from app.models.user import User
from app.services import scim as scim_service

scim_api = Blueprint("scim_api", __name__, url_prefix="/scim/v2")


def _error(detail: str, status: int) -> tuple:
    body = {
        "schemas": [scim_service.SCIM_ERROR_SCHEMA],
        "status": str(status),
        "detail": detail,
    }
    response = jsonify(body)
    response.status_code = status
    response.content_type = "application/scim+json"
    return response


def _scim_response(payload, status: int = 200):
    response = jsonify(payload)
    response.status_code = status
    response.content_type = "application/scim+json"
    return response


def _authenticate_or_401():
    account = scim_service.authenticate()
    if account is None:
        return None, _error("unauthenticated", 401)
    return account, None


@scim_api.route("/Users", methods=["GET"])
def list_users():
    account, err = _authenticate_or_401()
    if err is not None:
        return err
    try:
        start = max(1, int(request.args.get("startIndex", 1)))
    except ValueError:
        return _error("startIndex must be int", 400)
    try:
        count = max(1, min(200, int(request.args.get("count", 100))))
    except ValueError:
        return _error("count must be int", 400)
    query = User.query.filter_by(organization_id=account.organization_id)
    total = query.count()
    rows = (
        query.order_by(User.id.asc())
        .offset(start - 1)
        .limit(count)
        .all()
    )
    return _scim_response(
        {
            "schemas": [scim_service.SCIM_LIST_SCHEMA],
            "totalResults": int(total),
            "startIndex": start,
            "itemsPerPage": len(rows),
            "Resources": [scim_service.user_to_scim(r) for r in rows],
        }
    )


@scim_api.route("/Users", methods=["POST"])
def create_user():
    account, err = _authenticate_or_401()
    if err is not None:
        return err
    payload = request.get_json(silent=True)
    try:
        user = scim_service.apply_create(payload or {}, account.organization_id)
    except scim_service.ScimError as exc:
        return _error(str(exc), exc.status)
    db.session.commit()
    response = _scim_response(scim_service.user_to_scim(user), status=201)
    response.headers["Location"] = f"/scim/v2/Users/{user.id}"
    return response


@scim_api.route("/Users/<int:user_id>", methods=["GET"])
def get_user(user_id: int):
    account, err = _authenticate_or_401()
    if err is not None:
        return err
    user = User.query.filter_by(
        id=user_id, organization_id=account.organization_id
    ).first()
    if user is None:
        return _error("user not found", 404)
    return _scim_response(scim_service.user_to_scim(user))


@scim_api.route("/Users/<int:user_id>", methods=["PATCH"])
def patch_user(user_id: int):
    account, err = _authenticate_or_401()
    if err is not None:
        return err
    user = User.query.filter_by(
        id=user_id, organization_id=account.organization_id
    ).first()
    if user is None:
        return _error("user not found", 404)
    payload = request.get_json(silent=True)
    try:
        scim_service.apply_patch(user, payload or {})
    except scim_service.ScimError as exc:
        return _error(str(exc), exc.status)
    db.session.commit()
    return _scim_response(scim_service.user_to_scim(user))


@scim_api.route("/Users/<int:user_id>", methods=["PUT"])
def replace_user(user_id: int):
    """Replace ``active``, ``name``, and emails. Other fields are read-only."""
    account, err = _authenticate_or_401()
    if err is not None:
        return err
    user = User.query.filter_by(
        id=user_id, organization_id=account.organization_id
    ).first()
    if user is None:
        return _error("user not found", 404)
    payload = request.get_json(silent=True) or {}
    patch = {
        "schemas": [scim_service.SCIM_PATCH_SCHEMA],
        "Operations": [],
    }
    name = payload.get("name") or {}
    if "givenName" in name:
        patch["Operations"].append(
            {"op": "replace", "path": "name.givenName", "value": name["givenName"]}
        )
    if "familyName" in name:
        patch["Operations"].append(
            {"op": "replace", "path": "name.familyName", "value": name["familyName"]}
        )
    primary = scim_service._primary_email(payload.get("emails") or [])
    if primary:
        patch["Operations"].append(
            {
                "op": "replace",
                "path": "emails[primary eq true].value",
                "value": primary,
            }
        )
    if "active" in payload:
        patch["Operations"].append(
            {"op": "replace", "path": "active", "value": bool(payload["active"])}
        )
    try:
        scim_service.apply_patch(user, patch)
    except scim_service.ScimError as exc:
        return _error(str(exc), exc.status)
    db.session.commit()
    return _scim_response(scim_service.user_to_scim(user))


@scim_api.route("/Users/<int:user_id>", methods=["DELETE"])
def delete_user(user_id: int):
    """Soft-delete by marking the user inactive (SCIM-preferred)."""
    account, err = _authenticate_or_401()
    if err is not None:
        return err
    user = User.query.filter_by(
        id=user_id, organization_id=account.organization_id
    ).first()
    if user is None:
        return _error("user not found", 404)
    user.is_active = False
    db.session.commit()
    return ("", 204)
