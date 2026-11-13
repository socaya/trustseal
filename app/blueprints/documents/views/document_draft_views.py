from flask import Blueprint, render_template, request, redirect, url_for, flash
from app.blueprints.documents.forms.document_draft_form import DocumentDraftForm
from app.services.api_client import get_data, post_data, put_data, delete_data

document_draft_views = Blueprint('document_draft', __name__, url_prefix='/document-draft')

@document_draft_views.route('/')
def list_document_draft():
    items = get_data('document-draft') or []
    return render_template('document-draft/list.html', items=items)

@document_draft_views.route('/create', methods=['GET', 'POST'])
def create_document_draft():
    form = DocumentDraftForm()
    if form.validate_on_submit():
        result = post_data('document-draft', data=form.data)
        if result and not result.get("error"):
            flash("Document Draft created successfully.", "success")
            return redirect(url_for('document_draft.list_document_draft'))
        flash(result.get("error", "Failed to create."), "danger")
    return render_template('document-draft/create.html', form=form)

@document_draft_views.route('/<int:item_id>/edit', methods=['GET', 'POST'])
def edit_document_draft(item_id):
    item = get_data(f"document-draft/{item_id}")
    if not item or item.get("error"):
        flash("Document Draft not found.", "danger")
        return redirect(url_for('document_draft.list_document_draft'))

    form = DocumentDraftForm(data=item)
    if request.method == 'POST' and form.validate_on_submit():
        result = put_data(f"document-draft/{item_id}", data=form.data)
        if result and not result.get("error"):
            flash("Document Draft updated successfully.", "success")
            return redirect(url_for('document_draft.list_document_draft'))
        flash(result.get("error", "Update failed."), "danger")
    return render_template('document-draft/edit.html', form=form, item=item)

@document_draft_views.route('/<int:item_id>/delete', methods=['POST'])
def delete_document_draft(item_id):
    result = delete_data(f"document-draft/{item_id}")
    if result and result.get("success"):
        flash("Document Draft deleted successfully.", "success")
    else:
        flash(result.get("error", "Failed to delete."), "danger")
    return redirect(url_for('document_draft.list_document_draft'))
