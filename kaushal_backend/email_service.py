"""Email delivery through Resend's HTTPS API or local-development SMTP."""

import os
import smtplib
from email.message import EmailMessage

import requests


class EmailError(Exception):
    """Raised when an email cannot be sent."""


def email_configuration() -> tuple[str, bool]:
    provider = os.getenv("EMAIL_PROVIDER", "smtp").strip().lower()
    if provider == "resend":
        configured = bool(os.getenv("RESEND_API_KEY", "").strip() and os.getenv("EMAIL_FROM", "").strip())
    elif provider == "smtp":
        configured = bool(
            os.getenv("SMTP_USERNAME", "").strip()
            and os.getenv("SMTP_PASSWORD", "").strip()
            and os.getenv("EMAIL_FROM", "").strip()
        )
    else:
        configured = False
    return provider, configured


def send_email(recipient: str, subject: str, message: str) -> None:
    provider, configured = email_configuration()
    sender = os.getenv("EMAIL_FROM", "").strip()
    if not configured:
        if provider not in ("resend", "smtp"):
            raise EmailError("Unsupported EMAIL_PROVIDER. Use 'resend' or 'smtp'.")
        required = "RESEND_API_KEY and EMAIL_FROM" if provider == "resend" else "SMTP_USERNAME, SMTP_PASSWORD, and EMAIL_FROM"
        raise EmailError(f"{provider.capitalize()} email is not configured. Set {required}.")

    if provider == "resend":
        try:
            response = requests.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {os.environ['RESEND_API_KEY'].strip()}"},
                json={"from": sender, "to": [recipient], "subject": subject, "text": message},
                timeout=(3.05, 8),
            )
        except requests.RequestException as exc:
            raise EmailError(f"Resend request failed ({type(exc).__name__}).") from exc
        if not response.ok:
            raise EmailError(f"Resend rejected the email (HTTP {response.status_code}).")
        return

    host = os.getenv("SMTP_HOST", "smtp.gmail.com").strip() or "smtp.gmail.com"
    port = int(os.getenv("SMTP_PORT", "587"))
    username = os.getenv("SMTP_USERNAME", "").strip()
    password = "".join(os.getenv("SMTP_PASSWORD", "").split())

    email = EmailMessage()
    email["From"] = sender
    email["To"] = recipient
    email["Subject"] = subject
    email.set_content(message)

    try:
        if port == 465:
            with smtplib.SMTP_SSL(host, port, timeout=8) as smtp:
                smtp.login(username, password)
                smtp.send_message(email)
        else:
            with smtplib.SMTP(host, port, timeout=8) as smtp:
                smtp.starttls()
                smtp.login(username, password)
                smtp.send_message(email)
    except (OSError, smtplib.SMTPException) as exc:
        raise EmailError(f"SMTP delivery failed ({type(exc).__name__}).") from exc