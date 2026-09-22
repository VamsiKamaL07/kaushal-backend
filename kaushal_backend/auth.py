"""
auth.py
--------
Two independent auth flows living side by side:

    /api/auth/register, /api/auth/login
            -> student & alumni, backed by the `users` table.

  /api/admin/login
      -> placement-cell staff, backed by the separate `admins` table.
         Notice it never touches `users` at all.

`login_required` gates student/alumni routes; `admin_required` gates
admin routes. A session can hold either `user_id`+`role` OR `admin_id`
— never both meaningfully at once (admin_login() clears the session
first) — so a signed-in student can't also carry admin rights and
vice versa.
"""

import os
import re
import secrets
from datetime import datetime, timedelta
from functools import wraps
from flask import Blueprint, request, jsonify, session, redirect, url_for
from authlib.integrations.flask_client import OAuth

from models import db, User, Admin
from email_service import send_email, EmailError

auth_bp = Blueprint("auth", __name__)
oauth = OAuth()
google = None

EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def configure_oauth(app):
    global google
    oauth.init_app(app)
    client_id = os.getenv("GOOGLE_CLIENT_ID")
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
    if client_id and client_secret:
        google = oauth.register(
            name="google",
            client_id=client_id,
            client_secret=client_secret,
            server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
            client_kwargs={"scope": "openid email profile"},
        )


# ---------- decorators ----------

def login_required(role: str | None = None):
    """Protects student/alumni routes. Pass role='student' or 'alumni' to restrict further."""
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if not session.get("user_id"):
                return jsonify({"error": "Sign in required"}), 401
            if role and session.get("role") != role:
                return jsonify({"error": "Forbidden for this role"}), 403
            return fn(*args, **kwargs)
        return wrapper
    return decorator


def admin_required(fn):
    """Protects admin-only routes. A student/alumni session never satisfies this."""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("admin_id"):
            return jsonify({"error": "Admin authentication required"}), 401
        return fn(*args, **kwargs)
    return wrapper


# ---------- student / alumni signup & login ----------

@auth_bp.route("/api/auth/register", methods=["POST"])
def register():
    data = request.json or {}

    role = data.get("role")
    if role not in ("student", "alumni"):
        return jsonify({"error": "Role must be 'student' or 'alumni'"}), 400

    phone = data.get("phone", "").strip() or f"9{secrets.randbelow(10**9):09d}"
    email = data.get("email", "").strip().lower()
    if not EMAIL_RE.match(email):
        return jsonify({"error": "Invalid email address"}), 400

    password = data.get("password", "")
    if len(password) < 6:
        return jsonify({"error": "Password must be at least 6 characters"}), 400

    first_name = data.get("firstName", "").strip()
    last_name = data.get("lastName", "").strip()
    if not (first_name and last_name):
        return jsonify({"error": "First and last name are required"}), 400

    if User.query.filter((User.email == email) | (User.phone == phone)).first():
        return jsonify({"error": "An account with this email or phone already exists"}), 409

    token = secrets.token_urlsafe(48)
    user = User(role=role, first_name=first_name, last_name=last_name,
                email=email, phone=phone, auth_type="manual", verified=False,
                verification_token=token,
                verification_expires_at=datetime.utcnow() + timedelta(hours=24))
    user.set_password(password)
    db.session.add(user)
    db.session.commit()

    verification_url = url_for("auth.verify_email", token=token, _external=True)
    try:
        send_email(
            email,
            "Verify your KAUSHAL-X account",
            f"Hello {first_name},\n\nVerify your email to activate your account:\n{verification_url}\n\nThis link expires in 24 hours.",
        )
    except EmailError as exc:
        db.session.delete(user)
        db.session.commit()
        return jsonify({"error": str(exc)}), 503

    return jsonify({"message": "Account created. Check your email to verify it.",
                    "verification_required": True}), 201


@auth_bp.route("/api/auth/verify-email/<token>", methods=["GET"])
def verify_email(token):
    user = User.query.filter_by(verification_token=token).first()
    if not user or not user.verification_expires_at or user.verification_expires_at < datetime.utcnow():
        return jsonify({"error": "This verification link is invalid or expired"}), 400
    user.verified = True
    user.verification_token = None
    user.verification_expires_at = None
    db.session.commit()
    session["user_id"] = user.id
    session["role"] = user.role
    return redirect("/?verified=1")


