from flask import request, jsonify
from .. import subscription_bp
from ....extensions import db
from ....models.subscription import Payment

@subscription_bp.route('/api/payments', methods=['GET'])
def list_payments():
    payments = Payment.query.all()
    return jsonify([{
        "id": p.id,
        "subscription_id": p.subscription_id,
        "amount": str(p.amount),
        "payment_date": p.payment_date.isoformat(),
        "payment_method": p.payment_method,
        "status": p.status
    } for p in payments])

@subscription_bp.route('/api/payments', methods=['POST'])
def create_payment():
    data = request.get_json()
    payment = Payment(**data)
    db.session.add(payment)
    db.session.commit()
    return jsonify({"message": "Payment recorded", "id": payment.id}), 201