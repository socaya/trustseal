from datetime import datetime
from app.extensions import db

class SubscriptionPlan(db.Model):
    __tablename__ = 'subscription_plans'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    description = db.Column(db.Text)
    price = db.Column(db.Numeric(10, 2), nullable=False)
    duration_days = db.Column(db.Integer, nullable=False)
    currency = db.Column(db.String(10))
    trial_days = db.Column(db.Integer)
    is_active = db.Column(db.Boolean, default=True)

    # === Core Feature Flags ===
    can_create_documents = db.Column(db.Boolean, default=True)
    can_use_digital_stamps = db.Column(db.Boolean, default=True)
    can_sign_documents = db.Column(db.Boolean, default=True)
    can_invite_users = db.Column(db.Boolean, default=True)
    can_manage_templates = db.Column(db.Boolean, default=False)
    can_use_qr_validation = db.Column(db.Boolean, default=False)
    can_track_document_versions = db.Column(db.Boolean, default=False)
    can_access_audit_logs = db.Column(db.Boolean, default=False)
    can_use_contract_workflows = db.Column(db.Boolean, default=False)
    can_stamp_multiple_pages = db.Column(db.Boolean, default=True)

    # === Notification Feature Flags ===
    notify_signer_on_invite = db.Column(db.Boolean, default=True)
    notify_signer_on_reminder = db.Column(db.Boolean, default=True)
    notify_sender_on_sign = db.Column(db.Boolean, default=True)
    notify_all_on_final_signature = db.Column(db.Boolean, default=True)
    notify_owner_on_stamp = db.Column(db.Boolean, default=True)
    notify_admin_on_stamp = db.Column(db.Boolean, default=False)

    # === Premium Feature Flags ===
    priority_signature_routing = db.Column(db.Boolean, default=False)
    multi_signatures = db.Column(db.Boolean, default=False)
    signature_reminders = db.Column(db.Boolean, default=False)
    signature_expiry_control = db.Column(db.Boolean, default=False)
    real_time_tracking = db.Column(db.Boolean, default=False)
    signature_authentication = db.Column(db.Boolean, default=False)

    document_watermarking = db.Column(db.Boolean, default=False)
    document_expiry_dates = db.Column(db.Boolean, default=False)
    document_password_protect = db.Column(db.Boolean, default=False)
    custom_document_tags = db.Column(db.Boolean, default=False)
    document_templates_library = db.Column(db.Boolean, default=False)

    custom_stamp_designs = db.Column(db.Boolean, default=False)
    stamp_color_customization = db.Column(db.Boolean, default=False)
    auto_stamp_on_upload = db.Column(db.Boolean, default=False)
    multi_page_stamp_positions = db.Column(db.Boolean, default=False)
    remove_trustseal_branding = db.Column(db.Boolean, default=False)

    role_based_access_control = db.Column(db.Boolean, default=False)
    approval_workflows = db.Column(db.Boolean, default=False)
    team_activity_reporting = db.Column(db.Boolean, default=False)
    collaborative_drafting = db.Column(db.Boolean, default=False)

    api_access = db.Column(db.Boolean, default=False)
    webhook_notifications = db.Column(db.Boolean, default=False)
    advanced_analytics = db.Column(db.Boolean, default=False)
    scheduled_reports = db.Column(db.Boolean, default=False)
    audit_log_retention_days = db.Column(db.Integer, default=30)

    # === Usage Limits ===
    max_users = db.Column(db.Integer, default=5)
    max_documents_per_month = db.Column(db.Integer, default=100)
    max_storage_mb = db.Column(db.Integer, default=500)
    max_document_pages = db.Column(db.Integer, default=10)

    # === Metadata ===
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # === Relationships ===
    subscriptions = db.relationship('Subscription', back_populates='plan', cascade='all, delete-orphan')


class Subscription(db.Model):
    __tablename__ = 'subscriptions'

    id = db.Column(db.Integer, primary_key=True)
    start_date = db.Column(db.DateTime, nullable=False)
    end_date = db.Column(db.DateTime, nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    payment_method = db.Column(db.String(50))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    plan_id = db.Column(db.Integer, db.ForeignKey('subscription_plans.id'), nullable=False)

    organization = db.relationship(
        'Organization',
        back_populates='subscription',
        uselist=False
    )

    plan = db.relationship('SubscriptionPlan', back_populates='subscriptions')
    payments = db.relationship('Payment', back_populates='subscription', cascade='all, delete-orphan')


class Payment(db.Model):
    __tablename__ = 'payments'

    id = db.Column(db.Integer, primary_key=True)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    currency = db.Column(db.String(3), default='USD')
    payment_date = db.Column(db.DateTime, nullable=False)
    payment_method = db.Column(db.String(50))
    transaction_id = db.Column(db.String(100))
    status = db.Column(db.String(20), default='completed')  # pending/completed/failed/refunded
    invoice_number = db.Column(db.String(50))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    subscription_id = db.Column(db.Integer, db.ForeignKey('subscriptions.id'), nullable=False)

    # Relationships
    subscription = db.relationship('Subscription', back_populates='payments')