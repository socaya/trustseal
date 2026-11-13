from datetime import datetime
from app.extensions import db

class DocumentType(db.Model):
    __tablename__ = 'document_types'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    description = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    drafts = db.relationship('DocumentDraft', back_populates='document_type', lazy=True)
    documents = db.relationship('Document', backref='document_type', lazy=True, cascade='all, delete-orphan')

    def to_dict(self, include_counts=False):
        data = {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

        if include_counts:
            data["draft_count"] = len(self.drafts)
            data["document_count"] = len(self.documents)

        return data
