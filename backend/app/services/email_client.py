"""SMTP email delivery for OTP codes. No dummy fallback — if SMTP isn't
configured, the caller (routes/auth.py) returns an honest 503 rather than
pretending an email went out."""

import asyncio
import smtplib
from email.message import EmailMessage

from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.config import get_settings


class EmailDeliveryError(Exception):
    pass


def _send_sync(to_email: str, subject: str, body: str) -> None:
    settings = get_settings()
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings.smtp_from
    msg["To"] = to_email
    msg.set_content(body)

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as server:
        server.starttls()
        server.login(settings.smtp_user, settings.smtp_password)
        server.send_message(msg)


@retry(
    reraise=True,
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    retry=retry_if_exception_type((smtplib.SMTPException, OSError)),
)
async def send_otp_email(to_email: str, code: str, expiry_minutes: int) -> None:
    settings = get_settings()
    if not settings.smtp_configured:
        raise EmailDeliveryError("SMTP is not configured")

    subject = "Your VoxMind verification code"
    body = (
        f"Your VoxMind verification code is: {code}\n\n"
        f"This code expires in {expiry_minutes} minutes. If you didn't request this, "
        f"you can ignore this email."
    )
    await asyncio.to_thread(_send_sync, to_email, subject, body)
