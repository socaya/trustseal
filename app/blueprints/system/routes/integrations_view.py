"""Admin view: webhook endpoints + their recent deliveries.

Supports registering endpoints, rotating signing secrets (shown once),
enabling/disabling, and deleting endpoints directly from the workspace UI.
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timezone

from flask import Blueprint, abort, flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required
from sqlalchemy import desc, func

from app.extensions import db
from app.models.user import User
from app.models.webhook import WebhookDelivery, WebhookEndpoint
from app.policies.api_access import is_admin


integrations_views = Blueprint(
    "integrations_views", __name__, url_prefix="/admin/integrations"
)


def _admin():
    if not current_user.is_authenticated:
        abort(401)
    if current_user.organization_id is None:
        abort(403, description="organization_required")
    if not is_admin(current_user.id):
        abort(403, description="admin_required")
    return current_user


def _new_secret() -> tuple[str, str]:
    raw = "whsec_" + secrets.token_urlsafe(32)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return raw, digest


@integrations_views.route("", methods=["GET"])
@login_required
def index():
    actor = _admin()

    endpoints = (
        WebhookEndpoint.query
        .filter_by(organization_id=actor.organization_id)
        .order_by(WebhookEndpoint.id.desc())
        .all()
    )
    creator_ids = {e.created_by_id for e in endpoints if e.created_by_id}
    creators = {
        u.id: u
        for u in User.query.filter(User.id.in_(creator_ids)).all()
    } if creator_ids else {}

    deliveries = (
        WebhookDelivery.query
        .filter_by(organization_id=actor.organization_id)
        .order_by(desc(WebhookDelivery.id))
        .limit(100)
        .all()
    )

    counts_by_status = {
        row.status: row.n
        for row in db.session.query(
            WebhookDelivery.status, func.count().label("n")
        )
        .filter(WebhookDelivery.organization_id == actor.organization_id)
        .group_by(WebhookDelivery.status)
        .all()
    }

    revealed_secret = session.pop("new_webhook_secret", None)

    return render_template(
        "admin/integrations.html",
        endpoints=endpoints,
        creators=creators,
        deliveries=deliveries,
        counts_by_status=counts_by_status,
        revealed_secret=revealed_secret,
        now=datetime.now(timezone.utc),
    )


@integrations_views.route("/create", methods=["POST"])
@login_required
def create_endpoint():
    actor = _admin()
    url = (request.form.get("url") or "").strip()[:512]
    desc_text = (request.form.get("description") or "").strip()[:200]
    events_raw = (request.form.get("events") or "").strip()
    events = [e.strip() for e in events_raw.split(",") if e.strip()] or ["*"]

    if not url or not (url.startswith("https://") or url.startswith("http://")):
        flash("Please enter a valid http(s):// webhook URL.", "error")
        return redirect(url_for("integrations_views.index"))

    existing = WebhookEndpoint.query.filter_by(
        organization_id=actor.organization_id, url=url
    ).first()
    if existing:
        flash("A webhook endpoint with this URL already exists.", "warning")
        return redirect(url_for("integrations_views.index"))

    raw_secret, digest = _new_secret()
    ep = WebhookEndpoint(
        organization_id=actor.organization_id,
        created_by_id=actor.id,
        url=url,
        secret_hash=digest,
        events=events,
        active=True,
        description=desc_text or None,
    )
    db.session.add(ep)
    db.session.commit()
    session["new_webhook_secret"] = {"url": url, "secret": raw_secret}
    flash("Webhook endpoint registered. Copy the signing secret below — it is shown only once.", "success")
    return redirect(url_for("integrations_views.index"))


@integrations_views.route("/<int:ep_id>/rotate", methods=["POST"])
@login_required
def rotate_endpoint(ep_id: int):
    actor = _admin()
    ep = WebhookEndpoint.query.filter_by(
        id=ep_id, organization_id=actor.organization_id
    ).first()
    if ep is None:
        abort(404)
    raw_secret, digest = _new_secret()
    ep.secret_hash = digest
    db.session.commit()
    session["new_webhook_secret"] = {"url": ep.url, "secret": raw_secret}
    flash(f"Signing secret rotated for endpoint #{ep.id}.", "success")
    return redirect(url_for("integrations_views.index"))


@integrations_views.route("/<int:ep_id>/toggle", methods=["POST"])
@login_required
def toggle_endpoint(ep_id: int):
    actor = _admin()
    ep = WebhookEndpoint.query.filter_by(
        id=ep_id, organization_id=actor.organization_id
    ).first()
    if ep is None:
        abort(404)
    ep.active = not bool(ep.active)
    db.session.commit()
    flash(f'Endpoint #{ep.id} {"enabled" if ep.active else "disabled"}.', "success")
    return redirect(url_for("integrations_views.index"))


@integrations_views.route("/<int:ep_id>/delete", methods=["POST"])
@login_required
def delete_endpoint(ep_id: int):
    actor = _admin()
    ep = WebhookEndpoint.query.filter_by(
        id=ep_id, organization_id=actor.organization_id
    ).first()
    if ep is None:
        abort(404)
    WebhookDelivery.query.filter_by(
        endpoint_id=ep.id, organization_id=actor.organization_id
    ).delete()
    db.session.delete(ep)
    db.session.commit()
    flash(f"Endpoint #{ep.id} deleted.", "success")
    return redirect(url_for("integrations_views.index"))
