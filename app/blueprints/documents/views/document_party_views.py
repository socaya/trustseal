from flask import Blueprint, render_template, request, redirect, url_for, flash
from ....services import api_client
from app.blueprints.documents.forms.document_party_form import DocumentPartyForm

document_party_views = Blueprint('document_party_views', __name__, url_prefix='/documents/parties')

# === LIST ===
@document_party_views.route('/')
def view_document_parties():
    items = api_client.get_data("documents/parties") or []
    return render_template('documents/parties/list.html', items=items)

# === CREATE ===
@document_party_views.route('/create', methods=['GET', 'POST'])
def create_document_party_view():
    form = DocumentPartyForm()
    if form.validate_on_submit():
        result = api_client.post_data("documents/parties", data=form.data)
        if result and not result.get("error"):
            flash("DocumentParty created.", "success")
            return redirect(url_for("document_party_views.view_document_parties"))
        flash(result.get("error", "Failed to create party."), "danger")
    return render_template("documents/parties/create.html", form=form)

# === EDIT ===
@document_party_views.route('/<int:item_id>/edit', methods=['GET', 'POST'])
def edit_document_party_view(item_id):
    item = api_client.get_data(f"documents/parties/{item_id}")
    if not item or item.get("error"):
        flash("DocumentParty not found.", "danger")
        return redirect(url_for("document_party_views.view_document_parties"))

    form = DocumentPartyForm(data=item)
    if request.method == 'POST' and form.validate_on_submit():
        result = api_client.put_data(f"documents/parties/{item_id}", data=form.data)
        if result and not result.get("error"):
            flash("DocumentParty updated.", "success")
            return redirect(url_for("document_party_views.view_document_parties"))
        flash(result.get("error", "Update failed."), "danger")

    return render_template("documents/parties/edit.html", form=form, item=item)

# === DELETE ===
@document_party_views.route('/<int:item_id>/delete', methods=['POST'])
def delete_document_party_view(item_id):
    result = api_client.delete_data(f"documents/parties/{item_id}")
    if result and result.get("success"):
        flash("DocumentParty deleted.", "success")
    else:
        flash(result.get("error", "Failed to delete party."), "danger")
    return redirect(url_for("document_party_views.view_document_parties"))
