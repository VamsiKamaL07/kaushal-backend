import os
import unittest
from unittest.mock import patch


class RegistrationRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.env_patch = patch.dict(os.environ, {
            "DATABASE_URL": "sqlite://",
            "SECRET_KEY": "test-secret-key",
        })
        self.env_patch.start()
        os.environ.pop("RENDER", None)
        os.environ.pop("FLASK_ENV", None)

        from kaushal_backend.app import create_app

        self.app = create_app()
        self.app.config.update(TESTING=True)
        self.client = self.app.test_client()

    def tearDown(self):
        from kaushal_backend.models import db

        with self.app.app_context():
            db.session.remove()
            db.drop_all()
            db.engine.dispose()
        self.env_patch.stop()

    def register_user(self):
        return self.client.post("/api/auth/register", json={
            "role": "student",
            "firstName": "Test",
            "lastName": "Student",
            "email": "student@example.com",
            "phone": "9876543210",
            "password": "test-password",
        })

    def test_missing_production_database_url_explains_render_setup(self):
        from kaushal_backend.app import create_app

        with patch.dict(os.environ, {
            "RENDER": "true",
            "SECRET_KEY": "test-secret-key",
            "DATABASE_URL": "",
        }):
            with self.assertRaisesRegex(RuntimeError, "Internal Database URL"):
                create_app()

    def sign_in_admin(self):
        from kaushal_backend.models import Admin, db

        with self.app.app_context():
            admin = Admin(username="placement-admin")
            admin.set_password("admin-password")
            db.session.add(admin)
            db.session.commit()
        return self.client.post("/api/admin/login", json={
            "username": "placement-admin",
            "password": "admin-password",
        })

    def test_signup_keeps_user_and_audits_failed_email(self):
        from kaushal_backend.auth import EmailError
        from kaushal_backend.models import EmailNotification, User

        with patch("kaushal_backend.auth.send_email", side_effect=EmailError("provider unavailable")):
            response = self.register_user()

        self.assertEqual(response.status_code, 201)
        self.assertFalse(response.json["email_sent"])
        with self.app.app_context():
            self.assertEqual(User.query.filter_by(email="student@example.com").count(), 1)
            notification = EmailNotification.query.one()
            self.assertEqual(notification.status, "failed")
            self.assertIn("provider unavailable", notification.error)

    def test_admin_can_verify_user_but_public_user_cannot(self):
        from kaushal_backend.auth import EmailError
        from kaushal_backend.models import User, db

        with patch("kaushal_backend.auth.send_email", side_effect=EmailError("not configured")):
            self.register_user()
        with self.app.app_context():
            user_id = User.query.filter_by(email="student@example.com").one().id

        denied = self.client.post(f"/api/admin/users/{user_id}/verify")
        self.assertEqual(denied.status_code, 401)
        self.assertEqual(self.sign_in_admin().status_code, 200)
        verified = self.client.post(f"/api/admin/users/{user_id}/verify")
        self.assertEqual(verified.status_code, 200)
        with self.app.app_context():
            self.assertTrue(db.session.get(User, user_id).verified)

    def test_admin_resend_failure_keeps_user_and_audit(self):
        from kaushal_backend.admin_routes import EmailError
        from kaushal_backend.models import EmailNotification, User

        with patch("kaushal_backend.auth.send_email", side_effect=EmailError("not configured")):
            self.register_user()
        with self.app.app_context():
            user_id = User.query.filter_by(email="student@example.com").one().id
        self.assertEqual(self.sign_in_admin().status_code, 200)

        with patch("kaushal_backend.admin_routes.send_email", side_effect=EmailError("provider unavailable")):
            response = self.client.post(f"/api/admin/users/{user_id}/resend-verification")

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json["email_sent"])
        with self.app.app_context():
            self.assertEqual(User.query.filter_by(id=user_id).count(), 1)
            self.assertEqual(EmailNotification.query.order_by(EmailNotification.id.desc()).first().status, "failed")


if __name__ == "__main__":
    unittest.main()