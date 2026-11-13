from flask import Blueprint, render_template, request, redirect, url_for, flash
from app.blueprints.documents.forms.document_reminder_form import DocumentReminderForm
from app.services import api_client

document_reminder_views = Blueprint('document_reminder_views', __name__, url_prefix='/documents/reminders')


# === LIST ===
@document_reminder_views.route('/')
def list_reminders():
    items = api_client.get_data("document-reminders") or []
    return render_template('documents/reminders/list.html', items=items)


# === DETAILS ===
@document_reminder_views.route('/<int:item_id>')
def reminder_details(item_id):
    item = api_client.get_data(f"document-reminders/{item_id}")
    if not item or item.get("error"):
        flash("Reminder not found.", "danger")
        return redirect(url_for("document_reminder_views.list_reminders"))
    return render_template("documents/reminders/details.html", item=item)


# === CREATE ===
@document_reminder_views.route('/create', methods=['GET', 'POST'])
def create_reminder_view():
    form = DocumentReminderForm()
    if form.validate_on_submit():
        result = api_client.post_data("document-reminders", data=form.data)
        if result and not result.get("error"):
            flash("Reminder created.", "success")
            return redirect(url_for("document_reminder_views.list_reminders"))
        flash(result.get("error", "Failed to create reminder."), "danger")
    return render_template("documents/reminders/create.html", form=form)


# === EDIT ===
@document_reminder_views.route('/<int:item_id>/edit', methods=['GET', 'POST'])
def edit_reminder_view(item_id):
    item = api_client.get_data(f"document-reminders/{item_id}")
    if not item or item.get("error"):
        flash("Reminder not found.", "danger")
        return redirect(url_for("document_reminder_views.list_reminders"))

    form = DocumentReminderForm(data=item)
    if request.method == 'POST' and form.validate_on_submit():
        result = api_client.put_data(f"document-reminders/{item_id}", data=form.data)
        if result and not result.get("error"):
            flash("Reminder updated.", "success")
            return redirect(url_for("document_reminder_views.list_reminders"))
        flash(result.get("error", "Update failed."), "danger")

    return render_template("documents/reminders/edit.html", form=form, item=item)


# === DELETE ===
@document_reminder_views.route('/<int:item_id>/delete', methods=['POST'])
def delete_reminder_view(item_id):
    result = api_client.delete_data(f"document-reminders/{item_id}")
    if result and result.get("success"):
        flash("Reminder deleted.", "success")
    else:
        flash(result.get("error", "Failed to delete reminder."), "danger")
    return redirect(url_for("document_reminder_views.list_reminders"))