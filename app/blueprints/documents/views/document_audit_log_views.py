from flask import Blueprint, render_template, request, redirect, url_for, flash
from app.services import api_client

document_audit_log_views = Blueprint('document_audit_log_views', __name__, url_prefix='/documents/audit-logs')


# === LIST ===
@document_audit_log_views.route('/')
def list_audit_logs():
    items = api_client.get_data("document-audit-logs") or []
    return render_template('documents/audit_logs/list.html', items=items)


# === DETAILS ===
@document_audit_log_views.route('/<int:item_id>')
def audit_log_details(item_id):
    item = api_client.get_data(f"document-audit-logs/{item_id}")
    if not item or item.get("error"):
        flash("Audit log not found.", "danger")
        return redirect(url_for("document_audit_log_views.list_audit_logs"))
    return render_template("documents/audit_logs/details.html", item=item)

# === DELETE (if necessary) ===
@document_audit_log_views.route('/<int:item_id>/delete', methods=['POST'])
def delete_audit_log_view(item_id):
    result = api_client.delete_data(f"document-audit-logs/{item_id}")
    if result and result.get("success"):
        flash("Audit log entry deleted.", "success")
    else:
        flash(result.get("error", "Failed to delete log entry."), "danger")
    return redirect(url_for("document_audit_log_views.list_audit_logs"))