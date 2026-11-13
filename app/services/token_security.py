"""JWT identity and revocation helpers.

All security decisions fail closed when a user is missing, disabled or a
revocation lookup cannot complete. Revocation writes are committed before
success is returned.
"""
from datetime import datetime, timezone

from flask_jwt_extended import get_jwt_identity
from sqlalchemy.exc import IntegrityError

from app.extensions import db, jwt
from app.models.user import User
from app.models.revoked_token import RevokedToken


def active_token_user():
    try:
        user_id = int(get_jwt_identity())
    except (ValueError, TypeError):
        return None
    return db.session.get(User, user_id)


@jwt.token_in_blocklist_loader
def token_is_revoked(_header, payload):
    try:
        user_id = int(payload["sub"])
        jti = payload["jti"]
        user = db.session.get(User, user_id)
        if user is None or not user.is_active:
            return True
        return db.session.get(RevokedToken, jti) is not None
    except (KeyError, TypeError, ValueError):
        return True


def revoke_token(payload):
    """Persist one token JTI, idempotently, in the existing transaction."""
    jti = payload["jti"]
    user_id = int(payload["sub"])
    expires_at = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
    if db.session.get(RevokedToken, jti) is None:
        db.session.add(RevokedToken(jti=jti, user_id=user_id, expires_at=expires_at))
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            if db.session.get(RevokedToken, jti) is None:
                raise
