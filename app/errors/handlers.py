"""Safe server-error presentation: never disclose tracebacks to clients."""
from flask import current_app, jsonify, render_template, request
from app.extensions import db


def register_error_handlers(app):
    @app.errorhandler(500)
    def internal_server_error(error):
        db.session.rollback()
        # The traceback belongs in protected application logs, not responses.
        current_app.logger.exception("Unhandled server error on %s", request.path)
        if request.path.startswith("/api/"):
            response = jsonify(error="Internal server error")
            response.headers["Cache-Control"] = "no-store"
            return response, 500
        return render_template("errors/500.html", error_info=None), 500
