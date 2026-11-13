from flask import render_template, request, redirect, url_for, flash
from .. import esignatures_bp
from ....services import api_client
from ..forms.signature_profile_form import SignatureProfileForm

# === LIST ===
@esignatures_bp.route('/esignatures/signature_profiles')
def view_signature_profiles():
    items = api_client.get_data("esignatures/signature_profiles") or []
    return render_template("esignatures/signature_profiles/list.html", items=items)

# === CREATE ===
@esignatures_bp.route('/esignatures/signature_profiles/create', methods=['GET', 'POST'])
def create_signature_profile_view():
    form = SignatureProfileForm()
    if form.validate_on_submit():
        result = api_client.post_data("esignatures/signature_profiles", data=form.data)
        if result and not result.get("error"):
            flash("SignatureProfile created.", "success")
            return redirect(url_for("esignatures.view_signature_profiles"))
        flash(result.get("error", "Failed to create profile."), "danger")
    return render_template("esignatures/signature_profiles/create.html", form=form)

# === EDIT ===
@esignatures_bp.route('/esignatures/signature_profiles/<int:item_id>/edit', methods=['GET', 'POST'])
def edit_signature_profile_view(item_id):
    item = api_client.get_data(f"esignatures/signature_profiles/{item_id}")
    if not item or item.get("error"):
        flash("SignatureProfile not found.", "danger")
        return redirect(url_for("esignatures.view_signature_profiles"))

    form = SignatureProfileForm(data=item)
    if request.method == 'POST' and form.validate_on_submit():
        result = api_client.put_data(f"esignatures/signature_profiles/{item_id}", data=form.data)
        if result and not result.get("error"):
            flash("SignatureProfile updated.", "success")
            return redirect(url_for("esignatures.view_signature_profiles"))
        flash(result.get("error", "Update failed."), "danger")

    return render_template("esignatures/signature_profiles/edit.html", form=form, item=item)

# === DELETE ===
@esignatures_bp.route('/esignatures/signature_profiles/<int:item_id>/delete', methods=['POST'])
def delete_signature_profile_view(item_id):
    result = api_client.delete_data(f"esignatures/signature_profiles/{item_id}")
    if result and result.get("success"):
        flash("SignatureProfile deleted.", "success")
    else:
        flash(result.get("error", "Failed to delete signature profile."), "danger")
    return redirect(url_for("esignatures.view_signature_profiles"))
