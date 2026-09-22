"""
seed_admin.py
--------------
Run this once, locally or on the server, to create an admin login:

    python seed_admin.py

This is a CLI script, not an HTTP route — there is no "admin signup"
page anywhere in the app. That's the whole point: a student or alumni
can never create admin access for themselves through the website, no
matter what they enter, because the only code path that writes to the
`admins` table is this file, which only you can run.

Run it again to add more admin accounts (e.g. one per placement-cell
staff member).
"""

import getpass
from kaushal_backend.app import app
from kaushal_backend.models import db, Admin

with app.app_context():
    db.create_all()

    username = input("New admin username: ").strip()
    if not username:
        print("Username can't be empty.")
        raise SystemExit(1)

    if Admin.query.filter_by(username=username).first():
        print(f"An admin named '{username}' already exists.")
        raise SystemExit(1)

    password = getpass.getpass("New admin password: ")
    confirm = getpass.getpass("Confirm password: ")
    if password != confirm:
        print("Passwords didn't match.")
        raise SystemExit(1)
    if len(password) < 8:
        print("Use at least 8 characters for an admin password.")
        raise SystemExit(1)

    admin = Admin(username=username)
    admin.set_password(password)
    db.session.add(admin)
    db.session.commit()
    print(f"✅ Admin '{username}' created. Sign in at POST /api/admin/login")
