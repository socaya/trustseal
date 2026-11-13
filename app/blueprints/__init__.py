# app/blueprints/__init__.py
#Documents ---

from .documents.views.document_views import document_views
from app.blueprints.documents.api.document_api import document_api
from .documents.views.document_signature_views import document_signature_views
from app.blueprints.documents.api.document_signature_api import document_signature_api
from .documents.views.document_share_views import document_share_views
from app.blueprints.documents.api.document_share_api import document_share_api
from .documents.views.document_version_views import document_version_views
from app.blueprints.documents.api.document_version_api import document_version_api
from .documents.views.document_party_views import document_party_views
from app.blueprints.documents.api.document_party_api import document_party_api
from .documents.views.document_activity_views import document_activity_views
from app.blueprints.documents.api.document_activity_api import document_activity_api

from .estamp import estamp_bp
from .esignatures import esignatures_bp
from .organizations import organizations_bp
from .subscriptions import subscription_bp
from .system import system_bp
from .users import users_bp
from .auth.routes.auth_api import auth_api
from .auth.routes.auth_views import auth_views