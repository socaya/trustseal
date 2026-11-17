"""Operator profile HTML view (UI-P10.2).

Thin wrapper around the Phase AG1 ``PATCH /api/auth/me`` service — the
HTML form POSTs, and we call the same User model update under the
hood so there is no drift between surfaces. Email, username and
password are deliberately read-only here; those changes keep their
dedicated flows.
"""
from __future__ import annotations

from flask import (
    Blueprint,
    abort,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required

from app.extensions import db
from app.models.user import User


profile_views = Blueprint(
    "profile_views", __name__, url_prefix="/app/profile"
)


def _actor() -> User:
    if not current_user.is_authenticated or current_user.organization_id is None:
        abort(403)
    user = db.session.get(User, current_user.id)
    if user is None:
        abort(404)
    return user


@profile_views.route("", methods=["GET"])
@login_required
def show():
    user = _actor()
    return render_template(
        "auth/profile.html",
        user=user,
        changed_fields=request.args.get("changed", ""),
    )


@profile_views.route("", methods=["POST"])
@login_required
def update():
    user = _actor()
    changed = []
    for field in ("first_name", "last_name", "phone"):
        raw = request.form.get(field, "").strip()
        value = raw or None
        if value is not None and len(value) > 80:
            flash(f"{field.replace('_', ' ').capitalize()} is too long.", "danger")
            return redirect(url_for("profile_views.show"))
        if getattr(user, field) != value:
            setattr(user, field, value)
            changed.append(field)
    db.session.commit()
    if changed:
        flash(
            "Updated " + ", ".join(f.replace("_", " ") for f in changed) + ".",
            "success",
        )
    else:
        flash("No changes to save.", "info")
    return redirect(url_for("profile_views.show"))
