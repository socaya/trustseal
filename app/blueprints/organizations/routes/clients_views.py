from flask import abort, render_template, request, redirect, url_for, flash
from flask_login import current_user, login_required
from .. import organizations_bp
from ....extensions import db
from ....models.organization import Client
from ....services import api_client
from ..forms.client_form import ClientForm


@organizations_bp.route('/clients', methods=['GET', 'POST'])
@login_required
def view_clients():
    if current_user.organization_id is None:
        abort(403)
    if request.method == 'POST':
        action = (request.form.get('action') or 'create').strip()
        if action == 'delete':
            cid = request.form.get('client_id', type=int)
            row = db.session.get(Client, cid) if cid else None
            if row and row.organization_id == current_user.organization_id:
                db.session.delete(row)
                db.session.commit()
                flash('Client deleted.', 'success')
            return redirect(url_for('organizations_bp.view_clients'))
        if action == 'toggle_active':
            cid = request.form.get('client_id', type=int)
            row = db.session.get(Client, cid) if cid else None
            if row and row.organization_id == current_user.organization_id:
                row.is_active = not bool(row.is_active)
                db.session.commit()
                flash(f'Client "{row.name}" marked {"active" if row.is_active else "inactive"}.', 'success')
            return redirect(url_for('organizations_bp.view_clients'))
        if action == 'edit':
            cid = request.form.get('client_id', type=int)
            row = db.session.get(Client, cid) if cid else None
            name = (request.form.get('name') or '').strip()[:120]
            if row and row.organization_id == current_user.organization_id and name:
                row.name = name
                row.email = (request.form.get('email') or '').strip()[:120] or None
                row.phone = (request.form.get('phone') or '').strip()[:20] or None
                row.tax_id = (request.form.get('tax_id') or '').strip()[:50] or None
                row.address = (request.form.get('address') or '').strip() or None
                db.session.commit()
                flash(f'Client "{name}" updated.', 'success')
            return redirect(url_for('organizations_bp.view_clients'))
        name = (request.form.get('name') or '').strip()[:120]
        if name:
            row = Client(
                organization_id=current_user.organization_id,
                name=name,
                email=(request.form.get('email') or '').strip()[:120] or None,
                phone=(request.form.get('phone') or '').strip()[:20] or None,
                tax_id=(request.form.get('tax_id') or '').strip()[:50] or None,
                address=(request.form.get('address') or '').strip() or None,
                is_active=True,
            )
            db.session.add(row)
            db.session.commit()
            flash(f'Client "{name}" added.', 'success')
        return redirect(url_for('organizations_bp.view_clients'))

    items = (
        Client.query
        .filter(Client.organization_id == current_user.organization_id)
        .order_by(Client.created_at.desc())
        .limit(300)
        .all()
    )
    return render_template("organizations/clients/list.html", items=items)

@organizations_bp.route('/clients/create', methods=['GET', 'POST'])
def create_client_view():
    form = ClientForm()
    if form.validate_on_submit():
        result = api_client.post_data("clients", data=form.data)
        if result and not result.get("error"):
            flash("Client created.", "success")
            return redirect(url_for("organizations.view_clients"))
        flash(result.get("error", "Failed to create client."), "danger")
    return render_template("organizations/clients/create.html", form=form)

@organizations_bp.route('/clients/<int:item_id>/edit', methods=['GET', 'POST'])
def edit_client_view(item_id):
    item = api_client.get_data(f"clients/{item_id}")
    if not item or item.get("error"):
        flash("Client not found.", "danger")
        return redirect(url_for("organizations.view_clients"))

    form = ClientForm(data=item)
    if request.method == 'POST' and form.validate_on_submit():
        result = api_client.put_data(f"clients/{item_id}", data=form.data)
        if result and not result.get("error"):
            flash("Client updated.", "success")
            return redirect(url_for("organizations.view_clients"))
        flash(result.get("error", "Update failed."), "danger")
    return render_template("organizations/clients/edit.html", form=form, item=item)

@organizations_bp.route('/clients/<int:item_id>/delete', methods=['POST'])
def delete_client_view(item_id):
    result = api_client.delete_data(f"clients/{item_id}")
    if result.get("success"):
        flash("Client deleted.", "success")
    else:
        flash(result.get("error", "Failed to delete client."), "danger")
    return redirect(url_for("organizations.view_clients"))