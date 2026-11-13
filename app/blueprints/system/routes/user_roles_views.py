from flask import render_template, request, redirect, url_for, flash
from .. import system_bp
from ....services import api_client
from ..forms.user_role_form import AssignUserRoleForm

@system_bp.route('/user_roles/assign', methods=['GET', 'POST'])
def assign_user_role_view():
    form = AssignUserRoleForm()
    if form.validate_on_submit():
        result = api_client.post_data(f"users/{form.user_id.data}/roles", data={"role_id": form.role_id.data})
        if not result.get("error"):
            flash("Role assigned to user.", "success")
            return redirect(url_for("system.assign_user_role_view"))
        flash(result.get("error", "Assignment failed."), "danger")
    return render_template("system/user_roles/assign.html", form=form)