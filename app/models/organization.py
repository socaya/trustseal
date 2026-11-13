from datetime import datetime
from app.extensions import db

class Organization(db.Model):
    __tablename__ = 'organizations'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    legal_name = db.Column(db.String(120))
    registration_number = db.Column(db.String(120))
    tax_id = db.Column(db.String(50))
    country = db.Column(db.String(50))
    address = db.Column(db.Text)
    phone = db.Column(db.String(20))
    email = db.Column(db.String(120))
    website = db.Column(db.String(120))
    logo_path = db.Column(db.String(255))

    type = db.Column(db.Enum('individual', 'company', name='organization_type'), nullable=False, default='company')
    is_verified = db.Column(db.Boolean, default=False)
    verified_at = db.Column(db.DateTime)
    verification_notes = db.Column(db.Text)

    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    subscription_id = db.Column(db.Integer, db.ForeignKey('subscriptions.id'))
    subscription = db.relationship("Subscription", back_populates="organization", uselist=False)

    drafts = db.relationship('DocumentDraft', back_populates='organization', cascade='all, delete-orphan')
    documents = db.relationship('Document', back_populates='organization', cascade='all, delete-orphan')
    clients = db.relationship('Client', back_populates='organization', cascade='all, delete-orphan')
    members = db.relationship('User', back_populates='organization', cascade='all, delete-orphan')
    invitations = db.relationship('UserInvitation', back_populates='organization', cascade='all, delete-orphan')
    stamps = db.relationship('DigitalStamp', back_populates='organization', cascade='all, delete-orphan')

    def to_dict(self, deep=False):
        return {
            "id": self.id,
            "name": self.name,
            "legal_name": self.legal_name,
            "registration_number": self.registration_number,
            "tax_id": self.tax_id,
            "country": self.country,
            "address": self.address,
            "phone": self.phone,
            "email": self.email,
            "website": self.website,
            "logo_path": self.logo_path,
            "type": self.type,
            "is_verified": self.is_verified,
            "verified_at": self.verified_at.isoformat() if self.verified_at else None,
            "verification_notes": self.verification_notes,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "subscription": self.subscription.to_dict() if deep and self.subscription and hasattr(self.subscription, "to_dict") else None,
            "drafts": [d.to_dict() for d in self.drafts] if deep else [],
            "documents": [d.to_dict() for d in self.documents] if deep else [],
            "clients": [c.to_dict() for c in self.clients] if deep else [],
            "members": [m.to_dict() for m in self.members] if deep else [],
            "invitations": [i.to_dict() for i in self.invitations] if deep else [],
            "stamps": [s.to_dict() for s in self.stamps] if deep else [],
        }


class Client(db.Model):
    __tablename__ = 'clients'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120))
    phone = db.Column(db.String(20))
    address = db.Column(db.Text)
    tax_id = db.Column(db.String(50))
    notes = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=False)
    organization = db.relationship('Organization', back_populates='clients')
    documents = db.relationship('Document', back_populates='client', cascade='all, delete-orphan')

    def to_dict(self, include_organization=False):
        return {
            "id": self.id,
            "name": self.name,
            "email": self.email,
            "phone": self.phone,
            "address": self.address,
            "tax_id": self.tax_id,
            "notes": self.notes,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "organization": self.organization.to_dict() if (include_organization and self.organization and hasattr(self.organization, 'to_dict')) else None
        }