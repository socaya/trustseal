from flask import Blueprint

# Create the system blueprint
system_bp = Blueprint("system", __name__)

# Import and register route modules to attach their views to the blueprint
from .routes.main_views import main_views
from .routes.permissions_views import *
from .routes.roles_views import *
from .routes.settings_views import *
from .routes.user_roles_views import *

from .routes.permissions_api import *
from .routes.roles_api import *
from .routes.settings_api import *
from .routes.role_permissions_api import *
from .routes.user_roles_api import *
from .routes.audit_logs_api import *

# Register `main_views` separately if needed
system_bp.register_blueprint(main_views)