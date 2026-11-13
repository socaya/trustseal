# app/blueprints/documents/views/document_views.py

import os
from flask import (
    Blueprint, render_template, request, redirect, url_for,
    flash, send_from_directory, current_app, abort
)
from flask_login import login_required, current_user

# Assuming DocumentForm is correctly defined elsewhere
# Adjust the import path if your form is in a different location
from ..forms.document_form import DocumentForm

# Adjust the import path for api_client based on your project structure
# Assuming services is at the same level as the app directory (e.g., ../../services)
# Or maybe from app.services import api_client if services is inside app
from ....services import api_client # Modify '....' based on actual structure

# Add imports for the models you need for the dropdowns
# Adjust paths based on your models' location (e.g., app.models.organization etc.)
try:
    from app.models import Organization, Client, DocumentType, DigitalStamp
    MODELS_IMPORTED = True
except ImportError:
    # Handle case where models might not exist (e.g., during initial setup)
    # This allows the app to potentially start but form choices won't populate
    current_app.logger.warning("Could not import Organization, Client, DocumentType, or DigitalStamp models. Dropdown choices will be unavailable.")
    Organization, Client, DocumentType, DigitalStamp = None, None, None, None
    MODELS_IMPORTED = False


# Ensure the blueprint name matches how it's registered in app/__init__.py
document_views = Blueprint('document_views', __name__, url_prefix='/documents')


# --- Helper Function to Populate Form Choices ---
def _populate_form_choices(form):
    """Queries DB and sets choices for SelectFields on the given form instance."""
    if not MODELS_IMPORTED:
        current_app.logger.error("Cannot populate form choices because models failed to import.")
        flash("Error loading form options: Required models not found.", "danger")
        return False # Indicate failure immediately

    try:
        # Query choices - ensure models exist before querying
        org_choices = [(org.id, org.name) for org in Organization.query.order_by('name').all()] if Organization else []
        client_choices = [(c.id, c.name) for c in Client.query.order_by('name').all()] if Client else []
        type_choices = [(dt.id, dt.name) for dt in DocumentType.query.order_by('name').all()] if DocumentType else []
        stamp_choices = [(ds.id, ds.name) for ds in DigitalStamp.query.order_by('name').all()] if DigitalStamp else []

        # Set choices on form fields, using getattr for safety
        # Add a blank/prompt option for optional fields
        if hasattr(form, 'organization_id') and Organization:
            form.organization_id.choices = [('', '-- Select Organization --')] + org_choices
        if hasattr(form, 'client_id') and Client:
            form.client_id.choices = [('', '-- Select Client --')] + client_choices

        # *** VERIFY YOUR FIELD NAME IN DocumentForm ***
        # Change 'document_type' below if your form field name is different (e.g., document_type_id)
        correct_doc_type_field_name = 'document_type'
        if hasattr(form, correct_doc_type_field_name) and DocumentType:
            getattr(form, correct_doc_type_field_name).choices = [('', '-- Select Document Type --')] + type_choices
        elif not hasattr(form, correct_doc_type_field_name):
             current_app.logger.warning(f"Form does not have attribute '{correct_doc_type_field_name}' for choices.")

        if hasattr(form, 'stamp_id') and DigitalStamp:
            form.stamp_id.choices = [('', '-- Select Digital Stamp --')] + stamp_choices

        current_app.logger.debug("Attempted to populate form choices.")
        return True # Indicate success (even if some lists were empty)

    except Exception as e:
        # Log the specific error during database query or choice setting
        current_app.logger.error(f"Error populating form choices: {e}", exc_info=True)
        flash("Error loading form options. Please check server logs.", "danger")
        return False # Indicate failure


