from flask import request, jsonify
from app.blueprints.estamp import estamp_bp
from app.extensions import db
from app.models.estamp import StampUsage

@estamp_bp.route('/api/usages', methods=['GET'])
def list_stamp_usages():
    usages = StampUsage.query.order_by(StampUsage.used_at.desc()).all()
    return jsonify([{
        "id": u.id,
        "usage_type": u.usage_type,
        "usage_reason": u.usage_reason,
        "used_at": u.used_at.isoformat(),
        "stamp_id": u.stamp_id,
        "document_id": u.document_id,
        "user_id": u.user_id
    } for u in usages])