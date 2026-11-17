"""Admin view: current subscription, plan, usage, and payment history.

Read-only. Admin-gated.
"""
from __future__ import annotations

from datetime import datetime, timezone

from flask import Blueprint, abort, render_template
from flask_login import current_user, login_required
from sqlalchemy import desc

from app.models.organization import Organization
from app.models.subscription import Payment, Subscription, SubscriptionPlan
from app.models.usage_ledger import UsageLedgerEntry
from app.policies.api_access import is_admin


billing_views = Blueprint(
    "billing_views", __name__, url_prefix="/admin/billing"
)


def _admin():
    if not current_user.is_authenticated:
        abort(401)
    if current_user.organization_id is None:
        abort(403, description="organization_required")
    if not is_admin(current_user.id):
        abort(403, description="admin_required")
    return current_user


@billing_views.route("", methods=["GET"])
@login_required
def index():
    actor = _admin()

    org = Organization.query.get(actor.organization_id)
    subscription = (
        Subscription.query.get(org.subscription_id)
        if org and org.subscription_id
        else None
    )
    plan = subscription.plan if subscription else None
    payments = (
        Payment.query.filter_by(subscription_id=subscription.id)
        .order_by(desc(Payment.payment_date))
        .limit(24)
        .all()
        if subscription
        else []
    )

    usage = (
        UsageLedgerEntry.query
        .filter_by(organization_id=actor.organization_id)
        .order_by(desc(UsageLedgerEntry.id))
        .limit(50)
        .all()
    )

    all_plans = (
        SubscriptionPlan.query
        .filter_by(is_active=True)
        .order_by(SubscriptionPlan.price.asc())
        .all()
    )

    return render_template(
        "admin/billing.html",
        org=org,
        subscription=subscription,
        plan=plan,
        payments=payments,
        usage=usage,
        all_plans=all_plans,
        now=datetime.now(timezone.utc),
    )
