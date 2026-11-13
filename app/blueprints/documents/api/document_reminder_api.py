from flask import Blueprint, request, jsonify
from app.extensions import db
from app.models.documents.document_reminder import DocumentReminder
from datetime import datetime

document_reminder_api = Blueprint('document_reminder_api', __name__, url_prefix='/api/document-reminders')


# === LIST ALL ===
@document_reminder_api.route('/', methods=['GET'])
def list_reminders():
    reminders = DocumentReminder.query.order_by(DocumentReminder.id.desc()).all()
    return jsonify([r.to_dict() for r in reminders])


# === GET ONE ===
@document_reminder_api.route('/<int:reminder_id>', methods=['GET'])
def get_reminder(reminder_id):
    r = DocumentReminder.query.get_or_404(reminder_id)
    return jsonify(r.to_dict())


# === CREATE ===
@document_reminder_api.route('/', methods=['POST'])
def create_reminder():
    data = request.get_json()
    reminder = DocumentReminder(
        document_id=data.get("document_id"),
        scheduled_for=datetime.fromisoformat(data.get("scheduled_for")),
        message=data.get("message"),
        recipient_email=data.get("recipient_email"),
        sent_at=datetime.fromisoformat(data["sent_at"]) if data.get("sent_at") else None
    )
    db.session.add(reminder)
    db.session.commit()
    return jsonify({"message": "Reminder created", "id": reminder.id}), 201


# === UPDATE ===
@document_reminder_api.route('/<int:reminder_id>', methods=['PUT'])
def update_reminder(reminder_id):
    reminder = DocumentReminder.query.get_or_404(reminder_id)
    data = request.get_json()

    reminder.document_id = data.get("document_id", reminder.document_id)
    if "scheduled_for" in data:
        reminder.scheduled_for = datetime.fromisoformat(data["scheduled_for"])
    if "sent_at" in data:
        reminder.sent_at = datetime.fromisoformat(data["sent_at"]) if data["sent_at"] else None
    reminder.message = data.get("message", reminder.message)
    reminder.recipient_email = data.get("recipient_email", reminder.recipient_email)

    db.session.commit()
    return jsonify({"message": "Reminder updated", "id": reminder.id})


# === DELETE ===
@document_reminder_api.route('/<int:reminder_id>', methods=['DELETE'])
def delete_reminder(reminder_id):
    reminder = DocumentReminder.query.get_or_404(reminder_id)
    db.session.delete(reminder)
    db.session.commit()
    return jsonify({"message": "Reminder deleted", "id": reminder.id})
