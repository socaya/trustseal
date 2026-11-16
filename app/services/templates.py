"""Document template publication workflow.

Public API:

* ``create_template(organization_id, name, content, *, created_by_id,
  description=None)`` — initial v1 version, template starts in
  ``draft``.
* ``new_version(template, *, name, content, description, author_id)``
  — refuses when the template is archived or published. On a
  published template, publish must be undone to another draft
  (``start_revision``) before a new version can be added.
* ``start_revision(template, author_id)`` — move a published
  template back to draft while preserving history.
* ``publish(template, *, published_by_id)`` — flip the current
  version's ``published_at`` and the template's ``state``. The caller
  is responsible for :mod:`app.policies.separation_of_duties`
  checks (requester ≠ approver) at the HTTP layer.
* ``archive(template, *, archived_by_id)`` — final state; refuses
  further mutations.

All transitions emit a SecurityEvent for the chained audit log.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from app.extensions import db
from app.models.documents.document_template import (
    DocumentTemplate,
    DocumentTemplateVersion,
)
from app.models.event_delivery import SecurityEvent


class TemplateError(Exception):
    """Policy violation in the template service."""


def _emit(
    *,
    actor_id: int,
    organization_id: Optional[int],
    action: str,
    resource_id: int,
    outcome: str = "ok",
) -> None:
    db.session.add(
        SecurityEvent(
            organization_id=organization_id,
            actor_id=actor_id,
            action=action,
            resource_type="document_template",
            resource_id=resource_id,
            outcome=outcome,
            correlation_id=uuid.uuid4().hex,
        )
    )


def create_template(
    organization_id: int,
    name: str,
    content: str,
    *,
    created_by_id: int,
    description: Optional[str] = None,
) -> DocumentTemplate:
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 200:
        raise TemplateError("name_invalid")
    if content is None:
        content = ""
    template = DocumentTemplate(
        organization_id=organization_id,
        name=name.strip(),
        description=description,
        content=content,
        is_active=True,
        state="draft",
        created_by=created_by_id,
    )
    db.session.add(template)
    db.session.flush()
    version = DocumentTemplateVersion(
        template_id=template.id,
        revision=1,
        name=template.name,
        description=description,
        content=content,
        created_by_id=created_by_id,
    )
    db.session.add(version)
    db.session.flush()
    template.current_version_id = version.id
    _emit(
        actor_id=created_by_id,
        organization_id=organization_id,
        action="template.created",
        resource_id=template.id,
    )
    return template


def new_version(
    template: DocumentTemplate,
    *,
    name: str,
    content: str,
    description: Optional[str],
    author_id: int,
) -> DocumentTemplateVersion:
    if template.state == "archived":
        raise TemplateError("template_archived")
    if template.state == "published":
        raise TemplateError("start_revision_before_new_version")
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 200:
        raise TemplateError("name_invalid")
    current_max = (
        db.session.query(db.func.max(DocumentTemplateVersion.revision))
        .filter_by(template_id=template.id)
        .scalar()
        or 0
    )
    version = DocumentTemplateVersion(
        template_id=template.id,
        revision=current_max + 1,
        name=name.strip(),
        description=description,
        content=content or "",
        created_by_id=author_id,
    )
    db.session.add(version)
    db.session.flush()
    template.name = name.strip()
    template.description = description
    template.content = content or ""
    template.current_version_id = version.id
    _emit(
        actor_id=author_id,
        organization_id=template.organization_id,
        action="template.version_added",
        resource_id=template.id,
    )
    return version


def start_revision(template: DocumentTemplate, author_id: int) -> DocumentTemplate:
    """Move a published template back to draft so a new version can land."""
    if template.state != "published":
        raise TemplateError("only_published_templates_can_revise")
    template.state = "draft"
    _emit(
        actor_id=author_id,
        organization_id=template.organization_id,
        action="template.revision_started",
        resource_id=template.id,
    )
    return template


def publish(
    template: DocumentTemplate, *, published_by_id: int
) -> DocumentTemplate:
    if template.state == "archived":
        raise TemplateError("template_archived")
    if template.state == "published":
        return template
    if template.current_version_id is None:
        raise TemplateError("no_current_version")
    now = datetime.utcnow()
    template.state = "published"
    template.published_at = now
    template.published_by_id = published_by_id
    version = db.session.get(
        DocumentTemplateVersion, template.current_version_id
    )
    if version is not None and version.published_at is None:
        version.published_at = now
        version.published_by_id = published_by_id
    _emit(
        actor_id=published_by_id,
        organization_id=template.organization_id,
        action="template.published",
        resource_id=template.id,
    )
    return template


def archive(
    template: DocumentTemplate, *, archived_by_id: int
) -> DocumentTemplate:
    if template.state == "archived":
        return template
    template.state = "archived"
    template.is_active = False
    template.archived_at = datetime.utcnow()
    template.archived_by_id = archived_by_id
    _emit(
        actor_id=archived_by_id,
        organization_id=template.organization_id,
        action="template.archived",
        resource_id=template.id,
    )
    return template
