from flask import render_template, request, redirect, url_for, flash
from .. import users_bp
from ....services import api_client
from ..forms.user_invitaton_form import UserInvitationForm

@users_bp.route('/user-invitations')
def view_user_invitations():
    items = api_client.get_data("user-invitations") or []
    return render_template("users/invitations/list.html", items=items)

@users_bp.route('/user-invitations/create', methods=['GET', 'POST'])
def create_user_invitation_view():
    form = UserInvitationForm()
    if form.validate_on_submit():
        result = api_client.post_data("user-invitations", data=form.data)
        if not result.get("error"):
            flash("Invitation sent.", "success")
            return redirect(url_for("users.view_user_invitations"))
        flash(result.get("error", "Failed to send invitation."), "danger")
    return render_template("users/invitations/create.html", form=form)