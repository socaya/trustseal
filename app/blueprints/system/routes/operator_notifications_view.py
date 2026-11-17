"""Operator notifications HTML view (Phase W1 + UI-P4.1)."""
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
from app.services import operator_notifications as notifications


operator_notifications_views = Blueprint(
    "operator_notifications_views",
    __name__,
    url_prefix="/app/notifications",
)


def _actor():
    if not current_user.is_authenticated or current_user.organization_id is None:
        abort(403)
    return current_user


@operator_notifications_views.route("", methods=["GET"])
@login_required
def list_notifications():
    user = _actor()
    unread_only = request.args.get("unread") == "1"
    kind = request.args.get("kind") or None
    rows = notifications.list_for(
        recipient_user_id=user.id,
        organization_id=user.organization_id,
        unread_only=unread_only,
        kind=kind,
        limit=200,
    )
    unread_count = notifications.count_unread(
        recipient_user_id=user.id,
        organization_id=user.organization_id,
    )
    return render_template(
        "system/notifications.html",
        rows=rows,
        unread_only=unread_only,
        kind=kind,
        unread_count=unread_count,
    )


@operator_notifications_views.route("/<int:notification_id>/read", methods=["POST"])
@login_required
def mark_read(notification_id: int):
    user = _actor()
    notifications.mark_read(
        notification_id=notification_id,
        recipient_user_id=user.id,
        organization_id=user.organization_id,
    )
    db.session.commit()
    return redirect(request.referrer or url_for("operator_notifications_views.list_notifications"))


@operator_notifications_views.route("/read-all", methods=["POST"])
@login_required
def mark_all_read():
    user = _actor()
    n = notifications.mark_all_read(
        recipient_user_id=user.id,
        organization_id=user.organization_id,
    )
    db.session.commit()
    flash(f"Marked {n} notification{'s' if n != 1 else ''} as read.", "success")
    return redirect(url_for("operator_notifications_views.list_notifications"))
