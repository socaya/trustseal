import os
import logging
from datetime import datetime
from flask import (
    Flask, render_template, session, request, redirect, url_for, current_app, flash # Added flash import
)
from dotenv import load_dotenv
from flask_jwt_extended import decode_token, JWTManager # Added JWTManager for clarity if needed elsewhere
from flask_login import login_user, current_user, LoginManager

# Import extensions and models (adjust paths if necessary)
from .extensions import db, migrate, login_manager, ma, jwt
from .models import User # Assuming User model is in app.models

# Environment variables
load_dotenv()

# --- CLI ---
# Moved CLI registration function import outside create_app for better structure
from .cli.seed import register_cli

def create_app(config_class=None):
    """Factory function to create the Flask application."""
    app = Flask(__name__)

    # --- Configuration ---
    # Load configuration from object or environment variable
    # Ensure you have a 'CONFIG_NAME' key in your config classes for logging clarity
    loaded_config = config_class or os.getenv('FLASK_CONFIG') or 'config.Config'
    app.config.from_object(loaded_config)
    # Never start a production deployment with missing or example credentials.
    if str(app.config.get("FLASK_ENV", "")).lower() == "production":
        database_uri = app.config.get("SQLALCHEMY_DATABASE_URI") or ""
        if not app.config.get("SECRET_KEY") or not app.config.get("JWT_SECRET_KEY"):
            raise RuntimeError("Production SECRET_KEY and JWT_SECRET_KEY are required")
        if "trustseal:password@localhost" in database_uri:
            raise RuntimeError("Example database credentials cannot be used in production")
        if app.config.get("FLASK_DEBUG") or app.config.get("DEBUG"):
            raise RuntimeError("Flask debugging must be disabled in production")
    # Store the config name for logging, default if not present
    config_name = getattr(loaded_config, 'CONFIG_NAME', str(loaded_config))


    # --- Logging Configuration (Early Setup - Robust Handling) ---
    # Use app.logger instance available immediately after Flask(__name__)
    temp_logger = app.logger # Use the direct logger instance during setup

    log_level_setting = app.config.get("LOGGING_LEVEL", "INFO") # Get setting (could be str or int)
    log_level = logging.INFO # Default level
    log_level_name = "INFO" # Default name

    if isinstance(log_level_setting, str):
        # If it's a string, convert name to level, default to INFO on bad name
        log_level_name_temp = log_level_setting.upper()
        log_level = getattr(logging, log_level_name_temp, logging.INFO)
        log_level_name = logging.getLevelName(log_level) # Get canonical name
        if log_level == logging.INFO and log_level_name_temp != "INFO":
             temp_logger.warning(f"Invalid LOGGING_LEVEL name '{log_level_name_temp}'. Defaulting to INFO.")
    elif isinstance(log_level_setting, int):
        # If it's an int, use it directly (basic validation optional)
        # You might want to check if it's a valid logging level int e.g., if log_level_setting in logging._levelToName:
        log_level = log_level_setting
        log_level_name = logging.getLevelName(log_level) # Get canonical name
    else:
         # If it's neither string nor int, default to INFO
         temp_logger.warning(f"Invalid LOGGING_LEVEL type '{type(log_level_setting)}'. Defaulting to INFO.")
         log_level = logging.INFO
         log_level_name = logging.getLevelName(log_level)

    # Set the validated level on the app's logger directly
    temp_logger.setLevel(log_level)

    # Remove default Flask handler to avoid duplicate logs if adding custom ones
    temp_logger.handlers.clear()
    # Add a default handler (e.g., StreamHandler)
    handler = logging.StreamHandler()
    # You might want a more detailed formatter
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    temp_logger.addHandler(handler)

    # --- Extension Initialization ---
    db.init_app(app)
    migrate.init_app(app, db)
    ma.init_app(app)
    jwt.init_app(app) # Initialize Flask-JWT-Extended
    from .services import token_security  # Registers durable JWT blocklist callback

    # --- Flask-Login Configuration ---
    login_manager.init_app(app)
    login_manager.login_view = 'auth_views.login'  # Route name for the login page view
    login_manager.login_message = 'Please log in to access this page.' # User-friendly message
    login_manager.login_message_category = 'info' # Flash message category
    login_manager.session_protection = "strong"   # Helps prevent session hijacking

    @login_manager.user_loader
    def load_user(user_id):
        """Callback to reload the user object from the user ID stored in the session."""
        return User.query.get(int(user_id))

    @login_manager.unauthorized_handler
    def unauthorized():
        """Redirect unauthorized users to the login page."""
        session['next_url'] = request.url
        # Use current_app.logger here as it's called within a request context
        current_app.logger.debug(f"🔐 Unauthorized access attempt to {request.endpoint}. Redirecting to login.")
        flash(login_manager.login_message, login_manager.login_message_category)
        return redirect(url_for('auth_views.login'))

    # --- Jinja Filters ---
    def format_datetime(value, format="%Y-%m-%d %H:%M"):
        """Custom Jinja filter to format datetime objects."""
        if not isinstance(value, datetime):
            return value if value else ""
        return value.strftime(format)

    app.jinja_env.filters['datetime'] = format_datetime

    @app.context_processor
    def inject_current_year():
        """Inject the current year into template contexts."""
        return {'current_year': datetime.now().year}

    # --- Request Hooks ---
    @app.before_request
    def before_request_handler():
        # Historical uploads and generated QR files must never be served as
        # public Flask static assets. Reverse proxies must enforce the same.
        if request.path.startswith(("/static/uploads/", "/static/qrcodes/")):
            from flask import abort
            abort(404)
        session.permanent = True  # Make session persistent

        # Apply the interim API policy before legacy blueprints handle requests.
        from .policies.api_access import enforce_legacy_api_security
        enforce_legacy_api_security()
        if request.path.rstrip("/").startswith("/api/"):
            return

        # --- Allow Static Files ---
        if request.endpoint == 'static':
            return

        # --- Define Public View Endpoints (HTML Pages) ---
        public_endpoints = [
            'auth_views.login',
            'auth_views.register',
            # DO NOT list API endpoints here
        ]
        if request.endpoint in public_endpoints:
            current_app.logger.debug(f"🔓 Public access allowed for view endpoint: {request.endpoint}")
            return

        # --- Authentication Check & Auto-Login (For Web Views Only) ---
        if current_user.is_authenticated:
            current_app.logger.debug(
                f"👤 User {current_user.id} already authenticated via session for view: {request.endpoint}")
            return

        # Optional: Try JWT auto-login for web views if applicable
        access_token = session.get("access_token")
        if access_token:
            try:
                decoded = decode_token(access_token)
                user_id = decoded.get("sub")
                user = User.query.get(user_id)
                if user:
                    login_user(user)
                    current_app.logger.debug(
                        f"✅ Auto-login successful via JWT for user ID {user_id} accessing view {request.endpoint}")
                    return  # Allow access after successful auto-login
            except Exception as e:
                current_app.logger.warning(f"⚠️ JWT auto-login for view failed: {e}")
                # Clear potentially invalid/expired tokens from session
                session.pop("access_token", None)
                session.pop("refresh_token", None)

        # --- Redirect Unauthenticated Users for Protected Views ---
        session['next_url'] = request.url  # Store the intended destination
        current_app.logger.debug(
            f"🔐 Authentication required for VIEW {request.endpoint}. Redirecting to login. Next URL: {request.url}")
        # Use Flask-Login's standard mechanism
        return login_manager.unauthorized()


    @app.after_request
    def after_request_handler(response):
        """Runs after each request, before sending the response."""
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        return response

    # --- Blueprint Registration ---
    from .blueprints import ( # Assuming blueprints are in ./blueprints/__init__.py
        auth_api, auth_views, estamp_bp, esignatures_bp, organizations_bp,
        subscription_bp, system_bp, users_bp, document_views, document_api,
        document_activity_views, document_activity_api, document_party_views,
        document_party_api, document_share_views, document_share_api,
        document_signature_views, document_signature_api, document_version_views,
        document_version_api
    )

    blueprints = [
        auth_api, auth_views, estamp_bp, esignatures_bp, organizations_bp,
        subscription_bp, system_bp, users_bp, document_views, document_api,
        document_activity_views, document_activity_api, document_party_views,
        document_party_api, document_share_views, document_share_api,
        document_signature_views, document_signature_api, document_version_views,
        document_version_api
    ]

    # Authorized envelope preparation API; legacy signature writes remain blocked.
    from .blueprints.documents.api.envelope_api import envelope_api
    blueprints.append(envelope_api)
    from .blueprints.documents.api.signer_intent_api import signer_intent_api
    blueprints.append(signer_intent_api)
    from .blueprints.documents.api.review_receipt_api import receipt_api
    blueprints.append(receipt_api)
    from .blueprints.documents.api.sealed_pdf_api import sealed_pdf_api
    blueprints.append(sealed_pdf_api)
    from .blueprints.documents.api.signer_crypto_api import signer_crypto_api
    blueprints.append(signer_crypto_api)

    for bp in blueprints:
        app.register_blueprint(bp)
        # Use app.logger here instead of current_app.logger
        app.logger.info(f"Registered blueprint: {bp.name}")

    # --- Register CLI Commands ---
    register_cli(app)

    # --- Register Error Handlers ---
    register_error_handlers(app)

    # Final log after setup is complete, using app.logger and the determined log level name
    app.logger.info(f"Flask App '{app.name}' created with config '{config_name}'")
    app.logger.info(f"Logging level set to: {log_level_name}") # Use the determined name

    return app


