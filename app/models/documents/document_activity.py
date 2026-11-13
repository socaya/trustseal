from datetime import datetime
from app.extensions import db

class DocumentActivity(db.Model):
    __tablename__ = 'document_activities'

    id = db.Column(db.Integer, primary_key=True)
    activity_type = db.Column(db.String(50), nullable=False)
    details = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    document_id = db.Column(db.Integer, db.ForeignKey('documents.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))

    document = db.relationship('Document', back_populates='activities')
    user = db.relationship('User')

    def to_dict(self):
        return {
            "id": self.id,
            "activity_type": self.activity_type,
            "details": self.details,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "document": self.document.to_dict() if self.document else None,
            "user": self.user.to_dict() if self.user else None,
        }
