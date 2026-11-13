from datetime import datetime
from app.extensions import db


class SignatureProfile(db.Model):
    __tablename__ = 'signature_profiles'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    signature_type = db.Column(db.String(20), nullable=False)  # drawn/uploaded/text
    signature_data = db.Column(db.Text, nullable=False)  # SVG path or image path
    initials_data = db.Column(db.Text)  # For initials
    is_default = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    # Relationships
    user = db.relationship('User', back_populates='signatures')


class SignatureRequest(db.Model):
    __tablename__ = 'signature_requests'

    id = db.Column(db.Integer, primary_key=True)
    message = db.Column(db.Text)
    status = db.Column(db.String(20), default='pending')  # pending/completed/declined/expired
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime)
    expires_at = db.Column(db.DateTime)

    sender_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    recipient_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    recipient_email = db.Column(db.String(120))  # For external signers
    document_id = db.Column(db.Integer, db.ForeignKey('documents.id'), nullable=False)

    # Relationships
    sender = db.relationship(
        'User',
        foreign_keys=[sender_id],
        back_populates='sent_signature_requests'
    )
    recipient = db.relationship(
        'User',
        foreign_keys=[recipient_id],
        back_populates='received_signature_requests'
    )
    document = db.relationship('Document')
    activities = db.relationship('SignatureRequestActivity', back_populates='request', cascade='all, delete-orphan')


class SignatureRequestActivity(db.Model):
    __tablename__ = 'signature_request_activities'

    id = db.Column(db.Integer, primary_key=True)
    activity_type = db.Column(db.String(50), nullable=False)  # sent/viewed/signed/declined
    ip_address = db.Column(db.String(45))
    user_agent = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    request_id = db.Column(db.Integer, db.ForeignKey('signature_requests.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))

    # Relationships
    request = db.relationship('SignatureRequest', back_populates='activities')
    user = db.relationship('User')