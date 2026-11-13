from datetime import datetime
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from app.extensions import db


class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), index=True, unique=True, nullable=False)
    email = db.Column(db.String(120), index=True, unique=True, nullable=False)
    password_hash = db.Column(db.String(512))
    first_name = db.Column(db.String(64))
    last_name = db.Column(db.String(64))
    phone = db.Column(db.String(20))
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)
    subscription_id = db.Column(db.Integer, db.ForeignKey('subscriptions.id'))
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'))

    # Relationships
    organization = db.relationship('Organization', back_populates='members')
    roles = db.relationship('UserRole', backref='user', cascade='all, delete-orphan')

    stamps = db.relationship('DigitalStamp', back_populates='owner', lazy='dynamic')
    signatures = db.relationship('SignatureProfile', back_populates='user', lazy='dynamic')

    sent_signature_requests = db.relationship(
        'SignatureRequest',
        foreign_keys='SignatureRequest.sender_id',
        back_populates='sender',
        lazy='dynamic'
    )
    received_signature_requests = db.relationship(
        'SignatureRequest',
        foreign_keys='SignatureRequest.recipient_id',
        back_populates='recipient',
        lazy='dynamic'
    )

    sent_invitations = db.relationship('UserInvitation', back_populates='invited_by')

    # --- Document Relationships ---
    signed_documents = db.relationship('Document', foreign_keys='Document.signed_by_id', back_populates='signed_by')
    created_documents = db.relationship('Document', foreign_keys='Document.created_by', back_populates='creator')

    created_drafts = db.relationship('DocumentDraft', back_populates='creator', cascade='all, delete-orphan')
    document_versions = db.relationship('DocumentVersion', back_populates='creator', cascade='all, delete-orphan')
    document_activities = db.relationship('DocumentActivity', back_populates='user', cascade='all, delete-orphan')
    document_signatures = db.relationship('DocumentSignature', back_populates='user', cascade='all, delete-orphan')
    document_shares_created = db.relationship('DocumentShare', foreign_keys='DocumentShare.created_by_id', back_populates='created_by')
    document_shares_received = db.relationship('DocumentShare', foreign_keys='DocumentShare.shared_with_user_id', back_populates='shared_with_user')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def get_full_name(self):
        return f"{self.first_name} {self.last_name}"

    def to_dict(self):
        return {
            "id": self.id,
            "username": self.username,
            "email": self.email,
            "first_name": self.first_name,
            "last_name": self.last_name,
            "phone": self.phone,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "last_login": self.last_login.isoformat() if self.last_login else None,
            "organization_id": self.organization_id,
            "sent_invitations": [  # Include minimal info to prevent recursion
                {
                    "id": inv.id,
                    "email": inv.email,
                    "role": inv.role,
                    "created_at": inv.created_at.isoformat() if inv.created_at else None
                } for inv in self.sent_invitations
            ]
        }


class UserInvitation(db.Model):
    __tablename__ = 'user_invitations'

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), nullable=False)
    token = db.Column(db.String(64), index=True, unique=True)
    role = db.Column(db.String(20), default='member')
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'))
    invited_by_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime)

    organization = db.relationship('Organization', back_populates='invitations')
    invited_by = db.relationship('User', back_populates='sent_invitations')

    def to_dict(self):
        return {
            "id": self.id,
            "email": self.email,
            "token": self.token,
            "role": self.role,
            "organization_id": self.organization_id,
            "invited_by_id": self.invited_by_id,  # avoid full recursion
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
        }