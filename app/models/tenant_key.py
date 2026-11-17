"""Per-tenant Data Encryption Key (DEK) storage.

Each tenant has a random 256-bit Fernet key, generated on first use.
The raw key never touches the database — what's stored is the key
envelope-encrypted by a master Key Encryption Key derived from the
server's ``SECRET_KEY``.

Rotation separates two concerns:

* ``master_key_version``  — bumps when the server's SECRET_KEY rotates.
                             ``flask tsd rewrap --master`` re-wraps every
                             tenant's DEK under the new master.
* ``tenant_key_version``  — bumps when an individual tenant key rotates.
                             ``flask tsd rewrap --tenant <org_id>`` writes
                             a new random DEK and re-encrypts every
                             document in that tenant under it.
"""
from datetime import datetime

from app.extensions import db


class TenantKey(db.Model):
    __tablename__ = "tenant_keys"

    organization_id = db.Column(
        db.Integer,
        db.ForeignKey("organizations.id"),
        primary_key=True,
    )
    wrapped_key = db.Column(db.LargeBinary, nullable=False)
    master_key_version = db.Column(db.Integer, nullable=False, default=1)
    tenant_key_version = db.Column(db.Integer, nullable=False, default=1)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    rotated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
