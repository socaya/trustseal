from flask import Blueprint

estamp_bp = Blueprint('estamp', __name__, url_prefix='/api')

from .routes import *
