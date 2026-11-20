from flask import Blueprint, abort, render_template, request, redirect, url_for, flash
from flask_login import current_user, login_required
from ....services import api_client
from app.blueprints.documents.forms.document_party_form import DocumentPartyForm
from app.models.documents.document import Document
from app.models.documents.document_party import DocumentParty
from app.models.user import User

document_party_views = Blueprint('document_party_views', __name__, url_prefix='/documents/parties')

# === LIST ===
@document_party_views.route('/')
@login_required
def view_document_parties():
    if current_user.organization_id is None:
        abort(403)
    org_id = current_user.organization_id
    contacts = []
    seen = set()

    # 1. DocumentParty records scoped to tenant documents
    try:
        rows = (
            DocumentParty.query
            .join(Document, Document.id == DocumentParty.document_id)
            .filter(Document.organization_id == org_id)
            .order_by(DocumentParty.id.desc())
            .limit(250)
            .all()
        )
        u_ids = list({r.user_id for r in rows if r.user_id})
        users = {u.id: u for u in User.query.filter(User.id.in_(u_ids)).all()} if u_ids else {}
        for r in rows:
            u = users.get(r.user_id) if r.user_id else None
            email = r.external_email or (u.email if u else "")
            name = ((u.get_full_name() or u.username) if u else "") or email or f"Party #{r.id}"
            contacts.append({
                "name": name,
                "email": email or "—",
                "role": r.role or "party",
                "status": (r.status or "pending").lower(),
                "source": "Document Party",
                "signed_at": r.signed_at.strftime("%Y-%m-%d") if r.signed_at else "—",
            })
            if email:
                seen.add(email.lower())
    except Exception:
        pass

    # 2. EnvelopeParticipant records scoped to tenant envelopes
    try:
        from app.models.signing_envelope import EnvelopeParticipant, SigningEnvelope
        ep_rows = (
            EnvelopeParticipant.query
            .join(SigningEnvelope, SigningEnvelope.id == EnvelopeParticipant.envelope_id)
            .filter(SigningEnvelope.organization_id == org_id)
            .order_by(EnvelopeParticipant.id.desc())
            .limit(250)
            .all()
        )
        for p in ep_rows:
            email = getattr(p, "email", "") or ""
            contacts.append({
                "name": getattr(p, "name", None) or email or f"Participant #{p.id}",
                "email": email or "—",
                "role": getattr(p, "role", None) or "signer",
                "status": (getattr(p, "status", None) or "pending").lower(),
                "source": "Envelope Signer",
                "signed_at": p.signed_at.strftime("%Y-%m-%d") if getattr(p, "signed_at", None) else "—",
            })
    except Exception:
        pass

    return render_template('documents/parties/list.html', items=contacts)

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
