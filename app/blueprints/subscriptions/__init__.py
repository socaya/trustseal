from flask import Blueprint

subscription_bp = Blueprint('subscription_bp', __name__, url_prefix='/api')

from .routes import *