"""Project-scoped authorization & finance visibility checks (PM-33).

Combines organization tenancy, Org/Platform Admin roles, Project owner/sponsor,
and explicit ``ProjectMembership`` rows. Deny-by-default across tenants (404
anti-enumeration) and enforces finance rate/cost visibility boundaries.
"""
from __future__ import annotations

from flask import abort

from app.models.contract_workflow import Project
from app.models.project_management import ProjectMembership
from app.policies.api_access import get_user_nav_roles


_MANAGER_ROLES = frozenset(("sponsor", "pmo", "project_manager", "programme_manager"))
_FINANCE_ROLES = frozenset(("sponsor", "pmo", "project_manager", "finance", "procurement"))
_APPROVER_ROLES = frozenset(("sponsor", "pmo", "project_manager", "programme_manager", "finance"))
_READONLY_ROLES = frozenset(("viewer", "external_client"))


def is_org_or_platform_admin(user) -> bool:
    roles = get_user_nav_roles(user)
    return bool(roles.get("nav_is_org_admin") or roles.get("nav_is_platform_admin"))


def get_membership(project: Project, user) -> ProjectMembership | None:
    if not user or not getattr(user, "id", None):
        return None
    return ProjectMembership.query.filter_by(
        organization_id=project.organization_id,
        project_id=project.id,
        user_id=user.id,
        is_active=True,
    ).first()


def load_authorized_project(project_id: int, user, *, require_write: bool = False) -> Project:
    """Resolve a project in the user's tenant and verify project-level authorization.

    Returns 404 for cross-tenant or missing projects (anti-enumeration),
    and 403 when the project exists in the same tenant but the user lacks permission.
    """
    if not user or not getattr(user, "is_authenticated", False):
        abort(401)
    if getattr(user, "organization_id", None) is None:
        abort(403, description="organization_required")

    proj = Project.query.filter_by(id=project_id, organization_id=user.organization_id).first()
    if proj is None:
        abort(404)

    # Org/Platform admins, project owner, or sponsor have access
    if is_org_or_platform_admin(user) or proj.owner_user_id == user.id or proj.sponsor_user_id == user.id:
        return proj

    # Check explicit project membership
    mem = get_membership(proj, user)
    if mem is not None:
        if require_write and mem.project_role in _READONLY_ROLES:
            abort(403, description="project_read_only_role")
        return proj

    # For restricted/confidential projects, require explicit membership
    if (proj.confidentiality or "internal") in ("confidential", "restricted"):
        abort(403, description="project_membership_required")

    # For internal projects with no explicit membership rows yet, same-tenant members can access
    has_any_members = ProjectMembership.query.filter_by(
        organization_id=proj.organization_id, project_id=proj.id, is_active=True
    ).first()
    if has_any_members is not None:
        abort(403, description="project_membership_required")
    return proj


def can_view_project_finance(project: Project, user) -> bool:
    if is_org_or_platform_admin(user) or project.owner_user_id == user.id or project.sponsor_user_id == user.id:
        return True
    mem = get_membership(project, user)
    if mem is not None:
        return bool(mem.can_view_finance or mem.project_role in _FINANCE_ROLES)
    return (project.confidentiality or "internal") == "internal"


def can_approve_project_governance(project: Project, user) -> bool:
    if is_org_or_platform_admin(user) or project.owner_user_id == user.id or project.sponsor_user_id == user.id:
        return True
    mem = get_membership(project, user)
    return bool(mem is not None and mem.project_role in _APPROVER_ROLES)


def assert_project_mutable(project: Project) -> None:
    if (project.lifecycle_state or "executing") in ("closed", "archived", "cancelled"):
        abort(409, description=f"Project is {project.lifecycle_state} and read-only")
