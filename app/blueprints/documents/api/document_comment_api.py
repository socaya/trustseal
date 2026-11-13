from flask import Blueprint, request, jsonify
from app.extensions import db
from app.models.documents.document_comment import DocumentComment

document_comment_api = Blueprint('document_comment_api', __name__, url_prefix='/api/document-comments')


# === LIST ALL COMMENTS ===
@document_comment_api.route('/', methods=['GET'])
def list_comments():
    comments = DocumentComment.query.order_by(DocumentComment.created_at.desc()).all()
    return jsonify([comment.to_dict() for comment in comments])


# === GET A SPECIFIC COMMENT ===
@document_comment_api.route('/<int:comment_id>', methods=['GET'])
def get_comment(comment_id):
    comment = DocumentComment.query.get_or_404(comment_id)
    return jsonify(comment.to_dict())


# === CREATE A NEW COMMENT ===
@document_comment_api.route('/', methods=['POST'])
def create_comment():
    data = request.get_json()
    comment = DocumentComment(
        document_id=data.get("document_id"),
        user_id=data.get("user_id"),
        content=data.get("content")
    )
    db.session.add(comment)
    db.session.commit()
    return jsonify({"message": "Comment created", "id": comment.id}), 201


# === UPDATE AN EXISTING COMMENT ===
@document_comment_api.route('/<int:comment_id>', methods=['PUT'])
def update_comment(comment_id):
    comment = DocumentComment.query.get_or_404(comment_id)
    data = request.get_json()
    comment.content = data.get("content", comment.content)
    db.session.commit()
    return jsonify({"message": "Comment updated", "id": comment.id})


# === DELETE A COMMENT ===
@document_comment_api.route('/<int:comment_id>', methods=['DELETE'])
def delete_comment(comment_id):
    comment = DocumentComment.query.get_or_404(comment_id)
    db.session.delete(comment)
    db.session.commit()
    return jsonify({"message": "Comment deleted", "id": comment.id})