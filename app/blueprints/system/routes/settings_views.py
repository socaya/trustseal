from flask import render_template, request, redirect, url_for, flash
from flask_login import current_user, login_required
from .. import system_bp
from ..forms.system_setting_form import SystemSettingsForm
from ....extensions import db
from ....models.system import SystemSettings


@system_bp.route('/settings', methods=['GET', 'POST'])
@login_required
def system_settings_view():
    setting = db.session.get(SystemSettings, 1)
    if setting is None:
        setting = SystemSettings(id=1, platform_name="TrustSeal")
        db.session.add(setting)
        db.session.commit()

    if request.method == 'POST':
        setting.platform_name = (request.form.get('platform_name') or 'TrustSeal').strip()[:120]
        setting.platform_brand_color = (request.form.get('platform_brand_color') or '#18345e').strip()[:20]
        setting.default_from_email = (request.form.get('default_from_email') or '').strip()[:255] or None
        setting.smtp_host = (request.form.get('smtp_host') or '').strip()[:255] or None
        smtp_port = request.form.get('smtp_port', type=int)
        setting.smtp_port = smtp_port if smtp_port else setting.smtp_port
        setting.enable_signing = bool(request.form.get('enable_signing'))
        setting.enable_stamping = bool(request.form.get('enable_stamping'))
        setting.require_email_verification = bool(request.form.get('require_email_verification'))
        setting.enable_two_factor_auth = bool(request.form.get('enable_two_factor_auth'))
        setting.password_complexity = (request.form.get('password_complexity') or 'medium').strip()[:50]
        lock_thr = request.form.get('account_lock_threshold', type=int)
        if lock_thr:
            setting.account_lock_threshold = max(3, min(20, lock_thr))
        setting.auto_backup_enabled = bool(request.form.get('auto_backup_enabled'))
        ret_days = request.form.get('backup_retention_days', type=int)
        if ret_days:
            setting.backup_retention_days = max(1, min(3650, ret_days))
        db.session.commit()
        flash('Settings updated.', 'success')
        return redirect(url_for('system.system_settings_view'))

    form = SystemSettingsForm(obj=setting)
    return render_template(
        'system/settings/edit.html',
        form=form,
        setting=setting,
        org=getattr(current_user, 'organization', None),
    )