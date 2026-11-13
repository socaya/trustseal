from datetime import datetime
from app.extensions import db

class DocumentDraft(db.Model):
    __tablename__ = 'document_drafts'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text)
    content = db.Column(db.Text)

    document_type_id = db.Column(db.Integer, db.ForeignKey('document_types.id'))
    status = db.Column(db.String(20), default='draft')  # draft, in_review, ready
    is_template = db.Column(db.Boolean, default=False)
    tags = db.Column(db.String(255))

    file_name = db.Column(db.String(255))
    file_path = db.Column(db.String(255))
    file_type = db.Column(db.String(50))
    file_size = db.Column(db.Integer)

    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'))

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    deleted_at = db.Column(db.DateTime)

    # Relationships
    creator = db.relationship('User', back_populates='created_drafts')
    organization = db.relationship('Organization', back_populates='drafts')
    document_type = db.relationship('DocumentType', back_populates='drafts')

    def is_upload(self):
        return bool(self.file_path)

    def is_inline(self):
        return not self.is_upload()

    def is_ready(self):
        return self.status == 'ready'

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "content": self.content,
            "status": self.status,
            "is_template": self.is_template,
            "tags": self.tags,
            "file_name": self.file_name,
            "file_path": self.file_path,
            "file_type": self.file_type,
            "file_size": self.file_size,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "deleted_at": self.deleted_at.isoformat() if self.deleted_at else None,
            "creator": self.creator.to_dict() if self.creator else None,
            "organization": self.organization.to_dict() if self.organization else None,
            "document_type": self.document_type.to_dict() if self.document_type else None,
        }