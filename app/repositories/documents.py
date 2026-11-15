"""Document repository scoped to a single tenant."""
from __future__ import annotations

from typing import Optional

from app.models.documents.document import Document
from .base import TenantScopedRepository


class DocumentRepository(TenantScopedRepository[Document]):
    model = Document
    tenant_column = "organization_id"

    def get_active(self, document_id: int) -> Optional[Document]:
        """Return a non-deleted document or None."""
        return self._base().filter(
            Document.id == document_id, Document.deleted_at.is_(None)
        ).first()

    def owned_by(self, document_id: int, user_id: int) -> Optional[Document]:
        """Return a non-deleted, user-owned document or None."""
        return self._base().filter(
            Document.id == document_id,
            Document.created_by == user_id,
            Document.deleted_at.is_(None),
        ).first()
