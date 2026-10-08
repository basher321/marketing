"""Transactional email sender.

Dev mode: when SMTP is not configured (empty host, or the placeholder "changeme" user or
password from .env), the whole email - body included - is written to the backend console at
WARNING level instead of being sent, so flows like password reset stay usable locally. Only
in this mode is an email body ever logged. With real SMTP settings the email is sent and
nothing of its body is logged.
"""
import logging
import smtplib
from email.message import EmailMessage

from app.config import get_settings

settings = get_settings()

logger = logging.getLogger(__name__)

PLACEHOLDER = "changeme"


def smtp_configured() -> bool:
    password = settings.SMTP_PASSWORD.get_secret_value()
    return bool(settings.SMTP_HOST) and settings.SMTP_USER not in ("", PLACEHOLDER) and password not in ("", PLACEHOLDER)


def send_email(to: str, subject: str, body: str) -> None:
    if not smtp_configured():
        logger.warning(
            "\n==== DEV MODE EMAIL (SMTP not configured - not sent) ====\n"
            "To: %s\nSubject: %s\n\n%s\n==========================================================",
            to,
            subject,
            body,
        )
        return

    message = EmailMessage()
    message["From"] = settings.SMTP_FROM_EMAIL
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)

    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15) as server:
        server.starttls()
        server.login(settings.SMTP_USER, settings.SMTP_PASSWORD.get_secret_value())
        server.send_message(message)