# === LIST ===
@document_views.route('/')
@login_required # Good practice to protect list view too
def index():
    """Displays the list of accessible documents."""
    current_app.logger.debug(f"User {current_user.id} accessing document list view.")
    # Use trailing slash if API expects it, aligning with API route definitions
    api_endpoint = "documents/"
    documents_data = api_client.get_data(api_endpoint)

    documents = [] # Default to empty list

    # Check for API Client Errors
    if isinstance(documents_data, dict) and documents_data.get("error"):
        error_message = documents_data.get("error", "Unknown API error")
        status_code = documents_data.get("status_code")
        current_app.logger.error(f"API Error fetching documents list (Status {status_code}): {error_message}")
        # Provide more context if it's an auth error from the API
        if status_code == 401 or status_code == 403:
             flash("You may not be authorized to view documents or your session expired.", "warning")
        else:
             flash(f"Error loading documents: {error_message}", "danger")
    elif isinstance(documents_data, list):
         # Success case
         documents = documents_data
         current_app.logger.debug(f"Successfully fetched {len(documents)} documents from API for user {current_user.id}.")
    else:
        # Handle unexpected data type from api_client
        current_app.logger.error(f"Unexpected data type received from API client get_data('{api_endpoint}'): {type(documents_data)}")
        flash("Error loading documents: Unexpected response format from server.", "danger")

    return render_template("documents/list.html", documents=documents)


# === DETAILS ===
@document_views.route('/<int:document_id>')
@login_required # Protect details view
def view_document(document_id):
    """Displays the details page for a single document."""
    current_app.logger.debug(f"User {current_user.id} viewing document details for ID: {document_id}.")
    # Use trailing slash if API expects it
    api_endpoint = f"documents/{document_id}/"
    document_data = api_client.get_data(api_endpoint)

    # Check for API Client Errors or if document not found/authorized
    if not document_data or (isinstance(document_data, dict) and document_data.get("error")):
        error_message = "Document not found or could not be retrieved."
        status_code = None
        if isinstance(document_data, dict):
             error_message = document_data.get("error", error_message)
             status_code = document_data.get("status_code")

        current_app.logger.warning(f"Failed to retrieve document {document_id} for user {current_user.id}. API Status: {status_code}, Error: {error_message}")
        # Give specific feedback based on API status code if available
        if status_code == 404:
            flash("Document not found.", "danger")
        elif status_code == 403:
            flash("You do not have permission to view this document.", "danger")
        else:
            flash(error_message, "danger")
        return redirect(url_for(".index")) # Use '.' for endpoint within same blueprint

    # Check if the result is actually a dictionary (expected for a single document)
    if not isinstance(document_data, dict):
         current_app.logger.error(f"Unexpected data type {type(document_data)} received for document {document_id}.")
         flash("Error retrieving document details: Unexpected response format.", "danger")
         return redirect(url_for(".index"))

    # Pass the fetched dictionary to the template
    current_app.logger.debug(f"Rendering details for document {document_id}.")
    return render_template("documents/details.html", document=document_data)


# === CREATE ===
@document_views.route('/create', methods=['GET', 'POST'])
@login_required
def create_document():
    """Handles document creation form display (GET) and submission (POST)."""
    form = DocumentForm() # Instantiate the form

    # Populate choices BEFORE validation attempt on POST or rendering on GET
    if not _populate_form_choices(form):
        # If choices fail to load, prevent form display/processing
         return redirect(url_for('.index'))

    # Process POST request
    if form.validate_on_submit():
        payload = form.data.copy()
        payload.pop('csrf_token', None) # Remove CSRF token if not needed by API

        # Convert empty string selections from dropdowns to None for the API/DB
        # *** Ensure field names here MATCH EXACTLY the names in your DocumentForm ***
        form_fk_fields = {
            'organization_id': 'organization_id',
            'client_id': 'client_id',
            'document_type': 'document_type_id', # Map form field name to payload/DB name
            'stamp_id': 'stamp_id'
        }
        for form_field, payload_field in form_fk_fields.items():
             if payload.get(form_field) == '':
                  payload[payload_field] = None
             # Remove the original form field key if it's different from payload key
             if form_field != payload_field:
                 payload.pop(form_field, None)


        current_app.logger.debug(f"User {current_user.id} attempting to create document via API with payload: {payload}")
        # Use trailing slash if API expects it
        result = api_client.post_data("documents/", data=payload)

        if result and not result.get("error"):
            created_id = result.get('id')
            flash("Document created successfully.", "success")
            current_app.logger.info(f"Document {created_id} created successfully by user {current_user.id}.")
            # Redirect to the new document's detail page if ID is returned
            return redirect(url_for(".view_document", document_id=created_id) if created_id else url_for(".index"))
        else:
            # API returned an error
            api_error = result.get('error', 'Unknown API error')
            flash(f"Failed to create document: {api_error}", "danger")
            current_app.logger.error(f"API error creating document for user {current_user.id}: {result}")
            # Fall through to render form again (choices are populated, form has errors)
    elif request.method == 'POST':
         # Form validation failed
         flash("Please correct the errors below and resubmit.", "warning")

    # Render template on initial GET request or after POST validation failure
    return render_template("documents/create.html", form=form)


