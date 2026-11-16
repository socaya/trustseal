"""Document templates with publication workflow + version history.

The legacy ``DocumentTemplate`` fields (``name``, ``description``,
``content``, ``is_active``, ``created_by``) are preserved so the
prior CRUD endpoints still work. Phase E adds:

* ``organization_id`` — tenant scoping.
* ``state`` — ``draft`` (editable) → ``published`` (locked for use) →
  ``archived`` (hidden but retained). Only the service layer is
  allowed to flip the state.
* ``current_version_id`` — FK to the currently-active version row.
* ``published_at`` / ``archived_at`` + the actors who did them —
  audit metadata.

The legacy ``content`` column mirrors the current version's body so
old consumers don't need to be rewritten.
"""
from datetime import datetime
from app.extensions import db


class DocumentTemplate(db.Model):
    __tablename__ = 'document_templates'

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(
        db.Integer,
        db.ForeignKey('organizations.id'),
        nullable=True,
        index=True,
    )
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    content = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True)
    state = db.Column(
        db.String(20),
        nullable=False,
        default="draft",
        server_default="draft",
    )
    # FK is declared in migration ``r8d317f2b1c8`` only. Keeping it off
    # the ORM model avoids a chicken-and-egg cycle with the versions
    # table during ``db.create_all`` in tests + ``migration_replay``.
    current_version_id = db.Column(db.BigInteger, nullable=True)
    published_at = db.Column(db.DateTime, nullable=True)
    published_by_id = db.Column(
        db.Integer, db.ForeignKey('users.id'), nullable=True
    )
    archived_at = db.Column(db.DateTime, nullable=True)
    archived_by_id = db.Column(
        db.Integer, db.ForeignKey('users.id'), nullable=True
    )
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user = db.relationship('User', foreign_keys=[created_by])
    versions = db.relationship(
        'DocumentTemplateVersion',
        back_populates='template',
        cascade='all, delete-orphan',
        foreign_keys='DocumentTemplateVersion.template_id',
    )

    __table_args__ = (
        db.CheckConstraint(
            "state IN ('draft','published','archived')",
            name="ck_document_template_state",
        ),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "organization_id": self.organization_id,
            "name": self.name,
            "description": self.description,
            "content": self.content,
            "is_active": self.is_active,
            "state": self.state,
            "current_version_id": self.current_version_id,
            "published_at": self.published_at.isoformat()
            if self.published_at
            else None,
            "archived_at": self.archived_at.isoformat()
            if self.archived_at
            else None,
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "user": {
                "id": self.user.id,
                "first_name": self.user.first_name,
                "last_name": self.user.last_name,
                "email": self.user.email,
            } if self.user else None
        }


class DocumentTemplateVersion(db.Model):
    """One immutable snapshot of a template's body.

    Each new revision bumps ``revision`` monotonically per template.
    Versions are append-only on the application side — the service
    never rewrites an existing row. ``published_at`` is set on the
    version that was current at the moment ``publish()`` ran so the
    audit trail captures exactly which bytes went live.
    """

    __tablename__ = 'document_template_versions'

    id = db.Column(db.BigInteger, primary_key=True)
    template_id = db.Column(
        db.Integer,
        db.ForeignKey('document_templates.id'),
        nullable=False,
        index=True,
    )
    revision = db.Column(db.Integer, nullable=False)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    content = db.Column(db.Text, nullable=False, default="")
    created_by_id = db.Column(
        db.Integer, db.ForeignKey('users.id'), nullable=False
    )
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    published_at = db.Column(db.DateTime, nullable=True)
    published_by_id = db.Column(
        db.Integer, db.ForeignKey('users.id'), nullable=True
    )

    template = db.relationship(
        'DocumentTemplate',
        back_populates='versions',
        foreign_keys=[template_id],
    )

    __table_args__ = (
        db.UniqueConstraint(
            'template_id', 'revision',
            name='uq_document_template_version',
        ),
        db.CheckConstraint(
            'revision > 0', name='ck_document_template_version_revision'
        ),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "template_id": self.template_id,
            "revision": self.revision,
            "name": self.name,
            "description": self.description,
            "content": self.content,
            "created_by_id": self.created_by_id,
            "created_at": self.created_at.isoformat(),
            "published_at": self.published_at.isoformat()
            if self.published_at
            else None,
        }
