from datetime import datetime
from app.extensions import db

class DocumentParty(db.Model):
    __tablename__ = 'document_parties'

    id = db.Column(db.Integer, primary_key=True)
    role = db.Column(db.String(50), nullable=False)
    status = db.Column(db.String(20), default='pending')
    signed_at = db.Column(db.DateTime)
    document_id = db.Column(db.Integer, db.ForeignKey('documents.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    external_email = db.Column(db.String(120))

    document = db.relationship('Document', back_populates='parties')
    user = db.relationship('User')
    signatures = db.relationship('DocumentSignature', back_populates='party', cascade='all, delete-orphan')

    def to_dict(self):
        return {
            "id": self.id,
            "role": self.role,
            "status": self.status,
            "signed_at": self.signed_at.isoformat() if self.signed_at else None,
            "document_id": self.document_id,
            "user": self.user.to_dict() if self.user else None,
            "external_email": self.external_email,
            "signatures": [s.to_dict() for s in self.signatures]
        }