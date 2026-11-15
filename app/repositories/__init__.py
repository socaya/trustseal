"""Tenant-scoped repository boundary.

See ADR 0003. Every tenant-scoped resource is read or written through a
repository bound to a specific tenant at construction time. Repositories
never expose raw SQLAlchemy ``query`` objects; they expose narrow finders
so that policy predicates (``app/policies/authorization.py``) can receive
an already-scoped resource.
"""
from .base import TenantScopedRepository
from .documents import DocumentRepository
from .envelopes import EnvelopeRepository, EnvelopeParticipantRepository
from .stamps import StampAssetRepository
from .dossiers import ValidationDossierRepository

__all__ = [
    "TenantScopedRepository",
    "DocumentRepository",
    "EnvelopeRepository",
    "EnvelopeParticipantRepository",
    "StampAssetRepository",
    "ValidationDossierRepository",
]
