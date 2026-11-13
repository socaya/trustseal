from flask import Blueprint, render_template, request, redirect, url_for, flash
from app.blueprints.documents.forms.document_share_form import DocumentShareForm
from ....services import api_client

document_share_views = Blueprint('document_share_views', __name__, url_prefix='/documents/shares')

# === LIST ===
@document_share_views.route('/')
def view_document_shares():
    items = api_client.get_data("documents/shares") or []
    return render_template('documents/shares/list.html', items=items)

# === CREATE ===
@document_share_views.route('/create', methods=['GET', 'POST'])
def create_document_share_view():
    form = DocumentShareForm()
    if form.validate_on_submit():
        result = api_client.post_data("documents/shares", data=form.data)
        if result and not result.get("error"):
            flash("DocumentShare created.", "success")
            return redirect(url_for("document_share_views.view_document_shares"))
        flash(result.get("error", "Failed to create document share."), "danger")
    return render_template("documents/shares/create.html", form=form)

# === EDIT ===
@document_share_views.route('/<int:item_id>/edit', methods=['GET', 'POST'])
def edit_document_share_view(item_id):
    item = api_client.get_data(f"documents/shares/{item_id}")
    if not item or item.get("error"):
        flash("DocumentShare not found.", "danger")
        return redirect(url_for("document_share_views.view_document_shares"))

    form = DocumentShareForm(data=item)
    if request.method == 'POST' and form.validate_on_submit():
        result = api_client.put_data(f"documents/shares/{item_id}", data=form.data)
        if result and not result.get("error"):
            flash("DocumentShare updated.", "success")
            return redirect(url_for("document_share_views.view_document_shares"))
        flash(result.get("error", "Update failed."), "danger")

    return render_template("documents/shares/edit.html", form=form, item=item)

# === DELETE ===
@document_share_views.route('/<int:item_id>/delete', methods=['POST'])
def delete_document_share_view(item_id):
    result = api_client.delete_data(f"documents/shares/{item_id}")
    if result and result.get("success"):
        flash("DocumentShare deleted.", "success")
    else:
        flash(result.get("error", "Failed to delete share."), "danger")
    return redirect(url_for("document_share_views.view_document_shares"))