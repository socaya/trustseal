from datetime import datetime
from app.extensions import db

class DocumentSignature(db.Model):
    __tablename__ = 'document_signatures'

    id = db.Column(db.Integer, primary_key=True)
    signature_type = db.Column(db.String(20), nullable=False)
    signature_data = db.Column(db.Text)
    signed_at = db.Column(db.DateTime, default=datetime.utcnow)
    ip_address = db.Column(db.String(45))

    document_id = db.Column(db.Integer, db.ForeignKey('documents.id'), nullable=False)
    party_id = db.Column(db.Integer, db.ForeignKey('document_parties.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))

    document = db.relationship('Document', back_populates='signatures')
    party = db.relationship('DocumentParty', back_populates='signatures')
    user = db.relationship('User')

    def to_dict(self):
        return {
            "id": self.id,
            "signature_type": self.signature_type,
            "signed_at": self.signed_at.isoformat() if self.signed_at else None,
            "document_id": self.document_id,
            "party_id": self.party_id,
            "user_id": self.user_id,

        }