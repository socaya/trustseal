from datetime import datetime
from app.extensions import db

class DocumentAuditLog(db.Model):
    __tablename__ = 'document_audit_logs'

    id = db.Column(db.Integer, primary_key=True)
    document_id = db.Column(db.Integer, db.ForeignKey('documents.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    action = db.Column(db.String(50), nullable=False)  # e.g., "viewed", "edited", "signed"
    ip_address = db.Column(db.String(45))
    user_agent = db.Column(db.String(255))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    document = db.relationship('Document', backref='audit_logs')
    user = db.relationship('User')

    def to_dict(self):
        return {
            "id": self.id,
            "action": self.action,
            "ip_address": self.ip_address,
            "user_agent": self.user_agent,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "document": self.document.to_dict() if self.document else None,
            "user": self.user.to_dict() if self.user else None,
        }
