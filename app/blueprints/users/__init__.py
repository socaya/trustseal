from flask import Blueprint

users_bp = Blueprint('users', __name__, url_prefix='/api')

from .routes import *