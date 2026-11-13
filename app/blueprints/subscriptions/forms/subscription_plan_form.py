from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, IntegerField, BooleanField, DecimalField
from wtforms.validators import DataRequired, Optional

class SubscriptionPlanForm(FlaskForm):
    # Basic Info
    name = StringField('Name', validators=[DataRequired()])
    description = TextAreaField('Description', validators=[Optional()])
    price = DecimalField('Price', validators=[DataRequired()])
    duration_days = IntegerField('Duration Days', validators=[DataRequired()])
    currency = StringField('Currency', validators=[Optional()])
    trial_days = IntegerField('Trial Days', validators=[Optional()])
    is_active = BooleanField('Is Active')

    # Core Features
    can_create_documents = BooleanField('Can Create Documents')
    can_use_digital_stamps = BooleanField('Can Use Digital Stamps')
    can_sign_documents = BooleanField('Can Sign Documents')
    can_invite_users = BooleanField('Can Invite Users')
    can_manage_templates = BooleanField('Can Manage Templates')
    can_use_qr_validation = BooleanField('Can Use QR Validation')
    can_track_document_versions = BooleanField('Can Track Document Versions')
    can_access_audit_logs = BooleanField('Can Access Audit Logs')
    can_use_contract_workflows = BooleanField('Can Use Contract Workflows')
    can_stamp_multiple_pages = BooleanField('Can Stamp Multiple Pages')

    # Notification Flags
    notify_signer_on_invite = BooleanField('Notify Signer on Invite')
    notify_signer_on_reminder = BooleanField('Notify Signer on Reminder')
    notify_sender_on_sign = BooleanField('Notify Sender on Sign')
    notify_all_on_final_signature = BooleanField('Notify All on Final Signature')
    notify_owner_on_stamp = BooleanField('Notify Owner on Stamp')
    notify_admin_on_stamp = BooleanField('Notify Admin on Stamp')

    # Premium Features
    priority_signature_routing = BooleanField('Priority Signature Routing')
    multi_signatures = BooleanField('Multi Signatures')
    signature_reminders = BooleanField('Signature Reminders')
    signature_expiry_control = BooleanField('Signature Expiry Control')
    real_time_tracking = BooleanField('Real-time Tracking')
    signature_authentication = BooleanField('Signature Authentication')

    document_watermarking = BooleanField('Document Watermarking')
    document_expiry_dates = BooleanField('Document Expiry Dates')
    document_password_protect = BooleanField('Document Password Protect')
    custom_document_tags = BooleanField('Custom Document Tags')
    document_templates_library = BooleanField('Document Templates Library')

    custom_stamp_designs = BooleanField('Custom Stamp Designs')
    stamp_color_customization = BooleanField('Stamp Color Customization')
    auto_stamp_on_upload = BooleanField('Auto Stamp on Upload')
    multi_page_stamp_positions = BooleanField('Multi-Page Stamp Positions')
    remove_trustseal_branding = BooleanField('Remove TrustSeal Branding')

    role_based_access_control = BooleanField('Role Based Access Control')
    approval_workflows = BooleanField('Approval Workflows')
    team_activity_reporting = BooleanField('Team Activity Reporting')
    collaborative_drafting = BooleanField('Collaborative Drafting')

    api_access = BooleanField('API Access')
    webhook_notifications = BooleanField('Webhook Notifications')
    advanced_analytics = BooleanField('Advanced Analytics')
    scheduled_reports = BooleanField('Scheduled Reports')
    audit_log_retention_days = IntegerField('Audit Log Retention Days')

    # Limits
    max_users = IntegerField('Max Users')
    max_documents_per_month = IntegerField('Max Documents Per Month')
    max_storage_mb = IntegerField('Max Storage (MB)')
    max_document_pages = IntegerField('Max Document Pages')