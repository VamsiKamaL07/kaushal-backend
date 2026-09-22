# KAUSHAL-X — Full-Stack Local Build

One Flask server now serves **both** the API and the website itself.
No separate Live Server step, no CORS juggling — just:

## 1. Set up

```bash
cd kaushal_backend
python -m venv venv
```

Windows PowerShell:
```powershell
venv\Scripts\Activate.ps1
```
macOS/Linux:
```bash
source venv/bin/activate
```

Then:
```bash
pip install -r requirements.txt
```
Windows:
```powershell
copy .env.example .env
```
macOS/Linux:
```bash
cp .env.example .env
```

## 2. Create your admin login (one time)

```bash
python seed_admin.py
```
Remember the username/password you set — that's your Admin Portal login,
completely separate from student/alumni accounts.

## 3. Run it

```bash
python -m kaushal_backend.app
```

For Render, use this start command from the repository root:

```bash
gunicorn kaushal_backend.app:app
```

Set `ADMIN_USERNAME` and `ADMIN_PASSWORD` in Render Environment Variables.
The app creates or updates that admin account on startup; local SQLite users
and admin accounts are not copied to Render automatically.

Open **http://127.0.0.1:5000/** — that's the actual website now, not just
an API. Everything (home, role selection, signup, dashboards, admin) is
one live app.

## What's real vs. simulated right now

| Feature | Status |
|---|---|
| Role selection → Sign up / Sign in | **Real** — hits `/api/auth/register` and `/api/auth/login` |
| Phone number | **Stored** — collected as profile contact data; no SMS or OTP is required |
| Session-based route guards | **Real** — every dashboard nav click asks the server "am I actually logged in?" via `/api/auth/me` / `/api/admin/me` before showing the page |
| Admin Portal login | **Real** — separate `/api/admin/login`, separate `admins` table, only creatable via `seed_admin.py` |
| Admin "Send Email Notification" | **Real** — selects actual signed-up students/alumni and sends email via `/api/admin/notify` |
| Google Sign-In button | **Real when configured** — Authlib OAuth stores verified Google identity, profile picture, role, and auth type |
| Student skill profile and recommendations | **Real** — `/api/student/profile` stores skills/interests and `/api/recommend` uses alumni feedback |
| Alumni "Submit Placement Experience" | **Real** — `/api/alumni/submit` stores company, role, salary, skills, and experience |
| Admin analytics and recipient filtering | **Real** — `/api/admin/analytics` and role/skill/company filters query the database |

The auth + email-notify pipeline is genuinely wired end to end.
The learning roadmap and company cards remain presentation guidance, while
the skill profile, alumni outcomes, recommendations, analytics, and email
recipient selection now use the database-backed APIs.

## Try the full flow

1. Visit `http://127.0.0.1:5000/`
2. Click **Get Started** → pick **Pursuing Student** or **Alumni** → Continue
3. Fill in the sign-up form and click **Create account**
4. You land in your real, session-protected dashboard
5. Open a private/incognito window (or click **Reset flow**) and go to
   `http://127.0.0.1:5000/` → click **Admin** in the demo nav bar → sign
   in with the admin account you created in step 2
6. In the admin dashboard, select students or alumni by email, enter a
   subject and message, and click **Send email notification**. Delivery
   requires the SMTP settings below; every attempt is stored locally in
   the `email_notifications` table.

## Email notifications

The app uses standard SMTP and no paid SMS service. Gmail can be used with
a free account and a Google app password:

```env
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your-email@gmail.com
SMTP_PASSWORD=your-16-character-app-password
EMAIL_FROM=your-email@gmail.com
```

Create the app password in your Google Account security settings after
enabling two-step verification. Keep it only in `.env` and never commit it.

## Project structure

```
kaushal_backend/
├── __init__.py
├── app.py            # Flask app factory + serves frontend/index.html at "/"
├── models.py         # User (student/alumni) + separate Admin table
├── auth.py           # signup/login + /me session-check routes + admin login
├── admin_routes.py   # admin-only: list users, send email notifications
├── email_service.py  # SMTP email sender
├── seed_admin.py     # CLI-only way to create an admin account
├── requirements.txt
├── .env.example
└── frontend/
    └── index.html    # the full site — now calls the API instead of faking it
```
