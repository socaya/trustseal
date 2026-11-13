# app/blueprints/documents/api/document_api.py

from flask import Blueprint, request, jsonify, abort, current_app # Added abort, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity # Added JWT imports
from sqlalchemy.exc import SQLAlchemyError # For catching DB errors

from app.extensions import db
from app.models.documents.document import Document
# Make sure your User model is importable, adjust path if needed
# from app.models import User # Or from app.models.user import User
from app.models.user import User # Assuming this path is correct


# Define the Blueprint
# *** FIX: Removed strict_slashes=False argument ***
document_api = Blueprint('document_api', __name__, url_prefix='/api/documents')


# --- Helper Function for Authorization ---
# (Keep the helper function as defined in the previous response)
def get_authorized_document_or_abort(document_id, check_ownership_only=False):
    # ... (implementation from previous step) ...
    user_id_str = get_jwt_identity()
    try:
        user_id = int(user_id_str)
    except (ValueError, TypeError):
        current_app.logger.error(f"Invalid JWT identity (sub claim) format: {user_id_str}")
        abort(401, description="Invalid user identity in token.")

    current_user = User.query.get(user_id)
    if not current_user:
         current_app.logger.error(f"User with ID {user_id} from JWT not found in database.")
         abort(401, description="User identity from token not found.")

    doc = Document.query.get(document_id)
    if not doc:
        abort(404, description="Document not found.")

    is_authorized = False
    if doc.created_by == user_id:
        is_authorized = True
    # Add other authorization rules here (org, sharing etc.)

    if check_ownership_only:
        if doc.created_by != user_id:
             current_app.logger.warning(f"User {user_id} forbidden (ownership required) to modify/delete document {document_id} created by {doc.created_by}.")
             abort(403, description="Forbidden: You do not have permission to modify or delete this document.")
    elif not is_authorized:
        current_app.logger.warning(f"User {user_id} forbidden to access document {document_id}.")
        abort(403, description="Forbidden: You do not have permission to access this document.")

    current_app.logger.debug(f"User {user_id} authorized for document {document_id}.")
    return doc


# === LIST Documents ===
# (Keep the function as defined in the previous response)
@document_api.route('/mine', methods=['GET'])
@jwt_required()
def list_user_documents():
    # ... (implementation from previous step) ...
    user_id_str = get_jwt_identity()
    user_id = int(user_id_str)
    try:
        query = Document.query.filter(Document.created_by == user_id) # Example filter
        documents = query.order_by(Document.updated_at.desc()).all()
        current_app.logger.debug(f"Found {len(documents)} documents for user {user_id}.")
        return jsonify([d.to_dict(include_related_objects=True, include_content=False, include_collections=False) for d in documents])
    except SQLAlchemyError as e:
        # ... error handling ...
        abort(500, description="Database error occurred while retrieving documents.")
    except Exception as e:
        # ... error handling ...
        abort(500, description="Server error occurred while retrieving documents.")

