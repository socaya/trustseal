from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import func
from .. import system_bp
from ....extensions import db
from ....models.system import Permission, Role, RolePermission, UserRole
from ....models.user import User
from ..forms.role_form import RoleForm


@system_bp.route('/roles', methods=['GET', 'POST'])
@login_required
def view_roles():
    if request.method == 'POST':
        action = (request.form.get('action') or 'create_role').strip()
        if action == 'delete_role':
            rid = request.form.get('role_id', type=int)
            role = db.session.get(Role, rid) if rid else None
            if role:
                RolePermission.query.filter_by(role_id=role.id).delete()
                UserRole.query.filter_by(role_id=role.id).delete()
                db.session.delete(role)
                db.session.commit()
                flash(f'Role "{role.name}" deleted.', 'success')
            return redirect(url_for('system.view_roles'))

        if action == 'toggle_perm':
            rid = request.form.get('role_id', type=int)
            pid = request.form.get('permission_id', type=int)
            if rid and pid:
                existing = RolePermission.query.filter_by(role_id=rid, permission_id=pid).first()
                if existing:
                    db.session.delete(existing)
                    db.session.commit()
                    flash('Permission removed from role.', 'success')
                else:
                    db.session.add(RolePermission(role_id=rid, permission_id=pid))
                    db.session.commit()
                    flash('Permission granted to role.', 'success')
            return redirect(url_for('system.view_roles') + '#matrix')

        if action == 'toggle_user_role':
            uid = request.form.get('user_id', type=int)
            rid = request.form.get('role_id', type=int)
            if uid and rid:
                user = User.query.filter_by(
                    id=uid, organization_id=current_user.organization_id
                ).first()
                role = db.session.get(Role, rid)
                if user and role:
                    existing = UserRole.query.filter_by(user_id=user.id, role_id=role.id).first()
                    if existing:
                        db.session.delete(existing)
                        db.session.commit()
                        flash(f'Removed "{role.name}" from {user.email}.', 'success')
                    else:
                        db.session.add(UserRole(user_id=user.id, role_id=role.id))
                        db.session.commit()
                        flash(f'Assigned "{role.name}" to {user.email}.', 'success')
            return redirect(url_for('system.view_roles') + '#assignments')

        name = (request.form.get('name') or '').strip()[:64]
        desc = (request.form.get('description') or '').strip()
        if name:
            existing = Role.query.filter(func.lower(Role.name) == name.lower()).first()
            if existing:
                flash(f'Role "{name}" already exists.', 'warning')
            else:
                db.session.add(Role(name=name, description=desc or None))
                db.session.commit()
                flash(f'Role "{name}" created.', 'success')
        return redirect(url_for('system.view_roles'))

    roles = Role.query.order_by(Role.name.asc()).all()
    permissions = Permission.query.order_by(Permission.name.asc()).all()
    perm_counts = dict(
        db.session.query(RolePermission.role_id, func.count(RolePermission.permission_id))
        .group_by(RolePermission.role_id).all()
    )
    user_counts = dict(
        db.session.query(UserRole.role_id, func.count(UserRole.user_id))
        .group_by(UserRole.role_id).all()
    )
    role_perm_pairs = set(
        db.session.query(RolePermission.role_id, RolePermission.permission_id).all()
    )
    tenant_users = (
        User.query
        .filter_by(organization_id=current_user.organization_id)
        .order_by(User.email.asc())
        .limit(200)
        .all()
    )
    user_role_map: dict[int, list[Role]] = {}
    role_by_id = {r.id: r for r in roles}
    if tenant_users:
        uids = [u.id for u in tenant_users]
        for ur in UserRole.query.filter(UserRole.user_id.in_(uids)).all():
            r = role_by_id.get(ur.role_id)
            if r:
                user_role_map.setdefault(ur.user_id, []).append(r)

    return render_template(
        "system/roles/list.html",
        items=roles,
        permissions=permissions,
        perm_counts=perm_counts,
        user_counts=user_counts,
        role_perm_pairs=role_perm_pairs,
        tenant_users=tenant_users,
        user_role_map=user_role_map,
    )


@system_bp.route('/roles/create', methods=['GET', 'POST'])
@login_required
def create_role_view():
    form = RoleForm()
    if form.validate_on_submit():
        name = (form.name.data or '').strip()[:64]
        if name and not Role.query.filter(func.lower(Role.name) == name.lower()).first():
            db.session.add(Role(name=name, description=getattr(form, 'description', None) and form.description.data or None))
            db.session.commit()
            flash("Role created.", "success")
            return redirect(url_for("system.view_roles"))
        flash("Role name already exists or is invalid.", "danger")
    return render_template("system/roles/create.html", form=form)
