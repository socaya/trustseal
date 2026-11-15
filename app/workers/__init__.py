"""Long-running background worker processes.

Workers run as ordinary Python processes started via Flask CLI commands.
No container runtime is required. A typical production deployment runs
``flask worker outbox`` under systemd / supervisor / launchd with
automatic restart.

See ``app/workers/outbox_worker.py`` for the first worker and
``app/cli/outbox.py`` for its registration.
"""
