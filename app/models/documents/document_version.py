from datetime import datetime
from app.extensions import db

class DocumentVersion(db.Model):
    __tablename__ = 'document_versions'

    id = db.Column(db.Integer, primary_key=True)
    version_number = db.Column(db.Integer, nullable=False)
    file_name = db.Column(db.String(255), nullable=False)
    file_path = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    document_id = db.Column(db.Integer, db.ForeignKey('documents.id'), nullable=False)

    document = db.relationship('Document', back_populates='versions')
    creator = db.relationship('User')

    def to_dict(self, include_document=False, include_creator=False):
        data = {
            "id": self.id,
            "version_number": self.version_number,
            "file_name": self.file_name,
            "file_path": self.file_path,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "created_by_id": self.created_by_id,
            "document_id": self.document_id,
        }

        if include_creator and self.creator:
            data["creator"] = self.creator.to_dict() if hasattr(self.creator, 'to_dict') else {
                "id": self.creator.id,
                "email": self.creator.email
            }

        if include_document and self.document:
            data["document"] = self.document.to_dict() if hasattr(self.document, 'to_dict') else {
                "id": self.document.id,
                "title": self.document.title
            }

        return data