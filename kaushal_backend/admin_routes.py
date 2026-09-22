"""
admin_routes.py
-----------------
Everything here requires an active admin session (@admin_required from
auth.py) — a signed-in student or alumni gets a 401 even if they guess
the URL, because their session only ever holds `user_id`, never
`admin_id`.

This is where the "send email notification" feature lives: the admin
dashboard lists users, the admin ticks one or more, writes a message,
and POSTs to /api/admin/notify.
"""

import os

from flask import Blueprint, request, jsonify

from kaushal_backend.models import AlumniFeedback, StudentProfile, User, EmailNotification, db
from kaushal_backend.email_service import send_email, EmailError
from kaushal_backend.auth import admin_required

admin_bp = Blueprint("admin", __name__)


def _filtered_users():
    role = request.args.get("role")
    skill = request.args.get("skill", "").strip()
    company = request.args.get("company", "").strip()
    query = User.query
    if role in ("student", "alumni"):
        query = query.filter_by(role=role)
    if skill:
        query = query.filter(User.skills.ilike(f"%{skill}%"))
    if company:
        query = query.filter(User.company.ilike(f"%{company}%"))
    return query.order_by(User.created_at.desc()).all()


@admin_bp.route("/api/admin/filter-users", methods=["GET"])
@admin_required
def filter_users():
    """Return database-backed recipients for the admin notification UI."""
    return jsonify([
        {
            "id": user.id,
            "email": user.email,
            "name": f"{user.first_name} {user.last_name}",
            "role": user.role,
            "phone": user.phone,
        }
        for user in _filtered_users()
    ])


@admin_bp.route("/api/admin/get-users", methods=["GET"])
@admin_required
def get_users():
    """Return all users or users narrowed to one recipient role."""
    role = request.args.get("role")
    query = User.query
    if role in ("student", "alumni"):
        query = query.filter_by(role=role)
    users = query.order_by(User.created_at.desc()).all()
    return jsonify([
        {
            "id": user.id,
            "name": f"{user.first_name} {user.last_name}",
            "email": user.email,
            "role": user.role,
        }
        for user in users
    ])


@admin_bp.route("/api/admin/email-status", methods=["GET"])
@admin_required
def email_status():
    """Expose safe SMTP readiness information to the admin UI."""
    configured = all(os.getenv(name, "").strip() for name in ("SMTP_USERNAME", "SMTP_PASSWORD", "EMAIL_FROM"))
    return jsonify({
        "configured": configured,
        "provider": os.getenv("SMTP_HOST", "smtp.gmail.com"),
        "message": "Email service is ready." if configured else "Add SMTP_USERNAME, SMTP_PASSWORD, and EMAIL_FROM to .env.",
    })


@admin_bp.route("/api/admin/users", methods=["GET"])
@admin_required
def list_users():
    """Filter recipients by role, skill, and company from stored profiles."""
    users = _filtered_users()
    return jsonify([
        {
            "id": u.id,
            "name": f"{u.first_name} {u.last_name}",
            "role": u.role,
            "phone": u.phone,
            "email": u.email,
        }
        for u in users
    ])


@admin_bp.route("/api/admin/notify", methods=["POST"])
@admin_bp.route("/admin/send-mail", methods=["POST"])
@admin_required
def notify_users():
    """
    Body: { "user_ids": [1, 2, 3], "subject": "Placement drive", "message": "..." }
    Sends the same email to every selected user and stores an audit record.
    """
    data = request.json or {}
    user_ids = data.get("user_ids", [])
    subject = (data.get("subject") or "").strip()
    message = (data.get("message") or "").strip()

    if not subject:
        return jsonify({"error": "Email subject is required"}), 400
    if not message:
        return jsonify({"error": "Message text is required"}), 400
    if not user_ids:
        return jsonify({"error": "Select at least one recipient"}), 400
    if len(subject) > 200:
        return jsonify({"error": "Keep the subject under 200 characters"}), 400
    if len(message) > 5000:
        return jsonify({"error": "Keep the message under 5000 characters"}), 400

    users = User.query.filter(User.id.in_(user_ids)).all()
    if not users:
        return jsonify({"error": "No matching users found"}), 404

    results = []
    for u in users:
        notification = EmailNotification(
            recipient_email=u.email, subject=subject, message=message, status="failed"
        )
        try:
            send_email(u.email, subject, message)
            notification.status = "sent"
            results.append({"user_id": u.id, "name": f"{u.first_name} {u.last_name}",
                             "email": u.email, "status": "sent"})
        except EmailError as e:
            notification.error = str(e)
            results.append({"user_id": u.id, "name": f"{u.first_name} {u.last_name}",
                             "email": u.email, "status": "failed", "error": str(e)})
        db.session.add(notification)

    db.session.commit()

    sent = sum(1 for r in results if r["status"] == "sent")
    return jsonify({"sent": sent, "total": len(results), "results": results}), 200
