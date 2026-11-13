# app/blueprints/documents/__init__.py

# === API Blueprints ===
from app.blueprints.documents.api.document_api import document_api
from app.blueprints.documents.api.document_activity_api import document_activity_api
from app.blueprints.documents.api.document_party_api import document_party_api
from app.blueprints.documents.api.document_share_api import document_share_api
from app.blueprints.documents.api.document_signature_api import document_signature_api
from app.blueprints.documents.api.document_version_api import document_version_api
from app.blueprints.documents.api.document_draft_api import document_draft_api
from app.blueprints.documents.api.document_type_api import document_type_api
from app.blueprints.documents.api.document_template_api import document_template_api
from app.blueprints.documents.api.document_section_api import document_section_api
from app.blueprints.documents.api.document_reminder_api import document_reminder_api
from app.blueprints.documents.api.document_audit_log_api import document_audit_log_api

# === View Blueprints ===
from .views.document_views import document_views
from .views.document_activity_views import document_activity_views
from .views.document_party_views import document_party_views
from .views.document_share_views import document_share_views
from .views.document_signature_views import document_signature_views
from .views.document_version_views import document_version_views
from .views.document_draft_views import document_draft_views
from .views.document_type_views import document_type_views
from .views.document_template_views import document_template_views
from .views.document_section_views import document_section_views
from .views.document_reminder_views import document_reminder_views
from .views.document_audit_log_views import document_audit_log_views

# === Blueprint Collection ===
documents_blueprints = [
    document_api,
    document_views,
    document_activity_api,
    document_activity_views,
    document_party_api,
    document_party_views,
    document_share_api,
    document_share_views,
    document_signature_api,
    document_signature_views,
    document_version_api,
    document_version_views,
    document_draft_api,
    document_draft_views,
    document_type_api,
    document_type_views,
    document_template_api,
    document_template_views,
    document_section_api,
    document_section_views,
    document_reminder_api,
    document_reminder_views,
    document_audit_log_api,
    document_audit_log_views,
]