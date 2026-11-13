from flask import session
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from flask_marshmallow import Marshmallow
from flask_jwt_extended import JWTManager

# Initialize Flask extensions
db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()

ma = Marshmallow()
jwt = JWTManager()

# Configure Flask-Login
login_manager.login_view = 'auth_views.login'
login_manager.login_message_category = 'info'

# Import User model for user_loader
from app.models.user import User  # Ensure this path is correct based on your structure

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))