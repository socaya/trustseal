"""TSD viewer presence (lightweight polling — NOT real-time CRDT).

Each editor pings ``POST /api/tsd/<id>/presence`` every 15 seconds.
A viewer is considered active when ``last_ping_at`` is within the last
45 seconds. Production real-time multi-cursor editing requires a
WebSocket + CRDT stack (Y.js / Automerge) that is not in this
repository; this table is the awareness channel that will remain
useful even after a full co-editing engine lands.
"""
from datetime import datetime

from app.extensions import db


class TSDPresence(db.Model):
    __tablename__ = "ts_document_presence"

    tsd_id = db.Column(
        db.Integer, db.ForeignKey("ts_documents.id"),
        primary_key=True,
    )
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id"),
        primary_key=True,
    )
    last_ping_at = db.Column(
        db.DateTime, nullable=False, default=datetime.utcnow,
        onupdate=datetime.utcnow, index=True,
    )
