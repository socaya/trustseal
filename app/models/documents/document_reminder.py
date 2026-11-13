from app.extensions import db
from datetime import datetime

class DocumentReminder(db.Model):
    __tablename__ = 'document_reminders'

    id = db.Column(db.Integer, primary_key=True)
    document_id = db.Column(db.Integer, db.ForeignKey('documents.id'), nullable=False)
    recipient_email = db.Column(db.String(255), nullable=False)
    message = db.Column(db.Text)
    scheduled_for = db.Column(db.DateTime, nullable=False)
    sent_at = db.Column(db.DateTime)

    document = db.relationship('Document', backref='reminders')

    def to_dict(self):
        return {
            "id": self.id,
            "document_id": self.document_id,
            "recipient_email": self.recipient_email,
            "message": self.message,
            "scheduled_for": self.scheduled_for.isoformat() if self.scheduled_for else None,
            "sent_at": self.sent_at.isoformat() if self.sent_at else None
        }