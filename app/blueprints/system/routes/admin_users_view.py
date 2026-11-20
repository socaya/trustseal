"""Admin user roster + pending invitations (UI-P15.1).

Dedicated HTML view that renders and manages User + UserInvitation models
through the design-system shell. Admin-only; non-admins land on 403.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
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
    all_roles = Role.query.order_by(Role.name.asc()).all()

    return render_template(
        "admin/users.html",
        users=users,
        roles_by_user=roles_by_user,
        all_roles=all_roles,
        invitations=invitations,
        now=datetime.utcnow(),
    )


@admin_users_views.route("/invite", methods=["POST"])
@login_required
def invite_user():
    actor = _admin()
    email = (request.form.get("email") or "").strip().lower()[:120]
    role = (request.form.get("role") or "member").strip()[:20] or "member"
    if not email or "@" not in email:
        flash("Please enter a valid email address.", "error")
        return redirect(url_for("admin_users_views.index"))

    token = secrets.token_urlsafe(32)[:64]
    inv = UserInvitation(
        email=email,
        token=token,
        role=role,
        organization_id=actor.organization_id,
        invited_by_id=actor.id,
        expires_at=datetime.utcnow() + timedelta(days=7),
    )
    db.session.add(inv)
    db.session.commit()
    flash(f"Invitation created for {email} (role: {role}).", "success")
    return redirect(url_for("admin_users_views.index"))


@admin_users_views.route("/<int:user_id>/toggle-active", methods=["POST"])
@login_required
def toggle_user_active(user_id: int):
    actor = _admin()
    user = User.query.filter_by(id=user_id, organization_id=actor.organization_id).first()
    if user is None:
        abort(404)
    if user.id == actor.id:
        flash("You cannot deactivate your own account.", "error")
        return redirect(url_for("admin_users_views.index"))
    user.is_active = not bool(user.is_active)
    db.session.commit()
    flash(f'User "{user.email}" marked {"active" if user.is_active else "disabled"}.', "success")
    return redirect(url_for("admin_users_views.index"))


@admin_users_views.route("/<int:user_id>/role", methods=["POST"])
@login_required
def assign_user_role(user_id: int):
    actor = _admin()
    user = User.query.filter_by(id=user_id, organization_id=actor.organization_id).first()
    if user is None:
        abort(404)
    role_id = request.form.get("role_id", type=int)
    role = db.session.get(Role, role_id) if role_id else None
    if role is None:
        flash("Role not found.", "error")
        return redirect(url_for("admin_users_views.index"))
    existing = UserRole.query.filter_by(user_id=user.id, role_id=role.id).first()
    if existing:
        db.session.delete(existing)
        db.session.commit()
        flash(f'Removed role "{role.name}" from {user.email}.', "success")
    else:
        db.session.add(UserRole(user_id=user.id, role_id=role.id))
        db.session.commit()
        flash(f'Assigned role "{role.name}" to {user.email}.', "success")
    return redirect(url_for("admin_users_views.index"))


@admin_users_views.route("/invitations/<int:inv_id>/revoke", methods=["POST"])
@login_required
def revoke_invitation(inv_id: int):
    actor = _admin()
    inv = UserInvitation.query.filter_by(id=inv_id, organization_id=actor.organization_id).first()
    if inv is None:
        abort(404)
    email = inv.email
    db.session.delete(inv)
    db.session.commit()
    flash(f"Invitation for {email} revoked.", "success")
    return redirect(url_for("admin_users_views.index"))
