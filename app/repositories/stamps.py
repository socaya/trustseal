"""Stamp asset repository.

Uses the existing ``DigitalStamp`` model from ``app.models.estamp`` until
the Phase 5 governed stamp refactor introduces ``StampAsset`` /
``StampRevision``.
"""
from __future__ import annotations

from typing import Optional

from app.models.estamp import DigitalStamp
from .base import TenantScopedRepository


class StampAssetRepository(TenantScopedRepository[DigitalStamp]):
    model = DigitalStamp
    tenant_column = "organization_id"

    def get_active(self, stamp_id: int) -> Optional[DigitalStamp]:
        q = self._base().filter(DigitalStamp.id == stamp_id)
        if hasattr(DigitalStamp, "is_active"):
            q = q.filter(DigitalStamp.is_active.is_(True))
        return q.first()
