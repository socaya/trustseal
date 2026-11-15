"""Base class for tenant-scoped repositories.

A repository is constructed with a session and a ``tenant_id``. Every finder
joins on ``tenant_id`` (or the column named via ``tenant_column``). The
``__init_subclass__`` hook requires subclasses to declare ``model`` and
``tenant_column`` so no finder can silently run unscoped.
"""
from __future__ import annotations

from typing import Any, Generic, Optional, TypeVar

from sqlalchemy.orm import Session

T = TypeVar("T")


class TenantScopedRepository(Generic[T]):
    model: type
    tenant_column: str = "organization_id"

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if not hasattr(cls, "model") or cls.model is None:
            raise TypeError(f"{cls.__name__} must set a ``model`` attribute")
        if not hasattr(cls.model, cls.tenant_column):
            raise TypeError(
                f"{cls.model.__name__} has no column {cls.tenant_column!r}; "
                "set tenant_column to match the model's tenant FK."
            )

    def __init__(self, session: Session, tenant_id: int) -> None:
        if not isinstance(tenant_id, int):
            raise TypeError("tenant_id must be int")
        self._session = session
        self._tenant_id = tenant_id

    @property
    def tenant_id(self) -> int:
        return self._tenant_id

    def _base(self):
        return self._session.query(self.model).filter(
            getattr(self.model, self.tenant_column) == self._tenant_id
        )

    def get(self, resource_id: int) -> Optional[T]:
        return self._base().filter(self.model.id == resource_id).first()

    def exists(self, resource_id: int) -> bool:
        return self._base().filter(self.model.id == resource_id).first() is not None

    def list(self, *, limit: int = 100, offset: int = 0, **filters: Any) -> list[T]:
        if limit < 1 or limit > 500:
            raise ValueError("limit must be between 1 and 500")
        if offset < 0:
            raise ValueError("offset must be >= 0")
        q = self._base()
        for name, value in filters.items():
            q = q.filter(getattr(self.model, name) == value)
        return q.order_by(self.model.id.desc()).offset(offset).limit(limit).all()
