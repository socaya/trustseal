"""Refresh-token family tracking for reuse detection.

Each login issues a :class:`RefreshTokenFamily`. Every refresh token
JWT carries a ``fam`` claim pointing at the family and its ``jti`` is
recorded in :class:`RefreshTokenJti`. On rotation the previous ``jti``
is marked revoked and a fresh one is issued in the same family.

If a revoked ``jti`` is ever presented, the dispatcher treats it as a
replay: the entire family is revoked and a ``SecurityEvent`` is raised
so operators can respond to the credential leak.
"""
from datetime import datetime

from app.extensions import db


class RefreshTokenFamily(db.Model):
    __tablename__ = "refresh_token_families"

    id = db.Column(db.BigInteger, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, index=True
    )
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    revoked_at = db.Column(db.DateTime)
    revoke_reason = db.Column(db.String(80))


class RefreshTokenJti(db.Model):
    __tablename__ = "refresh_token_jtis"

    jti = db.Column(db.String(64), primary_key=True)
    family_id = db.Column(
        db.BigInteger,
        db.ForeignKey("refresh_token_families.id"),
        nullable=False,
        index=True,
    )
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, index=True
    )
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    rotated_at = db.Column(db.DateTime)
    revoked_at = db.Column(db.DateTime)