# === LIST Documents ===
@document_api.route('/', methods=['GET'])
@jwt_required() # Require JWT authentication
def list_documents():
    """Lists documents belonging to the current user's organization."""
    user_id_str = get_jwt_identity()
    try:
        # Ensure user ID from token is valid
        user_id = int(user_id_str)
    except (ValueError, TypeError):
         current_app.logger.error(f"Invalid JWT identity format listing documents: {user_id_str}")
         abort(401, description="Invalid user identity in token.")

    try:
        # 1. Fetch the current user object from database
        user = User.query.get(user_id)
        if not user:
            current_app.logger.warning(f"User {user_id} from token not found in DB during list_documents.")
            abort(401, description="User from token not found.") # Or return jsonify([]) if preferred

        # 2. Check if the user belongs to an organization
        if not user.organization_id:
            current_app.logger.info(f"User {user_id} does not belong to an organization. Returning empty document list.")
            return jsonify([]) # Return empty list if user has no organization

        # 3. Query documents matching the user's organization ID
        query = Document.query.filter(Document.organization_id == user.organization_id)

        # --- Optional: Add status filters if needed ---
        # Example: Exclude deleted/archived documents from the main list
        # query = query.filter(Document.status != 'archived', Document.deleted_at.is_(None))

        # 4. Apply sorting
        documents = query.order_by(Document.updated_at.desc()).all() # Sort by update time

        current_app.logger.debug(f"Found {len(documents)} documents for organization {user.organization_id} (user {user_id}).")

        # 5. Serialize and return the list
        # Exclude bulky/unnecessary fields for list view
        return jsonify([d.to_dict(include_related_objects=True, include_content=False, include_collections=False) for d in documents])

    except SQLAlchemyError as e:
        # Log database errors
        user_org_id = user.organization_id if 'user' in locals() and user else 'N/A'
        current_app.logger.error(f"Database error listing documents for user {user_id} / org {user_org_id}: {e}", exc_info=True)
        abort(500, description="Database error occurred while retrieving documents.")
    except Exception as e:
        # Log other unexpected errors
        current_app.logger.error(f"Unexpected error listing documents for user {user_id}: {e}", exc_info=True)
        abort(500, description="Server error occurred while retrieving documents.")

# Keep the rest of your API functions (get_document, create_document, etc.) as they were
# in the previous corrected version (with authentication/authorization).


# === GET ONE Document ===
# Using trailing slash here, Flask default (strict_slashes=True) will handle requests without it via redirect
@document_api.route('/<int:document_id>/', methods=['GET'])
@jwt_required()
def get_document(document_id):
    # (Keep the function as defined in the previous response)
    try:
        doc = get_authorized_document_or_abort(document_id)
        return jsonify(doc.to_dict(include_related_objects=True, include_collections=True, include_content=True))
    except SQLAlchemyError as e:
         # ... error handling ...
         abort(500, description="Database error occurred while retrieving the document.")
    except Exception as e:
         # ... error handling ...
         abort(500, description="Server error occurred while retrieving the document.")


# === CREATE Document ===
# (Keep the function as defined in the previous response)
@document_api.route('/', methods=['POST'])
@jwt_required()
def create_document():
    # ... (implementation from previous step) ...
    user_id_str = get_jwt_identity()
    user_id = int(user_id_str)
    data = request.get_json()
    if not data: abort(400, description="No input data provided or request is not JSON.")
    # ... (map allowed fields, set created_by=user_id) ...
    try:
        # ... (create doc, commit) ...
        return jsonify(doc.to_dict(include_related_objects=True)), 201
    except SQLAlchemyError as e:
        # ... error handling ...
        abort(500, description=f"Failed to create document due to database error: {e}")
    except Exception as e:
        # ... error handling ...
        abort(500, description="Failed to create document due to server error.")


# === UPDATE Document ===
# (Keep the function as defined in the previous response)
@document_api.route('/<int:document_id>/', methods=['PUT'])
@jwt_required()
def update_document(document_id):
     # ... (implementation from previous step, calls get_authorized_document_or_abort) ...
    try:
        # ... (update fields, commit) ...
        return jsonify(doc.to_dict(include_related_objects=True))
    except SQLAlchemyError as e:
        # ... error handling ...
        abort(500, description=f"Failed to update document due to database error: {e}")
    except Exception as e:
        # ... error handling ...
        abort(500, description="Failed to update document due to server error.")


# === DELETE Document ===
# (Keep the function as defined in the previous response)
@document_api.route('/<int:document_id>/', methods=['DELETE'])
@jwt_required()
def delete_document(document_id):
     # ... (implementation from previous step, calls get_authorized_document_or_abort) ...
    try:
        # ... (delete doc, commit) ...
        return '', 204
    except SQLAlchemyError as e:
        # ... error handling ...
        abort(500, description=f"Failed to delete document due to database error: {e}")
    except Exception as e:
        # ... error handling ...
        abort(500, description="Failed to delete document due to server error.")