from datetime import datetime
from app.extensions import db

class DocumentShare(db.Model):
    __tablename__ = 'document_shares'

    id = db.Column(db.Integer, primary_key=True)
    document_id = db.Column(db.Integer, db.ForeignKey('documents.id'), nullable=False)
    shared_with_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    shared_with_email = db.Column(db.String(120), nullable=True)

    can_view = db.Column(db.Boolean, default=True)
    can_edit = db.Column(db.Boolean, default=False)
    can_sign = db.Column(db.Boolean, default=False)
    can_stamp = db.Column(db.Boolean, default=False)
    can_download = db.Column(db.Boolean, default=False)
    can_share = db.Column(db.Boolean, default=False)

    token = db.Column(db.String(64), unique=True, nullable=False)
    expires_at = db.Column(db.DateTime, nullable=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    document = db.relationship('Document', back_populates='shares')
    created_by = db.relationship('User', foreign_keys=[created_by_id])
    shared_with_user = db.relationship('User', foreign_keys=[shared_with_user_id])

    def to_dict(self):
        return {
            "id": self.id,
            "document_id": self.document_id,
            "shared_with_user_id": self.shared_with_user_id,
            "shared_with_email": self.shared_with_email,

            "can_view": self.can_view,
            "can_edit": self.can_edit,
            "can_sign": self.can_sign,
            "can_stamp": self.can_stamp,
            "can_download": self.can_download,
            "can_share": self.can_share,

            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "created_by_id": self.created_by_id,
            "created_at": self.created_at.isoformat(),

        }