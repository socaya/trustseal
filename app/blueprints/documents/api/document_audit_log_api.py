from flask import Blueprint, request, jsonify
from datetime import datetime

from app.decorators import system_only
from app.extensions import db
from app.models.documents.document_audit_log import DocumentAuditLog

document_audit_log_api = Blueprint('document_audit_log_api', __name__, url_prefix='/api/document-audit-logs')


# === LIST ALL AUDIT LOGS ===
@document_audit_log_api.route('/', methods=['GET'])
def list_audit_logs():
    logs = DocumentAuditLog.query.order_by(DocumentAuditLog.timestamp.desc()).all()
    return jsonify([log.to_dict() for log in logs])


# === GET A SPECIFIC LOG ===
@document_audit_log_api.route('/<int:log_id>', methods=['GET'])
def get_audit_log(log_id):
    log = DocumentAuditLog.query.get_or_404(log_id)
    return jsonify(log.to_dict())


# === CREATE AUDIT LOG (system use only) ===
@document_audit_log_api.route('/', methods=['POST'])
@system_only
def create_audit_log():
    data = request.get_json()
    log = DocumentAuditLog(
        document_id=data.get("document_id"),
        user_id=data.get("user_id"),
        action=data.get("action"),
        details=data.get("details"),
        ip_address=data.get("ip_address"),
        user_agent=data.get("user_agent"),
        timestamp=datetime.utcnow()
    )
    db.session.add(log)
    db.session.commit()
    return jsonify({"message": "Audit log created", "id": log.id}), 201
