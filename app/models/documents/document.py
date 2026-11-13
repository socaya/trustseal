from datetime import datetime
from app.extensions import db
# Assuming related models like User, Organization, Client etc. are importable
# from .user import User # Example
# from .organization import Organization # Example

class Document(db.Model):
    __tablename__ = 'documents'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    content = db.Column(db.Text) # Content of the document, potentially large
    file_name = db.Column(db.String(255)) # Original uploaded file name
    file_path = db.Column(db.String(255)) # Storage path (e.g., S3 key, local path)
    file_size = db.Column(db.Integer) # Size in bytes
    file_type = db.Column(db.String(50)) # MIME type
    document_type_id = db.Column(db.Integer, db.ForeignKey('document_types.id')) # Optional FK
    status = db.Column(db.String(20), default='draft', index=True) # E.g., draft, pending, signed, archived
    is_template = db.Column(db.Boolean, default=False, index=True)
    tags = db.Column(db.String(255)) # Comma-separated or JSON string of tags
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    deleted_at = db.Column(db.DateTime, index=True) # For soft deletes

    # Foreign Keys linking to Users
    signed_by_id = db.Column(db.Integer, db.ForeignKey('users.id')) # User who performed the final signature (if applicable)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False) # User who created the document record
    last_modified_by_id = db.Column(db.Integer, db.ForeignKey('users.id')) # User who last updated the record

    # Other Foreign Keys
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), index=True)
    stamp_id = db.Column(db.Integer, db.ForeignKey('digital_stamps.id')) # If using digital stamps
    client_id = db.Column(db.Integer, db.ForeignKey('clients.id')) # If linked to specific clients
    version = db.Column(db.Integer, default=1) # Document version number
    parent_id = db.Column(db.Integer, db.ForeignKey('documents.id')) # For version history linking
    is_shared = db.Column(db.Boolean, default=False) # Simple flag if shared

    # --- Relationships ---

    # Relationships to User model
    # `creator` links `created_by` FK to User. Use `creator` in code.
    creator = db.relationship('User', foreign_keys=[created_by], back_populates='created_documents')
    # *** This relationship is named 'signed_by' ***
    signed_by = db.relationship('User', foreign_keys=[signed_by_id], back_populates='signed_documents')
    # `last_modified_by_user` links `last_modified_by_id` FK. This name is correct.
    last_modified_by_user = db.relationship('User', foreign_keys=[last_modified_by_id], backref='modified_documents') # backref is simpler here if User doesn't need `modified_documents` defined with back_populates

    # Other relationships
    organization = db.relationship('Organization', back_populates='documents') # Assumes Organization model has 'documents' relationship
    client = db.relationship('Client', back_populates='documents') # Assumes Client model has 'documents' relationship
    # stamp = db.relationship('DigitalStamp', back_populates='documents') # Assumes DigitalStamp model and relationship named 'stamp'

    # One-to-Many relationships (Collections)
    parties = db.relationship('DocumentParty', back_populates='document', cascade='all, delete-orphan', lazy='dynamic') # Use lazy='dynamic' for large collections
    versions = db.relationship('DocumentVersion', back_populates='document', cascade='all, delete-orphan', lazy='dynamic')
    signatures = db.relationship('DocumentSignature', back_populates='document', cascade='all, delete-orphan', lazy='dynamic')
    activities = db.relationship('DocumentActivity', back_populates='document', cascade='all, delete-orphan', lazy='dynamic')
    shares = db.relationship('DocumentShare', back_populates='document', cascade='all, delete-orphan', lazy='dynamic')
    usages = db.relationship('StampUsage', back_populates='document', cascade='all, delete-orphan', lazy='dynamic') # For stamp usage tracking


    def to_dict(self, include_collections=False, include_content=False, include_related_objects=True):
        """
        Serializes the Document object to a dictionary.

        Args:
            include_collections (bool): If True, include lists of related items like parties, versions etc.
                                       Requires the related models to have to_dict(). Be cautious of performance.
            include_content (bool): If True, include the potentially large 'content' field.
            include_related_objects (bool): If True, includes simplified dictionary representations of related single objects
                                           (creator, organization etc.) Requires related models to have to_dict().
        """
        data = {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "file_name": self.file_name,
            "file_size": self.file_size,
            "file_type": self.file_type,
            "document_type_id": self.document_type_id, # Keep FK for reference
            "status": self.status,
            "is_template": self.is_template,
            "tags": self.tags,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "deleted_at": self.deleted_at.isoformat() if self.deleted_at else None,
            "organization_id": self.organization_id, # Keep FK for reference
            "stamp_id": self.stamp_id, # Keep FK for reference
            "client_id": self.client_id, # Keep FK for reference
            "version": self.version,
            "parent_id": self.parent_id, # Keep FK for reference
            "is_shared": self.is_shared,
            # Include FKs for user relationships for reference, even if objects are included
            "created_by_id": self.created_by,
            "signed_by_id": self.signed_by_id,
            "last_modified_by_id": self.last_modified_by_id,
        }

        # --- Conditional Fields ---
        if include_content:
            data['content'] = self.content

        # --- Conditional Related Objects ---
        if include_related_objects:
            # Assumes User, Organization, Client models have a basic to_dict() method
            # that DOES NOT recursively include documents to avoid circular references.
            if self.creator:
                 # Map the 'creator' relationship object to the 'created_by' key in the dict
                data['created_by'] = self.creator.to_dict()
            else:
                data['created_by'] = None

            # *** FIX: Use the correct relationship name 'signed_by' ***
            if self.signed_by:
                 # Map the 'signed_by' relationship object to the 'signed_by' key in the dict
                data['signed_by'] = self.signed_by.to_dict()
            else:
                data['signed_by'] = None

            # *** This relationship name 'last_modified_by_user' is correct based on definition above ***
            if self.last_modified_by_user:
                 # Map the 'last_modified_by_user' relationship object to the 'last_modified_by' key in the dict
                data['last_modified_by'] = self.last_modified_by_user.to_dict()
            else:
                data['last_modified_by'] = None

            if self.organization:
                data['organization'] = self.organization.to_dict() # Assumes Organization.to_dict() exists
            else:
                data['organization'] = None

            if self.client:
                data['client'] = self.client.to_dict() # Assumes Client.to_dict() exists
            else:
                data['client'] = None

            # Add other related objects like stamp if needed following the same pattern

        # --- Conditional Collections ---
        if include_collections:
            # Assumes DocumentParty, DocumentVersion etc. have to_dict() methods.
            # Use .all() because relationships are set to lazy='dynamic'
            data['parties'] = [party.to_dict() for party in self.parties.all()]
            data['versions'] = [version.to_dict() for version in self.versions.all()]
            data['signatures'] = [{"id": sig.id, "signature_type": sig.signature_type, "signed_at": sig.signed_at.isoformat() if sig.signed_at else None} for sig in self.signatures.all()]
            data['activities'] = [{"id": act.id, "activity_type": act.activity_type, "created_at": act.created_at.isoformat() if act.created_at else None} for act in self.activities.all()]
            data['shares'] = [{"id": share.id, "shared_with_user_id": share.shared_with_user_id, "can_view": share.can_view, "expires_at": share.expires_at.isoformat() if share.expires_at else None} for share in self.shares.all()]
            # data['usages'] = [usage.to_dict() for usage in self.usages.all()]


        return data

    def __repr__(self):
        return f'<Document {self.id}: {self.title}>'