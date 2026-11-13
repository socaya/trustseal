from datetime import datetime
from app.extensions import db


class AuditLog(db.Model):
    __tablename__ = 'audit_logs'

    id = db.Column(db.Integer, primary_key=True)
    action = db.Column(db.String(50), nullable=False)
    entity_type = db.Column(db.String(50))
    entity_id = db.Column(db.Integer)
    old_values = db.Column(db.JSON)
    new_values = db.Column(db.JSON)
    ip_address = db.Column(db.String(45))
    user_agent = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))

    # Relationships
    user = db.relationship('User')

class SystemSettings(db.Model):
    __tablename__ = 'system_settings'
    id = db.Column(db.Integer, primary_key=True, default=1)  # force single row

    # EMAIL
    smtp_host = db.Column(db.String(255))
    smtp_port = db.Column(db.Integer)
    smtp_username = db.Column(db.String(255))
    smtp_password = db.Column(db.String(255))
    smtp_use_tls = db.Column(db.Boolean, default=True)
    smtp_use_ssl = db.Column(db.Boolean, default=False)
    default_from_email = db.Column(db.String(255))

    # SMS
    sms_gateway_type = db.Column(db.String(50))
    sms_api_url = db.Column(db.String(255))
    sms_api_key = db.Column(db.String(255))
    sms_sender_id = db.Column(db.String(100))
    sms_smpp_host = db.Column(db.String(255))
    sms_smpp_port = db.Column(db.Integer)
    sms_smpp_bind_type = db.Column(db.String(50))
    sms_smpp_system_type = db.Column(db.String(50))

    # SECURITY
    enable_signing = db.Column(db.Boolean, default=True)
    enable_stamping = db.Column(db.Boolean, default=True)
    require_email_verification = db.Column(db.Boolean, default=False)
    enable_two_factor_auth = db.Column(db.Boolean, default=False)
    password_complexity = db.Column(db.String(50), default='medium')
    account_lock_threshold = db.Column(db.Integer, default=5)

    # BACKUP
    auto_backup_enabled = db.Column(db.Boolean, default=False)
    backup_frequency_cron = db.Column(db.String(100))
    backup_retention_days = db.Column(db.Integer, default=30)
    backup_storage_path = db.Column(db.String(255))
    backup_storage_provider = db.Column(db.String(100))

    # METADATA
    platform_name = db.Column(db.String(120), default="TrustSeal")
    platform_logo_url = db.Column(db.String(255))
    platform_brand_color = db.Column(db.String(20))
    terms_url = db.Column(db.String(255))
    privacy_url = db.Column(db.String(255))

    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ✅ RBAC MODELS

class Role(db.Model):
    __tablename__ = 'roles'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), unique=True, nullable=False)
    description = db.Column(db.Text)


class Permission(db.Model):
    __tablename__ = 'permissions'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), unique=True, nullable=False)
    description = db.Column(db.Text)


class RolePermission(db.Model):
    __tablename__ = 'role_permissions'
    role_id = db.Column(db.Integer, db.ForeignKey('roles.id'), primary_key=True)
    permission_id = db.Column(db.Integer, db.ForeignKey('permissions.id'), primary_key=True)


class UserRole(db.Model):
    __tablename__ = 'user_roles'
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), primary_key=True)
    role_id = db.Column(db.Integer, db.ForeignKey('roles.id'), primary_key=True)