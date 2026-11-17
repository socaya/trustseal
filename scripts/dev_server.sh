#!/usr/bin/env bash
# Launch the TRUSTSEAL dev server for in-browser UI review.
#
# Binds to 127.0.0.1:5017 so it never clashes with the default
# Flask :5000 you might have running elsewhere. Picks up the
# repository's .env automatically via Flask's dotenv support.
#
# Usage:
#   scripts/dev_server.sh
#
# The script will:
#   1. Seed a demo tenant + admin user if missing.
#   2. Start `flask run` on port 5017 with debug on.
#   3. Print the browser URL + demo credentials.

set -euo pipefail

cd "$(dirname "$0")/.."

PY=".venv/bin/python"
FLASK=".venv/bin/flask"
PORT="${PORT:-5017}"

if [ ! -x "$PY" ]; then
  echo "error: .venv/bin/python not found. Create the venv first." >&2
  exit 1
fi

export FLASK_APP="${FLASK_APP:-main:app}"
export FLASK_DEBUG="${FLASK_DEBUG:-1}"
export FLASK_ENV="${FLASK_ENV:-development}"
# Keep the browser-facing frontend and the internal API client on the
# same origin — register / login views otherwise POST to :5000 and
# get a connection-refused (or 403 from a stale backend).
export API_BASE_URL="http://127.0.0.1:${PORT}/api"

echo "[dev-server] Seeding demo tenant + admin user (idempotent)…"
"$PY" scripts/seed_dev.py

echo
echo "[dev-server] Starting Flask on http://127.0.0.1:${PORT}"
echo "[dev-server]   Sign in:   http://127.0.0.1:${PORT}/auth/login"
echo "[dev-server]   Landing:   http://127.0.0.1:${PORT}/welcome"
echo "[dev-server]   Verify:    http://127.0.0.1:${PORT}/verify"
echo "[dev-server]   Pricing:   http://127.0.0.1:${PORT}/pricing"
echo "[dev-server]   Trust:     http://127.0.0.1:${PORT}/trust"
echo "[dev-server]   Overview:  http://127.0.0.1:${PORT}/  (after sign-in)"
echo "[dev-server]   Profile:   http://127.0.0.1:${PORT}/app/profile"
echo "[dev-server]   Design:    http://127.0.0.1:${PORT}/design/gallery  (admin only)"
echo

exec "$FLASK" run --host 127.0.0.1 --port "$PORT"