@auth_bp.route("/api/auth/login", methods=["POST"])
def login():
    data = request.json or {}
    email = data.get("email", "").strip().lower()
    password = data.get("password", "")

    user = User.query.filter_by(email=email).first()
    if not user or not user.check_password(password):
        return jsonify({"error": "Invalid email or password"}), 401
    if not user.verified:
        return jsonify({"error": "Verify your email before signing in"}), 403

    session["user_id"] = user.id
    session["role"] = user.role
    return jsonify({"message": "Signed in", "role": user.role,
                     "name": f"{user.first_name} {user.last_name}"}), 200


@auth_bp.route("/api/auth/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"message": "Logged out"}), 200


@auth_bp.route("/api/auth/me", methods=["GET"])
def me():
    """
    Lets the frontend ask 'am I actually signed in?' against the real
    session, instead of trusting a JS variable that a page refresh
    would lose. Always returns 200 — check the `authenticated` field.
    """
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"authenticated": False}), 200
    user = User.query.get(user_id)
    if not user:
        session.clear()
        return jsonify({"authenticated": False}), 200
    if not user.verified:
        session.clear()
        return jsonify({"authenticated": False, "verification_required": True}), 200
    return jsonify({"authenticated": True, "role": user.role,
                     "name": f"{user.first_name} {user.last_name}", "id": user.id}), 200


@auth_bp.route("/login/google")
def login_google():
    if google is None:
        return jsonify({"error": "Google OAuth is not configured. Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET."}), 503
    session["google_role"] = request.args.get("role", "student")
    redirect_uri = url_for("auth.google_callback", _external=True)
    return google.authorize_redirect(redirect_uri)


@auth_bp.route("/google/callback")
def google_callback():
    if google is None:
        return jsonify({"error": "Google OAuth is not configured"}), 503
    try:
        token = google.authorize_access_token()
        user_info = token.get("userinfo") or google.userinfo()
    except Exception as exc:
        return jsonify({"error": f"Google sign-in failed: {exc}"}), 502

    email = (user_info.get("email") or "").strip().lower()
    if not email or not user_info.get("email_verified"):
        return jsonify({"error": "Google did not provide a verified email"}), 400
    name_parts = (user_info.get("name") or email.split("@")[0]).split(maxsplit=1)
    user = User.query.filter_by(email=email).first()
    if not user:
        role = session.pop("google_role", "student")
        if role not in ("student", "alumni"):
            role = "student"
        user = User(role=role, first_name=name_parts[0],
                    last_name=name_parts[1] if len(name_parts) > 1 else "User",
                    email=email, phone=f"google{secrets.token_hex(4)}",
                    auth_type="google", verified=True,
                    profile_pic=user_info.get("picture"))
        user.set_password(secrets.token_urlsafe(48))
        db.session.add(user)
    else:
        session.pop("google_role", None)
        user.verified = True
        user.auth_type = "google"
        user.profile_pic = user_info.get("picture") or user.profile_pic
    db.session.commit()
    session.clear()
    session["user_id"] = user.id
    session["role"] = user.role
    return redirect("/")


# ---------- admin: separate credentials, separate endpoint, separate table ----------

@auth_bp.route("/api/admin/login", methods=["POST"])
def admin_login():
    data = request.json or {}
    username = data.get("username", "").strip()
    password = data.get("password", "")

    admin = Admin.query.filter_by(username=username).first()
    if not admin or not admin.check_password(password):
        return jsonify({"error": "Invalid admin credentials"}), 401

    session.clear()  # never let a leftover student/alumni session coexist
    session["admin_id"] = admin.id
    return jsonify({"message": "Admin signed in", "username": admin.username}), 200


@auth_bp.route("/api/admin/logout", methods=["POST"])
@admin_required
def admin_logout():
    session.clear()
    return jsonify({"message": "Logged out"}), 200


@auth_bp.route("/api/admin/me", methods=["GET"])
def admin_me():
    """Same idea as /api/auth/me, but for the separate admin session key."""
    admin_id = session.get("admin_id")
    if not admin_id:
        return jsonify({"authenticated": False}), 200
    admin = Admin.query.get(admin_id)
    if not admin:
        session.clear()
        return jsonify({"authenticated": False}), 200
    return jsonify({"authenticated": True, "username": admin.username}), 200
