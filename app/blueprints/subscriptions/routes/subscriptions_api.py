from flask import request, jsonify
from .. import subscription_bp
from ....extensions import db
from ....models.subscription import Subscription

@subscription_bp.route('/api/subscriptions', methods=['GET'])
def list_subscriptions():
    subs = Subscription.query.all()
    return jsonify([{
        "id": s.id,
        "organization_id": s.organization_id,
        "plan_id": s.plan_id,
        "start_date": s.start_date.isoformat(),
        "end_date": s.end_date.isoformat(),
        "is_active": s.is_active
    } for s in subs])

@subscription_bp.route('/api/subscriptions', methods=['POST'])
def create_subscription():
    data = request.get_json()
    sub = Subscription(**data)
    db.session.add(sub)
    db.session.commit()
    return jsonify({"message": "Subscription created", "id": sub.id}), 201