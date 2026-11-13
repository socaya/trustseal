from flask import render_template, request, redirect, url_for, flash, Blueprint
from app.blueprints.documents.forms.document_activity_form import DocumentActivityForm
from ....services import api_client

document_activity_views = Blueprint('document_activity_views', __name__, url_prefix='/documents/activities')

# === LIST ===
@document_activity_views.route('/')
def view_document_activities():
    items = api_client.get_data("document-activity") or []
    return render_template('documents/activities/list.html', items=items)

# === CREATE ===
@document_activity_views.route('/create', methods=['GET', 'POST'])
def create_document_activity_view():
    form = DocumentActivityForm()
    if form.validate_on_submit():
        result = api_client.post_data("document-activity", data=form.data)
        if result and not result.get("error"):
            flash("DocumentActivity created.", "success")
            return redirect(url_for('document_activity_views.view_document_activities'))
        flash(result.get("error", "Failed to create document activity."), "danger")
    return render_template("documents/activities/create.html", form=form)

# === EDIT ===
@document_activity_views.route('/<int:item_id>/edit', methods=['GET', 'POST'])
def edit_document_activity_view(item_id):
    item = api_client.get_data(f"document-activity/{item_id}")
    if not item or item.get("error"):
        flash("DocumentActivity not found.", "danger")
        return redirect(url_for("document_activity_views.view_document_activities"))

    form = DocumentActivityForm(data=item)
    if request.method == 'POST' and form.validate_on_submit():
        result = api_client.put_data(f"document-activity/{item_id}", data=form.data)
        if result and not result.get("error"):
            flash("DocumentActivity updated.", "success")
            return redirect(url_for("document_activity_views.view_document_activities"))
        flash(result.get("error", "Update failed."), "danger")

    return render_template("documents/activities/edit.html", form=form, item=item)

# === DELETE ===
@document_activity_views.route('/<int:item_id>/delete', methods=['POST'])
def delete_document_activity_view(item_id):
    result = api_client.delete_data(f"document-activity/{item_id}")
    if result and result.get("success"):
        flash("DocumentActivity deleted.", "success")
    else:
        flash(result.get("error", "Failed to delete item."), "danger")
    return redirect(url_for("document_activity_views.view_document_activities"))