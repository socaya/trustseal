from flask import request, jsonify
from .. import subscription_bp
from ....extensions import db
from ....models.subscription import SubscriptionPlan

@subscription_bp.route('/api/plans', methods=['GET'])
def list_subscription_plans():
    plans = SubscriptionPlan.query.all()
    return jsonify([{
        "id": p.id,
        "name": p.name,
        "price": str(p.price),
        "duration_days": p.duration_days,
        "currency": p.currency,
        "trial_days": p.trial_days,
        "is_active": p.is_active
    } for p in plans])

@subscription_bp.route('/api/plans', methods=['POST'])
def create_subscription_plan():
    data = request.get_json()
    plan = SubscriptionPlan(**data)
    db.session.add(plan)
    db.session.commit()
    return jsonify({"message": "Subscription plan created", "id": plan.id}), 201
