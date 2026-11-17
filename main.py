"""WSGI entry point.

Keep this file tiny — everything the app needs is wired up inside
:func:`app.create_app`. Importing ``app`` from here is what both the
Flask CLI (``FLASK_APP=main.py``) and WSGI servers (``gunicorn main:app``)
expect.
"""
from app import create_app

app = create_app()


if __name__ == "__main__":
    # Local developer convenience. Binds to loopback by default; use the
    # scripts/dev_server.sh wrapper for the browser-facing port.
    app.run(host="127.0.0.1", port=5017, debug=True)
