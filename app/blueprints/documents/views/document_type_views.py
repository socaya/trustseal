from flask import Blueprint, render_template, request, redirect, url_for, flash
from app.blueprints.documents.forms.document_type_form import DocumentTypeForm
from app.services.api_client import get_data, post_data, put_data, delete_data

document_type_views = Blueprint('document_type_views', __name__, url_prefix='/document-type')

@document_type_views.route('/')
def list_document_type():
    items = get_data('document-type') or []
    return render_template('document-type/list.html', items=items)

@document_type_views.route('/create', methods=['GET', 'POST'])
def create_document_type():
    form = DocumentTypeForm()
    if form.validate_on_submit():
        result = post_data('document-type', data=form.data)
        if result and not result.get("error"):
            flash("Document Type created successfully.", "success")
            return redirect(url_for('document_type.list_document_type'))
        flash(result.get("error", "Failed to create."), "danger")
    return render_template('document-type/create.html', form=form)

@document_type_views.route('/<int:item_id>/edit', methods=['GET', 'POST'])
def edit_document_type(item_id):
    item = get_data(f"document-type/{item_id}")
    if not item or item.get("error"):
        flash("Document Type not found.", "danger")
        return redirect(url_for('document_type.list_document_type'))

    form = DocumentTypeForm(data=item)
    if request.method == 'POST' and form.validate_on_submit():
        result = put_data(f"document-type/{item_id}", data=form.data)
        if result and not result.get("error"):
            flash("Document Type updated successfully.", "success")
            return redirect(url_for('document_type.list_document_type'))
        flash(result.get("error", "Update failed."), "danger")
    return render_template('document-type/edit.html', form=form, item=item)

@document_type_views.route('/<int:item_id>/delete', methods=['POST'])
def delete_document_type(item_id):
    result = delete_data(f"document-type/{item_id}")
    if result and result.get("success"):
        flash("Document Type deleted successfully.", "success")
    else:
        flash(result.get("error", "Failed to delete."), "danger")
    return redirect(url_for('document_type.list_document_type'))
