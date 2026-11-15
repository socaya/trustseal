"""Per-resource authorization policy.

Pure predicates and a ``@require_policy`` decorator that compose with the
interim ``enforce_legacy_api_security`` guard. Policies NEVER query the
database directly — callers resolve the resource through a tenant-scoped
repository (``app/repositories/``), then pass the loaded resource to the
predicate. This keeps policy testable in isolation and keeps tenant
scoping in one place.

Convention: when a loader returns ``None`` (resource absent OR present in
another tenant), the decorator returns HTTP 404. 403 is only used when the
resource exists in the caller's tenant but the predicate denies. This is
anti-enumeration behaviour; see ADR 0003.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import wraps
from typing import Any, Callable, Optional

from flask import abort, g, request
from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request

from app.extensions import db
from app.models.system import Role, UserRole
from app.models.user import User


@dataclass(frozen=True)
class Actor:
    """Authenticated caller bound to a tenant.

    ``roles`` is the lower-cased set of global role names. Tenant membership
    is represented by ``tenant_id`` (currently ``User.organization_id`` in the
    legacy schema; a dedicated Membership model lands with the tenancy refactor).
    """

    user_id: int
    tenant_id: Optional[int]
    roles: frozenset[str]
    is_active: bool

    def has_role(self, *names: str) -> bool:
        return bool(self.roles.intersection(n.lower() for n in names))


_PRIVILEGED = frozenset(("admin", "administrator", "superadmin", "super_admin"))


def _load_actor() -> Actor:
    verify_jwt_in_request()
    try:
        user_id = int(get_jwt_identity())
    except (TypeError, ValueError):
        abort(401)
    user = User.query.get(user_id)
    if user is None or not user.is_active:
        abort(401)
    roles = {
        name.strip().lower()
        for (name,) in db.session.query(Role.name)
        .join(UserRole, UserRole.role_id == Role.id)
        .filter(UserRole.user_id == user.id)
        .all()
        if name
    }
    return Actor(
        user_id=user.id,
        tenant_id=user.organization_id,
        roles=frozenset(roles),
        is_active=bool(user.is_active),
    )


def current_actor() -> Actor:
    actor = getattr(g, "_trustseal_actor", None)
    if actor is None:
        actor = _load_actor()
        g._trustseal_actor = actor
    return actor


# --- Predicates ---------------------------------------------------------
#
# Each predicate takes an already-loaded resource plus the actor and returns
# a bool. The decorator is responsible for loading (through a tenant-scoped
# repository) and for returning 404 when the loader yields None.

def can_read(actor: Actor, resource: Any) -> bool:
    if not actor.is_active:
        return False
    if actor.has_role(*_PRIVILEGED):
        return True
    owner = getattr(resource, "created_by", None) or getattr(resource, "created_by_id", None)
    if owner is not None and owner == actor.user_id:
        return True
    tenant = getattr(resource, "organization_id", None) or getattr(resource, "tenant_id", None)
    return tenant is not None and tenant == actor.tenant_id


def can_write(actor: Actor, resource: Any, op: str) -> bool:
    if not actor.is_active:
        return False
    if actor.has_role(*_PRIVILEGED):
        return True
    owner = getattr(resource, "created_by", None) or getattr(resource, "created_by_id", None)
    return owner is not None and owner == actor.user_id


def can_sign(actor: Actor, envelope: Any, participant: Any) -> bool:
    if not actor.is_active:
        return False
    if getattr(participant, "user_id", None) != actor.user_id:
        return False
    if getattr(envelope, "organization_id", None) != actor.tenant_id:
        return False
    return getattr(envelope, "state", None) in {"prepared", "active"}


def can_admin(actor: Actor, tenant_id: Optional[int]) -> bool:
    if not actor.is_active:
        return False
    if actor.has_role(*_PRIVILEGED):
        return True
    return tenant_id is not None and tenant_id == actor.tenant_id and actor.has_role("tenant_admin")


_PREDICATES: dict[str, Callable[..., bool]] = {
    "can_read": can_read,
    "can_write": can_write,
    "can_sign": can_sign,
    "can_admin": can_admin,
}


# --- Decorator ----------------------------------------------------------

def require_policy(
    predicate: str,
    loader: Callable[..., Any] | None = None,
    *,
    op: str = "write",
):
    """Enforce a policy predicate for the decorated route.

    ``loader`` receives the route's view kwargs and the resolved ``Actor``.
    It MUST query through a tenant-scoped repository so that resources in
    other tenants return ``None`` (producing an anti-enumeration 404).

    For predicates that do not need a resource (``can_admin`` on the current
    tenant), pass ``loader=None`` and the decorator calls the predicate with
    just the actor and ``actor.tenant_id``.
    """
    if predicate not in _PREDICATES:
        raise ValueError(f"unknown predicate: {predicate}")
    fn = _PREDICATES[predicate]

    def wrap(view):
        @wraps(view)
        def inner(*args, **kwargs):
            actor = current_actor()
            if loader is None:
                allowed = fn(actor, actor.tenant_id) if predicate == "can_admin" else fn(actor)
                if not allowed:
                    abort(403)
                return view(*args, **kwargs)
            resource = loader(actor=actor, **kwargs)
            if resource is None:
                abort(404)
            if predicate == "can_write":
                allowed = fn(actor, resource, op)
            elif predicate == "can_sign":
                envelope, participant = resource
                allowed = fn(actor, envelope, participant)
            else:
                allowed = fn(actor, resource)
            if not allowed:
                abort(403)
            g._trustseal_resource = resource
            return view(*args, **kwargs)

        return inner

    return wrap


def loaded_resource() -> Any:
    """Return the resource populated by the most recent ``require_policy``."""
    return getattr(g, "_trustseal_resource", None)
