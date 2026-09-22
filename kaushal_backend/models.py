"""
models.py
----------
Two separate tables by design:

  User   — students and alumni. Created only through /api/auth/register.
  Admin  — placement-cell staff. Created ONLY by running seed_admin.py
           on the server/your machine. There is no HTTP route that can
           create an Admin row, so a student or alumni account — no
           matter what email/password they use — can never become an
           admin, and the admin login endpoint never even queries the
           User table, so credentials can't cross over by coincidence
           either.
"""

from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    role = db.Column(db.String(20), nullable=False)  # 'student' or 'alumni'
    first_name = db.Column(db.String(80), nullable=False)
    last_name = db.Column(db.String(80), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    phone = db.Column(db.String(10), unique=True, nullable=False)
    skills = db.Column(db.Text, nullable=False, default="")
    company = db.Column(db.String(100))
    password_hash = db.Column(db.String(255), nullable=False)
    profile_pic = db.Column(db.String(500))
    verified = db.Column(db.Boolean, nullable=False, default=False)
    auth_type = db.Column(db.String(20), nullable=False, default="manual")
    verification_token = db.Column(db.String(128), unique=True)
    verification_expires_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)


class Admin(db.Model):
    __tablename__ = "admins"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)


class EmailNotification(db.Model):
    __tablename__ = "email_notifications"

    id = db.Column(db.Integer, primary_key=True)
    recipient_email = db.Column(db.String(120), nullable=False)
    subject = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), nullable=False)
    error = db.Column(db.String(500))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class StudentProfile(db.Model):
    __tablename__ = "student_profiles"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), unique=True, nullable=False)
    skills = db.Column(db.Text, nullable=False, default="")
    interests = db.Column(db.Text, nullable=False, default="")
    cgpa = db.Column(db.Float)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AlumniProfile(db.Model):
    __tablename__ = "alumni_profiles"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), unique=True, nullable=False)
    company = db.Column(db.String(160))
    job_role = db.Column(db.String(160))
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AlumniFeedback(db.Model):
    __tablename__ = "alumni_feedback"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    company = db.Column(db.String(160), nullable=False)
    role = db.Column(db.String(160), nullable=False)
    salary = db.Column(db.Float, nullable=False)
    skills_needed = db.Column(db.Text, nullable=False, default="")
    experience = db.Column(db.Text, nullable=False, default="")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
