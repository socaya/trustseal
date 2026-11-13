from flask import Blueprint, render_template, request, redirect, url_for, flash
from app.blueprints.documents.forms.document_section_form import DocumentSectionForm
from app.services import api_client

document_section_views = Blueprint('document_section_views', __name__, url_prefix='/documents/sections')


# === LIST ===
@document_section_views.route('/')
def list_sections():
    items = api_client.get_data("document-sections") or []
    return render_template('documents/sections/list.html', items=items)


# === DETAILS ===
@document_section_views.route('/<int:item_id>')
def section_details(item_id):
    item = api_client.get_data(f"document-sections/{item_id}")
    if not item or item.get("error"):
        flash("Section not found.", "danger")
        return redirect(url_for("document_section_views.list_sections"))
    return render_template("documents/sections/details.html", item=item)


# === CREATE ===
@document_section_views.route('/create', methods=['GET', 'POST'])
def create_section_view():
    form = DocumentSectionForm()
    if form.validate_on_submit():
        result = api_client.post_data("document-sections", data=form.data)
        if result and not result.get("error"):
            flash("Section created.", "success")
            return redirect(url_for("document_section_views.list_sections"))
        flash(result.get("error", "Failed to create section."), "danger")
    return render_template("documents/sections/create.html", form=form)


# === EDIT ===
@document_section_views.route('/<int:item_id>/edit', methods=['GET', 'POST'])
def edit_section_view(item_id):
    item = api_client.get_data(f"document-sections/{item_id}")
    if not item or item.get("error"):
        flash("Section not found.", "danger")
        return redirect(url_for("document_section_views.list_sections"))

    form = DocumentSectionForm(data=item)
    if request.method == 'POST' and form.validate_on_submit():
        result = api_client.put_data(f"document-sections/{item_id}", data=form.data)
        if result and not result.get("error"):
            flash("Section updated.", "success")
            return redirect(url_for("document_section_views.list_sections"))
        flash(result.get("error", "Update failed."), "danger")

    return render_template("documents/sections/edit.html", form=form, item=item)


# === DELETE ===
@document_section_views.route('/<int:item_id>/delete', methods=['POST'])
def delete_section_view(item_id):
    result = api_client.delete_data(f"document-sections/{item_id}")
    if result and result.get("success"):
        flash("Section deleted.", "success")
    else:
        flash(result.get("error", "Failed to delete section."), "danger")
    return redirect(url_for("document_section_views.list_sections"))