"""SMTP email delivery for admin notifications."""

import os
import smtplib
import socket
import time
from email.message import EmailMessage


class EmailError(Exception):
    """Raised when an email cannot be sent."""


def send_email(recipient: str, subject: str, message: str) -> None:
    host = os.getenv("SMTP_HOST", "smtp.gmail.com").strip() or "smtp.gmail.com"
    if host.lower() in ("smtp.gmail.com:587", "smtp.gmail.com:465"):
        host = "smtp.gmail.com"
    port = int(os.getenv("SMTP_PORT", "587"))
    username = os.getenv("SMTP_USERNAME", "").strip()
    password = "".join(os.getenv("SMTP_PASSWORD", "").split())
    sender = os.getenv("EMAIL_FROM", username).strip()

    if not username or not password or not sender:
        raise EmailError("SMTP email is not configured. Set SMTP_USERNAME, SMTP_PASSWORD, and EMAIL_FROM.")

    email = EmailMessage()
    email["From"] = sender
    email["To"] = recipient
    email["Subject"] = subject
    email.set_content(message)

    last_error = None
    for attempt in range(2):
        try:
            with smtplib.SMTP(host, port, timeout=20) as smtp:
                smtp.starttls()
                smtp.login(username, password)
                smtp.send_message(email)
            return
        except (OSError, smtplib.SMTPException) as exc:
            last_error = exc
            if attempt == 0 and isinstance(exc, socket.gaierror):
                time.sleep(1)
            else:
                break
    raise EmailError(f"Email delivery failed: {last_error}") from last_error