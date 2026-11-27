"""TrustSeal Enterprise Project Management domain package (v2.0)."""
from __future__ import annotations

from app.blueprints.projects.api import (
    portfolios_api,
    programmes_api,
    project_intakes_api,
    projects_v2_api,
)
from app.blueprints.projects.api_batch2 import (
    projects_batch2_api,
    resources_api,
)
from app.blueprints.projects.api_batch3 import (
    project_portal_api,
    project_templates_api,
    projects_batch3_api,
)
from app.blueprints.projects.timesheets_api import (
    project_timesheets_v21_api,
    timesheets_v21_api,
)

__all__ = [
    "portfolios_api",
    "programmes_api",
    "project_intakes_api",
    "projects_v2_api",
    "resources_api",
    "projects_batch2_api",
    "project_templates_api",
    "project_portal_api",
    "projects_batch3_api",
    "timesheets_v21_api",
    "project_timesheets_v21_api",
]
