from flask import Blueprint, render_template, request, redirect, url_for, flash
from app.blueprints.documents.forms.document_template_form import DocumentTemplateForm
from app.services import api_client

document_template_views = Blueprint('document_template_views', __name__, url_prefix='/documents/templates')


# === LIST ===
@document_template_views.route('/')
def list_templates():
    items = api_client.get_data("document-templates") or []
    return render_template('documents/templates/list.html', items=items)


# === DETAILS ===
@document_template_views.route('/<int:item_id>')
def template_details(item_id):
    item = api_client.get_data(f"document-templates/{item_id}")
    if not item or item.get("error"):
        flash("Template not found.", "danger")
        return redirect(url_for("document_template_views.list_templates"))
    return render_template("documents/templates/details.html", item=item)


# === CREATE ===
@document_template_views.route('/create', methods=['GET', 'POST'])
def create_template_view():
    form = DocumentTemplateForm()
    if form.validate_on_submit():
        result = api_client.post_data("document-templates", data=form.data)
        if result and not result.get("error"):
            flash("Template created.", "success")
            return redirect(url_for("document_template_views.list_templates"))
        flash(result.get("error", "Failed to create template."), "danger")
    return render_template("documents/templates/create.html", form=form)


# === EDIT ===
@document_template_views.route('/<int:item_id>/edit', methods=['GET', 'POST'])
def edit_template_view(item_id):
    item = api_client.get_data(f"document-templates/{item_id}")
    if not item or item.get("error"):
        flash("Template not found.", "danger")
        return redirect(url_for("document_template_views.list_templates"))

    form = DocumentTemplateForm(data=item)
    if request.method == 'POST' and form.validate_on_submit():
        result = api_client.put_data(f"document-templates/{item_id}", data=form.data)
        if result and not result.get("error"):
            flash("Template updated.", "success")
            return redirect(url_for("document_template_views.list_templates"))
        flash(result.get("error", "Update failed."), "danger")

    return render_template("documents/templates/edit.html", form=form, item=item)


# === DELETE ===
@document_template_views.route('/<int:item_id>/delete', methods=['POST'])
def delete_template_view(item_id):
    result = api_client.delete_data(f"document-templates/{item_id}")
    if result and result.get("success"):
        flash("Template deleted.", "success")
    else:
        flash(result.get("error", "Failed to delete template."), "danger")
    return redirect(url_for("document_template_views.list_templates"))