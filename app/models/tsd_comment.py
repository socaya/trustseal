"""TSD inline comment threads (DOC-071–DOC-075).

Comments are anchored to a text span the author selected. The anchor
stores both the DOM element id and the original quoted text so we can
re-locate the comment even after the surrounding content is edited.

Replies are modelled as child comments (``parent_comment_id`` points at
the thread root). Resolution is per-thread: setting ``resolved_at`` on
the root marks the whole thread resolved; replies inherit.
"""
from datetime import datetime

from app.extensions import db


class TSDComment(db.Model):
    __tablename__ = "ts_document_comments"

    id = db.Column(db.Integer, primary_key=True)
    tsd_id = db.Column(
        db.Integer, db.ForeignKey("ts_documents.id"),
        nullable=False, index=True,
    )
    parent_comment_id = db.Column(
        db.Integer, db.ForeignKey("ts_document_comments.id"),
        index=True,
    )
    author_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False,
    )
    body = db.Column(db.Text, nullable=False)

    # Anchor: DOM id of the span that wraps the highlighted selection,
    # plus a snapshot of the quoted text for display and re-anchoring.
    anchor_id = db.Column(db.String(64))
    anchor_text = db.Column(db.String(500))

    resolved_at = db.Column(db.DateTime, index=True)
    resolved_by_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "tsd_id": self.tsd_id,
            "parent_comment_id": self.parent_comment_id,
            "author_id": self.author_id,
            "body": self.body,
            "anchor_id": self.anchor_id,
            "anchor_text": self.anchor_text,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "resolved_by_id": self.resolved_by_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
