from flask import render_template, request, redirect, url_for, flash
from flask_login import login_required
from .. import users_bp
from ....services import api_client
from ..forms.user_form import UserForm

@users_bp.route('/users')
@login_required
def view_users():
    users = api_client.get_data("users") or []
    return render_template("users/list.html", users=users)

@users_bp.route('/users/create', methods=['GET', 'POST'])
@login_required
def create_user_view():
    form = UserForm()
    if form.validate_on_submit():
        result = api_client.post_data("users", data=form.data)
        if not result.get("error"):
            flash("User created successfully.", "success")
            return redirect(url_for("users.view_users"))
        flash(result.get("error", "Failed to create user."), "danger")
    return render_template("users/create.html", form=form)

@users_bp.route('/users/<int:user_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_user_view(user_id):
    user = api_client.get_data(f"users/{user_id}")
    if not user or user.get("error"):
        flash("User not found.", "danger")
        return redirect(url_for("users.view_users"))

    form = UserForm(data=user)
    if request.method == 'POST' and form.validate_on_submit():
        result = api_client.put_data(f"users/{user_id}", data=form.data)
        if not result.get("error"):
            flash("User updated successfully.", "success")
            return redirect(url_for("users.view_users"))
        flash(result.get("error", "Update failed."), "danger")
    return render_template("users/edit.html", form=form, user=user)

@users_bp.route('/users/<int:user_id>/delete', methods=['POST'])
@login_required
def delete_user_view(user_id):
    result = api_client.delete_data(f"users/{user_id}")
    if result.get("success"):
        flash("User deleted.", "success")
    else:
        flash(result.get("error", "Failed to delete user."), "danger")
    return redirect(url_for("users.view_users"))