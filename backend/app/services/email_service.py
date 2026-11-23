"""Transactional email delivery for account verification and password reset."""
from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage
from urllib.parse import quote

from app.core.config import settings

logger = logging.getLogger("cinerank.email")
_PURPOSE_LABELS = {
    "verify_email": "Verify your CineRank email",
    "reset_password": "Reset your CineRank password",
}


class EmailNotConfigured(RuntimeError):
    """Raised when SMTP delivery is requested without a configured server."""


class EmailDeliveryError(RuntimeError):
    """Raised when the configured mail server rejects or cannot send a message."""


def is_configured() -> bool:
    return bool(settings.SMTP_HOST.strip() and settings.SMTP_FROM_EMAIL.strip())


def _frontend_link(path: str, token: str) -> str:
    base = settings.FRONTEND_BASE_URL.rstrip("/")
    return f"{base}/{path.lstrip('/')}?token={quote(token, safe='')}"


def _send(to_email: str, subject: str, body: str) -> None:
    if not is_configured():
        raise EmailNotConfigured("SMTP delivery is not configured")

    message = EmailMessage()
    message["From"] = settings.SMTP_FROM_EMAIL
    message["To"] = to_email
    message["Subject"] = subject
    message.set_content(body)

    try:
        if settings.SMTP_SSL:
            client = smtplib.SMTP_SSL(
                settings.SMTP_HOST,
                settings.SMTP_PORT,
                timeout=settings.SMTP_TIMEOUT_SECONDS,
            )
        else:
            client = smtplib.SMTP(
                settings.SMTP_HOST,
                settings.SMTP_PORT,
                timeout=settings.SMTP_TIMEOUT_SECONDS,
            )
        with client:
            if settings.SMTP_STARTTLS and not settings.SMTP_SSL:
                client.starttls()
            if settings.SMTP_USERNAME:
                client.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
            client.send_message(message)
    except (OSError, smtplib.SMTPException) as exc:
        logger.warning("email_delivery_failed purpose_subject=%s", subject[:80])
        raise EmailDeliveryError("Email could not be delivered") from exc


def send_verification_email(to_email: str, token: str) -> None:
    link = _frontend_link("/verify-email", token)
    _send(
        to_email,
        _PURPOSE_LABELS["verify_email"],
        "Confirm this email address to finish setting up your CineRank account.\n\n"
        f"Verify your email: {link}\n\n"
        f"This link expires in {settings.EMAIL_VERIFICATION_TTL_HOURS} hours. "
        "If you did not create a CineRank account, you can ignore this message.\n",
    )


def send_password_reset_email(to_email: str, token: str) -> None:
    link = _frontend_link("/reset-password", token)
    _send(
        to_email,
        _PURPOSE_LABELS["reset_password"],
        "Use this link to choose a new password for your CineRank account.\n\n"
        f"Reset your password: {link}\n\n"
        f"This link expires in {settings.PASSWORD_RESET_TTL_MINUTES} minutes. "
        "If you did not request a reset, you can ignore this message. "
        "Your current password stays active until a new one is saved.\n",
    )
