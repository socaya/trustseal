from flask import render_template, redirect, url_for, flash
from flask_login import login_required, current_user
from .. import users_bp
from ....services import api_client
from ..forms.change_papssword_form import ChangePasswordForm

@users_bp.route('/users/change-password', methods=['GET', 'POST'])
@login_required
def change_password_view():
    form = ChangePasswordForm()
    if form.validate_on_submit():
        data = {
            "current_password": form.current_password.data,
            "new_password": form.new_password.data
        }
        result = api_client.post_data(f"users/{current_user.id}/change-password", data=data)
        if not result.get("error"):
            flash("Password changed successfully.", "success")
            return redirect(url_for("users.view_users"))
        flash(result.get("error", "Failed to change password."), "danger")
    return render_template("users/change_password.html", form=form)