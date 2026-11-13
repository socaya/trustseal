from flask import render_template, request, redirect, url_for, flash
from .. import esignatures_bp
from ....services import api_client
from ..forms.signature_request_form import SignatureRequestForm

# === LIST ===
@esignatures_bp.route('/esignatures/signature_requests')
def view_signature_requests():
    items = api_client.get_data("esignatures/signature_requests") or []
    return render_template("esignatures/signature_requests/list.html", items=items)

# === CREATE ===
@esignatures_bp.route('/esignatures/signature_requests/create', methods=['GET', 'POST'])
def create_signature_request_view():
    form = SignatureRequestForm()
    if form.validate_on_submit():
        result = api_client.post_data("esignatures/signature_requests", data=form.data)
        if result and not result.get("error"):
            flash("SignatureRequest created.", "success")
            return redirect(url_for("esignatures.view_signature_requests"))
        flash(result.get("error", "Failed to create signature request."), "danger")
    return render_template("esignatures/signature_requests/create.html", form=form)

# === EDIT ===
@esignatures_bp.route('/esignatures/signature_requests/<int:item_id>/edit', methods=['GET', 'POST'])
def edit_signature_request_view(item_id):
    item = api_client.get_data(f"esignatures/signature_requests/{item_id}")
    if not item or item.get("error"):
        flash("SignatureRequest not found.", "danger")
        return redirect(url_for("esignatures.view_signature_requests"))

    form = SignatureRequestForm(data=item)
    if request.method == 'POST' and form.validate_on_submit():
        result = api_client.put_data(f"esignatures/signature_requests/{item_id}", data=form.data)
        if result and not result.get("error"):
            flash("SignatureRequest updated.", "success")
            return redirect(url_for("esignatures.view_signature_requests"))
        flash(result.get("error", "Update failed."), "danger")

    return render_template("esignatures/signature_requests/edit.html", form=form, item=item)

# === DELETE ===
@esignatures_bp.route('/esignatures/signature_requests/<int:item_id>/delete', methods=['POST'])
def delete_signature_request_view(item_id):
    result = api_client.delete_data(f"esignatures/signature_requests/{item_id}")
    if result and result.get("success"):
        flash("SignatureRequest deleted.", "success")
    else:
        flash(result.get("error", "Failed to delete request."), "danger")
    return redirect(url_for("esignatures.view_signature_requests"))