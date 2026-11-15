"""Validation dossier repository."""
from __future__ import annotations

from app.models.validation_dossier import ValidationDossier
from .base import TenantScopedRepository


class ValidationDossierRepository(TenantScopedRepository[ValidationDossier]):
    model = ValidationDossier
    tenant_column = "organization_id"
