from datetime import datetime
from app.extensions import db

class DocumentComment(db.Model):
    __tablename__ = 'document_comments'

    id = db.Column(db.Integer, primary_key=True)
    document_id = db.Column(db.Integer, db.ForeignKey('documents.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    document = db.relationship('Document', backref='comments')
    user = db.relationship('User')

    def to_dict(self):
        return {
            "id": self.id,
            "content": self.content,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "document": self.document.to_dict() if self.document else None,
            "user": self.user.to_dict() if self.user else None,
        }
