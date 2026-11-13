from flask import Blueprint

esignatures_bp = Blueprint('esignatures', __name__, url_prefix='/api')

from .routes import *
