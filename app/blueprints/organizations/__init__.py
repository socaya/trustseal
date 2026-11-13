from flask import Blueprint

organizations_bp = Blueprint('organizations_bp', __name__)

from .routes.organization_api import *
from .routes.clients_api import *
from .routes.organization_views import *
from .routes.clients_views import *