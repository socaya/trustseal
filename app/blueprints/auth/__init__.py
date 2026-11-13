from flask import Blueprint

from .routes import auth_views
from .routes import auth_api  # your API views

# Define the blueprint group (optional if not grouping further)
__all__ = ["auth_api", "auth_views"]