from flask import render_template, request, redirect, url_for, flash
from .. import system_bp
from ..forms.system_setting_form import SystemSettingsForm
from ....extensions import db
from ....models.system import SystemSettings


@system_bp.route('/settings', methods=['GET', 'POST'])
def system_settings_view():
    setting = SystemSettings.query.get(1)
    form = SystemSettingsForm(obj=setting)
    if form.validate_on_submit():
        form.populate_obj(setting)
        db.session.commit()
        flash('System settings updated successfully.', 'success')
        return redirect(url_for('system.system_settings_view'))
    return render_template('system/settings/edit.html', form=form)