from flask import render_template, request, redirect, url_for, flash
from .. import organizations_bp
from ....services import api_client
from ..forms.organization_form import OrganizationForm

@organizations_bp.route('/organizations')
def view_organizations():
    items = api_client.get_data("organizations") or []
    return render_template("organizations/list.html", items=items)

@organizations_bp.route('/organizations/create', methods=['GET', 'POST'])
def create_organization_view():
    form = OrganizationForm()
    if form.validate_on_submit():
        result = api_client.post_data("organizations", data=form.data)
        if result and not result.get("error"):
            flash("Organization created.", "success")
            return redirect(url_for("organizations.view_organizations"))
        flash(result.get("error", "Failed to create organization."), "danger")
    return render_template("organizations/create.html", form=form)

@organizations_bp.route('/organizations/<int:item_id>/edit', methods=['GET', 'POST'])
def edit_organization_view(item_id):
    item = api_client.get_data(f"organizations/{item_id}")
    if not item or item.get("error"):
        flash("Organization not found.", "danger")
        return redirect(url_for("organizations.view_organizations"))

    form = OrganizationForm(data=item)
    if request.method == 'POST' and form.validate_on_submit():
        result = api_client.put_data(f"organizations/{item_id}", data=form.data)
        if result and not result.get("error"):
            flash("Organization updated.", "success")
            return redirect(url_for("organizations.view_organizations"))
        flash(result.get("error", "Update failed."), "danger")
    return render_template("organizations/edit.html", form=form, item=item)

@organizations_bp.route('/organizations/<int:item_id>/delete', methods=['POST'])
def delete_organization_view(item_id):
    result = api_client.delete_data(f"organizations/{item_id}")
    if result.get("success"):
        flash("Organization deleted.", "success")
    else:
        flash(result.get("error", "Failed to delete organization."), "danger")
    return redirect(url_for("organizations.view_organizations"))