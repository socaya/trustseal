from flask import Blueprint, render_template, request, redirect, url_for, flash
from app.blueprints.documents.forms.document_version_form import DocumentVersionForm
from ....services import api_client

document_version_views = Blueprint('document_version_views', __name__, url_prefix='/documents/versions')

# === LIST ===
@document_version_views.route('/')
def view_document_versions():
    items = api_client.get_data("documents/versions") or []
    return render_template('documents/versions/list.html', items=items)

# === CREATE ===
@document_version_views.route('/create', methods=['GET', 'POST'])
def create_document_version_view():
    form = DocumentVersionForm()
    if form.validate_on_submit():
        result = api_client.post_data("documents/versions", data=form.data)
        if result and not result.get("error"):
            flash("DocumentVersion created.", "success")
            return redirect(url_for("document_version_views.view_document_versions"))
        flash(result.get("error", "Failed to create version."), "danger")
    return render_template("documents/versions/create.html", form=form)

# === EDIT ===
@document_version_views.route('/<int:item_id>/edit', methods=['GET', 'POST'])
def edit_document_version_view(item_id):
    item = api_client.get_data(f"documents/versions/{item_id}")
    if not item or item.get("error"):
        flash("DocumentVersion not found.", "danger")
        return redirect(url_for("document_version_views.view_document_versions"))

    form = DocumentVersionForm(data=item)
    if request.method == 'POST' and form.validate_on_submit():
        result = api_client.put_data(f"documents/versions/{item_id}", data=form.data)
        if result and not result.get("error"):
            flash("DocumentVersion updated.", "success")
            return redirect(url_for("document_version_views.view_document_versions"))
        flash(result.get("error", "Update failed."), "danger")

    return render_template("documents/versions/edit.html", form=form, item=item)

# === DELETE ===
@document_version_views.route('/<int:item_id>/delete', methods=['POST'])
def delete_document_version_view(item_id):
    result = api_client.delete_data(f"documents/versions/{item_id}")
    if result and result.get("success"):
        flash("DocumentVersion deleted.", "success")
    else:
        flash(result.get("error", "Failed to delete version."), "danger")
    return redirect(url_for("document_version_views.view_document_versions"))