from flask import render_template, request, redirect, url_for, flash
from .. import system_bp
from ....services import api_client
from ..forms.role_form import RoleForm

@system_bp.route('/roles')
def view_roles():
    items = api_client.get_data("roles") or []
    return render_template("system/roles/list.html", items=items)

@system_bp.route('/roles/create', methods=['GET', 'POST'])
def create_role_view():
    form = RoleForm()
    if form.validate_on_submit():
        result = api_client.post_data("roles", data=form.data)
        if not result.get("error"):
            flash("Role created.", "success")
            return redirect(url_for("system.view_roles"))
        flash(result.get("error", "Failed to create role."), "danger")
    return render_template("system/roles/create.html", form=form)
