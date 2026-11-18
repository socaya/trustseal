"""Real-time TSD awareness channel via Flask-SocketIO.

Scope of this module
--------------------

This ships the **awareness layer** that a Y.js / Automerge CRDT engine
will later reuse — live presence, cursors and selections broadcast
over a WebSocket, under a per-document room. It does **not** ship
conflict-free co-editing of the document content itself; text changes
still travel through the existing HTTP autosave (PUT /api/tsd/<id>)
with ``If-Match`` concurrency guards.

The step from "awareness only" to "full co-editing" is to plug the
same socket channel into a `y-websocket` server or embed `y-redis`
as the backing store. See ``docs/TSD_Real_Time_Collab_Plan.md``.

Protocol (namespace ``/tsd``)
-----------------------------

Client → server:

* ``join``        — ``{tsd_id}``. Joins the room after an auth check.
* ``cursor``      — ``{tsd_id, position, selection, color}``. Broadcast
                    to the room (except sender).
* ``typing``      — ``{tsd_id}``. Broadcast a transient typing indicator.
* ``leave``       — ``{tsd_id}``. Leaves the room explicitly.

Server → client (broadcast within the room):

* ``peer_joined`` — ``{user_id, name, email, initials, color, sid}``
* ``peer_left``   — ``{user_id, sid}``
* ``peer_cursor`` — ``{user_id, sid, position, selection, color}``
* ``peer_typing`` — ``{user_id, sid}``

Authorization
-------------

Each socket inherits the HTTP session via ``flask_login.current_user``.
On every ``join`` we re-check that the caller can access the document
through the same ``_owned`` logic as the HTTP layer. A session that
loses access during a long-lived connection will be denied at the
next ``join`` but not forcibly disconnected — that would require a
separate server-side invalidation loop and is out of scope here.
"""
from __future__ import annotations

import hashlib
import logging
from typing import Any

from flask import request
from flask_login import current_user
from flask_socketio import SocketIO, disconnect, emit, join_room, leave_room

from app.extensions import db


log = logging.getLogger(__name__)
socketio = SocketIO(
    async_mode="threading",
    cors_allowed_origins="*",       # same-origin served by Flask; CORS is irrelevant
    logger=False,
    engineio_logger=False,
)


# ---- helpers -----------------------------------------------------------


def _room(tsd_id: int) -> str:
    return f"tsd:{int(tsd_id)}"


def _color_for(user_id: int) -> str:
    """Stable, legible colour per user id (HSL slice at good saturation)."""
    h = int(hashlib.sha256(str(user_id).encode()).hexdigest(), 16) % 360
    return f"hsl({h}, 65%, 42%)"


def _initials(user) -> str:
    base = (user.first_name or user.username or "?")[:1] + (user.last_name or "")[:1]
    return base.upper()


def _user_payload(user) -> dict:
    return {
        "user_id": user.id,
        "name": ((user.first_name or "") + " " + (user.last_name or "")).strip() or user.username,
        "email": user.email,
        "initials": _initials(user),
        "color": _color_for(user.id),
    }


def _can_access(user, tsd_id: int) -> bool:
    """Replicate the HTTP ``_owned`` check in the socket context."""
    from datetime import datetime
    from app.models.tsd_document import TSDocument
    from app.models.tsd_share import TSDShare

    row = (
        TSDocument.query
        .filter(
            TSDocument.id == tsd_id,
            TSDocument.organization_id == user.organization_id,
            TSDocument.deleted_at.is_(None),
        )
        .first()
    )
    if row is not None:
        return True
    row = (
        TSDocument.query
        .join(TSDShare, TSDShare.tsd_id == TSDocument.id)
        .filter(
            TSDocument.id == tsd_id,
            TSDocument.deleted_at.is_(None),
            TSDShare.grantee_user_id == user.id,
            TSDShare.revoked_at.is_(None),
            db.or_(TSDShare.expires_at.is_(None),
                   TSDShare.expires_at > datetime.utcnow()),
        )
        .first()
    )
    return row is not None


# ---- socket handlers --------------------------------------------------


def register_handlers(sio: SocketIO) -> None:
    """Register the /tsd namespace handlers on the given SocketIO instance."""

    @sio.on("connect", namespace="/tsd")
    def _connect():
        if not getattr(current_user, "is_authenticated", False):
            # Reject anonymous connections.
            return False
        emit("hello", _user_payload(current_user))
        return None

    @sio.on("join", namespace="/tsd")
    def _join(data: dict[str, Any]):
        try:
            tsd_id = int(data.get("tsd_id"))
        except (TypeError, ValueError):
            emit("error", {"error": "invalid_tsd_id"})
            return
        if not _can_access(current_user, tsd_id):
            emit("error", {"error": "access_denied"})
            return
        room = _room(tsd_id)
        join_room(room)
        payload = {**_user_payload(current_user), "sid": request.sid}
        emit("peer_joined", payload, room=room, include_self=False)
        # Tell the newcomer who's already here (best-effort — we broadcast
        # a "whois" event that existing peers answer with their identity).
        emit("whois", {"asker_sid": request.sid}, room=room, include_self=False)

    @sio.on("whoami", namespace="/tsd")
    def _whoami(data: dict[str, Any]):
        asker_sid = data.get("asker_sid")
        if not asker_sid:
            return
        try:
            tsd_id = int(data.get("tsd_id"))
        except (TypeError, ValueError):
            return
        payload = {**_user_payload(current_user), "sid": request.sid,
                   "tsd_id": tsd_id}
        emit("peer_joined", payload, to=asker_sid)

    @sio.on("leave", namespace="/tsd")
    def _leave(data: dict[str, Any]):
        try:
            tsd_id = int(data.get("tsd_id"))
        except (TypeError, ValueError):
            return
        room = _room(tsd_id)
        leave_room(room)
        emit("peer_left", {"user_id": current_user.id, "sid": request.sid},
             room=room, include_self=False)

    @sio.on("disconnect", namespace="/tsd")
    def _disconnect():
        # The library auto-leaves rooms on disconnect; broadcast a
        # best-effort departure so UIs can drop the cursor overlay
        # without waiting for the per-doc join list to refresh.
        try:
            user_id = current_user.id
        except Exception:
            return
        emit("peer_left", {"user_id": user_id, "sid": request.sid}, broadcast=True)

    @sio.on("cursor", namespace="/tsd")
    def _cursor(data: dict[str, Any]):
        try:
            tsd_id = int(data.get("tsd_id"))
        except (TypeError, ValueError):
            return
        if not _can_access(current_user, tsd_id):
            return
        emit("peer_cursor", {
            "user_id": current_user.id,
            "sid": request.sid,
            "color": _color_for(current_user.id),
            "name": (current_user.first_name or current_user.username or "?"),
            "position": data.get("position"),
            "selection": data.get("selection"),
        }, room=_room(tsd_id), include_self=False)

    @sio.on("typing", namespace="/tsd")
    def _typing(data: dict[str, Any]):
        try:
            tsd_id = int(data.get("tsd_id"))
        except (TypeError, ValueError):
            return
        emit("peer_typing", {
            "user_id": current_user.id,
            "sid": request.sid,
        }, room=_room(tsd_id), include_self=False)


def init_app(app) -> SocketIO:
    """Attach the namespace to the app; wire handlers once per process."""
    socketio.init_app(app)
    register_handlers(socketio)
    return socketio
