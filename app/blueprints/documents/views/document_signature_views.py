from flask import Blueprint, render_template, request, redirect, url_for, flash
from app.blueprints.documents.forms.document_signature_form import DocumentSignatureForm
from ....services import api_client

document_signature_views = Blueprint('document_signature_views', __name__, url_prefix='/documents/signatures')

# === LIST ===
@document_signature_views.route('/')
def view_document_signatures():
    items = api_client.get_data("documents/signatures") or []
    return render_template('documents/signatures/list.html', items=items)

# === CREATE ===
@document_signature_views.route('/create', methods=['GET', 'POST'])
def create_document_signature_view():
    form = DocumentSignatureForm()
    if form.validate_on_submit():
        result = api_client.post_data("documents/signatures", data=form.data)
        if result and not result.get("error"):
            flash("DocumentSignature created.", "success")
            return redirect(url_for("document_signature_views.view_document_signatures"))
        flash(result.get("error", "Failed to create document signature."), "danger")
    return render_template("documents/signatures/create.html", form=form)

# === EDIT ===
@document_signature_views.route('/<int:item_id>/edit', methods=['GET', 'POST'])
def edit_document_signature_view(item_id):
    item = api_client.get_data(f"documents/signatures/{item_id}")
    if not item or item.get("error"):
        flash("DocumentSignature not found.", "danger")
        return redirect(url_for("document_signature_views.view_document_signatures"))

    form = DocumentSignatureForm(data=item)
    if request.method == 'POST' and form.validate_on_submit():
        result = api_client.put_data(f"documents/signatures/{item_id}", data=form.data)
        if result and not result.get("error"):
            flash("DocumentSignature updated.", "success")
            return redirect(url_for("document_signature_views.view_document_signatures"))
        flash(result.get("error", "Update failed."), "danger")

    return render_template("documents/signatures/edit.html", form=form, item=item)

# === DELETE ===
@document_signature_views.route('/<int:item_id>/delete', methods=['POST'])
def delete_document_signature_view(item_id):
    result = api_client.delete_data(f"documents/signatures/{item_id}")
    if result and result.get("success"):
        flash("DocumentSignature deleted.", "success")
    else:
        flash(result.get("error", "Failed to delete signature."), "danger")
    return redirect(url_for("document_signature_views.view_document_signatures"))