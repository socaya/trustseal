from functools import wraps
from flask import request, abort
import os

def system_only(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        system_token = os.getenv("SYSTEM_API_TOKEN")
        auth_header = request.headers.get("X-System-Token")

        if not system_token or not auth_header or auth_header != system_token:
            abort(403, description="Access forbidden: system access only")
        return f(*args, **kwargs)
    return decorated_function
