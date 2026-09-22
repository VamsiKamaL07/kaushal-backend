"""Authenticated student/alumni data APIs and admin analytics."""

from collections import Counter
from datetime import datetime

from flask import Blueprint, jsonify, request

from auth import admin_required, login_required
from models import AlumniFeedback, AlumniProfile, StudentProfile, User, db

data_bp = Blueprint("data", __name__)


def _split_values(value):
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [item.strip() for item in str(value or "").split(",") if item.strip()]


@data_bp.route("/api/student/profile", methods=["GET", "POST"])
@login_required("student")
def student_profile():
    profile = StudentProfile.query.filter_by(user_id=request_user_id()).first()
    if request.method == "POST":
        data = request.json or {}
        skills = _split_values(data.get("skills"))
        interests = _split_values(data.get("interests"))
        try:
            cgpa = float(data["cgpa"]) if data.get("cgpa") not in (None, "") else None
        except (TypeError, ValueError):
            return jsonify({"error": "CGPA must be a number"}), 400
        if cgpa is not None and not 0 <= cgpa <= 10:
            return jsonify({"error": "CGPA must be between 0 and 10"}), 400
        if not skills:
            return jsonify({"error": "Select at least one skill"}), 400
        if profile is None:
            profile = StudentProfile(user_id=request_user_id())
            db.session.add(profile)
        profile.skills = ",".join(skills)
        profile.interests = ",".join(interests)
        profile.cgpa = cgpa
        user = User.query.get(request_user_id())
        user.skills = profile.skills
        db.session.commit()
    return jsonify(_student_profile_json(profile))


def request_user_id():
    from flask import session
    return session["user_id"]


def _student_profile_json(profile):
    if profile is None:
        return {"skills": [], "interests": [], "cgpa": None}
    return {"skills": _split_values(profile.skills), "interests": _split_values(profile.interests), "cgpa": profile.cgpa}


@data_bp.route("/api/alumni/submit", methods=["POST"])
@login_required("alumni")
def submit_alumni_feedback():
    data = request.json or {}
    company = str(data.get("company") or "").strip()
    role = str(data.get("role") or "").strip()
    experience = str(data.get("experience") or "").strip()
    skills = _split_values(data.get("skills_needed"))
    try:
        salary = float(data.get("salary"))
    except (TypeError, ValueError):
        return jsonify({"error": "Salary must be a number"}), 400
    if not company or not role or salary < 0 or not skills or not experience:
        return jsonify({"error": "Company, role, salary, skills, and experience are required"}), 400
    feedback = AlumniFeedback(user_id=request_user_id(), company=company, role=role,
                              salary=salary, skills_needed=",".join(skills), experience=experience)
    profile = AlumniProfile.query.filter_by(user_id=request_user_id()).first()
    if profile is None:
        profile = AlumniProfile(user_id=request_user_id())
        db.session.add(profile)
    profile.company = company
    profile.job_role = role
    user = User.query.get(request_user_id())
    user.company = company
    user.skills = ",".join(skills)
    db.session.add(feedback)
    db.session.commit()
    return jsonify({"message": "Experience saved", "id": feedback.id}), 201


@data_bp.route("/api/recommend", methods=["POST"])
@login_required("student")
def recommend():
    data = request.json or {}
    skills = set(_split_values(data.get("skills")))
    if not skills:
        profile = StudentProfile.query.filter_by(user_id=request_user_id()).first()
        skills = set(_split_values(profile.skills if profile else ""))
    feedback = AlumniFeedback.query.all()
    counts = Counter(skill for item in feedback for skill in _split_values(item.skills_needed))
    top_skills = [skill for skill, _ in counts.most_common(8)]
    gaps = [skill for skill in top_skills if skill not in skills]
    role_counts = Counter(item.role for item in feedback)
    return jsonify({"top_skills": top_skills, "skill_gaps": gaps, "top_role": role_counts.most_common(1)[0][0] if role_counts else "Build your profile", "feedback_count": len(feedback)})


@data_bp.route("/api/admin/analytics", methods=["GET"])
@admin_required
def admin_analytics():
    feedback = AlumniFeedback.query.all()
    skills = Counter(skill for item in feedback for skill in _split_values(item.skills_needed))
    companies = Counter(item.company for item in feedback)
    salaries = [item.salary for item in feedback]
    recent = sorted(feedback, key=lambda item: item.created_at or datetime.min, reverse=True)[:8]
    return jsonify({
        "feedback_count": len(feedback),
        "average_salary": round(sum(salaries) / len(salaries), 2) if salaries else 0,
        "top_skills": skills.most_common(8),
        "companies": companies.most_common(8),
        "recent": [{"company": item.company, "role": item.role, "salary": item.salary, "created_at": item.created_at.isoformat() if item.created_at else None} for item in recent],
        "users": User.query.count(),
    })