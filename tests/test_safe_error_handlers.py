"""Security regressions: API failures must not disclose exception details."""
from unittest.mock import patch
from flask import Flask

from app.errors.handlers import register_error_handlers


def test_internal_api_error_is_json_and_never_includes_traceback():
    app = Flask(__name__)
    app.config["TESTING"] = False
    register_error_handlers(app)

    @app.route("/api/private-failure")
    def fail():
        raise RuntimeError("SECRET_TOKEN_SHOULD_NOT_BE_EXPOSED")

    with patch("app.errors.handlers.db") as database:
        response = app.test_client().get("/api/private-failure")
        assert response.status_code == 500
        assert response.is_json
        assert response.get_json() == {"error": "Internal server error"}
        assert "SECRET_TOKEN_SHOULD_NOT_BE_EXPOSED" not in response.get_data(as_text=True)
        assert response.headers["Cache-Control"] == "no-store"
        database.session.rollback.assert_called_once()
