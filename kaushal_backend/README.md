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

Choose a new admin username and a unique strong password in Render's
Environment settings. Never put deployed credentials in this README or Git.

Open **http://127.0.0.1:5000/** — that's the actual website now, not just
an API. Everything (home, role selection, signup, dashboards, admin) is
one live app.

## What's real vs. simulated right now

| Feature | Status |
|---|---|
| Role selection → Sign up / Sign in | **Real** — hits `/api/auth/register` and `/api/auth/login` |
| Phone number | **Stored** — collected as profile contact data; no SMS or OTP is required |
| Session-based route guards | **Real** — every dashboard nav click asks the server "am I actually logged in?" via `/api/auth/me` / `/api/admin/me` before showing the page |
| Admin Portal login | **Real** — separate `/api/admin/login`, separate `admins` table, provisioned by `seed_admin.py` or deployment environment variables |
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
   requires the configured email provider; every attempt is stored in
   the `email_notifications` table.

## Email notifications

Render deployments should use Resend's HTTPS API because Render Free blocks
outbound SMTP. Configure these environment variables in Render:

```env
EMAIL_PROVIDER=resend
RESEND_API_KEY=re_...
EMAIL_FROM=KAUSHAL-X <verified-sender@your-domain.example>
```

Verify the sender/domain in Resend before using it. Email delivery failure does
not delete a registration; admins can verify the account or resend the link.

## Render deployment

The root `render.yaml` creates the web service and persistent PostgreSQL
database. Connect the GitHub repository to Render, review the Blueprint
resources, and supply `ADMIN_USERNAME`, `ADMIN_PASSWORD`, `EMAIL_FROM`, and
`RESEND_API_KEY` when prompted. Set the email sender to a verified Resend
identity. The health check is `/api/health`; the Gunicorn entry point is
`kaushal_backend.app:app`.

The Blueprint uses Render's smallest paid web and PostgreSQL plans. This
avoids Free web-service spin-down delays and Free Postgres's 30-day expiry.
Review the current Render pricing before applying the Blueprint. Render Free
can still be selected manually for a temporary demo, but it does not meet the
always-on or long-term data-retention requirements.

The app rejects production startup if `SECRET_KEY` or `DATABASE_URL` is
missing, so production will not silently use ephemeral SQLite storage.

If the web service was created manually in the Render Dashboard, the Blueprint
environment wiring is not applied automatically. Create a Render PostgreSQL
database, then open the web service's **Environment** settings and add
`DATABASE_URL` using the database's **Internal Database URL**. Keep the web
service and database in the same region, save the change, and redeploy. The
startup log names this setting if it is missing.

Previously committed credentials can remain visible in Git history even after
their files are removed. Rotate any credentials that were ever committed,
including the Render admin password and mail-provider credentials.

## Project structure

```
kaushal_backend/
├── __init__.py
├── app.py            # Flask app factory + serves frontend/index.html at "/"
├── models.py         # User (student/alumni) + separate Admin table
├── auth.py           # signup/login + /me session-check routes + admin login
├── admin_routes.py   # admin-only: list users, send email notifications
├── email_service.py  # Resend HTTPS API and local SMTP sender
├── seed_admin.py     # CLI-only way to create an admin account
├── requirements.txt
├── .env.example
└── frontend/
    └── index.html    # the full site — now calls the API instead of faking it
```
