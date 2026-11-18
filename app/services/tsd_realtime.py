"""Real-time TSD awareness + CRDT text co-editing via Flask-SocketIO.

This module ships two coupled things:

1. **Awareness layer** — live presence, cursors, selections and
   typing indicators broadcast over a WebSocket, under per-document
   rooms.
2. **CRDT co-editing** — Y.js updates relayed over the same socket,
   with a server-side :class:`pycrdt.Doc` per document that applies
   every update, serves initial state to late joiners, and
   periodically snapshots the merged plaintext back to the encrypted
   TSD so disconnect-reconnect never loses edits.

CRDT protocol events (namespace ``/tsd``)
-----------------------------------------

Client → server:

* ``y-sync-request``  — ``{tsd_id}``. New joiner asks the server for
                        the current accumulated Y.js state.
* ``y-update``        — ``{tsd_id, update: bytes}``. Local Y.Doc
                        update to merge + broadcast.

Server → client:

* ``y-sync-reply``    — ``{tsd_id, state: bytes}``. Full Y.Doc
                        encoded state the joiner applies to bootstrap.
* ``y-update``        — ``{tsd_id, update: bytes, from_sid: str}``.
                        Updates from other peers in the room,
                        broadcast after the server has merged them
                        into its authoritative Doc.

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

from datetime import datetime
from threading import Lock

from flask import current_app, request
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


# ---- CRDT document state ----------------------------------------------

# One :class:`pycrdt.Doc` is kept in memory per active tsd_id for as long
# as there's at least one connected editor. Updates are applied here and
# the encoded state is handed out to late joiners. On every N ms of
# inactivity the merged plaintext is snapshotted back to the encrypted
# TSD via the existing autosave path.

_DOC_CACHE: dict[int, "CrdtSession"] = {}
_CACHE_LOCK = Lock()

# Minimum interval between snapshot writes per document, in seconds.
# Keeps the write amplification sensible under rapid co-editing.
SNAPSHOT_DEBOUNCE_SECONDS = 4


class CrdtSession:
    """In-memory Y.Doc + metadata for a single active TSD."""

    __slots__ = ("tsd_id", "ydoc", "ytext", "ref_count", "dirty",
                 "last_snapshot_at", "last_update_at")

    def __init__(self, tsd_id: int):
        from pycrdt import Doc, Text
        self.tsd_id = tsd_id
        self.ydoc = Doc()
        self.ytext: Text = self.ydoc.get("content", type=Text)
        self.ref_count = 0
        self.dirty = False
        self.last_snapshot_at = datetime.utcnow()
        self.last_update_at = datetime.utcnow()

    def bootstrap_from_tsd(self, tsd_html: str) -> None:
        """Initialise the empty Y.Doc with the current TSD HTML."""
        if tsd_html and len(str(self.ytext)) == 0:
            self.ytext += tsd_html

    def apply_update(self, update: bytes) -> None:
        self.ydoc.apply_update(update)
        self.dirty = True
        self.last_update_at = datetime.utcnow()

    def encode_state(self) -> bytes:
        return self.ydoc.get_update()

    def current_html(self) -> str:
        return str(self.ytext)


def _get_or_create_session(tsd_id: int) -> CrdtSession:
    from app.models.tsd_document import TSDocument
    from app.services.tsd_format import decrypt_content_envelope

    with _CACHE_LOCK:
        sess = _DOC_CACHE.get(tsd_id)
        if sess is None:
            sess = CrdtSession(tsd_id)
            _DOC_CACHE[tsd_id] = sess
            # Bootstrap from the stored TSD so late joiners don't start
            # from an empty doc.
            doc = TSDocument.query.get(tsd_id)
            if doc is not None:
                try:
                    content = decrypt_content_envelope(
                        doc.ciphertext, organization_id=doc.organization_id
                    )
                    sess.bootstrap_from_tsd(content.get("html") or "")
                except Exception as exc:
                    log.warning("bootstrap_from_tsd failed for %s: %s", tsd_id, exc)
        sess.ref_count += 1
        return sess


def _release_session(tsd_id: int) -> None:
    """Drop the in-memory Doc when the last peer leaves (after snapshot)."""
    with _CACHE_LOCK:
        sess = _DOC_CACHE.get(tsd_id)
        if sess is None:
            return
        sess.ref_count = max(0, sess.ref_count - 1)
        if sess.ref_count == 0:
            _snapshot_session(sess, force=True)
            _DOC_CACHE.pop(tsd_id, None)


def _snapshot_session(sess: CrdtSession, *, force: bool = False) -> bool:
    """Write the merged CRDT plaintext back to the encrypted TSD.

    Respects :data:`SNAPSHOT_DEBOUNCE_SECONDS` unless ``force`` is set.
    Uses the existing format sanitize + encrypt + version-snapshot path
    so Y.js co-editing lands in the same audit trail as HTTP autosave.
    """
    from app.models.tsd_document import TSDocument
    from app.models.tsd_document_version import TSDocumentVersion
    from app.services.tsd_format import (
        encrypt_content_envelope, pack_content, sanitize_html, sha256_hex,
    )

    if not sess.dirty:
        return False
    now = datetime.utcnow()
    if not force and (now - sess.last_snapshot_at).total_seconds() < SNAPSHOT_DEBOUNCE_SECONDS:
        return False

    doc = TSDocument.query.get(sess.tsd_id)
    if doc is None or doc.deleted_at is not None:
        return False

    html = sanitize_html(sess.current_html() or "")
    plaintext = pack_content(html=html, description=doc.description,
                             tags=[t for t in (doc.tags or "").split(",") if t.strip()])
    ciphertext = encrypt_content_envelope(plaintext, organization_id=doc.organization_id)

    # Mirror the HTTP update path: snapshot the previous version first.
    db.session.add(TSDocumentVersion(
        tsd_id=doc.id,
        version=doc.version,
        ciphertext=doc.ciphertext,
        ciphertext_sha256=doc.ciphertext_sha256,
        plaintext_bytes=doc.plaintext_bytes,
        created_by_id=doc.created_by_id,
        change_note="crdt co-editing snapshot",
    ))
    doc.ciphertext = ciphertext
    doc.ciphertext_sha256 = sha256_hex(ciphertext)
    doc.plaintext_bytes = len(plaintext)
    doc.version += 1
    doc.updated_at = now
    db.session.commit()

    sess.dirty = False
    sess.last_snapshot_at = now
    return True


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
        # Track the session for CRDT lifecycle (release on disconnect/leave).
        from flask import session as _fs
        tracked = _fs.setdefault("_tsd_rooms", [])
        if tsd_id not in tracked:
            tracked.append(tsd_id)
            _fs.modified = True
        _get_or_create_session(tsd_id)

        payload = {**_user_payload(current_user), "sid": request.sid}
        emit("peer_joined", payload, room=room, include_self=False)
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
        _release_session(tsd_id)
        from flask import session as _fs
        tracked = _fs.get("_tsd_rooms") or []
        if tsd_id in tracked:
            tracked.remove(tsd_id)
            _fs["_tsd_rooms"] = tracked
            _fs.modified = True
        emit("peer_left", {"user_id": current_user.id, "sid": request.sid},
             room=room, include_self=False)

    @sio.on("disconnect", namespace="/tsd")
    def _disconnect():
        # Release every room we joined on this socket; last-one-out
        # snapshots the Y.Doc back to the encrypted TSD.
        try:
            from flask import session as _fs
            for tsd_id in list(_fs.get("_tsd_rooms") or []):
                _release_session(tsd_id)
            _fs.pop("_tsd_rooms", None)
        except Exception:
            pass
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

    # ---- CRDT co-editing handlers --------------------------------------

    @sio.on("y-sync-request", namespace="/tsd")
    def _y_sync_request(data: dict[str, Any]):
        try:
            tsd_id = int(data.get("tsd_id"))
        except (TypeError, ValueError):
            return
        if not _can_access(current_user, tsd_id):
            emit("error", {"error": "access_denied"})
            return
        sess = _get_or_create_session(tsd_id)
        state = sess.encode_state()
        emit("y-sync-reply", {
            "tsd_id": tsd_id,
            "state": bytes(state),  # socket.io sends as binary attachment
        })

    @sio.on("y-update", namespace="/tsd")
    def _y_update(data: dict[str, Any]):
        try:
            tsd_id = int(data.get("tsd_id"))
        except (TypeError, ValueError):
            return
        if not _can_access(current_user, tsd_id):
            return
        update = data.get("update")
        if not update:
            return
        # Normalise to bytes — Socket.IO can hand us a bytearray or bytes.
        if isinstance(update, (bytearray, memoryview)):
            update = bytes(update)
        if not isinstance(update, (bytes,)):
            return
        sess = _DOC_CACHE.get(tsd_id)
        if sess is None:
            # Late message after our in-memory session was cleared;
            # bootstrap one so we still merge + broadcast.
            sess = _get_or_create_session(tsd_id)
        try:
            sess.apply_update(update)
        except Exception as exc:
            log.warning("y-update apply failed for %s: %s", tsd_id, exc)
            return

        emit("y-update", {
            "tsd_id": tsd_id,
            "update": update,
            "from_sid": request.sid,
            "from_user_id": current_user.id,
        }, room=_room(tsd_id), include_self=False)

        # Opportunistic snapshot — honours the debounce window.
        try:
            _snapshot_session(sess)
        except Exception as exc:
            log.warning("snapshot_session failed for %s: %s", tsd_id, exc)
            db.session.rollback()


def init_app(app) -> SocketIO:
    """Attach the namespace to the app; wire handlers once per process."""
    socketio.init_app(app)
    register_handlers(socketio)
    return socketio
