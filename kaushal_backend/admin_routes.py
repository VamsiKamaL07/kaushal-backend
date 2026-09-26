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

import secrets
from datetime import datetime, timedelta

from flask import Blueprint, request, jsonify, url_for

from kaushal_backend.models import AlumniFeedback, StudentProfile, User, EmailNotification, db
from kaushal_backend.email_service import send_email, EmailError, email_configuration
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
            "verified": user.verified,
            "skills": user.skills,
            "company": user.company,
            "created_at": user.created_at.isoformat() if user.created_at else None,
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
            "verified": user.verified,
            "skills": user.skills,
            "company": user.company,
            "created_at": user.created_at.isoformat() if user.created_at else None,
        }
        for user in users
    ])


@admin_bp.route("/api/admin/email-status", methods=["GET"])
@admin_required
def email_status():
    """Expose safe email-provider readiness information to the admin UI."""
    provider, configured = email_configuration()
    return jsonify({
        "configured": configured,
        "provider": provider,
        "message": "Email service is ready." if configured else "Configure the email provider and sender in the service environment.",
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
            "verified": u.verified,
            "skills": u.skills,
            "company": u.company,
            "created_at": u.created_at.isoformat() if u.created_at else None,
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


@admin_bp.route("/api/admin/users/<int:user_id>/verify", methods=["POST"])
@admin_required
def verify_user(user_id):
    user = User.query.get_or_404(user_id)
    user.verified = True
    user.verification_token = None
    user.verification_expires_at = None
    db.session.commit()
    return jsonify({"message": "User verified", "user_id": user.id}), 200


@admin_bp.route("/api/admin/users/<int:user_id>/resend-verification", methods=["POST"])
@admin_required
def resend_verification(user_id):
    user = User.query.get_or_404(user_id)
    if user.verified:
        return jsonify({"error": "This account is already verified"}), 409

    token = secrets.token_urlsafe(48)
    user.verification_token = token
    user.verification_expires_at = datetime.utcnow() + timedelta(hours=24)
    verification_url = url_for("auth.verify_email", token=token, _external=True)
    notification = EmailNotification(
        recipient_email=user.email,
        subject="Verify your KAUSHAL-X account",
        message=f"Hello {user.first_name},\n\nVerify your email to activate your account:\n{verification_url}\n\nThis link expires in 24 hours.",
        status="pending",
    )
    db.session.add(notification)
    db.session.commit()

    try:
        send_email(user.email, notification.subject, notification.message)
        notification.status = "sent"
        result = {"message": "Verification email sent", "email_sent": True}
    except EmailError as exc:
        notification.status = "failed"
        notification.error = str(exc)[:500]
        result = {"message": "Verification email could not be sent", "email_sent": False}
    db.session.commit()
    return jsonify(result), 200
