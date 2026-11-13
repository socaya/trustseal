from flask import jsonify
from .. import system_bp
from ....models.system import AuditLog

@system_bp.route('/api/audit-logs', methods=['GET'])
def list_audit_logs():
    logs = AuditLog.query.order_by(AuditLog.created_at.desc()).limit(100).all()
    return jsonify([{
        "id": log.id,
        "action": log.action,
        "entity_type": log.entity_type,
        "entity_id": log.entity_id,
        "user_id": log.user_id,
        "created_at": log.created_at.isoformat()
    } for log in logs])