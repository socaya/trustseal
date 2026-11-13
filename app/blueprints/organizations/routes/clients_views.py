from flask import render_template, request, redirect, url_for, flash
from .. import organizations_bp
from ....services import api_client
from ..forms.client_form import ClientForm

@organizations_bp.route('/clients')
def view_clients():
    items = api_client.get_data("clients") or []
    return render_template("organizations/clients/list.html", items=items)

@organizations_bp.route('/clients/create', methods=['GET', 'POST'])
def create_client_view():
    form = ClientForm()
    if form.validate_on_submit():
        result = api_client.post_data("clients", data=form.data)
        if result and not result.get("error"):
            flash("Client created.", "success")
            return redirect(url_for("organizations.view_clients"))
        flash(result.get("error", "Failed to create client."), "danger")
    return render_template("organizations/clients/create.html", form=form)

@organizations_bp.route('/clients/<int:item_id>/edit', methods=['GET', 'POST'])
def edit_client_view(item_id):
    item = api_client.get_data(f"clients/{item_id}")
    if not item or item.get("error"):
        flash("Client not found.", "danger")
        return redirect(url_for("organizations.view_clients"))

    form = ClientForm(data=item)
    if request.method == 'POST' and form.validate_on_submit():
        result = api_client.put_data(f"clients/{item_id}", data=form.data)
        if result and not result.get("error"):
            flash("Client updated.", "success")
            return redirect(url_for("organizations.view_clients"))
        flash(result.get("error", "Update failed."), "danger")
    return render_template("organizations/clients/edit.html", form=form, item=item)

@organizations_bp.route('/clients/<int:item_id>/delete', methods=['POST'])
def delete_client_view(item_id):
    result = api_client.delete_data(f"clients/{item_id}")
    if result.get("success"):
        flash("Client deleted.", "success")
    else:
        flash(result.get("error", "Failed to delete client."), "danger")
    return redirect(url_for("organizations.view_clients"))