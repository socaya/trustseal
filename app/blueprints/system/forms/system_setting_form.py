from flask_wtf import FlaskForm
from wtforms import StringField, IntegerField, BooleanField
from wtforms.validators import Optional


class SystemSettingsForm(FlaskForm):
    smtp_host = StringField('Smtp Host', validators=[Optional()])
    smtp_port = IntegerField('Smtp Port', validators=[Optional()])
    smtp_username = StringField('Smtp Username', validators=[Optional()])
    smtp_password = StringField('Smtp Password', validators=[Optional()])
    smtp_use_tls = BooleanField('Smtp Use Tls', validators=[Optional()])
    smtp_use_ssl = BooleanField('Smtp Use Ssl', validators=[Optional()])
    default_from_email = StringField('Default From Email', validators=[Optional()])

    sms_gateway_type = StringField('Sms Gateway Type', validators=[Optional()])
    sms_api_url = StringField('Sms Api Url', validators=[Optional()])
    sms_api_key = StringField('Sms Api Key', validators=[Optional()])
    sms_sender_id = StringField('Sms Sender Id', validators=[Optional()])
    sms_smpp_host = StringField('Sms Smpp Host', validators=[Optional()])
    sms_smpp_port = IntegerField('Sms Smpp Port', validators=[Optional()])
    sms_smpp_bind_type = StringField('Sms Smpp Bind Type', validators=[Optional()])
    sms_smpp_system_type = StringField('Sms Smpp System Type', validators=[Optional()])

    enable_signing = BooleanField('Enable Signing', validators=[Optional()])
    enable_stamping = BooleanField('Enable Stamping', validators=[Optional()])
    require_email_verification = BooleanField('Require Email Verification', validators=[Optional()])
    enable_two_factor_auth = BooleanField('Enable Two Factor Auth', validators=[Optional()])
    password_complexity = StringField('Password Complexity', validators=[Optional()])
    account_lock_threshold = IntegerField('Account Lock Threshold', validators=[Optional()])

    auto_backup_enabled = BooleanField('Auto Backup Enabled', validators=[Optional()])
    backup_frequency_cron = StringField('Backup Frequency Cron', validators=[Optional()])
    backup_retention_days = IntegerField('Backup Retention Days', validators=[Optional()])
    backup_storage_path = StringField('Backup Storage Path', validators=[Optional()])
    backup_storage_provider = StringField('Backup Storage Provider', validators=[Optional()])

    platform_name = StringField('Platform Name', validators=[Optional()])
    platform_logo_url = StringField('Platform Logo Url', validators=[Optional()])
    platform_brand_color = StringField('Platform Brand Color', validators=[Optional()])
    terms_url = StringField('Terms Url', validators=[Optional()])
    privacy_url = StringField('Privacy Url', validators=[Optional()])