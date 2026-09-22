"""Change the existing admin username and password interactively."""

import getpass
from kaushal_backend.app import app
from kaushal_backend.models import db, Admin

with app.app_context():
    admins = Admin.query.order_by(Admin.id).all()
    if not admins:
        print("No admin account exists. Run seed_admin.py first.")
        raise SystemExit(1)

    current_username = input("Current admin username: ").strip()
    admin = Admin.query.filter_by(username=current_username).first()
    if not admin:
        print("Admin account not found.")
        raise SystemExit(1)

    new_username = input("New admin username: ").strip()
    if not new_username:
        print("Username cannot be empty.")
        raise SystemExit(1)

    existing = Admin.query.filter(Admin.username == new_username, Admin.id != admin.id).first()
    if existing:
        print("That username is already in use.")
        raise SystemExit(1)

    password = getpass.getpass("New admin password: ")
    confirm = getpass.getpass("Confirm new password: ")
    if password != confirm:
        print("Passwords did not match.")
        raise SystemExit(1)
    if len(password) < 8:
        print("Use at least 8 characters for the admin password.")
        raise SystemExit(1)

    admin.username = new_username
    admin.set_password(password)
    db.session.commit()
    print(f"Admin credentials updated for '{new_username}'.")
