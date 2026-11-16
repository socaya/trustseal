from flask import Blueprint, abort, request, jsonify
from flask_jwt_extended import jwt_required

from app.extensions import db
from app.models.documents.document_draft import DocumentDraft
from app.services.token_security import active_token_user

document_draft_api = Blueprint('document_draft_api', __name__, url_prefix='/api/document-drafts')


def _actor():
    user = active_token_user()
    if user is None or not user.is_active:
        abort(401)
    return user


def _owned_draft(draft_id, user):
    row = DocumentDraft.query.filter_by(
        id=draft_id, organization_id=user.organization_id, created_by=user.id
    ).first()
    if row is None:
        abort(404)
    return row


# === LIST ALL DRAFTS ===
@document_draft_api.route('/', methods=['GET'])
def list_drafts():
    drafts = DocumentDraft.query.order_by(DocumentDraft.created_at.desc()).all()
    return jsonify([draft.to_dict() for draft in drafts])


# === GET A SPECIFIC DRAFT ===
@document_draft_api.route('/<int:id>', methods=['GET'])
def get_draft(id):
    draft = DocumentDraft.query.get_or_404(id)
    return jsonify(draft.to_dict())


# === CREATE A NEW DRAFT ===
@document_draft_api.route('/', methods=['POST'])
def create_draft():
    data = request.get_json()
    draft = DocumentDraft(**data)
    db.session.add(draft)
    db.session.commit()
    return jsonify({"message": "Draft created", "id": draft.id}), 201


# === UPDATE EXISTING DRAFT ===
@document_draft_api.route('/<int:id>', methods=['PUT'])
def update_draft(id):
    draft = DocumentDraft.query.get_or_404(id)
    data = request.get_json()
    for key, value in data.items():
        setattr(draft, key, value)
    db.session.commit()
    return jsonify({"message": "Draft updated", "id": draft.id})


# === DELETE DRAFT ===
@document_draft_api.route('/<int:id>', methods=['DELETE'])
def delete_draft(id):
    draft = DocumentDraft.query.get_or_404(id)
    db.session.delete(draft)
    db.session.commit()
    return jsonify({"message": "Draft deleted", "id": id})


# === AUTOSAVE WITH OPTIMISTIC CONCURRENCY ===


AUTOSAVE_EDITABLE_KEYS = {
    "title",
    "description",
    "content",
    "tags",
    "status",
}


@document_draft_api.route("/<int:id>/autosave", methods=["POST"])
@jwt_required()
def autosave_draft(id):
    """Idempotent, concurrency-safe autosave for a draft.

    Requires ``If-Match: <version>`` and returns 412 with the current
    version when the caller's version is stale. On success the
    version is bumped and the new value returned so the UI can
    update its local copy.
    """
    user = _actor()
    draft = _owned_draft(id, user)
    expected_version_raw = request.headers.get("If-Match")
    if not expected_version_raw:
        abort(428, description="if_match_header_required")
    try:
        expected_version = int(expected_version_raw.strip('"'))
    except (TypeError, ValueError):
        abort(400, description="if_match_not_integer")
    # Lock the row + revalidate under the lock so two concurrent
    # autosaves cannot both succeed with the same If-Match value.
    draft = (
        DocumentDraft.query.filter_by(id=draft.id).with_for_update().one()
    )
    if draft.version != expected_version:
        return (
            jsonify(
                error="version_stale",
                current_version=draft.version,
                expected_version=expected_version,
                type="https://trustseal.dev/problems/version-stale",
            ),
            412,
        )
    data = request.get_json(silent=True) or {}
    extra = set(data) - AUTOSAVE_EDITABLE_KEYS
    if extra:
        abort(400, description=f"unsupported_fields:{','.join(sorted(extra))}")
    for key, value in data.items():
        setattr(draft, key, value)
    draft.version = expected_version + 1
    db.session.commit()
    return jsonify(id=draft.id, version=draft.version, draft=draft.to_dict())