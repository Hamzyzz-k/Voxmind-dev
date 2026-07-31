"""OTP email delivery.

Two transports, tried in order:

1. **Brevo HTTP API** (preferred). Render's free web services block outbound
   traffic to SMTP ports 25, 465 and 587, so SMTP simply cannot leave the
   container there — the connection times out no matter how correct the
   credentials are. The HTTP API runs over ordinary HTTPS and is unaffected.
2. **SMTP** (fallback). Still useful for local development and for any host
   that permits SMTP egress.

No dummy fallback: if neither transport is configured, the caller
(routes/auth.py) returns an honest 503 rather than pretending an email went
out.
"""

import asyncio
import logging
import smtplib
from email.message import EmailMessage

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.config import get_settings

logger = logging.getLogger(__name__)

BREVO_ENDPOINT = "https://api.brevo.com/v3/smtp/email"


class EmailDeliveryError(Exception):
    pass


class _TransientEmailError(Exception):
    pass


def _build_body(code: str, expiry_minutes: int) -> tuple[str, str]:
    subject = "Your VoxMind verification code"
    body = (
        f"Your VoxMind verification code is: {code}\n\n"
        f"This code expires in {expiry_minutes} minutes. If you didn't request this, "
        f"you can ignore this email."
    )
    return subject, body


# --- Transport 1: Brevo HTTP API ---


async def _send_via_api(to_email: str, subject: str, body: str) -> None:
    settings = get_settings()
    payload = {
        "sender": {"email": settings.smtp_from, "name": "VoxMind"},
        "to": [{"email": to_email}],
        "subject": subject,
        "textContent": body,
    }
    headers = {
        "api-key": settings.brevo_api_key,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(BREVO_ENDPOINT, headers=headers, json=payload)

    if response.status_code in (200, 201, 202):
        return

    detail = response.text[:300]
    # 5xx is worth another attempt; a rejected key or unverified sender is not.
    if response.status_code >= 500:
        raise _TransientEmailError(f"Brevo API {response.status_code}: {detail}")
    raise EmailDeliveryError(f"Brevo API {response.status_code}: {detail}")


# --- Transport 2: SMTP ---


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
    retry=retry_if_exception_type((_TransientEmailError, smtplib.SMTPException, OSError)),
)
async def _deliver(to_email: str, subject: str, body: str) -> str:
    settings = get_settings()

    if settings.brevo_api_configured:
        await _send_via_api(to_email, subject, body)
        return "brevo_api"

    if settings.smtp_configured:
        await asyncio.to_thread(_send_sync, to_email, subject, body)
        return "smtp"

    raise EmailDeliveryError("No email transport is configured")


async def send_otp_email(to_email: str, code: str, expiry_minutes: int) -> str:
    """Sends the code and returns which transport delivered it."""
    settings = get_settings()
    if not settings.email_configured:
        raise EmailDeliveryError("No email transport is configured")

    subject, body = _build_body(code, expiry_minutes)
    try:
        transport = await _deliver(to_email, subject, body)
    except _TransientEmailError as exc:
        raise EmailDeliveryError(str(exc)) from exc

    logger.info("OTP email sent via %s", transport)
    return transport
