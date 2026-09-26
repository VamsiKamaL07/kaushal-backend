"""
app.py
-------
Entry point. Run with:  python app.py
API will be at http://localhost:5000
"""

import os
from sqlalchemy import inspect, text
from flask import Flask, send_from_directory
from flask_cors import CORS
from dotenv import load_dotenv
from werkzeug.middleware.proxy_fix import ProxyFix

from kaushal_backend.models import Admin, db
from kaushal_backend.auth import auth_bp, configure_oauth
from kaushal_backend.admin_routes import admin_bp
from kaushal_backend.data_routes import data_bp

load_dotenv()  # reads .env into environment variables

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")


def migrate_user_columns():
    """Add searchable user fields and auth columns to existing databases."""
    inspector = inspect(db.engine)
    columns = {column["name"] for column in inspector.get_columns("users")}
    additions = {
        "skills": "TEXT NOT NULL DEFAULT ''",
        "company": "VARCHAR(100)",
        "profile_pic": "VARCHAR(500)",
        "verified": "BOOLEAN NOT NULL DEFAULT TRUE",
        "auth_type": "VARCHAR(20) NOT NULL DEFAULT 'manual'",
        "verification_token": "VARCHAR(128)",
        "verification_expires_at": "TIMESTAMP",
    }
    for name, definition in additions.items():
        if name not in columns:
            db.session.execute(text(f"ALTER TABLE users ADD COLUMN {name} {definition}"))
    db.session.execute(text("""
        UPDATE users
        SET skills = COALESCE((
            SELECT skills FROM student_profiles
            WHERE student_profiles.user_id = users.id
        ), '')
        WHERE role = 'student' AND (skills IS NULL OR skills = '')
    """))
    db.session.execute(text("""
        UPDATE users
        SET company = COALESCE((
            SELECT company FROM alumni_profiles
            WHERE alumni_profiles.user_id = users.id
        ), company)
        WHERE role = 'alumni' AND (company IS NULL OR company = '')
    """))
    db.session.commit()


def provision_admin_from_environment():
    """Create or update the deployment admin when credentials are configured."""
    username = os.getenv("ADMIN_USERNAME", "").strip()
    password = os.getenv("ADMIN_PASSWORD", "")
    if not username or not password:
        return
    admin = Admin.query.filter_by(username=username).first()
    if admin is None:
        admin = Admin(username=username)
        db.session.add(admin)
    admin.set_password(password)
    db.session.commit()


def create_app() -> Flask:
    app = Flask(__name__, static_folder=None)

    production = os.getenv("RENDER", "").lower() == "true" or os.getenv("FLASK_ENV") == "production"
    secret_key = os.getenv("SECRET_KEY", "")
    database_url = os.getenv("DATABASE_URL", "").strip()
    if production and not secret_key:
        raise RuntimeError("SECRET_KEY must be set in production.")
    if production and not database_url:
        raise RuntimeError(
            "DATABASE_URL is missing. Create a Render PostgreSQL database, then add its Internal Database URL "
            "to this web service as the DATABASE_URL environment variable and redeploy."
        )
    if not database_url:
        database_url = "sqlite:///kaushalx.db"
    if database_url.startswith("postgres://"):
        database_url = "postgresql+psycopg://" + database_url[len("postgres://"):]
    elif database_url.startswith("postgresql://"):
        database_url = "postgresql+psycopg://" + database_url[len("postgresql://"):]

    app.config["SECRET_KEY"] = secret_key or "local-development-only-change-me"
    app.config["SQLALCHEMY_DATABASE_URI"] = database_url
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SECURE"] = os.getenv("SESSION_COOKIE_SECURE", str(production)).lower() == "true"
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"pool_pre_ping": True}

    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    db.init_app(app)
    configure_oauth(app)

    # Allow your frontend origin(s) to send cookies cross-origin.
    # Replace "*" with your actual frontend URL(s) before deploying.
    CORS(app, supports_credentials=True, origins=os.getenv("FRONTEND_ORIGIN", "*"))

    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(data_bp)

    with app.app_context():
        db.create_all()
        migrate_user_columns()
        provision_admin_from_environment()

    @app.route("/api/health")
    def health():
        return {"status": "ok"}

    # Serve the frontend itself — visiting http://127.0.0.1:5000/ now
    # loads the actual site, not a 404. The API and the site share one
    # origin, so session cookies just work without any CORS juggling.
    @app.route("/")
    def serve_index():
        return send_from_directory(FRONTEND_DIR, "index.html")

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", debug=True, port=int(os.getenv("PORT", "5000")))
