from datetime import datetime
from app.extensions import db


class DigitalStamp(db.Model):
    __tablename__ = 'digital_stamps'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    design_data = db.Column(db.JSON, nullable=False)  # JSON containing design parameters
    image_path = db.Column(db.String(255), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    is_official = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    owner_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'))

    # Relationships
    owner = db.relationship('User', back_populates='stamps')
    organization = db.relationship('Organization', back_populates='stamps')
    documents = db.relationship('Document', backref='stamp', lazy='dynamic')


class StampTemplate(db.Model):
    __tablename__ = 'stamp_templates'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    design_json = db.Column(db.Text)
    preview_path = db.Column(db.String(255))
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    is_system = db.Column(db.Boolean, default=False)  # True for admin-created templates
    is_active = db.Column(db.Boolean, default=True)


class StampUsage(db.Model):
    __tablename__ = 'stamp_usages'

    id = db.Column(db.Integer, primary_key=True)
    usage_type = db.Column(db.String(50), nullable=False)  # document/contract/certificate
    usage_reason = db.Column(db.Text)
    used_at = db.Column(db.DateTime, default=datetime.utcnow)

    stamp_id = db.Column(db.Integer, db.ForeignKey('digital_stamps.id'), nullable=False)
    document_id = db.Column(db.Integer, db.ForeignKey('documents.id'))
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    # Relationships
    stamp = db.relationship('DigitalStamp', backref='usages')
    document = db.relationship('Document')
    user = db.relationship('User')