"""Per-plan metered entitlements.

Each row names one meter + period that a plan limits. If an
organization's active subscription references a plan that has an
entitlement row for a meter, the enforcement middleware blocks
mutations that would push usage over the ``limit`` within the
``period``.

Absent rows mean "unmetered" — the meter is not enforced for the
plan. This lets the Free plan limit `envelope.prepared` per month
while the Enterprise plan is unlimited by simply not having a row.
"""
from datetime import datetime

from app.extensions import db


class PlanEntitlement(db.Model):
    __tablename__ = "plan_entitlements"

    id = db.Column(db.BigInteger, primary_key=True)
    plan_id = db.Column(
        db.Integer,
        db.ForeignKey("subscription_plans.id"),
        nullable=False,
        index=True,
    )
    meter = db.Column(db.String(60), nullable=False)
    period = db.Column(db.String(20), nullable=False, default="month")
    hit_limit = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint(
            "plan_id", "meter", "period", name="uq_plan_entitlement"
        ),
        db.CheckConstraint("hit_limit > 0", name="ck_plan_entitlement_limit"),
        db.CheckConstraint(
            "period IN ('day','month','year')",
            name="ck_plan_entitlement_period",
        ),
    )
