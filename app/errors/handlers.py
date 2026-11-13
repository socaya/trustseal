from flask import render_template, request
from app.extensions import db
import traceback

def register_error_handlers(app):
    @app.errorhandler(500)
    def internal_server_error(e):
        db.session.rollback()
        error_info = traceback.format_exc()
        return render_template("errors/500.html", error_info=error_info), 500