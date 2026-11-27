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


    # --- Structured logging, request IDs, and redaction ---
    from .observability import configure_observability
    configure_observability(app)

    # --- Prometheus metrics ---
    from .metrics import configure_metrics
    configure_metrics(app)

    # --- Audit chain integrity hook ---
    from .services.audit_chain import register_chain_hook
    register_chain_hook(app)

    # --- OpenTelemetry tracing (opt-in via OTEL_ENABLED) ---
    from .tracing import configure_tracing
    configure_tracing(app)

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

    @app.context_processor
    def inject_design_system_helpers():
        """Expose a cheap set-lookup of registered endpoints and the
        current moment to every template so the design-system sidebar
        can hide dead links (TS-UI-008) and layouts can print the year
        without reaching into global state.
        """
        from flask_login import current_user
        from .policies.api_access import get_user_nav_roles
        nav_roles = get_user_nav_roles(current_user)
        return {
            "url_map_endpoints": {rule.endpoint for rule in app.url_map.iter_rules()},
            "now": datetime.utcnow(),
            "density": "default",
            "unread_notifications": False,
            **nav_roles,
        }

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
        # SCIM 2.0 endpoints use their own bearer-token authentication;
        # do not redirect anonymous callers to the HTML login view.
        if request.path.startswith("/scim/"):
            return

        # --- Allow Static Files ---
        if request.endpoint == 'static':
            return

        # --- Define Public View Endpoints (HTML Pages) ---
        public_endpoints = [
            'auth_views.login',
            'auth_views.register',
            'verify_views.verify_form',
            'verify_views.verify_pdf',
            'sign_views.landing',
            'sign_views.decision',
            'sign_views.download',
            'sign_views.upload_attachment',
            'sign_views.status',
            'send_studio_views.sign_package_page',
            'send_studio_views.share_link_kiosk',
            'send_studio_views.completion_certificate_page',
            # External TSD share magic-link landing — anonymous by
            # design, authorized by the one-shot token in the URL.
            'tsd_external_views.landing',
            # Public stamp verification — anyone with a receipt id + nonce
            # can validate a stamp impression without logging in.
            'stamp_verify_public.verify_public',
            'stamp_verify_public.qr_svg',
            # Public landing + root hit are explicitly anonymous.
            # The endpoint is nested under the parent 'system' blueprint.
            'system.main_views.home',
            'system.main_views.welcome',
            'system.main_views.platform',
            'system.main_views.platform_module',
            'system.main_views.how_it_works',
            'system.main_views.trust',
            'system.main_views.pricing',
            'design_gallery_bp.gallery',
            # SAML SP endpoints are the entry point for SSO — the IdP
            # posts the response here before the user has a session.
            'saml_views.metadata',
            'saml_views.login',
            'saml_views.acs',
            # Liveness / readiness probes for k8s + load balancers.
            'health_bp.health',
            'health_bp.ready',
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


    @app.before_request
    def _bind_request_id():
        """Honour an incoming X-Request-Id or mint a fresh one.

        Stored on ``g.request_id`` so downstream code (audit chain,
        security events, structured logs) can correlate work for a
        single request. Trimmed to a defensive max-length to prevent
        header-smuggling / log-flooding.
        """
        from flask import g
        import uuid as _uuid

        incoming = request.headers.get("X-Request-Id", "").strip()
        if incoming and len(incoming) <= 128 and all(
            ch.isalnum() or ch in "-_" for ch in incoming
        ):
            g.request_id = incoming
        else:
            g.request_id = _uuid.uuid4().hex


    @app.after_request
    def after_request_handler(response):
        """Runs after each request, before sending the response."""
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'

        # S2 — surface the request/trace correlation so clients and
        # proxies can line up API responses with server-side logs.
        from flask import g

        request_id = getattr(g, "request_id", None)
        if request_id:
            response.headers["X-Request-Id"] = request_id

        trace_id = None
        try:
            from opentelemetry import trace as _otel

            span = _otel.get_current_span()
            ctx = span.get_span_context() if span is not None else None
            if ctx is not None and getattr(ctx, "trace_id", 0):
                trace_id = format(ctx.trace_id, "032x")
        except Exception:
            trace_id = None
        response.headers["X-Trace-Id"] = trace_id or request_id or ""
        return response

    # --- PostgreSQL row-level security tenant propagation ---
    # Registered AFTER the login_manager + app before_request chain so
    # Flask-Login has already resolved current_user by the time this
    # hook runs. RLS is defence-in-depth behind the application-layer
    # TenantScopedRepository.
    from .services.tenant_rls import register_rls_hook
    register_rls_hook(app)

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

    # Document-draft API (autosave with optimistic concurrency, Phase H2).
    from .blueprints.documents.api.document_draft_api import document_draft_api
    blueprints.append(document_draft_api)
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
    from .blueprints.documents.api.public_pdf_verify_api import public_pdf_verify_api
    blueprints.append(public_pdf_verify_api)
    from .blueprints.estamp.stamp_custody_api import stamp_custody_api
    from .blueprints.estamp.stamp_attestation_api import stamp_attestation_api
    blueprints.extend([stamp_custody_api, stamp_attestation_api])
    from .blueprints.estamp.stamped_pdf_api import stamped_pdf_api
    blueprints.append(stamped_pdf_api)
    from .blueprints.estamp.stamp_design_api import stamp_design_api
    blueprints.append(stamp_design_api)
    from .blueprints.documents.api.evidence_preservation_api import evidence_preservation_api
    blueprints.append(evidence_preservation_api)
    from .blueprints.integrations.webhook_api import webhook_api
    blueprints.append(webhook_api)
    from .blueprints.auth.routes.mfa_api import mfa_api
    blueprints.append(mfa_api)
    from .blueprints.organizations.routes.teams_api import teams_api
    blueprints.append(teams_api)
    from .blueprints.organizations.routes.delegations_api import delegations_api
    blueprints.append(delegations_api)
    from .blueprints.documents.api.templates_api import templates_api
    blueprints.append(templates_api)
    from .blueprints.documents.api.clauses_api import clauses_api
    blueprints.append(clauses_api)
    from .blueprints.subscriptions.routes.usage_api import usage_api
    blueprints.append(usage_api)
    from .blueprints.auth.routes.saml_views import saml_views
    blueprints.append(saml_views)
    from .blueprints.system.routes.slo_api import slo_api
    blueprints.append(slo_api)
    from .blueprints.organizations.routes.tenant_export_api import tenant_export_api
    blueprints.append(tenant_export_api)
    from .blueprints.organizations.routes.tenant_erasure_api import tenant_erasure_api
    blueprints.append(tenant_erasure_api)
    from .blueprints.system.routes.break_glass_api import break_glass_api
    blueprints.append(break_glass_api)
    from .blueprints.integrations.scim_admin_api import scim_admin_api
    blueprints.append(scim_admin_api)
    from .blueprints.auth.routes.sso_logout import sso_logout_api
    blueprints.append(sso_logout_api)
    from .blueprints.system.routes.audit_chain_export_api import audit_chain_export_api
    blueprints.append(audit_chain_export_api)
    from .blueprints.system.routes.health import health_bp
    blueprints.append(health_bp)
    from .blueprints.system.routes.outbox_admin import outbox_admin_api
    blueprints.append(outbox_admin_api)
    from .blueprints.system.routes.admin_dashboard import admin_dashboard_api
    blueprints.append(admin_dashboard_api)
    from .blueprints.documents.api.envelope_template_api import (
        envelope_template_api,
    )
    blueprints.append(envelope_template_api)
    from .blueprints.system.routes.security_events_export import (
        security_events_export_api,
    )
    blueprints.append(security_events_export_api)
    from .blueprints.system.routes.usage_export import usage_export_api
    blueprints.append(usage_export_api)
    from .blueprints.system.routes.operator_notifications import (
        operator_notifications_api,
    )
    blueprints.append(operator_notifications_api)
    from .blueprints.system.routes.design_gallery import design_gallery_bp
    blueprints.append(design_gallery_bp)
    from .blueprints.system.routes.operator_notifications_view import (
        operator_notifications_views,
    )
    blueprints.append(operator_notifications_views)
    from .blueprints.auth.routes.profile_views import profile_views
    blueprints.append(profile_views)
    from .blueprints.system.routes.admin_users_view import admin_users_views
    blueprints.append(admin_users_views)
    from .blueprints.system.routes.audit_security_view import audit_security_views
    blueprints.append(audit_security_views)
    from .blueprints.system.routes.integrations_view import integrations_views
    blueprints.append(integrations_views)
    from .blueprints.system.routes.billing_view import billing_views
    blueprints.append(billing_views)
    from .blueprints.documents.api.tsd_api import tsd_api
    blueprints.append(tsd_api)
    from .blueprints.documents.views.tsd_views import tsd_views
    blueprints.append(tsd_views)
    from .blueprints.documents.views.tsd_external_views import tsd_external_views
    blueprints.append(tsd_external_views)
    from .blueprints.estamp.tsd_stamps_api import tsd_stamps_api
    blueprints.append(tsd_stamps_api)
    from .blueprints.estamp.tsd_stamps_views import tsd_stamps_views
    blueprints.append(tsd_stamps_views)
    from .blueprints.estamp.stamp_verify_public import stamp_verify_public
    blueprints.append(stamp_verify_public)
    from .blueprints.estamp.media_letterheads_api import (
        media_library_api,
        letterheads_api,
    )
    blueprints.append(media_library_api)
    blueprints.append(letterheads_api)
    from .blueprints.estamp.media_letterheads_views import workspace_assets_views
    blueprints.append(workspace_assets_views)

    from .blueprints.contracts import (
        contract_templates_api,
        contracts_api,
        contracts_views,
        projects_api,
    )
    blueprints.extend([contracts_api, projects_api, contract_templates_api, contracts_views])
    from .blueprints.projects import (
        portfolios_api,
        programmes_api,
        project_intakes_api,
        project_portal_api,
        project_templates_api,
        project_timesheets_v21_api,
        projects_batch2_api,
        projects_batch3_api,
        projects_v2_api,
        resources_api,
        timesheets_v21_api,
    )
    blueprints.extend([
        portfolios_api, programmes_api, project_intakes_api, projects_v2_api,
        resources_api, projects_batch2_api, project_templates_api, project_portal_api,
        projects_batch3_api, timesheets_v21_api, project_timesheets_v21_api,
    ])
    from .blueprints.documents.api.document_label_api import (
        document_label_api,
    )
    blueprints.append(document_label_api)
    from .blueprints.documents.api.signer_attachment_api import (
        signer_attachment_api,
    )
    blueprints.append(signer_attachment_api)
    from .blueprints.integrations.scim_api import scim_api
    blueprints.append(scim_api)
    from .blueprints.integrations.openapi_api import openapi_api
    blueprints.append(openapi_api)
    from .blueprints.trust.views.verify_views import verify_views
    blueprints.append(verify_views)
    from .blueprints.trust.views.evidence_views import evidence_views
    blueprints.append(evidence_views)
    from .blueprints.envelopes.views.sign_views import sign_views
    blueprints.append(sign_views)
    from .blueprints.esignatures.eidas_api import eidas_api, send_esign_api
    from .blueprints.esignatures.send_studio_views import send_studio_views
    blueprints.extend([eidas_api, send_esign_api, send_studio_views])
    from .blueprints.estamp.brand_studio_api import brand_studio_api
    from .blueprints.estamp.brand_studio_views import brand_studio_views
    blueprints.extend([brand_studio_api, brand_studio_views])

    for bp in blueprints:
        app.register_blueprint(bp)
        # Use app.logger here instead of current_app.logger
        app.logger.info(f"Registered blueprint: {bp.name}")

    # --- Register CLI Commands ---
    register_cli(app)
    from .cli.mfa_rewrap import register_cli as _register_mfa_cli
    _register_mfa_cli(app)
    from .cli.envelope_ops import register_cli as _register_envelope_cli
    _register_envelope_cli(app)
    from .cli.reminders import register_cli as _register_reminders_cli
    _register_reminders_cli(app)
    from .cli.tsd_rewrap import register_cli as _register_tsd_cli
    _register_tsd_cli(app)

    # --- Register Error Handlers (RFC 7807 for /api/, Jinja for views) ---
    from .errors.problem import register_problem_handlers
    register_problem_handlers(app)

    # Real-time collab awareness channel (WebSocket /tsd namespace).
    # Dev: Werkzeug + threading. Prod: gunicorn with -k gevent/eventlet.
    from .services.tsd_realtime import init_app as _init_realtime
    _init_realtime(app)

    app.logger.info(
        "application_started",
        extra={"config": config_name, "env": app.config.get("FLASK_ENV")},
    )
    return app


# --- Utility ---
def get_config_name():
    return os.getenv('FLASK_CONFIG') or 'config.Config'