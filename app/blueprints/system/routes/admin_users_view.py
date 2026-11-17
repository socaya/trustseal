"""Admin user roster + pending invitations (UI-P15.1).

Dedicated HTML view that renders the User + UserInvitation models
through the design-system shell. Admin-only; non-admins land on 403.
"""
from __future__ import annotations

from datetime import datetime, timezone

from flask import Blueprint, abort, render_template
from flask_login import current_user, login_required

from app.extensions import db
from app.models.system import Role, UserRole
from app.models.user import User, UserInvitation
from app.policies.api_access import is_admin


admin_users_views = Blueprint(
    "admin_users_views", __name__, url_prefix="/admin/users"
)


def _admin():
    if not current_user.is_authenticated:
        abort(401)
    if current_user.organization_id is None:
        abort(403, description="organization_required")
    if not is_admin(current_user.id):
        abort(403, description="admin_required")
    return current_user


@admin_users_views.route("", methods=["GET"])
@login_required
def index():
    actor = _admin()

    users = (
        User.query.filter_by(organization_id=actor.organization_id)
        .order_by(User.id.asc())
        .all()
    )

    # Preload role names per user so the table can render them without
    # N+1 queries.
    user_roles = (
        db.session.query(UserRole.user_id, Role.name)
        .join(Role, Role.id == UserRole.role_id)
        .all()
    )
    roles_by_user: dict[int, list[str]] = {}
    for user_id, role_name in user_roles:
        roles_by_user.setdefault(user_id, []).append(role_name)

    invitations = (
        UserInvitation.query.filter_by(organization_id=actor.organization_id)
        .order_by(UserInvitation.id.desc())
        .limit(200)
        .all()
    )

    return render_template(
        "admin/users.html",
        users=users,
        roles_by_user=roles_by_user,
        invitations=invitations,
        now=datetime.now(timezone.utc),
    )