# --- Error Handlers ---
def register_error_handlers(app):
    """Register custom error handlers for the application."""
    @app.errorhandler(404)
    def not_found_error(error):
        current_app.logger.warning(f"404 Not Found: {request.path} - {error}")
        return render_template("errors/404.html"), 404

    @app.errorhandler(500)
    def internal_error(error):
        db.session.rollback()
        current_app.logger.error(f"500 Internal Server Error: {error}", exc_info=True)
        return render_template("errors/500.html"), 500

    @app.errorhandler(401)
    def unauthorized_error(error):
        current_app.logger.warning(f"401 Unauthorized Error Handler: {request.path} - {error}")
        if request.path.startswith("/api/"):
            from flask import jsonify
            return jsonify(error="Authentication required"), 401
        flash("Authorization is required to access this page.", "warning")
        return redirect(url_for('auth_views.login'))

    @app.errorhandler(403)
    def forbidden_error(error):
        user_info = current_user.id if current_user.is_authenticated else 'Anonymous'
        current_app.logger.warning(f"403 Forbidden: User {user_info} attempted to access {request.path} - {error}")
        if request.path.startswith("/api/"):
            from flask import jsonify
            return jsonify(error="Forbidden"), 403
        return render_template("errors/403.html"), 403

# --- Utility ---
def get_config_name():
    return os.getenv('FLASK_CONFIG') or 'config.Config'