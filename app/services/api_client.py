import os
import json
import logging
import requests
from flask import current_app, session, flash, has_request_context

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


# --------------------------------------------
# 🔧 Helpers
# --------------------------------------------

def get_base_url():
    return current_app.config.get("API_BASE_URL", os.getenv("API_BASE_URL", "http://127.0.0.1:5000/api"))

def build_url(endpoint):
    return f"{get_base_url().rstrip('/')}/{endpoint.lstrip('/')}"

def prepare_headers(token=None):
    headers = {"Content-Type": "application/json"}
    token = token or session.get("access_token")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers

def _flash(msg, category="danger"):
    if has_request_context():
        flashed = set(session.get("_flashed_messages", []))
        if msg not in flashed:
            flash(msg, category)
            flashed.add(msg)
            session["_flashed_messages"] = list(flashed)
    else:
        logger.warning(f"(no request) FLASH [{category}]: {msg}")

def _log_response(response):
    try:
        logger.debug(f"[{response.status_code}] Response: {json.dumps(response.json(), indent=2)}")
    except Exception:
        logger.debug(f"[{response.status_code}] Response (non-JSON): {response.text[:300]}")

def _handle_error_response(e, method=""):
    try:
        content = e.response.json()
        msg = content.get("message") or content.get("error") or str(e)
        logger.warning(f"❌ {method} ERROR: {msg}")
        return {"error": msg, "status_code": e.response.status_code}
    except Exception:
        logger.exception(f"❌ {method} UNCAUGHT ERROR")
        return {"error": str(e), "status_code": 500}


# --------------------------------------------
# 🔄 Token Refresh + Retry Logic
# --------------------------------------------

def handle_token_refresh():
    refresh_token = session.get("refresh_token")
    if not refresh_token:
        logger.warning("🔒 No refresh token.")
        return False

    url = build_url("auth/refresh")
    headers = {"Authorization": f"Bearer {refresh_token}"}

    try:
        response = requests.post(url, headers=headers)
        if response.status_code == 200:
            new_token = response.json().get("access_token")
            if new_token:
                session["access_token"] = new_token
                logger.info("🔄 Token refreshed.")
                return True
        logger.warning(f"🔄 Refresh failed ({response.status_code})")
        return False
    except Exception as e:
        logger.error(f"🔄 Refresh error: {e}")
        return False

def _retry_request(func, *args, **kwargs):
    result = func(*args, **kwargs)
    if isinstance(result, dict) and result.get("status_code") in [401, 422]:
        if kwargs.get("token") or session.get("access_token"):
            logger.warning("🔐 Expired token. Attempting refresh...")
            if handle_token_refresh():
                kwargs["token"] = session.get("access_token")
                return func(*args, **kwargs)
            else:
                session.clear()
                _flash("Session expired. Please log in again.", "warning")
                return {"error": "Session expired", "status_code": 401}
    return result


# --------------------------------------------
# 🌐 CRUD Operations
# --------------------------------------------

def get_data(endpoint, params=None, token=None):
    def _request(endpoint=endpoint, params=params, token=token):
        url = build_url(endpoint)
        try:
            r = requests.get(url, headers=prepare_headers(token), params=params)
            r.raise_for_status()

            if "application/json" not in r.headers.get("Content-Type", ""):
                logger.warning(f"❌ Invalid Content-Type: {r.headers.get('Content-Type')} - {r.status_code} - {r.text[:200]}")
                return {"error": "Non-JSON response", "status_code": r.status_code, "text": r.text}

            _log_response(r)
            return r.json()

        except requests.exceptions.HTTPError as e:
            _log_response(e.response)
            return _handle_error_response(e, "GET")
        except Exception as e:
            logger.exception("GET Error")
            return {"error": "API connection error", "status_code": None}

    return _retry_request(_request)


def post_data(endpoint, data=None, token=None):
    def _request(endpoint=endpoint, data=data, token=token):
        url = build_url(endpoint)
        try:
            r = requests.post(url, headers=prepare_headers(token), json=data or {})
            r.raise_for_status()

            if "application/json" not in r.headers.get("Content-Type", ""):
                logger.warning(f"❌ Invalid Content-Type: {r.headers.get('Content-Type')} - {r.status_code} - {r.text[:200]}")
                return {"error": "Non-JSON response", "status_code": r.status_code, "text": r.text}

            _log_response(r)
            return r.json()

        except requests.exceptions.HTTPError as e:
            _log_response(e.response)
            return _handle_error_response(e, "POST")
        except Exception as e:
            logger.exception("POST Error")
            return {"error": "API connection error", "status_code": None}

    result = _retry_request(_request)
    if isinstance(result, dict) and result.get("status_code") == 401 and result.get("error") == "Session expired":
        _flash(result["error"], "warning")
    return result


def put_data(endpoint, data=None, token=None):
    def _request(endpoint=endpoint, data=data, token=token):
        url = build_url(endpoint)
        try:
            r = requests.put(url, headers=prepare_headers(token), json=data or {})
            r.raise_for_status()

            if "application/json" not in r.headers.get("Content-Type", ""):
                logger.warning(f"❌ Invalid Content-Type: {r.headers.get('Content-Type')} - {r.status_code} - {r.text[:200]}")
                return {"error": "Non-JSON response", "status_code": r.status_code, "text": r.text}

            _log_response(r)
            return r.json()

        except requests.exceptions.HTTPError as e:
            _log_response(e.response)
            return _handle_error_response(e, "PUT")
        except Exception as e:
            logger.exception("PUT Error")
            return {"error": "API connection error", "status_code": None}

    return _retry_request(_request)


def delete_data(endpoint, token=None):
    def _request(endpoint=endpoint, token=token):
        url = build_url(endpoint)
        try:
            r = requests.delete(url, headers=prepare_headers(token))
            r.raise_for_status()
            _log_response(r)
            return {"success": True}

        except requests.exceptions.HTTPError as e:
            _log_response(e.response)
            return _handle_error_response(e, "DELETE")
        except Exception as e:
            logger.exception("DELETE Error")
            return {"error": "API connection error", "status_code": None}

    return _retry_request(_request)