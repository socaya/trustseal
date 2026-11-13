from flask import render_template, request, redirect, url_for, flash
from .. import esignatures_bp
from ....services import api_client
from ..forms.signature_request_activity_form import SignatureRequestActivityForm

# === LIST ===
@esignatures_bp.route('/esignatures/signature_request_activitys')
def view_signature_request_activitys():
    items = api_client.get_data("esignatures/signature_request_activitys") or []
    return render_template("esignatures/signature_request_activitys/list.html", items=items)

# === CREATE ===
@esignatures_bp.route('/esignatures/signature_request_activitys/create', methods=['GET', 'POST'])
def create_signature_request_activity_view():
    form = SignatureRequestActivityForm()
    if form.validate_on_submit():
        result = api_client.post_data("esignatures/signature_request_activitys", data=form.data)
        if result and not result.get("error"):
            flash("SignatureRequestActivity created.", "success")
            return redirect(url_for("esignatures.view_signature_request_activitys"))
        flash(result.get("error", "Failed to create activity."), "danger")
    return render_template("esignatures/signature_request_activitys/create.html", form=form)

# === EDIT ===
@esignatures_bp.route('/esignatures/signature_request_activitys/<int:item_id>/edit', methods=['GET', 'POST'])
def edit_signature_request_activity_view(item_id):
    item = api_client.get_data(f"esignatures/signature_request_activitys/{item_id}")
    if not item or item.get("error"):
        flash("Activity not found.", "danger")
        return redirect(url_for("esignatures.view_signature_request_activitys"))

    form = SignatureRequestActivityForm(data=item)
    if request.method == 'POST' and form.validate_on_submit():
        result = api_client.put_data(f"esignatures/signature_request_activitys/{item_id}", data=form.data)
        if result and not result.get("error"):
            flash("SignatureRequestActivity updated.", "success")
            return redirect(url_for("esignatures.view_signature_request_activitys"))
        flash(result.get("error", "Update failed."), "danger")

    return render_template("esignatures/signature_request_activitys/edit.html", form=form, item=item)

# === DELETE ===
@esignatures_bp.route('/esignatures/signature_request_activitys/<int:item_id>/delete', methods=['POST'])
def delete_signature_request_activity_view(item_id):
    result = api_client.delete_data(f"esignatures/signature_request_activitys/{item_id}")
    if result and result.get("success"):
        flash("SignatureRequestActivity deleted.", "success")
    else:
        flash(result.get("error", "Failed to delete activity."), "danger")
    return redirect(url_for("esignatures.view_signature_request_activitys"))
