"""TrustSeal Contracts Lifecycle Management (CLM) blueprint package."""
from app.blueprints.contracts.api import (
    contract_templates_api,
    contracts_api,
    projects_api,
)
from app.blueprints.contracts.views import contracts_views

__all__ = [
    "contracts_api",
    "projects_api",
    "contract_templates_api",
    "contracts_views",
]