# === EDIT ===
@document_views.route('/<int:document_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_document_view(document_id):
    """Handles document edit form display (GET) and submission (POST)."""
    form = DocumentForm() # Instantiate blank form first for choice population

    # Populate choices BEFORE dealing with existing data or validation
    if not _populate_form_choices(form):
         return redirect(url_for('.index'))

    # Handle GET request: Fetch existing data AFTER choices are set
    if request.method == 'GET':
        current_app.logger.debug(f"User {current_user.id} fetching document {document_id} for editing...")
        doc_data = api_client.get_data(f"documents/{document_id}/") # Trailing slash
        if not doc_data or doc_data.get("error"):
            flash(f"Document not found or error retrieving: {doc_data.get('error', 'Not Found')}", "danger")
            return redirect(url_for(".index"))
        if not isinstance(doc_data, dict):
            flash("Failed to load document data: Invalid format received.", "danger")
            return redirect(url_for(".index"))
        # Populate form with existing data for display
        form.process(data=doc_data)
        # Handle potential mismatches between DB FK IDs and form field names if necessary
        # Example: if form has 'document_type' but data has 'document_type_id'
        if 'document_type_id' in doc_data and hasattr(form, 'document_type'):
             form.document_type.data = doc_data['document_type_id']

    # Handle POST request (after choices are populated)
    if form.validate_on_submit(): # Validates incoming request.form data against the form definition
        payload = form.data.copy()
        payload.pop('csrf_token', None)
        # Convert empty string selections to None
        form_fk_fields = {
            'organization_id': 'organization_id',
            'client_id': 'client_id',
            'document_type': 'document_type_id', # Map form field name to payload/DB name
            'stamp_id': 'stamp_id'
        }
        for form_field, payload_field in form_fk_fields.items():
             if payload.get(form_field) == '':
                  payload[payload_field] = None
             if form_field != payload_field:
                 payload.pop(form_field, None)

        current_app.logger.debug(f"User {current_user.id} attempting to update document {document_id} via API...")
        result = api_client.put_data(f"documents/{document_id}/", data=payload) # Trailing slash

        if result and not result.get("error"):
            flash("Document updated successfully.", "success")
            return redirect(url_for(".view_document", document_id=document_id))
        else:
            api_error = result.get('error', 'Unknown error')
            flash(f"Failed to update document: {api_error}", "danger")
            current_app.logger.error(f"API error updating document {document_id} for user {current_user.id}: {result}")
            # Fall through to render form again (choices populated, form has errors/submitted data)
    elif request.method == 'POST':
         # Form validation failed
         flash("Please correct the errors below and resubmit.", "warning")

    # Render template on initial GET or after POST validation failure
    return render_template("documents/edit.html", form=form, document_id=document_id)


# === DELETE ===
@document_views.route('/<int:document_id>/delete', methods=['POST'])
@login_required # Important! Protect delete action
def delete_document_view(document_id):
    """Handles document deletion via POST request."""
    # Consider adding CSRF protection check here, perhaps via a simple hidden field form
    current_app.logger.debug(f"User {current_user.id} attempting to delete document {document_id} via API...")
    # Use trailing slash if API expects it
    result = api_client.delete_data(f"documents/{document_id}/")

    if result and result.get("success"):
        flash("Document deleted successfully.", "success")
        current_app.logger.info(f"Document {document_id} deleted by user {current_user.id}.")
    else:
        error_message = result.get("error", "Unknown error")
        flash(f"Failed to delete document: {error_message}", "danger")
        current_app.logger.error(f"API error deleting document {document_id} for user {current_user.id}: {result}")

    # Redirect back to the list view after attempting delete
    return redirect(url_for(".index"))


# === DOWNLOAD ===
@document_views.route('/<int:document_id>/download')
@login_required # Ensure user is logged in
def download_document(document_id):
    """Handles file downloads for a specific document."""
    # 1. Get document metadata from API
    current_app.logger.debug(f"User {current_user.id} fetching metadata for document {document_id} to download...")
    api_endpoint = f"documents/{document_id}/"
    doc = api_client.get_data(api_endpoint) # Use trailing slash if API expects it

    # 2. Handle errors (document not found, API error, invalid format)
    error_message = None
    if not doc or (isinstance(doc, dict) and doc.get("error")):
        error_message = "Could not retrieve document information."
        status_code = None
        if isinstance(doc, dict):
            error_message = doc.get("error", error_message)
            status_code = doc.get("status_code")
        flash(error_message, "danger")
        current_app.logger.warning(f"Download failed: Cannot get metadata for document {document_id}. User: {current_user.id}, Status: {status_code}, Error: {error_message}")
        # Redirect back safely
        referer = request.headers.get("Referer")
        if referer and 'download' in referer: return redirect(url_for(".index")) # Avoid loop
        return redirect(referer or url_for(".index"))

    if not isinstance(doc, dict):
         flash("Could not retrieve document information: Invalid format.", "danger")
         current_app.logger.error(f"Download failed: Unexpected data type for document {document_id}: {type(doc)}")
         return redirect(url_for(".index"))

    # 3. Extract file information
    file_path_relative = doc.get("file_path") # Filename or relative path within UPLOAD_FOLDER
    original_filename = doc.get("file_name") # Original filename for download prompt

    if not file_path_relative:
        flash("Document record found, but no associated file path is available.", "warning")
        current_app.logger.warning(f"Download failed: No file_path found for document {document_id}. User: {current_user.id}")
        # Redirect to details page might be better here
        return redirect(url_for(".view_document", document_id=document_id))

    # Determine the name for the download prompt (prefer original, fallback to path basename)
    download_name = original_filename if original_filename else os.path.basename(file_path_relative)

    # 4. Get upload directory from config
    upload_folder = current_app.config.get('UPLOAD_FOLDER')
    # CRITICAL: Ensure UPLOAD_FOLDER is configured and is an ABSOLUTE path for security
    if not upload_folder or not os.path.isabs(upload_folder):
        current_app.logger.error(f"UPLOAD_FOLDER ('{upload_folder}') is not configured correctly or is not an absolute path.")
        flash("Server configuration error: Cannot determine file location.", "danger")
        return redirect(url_for(".view_document", document_id=document_id))

    current_app.logger.info(f"Attempting to send file for document {document_id}: directory='{upload_folder}', path='{file_path_relative}', download_name='{download_name}' for user {current_user.id}")

    # 5. Send the file using send_from_directory
    try:
        # Let send_from_directory handle joining directory and path safely
        return send_from_directory(
            directory=upload_folder,
            path=file_path_relative,
            as_attachment=True,
            download_name=download_name
        )
    except FileNotFoundError:
         # Log the path where the file was expected
         expected_path = os.path.normpath(os.path.join(upload_folder, file_path_relative))
         current_app.logger.error(f"Download failed: File not found for document {document_id}. User: {current_user.id}. Expected at '{expected_path}'")
         flash("Error: The document file could not be found on the server.", "danger")
         # Use abort(404) for a cleaner file-not-found response to the client
         abort(404, description="Document file not found on server.")
    except Exception as e:
         # Catch other potential errors (e.g., permissions, network issues)
         current_app.logger.error(f"Error sending file for document {document_id}. User: {current_user.id}. Error: {e}", exc_info=True)
         flash("An unexpected error occurred while trying to download the file.", "danger")
         return redirect(url_for(".view_document", document_id=document_id))